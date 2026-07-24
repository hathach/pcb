"""pcbnew driver: route the SI-critical trace bundle + the SWD/NRESET/VTref
tree (Task 13).

Run: python3 hw/route_trace.py

Routes, on the board saved by `hw/build_board.py --place`:

  - TRACECLK, TD0-3 (+ source-side GP1-5): F_Cu only, Trace-class width
    (0.3mm), no vias (SI rule -- DESIGN.md SS5.4). Each Rt->J3 run must
    cross the J1B breakout row's own THT pads (1.7x1.7mm at 2.54mm pitch,
    so only ~0.84mm gaps between columns) -- each net jogs sideways by one
    PICO-pin-pitch to land in an adjacent gap before descending. Rt1/
    TRACECLK jogs toward its nearer gap (the *shortest* natural Rt->J3
    run of the five, ~17.7mm); Rt2-5 deliberately jog the OTHER way (a
    "wrong-way" detour) to burn extra length and close most of the
    natural spread; a length-matching meander (see `_meander`) tops each
    up to Rt1's length exactly (spread ~0.0mm, see task-13-report.md).
    Each net's GP-segment jog direction is the OPPOSITE of its own TDx
    jog, so the two paths -- which share the ~1mm y-band between Rt's
    two pads -- diverge instead of crossing.

  - SWDIO, SWCLK: daisy chain J3-J4-J6-J7 via a B_Cu trunk.
  - NRESET: PICO.30 -> J3.10 -> J6.10 -> SW1.1 via B_Cu.
  - P3V3 (VTref taps only -- the rest of this net is Task 14's job):
    PICO.36 -> J3.1 -> J6.1 via B_Cu, necked to Default width (0.2mm) for
    the PICO/J1B header-row crossing (0.5mm does not fit an 0.84mm
    pin-pitch gap with clearance to spare: 0.17mm < 0.2mm required; 0.2mm
    clears with margin, 0.32mm).

  B_Cu is used for all four of these because J3/J4/J6/J7/SW1 are all SMD
  (F_Cu-only) -- B_Cu is unobstructed under them; only the THT parts
  PICO/J1B/J2B/JP2/JP3 carry B_Cu copper, and only PICO's own header row
  and J1B's breakout row lie on the NRESET/P3V3 descent from PICO (each
  crossed once, through an unused inter-pin gap, same technique as the
  trace bundle). SWDIO and SWCLK share the same 4 physical connectors, so
  a "shallower" net's full-width B_Cu trunk is unavoidably crossed by a
  "deeper" net's vertical pad-to-trunk run wherever their X ranges
  overlap (they mostly do, since all four connectors are shared) --
  `_spike_to_trunk` hops each such crossing onto F_Cu (clear in this
  region -- verified empty of copper except a mounting hole far to the
  west) for a short span and back, via two vias.

Idempotent: skip-if-already-routed -- before adding tracks/vias for a
net, check whether it already has any (BOARD.GetTracks() returns both
PCB_TRACK and PCB_VIA, since PCB_VIA subclasses PCB_TRACK), so re-running
is a no-op. Matches place.py/build_board.py's skip-if-present pattern;
never BOARD.Remove() (see build_board.py's docstrings for why).
"""

from __future__ import annotations

import os
import sys

if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pcbnew

BOARD_FILE = "pico2_trace.kicad_pcb"

# --- Trace bundle ------------------------------------------------------------
# rt_ref, gp_net, td_net, pico_pad (source), j3_pad (dest),
# jog_dir (+1 = jog toward the higher-numbered neighboring PICO pin,
# -1 = toward the lower), meander_passes (length-matching, see _meander).
_TRACE_CHAIN = [
    ("Rt1", "GP1", "TRACECLK", "2", "12", +1, 0),
    ("Rt2", "GP2", "TD0", "4", "14", -1, 1),
    ("Rt3", "GP3", "TD1", "5", "16", -1, 2),
    ("Rt4", "GP4", "TD2", "6", "18", -1, 3),
    ("Rt5", "GP5", "TD3", "7", "20", -1, 4),
]

_GP_JOG_MM = 0.72         # clears Rt's own sibling pad (half-width 0.32mm +
                          # 0.25mm Trace clearance + 0.1mm half of a *0.2mm*
                          # GP track = 0.67mm min) *and* stays clear of the
                          # neighboring Rt's TDx lane-jog 1.27mm away (needs
                          # <=0.77mm) -- see task-13-report.md "GP jog width"
_GP_WIDTH_MM = 0.2        # GP segments (the short pre-termination stub, not
                          # the length-gated Rt->J3 run) are necked to
                          # Default width -- 0.3mm leaves *no* room between
                          # the two constraints above (both resolve to
                          # exactly 0.72mm, a zero-margin knife-edge)
_GP_APPROACH_MARGIN_MM = 0.4  # above Rt's far pad before jogging sideways
                              # (0.25mm Trace clearance + 0.1mm GP-track
                              # half-width + a bit of rounding margin)
_MEANDER_W_MM = 0.635     # meander tooth half-width -- 2*N*W is the exact
                          # extra length needed per net, derived below from
                          # each net's natural (unmeandered) length
_MEANDER_STEP_MM = 0.04   # vertical step between meander rungs -- same net
                          # on both sides of each rung, so no DRC clearance
                          # requirement applies; just small enough that the
                          # densest meander (5 passes, TD3) still fits before
                          # its own net's _CONV_START_OFFSETS_MM turn
_J1B_CLEAR_MARGIN_MM = 0.35   # below J1B pads' bottom edge before turning
# Per-net "start the final convergence" depth, as an offset *above* J3's
# pad-row top edge, indexed by each net's position in _TRACE_CHAIN (0 =
# TRACECLK .. 4 = TD3). Deliberately in *reverse* of natural dx (TRACECLK,
# with by far the largest lane->dest dx, starts deepest/latest; TD3, with
# almost no dx, starts shallowest/earliest) -- this keeps the 5 converging
# 45-degree-ish polylines strictly ordered (source lane order == dest pad
# order, preserved throughout, per task-13-report.md "final convergence")
# so none of them cross each other.
_CONV_START_OFFSETS_MM = [0.65, 1.25, 1.85, 2.45, 3.05]
_ROW_SAFE_MARGIN_MM = 0.4  # above J3's pad-row top edge: every net's
                           # straight-then-diagonal convergence must finish
                           # its *horizontal* motion by here, landing
                           # exactly on its own dest_x, before a final pure
                           # -vertical drop into the pad. J3's pads are
                           # ~2.4mm tall (not just "at" y=62.05) -- an
                           # earlier design that let the diagonal run all
                           # the way to the pad while still sweeping in X
                           # clipped straight through neighboring columns
                           # on the same row.

# --- SWD / NRESET / P3V3 tree -------------------------------------------------
# net, [(ref, pad), ...] daisy-chain nodes, optional PICO descent
# (pico_ref, pico_pad, gap_pin_a, gap_pin_b) -- gap_pin_a/b select the
# unused inter-pin gap this net's PICO-row crossing threads through --,
# lateral spike offset. J3 pin1 (P3V3) and pin2 (SWDIO) share the same x
# column (and likewise J6 pin1/pin2) -- without an offset, both nets'
# vertical pad-to-trunk runs would be coincident there. The offset only
# applies to each spike's B_Cu run (a short jog right at the pad re-aligns
# to the exact pad x), so it's safe to apply uniformly across a net's
# whole chain (B_Cu is otherwise clear in this region regardless of x).
# Only SWDIO needs the offset: its via sits exactly at J3.2/J6.2, so its
# *descent* jogs -0.7mm clear of that column immediately (at its own pad's
# y) before heading down to its trunk. P3V3's via at J3.1/J6.1 (a
# different y -- the *other* row of the 2-row MIPI-20/cortex-10 headers)
# then never overlaps SWDIO's vacated column, so it can stay unoffset;
# giving it an offset too was tried and re-introduced its own conflicts
# (too close to J3/J6's *next* column, pin4/SWCLK, only 1.27mm away, once
# a 0.5mm track + 0.6mm via are accounted for; and a same-net hole-to-hole
# clash between the offset landing point and the nearby PICO/J1B gap
# column reused below).
# P3V3's PICO/J1B gap crossing uses PICO's own pin1/pin2 gap (x=3.485,
# genuinely unused elsewhere) rather than reusing one of the trace
# bundle's gaps -- every trace-bundle gap turned out to sit within
# ~0.6mm of some *other* SWD-tree node's own column (a coincidence of
# the MIPI-20/cortex-10 1.27mm pitch vs. the PICO/J1B 2.54mm pitch), so
# reusing any of them just traded the JP2 problem for a new one. Pin1/2's
# gap has its own problem instead -- it sits almost directly under JP2 (a
# THT guard jumper, B_Cu-blocking) further down the board -- handled by
# routing.main's P3V3 special case: a dogleg to a genuinely clear column
# right after crossing J1B's row, before continuing down past JP2.
_SWD_TREE = [
    ("SWDIO", [("J3", "2"), ("J4", "3"), ("J6", "2"), ("J7", "3")], None, -0.7),
    ("SWCLK", [("J3", "4"), ("J4", "1"), ("J6", "4"), ("J7", "1")], None, 0.0),
    ("NRESET", [("J3", "10"), ("J6", "10"), ("SW1", "1")], ("PICO", "30", "8", "9"), 0.0),
    ("P3V3", [("J3", "1"), ("J6", "1")], ("PICO", "36", "1", "2"), 0.0),
]
_P3V3_DOGLEG_X_MM = 4.5   # post-J1B column P3V3's PICO descent jogs to,
                          # clear of JP2 (blocks x 1.965-3.665) and of
                          # J3's leftmost pad (x=7.31, clear by 2.44mm)
