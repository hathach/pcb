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


def main():
    board = pcbnew.LoadBoard(BOARD_FILE)
    assert board is not None, f"LoadBoard({BOARD_FILE!r}) returned None"

    _route_trace_bundle(board)
    _route_swd_tree(board)

    pcbnew.SaveBoard(BOARD_FILE, board)
    print("route_trace: done")


if __name__ == "__main__":
    main()
