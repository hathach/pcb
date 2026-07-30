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
_P3V3_DOGLEG_X_MM = 6.6   # post-J1B column P3V3's PICO descent jogs to,
                          # clear of JP2 (blocks x 1.965-3.665), of MH3's
                          # NPTH hole zone (x<=6.1 for y 57.9-62.1 at the
                          # Task-14c 92x64 board), and of J3's leftmost pad
                          # column (x=8.815, clear by 1.9mm on B_Cu)
_TRUNK_SPACING_MM = 0.85  # vertical spacing between the 4 nets' B_Cu trunks
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



# ============================================================================
# Task 14c: co-designed completion routing for the 92x64 board.
#
# Architecture (matched pair with hw/place.py's POS -- see task-14c-report):
#   - Top band (B_Cu, y 17.2..20.4, between J2B's row and PICO's top row):
#     west-to-east sources GP21/GP20/GP19/GP18 take shallow-to-deep lanes;
#     GP21/GP20 terminate in-band at R_HDM/R_HDP, GP19/GP18 descend the
#     east corridor to the device cluster (dest rows ordered to match).
#   - Bottom band (B_Cu, y 43.5..45.9): FLT/BTN/DPU/SCL/SDA, west source =
#     deeper lane; corridor columns at x 52.0..56.9.
#   - B_Cu rims across the top strip (y 9.4 VBUS_SEL, 13.05 VBUS_NET,
#     13.9 DEV_VBUS_DET, 14.35 ISENSE) with east-side drops at x 84.2/83.6.
#   - North-bound nets (I2C to STEMMA, GP10, UART, plus the DVD/ISENSE
#     escapes) thread PICO-top-row/J2B gap columns: B_Cu between the rows,
#     a via just north of the top row, F_Cu across the band/J2B/rim strip
#     (F is clear there; every horizontal system in the strip is B_Cu).
#   - GND stays unrouted (Task 15 pour), incl. SW1/SW_USER pad-2 pairs,
#     JP2.2/JP3.2, all *_PD pad 2s, TP3, ESD GND, shields.
# ============================================================================

_EAST = {}  # net -> corridor column x
_EAST["DPU"] = 52.0
_EAST["FLT"] = 52.6
_EAST["BTN"] = 53.52   # = SW_USER pad 1L x (F_Cu above y 22.3)
_EAST["SCL"] = 54.2
_EAST["SDA"] = 54.8
_EAST["GP19"] = 56.1
_EAST["GP18"] = 57.1

_TOP_LANE = {"GP21": 17.2, "GP20": 18.0, "GP19": 18.8, "GP18": 19.6}
_BOT_LANE = {"FLT": 43.5, "BTN": 44.1, "DPU": 44.7, "SCL": 45.3, "SDA": 45.9}

_RIM_SEL_Y = 9.4      # VBUS_SEL west-east rim (above the JP1/JP4 hole row)
_RIM_NET_Y = 13.05    # VBUS_NET short rim segment (x 12..13.645)
_RIM_DVD_Y = 13.9     # DEV_VBUS_DET rim -> east drop x 84.2
_RIM_ISNS_Y = 14.35   # ISENSE rim -> east drop x 83.6
_DROP_DVD_X = 84.2
_DROP_ISNS_X = 83.6

# North-bound gap columns (PICO top row / J2B share pin columns, so one gap
# x threads both rows) + per-net inter-row jog depth (stacked so no two
# same-layer segments collide; NRESET's Task-13 jog sits at y 23.9).
_GAP_COL = {"SDA": 28.885, "GP10": 33.965,
            "UART0_TX": 39.045, "UART0_RX": 41.585}
_NB_JOG = {"SDA": 25.1, "GP10": 24.5,
           "UART0_TX": 24.5, "UART0_RX": 24.5}
_NB_VIA_Y = 21.9      # F/B transition just north of PICO's top row


def _cls(board, net_name):
    ns = board.GetDesignSettings().m_NetSettings
    ncls = ns.GetEffectiveNetClass(net_name)
    return (pcbnew.ToMM(ncls.GetTrackWidth()),
            pcbnew.ToMM(ncls.GetViaDiameter()),
            pcbnew.ToMM(ncls.GetViaDrill()))