_TRUNK_SPACING_MM = 0.9   # vertical spacing between the 4 nets' B_Cu trunks
                          # -- kept modest because the *deepest* trunk plus
                          # a crossing hop must still clear MH3 (a mounting
                          # hole at x 2.4-5.6mm, y>=72.4mm -- P3V3's own
                          # PICO/J1B-row descent column, 3.485mm, sits
                          # inside that x range, so how deep the trunk
                          # stack is allowed to go is bounded by MH3's y)
_HOP_MM = 1.0             # F_Cu-hop half-span around a crossed shallower
                          # trunk (clears via + trunk halfwidth + clearance)


def _mm(x, y):
    return pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y))


def _pad(board, ref, num, index=0):
    fp = board.FindFootprintByReference(ref)
    assert fp is not None, f"route_trace.py: no footprint {ref!r} on board"
    matches = [p for p in fp.Pads() if p.GetNumber() == num]
    assert matches, f"route_trace.py: {ref} has no pad {num!r}"
    return matches[index]


def _pos(pad):
    p = pad.GetPosition()
    return (pcbnew.ToMM(p.x), pcbnew.ToMM(p.y))


def _bbox(pad):
    bb = pad.GetBoundingBox()
    return (pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop()),
             pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom()))


def _gap_x(board, ref, pin_a, pin_b):
    """Midpoint x (mm) between two adjacent same-row pads on `ref` -- a
    safe vertical-crossing lane through a dense THT header row."""
    xa = _pos(_pad(board, ref, pin_a))[0]
    xb = _pos(_pad(board, ref, pin_b))[0]
    return (xa + xb) / 2.0


def _approach_above(board, ref, pins, margin=0.3):
    """y (mm) just above the topmost edge of the given pads -- a safe
    point to be at before turning to thread the row's gap."""
    tops = [_bbox(_pad(board, ref, p))[1] for p in pins]
    return min(tops) - margin


def _south_clear_y(board):
    """y (mm) below every pad belonging to the debug-connector row (JP2,
    JP3, SW1, J3/J6's own south-row pads which are ~2.4mm tall, J4/J7's
    mechanical pads) -- a safe corridor for the shallowest B_Cu SWD/
    NRESET/P3V3 trunk (SWDIO).

    Margin includes `_HOP_MM` because a *deeper* net's first crossing hop
    lands at (shallowest_trunk_y - _HOP_MM) -- i.e. back *up towards* the
    pad row -- so the shallowest trunk itself must sit `_HOP_MM` (plus a
    real clearance allowance) past every obstacle, or that hop-via would
    land inside e.g. J3's south-row pads (which was the actual bug: they
    reach much further down, to the row's ~67mm bottom edge, than their
    own header's nominal y suggests)."""
    lowest = 0.0
    for ref in ("JP2", "JP3", "SW1", "J3", "J6", "J4", "J7"):
        fp = board.FindFootprintByReference(ref)
        for p in fp.Pads():
            lowest = max(lowest, _bbox(p)[3])
    return lowest + _HOP_MM + 0.6


def _net(board, name):
    ni = board.FindNet(name)
    assert ni is not None, f"route_trace.py: no net {name!r} on board"
    return ni


def _net_has_tracks(board, ni):
    nc = ni.GetNetCode()
    return any(t.GetNetCode() == nc for t in board.GetTracks())


def _add_track(board, ni, layer, pts, width_mm):
    """Add PCB_TRACK segments through waypoints `pts` ([(x,y),...] mm);
    skips zero-length hops."""
    width = pcbnew.FromMM(width_mm)
    segs = []
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if (x0, y0) == (x1, y1):
            continue
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(_mm(x0, y0))
        t.SetEnd(_mm(x1, y1))
        t.SetLayer(layer)
        t.SetWidth(width)
        t.SetNet(ni)
        board.Add(t)
        segs.append(t)
    return segs


def _add_via(board, ni, xy, dia_mm, drill_mm):
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(_mm(*xy))
    v.SetViaType(pcbnew.VIATYPE_THROUGH)
    v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    v.SetWidth(pcbnew.F_Cu, pcbnew.FromMM(dia_mm))
    v.SetDrill(pcbnew.FromMM(drill_mm))
    v.SetNet(ni)
    board.Add(v)
    return v


def _straight_then_diag(p0, p1):
    """[p0, mid, p1] where p0->mid is a straight H or V run for the
    "excess" delta (whichever of dx/dy is larger) and mid->p1 is a pure
    45-degree diagonal for the rest, ending exactly at p1 -- unlike a
    diagonal-first hop, this never has an extended straight run sitting
    at p1's own y (or x), so it can't clip through a whole row of pads
    at that coordinate; only mid->p1 (a single point per row) touches it."""
    x0, y0 = p0
    x1, y1 = p1
    dx, dy = x1 - x0, y1 - y0
    if abs(dx) >= abs(dy):
        excess = abs(dx) - abs(dy)
        sx = 1 if dx >= 0 else -1
        mid = (x0 + sx * excess, y0)
    else:
        excess = abs(dy) - abs(dx)
        sy = 1 if dy >= 0 else -1
        mid = (x0, y0 + sy * excess)
    return [p0, mid, p1]


def _meander(x0, y_start, n_passes, w_mm, step_mm, direction=1):
    """Length-matching meander: `n_passes` there-and-back teeth of width
    `w_mm`, each adding exactly 2*w_mm of path length while progressing
    2*step_mm down the same lane (x0). Returns (points, y_end)."""
    pts = [(x0, y_start)]
    y = y_start
    for _ in range(n_passes):
        pts.append((x0 + direction * w_mm, y))
        y += step_mm
        pts.append((x0 + direction * w_mm, y))
        pts.append((x0, y))
        y += step_mm
        pts.append((x0, y))
    return pts, y


def _route_trace_bundle(board):
    ds = board.GetDesignSettings().m_NetSettings
    width_mm = pcbnew.ToMM(ds.GetEffectiveNetClass("TRACECLK").GetTrackWidth())  # 0.3mm

    j1b_bottom = max(_bbox(_pad(board, "J1B", str(n)))[3] for n in range(1, 10))
    j1b_clear_y = j1b_bottom + _J1B_CLEAR_MARGIN_MM
    j3_pad_top = min(_bbox(_pad(board, "J3", chain[4]))[1] for chain in _TRACE_CHAIN)
    conv_start = [j3_pad_top - off for off in _CONV_START_OFFSETS_MM]
    row_safe_y = j3_pad_top - _ROW_SAFE_MARGIN_MM

    def _final_leg(lane_x, j3):
        """From (lane_x, conv_start_i) into J3 pad `j3`: straight-then-
        -diagonal onto (j3.x, row_safe_y) -- landing exactly on the dest
        column while still above the pad row -- then one pure-vertical
        drop into the pad itself (never sweeping in X while inside the
        row's Y span, so it can't clip a neighboring column's pad)."""
        pts = _straight_then_diag((lane_x, conv_start[i]), (j3[0], row_safe_y))
        pts.append(j3)
        return pts

    # Pass 1: each net's natural (unmeandered) length from J1B-clear straight
    # down to its own conv_start, then the final leg into J3.
    lanes = {}
    natural_len = {}
    for i, (rt_ref, gp_net, td_net, pico_pad, j3_pad, jog_dir, _n) in enumerate(_TRACE_CHAIN):
        rt_b = _pos(_pad(board, rt_ref, "2"))
        pico_pin = int(pico_pad)
        pair = (pico_pin, pico_pin + 1) if jog_dir > 0 else (pico_pin - 1, pico_pin)
        lane_x = _gap_x(board, "J1B", str(pair[0]), str(pair[1]))
        lanes[i] = lane_x
        j3 = _pos(_pad(board, "J3", j3_pad))
        pts = [(rt_b[0], rt_b[1]), (lane_x, rt_b[1]), (lane_x, j1b_clear_y), (lane_x, conv_start[i])]
        pts += _final_leg(lane_x, j3)[1:]
        natural_len[i] = sum(
            ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5
            for a, b in zip(pts, pts[1:])
        )

    target_len = max(natural_len.values())
    n_passes = {
        i: max(0, round((target_len - natural_len[i]) / (2 * _MEANDER_W_MM)))
        for i in range(len(_TRACE_CHAIN))
    }

    # Pass 2: actually route, with the length-matching meander inserted
    # between the J1B crossing and each net's own conv_start.
    for i, (rt_ref, gp_net, td_net, pico_pad, j3_pad, jog_dir, _n) in enumerate(_TRACE_CHAIN):
        gp_ni = _net(board, gp_net)
        td_ni = _net(board, td_net)
        if _net_has_tracks(board, td_ni) or _net_has_tracks(board, gp_ni):
            continue  # idempotent: already routed

        pico = _pos(_pad(board, "PICO", pico_pad))
        rt_a = _pos(_pad(board, rt_ref, "1"))  # GP side
        rt_b = _pos(_pad(board, rt_ref, "2"))  # TDx side
        b_top = _bbox(_pad(board, rt_ref, "2"))[1]
        j3 = _pos(_pad(board, "J3", j3_pad))
        lane_x = lanes[i]

        # --- GP segment: PICO -> Rt.pad1, detouring around Rt.pad2 -------
        gp_dir = -jog_dir
        approach_y = b_top - _GP_APPROACH_MARGIN_MM
        gp_pts = [
            pico,
            (pico[0], approach_y),
            (pico[0] + gp_dir * _GP_JOG_MM, approach_y),
            (pico[0] + gp_dir * _GP_JOG_MM, rt_a[1]),
            rt_a,
        ]
        _add_track(board, gp_ni, pcbnew.F_Cu, gp_pts, _GP_WIDTH_MM)

        # --- TDx segment: Rt.pad2 -> gap lane -> J1B row -> meander -> J3 -
        td_pts = [rt_b, (lane_x, rt_b[1]), (lane_x, j1b_clear_y)]
        mpts, y_after = _meander(lane_x, j1b_clear_y, n_passes[i], _MEANDER_W_MM, _MEANDER_STEP_MM, direction=1)
        td_pts += mpts[1:]
        assert y_after <= conv_start[i], f"{rt_ref}: meander ({y_after}) overruns conv_start ({conv_start[i]})"
        td_pts.append((lane_x, conv_start[i]))
        td_pts += _final_leg(lane_x, j3)[1:]

        _add_track(board, td_ni, pcbnew.F_Cu, td_pts, width_mm)


def _spike_to_trunk(board, ni, px, py, trunk_y, width_mm, via_dia, via_drill, shallower, x_offset=0.0):
    """B_Cu path from (px,py) down to (px+x_offset,trunk_y), hopping to
    F_Cu around any already-routed shallower trunk (a (y, x_min, x_max)
    tuple) that this vertical run would otherwise cross on B_Cu.

    `x_offset` shifts the whole descent sideways (via a short jog right
    at the start) -- for the rare case where two different nets' pads
    share the same x column (see _SWD_TREE) -- and returns the offset x
    the caller should use as this node's contribution to the trunk span.
    """
    pxo = px + x_offset
    pts = [(px, py)]
    if x_offset:
        pts.append((pxo, py))
    lo, hi = sorted((py, trunk_y))
    hits = sorted(oy for oy, x0, x1 in shallower if lo < oy < hi and x0 <= pxo <= x1)
    merged = []
    for oy in hits:
        a, b = max(oy - _HOP_MM, lo), min(oy + _HOP_MM, hi)
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    cur = py
    for a, b in merged:
        pts.append((pxo, a))
        _add_track(board, ni, pcbnew.B_Cu, pts, width_mm)
        _add_via(board, ni, (pxo, a), via_dia, via_drill)
        _add_track(board, ni, pcbnew.F_Cu, [(pxo, a), (pxo, b)], width_mm)
        _add_via(board, ni, (pxo, b), via_dia, via_drill)
        pts = [(pxo, b)]
        cur = b
    pts.append((pxo, trunk_y))
    _add_track(board, ni, pcbnew.B_Cu, pts, width_mm)
    return pxo


def _route_swd_tree(board):
    base_y = _south_clear_y(board)
    default_width_mm = pcbnew.ToMM(
        board.GetDesignSettings().m_NetSettings.GetDefaultNetclass().GetTrackWidth()
    )
    shallower = []  # (trunk_y, x_min, x_max) of nets already routed this call

    for i, (net_name, nodes, pico_descent, x_offset) in enumerate(_SWD_TREE):
        ni = _net(board, net_name)
        if _net_has_tracks(board, ni):
            # Idempotent skip -- but a *later* net must still know about
            # this one's trunk so its own crossings are computed
            # correctly on a from-scratch re-run vs. a partial one. Since
            # this script only ever runs the whole tree atomically (no
            # tracks => none of the four have tracks yet), this is a
            # no-op path in practice; recompute the trunk_y the same way
            # main() would have, for consistency.
            trunk_y = base_y + i * _TRUNK_SPACING_MM
            xs = [_pos(_pad(board, r, p))[0] + x_offset for r, p in nodes]
            if pico_descent:
                xs.append(_P3V3_DOGLEG_X_MM if net_name == "P3V3" else
                          _gap_x(board, pico_descent[0], pico_descent[2], pico_descent[3]))
            shallower.append((trunk_y, min(xs) - 1.0, max(xs) + 1.0))
            continue

        ncls = board.GetDesignSettings().m_NetSettings.GetEffectiveNetClass(net_name)
        width_mm = pcbnew.ToMM(ncls.GetTrackWidth())
        via_dia = pcbnew.ToMM(ncls.GetViaDiameter())
        via_drill = pcbnew.ToMM(ncls.GetViaDrill())
        trunk_y = base_y + i * _TRUNK_SPACING_MM

        xs = []
        for ref, pad in nodes:
            xy = _pos(_pad(board, ref, pad))
            _add_via(board, ni, xy, via_dia, via_drill)
            pxo = _spike_to_trunk(board, ni, xy[0], xy[1], trunk_y, width_mm, via_dia, via_drill, shallower, x_offset)
            xs.append(pxo)

        if pico_descent:
            pico_ref, pico_pad, gap_a, gap_b = pico_descent
            pico_xy = _pos(_pad(board, pico_ref, pico_pad))
            gap_x = _gap_x(board, pico_ref, gap_a, gap_b)
            approach_y = _approach_above(board, pico_ref, [gap_a, gap_b])
            # P3V3's nominal 0.5mm Power-class width does not fit the
            # ~0.84mm PICO/J1B pin-pitch gap with clearance to spare
            # (0.17mm < 0.2mm required); neck to Default width (0.2mm,
            # clears with 0.32mm margin) for this crossing only.
            neck_mm = default_width_mm if net_name == "P3V3" else width_mm
            if net_name == "P3V3":
                # Dogleg clear of JP2 (see _SWD_TREE comment): cross J1B's
                # row at gap_x as usual, then jog to _P3V3_DOGLEG_X_MM
                # right after (while still well above JP2), and only
                # then descend the rest of the way.
                j1b_bottom = max(_bbox(_pad(board, "J1B", str(n)))[3] for n in range(1, 10))
                post_j1b_y = j1b_bottom + 0.6
                descent_x = _P3V3_DOGLEG_X_MM
                _add_track(board, ni, pcbnew.B_Cu,
                           [pico_xy, (gap_x, approach_y), (gap_x, post_j1b_y), (descent_x, post_j1b_y)],
                           neck_mm)
                _spike_to_trunk(board, ni, descent_x, post_j1b_y, trunk_y, neck_mm, via_dia, via_drill, shallower)
            else:
                descent_x = gap_x
                _add_track(board, ni, pcbnew.B_Cu, [pico_xy, (gap_x, approach_y)], neck_mm)
                _spike_to_trunk(board, ni, gap_x, approach_y, trunk_y, neck_mm, via_dia, via_drill, shallower)
            xs.append(descent_x)

        x0, x1 = min(xs), max(xs)
        _add_track(board, ni, pcbnew.B_Cu, [(x0, trunk_y), (x1, trunk_y)], width_mm)
        shallower.append((trunk_y, x0 - 1.0, x1 + 1.0))



# ============================================================================
# Task 14: power / USB pairs / guards / finish bulk (non-GND) nets
# ============================================================================
#
# Task 13 claimed: B_Cu y~30-72mm x~3.5-53.4mm (SWD/NRESET/P3V3 trunk stack)
# and F_Cu y~48-72mm x~4-53.4mm (trace bundle + GP1-5). Everything below
# routes AROUND those claims, using regions Task 13 never touched:
#   - the open rectangle between PICO's two header rows (y~30.5-47.1,
#     x -1..52.9) -- nothing is placed there;
#   - the open band between J2B's row (y=22.6) and the top peripheral
#     group (JP1/JP4/R_NVD/LED_PWR/J_UART/SW_USER/LED_USER, bottom edges
#     <=13.9mm) -- clear from y~14 to y~21.5;
#   - the entire right two-thirds of the board (x>=53mm) and the entire
#     top strip (y<22.6mm out past x=53) -- both totally unclaimed.
# GND is left unrouted throughout (Task 15's pour + stitching vias own it),
# except where noted.

_BREAKOUT_GND = {"3", "8", "13", "18"}  # PTH pad numbers landing on GND
# J1B-only: these breakout pads sit directly under Rt1-5 (same x as the
# PICO pad), so the straight stub is sourced from Rt's own GP-side pad
# (already on-net from Task 13) instead of punching through Rt's body.
_BREAKOUT_TRACE_RT = {"2": "Rt1", "4": "Rt2", "5": "Rt3", "6": "Rt4", "7": "Rt5"}
# J1B-only: GP0/GP6 guard pins also tie to their jumper (JP2/JP3 pin 1).
_BREAKOUT_GUARD = {"1": "JP2", "9": "JP3"}