def _route_mixed(board, net_name, segs, width=None):
    """Idempotently add a mixed F/B path for `net_name`. `segs` is a list of
    ("F"|"B", [pts...]) runs; a via is dropped automatically at every layer
    transition point (last pt of one run == first pt of the next). Skip-if-
    present keyed on the first segment of the first run."""
    ni = _net(board, net_name)
    w, via_dia, via_drill = _cls(board, net_name)
    if width is not None:
        w = width
    first = segs[0][1]
    if _track_exists(board, ni.GetNetCode(),
                     pcbnew.F_Cu if segs[0][0] == "F" else pcbnew.B_Cu,
                     _mm(*first[0]), _mm(*first[1])):
        return False
    prev = None
    for layer_name, pts in segs:
        layer = pcbnew.F_Cu if layer_name == "F" else pcbnew.B_Cu
        if prev is not None and prev[1] is not None:
            pl, pp = prev
            if pl != layer_name:
                assert pp == pts[0], f"{net_name}: via point mismatch {pp} vs {pts[0]}"
                _add_via(board, ni, pts[0], via_dia, via_drill)
        _add_track(board, ni, layer, pts, w)
        prev = (layer_name, pts[-1])
    return True


def _p(board, ref, num, index=0):
    return _pos(_pad(board, ref, num, index))


# --- Local cluster edges (F_Cu; explicit waypoints where a plain bend would
# clip a neighbor). Pad numbers per hw/netlist.py padmaps: ESD 1=IO1 2=GND
# 3=IO2 4=IO2B 5=VBUS 6=IO1B; U_HSW 1=OUT 2=GND 3=FLG 4=EN 5=IN; U_ISNS
# 1=OUT 2=GND 3=IN+ 4=IN- 5=VS; J5 1=VBUS 2=DM 3=DP 4=GND; INA219 1=IN+
# 2=IN- 3=GND 4=VS 5=SCL 6=SDA.
_LOCAL_EDGES = [
    # Host D+ row (y 15.55): R_HDP.2 -> TP1 (in-line V-jog north) -> ESD_H.1;
    # ESD_H.6 -> J5.DP. R_HDP_PD taps ESD_H.1's pad box vertically.
    ("HOST_DP", ("R_HDP", "2"), ("TP1", "1"), None),
    ("HOST_DP", ("TP1", "1"), ("ESD_H", "1"), None),
    ("HOST_DP", ("R_HDP_PD", "1"), ("ESD_H", "1"), [(72.3, 15.55)]),
    ("HOST_DP", ("ESD_H", "6"), ("J5", "3"), None),
    # Host D- row (y 17.45): mirrored through TP2 (V-jog south).
    ("HOST_DM", ("R_HDM", "2"), ("TP2", "1"), None),
    ("HOST_DM", ("TP2", "1"), ("ESD_H", "3"), None),
    ("HOST_DM", ("R_HDM_PD", "1"), ("ESD_H", "3"), [(72.3, 17.45)]),
    ("HOST_DM", ("ESD_H", "4"), ("J5", "2"), None),
    # Device D+ row (y 43.75) and D- row (y 45.65) into ESD_D then J9.
    ("DEV_DP", ("R_DDP", "2"), ("ESD_D", "1"), None),
    ("DEV_DP", ("ESD_D", "6"), ("J9", "3"), [(85.5, 44.85)]),
    ("DEV_DM", ("R_DDM", "2"), ("ESD_D", "3"), None),
    ("DEV_DM", ("ESD_D", "4"), ("J9", "2"), None),
    # R_DPU.1 taps the DEV_DP row between R_DDP.2 and ESD_D.1.
    ("DEV_DP", ("R_DPU", "1"), ("R_DDP", "2"), [(63.0, 44.55), (70.3, 44.55), (70.3, 43.75)]),
    # ESD arrays are flow-through: tie each net's in/out pads through the body.
    ("HOST_DP", ("ESD_H", "1"), ("ESD_H", "6"), None),
    ("HOST_DM", ("ESD_H", "3"), ("ESD_H", "4"), None),
    ("DEV_DP", ("ESD_D", "1"), ("ESD_D", "6"), None),
    ("DEV_DM", ("ESD_D", "3"), ("ESD_D", "4"), None),
    # J9_VBUS web: divider top pad -> J9.1 (necked 0.3 past J9's shield pad),
    # DNP bus-power diode -> divider; ESD_D.5 joins via _route_j9_vbus_esd.
    ("J9_VBUS", ("R_J9VD_T", "1"), ("J9", "1"), [(85.3, 47.81), (85.3, 46.3)], 0.3),
    ("J9_VBUS", ("D_J9_BUSPWR", "1"), ("R_J9VD_T", "1"), [(82.4, 52.5), (82.4, 47.81)]),
    # DEV_VBUS_DET local: R_J9VD_T.2 -> R_J9VD_B.1 (straight, y 45.89).
    ("DEV_VBUS_DET", ("R_J9VD_T", "2"), ("R_J9VD_B", "1"), None),
    # NRESET: C_NRESET.1 drops onto SW1's pad-1 tie row.
    ("NRESET", ("C_NRESET", "1"), ("SW1", "1"), [(58.35, 53.55)]),
    # Power cluster locals (U_ISNS/U_INA219_ALT flank R_SHUNT; sense taps
    # necked to 0.25mm -- they carry no current). HOST_5V_IN's spine is a
    # single vertical at x 67.0 east of everything.
    ("HOST_5V_IN", ("U_INA219_ALT", "2"), ("U_HSW", "5"), [(67.0, 28.63), (67.0, 37.25)]),
    ("HOST_5V_IN", ("R_SHUNT", "2"), ("U_ISNS", "4"), [(67.0, 31.5), (67.0, 35.55)]),
    ("VBUS_SEL", ("U_INA219_ALT", "1"), ("R_SHUNT", "1"), [(62.64, 30.9)], 0.25),
    ("VBUS_SEL", ("U_ISNS", "3"), ("R_SHUNT", "1"), [(62.4, 35.55), (62.4, 31.5)], 0.25),
    # Power LED chain + native-VBUS-detect divider + user LED chain.
    ("LED_PWR_A", ("R_LED_PWR", "2"), ("LED_PWR", "2"), None),
    ("NATIVE_VBUS_DET", ("R_NVD_T", "2"), ("R_NVD_B", "1"), None),
    ("LED_USER", ("R_LED_USER", "2"), ("LED_USER", "2"), None),
    # V5_JTRACE local tie along J3's south row.
    ("V5_JTRACE", ("J3", "11"), ("J3", "13"), None),
]