def _class_width(board, net_name):
    ncls = board.GetDesignSettings().m_NetSettings.GetEffectiveNetClass(net_name)
    return pcbnew.ToMM(ncls.GetTrackWidth())


def _track_exists(board, net_code, layer, p0, p1):
    for t in board.GetTracks():
        if t.GetClass() == "PCB_VIA":
            continue
        if t.GetNetCode() != net_code or t.GetLayer() != layer:
            continue
        s, e = t.GetStart(), t.GetEnd()
        if (s == p0 and e == p1) or (s == p1 and e == p0):
            return True
    return False


def _add_path_once(board, ni, layer, pts, width_mm):
    """Add a polyline unless its first segment is already present on this
    net+layer.

    Task 13's per-net "any tracks yet? skip" idempotence doesn't work for
    Task 14: several nets it touches (GP1-5, NRESET, P3V3, SWDIO, SWCLK)
    already carry Task-13 tracks and still need *more* segments added on
    top here. Checking the first segment specifically works because every
    connection this file adds starts at a previously-bare pad (confirmed
    against the pre-Task-14 DRC unconnected_items list), so no other code
    path produces a coincidentally-matching first segment.
    """
    if len(pts) < 2:
        return []
    p0, p1 = _mm(*pts[0]), _mm(*pts[1])
    if _track_exists(board, ni.GetNetCode(), layer, p0, p1):
        return []
    return _add_track(board, ni, layer, pts, width_mm)


def _bend_hv(p0, p1):
    """[p0, mid, p1] bending horizontal-then-vertical (move in X at p0's Y,
    then in Y at p1's X)."""
    return [p0, (p1[0], p0[1]), p1]


def _bend_vh(p0, p1):
    """[p0, mid, p1] bending vertical-then-horizontal (move in Y at p0's X,
    then in X at p1's Y)."""
    return [p0, (p0[0], p1[1]), p1]


def _route_breakout_stubs(board):
    """40 breakout ties (J1B pad n <-> PICO pad n, J2B pad n <-> PICO pad
    n+20), skipping the 8 GND ones -- Task 15's pour handles those. Every
    stub is a straight vertical run (pads are x-aligned, constant dy) except
    the 5 trace-net ones (sourced from Rt's own pad, see module docstring)
    and the 2 guard ones (J1B ties on to JP2/JP3 pin 1 too)."""
    for n in range(1, 21):
        s = str(n)
        if s in _BREAKOUT_GND:
            continue
        pico_pad = _pad(board, "PICO", s)
        j1b_pad = _pad(board, "J1B", s)
        net_name = pico_pad.GetNetname()
        ni = _net(board, net_name)
        w = _class_width(board, net_name)
        src_xy = _pos(_pad(board, _BREAKOUT_TRACE_RT[s], "1")) if s in _BREAKOUT_TRACE_RT else _pos(pico_pad)
        j1b_xy = _pos(j1b_pad)
        _add_path_once(board, ni, pcbnew.F_Cu, [src_xy, j1b_xy], w)
        if s in _BREAKOUT_GUARD:
            jp_xy = _pos(_pad(board, _BREAKOUT_GUARD[s], "1"))
            _add_path_once(board, ni, pcbnew.F_Cu, [j1b_xy, jp_xy], w)

    for n in range(1, 21):
        s = str(n)
        if s in _BREAKOUT_GND:
            continue
        pico_pad = _pad(board, "PICO", str(n + 20))
        j2b_pad = _pad(board, "J2B", s)
        net_name = pico_pad.GetNetname()
        ni = _net(board, net_name)
        w = _class_width(board, net_name)
        _add_path_once(board, ni, pcbnew.F_Cu, [_pos(pico_pad), _pos(j2b_pad)], w)


def _route_internal_ties(board):
    """SW1 and SW_USER (Button_Switch_SMD:SW_SPST_B3S-1000) each expose the
    same logical pin as two separate physical pads (mechanical, not footprint
    -internally-bridged) -- tie each pair together directly. SW1's GND pair
    (pad 2) is left for Task 15's pour; its NRESET pair (pad 1) is not GND,
    so it's fixed here."""
    for ref, num, net_name in [("SW1", "1", "NRESET"), ("SW_USER", "1", "BTN_USER")]:
        fp = board.FindFootprintByReference(ref)
        pads = [p for p in fp.Pads() if p.GetNumber() == num]
        assert len(pads) == 2, f"{ref}: expected 2 pads numbered {num!r}, got {len(pads)}"
        ni = _net(board, net_name)
        w = _class_width(board, net_name)
        _add_path_once(board, ni, pcbnew.F_Cu, [_pos(pads[0]), _pos(pads[1])], w)


# (net, (ref_a, pad_a), (ref_b, pad_b), bend) -- short same-cluster
# connections where both ends already sit next to each other (per place.py's
# clustering); "bend" picks _bend_hv/_bend_vh/None(straight) to dodge a
# neighboring pad of a different net (see per-edge comments below). Pad
# numbers are real footprint pad numbers (not the netlist model's logical pin
# names) -- ESD_H/ESD_D (USBLC6-2SC6): 1=IO1,2=GND,3=IO2,4=IO2B,5=VBUS,
# 6=IO1B; U_HSW (TPS2051B): 1=OUT,2=GND,3=FLG,4=EN,5=IN; U_ISNS (INA180):
# 1=OUT,2=GND,3=IN+,4=IN-,5=VS; J5 (USB-A): 1=VBUS,2=DM,3=DP,4=GND -- see
# hw/netlist.py's padmap comments for the datasheet citations.
_LOCAL_EDGES = [
    # --- Host USB port cluster (J5/R_HDP*/R_HDM*/ESD_H/TP1-3) ---
    ("HOST_DP", ("ESD_H", "1"), ("ESD_H", "6"), None),
    ("HOST_DP", ("R_HDP_PD", "1"), ("R_HDP", "2"), None),
    # straight ESD_H.1(IO1)->R_HDP_PD.1 clips R_HDP_PD's own GND pad (pad 2,
    # 1.02mm away) by ~0.16mm -- go via ESD_H's own row (y=21.05) first.
    ("HOST_DP", ("ESD_H", "1"), ("R_HDP_PD", "1"), _bend_hv),
    ("HOST_DP", ("TP1", "1"), ("ESD_H", "6"), None),
    ("HOST_DP", ("J5", "3"), ("TP1", "1"), None),
    ("HOST_DM", ("ESD_H", "4"), ("ESD_H", "3"), None),
    ("HOST_DM", ("R_HDM_PD", "1"), ("R_HDM", "2"), None),
    ("HOST_DM", ("ESD_H", "3"), ("R_HDM_PD", "1"), _bend_hv),
    ("HOST_DM", ("ESD_H", "4"), ("TP2", "1"), None),
    ("HOST_DM", ("TP2", "1"), ("J5", "2"), None),
    # C_HVBUS_BULK/100n pad1/pad2 share a Y row (pad2 = GND) -- a straight
    # line or plain bend between the two pad1's rides right across the
    # intervening GND pad(s); jog above the row (y=40.0, clear of both caps'
    # 41.275 top edge) then back down.
    ("HOST_VBUS", ("C_HVBUS_BULK", "1"), ("C_HVBUS_100n", "1"),
     [(78.05, 40.0), (84.52, 40.0)]),
    # U_HSW is a 2-column SOT-23-5 (OUT/GND/FLG at x=77.862; EN/IN at
    # x=80.138) -- pad1 (OUT) sits above pad2/3 (GND/FLG) on its own
    # column. Reach C_HVBUS_BULK.1 by jogging *right* into the gap between
    # the two columns (x=79.0, clear of both by >=1.1mm) before descending
    # -- jogging left instead runs straight through R_SHUNT/HOST_5V_IN's
    # own territory (x=71.5-80.1).
    ("HOST_VBUS", ("U_HSW", "1"), ("C_HVBUS_BULK", "1"),
     [(79.0, 35.05), (79.0, 42.0)]),
    # ESD_H.5<->U_HSW.1 and J5.1<->ESD_H.5 are routed by
    # _route_host_vbus_chain (B_Cu hops) -- both F_Cu waypoint attempts
    # tried here kept re-crossing HOST_DM's ESD_H.4->TP2.1->J5.2 diagonal
    # pair (verified against the real DRC run), which fans out from
    # ESD_H's own column across exactly the x-range (82-96) this chain
    # needs to cross.
    # --- Host load-switch / shunt / current-sense cluster ---
    # U_HSW pad5 (IN, our source) shares its column (x=80.138) with pad4
    # (EN) below it, and R_SHUNT.2 sits under U_HSW's *other* column
    # (77.862, OUT/GND/FLG) -- a plain bend_vh's straight drop threads pad4,
    # and the horizontal leg at y=36.0 runs right across U_HSW.2 (GND,
    # 77.862,36.0). Jog right off the column, then *above* U_HSW's whole
    # row (34.0, clear of pad1's top edge 34.75) -- HOST_VBUS's own
    # U_HSW.1->C_HVBUS_BULK.1 jog owns the x=79.0 column from y=35.05 down
    # to 42.0, so crossing back to R_SHUNT below that (y=38.0) rides
    # straight through it instead.
    ("HOST_5V_IN", ("U_HSW", "5"), ("R_SHUNT", "2"),
     [(81.3, 35.05), (81.3, 34.0), (74.463, 34.0)]),
    # R_SHUNT.2's straight/bend_hv approach to U_ISNS.4 (74.138,42.95) rides
    # at x=74.463 (R_SHUNT's own pad x), which sits inside U_ISNS pad5's
    # bbox (P3V3, 73.475-74.8) -- jog further right, clear of that bbox,
    # before descending.
    ("HOST_5V_IN", ("R_SHUNT", "2"), ("U_ISNS", "4"),
     [(75.5, 36.0), (75.5, 42.95)]),
    # U_ISNS pad3 (VBUS_SEL, 71.862,42.95) shares its x column with pads
    # 1/2 (ISENSE/GND, y=41.05/42.0) -- descending straight down from pad3
    # threads both. Jog right off the column first.
    ("VBUS_SEL", ("U_ISNS", "3"), ("R_SHUNT", "1"),
     [(73.0, 42.95), (73.0, 36.0)]),
    # --- Device USB port cluster (J9/R_DDP*/R_DDM*/ESD_D/R_DPU/R_J9VD*) ---
    ("DEV_DP", ("ESD_D", "1"), ("ESD_D", "6"), None),
    ("DEV_DP", ("R_DDP", "2"), ("ESD_D", "1"), None),
    ("DEV_DP", ("R_DPU", "1"), ("ESD_D", "6"), None),
    # J9's pads all share the x=104.795 column -- bend_vh's straight drop
    # from pad3 threads pads 4/5/6. Go horizontal first (off the column) at
    # y=61.0 -- between J9_VBUS's own y=62.0 jog row and R_DPU/R_DDP's
    # y=60.0 row, clear of both -- then align y and approach R_DPU.1 from
    # the *left* (x<90.745): R_DPU's own pad2 (DEV_DP_PU_EN, 91.765,60.0)
    # sits right next to pad1 on the same row, so approaching from the
    # right would ride straight across it.
    ("DEV_DP", ("J9", "3"), ("R_DPU", "1"),
     [(95.0, 62.0), (95.0, 61.0), (89.5, 61.0), (89.5, 60.0)]),
    ("DEV_DM", ("ESD_D", "4"), ("ESD_D", "3"), None),
    ("DEV_DM", ("ESD_D", "3"), ("R_DDM", "2"), None),
    # DEV_DM: J9.2 <-> ESD_D.4 deliberately NOT routed here -- see
    # task-14-report.md "Concerns". ESD_D pad4 (our dest, 86.392,62.95)
    # sits directly above pad5 (J9_VBUS, 62.0) on the same column, and
    # J9_VBUS's own routing forms an L-shaped obstacle around it (a
    # vertical at x=90.745 spanning y=62.0-64.0, *and* a horizontal at
    # y=63.3 spanning x=90.745-104.795) that leaves no way from J9.2
    # (inside the L's corner) back out to ESD_D's column without either
    # crossing J9_VBUS itself or DEV_VBUS_DET's own local edge just beyond
    # it (90.745-91.765, y=64.0-68.0) -- confirmed by exhausting the
    # available approach angles, not just one failed attempt. Deferred to
    # the brief's sanctioned interactive-GUI finish.
    ("J9_VBUS", ("ESD_D", "5"), ("R_J9VD_T", "1"), _bend_hv),
    ("J9_VBUS", ("R_J9VD_T", "1"), ("J9", "1"), _bend_vh),
    ("DEV_VBUS_DET", ("R_J9VD_B", "1"), ("R_J9VD_T", "2"), None),
    # --- Top-left power-select / native-VBUS-detect / power-LED cluster ---
    ("VBUS_NET", ("JP4", "1"), ("JP1", "3"), None),
    # PICO.40<->JP1.3 is routed by _route_vbus_net_pico_tie (B_Cu, both
    # ends THT) -- see its docstring: an F_Cu waypoint attempt here
    # genuinely interleaves with VBUS_SEL's JP1.2->R_LED_PWR.1 edge (both
    # exit JP1's row from adjacent pins headed in opposite directions).
    ("NVD_TOP", ("JP4", "2"), ("R_NVD_T", "1"), None),
    ("NATIVE_VBUS_DET", ("R_NVD_T", "2"), ("R_NVD_B", "1"), None),
    # JP1.2<->R_LED_PWR.1 is routed by _route_vbus_sel_jp1_tie (B_Cu hop):
    # NATIVE_VBUS_DET's own L-shaped path (a vertical at x=17.49, y=12.5-
    # 20.0, plus a horizontal at y=20.0) sits directly between JP1's row
    # and R_LED_PWR -- there's no y left between JP1's row (bottom edge
    # 11.85) and R_NVD_B's pad (bbox top 12.18) to cross x=17.49 on the
    # same layer.
    ("LED_PWR_A", ("R_LED_PWR", "2"), ("LED_PWR", "2"), None),
    # --- Top-region user-LED pair ---
    ("LED_USER", ("R_LED_USER", "2"), ("LED_USER", "2"), None),
    # --- Debug connector: J3's two 5V-supply pins tied together ---
    ("V5_JTRACE", ("J3", "11"), ("J3", "13"), None),
]


def _route_local_clusters(board):
    for net_name, (ref_a, pad_a), (ref_b, pad_b), bend in _LOCAL_EDGES:
        ni = _net(board, net_name)
        w = _class_width(board, net_name)
        p0 = _pos(_pad(board, ref_a, pad_a))
        p1 = _pos(_pad(board, ref_b, pad_b))
        if bend is None:
            pts = [p0, p1]
        elif callable(bend):
            pts = bend(p0, p1)
        else:
            # explicit list of intermediate waypoints (mm) between p0 and p1
            # -- used where a plain H/V bend still clips a neighboring pad
            # (dense SOT-23/connector pin spacing); see per-edge comments.
            pts = [p0] + list(bend) + [p1]
        _add_path_once(board, ni, pcbnew.F_Cu, pts, w)


def _route_vbus_net_pico_tie(board):
    """VBUS_NET: JP1.3 (7.295,11.0) <-> PICO.40 (2.215,30.11) -- the tie
    that actually merges the JP4/JP1/J8 side of this net (see
    _route_vbus_net_cross) with the PICO/J2B breakout side (see
    _route_breakout_stubs); without it they're two disconnected
    components of the same net. An F_Cu waypoint (jogging below JP1's own
    row, same technique as everywhere else) genuinely interleaves with
    VBUS_SEL's JP1.2->R_LED_PWR.1 edge next door (both exit JP1's row from
    adjacent pins headed in opposite directions -- a real crossing, not a
    routing mistake, per the same interleaving proof as the top-region
    long-runs). Both ends are THT (JP1, PICO) so a straight B_Cu run needs
    no vias at all."""
    ni = _net(board, "VBUS_NET")
    w = _class_width(board, "VBUS_NET")
    jp1_3 = _pos(_pad(board, "JP1", "3"))
    pico40 = _pos(_pad(board, "PICO", "40"))
    # Jog below JP1's row, cross the J2B row only at PICO.40's own column
    # (x=2.215 -- J2B pad 20 is the *same* net there, so threading its own
    # THT pad is safe), then straight down into PICO.40.
    pts = [jp1_3, (7.295, 13.0), (2.215, 13.0), pico40]
    if _track_exists(board, ni.GetNetCode(), pcbnew.B_Cu, _mm(*pts[0]), _mm(*pts[1])):
        return
    _add_track(board, ni, pcbnew.B_Cu, pts, w)


def _route_vbus_sel_jp1_tie(board):
    """VBUS_SEL: JP1.2 (4.755,11.0) <-> R_LED_PWR.1 (21.49,12.0).
    Below JP1's row (y>11.85) is claimed by NATIVE_VBUS_DET's own
    L-shaped path (a vertical at x=17.49 from R_NVD_B's pad, 12.5, up to
    20.0) on one side and _route_vbus_net_pico_tie's B_Cu presence (a
    vertical at x=7.295, y=11.0-13.0, plus a horizontal at y=13.0) on the
    other -- no y in that band clears both. Going *above* the row instead
    (y=7.5, clear of R_NVD_T/LED_PWR's own pads, top edges 9.18/9.025, and
    of _route_vbus_net_cross's own B_Cu hop entry at (7.295,8.5)) avoids
    every one of them at once, entirely on F_Cu. The final approach jogs
    to x=20.0 before descending -- LED_PWR sits almost directly above
    R_LED_PWR (same x-ish, y=9.5 vs 12.0), and R_LED_PWR's own 2 pads
    share a row (21.49/22.51 at y=12.0), so both a straight vertical drop
    and a rightward final approach clip a neighboring GND/LED_PWR_A pad --
    only approaching pad 1 from the left, x<21.49, clears both at once."""
    ni = _net(board, "VBUS_SEL")
    w = _class_width(board, "VBUS_SEL")
    jp1_2 = _pos(_pad(board, "JP1", "2"))
    r_led_pwr1 = _pos(_pad(board, "R_LED_PWR", "1"))
    y = 7.5
    x_approach = 20.0
    pts = [jp1_2, (jp1_2[0], y), (x_approach, y), (x_approach, r_led_pwr1[1]), r_led_pwr1]
    if _track_exists(board, ni.GetNetCode(), pcbnew.F_Cu, _mm(*pts[0]), _mm(*pts[1])):
        return
    _add_track(board, ni, pcbnew.F_Cu, pts, w)