def _route_local_clusters(board):
    for edge in _LOCAL_EDGES:
        net_name, (ref_a, pad_a), (ref_b, pad_b), bend = edge[:4]
        ni = _net(board, net_name)
        w = edge[4] if len(edge) > 4 else _class_width(board, net_name)
        p0 = _p(board, ref_a, pad_a)
        p1 = _p(board, ref_b, pad_b)
        if bend is None:
            pts = [p0, p1]
        elif callable(bend):
            pts = bend(p0, p1)
        else:
            pts = [p0] + list(bend) + [p1]
        _add_path_once(board, ni, pcbnew.F_Cu, pts, w)


def _route_top_band(board):
    """GP21/GP20/GP19/GP18: PICO top-row pads (THT, direct B_Cu) escape
    north into their lanes and head east. GP21/GP20 terminate at R_HDM.1/
    R_HDP.1 (dest rows chosen == lane order, so no crossings); GP19/GP18
    descend corridor columns to R_DDM.1/R_DDP.1. GP18 (east source, deep
    lane, shallow dest -- the one genuine inversion) hops F_Cu over GP19's
    column at the lane depth."""
    # GP21 -> R_HDM.1 (67.01,17.45): via at lane end, short F feed.
    p27 = _p(board, "PICO", "27")
    hdm1 = _p(board, "R_HDM", "1")
    _route_mixed(board, "GP21", [
        ("B", [p27, (p27[0], 17.2), (66.2, 17.2)]),
        ("F", [(66.2, 17.2), hdm1]),
    ])
    # GP20 -> R_HDP.1 (67.01,15.55): via west of R_HDM, F north then east.
    p26 = _p(board, "PICO", "26")
    hdp1 = _p(board, "R_HDP", "1")
    _route_mixed(board, "GP20", [
        ("B", [p26, (p26[0], 18.0), (65.6, 18.0)]),
        ("F", [(65.6, 18.0), (65.6, 15.55), hdp1]),
    ])
    # GP19 -> corridor col 55.9 -> exit y 45.65 -> via -> F -> R_DDM.1.
    p25 = _p(board, "PICO", "25")
    ddm1 = _p(board, "R_DDM", "1")
    _route_mixed(board, "GP19", [
        ("B", [p25, (p25[0], 18.8), (_EAST["GP19"], 18.8),
               (_EAST["GP19"], 45.65), (67.5, 45.65)]),
        ("F", [(67.5, 45.65), ddm1]),
    ])
    # GP18: B lane 19.6 to x 55.3, F hop over GP19's column, B col 56.9
    # down to y 43.75, east, via, F feed into R_DDP.1.
    p24 = _p(board, "PICO", "24")
    ddp1 = _p(board, "R_DDP", "1")
    _route_mixed(board, "GP18", [
        ("B", [p24, (p24[0], 19.6), (55.5, 19.6)]),
        ("F", [(55.5, 19.6), (_EAST["GP18"], 19.6)]),
        ("B", [(_EAST["GP18"], 19.6), (_EAST["GP18"], 43.75), (67.5, 43.75)]),
        ("F", [(67.5, 43.75), ddp1]),
    ])