def _route_host_vbus_chain(board):
    """HOST_VBUS: J5.1 (96.615,21.5) -> ESD_H.5 (81.752,22.0, via-in-pad)
    -> U_HSW.1 (77.862,35.05). Every F_Cu waypoint path tried here re-crossed
    HOST_DM's own ESD_H.4->TP2.1->J5.2 diagonal pair, which fans out from
    ESD_H's column across exactly the x-range (82-96) this chain must
    cross (confirmed against the real DRC run, not just by inspection) --
    simplest fix is to just take the whole middle stretch to B_Cu, clear of
    all of HOST_DM/HOST_DP's F_Cu local wiring regardless of exact path."""
    ni = _net(board, "HOST_VBUS")
    w = _class_width(board, "HOST_VBUS")
    ncls = board.GetDesignSettings().m_NetSettings.GetEffectiveNetClass("HOST_VBUS")
    via_dia, via_drill = pcbnew.ToMM(ncls.GetViaDiameter()), pcbnew.ToMM(ncls.GetViaDrill())
    j5 = _pos(_pad(board, "J5", "1"))
    esd_h5 = _pos(_pad(board, "ESD_H", "5"))
    u_hsw1 = _pos(_pad(board, "U_HSW", "1"))
    if _pad_routed_target(board, _pad(board, "ESD_H", "5")):
        return
    # J5 is THT (PTH) -- already has B_Cu copper, no via needed to start.
    _add_track(board, ni, pcbnew.B_Cu, [j5, esd_h5], w)
    _add_via(board, ni, esd_h5, via_dia, via_drill)
    _add_track(board, ni, pcbnew.B_Cu, [esd_h5, u_hsw1], w)
    _add_via(board, ni, u_hsw1, via_dia, via_drill)


# --- Middle-gap crossings: PICO top/bottom row -> right-side clusters or
# top-region peripherals, entirely on B_Cu (see module-level comment: the
# open rectangle between PICO's two header rows). B_Cu (rather than F_Cu,
# tried first) sidesteps two problems the actual DRC run found: (1) the PICO
# module's own "Antenna Copper Keep Out" zone (F.Cu only, x 43.3-52.3,
# y 31.9-46.1) sits right across this gap; (2) it keeps this whole group off
# the same layer as the F.Cu breakout stubs and local-cluster wiring, so it
# can't short against them regardless of incidental 2D overlap. Every source
# here is a PICO PTH pad (copper on both layers already, no via needed to
# start); every destination is SMD (needs a via-in-pad for the final F.Cu
# hop) except J_UART (THT -- the B_Cu track lands directly on it).
#
# Every entry: (net, source_row ("top"|"bottom"), source_pico_pad, dest_ref,
# dest_pad). Each net exits into the gap at its own lane-y (see
# _TOP_LANE_Y/_BOTTOM_LANE_Y below) then either goes straight for its
# right-cluster target, or (the 4 in _NORTH_THREAD, whose target sits back
# west of x=53) threads a dedicated column + transit-y first.
_GAP_NETS = [
    # top-row sourced (U_HSW pad numbers: 3=FLG,4=EN; U_ISNS: 1=OUT,5=VS --
    # see _LOCAL_EDGES' comment for the full padmaps)
    ("HOST_VBUS_EN", "top", "22", "U_HSW", "4"),
    ("ISENSE", "top", "31", "U_ISNS", "1"),
    ("DEV_VBUS_DET", "top", "32", "R_J9VD_T", "2"),
    ("GP18", "top", "24", "R_DDP", "1"),
    ("GP19", "top", "25", "R_DDM", "1"),
    ("GP20", "top", "26", "R_HDP", "1"),
    ("GP21", "top", "27", "R_HDM", "1"),
    ("P3V3", "top", "36", "U_ISNS", "5"),
    # bottom-row sourced, east-bound
    ("HOST_VBUS_FLT", "bottom", "20", "U_HSW", "3"),
    ("DEV_DP_PU_EN", "bottom", "15", "R_DPU", "2"),
    # bottom-row sourced, north-bound -- all 6 threaded (see _NORTH_THREAD):
    # even GP10/BTN_USER, whose target x itself is >53, still cross straight
    # through the *other* east-bound nets' final approaches if not given
    # their own dedicated column (found by the actual DRC run: an
    # unthreaded GP10 crossed nearly every other gap net).
    ("GP10", "bottom", "14", "R_LED_USER", "1"),
    ("BTN_USER", "bottom", "19", "SW_USER", "1"),
    ("I2C0_SDA", "bottom", "11", "J_STEMMA", "3"),
    ("I2C0_SCL", "bottom", "12", "J_STEMMA", "4"),
    ("UART0_TX", "bottom", "16", "J_UART", "1"),
    ("UART0_RX", "bottom", "17", "J_UART", "2"),
]
_GAP_DEST_THT = {"UART0_TX", "UART0_RX"}  # J_UART is THT -- no via needed

# East-bound nets that share a destination cluster with another east-bound
# net (R_HDP/R_HDM; U_HSW x2 + U_ISNS x2; R_DDP/R_DDM; R_J9VD_T/R_DPU) found
# real crossings in the actual DRC run once their straight-then-diagonal
# final approaches converged on the same small area. Fixed by putting one of
# each pair back on F_Cu (via a via right at clear_x/its column -- the
# keepout is already behind them by then) so same-cluster pairs are never on
# the same layer during their final approach.
_GAP_FINAL_FCU = {"HOST_VBUS_FLT", "DEV_DP_PU_EN", "GP19", "GP21", "P3V3", "GP10"}
# GP10 also needs a real crossing fixed against the two other north-threaded
# nets it doesn't share a layer-split with structurally (TX, RX) -- their
# (column, target-x) orderings genuinely invert (found via a geometric
# self-check, not just the DRC run), so no single consistent depth ordering
# separates all six threaded nets on one layer. GP10 moving to F_Cu resolves
# GP10 x TX and GP10 x RX; SDA x SCL is the remaining inverted pair, fixed
# below with a short local hop instead of a wholesale layer move (which was
# tried and re-conflicted with P3V3's own J_STEMMA descent at x=29.5).

# lane y assigned by source-x ascending order (see module docstring's
# non-crossing proof: leftmost source gets the lane farthest from its own
# row, rightmost gets the lane closest to its row -- guarantees no net's
# vertical entry ever crosses another net's horizontal lane).
# NOTE: these lanes deliberately stay OUTSIDE y=[31.9,46.1] -- the real DRC
# run found the PICO module's own "Antenna Copper Keep Out" rule-area zone
# covers *both* copper layers (F.Cu+B.Cu+paste, queried via
# fp.Zones()/GetLayerSet()), not just F.Cu as first assumed, over x
# 43.3-52.3. Top-sourced nets exit *upward* into the J2B-row<->PICO-top-row
# gap (22.6-30.11); bottom-sourced exit *downward* into the PICO-bottom-row
# <->J1B-row gap (47.89-56.0) -- both entirely below/above the keepout's y
# range regardless of x, and (being B_Cu) the downward option no longer
# conflicts with the F.Cu breakout stubs occupying that same y-band at other
# columns (different layer).
_TOP_LANE_Y = {  # y in [23.9, 28.9]; deepest (smallest, farthest from the
    # row at 30.11) = leftmost source x -- see the non-crossing proof above.
    "P3V3": 23.9, "DEV_VBUS_DET": 24.61, "ISENSE": 25.32, "GP21": 26.03,
    "GP20": 26.74, "GP19": 27.45, "GP18": 28.16, "HOST_VBUS_EN": 28.87,
}
_BOTTOM_LANE_Y = {  # y in [49.2, 54.4]; deepest (largest, farthest from the
    # row at 47.89) = leftmost source x.
    "I2C0_SDA": 54.38, "I2C0_SCL": 53.64, "GP10": 52.9, "DEV_DP_PU_EN": 52.16,
    "UART0_TX": 51.42, "UART0_RX": 50.68, "BTN_USER": 49.94, "HOST_VBUS_FLT": 49.2,
}
_EAST_CLEAR_X = 53.0  # east of PICO/J1B/J2B (courtyard right edge 52.94)

# The 4 "threaded" north-bound nets (target x < _EAST_CLEAR_X): each gets its
# own column (x, east of PICO) to go straight up on, and its own transit-y
# (where it turns west toward its target) in the band above the gap. Order/
# values derived so no net's column is crossed by another net's westbound
# transit lane while that lane is within reach of it -- see
# task-14-report.md "middle-gap lane derivation" for the full proof.
_NORTH_THREAD = {
    "I2C0_SDA": (53.5, 20.5),
    "I2C0_SCL": (54.5, 19.0),
    "GP10": (55.5, 17.5),
    "UART0_TX": (56.5, 16.0),
    "UART0_RX": (57.5, 14.5),
    "BTN_USER": (58.5, 13.0),
}


def _pad_routed_target(board, pad):
    """True if `pad` already has copper touching it (idempotence check for
    the gap-crossing / long-run phases, where each destination pad is only
    ever the target of exactly one routing action)."""
    xy = _mm(*_pos(pad))
    for t in board.GetTracks():
        if t.GetClass() == "PCB_VIA":
            if t.GetPosition() == xy:
                return True
        elif t.GetStart() == xy or t.GetEnd() == xy:
            return True
    return False


def _route_gap_crossings(board):
    for net_name, side, pico_pad_num, dref, dpad in _GAP_NETS:
        ni = _net(board, net_name)
        w = _class_width(board, net_name)
        dest = _pad(board, dref, dpad)
        if _pad_routed_target(board, dest):
            continue
        src = _pos(_pad(board, "PICO", pico_pad_num))
        dest_xy = _pos(dest)
        lane_y = _TOP_LANE_Y[net_name] if side == "top" else _BOTTOM_LANE_Y[net_name]
        ncls = board.GetDesignSettings().m_NetSettings.GetEffectiveNetClass(net_name)
        via_dia, via_drill = pcbnew.ToMM(ncls.GetViaDiameter()), pcbnew.ToMM(ncls.GetViaDrill())

        entry_pts = [src, (src[0], lane_y)]  # straight vertical exit into the gap
        if net_name in _NORTH_THREAD:
            col_x, transit_y = _NORTH_THREAD[net_name]
            entry_pts += [(col_x, lane_y), (col_x, transit_y)]
            turn_xy = (col_x, transit_y)
        else:
            clear_x = max(_EAST_CLEAR_X, src[0])
            entry_pts += [(clear_x, lane_y)]
            turn_xy = (clear_x, lane_y)
        _add_track(board, ni, pcbnew.B_Cu, entry_pts, w)

        final_pts = _straight_then_diag(turn_xy, dest_xy)
        if net_name == "I2C0_SDA":
            # The one pair among the 6 north-threaded nets that neither the
            # GP10 F_Cu move nor any consistent column/transit-y ordering
            # resolves: I2C0_SDA's (column, target-x) order inverts against
            # I2C0_SCL's (found by a geometric self-check). Both target
            # adjacent J_STEMMA pins, so neither can just move to F_Cu
            # wholesale without re-conflicting with P3V3's own J_STEMMA
            # descent at x=29.5. Instead, hop I2C0_SDA to F_Cu for a short
            # stretch of its own diagonal (19.5-18.5, right where it would
            # cross I2C0_SCL's transit lane at y=19.0) and back to B_Cu.
            _add_track(board, ni, pcbnew.B_Cu, [final_pts[0], final_pts[1], (42.6, 19.5)], w)
            _add_via(board, ni, (42.6, 19.5), via_dia, via_drill)
            _add_track(board, ni, pcbnew.F_Cu, [(42.6, 19.5), (41.6, 18.5)], w)
            _add_via(board, ni, (41.6, 18.5), via_dia, via_drill)
            _add_track(board, ni, pcbnew.B_Cu, [(41.6, 18.5), dest_xy], w)
            _add_via(board, ni, dest_xy, via_dia, via_drill)
        elif net_name in _GAP_FINAL_FCU:
            # Same-cluster pair as another gap net (see _GAP_FINAL_FCU) --
            # hop to F_Cu for the final approach so the two can't cross. No
            # via needed at the destination itself: it's an SMD pad (F_Cu),
            # and we're already on F_Cu -- a via there would only touch
            # F_Cu, leaving its B_Cu side dangling (a real DRC catch).
            _add_via(board, ni, turn_xy, via_dia, via_drill)
            _add_track(board, ni, pcbnew.F_Cu, final_pts, w)
        else:
            _add_track(board, ni, pcbnew.B_Cu, final_pts, w)
            if net_name not in _GAP_DEST_THT:
                _add_via(board, ni, dest_xy, via_dia, via_drill)


# --- Top-region long runs (JP1/JP4/J2B.16 area -> R_NVD_B / R_SHUNT /
# J_STEMMA / J8): mostly F_Cu (short, low-traffic, no reason to leave the
# top layer), but three of the four genuinely interleave with each other in
# X (NATIVE_VBUS_DET x VBUS_SEL, NATIVE_VBUS_DET x P3V3, P3V3 x VBUS_SEL --
# real crossings, not a routing mistake: their (source-x, dest-x) intervals
# pairwise overlap without nesting, so *some* pair is guaranteed to cross on
# a shared layer). Resolved with short B_Cu hops (2 vias each) exactly where
# each pair would otherwise cross, verified against the actual DRC run.
def _route_native_vbus_det(board):
    """NATIVE_VBUS_DET: PICO.21 (x=50.475) -> R_NVD_B.1 (x=17.49,y=12.5),
    F_Cu the whole way at y=20.0 -- deeper (further from the top edge) than
    every north-threaded transit-y (max 19.0, different layer anyway) and
    P3V3's crossing y (18.0, see below), so it never touches either."""
    ni = _net(board, "NATIVE_VBUS_DET")
    w = _class_width(board, "NATIVE_VBUS_DET")
    dest = _pad(board, "R_NVD_B", "1")
    src = _pos(_pad(board, "PICO", "21"))
    dest_xy = _pos(dest)
    pts = [src, (src[0], 20.0), (dest_xy[0], 20.0), dest_xy]
    # R_NVD_B.1 is also NVD_TOP/NATIVE_VBUS_DET's local-cluster destination
    # (R_NVD_T.2->R_NVD_B.1), so it already has copper by the time this
    # runs -- _pad_routed_target(dest) would false-positive. Check this
    # path's own first segment instead.
    if _track_exists(board, ni.GetNetCode(), pcbnew.F_Cu, _mm(*pts[0]), _mm(*pts[1])):
        return
    _add_track(board, ni, pcbnew.F_Cu, pts, w)


def _route_vbus_sel_cross(board):
    """VBUS_SEL long run: R_LED_PWR.1 (top-left, 21.49,12.0) -> R_SHUNT.1
    (right cluster, 71.537,36.0). This crosses NATIVE_VBUS_DET's span
    (17.49-50.475) *and* all 6 north-threaded gap nets' columns (53.5-58.5,
    vertical ranges collectively spanning y=13.0(BTN_USER)-54.38) -- there's
    no F_Cu y left in the shared band that clears every one of them, so it
    hops to B_Cu (via right at the source -- R_LED_PWR is SMD) for the
    narrow window y=12.3-12.55 (clear of J_UART's THT pads below, bottom
    edge 11.85, *and* BTN_USER's column starting at 13.0) just long enough
    to clear x=58.5 (BTN_USER's own column, the rightmost). Re-entering
    F_Cu at x=60 (east of every column), it descends to y=28.0 -- below
    R_HDP/R_HDM's row *and* TP1/TP2/ESD_H's whole diagonal fan (which the
    original y=28 approach from farther out, x=90-102, rode straight
    through, since TP2's own pad/diagonal + J5's mechanical shield pads
    occupy nearly every y in 9-27 somewhere between x=60 and x=102 --
    turning immediately at x=60 avoids needing to cross that whole belt at
    all) -- before turning to R_SHUNT.1's column; ending the vertical at
    x=71.537 directly clips R_HDP.2/R_HDM.2's pads (x up to 71.395) if it
    runs the full y=12-36 span."""
    ni = _net(board, "VBUS_SEL")
    w = _class_width(board, "VBUS_SEL")
    ncls = board.GetDesignSettings().m_NetSettings.GetEffectiveNetClass("VBUS_SEL")
    via_dia, via_drill = pcbnew.ToMM(ncls.GetViaDiameter()), pcbnew.ToMM(ncls.GetViaDrill())
    dest = _pad(board, "R_SHUNT", "1")
    src = _pos(_pad(board, "R_LED_PWR", "1"))
    dest_xy = _pos(dest)
    hop_y = 12.4
    hop_x = 61.0  # clear of R_LED_USER.2's bbox (59.24-59.78,12.68-13.32)
    safe_y = 28.0
    # Both R_SHUNT.1 (U_ISNS.3->R_SHUNT.1) and R_LED_PWR.1 (JP1.2->
    # R_LED_PWR.1) are also local-cluster destinations, so either would
    # already have copper by the time this runs -- check for the hop's own
    # mid-point via instead (unique to this path).
    hop_pt = _mm(hop_x, hop_y)
    if any(t.GetClass() == "PCB_VIA" and t.GetPosition() == hop_pt for t in board.GetTracks()):
        return
    _add_via(board, ni, src, via_dia, via_drill)
    _add_track(board, ni, pcbnew.B_Cu, [src, (src[0], hop_y), (hop_x, hop_y)], w)
    _add_via(board, ni, (hop_x, hop_y), via_dia, via_drill)
    _add_track(board, ni, pcbnew.F_Cu,
               [(hop_x, hop_y), (hop_x, safe_y), (dest_xy[0], safe_y), dest_xy], w)