def _route_bottom_band(board):
    """Bottom-row escapes into the east corridor. Sources descend from
    their THT pads to their lanes (west source = deeper lane), run east,
    and resolve at their columns: FLT ascends to U_HSW.FLG, BTN ascends
    (B to y 22.3, then F -- its column doubles as SW_USER pad 1L's x) to
    the user button, DPU drops to R_DPU.2, SCL/SDA ascend to the INA219
    (DNP) I2C pads."""
    flg = _p(board, "U_HSW", "3")
    p20 = _p(board, "PICO", "20")
    _route_mixed(board, "HOST_VBUS_FLT", [
        ("B", [p20, (p20[0], _BOT_LANE["FLT"]), (_EAST["FLT"], _BOT_LANE["FLT"]),
               (_EAST["FLT"], flg[1])]),
        ("F", [(_EAST["FLT"], flg[1]), flg]),
    ])
    p19 = _p(board, "PICO", "19")
    sw1l = _p(board, "SW_USER", "1")  # west pad of the pad-1 pair
    _route_mixed(board, "BTN_USER", [
        ("B", [p19, (p19[0], _BOT_LANE["BTN"]), (_EAST["BTN"], _BOT_LANE["BTN"]),
               (_EAST["BTN"], 22.3)]),
        ("F", [(_EAST["BTN"], 22.3), (_EAST["BTN"], 13.4), (52.445, 13.4),
               (52.445, 8.0), sw1l]),
    ])
    p15 = _p(board, "PICO", "15")
    dpu2 = _p(board, "R_DPU", "2")
    _route_mixed(board, "DEV_DP_PU_EN", [
        ("B", [p15, (p15[0], _BOT_LANE["DPU"]), (51.4, _BOT_LANE["DPU"])]),
        ("F", [(51.4, _BOT_LANE["DPU"]), (51.4, 47.0), (63.0, 47.0), dpu2]),
    ])
    # SCL/SDA: south lanes east, columns north to the INA219's west pads;
    # the north (STEMMA) branches are separate paths in _route_north_bound.
    p12 = _p(board, "PICO", "12")
    ina_scl = _p(board, "U_INA219_ALT", "5")
    _route_mixed(board, "I2C0_SCL", [
        ("B", [p12, (p12[0], _BOT_LANE["SCL"]), (_EAST["SCL"], _BOT_LANE["SCL"]),
               (_EAST["SCL"], ina_scl[1])]),
        ("F", [(_EAST["SCL"], ina_scl[1]), ina_scl]),
    ])
    p11 = _p(board, "PICO", "11")
    ina_sda = _p(board, "U_INA219_ALT", "6")
    _route_mixed(board, "I2C0_SDA", [
        ("B", [p11, (p11[0], _BOT_LANE["SDA"]), (_EAST["SDA"], _BOT_LANE["SDA"]),
               (_EAST["SDA"], ina_sda[1])]),
        ("F", [(_EAST["SDA"], ina_sda[1]), ina_sda]),
    ])


def _route_north_bound(board):
    """STEMMA I2C, GP10 and UART: B_Cu inter-row ascent from the bottom-row
    THT pad, jog to a gap column, B through the top-row gap, via at
    y 21.9, then F_Cu north across the band/J2B/rim strip to the top-edge
    peripheral (F is clear there; all the horizontal strip systems are B)."""
    def nb(net, pico_pad, tail_F, key=None):
        key = key or net
        src = _p(board, "PICO", pico_pad)
        g = _GAP_COL[key]
        jog = _NB_JOG[key]
        _route_mixed(board, net, [
            ("B", [src, (src[0], jog), (g, jog), (g, _NB_VIA_Y)]),
            ("F", [(g, _NB_VIA_Y)] + tail_F),
        ])

    # SCL -> J_STEMMA.4 (27.5,5.4): must reach the *west* gap (dest order)
    # from the *east* source -- hop F over SDA's inter-row ascent and the
    # NRESET diagonal at y 25.5, then down the 26.345 gap column.
    st4 = _p(board, "J_STEMMA", "4")
    p12n = _p(board, "PICO", "12")
    _route_mixed(board, "I2C0_SCL", [
        ("B", [p12n, (p12n[0], 25.9), (28.25, 25.9)]),
        ("F", [(28.25, 25.9), (25.7, 25.9)]),
        ("B", [(25.7, 25.9), (25.7, 24.1), (26.345, 24.1), (26.345, _NB_VIA_Y)]),
        ("F", [(26.345, _NB_VIA_Y), (26.345, 7.0), (st4[0], 7.0), st4]),
    ])
    # SDA -> J_STEMMA.3 (28.5,5.4), same pattern one gap east.
    st3 = _p(board, "J_STEMMA", "3")
    nb("I2C0_SDA", "11", [(_GAP_COL["SDA"], 7.0), (st3[0], 7.0), st3], key="SDA")
    # GP10 -> R_LED_USER.1 (col == pad x, straight in).
    rlu1 = _p(board, "R_LED_USER", "1")
    nb("GP10", "14", [rlu1])
    # UART: pin columns sit just east of their gaps.
    j_u1 = _p(board, "J_UART", "1")
    nb("UART0_TX", "16", [(_GAP_COL["UART0_TX"], 12.4), j_u1])
    j_u2 = _p(board, "J_UART", "2")
    nb("UART0_RX", "17", [(_GAP_COL["UART0_RX"], 12.4), j_u2])


def _route_rims(board):
    """DEV_VBUS_DET + ISENSE: top-row escapes at the west end of the row
    (west of every lane's x-span), north through their own gap columns,
    east along B_Cu rims across the whole top strip, then down the far-east
    drops (between J5's shell holes at x<=82.9 and MH2/MH4's zone x>=84.5)
    to the device divider / the INA180."""
    p32 = _p(board, "PICO", "32")   # DEV_VBUS_DET, x 22.535
    t2 = _p(board, "R_J9VD_T", "2")  # (82.6,45.89)
    b1 = _p(board, "R_J9VD_B", "1")  # (80.9,45.89)
    _route_mixed(board, "DEV_VBUS_DET", [
        ("B", [p32, (p32[0], 21.35), (23.805, 21.35), (23.805, _RIM_DVD_Y),
               (76.6, _RIM_DVD_Y), (76.6, 11.815), (_DROP_DVD_X, 11.815),
               (_DROP_DVD_X, t2[1] - 0.29)]),
        ("F", [(_DROP_DVD_X, t2[1] - 0.29), (_DROP_DVD_X, t2[1]), t2, b1]),
    ])
    p31 = _p(board, "PICO", "31")   # ISENSE, x 25.075
    out1 = _p(board, "U_ISNS", "1")  # (63.46,33.65)
    _route_mixed(board, "ISENSE", [
        ("B", [p31, (p31[0], 21.0), (26.345, 21.0), (26.345, _RIM_ISNS_Y),
               (_DROP_ISNS_X, _RIM_ISNS_Y), (_DROP_ISNS_X, 30.1), (65.6, 30.1)]),
        ("F", [(65.6, 30.1), (64.4, 30.1), (64.4, out1[1]), out1]),
    ])