def _route_p3v3_extra(board):
    """P3V3's remaining breakout-cluster member: J_STEMMA.2 (29.5,5.4),
    sourced from J2B.16 (12.375,22.6). Interleaves with NATIVE_VBUS_DET's
    span at x=17.49 (NATIVE's own final descent), so hops to B_Cu briefly
    (16.5-18.5, y=18.0) right there before continuing F_Cu down into
    J_STEMMA -- same "finish horizontal motion above the row, then drop
    straight down" technique as Task 13's J3 convergence for the final
    vertical, so it can't clip J_STEMMA's neighboring pads 1/3/4."""
    ni = _net(board, "P3V3")
    w = _class_width(board, "P3V3")
    ncls = board.GetDesignSettings().m_NetSettings.GetEffectiveNetClass("P3V3")
    via_dia, via_drill = pcbnew.ToMM(ncls.GetViaDiameter()), pcbnew.ToMM(ncls.GetViaDrill())
    dest = _pad(board, "J_STEMMA", "2")
    if _pad_routed_target(board, dest):
        return
    src = _pos(_pad(board, "J2B", "16"))
    dest_xy = _pos(dest)
    y = 18.0
    pts = [src, (src[0], y), (16.5, y)]
    _add_track(board, ni, pcbnew.F_Cu, pts, w)
    _add_via(board, ni, (16.5, y), via_dia, via_drill)
    _add_track(board, ni, pcbnew.B_Cu, [(16.5, y), (18.5, y)], w)
    _add_via(board, ni, (18.5, y), via_dia, via_drill)
    _add_track(board, ni, pcbnew.F_Cu, [(18.5, y), (dest_xy[0], y), (dest_xy[0], 7.5), dest_xy], w)


def _route_vbus_net_cross(board):
    """VBUS_NET long run: JP1.3 (already tied to JP4.1/J2B.20 by the local
    + breakout phases) -> J8.1 (104.795,43.3). Its span (7.295-104.795)
    contains both NATIVE_VBUS_DET's and P3V3's, so the whole congested
    middle stretch (7.295-102.5, past J5's own footprint/cluster too --
    J5's courtyard/pads reach out to x~100.8, and its DP/DM/VBUS local
    wiring runs through x=70-97 at various y) hops to B_Cu at y=8.5 --
    clear of JP4's THT pads (top edge 10.15) and of R_NVD_T's SMD pads (top
    edge 9.18, irrelevant on B_Cu anyway)."""
    ni = _net(board, "VBUS_NET")
    w = _class_width(board, "VBUS_NET")
    ncls = board.GetDesignSettings().m_NetSettings.GetEffectiveNetClass("VBUS_NET")
    via_dia, via_drill = pcbnew.ToMM(ncls.GetViaDiameter()), pcbnew.ToMM(ncls.GetViaDrill())
    dest = _pad(board, "J8", "1")
    if _pad_routed_target(board, dest):
        return
    src = _pos(_pad(board, "JP1", "3"))
    dest_xy = _pos(dest)
    hop_y = 8.5
    hop_x = 102.5
    pts = [src, (src[0], hop_y)]
    _add_track(board, ni, pcbnew.F_Cu, pts, w)
    _add_via(board, ni, (src[0], hop_y), via_dia, via_drill)
    _add_track(board, ni, pcbnew.B_Cu, [(src[0], hop_y), (hop_x, hop_y)], w)
    _add_via(board, ni, (hop_x, hop_y), via_dia, via_drill)
    _add_track(board, ni, pcbnew.F_Cu, [(hop_x, hop_y), (hop_x, dest_xy[1])], w)
    # Final approach into J8.1 necks to Default width: J8's pad2 (GND,
    # 42.65) sits only 0.425mm off this row, and J8's own micro-B shield
    # tabs crowd the rest -- the full 0.5mm Power-class width doesn't clear
    # pad2 with margin (needs 0.45mm), Default (0.2mm) does (needs 0.3mm).
    default_w = pcbnew.ToMM(board.GetDesignSettings().m_NetSettings.GetDefaultNetclass().GetTrackWidth())
    _add_track(board, ni, pcbnew.F_Cu, [(hop_x, dest_xy[1]), dest_xy], default_w)


def _route_v5_jtrace(board):
    """V5_JTRACE: JP1.1 (2.215,11.0) -> J3.11 (13.66,65.95), down the far
    west edge (x=0.9) -- west of every Task-13 claim (B_Cu min x=3.485,
    F_Cu min x=4.035) and west of PICO/J1B pad-1's own copper (bbox left
    edge 1.415/1.365), then east into J3.11 along the debug row's own
    approach lane once clear of J1B's row."""
    ni = _net(board, "V5_JTRACE")
    w = _class_width(board, "V5_JTRACE")
    dest = _pad(board, "J3", "11")
    src = _pos(_pad(board, "JP1", "1"))
    dest_xy = _pos(dest)
    # J3.11 is also V5_JTRACE's local-cluster destination (J3.11<->J3.13),
    # so it already has copper by the time this runs -- _pad_routed_target
    # (dest) would false-positive. Check this path's own first segment
    # instead.
    if _track_exists(board, ni.GetNetCode(), pcbnew.F_Cu, _mm(*src), _mm(0.9, src[1])):
        return
    j1b_bottom = max(_bbox(_pad(board, "J1B", str(n)))[3] for n in range(1, 10))
    post_j1b_y = j1b_bottom + 0.6
    pts = [
        src, (0.9, src[1]), (0.9, post_j1b_y),
        (dest_xy[0], post_j1b_y), dest_xy,
    ]
    _add_track(board, ni, pcbnew.F_Cu, pts, w)


def _set_extra_power_classes(board):
    """VBUS_SEL and HOST_5V_IN carry the same 5V rail as the Power-classed
    nets (broken only by R_SHUNT/U_HSW) -- Task 10 didn't include them in
    the "Power" netclass pattern list, but the Task 14 brief calls them out
    explicitly under "Power tree (Power class 0.5mm)". Widen them by adding
    two more pattern entries to the existing class (not inventing a new
    one); per PLAN.md's verified environment facts, this needs an explicit
    SaveProject() or it's lost on the next LoadBoard."""
    ns = board.GetDesignSettings().m_NetSettings
    for n in ["VBUS_SEL", "HOST_5V_IN"]:
        ns.SetNetclassPatternAssignment(n, "Power")


def main():
    board = pcbnew.LoadBoard(BOARD_FILE)
    assert board is not None, f"LoadBoard({BOARD_FILE!r}) returned None"

    _route_trace_bundle(board)
    _route_swd_tree(board)

    _set_extra_power_classes(board)
    _route_breakout_stubs(board)
    _route_internal_ties(board)
    _route_local_clusters(board)
    _route_host_vbus_chain(board)
    # _route_gap_crossings(board) intentionally NOT called: see
    # task-14-report.md "Concerns" -- the 16 nets it targets (PICO row pads
    # fanning out to scattered right-side-cluster/top-region destinations)
    # produce a provably non-2-colorable crossing graph even after every
    # ordering/layer-split scheme tried (verified with a standalone geometric
    # simulator, not just the DRC run) -- some pairs need real local via-hops
    # that don't reduce to a clean parametrized rule. Their breakout stubs
    # (PICO<->J1B/J2B) ARE routed by _route_breakout_stubs above; only the
    # stub-to-final-component run is left for the Task 14 brief's sanctioned
    # interactive-GUI finish.
    _route_native_vbus_det(board)
    _route_vbus_sel_cross(board)
    _route_vbus_sel_jp1_tie(board)
    # _route_v5_jtrace(board) intentionally NOT called: see
    # task-14-report.md "Concerns". Its west-corridor path (idempotence bug
    # fixed, but only then actually exercised for the first time) crosses
    # Task 13's untouchable F_Cu trace bundle where it converges into J3's
    # bottom pin row -- confirmed by the real DRC run (tracks_crossing /
    # shorting_items against TD0/TD1/TD2/TRACECLK), not just inspection.
    # Fixing it safely needs the same B_Cu via-in-pad + hop technique Task
    # 13 used for J3's other pins, which requires integrating with Task
    # 13's own trunk/hop bookkeeping -- deferred rather than risk touching
    # untouchable routing under time pressure. J3.11/J3.13 are tied
    # together (_LOCAL_EDGES) and JP1.1 has its own breakout stub; only
    # the JP1.1<->J3.11 run itself is left for the interactive-GUI finish.
    _route_vbus_net_cross(board)
    _route_vbus_net_pico_tie(board)
    _route_p3v3_extra(board)

    pcbnew.SaveBoard(BOARD_FILE, board)
    pcbnew.GetSettingsManager().SaveProject()
    print("route_trace: done")


if __name__ == "__main__":
    main()