def _route_en(board):
    """HOST_VBUS_EN: PICO.22 -> F gap column 46.665 north -> east at y 10.6
    (threading between SW_USER's pad rows) with a short B hop under BTN's
    F column -> F column x 62.6 south across the band (F is clear; every
    horizontal band system is B) -> via -> B to y 40.6 -> via -> F into
    U_HSW.EN + R_HVEN_PD.1."""
    p22 = _p(board, "PICO", "22")
    en = _p(board, "U_HSW", "4")      # (65.64,39.15)
    pd1 = _p(board, "R_HVEN_PD", "1")  # (65.64,41.09)
    _route_mixed(board, "HOST_VBUS_EN", [
        ("F", [p22, (p22[0], 21.9), (46.665, 21.9), (46.665, 10.6), (51.1, 10.6)]),
        ("B", [(51.1, 10.6), (54.9, 10.6)]),
        ("F", [(54.9, 10.6), (62.6, 10.6), (62.6, 21.6)]),
        ("B", [(62.6, 21.6), (62.6, 40.6)]),
        ("F", [(62.6, 40.6), (65.64, 40.6), en]),
    ])
    ni = _net(board, "HOST_VBUS_EN")
    _add_path_once(board, ni, pcbnew.F_Cu, [(65.64, 40.6), pd1],
                   _class_width(board, "HOST_VBUS_EN"))


def _route_vbus_sel(board):
    """VBUS_SEL: JP1.2 -> B rim y 9.4 (above the JP1/JP4 hole row) east to
    x 60.4 -> B down to 13.5 -> F hop across the rim/band strip -> B down
    to 31.5 -> via -> F into R_SHUNT.1. Branch at x 10.2: via + F north to
    R_LED_PWR.1 (threading the JP1.3/JP4.1 hole gap)."""
    jp1_2 = _p(board, "JP1", "2")
    sh1 = _p(board, "R_SHUNT", "1")
    _route_mixed(board, "VBUS_SEL", [
        ("B", [jp1_2, (jp1_2[0], _RIM_SEL_Y), (60.4, _RIM_SEL_Y), (60.4, 13.2)]),
        ("F", [(60.4, 13.2), (60.4, 20.8)]),
        ("B", [(60.4, 20.8), (60.4, 31.5)]),
        ("F", [(60.4, 31.5), sh1]),
    ])
    led1 = _p(board, "R_LED_PWR", "1")
    _route_mixed(board, "VBUS_SEL", [
        ("B", [(10.2, _RIM_SEL_Y), (10.2, 9.5)]),
        ("F", [(10.2, 9.5), led1]),
    ])


def _route_vbus_net(board):
    """VBUS_NET: JP1.3 -> JP4.1 on B at the hole row's own y; JP4.1 diag to
    the long descent column x 13.645 (a shared PICO/J1B/J2B gap column),
    south through all four THT rows to y 50.3, east along y 50.3 (F-hopping
    NRESET's B descent at x 21.265), via at (76.8,50.3), F to
    D_J9_BUSPWR.2. Feeders: J8.1 (via 18.3,11.9 -> B west at y 12.4),
    J2B.20 (B north + east at y 13.7)."""
    jp1_3 = _p(board, "JP1", "3")
    jp4_1 = _p(board, "JP4", "1")
    d2 = _p(board, "D_J9_BUSPWR", "2")
    _route_mixed(board, "VBUS_NET", [
        ("B", [jp1_3, jp4_1, (jp4_1[0], 12.55), (18.725, 12.55),
               (18.725, 50.3), (20.3, 50.3)]),
        ("F", [(20.3, 50.3), (22.3, 50.3)]),
        ("B", [(22.3, 50.3), (76.8, 50.3)]),
        ("F", [(76.8, 50.3), (76.8, d2[1]), d2]),
    ], width=0.35)
    j8_1 = _p(board, "J8", "1")
    _route_mixed(board, "VBUS_NET", [
        ("F", [j8_1, (j8_1[0], 12.55)]),
        ("B", [(j8_1[0], 12.55), (18.725, 12.55)]),
    ], width=0.4)
    j2b20 = _p(board, "J2B", "20")
    _route_mixed(board, "VBUS_NET", [
        ("B", [j2b20, (j2b20[0], 13.7), (18.725, 13.7)]),
    ])


def _route_nvd(board):
    """NVD_TOP: JP4.2 -> B at y 11.55 east to the divider -> via -> F into
    R_NVD_T.1. NATIVE_VBUS_DET: branch off the T.2<->B.1 tie southward,
    B at y 8.55 east to x 52.3, via, F south past the rims into J2B.1
    (whose breakout stub then feeds PICO.21)."""
    jp4_2 = _p(board, "JP4", "2")
    t1 = _p(board, "R_NVD_T", "1")   # (30.8,10.11)
    _route_mixed(board, "NVD_TOP", [
        ("B", [jp4_2, (jp4_2[0], 11.35), (t1[0], 11.35), (t1[0], 11.2)]),
        ("F", [(t1[0], 11.2), t1]),
    ])
    t2 = _p(board, "R_NVD_T", "2")   # (30.8,9.09)
    j2b1 = _p(board, "J2B", "1")     # (50.475,15.6)
    _route_mixed(board, "NATIVE_VBUS_DET", [
        ("F", [(31.7, t2[1]), (31.7, 8.55)]),
        ("B", [(31.7, 8.55), (51.7, 8.55)]),
        ("F", [(51.7, 8.55), (51.7, 15.1), j2b1]),
    ])


def _route_j9_vbus_esd(board):
    """ESD_D.5 (VBUS clamp) -> the J9_VBUS web at R_J9VD_T.1: short F east,
    then a B diagonal under the D+/D- fan-out, re-emerging beside the
    divider."""
    esd5 = _p(board, "ESD_D", "5")     # (78.64,44.7)
    t1 = _p(board, "R_J9VD_T", "1")    # (82.6,47.81)
    _route_mixed(board, "J9_VBUS", [
        ("F", [esd5, (79.9, esd5[1])]),
        ("B", [(79.9, esd5[1]), (81.75, 47.55)]),
        ("F", [(81.75, 47.55), t1]),
    ])


def _route_host_vbus(board):
    """HOST_VBUS: U_HSW.OUT -> via west of the EN corridor -> B north to
    y 26.4 -> F east through the two bulk caps' pad-1s -> via (77.3,26.4)
    -> B column between ESD_H/J5's pads and J5's shell holes, tapping
    J5.1 (THT) at y 20 and ending at a via that feeds ESD_H.5 on F."""
    out = _p(board, "U_HSW", "1")     # (63.36,37.25)
    esd5 = _p(board, "ESD_H", "5")    # (74.74,16.5)
    j5_1 = _p(board, "J5", "1")       # (78.615,20.0)
    c1a = _p(board, "C_HVBUS_100n", "1")
    c1b = _p(board, "C_HVBUS_BULK", "1")
    _route_mixed(board, "HOST_VBUS", [
        ("F", [out, (59.6, out[1])]),
        ("B", [(59.6, out[1]), (59.6, 26.4)]),
        ("F", [(59.6, 26.4), (77.3, 26.4)]),
        ("B", [(77.3, 26.4), (77.3, 16.5)]),
        ("F", [(77.3, 16.5), esd5]),
    ])
    ni = _net(board, "HOST_VBUS")
    w, _vd, _vdr = _cls(board, "HOST_VBUS")
    _add_path_once(board, ni, pcbnew.B_Cu, [(77.3, j5_1[1]), j5_1], w)
    _add_path_once(board, ni, pcbnew.F_Cu, [(c1a[0], 26.4), c1a], w)
    _add_path_once(board, ni, pcbnew.F_Cu, [(c1b[0], 26.4), c1b], w)


def _route_p3v3_cluster(board):
    """P3V3 to the power cluster, sourced at PICO.36's own THT pad: B_Cu
    inter-row descent at x 12.375, west jog above the bottom row, through
    the row's 4/5 gap column (11.105), then a deep bottom-band lane at
    y 46.35 (below every bottom-band escape) east to a column at x 61.55
    (west of EN's B column), F-hopping the GP19/GP18 exit rows, up to
    U_INA219_ALT.VS. U_ISNS.VS hangs off that via a B diagonal into a
    small via-in-pad (0.5/0.3 -- drill at the DFM floor). Whole subtree
    necked to 0.25mm (mA-level VS/VS supply taps; the 0.5mm Power rail
    would not clear the row-gap crossings, same precedent as the SWD
    tree's P3V3 descent)."""
    p36 = _p(board, "PICO", "36")
    ina_vs = _p(board, "U_INA219_ALT", "4")   # (62.64,27.33)
    isns_vs = _p(board, "U_ISNS", "5")        # (65.74,33.65)
    _route_mixed(board, "P3V3", [
        ("B", [p36, (p36[0], 39.3)]),
        ("F", [(p36[0], 39.3), (23.805, 39.3)]),
        ("B", [(23.805, 39.3), (23.805, 49.65), (61.55, 49.65),
               (61.55, 46.35)]),
        ("F", [(61.55, 46.35), (61.55, 42.9)]),
        ("B", [(61.55, 42.9), (61.55, ina_vs[1])]),
        ("F", [(61.55, ina_vs[1]), ina_vs]),
    ], width=0.25)
    ni = _net(board, "P3V3")
    if not _track_exists(board, ni.GetNetCode(), pcbnew.F_Cu,
                         _mm(ina_vs[0] + 0.66, ina_vs[1]), _mm(63.8, ina_vs[1])):
        _add_track(board, ni, pcbnew.F_Cu,
                   [(ina_vs[0] + 0.66, ina_vs[1]), (63.8, ina_vs[1])], 0.25)
        _add_via(board, ni, (63.8, ina_vs[1]), 0.6, 0.3)
        _add_track(board, ni, pcbnew.B_Cu, [(63.8, ina_vs[1]), isns_vs], 0.25)
        _add_via(board, ni, isns_vs, 0.5, 0.3)


def _route_p3v3_stemma(board):
    """P3V3 to J_STEMMA.2: J2B.16 (THT) -> F north -> east at y 13.55 ->
    north column x 24.4 (west of the STEMMA shield pad) -> over the top at
    y 2.6 -> down into pad 2 from the north."""
    j2b16 = _p(board, "J2B", "16")   # (12.375,15.6)
    st2 = _p(board, "J_STEMMA", "2")  # (29.5,5.4)
    _route_mixed(board, "P3V3", [
        ("F", [j2b16, (j2b16[0], 13.55), (24.4, 13.55), (24.4, 2.95),
               (st2[0], 2.95), st2]),
    ])


def _route_v5_jtrace(board):
    """V5_JTRACE: JP1.1 -> west corridor x 0.9 -> east through J3's
    inter-pad-row band (y 55.8, between the north row's 55.05 bottom and
    the south row's 56.55 top) -> drop into J3.11 at its own column.
    Necked to 0.3mm for the inter-row ride."""
    jp1_1 = _p(board, "JP1", "1")
    j3_11 = _p(board, "J3", "11")
    ni = _net(board, "V5_JTRACE")
    w = _class_width(board, "V5_JTRACE")
    _add_path_once(board, ni, pcbnew.F_Cu, [jp1_1, (0.9, jp1_1[1])], w)
    _add_path_once(board, ni, pcbnew.F_Cu,
                   [(0.9, jp1_1[1]), (0.9, 55.8), (j3_11[0], 55.8), j3_11], 0.3)


def _set_extra_power_classes(board):
    ns = board.GetDesignSettings().m_NetSettings
    for n in ("VBUS_SEL", "HOST_5V_IN"):
        ns.SetNetclassPatternAssignment(n, "Power")


def main():
    b = pcbnew.LoadBoard(BOARD_FILE)
    assert b is not None, f"LoadBoard({BOARD_FILE!r}) returned None"

    _route_trace_bundle(b)
    _route_swd_tree(b)

    _route_breakout_stubs(b)
    _route_internal_ties(b)
    _route_local_clusters(b)
    _route_top_band(b)
    _route_bottom_band(b)
    _route_north_bound(b)
    _route_rims(b)
    _route_en(b)
    _route_vbus_sel(b)
    _route_vbus_net(b)
    _route_nvd(b)
    _route_j9_vbus_esd(b)
    _route_host_vbus(b)
    _route_p3v3_cluster(b)
    _route_p3v3_stemma(b)
    _route_v5_jtrace(b)

    _set_extra_power_classes(b)

    pcbnew.SaveBoard(BOARD_FILE, b)
    pcbnew.GetSettingsManager().SaveProject()
    print(f"routed: tracks={len(list(b.GetTracks()))}")


if __name__ == "__main__":
    main()
