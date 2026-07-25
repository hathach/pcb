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

  - SWDIO, SWCLK: daisy chain J3-J6-J7 via a B_Cu trunk.
  - NRESET: PICO.30 -> J3.10 -> J6.10 -> SW1.1 via B_Cu.
  - P3V3 (VTref taps only -- the rest of this net is Task 14's job):
    PICO.36 -> J3.1 -> J6.1 via B_Cu, necked to Default width (0.2mm) for
    the PICO/J1B header-row crossing (0.5mm does not fit an 0.84mm
    pin-pitch gap with clearance to spare: 0.17mm < 0.2mm required; 0.2mm
    clears with margin, 0.32mm).

  B_Cu is used for all four of these because J3/J6/J7/SW1 are all SMD
  (F_Cu-only) -- B_Cu is unobstructed under them; only the THT parts
  PICO/J1B/J2B/JP2/JP3 carry B_Cu copper, and only PICO's own header row
  and J1B's breakout row lie on the NRESET/P3V3 descent from PICO (each
  crossed once, through an unused inter-pin gap, same technique as the
  trace bundle). SWDIO and SWCLK share the same 3 physical connectors, so
  a "shallower" net's full-width B_Cu trunk is unavoidably crossed by a
  "deeper" net's vertical pad-to-trunk run wherever their X ranges
  overlap (they mostly do, since all three connectors are shared) --
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
# Task-14f re-placement note: J3/J6's pads are 2.4mm TALL (not wide --
# footprint rotation swaps W/H), so the two pin rows sit at y 56.05-58.45
# (north: SWDIO/SWCLK/-/-/NRESET/[trace bundle]) and y 59.95-62.35 (south:
# P3V3/GND/GND/-/GND/V5_JTRACE...), only 1.5mm apart. The board is also
# only 64.1mm tall, so "stack all 4 trunks south of SW1" (the pre-Task-14f
# strategy) no longer fits at all (SW1's own bottom pad edge is at
# y=62.855, leaving under 1mm before the 0.5mm board-edge-clearance
# limit) -- and even 3 B_Cu trunks sharing the 1.5mm inter-row gap don't
# DRC-clean (a hopping net's via, clipped to land at its own trunk_y,
# needs 0.6mm clearance -- via radius 0.3 + track halfwidth 0.1 +
# clearance 0.2 -- from EVERY other trunk it's near, and 3-way stacking
# in 1.5mm can't provide that everywhere).
#
# New strategy: SWDIO and NRESET are the *only* B_Cu nets through the
# tight inter-row gap (NRESET hopping over SWDIO via `_spike_to_trunk`'s
# shallower-trunk machinery -- proven DRC-clean: 0.3mm row-edge margin +
# 0.6mm+ via-vs-track clearance + 0.5mm+ via-vs-south-row margin, all
# inside 1.5mm with a few hundredths of a mm to spare). A *third* net
# sharing this gap on either layer always collides with one of the two:
# 3-way B_Cu stacking needs 0.3+0.6+0.6+0.5=2.0mm (only 1.5mm exists),
# and a constant-y F_Cu net collides with NRESET's hop bridge -- which,
# to physically get past SWDIO's B_Cu line, must itself occupy B_Cu
# across a ~1.3mm y-span centered on SWDIO's trunk, which is most of the
# gap's own height.
#
# So SWCLK and P3V3 skip the gap entirely -- both plain F_Cu, which
# never needs clearance against SWDIO/NRESET's B_Cu (different layer);
# they only need to dodge the *pads* they pass on the way down (the
# south row's own GND/P3V3 pads share SWCLK's J3/J6 columns) via a
# sideways jog while still between the two rows (open, unconstrained by
# pad pitch there), landing in a south-of-south-row F_Cu band
# (_SWD_LANE_Y) where SWCLK and P3V3 in turn need only ONE mutual hop
# (SWCLK is shallow and spans wider -- J3/J6/J7 -- so keeping it
# shallow means P3V3, which only touches J3/J6, needs just a single hop
# where its J6 spike must pass SWCLK's line).
_SWD_TREE = {
    "SWDIO": [("J3", "2"), ("J6", "2"), ("J7", "3")],
    "SWCLK": [("J3", "4"), ("J6", "4"), ("J7", "1")],
    "NRESET": [("J3", "10"), ("J6", "10"), ("SW1", "1")],
    "P3V3": [("J3", "1"), ("J6", "1")],
}
_SWD_LANE_Y = {"SWDIO": 58.80, "NRESET": 59.42, "SWCLK": 62.65, "P3V3": 62.90}
_HOP_MM = 0.65            # F_Cu-hop half-span around a crossed shallower
                          # B_Cu trunk (NRESET hopping SWDIO) -- clears
                          # via radius (0.3) + track halfwidth (0.1) +
                          # clearance (0.2) = 0.6mm from the crossed
                          # track's centerline, with a hair of margin.
# NRESET's PICO descent: gap pins 9/10 (x=23.805) -- east of the whole
# trace-bundle corridor (lanes max x=16.185, J3 landings max x=20.605) AND
# with real margin from J3's TD3 pad (edge x=20.975): the nearer 8/9 gap
# (x=21.265) is only 0.29mm from that edge, not enough for the hop-via
# NRESET needs there (0.5mm: via radius 0.3 + clearance 0.2) even though
# a plain track fits fine.
_NRESET_PICO_GAP = ("PICO", "30", "9", "10")
# SWCLK's J3/J6 columns (10.445/51.13) sit directly above a south-row GND
# pad at the *same* x -- jog to a clear column before descending past it.
_SWCLK_ESCAPE_X = {"J3": 7.5, "J6": 48.5}  # WEST -- east would cross
                                           # NRESET's B_Cu-hop F_Cu bridge
                                           # (a single-point obstacle at
                                           # x=14.255/23.805/54.94, y
                                           # 58.15-59.42) which only
                                           # exists east of J3/J6's own
                                           # columns here
_ROW_CLEAR_Y = 58.90     # south of J3/J6/J7's north-row pad bottom
                         # edge (58.45) by 0.45mm -- SWCLK's safe y to
                         # jog sideways in before continuing down
# P3V3's PICO descent: gap pins 1/2 (x=3.485, PICO's own westmost gap),
# then a short dogleg WEST to x=0.7 -- east (as originally tried) crosses
# the trace bundle's own TRACECLK lane (x=6.025, occupied y~49.0-55.4).
# The dogleg happens south of JP2 (pad bbox bottom edge 53.105 at
# x=2.215; GP0's guard-net breakout runs J1B(47.8)->JP2(52.255) right
# through that column) but the deep run down to the south band only
# rejoins x=7.0 (not staying at x=0.7 the whole way) -- x=0.7 clips the
# board's rounded SW corner once y gets as deep as the south band (arc
# center (3,61) r=3mm; solving for the min x clearing r+0.5mm clearance+
# 0.1mm halfwidth at y=62.9 gives x>=6.15), so the path returns east to
# x=7.0 (clear of both the corner and MH3's NPTH hole -- pad bbox x
# 2.4-5.6, y 58.4-61.6, r=1.6mm center (4,60); needs center-to-track
# >=1.6+0.25+0.1=1.95mm, x=7.0 gives 3.0mm) at y=57.0, i.e. *after*
# TRACECLK's lane has already ended (conv_start ~55.4) so the return
# jog can't cross it either.
_P3V3_PICO_GAP = ("PICO", "36", "1", "2")
_P3V3_WEST_X_MM = 0.7
_P3V3_DOGLEG_X_MM = 7.0
_P3V3_DOGLEG_Y_MM = 57.0


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


def _route_swd_tree_bcu(board, net_name, shallower, pico_gap=None):
    """B_Cu trunk at _SWD_LANE_Y[net_name], via-per-node (J3/J6/J7/SW1
    pads are all F_Cu-only SMD), hopping over any already-routed
    *shallower* B_Cu trunk via `_spike_to_trunk`. Only SWDIO uses this
    path now (see module-level comment) -- kept general in case a future
    net needs the same shallower-hop machinery."""
    ni = _net(board, net_name)
    trunk_y = _SWD_LANE_Y[net_name]
    if _net_has_tracks(board, ni):
        xs = [_pos(_pad(board, r, p))[0] for r, p in _SWD_TREE[net_name]]
        if pico_gap:
            xs.append(_gap_x(board, pico_gap[0], pico_gap[2], pico_gap[3]))
        shallower.append((trunk_y, min(xs) - 1.0, max(xs) + 1.0))
        return

    ncls = board.GetDesignSettings().m_NetSettings.GetEffectiveNetClass(net_name)
    width_mm = pcbnew.ToMM(ncls.GetTrackWidth())
    via_dia = pcbnew.ToMM(ncls.GetViaDiameter())
    via_drill = pcbnew.ToMM(ncls.GetViaDrill())

    xs = []
    for ref, pad in _SWD_TREE[net_name]:
        xy = _pos(_pad(board, ref, pad))
        _add_via(board, ni, xy, via_dia, via_drill)
        pxo = _spike_to_trunk(board, ni, xy[0], xy[1], trunk_y, width_mm, via_dia, via_drill, shallower)
        xs.append(pxo)

    if pico_gap:
        pico_ref, pico_pad, gap_a, gap_b = pico_gap
        pico_xy = _pos(_pad(board, pico_ref, pico_pad))
        gap_x = _gap_x(board, pico_ref, gap_a, gap_b)
        approach_y = _approach_above(board, pico_ref, [gap_a, gap_b])
        _add_track(board, ni, pcbnew.B_Cu, [pico_xy, (gap_x, approach_y)], width_mm)
        _spike_to_trunk(board, ni, gap_x, approach_y, trunk_y, width_mm, via_dia, via_drill, shallower)
        xs.append(gap_x)

    x0, x1 = min(xs), max(xs)
    _add_track(board, ni, pcbnew.B_Cu, [(x0, trunk_y), (x1, trunk_y)], width_mm)
    shallower.append((trunk_y, x0 - 1.0, x1 + 1.0))


def _route_swclk(board):
    """SWCLK: plain F_Cu throughout, no vias -- J3/J6/J7 pads are all
    F_Cu-only SMD. Skips the tight inter-row gap (SWDIO/NRESET's B_Cu
    territory -- different layer, so no clearance conflict either way,
    but the gap has no room left regardless) and descends straight to
    the south-of-south-row band (_SWD_LANE_Y['SWCLK'], the *shallow* F_Cu
    lane -- P3V3 hops over it, see _route_p3v3_swd). J3/J6's columns
    (10.445/51.13) sit directly above a south-row GND pad at the *same*
    x, so those two nodes jog to a connector-clear column
    (_SWCLK_ESCAPE_X) while still between the rows (open, unconstrained
    by row pad pitch) before continuing down; J7 is a simple single-row
    header with nothing blocking below, so it descends directly."""
    ni = _net(board, "SWCLK")
    if _net_has_tracks(board, ni):
        return
    w = _class_width(board, "SWCLK")
    south_y = _SWD_LANE_Y["SWCLK"]
    xs = []
    for ref, pad in _SWD_TREE["SWCLK"]:
        x, y = _pos(_pad(board, ref, pad))
        esc_x = _SWCLK_ESCAPE_X.get(ref, x)
        # Straight down the pad's own column to _ROW_CLEAR_Y first (south
        # of the row's bottom edge, 58.45) -- *then* jog sideways. Jogging
        # at the pad's own y=57.2-57.25 would sweep straight through the
        # whole row (every other pin's pad, plus the trace bundle's
        # landing columns further east).
        _add_track(board, ni, pcbnew.F_Cu,
                   [(x, y), (x, _ROW_CLEAR_Y), (esc_x, _ROW_CLEAR_Y), (esc_x, south_y)], w)
        xs.append(esc_x)
    x0, x1 = min(xs), max(xs)
    _add_track(board, ni, pcbnew.F_Cu, [(x0, south_y), (x1, south_y)], w)


def _route_p3v3_swd(board):
    """P3V3's VTref taps (J3.1/J6.1): B_Cu throughout except a short F_Cu
    stub into each SMD pad (PICO.36 is THT, no via needed to start on
    B_Cu). Descends PICO's own westmost row-gap (pins 1/2, x=3.485),
    doglegs west then back east around the board's rounded corner/MH3
    (see _P3V3_WEST_X_MM/_P3V3_DOGLEG_X_MM comment) to the
    south-of-south-row band (_SWD_LANE_Y['P3V3']), then east to J3.1/
    J6.1. Being B_Cu the whole way avoids SWCLK's F_Cu south lane (also
    x 7.5-68.57ish, would otherwise need a hop that doesn't fit the
    board-edge-constrained vertical budget down there) and SWDIO/
    NRESET's B_Cu trunks (58.80/59.42 -- P3V3's own B_Cu never reaches
    that far north in x<9.175, its own path's x range is disjoint from
    theirs). Necked to Default width (0.2mm): the nominal 0.5mm Power
    width doesn't clear the ~0.84mm PICO/J1B pin-pitch gap."""
    ni = _net(board, "P3V3")
    if _net_has_tracks(board, ni):
        return
    w = pcbnew.ToMM(
        board.GetDesignSettings().m_NetSettings.GetDefaultNetclass().GetTrackWidth()
    )
    ncls = board.GetDesignSettings().m_NetSettings.GetEffectiveNetClass("P3V3")
    via_dia = pcbnew.ToMM(ncls.GetViaDiameter())
    via_drill = pcbnew.ToMM(ncls.GetViaDrill())
    south_y = _SWD_LANE_Y["P3V3"]

    pico_ref, pico_pad, gap_a, gap_b = _P3V3_PICO_GAP
    pico_xy = _pos(_pad(board, pico_ref, pico_pad))
    gap_x = _gap_x(board, pico_ref, gap_a, gap_b)
    approach_y = _approach_above(board, pico_ref, [gap_a, gap_b])
    # The westward dogleg must happen *south* of JP2 (pad bbox bottom edge
    # 53.105 at x=2.215), not just south of J1B's row -- GP0's guard-net
    # breakout stub runs J1B(47.8)->JP2(52.255) right through x=2.215, and
    # the dogleg's horizontal jog (gap_x=3.485 -> _P3V3_WEST_X_MM) would
    # otherwise cross it (though it's B_Cu vs GP0's F_Cu now, so this is
    # belt-and-suspenders, not strictly required any more).
    jp2_bottom = _bbox(_pad(board, "JP2", "1"))[3]
    post_jp2_y = jp2_bottom + 0.3
    _add_track(board, ni, pcbnew.B_Cu, [
        pico_xy, (gap_x, approach_y), (gap_x, post_jp2_y),
        (_P3V3_WEST_X_MM, post_jp2_y), (_P3V3_WEST_X_MM, _P3V3_DOGLEG_Y_MM),
        (_P3V3_DOGLEG_X_MM, _P3V3_DOGLEG_Y_MM), (_P3V3_DOGLEG_X_MM, south_y),
    ], w)

    xs = [_P3V3_DOGLEG_X_MM]
    for ref, pad in _SWD_TREE["P3V3"]:
        x, y = _pos(_pad(board, ref, pad))
        _add_track(board, ni, pcbnew.B_Cu, [(x, south_y), (x, y)], w)
        _add_via(board, ni, (x, y), via_dia, via_drill)
        xs.append(x)
    x0, x1 = min(xs), max(xs)
    _add_track(board, ni, pcbnew.B_Cu, [(x0, south_y), (x1, south_y)], w)


def _route_swd_tree(board):
    shallower = []  # only SWDIO/NRESET use the B_Cu shallower-hop machinery
    _route_swd_tree_bcu(board, "SWDIO", shallower)
    _route_swd_tree_bcu(board, "NRESET", shallower, pico_gap=_NRESET_PICO_GAP)
    _route_swclk(board)
    _route_p3v3_swd(board)


def _route_j10_taps(board):
    """J10 (58.6/61.14/63.68,57.5): the new dupont SWD header sits in the
    J6-J7 debug-row gap. GND (pin 2) is left for the pour, matching every
    other GND pin in this tree. SWCLK/SWDIO tap straight into the
    existing trunks -- never touching their own copper, only adding a T
    off it:
      - SWCLK: F_Cu main trunk runs at y=62.65 (x=7.5-68.57, same layer
        as every other connector's own stub, e.g. J6's at x=51.13). A
        plain vertical from J10.1 up to the trunk crosses SWDIO's own
        B_Cu trunk (y=58.8) and NRESET's own B_Cu trunk (y=59.42) along
        the way -- different layer both times, so no hop is needed
        (exactly how J6/J7's own stubs already cross both for free).
      - SWDIO: B_Cu main trunk runs at y=58.8 (x=9.175-70.57). J10 is a
        THT/PTH connector (copper on both layers already), so a plain
        B_Cu drop from J10.3 straight into the trunk needs no via.
    Both columns (58.6, 63.68) are clear of NRESET's own via cluster at
    x=54.94 and of J7's pad column at 68.57 -- verified by direct
    pad/track query, no other net occupies x=58.6 or 63.68 in this Y
    band.
    """
    j10_1 = _pos(_pad(board, "J10", "1"))
    j10_3 = _pos(_pad(board, "J10", "3"))
    _add_path_once(board, _net(board, "SWCLK"), pcbnew.F_Cu,
                    [j10_1, (j10_1[0], 62.65)], _class_width(board, "SWCLK"))
    _add_path_once(board, _net(board, "SWDIO"), pcbnew.B_Cu,
                    [j10_3, (j10_3[0], 58.8)], _class_width(board, "SWDIO"))



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
# Task 14h: finish routing -- the ~65 non-GND pad-pairs task-14f left, plus
# J10 (new SWD dupont header). Builds on the now-cleared "Antenna Copper Keep
# Out" rule area (hw/build_board.py's _clear_antenna_keepout) -- the open
# rectangle between PICO's two THT rows (row1 y=40.89, row2 y=23.11) is now
# usable as a crossing corridor. See task-14h-report.md for the derivation
# (row1 pad n and row2 pad (41-n) share the same X column -- the two rows,
# plus J1B's row (y=47.8) and J2B's row (y=15.6), are all pin-aligned since
# J1B/J2B tie 1:1 to PICO -- a track jogged to the gap between two adjacent
# PICO columns clears the corresponding pad in EVERY one of those four rows
# at once).
# ============================================================================

# --- Simple local ties: both pads already close together, no PICO-row
# crossing needed. (net, ref_a, pad_a, ref_b, pad_b, bend) -- bend is "d"
# (direct 2-point), "hv" (horizontal then vertical), or "vh" (vertical then
# horizontal); layer is F_Cu throughout (all involved pads are SMD/THT F_Cu
# pads in the open areas this table covers).
_LOCAL_TIES = [
    ("LED_PWR_A", "LED_PWR", "2", "R_LED_PWR", "2", "d"),
    ("LED_USER", "LED_USER", "2", "R_LED_USER", "2", "d"),
    ("NATIVE_VBUS_DET", "R_NVD_B", "1", "R_NVD_T", "2", "d"),
    ("DEV_VBUS_DET", "R_J9VD_B", "1", "R_J9VD_T", "2", "d"),
    ("V5_JTRACE", "J3", "11", "J3", "13", "d"),
    ("NVD_TOP", "JP4", "2", "R_NVD_T", "1", "vh"),
    ("NRESET", "C_NRESET", "1", "SW1", "1", "hv"),
    # Device USB port: ESD_D feed-through ties (IO1/IO1B share DEV_DP,
    # IO2/IO2B share DEV_DM) + R_DDP/R_DDM series resistor -> ESD_D -> J9.
    # ESD_D.6->J9.3 uses vh (not hv): J9's 5 signal pads share x=86.795 --
    # an hv bend's horizontal leg lands ON that column at the *wrong* pad's
    # y first (clips J9.5/J9.4 before reaching J9.3); vh's vertical leg
    # stays on ESD_D's own column (safe) and only touches x=86.795 once,
    # already at J9.3's own y.
    # ESD_D.6->J9.3 is routed separately (_route_dev_dp_esd_j9 below) --
    # J9's own pad5 (J9_VBUS) sits directly under ESD_D.6 on the same
    # column and needs a jog-around, same treatment as the R_HDP_PD etc.
    ("DEV_DP", "ESD_D", "1", "ESD_D", "6", "d"),
    ("DEV_DP", "R_DDP", "2", "ESD_D", "1", "hv"),
    # ESD_D.4<->J9.2 are exactly level (both y=45.65) -- direct, no bend.
    ("DEV_DM", "ESD_D", "3", "ESD_D", "4", "d"),
    ("DEV_DM", "R_DDM", "2", "ESD_D", "3", "hv"),
    ("DEV_DM", "ESD_D", "4", "J9", "2", "d"),
    # Host USB port: ESD_H feed-through ties + pulldowns + probe points.
    # R_HDP_PD/R_HDM_PD's own pad1(signal)/pad2(GND) are 1mm apart on the
    # SAME x -- vh (not hv) so the final approach is horizontal at pad1's
    # own y, never sweeping vertically past pad2's y.
    ("HOST_DP", "ESD_H", "1", "ESD_H", "6", "d"),
    ("HOST_DP", "R_HDP_PD", "1", "ESD_H", "1", "vh"),
    ("HOST_DP", "TP1", "1", "R_HDP_PD", "1", "vh"),
    ("HOST_DP", "TP1", "1", "R_HDP", "2", "d"),
    ("HOST_DP", "ESD_H", "6", "J5", "3", "hv"),
    ("HOST_DM", "ESD_H", "3", "ESD_H", "4", "d"),
    ("HOST_DM", "R_HDM_PD", "1", "ESD_H", "3", "vh"),
    ("HOST_DM", "TP2", "1", "R_HDM_PD", "1", "vh"),
    ("HOST_DM", "TP2", "1", "R_HDM", "2", "d"),
    ("HOST_DM", "ESD_H", "4", "J5", "2", "hv"),
    # Host VBUS: bulk/decoupling caps + J5 (U_HSW.1 leg is B_Cu, see
    # _route_power_cluster_bcu -- it would otherwise cross the VBUS_SEL/
    # HOST_5V_IN F_Cu ladder below).
    ("HOST_VBUS", "C_HVBUS_100n", "1", "C_HVBUS_BULK", "1", "hv"),
    ("HOST_VBUS", "J5", "1", "C_HVBUS_100n", "1", "vh"),
    # J9_VBUS web (D_J9_BUSPWR DNP anode -> R_J9VD_T top leg -> J9). The
    # ESD_D.5 tap is routed separately (_route_j9_vbus_esd_tap) -- R_J9VD_T's
    # own pad1(J9_VBUS)/pad2(DEV_VBUS_DET) share x=82.6, so a naive path
    # toward ESD_D (west) sweeping through pad2's y needs the same jog-around
    # treatment as R_HDP_PD/R_HDM_PD above, done explicitly there.
    ("J9_VBUS", "D_J9_BUSPWR", "1", "R_J9VD_T", "1", "hv"),
]


def _route_local_ties(board):
    for net, ref_a, pad_a, ref_b, pad_b, bend in _LOCAL_TIES:
        ni = _net(board, net)
        w = _class_width(board, net)
        p0 = _pos(_pad(board, ref_a, pad_a))
        p1 = _pos(_pad(board, ref_b, pad_b))
        if bend == "d":
            pts = [p0, p1]
        elif bend == "hv":
            pts = _bend_hv(p0, p1)
        else:
            pts = _bend_vh(p0, p1)
        _add_path_once(board, ni, pcbnew.F_Cu, pts, w)


def _hop_x(board, ni, w, via_dia, via_drill, y, x_before, x_after):
    """B_Cu horizontal run, pausing to hop briefly onto F_Cu between
    x_before and x_after at height y -- clears a same-layer (B_Cu)
    column obstacle at that X (margin is the caller's responsibility, via
    its choice of x_before/x_after -- each obstacle's own track width
    differs). Mirrors _via_hop but for a horizontal run crossing a
    vertical obstacle, rather than a vertical run crossing a horizontal
    one (_spike_to_trunk's shape)."""
    _add_via(board, ni, (x_before, y), via_dia, via_drill)
    _add_track(board, ni, pcbnew.F_Cu, [(x_before, y), (x_after, y)], w)
    _add_via(board, ni, (x_after, y), via_dia, via_drill)


def _via_hop(board, ni, w, via_dia, via_drill, pts):
    """via at pts[0] -> B_Cu polyline through pts -> via at pts[-1]. Used
    for legs that would otherwise cross an already-F_Cu-committed net in a
    tight cluster -- B_Cu is empty in these regions, so a same-layer clash
    is only possible against another leg *also* routed this way (avoided
    by picking disjoint waypoints, see each caller). Only the two
    endpoints get vias; interior bend points stay on B_Cu throughout."""
    _add_via(board, ni, pts[0], via_dia, via_drill)
    _add_via(board, ni, pts[-1], via_dia, via_drill)
    _add_track(board, ni, pcbnew.B_Cu, pts, w)


def _via_stub(board, ni, w, via_dia, via_drill, via_xy, pad_xy):
    """via at `via_xy` (offset, clear of any tight-pitch neighbor pad) +
    a short F_Cu stub over to the actual pad at `pad_xy`. Used instead of
    placing the via directly on a pad when that pad's immediate neighbors
    (<1.2mm away, e.g. U_INA219_ALT's 0.65mm-pitch SOT-23-8 pins) would
    otherwise fail hole-to-hole/pad clearance against the via."""
    _add_via(board, ni, via_xy, via_dia, via_drill)
    _add_track(board, ni, pcbnew.F_Cu, [via_xy, pad_xy], w)


def _route_power_cluster_bcu(board):
    """P3V3 (U_ISNS.5<->U_INA219_ALT.4) and HOST_VBUS's U_HSW.1 leg: both
    would cross the VBUS_SEL/HOST_5V_IN F_Cu ladder around R_SHUNT/U_ISNS/
    U_INA219_ALT (INA219's own VBUS_SEL/HOST_5V_IN/GND/P3V3 pads share
    x=62.638 at 0.65mm pitch -- any F_Cu path threading between them has no
    room). Routed on B_Cu instead (empty here, so no clearance fight with
    the F_Cu ladder -- different layers never need mutual clearance).
    P3V3's INA219.4 via sits 1.2mm north of the pad (still clear of any
    neighbor -- pad4 is INA219's northmost 1-4 pin) with an F_Cu stub back
    down; U_ISNS.5's via and HOST_VBUS's U_HSW.1/C_HVBUS_100n.1 vias all
    have >=1.2mm to their nearest same-footprint neighbor, so they go
    straight on the pad (matching _route_swd_tree_bcu's convention).
    P3V3's vertical leg is offset to x=68.5 (east of U_ISNS/U_HSW's own
    courtyards and of HOST_5V_IN's spine at x=67.3, see
    _route_vbus_sel_5v_ladder) -- it still crosses HOST_VBUS's own B_Cu
    U_HSW.1->C_HVBUS_100n.1 leg (y=28.72, spanning x=63.362-70.0, an
    unavoidable span since it bridges those two pads) at (68.5,28.72), so
    it hops briefly to F_Cu there (empty at that point) and back, exactly
    like _spike_to_trunk's shallower-trunk hop."""
    ni = _net(board, "P3V3")
    ncls = board.GetDesignSettings().m_NetSettings.GetEffectiveNetClass("P3V3")
    w = pcbnew.ToMM(ncls.GetTrackWidth())
    w_default = pcbnew.ToMM(
        board.GetDesignSettings().m_NetSettings.GetDefaultNetclass().GetTrackWidth()
    )
    via_dia = pcbnew.ToMM(ncls.GetViaDiameter())
    via_drill = pcbnew.ToMM(ncls.GetViaDrill())
    p_ina = _pos(_pad(board, "U_INA219_ALT", "4"))
    p_isns = _pos(_pad(board, "U_ISNS", "5"))
    via_ina = (p_ina[0], p_ina[1] - 1.2)
    hop_x = 68.5
    if not _track_exists(board, ni.GetNetCode(), pcbnew.B_Cu, _mm(*via_ina), _mm(hop_x, via_ina[1])):
        # Default width for the short stub into pad4 (Power's 0.5mm round
        # end-cap would otherwise reach into pad3/GND, 0.65mm away).
        _via_stub(board, ni, w_default, via_dia, via_drill, via_ina, p_ina)
        _add_via(board, ni, p_isns, via_dia, via_drill)
        # hop span 0.85mm (not 0.65): a Power-class via (0.3mm radius) needs
        # >=0.6mm clearance from HOST_VBUS's own Power-width (0.25mm
        # halfwidth) centerline -- 0.65mm left only 0.05mm margin (measured
        # short), 0.85mm clears with room.
        hop_lo, hop_hi = 28.72 - 0.85, 28.72 + 0.85
        _add_track(board, ni, pcbnew.B_Cu, [via_ina, (hop_x, via_ina[1]), (hop_x, hop_lo)], w)
        _add_via(board, ni, (hop_x, hop_lo), via_dia, via_drill)
        _add_track(board, ni, pcbnew.F_Cu, [(hop_x, hop_lo), (hop_x, hop_hi)], w)
        _add_via(board, ni, (hop_x, hop_hi), via_dia, via_drill)
        _add_track(board, ni, pcbnew.B_Cu, [(hop_x, hop_hi), (hop_x, p_isns[1]), p_isns], w)

    ni2 = _net(board, "HOST_VBUS")
    ncls2 = board.GetDesignSettings().m_NetSettings.GetEffectiveNetClass("HOST_VBUS")
    w2 = pcbnew.ToMM(ncls2.GetTrackWidth())
    via_dia2 = pcbnew.ToMM(ncls2.GetViaDiameter())
    via_drill2 = pcbnew.ToMM(ncls2.GetViaDrill())
    p_hsw = _pos(_pad(board, "U_HSW", "1"))
    p_cap = _pos(_pad(board, "C_HVBUS_100n", "1"))
    # Vertical leg offset to x=64.5 (not p_hsw's own 63.362): U_ISNS.1
    # (ISENSE's destination, 63.462,33.65 -- routed separately, below)
    # sits only 0.1mm from 63.362, too close for mutual via/track
    # clearance; 64.5 clears U_ISNS's own pad columns (63.462/65.737) by
    # >=1.0mm on both sides.
    hop_col = 64.5
    if not _track_exists(board, ni2.GetNetCode(), pcbnew.B_Cu, _mm(*p_hsw), _mm(hop_col, p_hsw[1])):
        _via_hop(board, ni2, w2, via_dia2, via_drill2,
                 [p_hsw, (hop_col, p_hsw[1]), (hop_col, p_cap[1]), p_cap])


def _route_i2c0_stemma_bcu(board):
    """I2C0_SCL/SDA: U_INA219_ALT (power cluster, y~27) -> J_STEMMA (top
    strip, y~5.9) would cross NVD_TOP's F_Cu run plus the HOST_VBUS_EN/
    GP20/GP21 PICO-breakout stubs on the way north. B_Cu (empty across
    this whole span). INA219 pins 5/6 (SCL/SDA) are only 0.65mm apart and
    pin7 (GND) is a further 0.65mm beyond SDA -- vias land offset (west of
    SCL, further west of SDA) with F_Cu stubs back to the actual pads,
    exactly like P3V3's INA219.4 tap above. Three parallel nets converge
    on J_STEMMA's y=5.9 pad row here (this pair plus P3V3's own
    INA219.4->J_STEMMA.2 leg, _route_cluster_leftovers): SCL (col 56.0),
    SDA (col 57.0), P3V3-stemma (col 58.0, _route_cluster_leftovers) --
    all clear of J_UART's THT pad1 (59.26, B_Cu copper too) and R_NVD_B's
    courtyard (right edge 55.015). Dest columns keep the same west-to-east
    order (SCL 46.6 < SDA 47.6 < P3V3 48.6) as the source columns, so each
    net's horizontal sweep toward J_STEMMA only ever passes *over* a
    net-to-its-east's target column, never its own or one further west.
    Whichever net's horizontal crosses another's target column must peel
    off at a y strictly outside that other net's own [5.9, peel_y] span --
    SCL crosses both SDA's and P3V3's targets so it peels deepest (7.0);
    SDA crosses only P3V3's so it peels next (6.5); P3V3 crosses neither
    so it peels shallowest (6.1, _route_cluster_leftovers)."""
    ncls = board.GetDesignSettings().m_NetSettings.GetEffectiveNetClass("I2C0_SCL")
    w = pcbnew.ToMM(ncls.GetTrackWidth())
    via_dia = pcbnew.ToMM(ncls.GetViaDiameter())
    via_drill = pcbnew.ToMM(ncls.GetViaDrill())

    p_scl = _pos(_pad(board, "U_INA219_ALT", "5"))
    p_sda = _pos(_pad(board, "U_INA219_ALT", "6"))
    st_scl = _pos(_pad(board, "J_STEMMA", "4"))
    st_sda = _pos(_pad(board, "J_STEMMA", "3"))

    ni_scl = _net(board, "I2C0_SCL")
    via_scl = (56.0, p_scl[1])
    if not _track_exists(board, ni_scl.GetNetCode(), pcbnew.B_Cu, _mm(*via_scl), _mm(56.0, 7.0)):
        _via_stub(board, ni_scl, w, via_dia, via_drill, via_scl, p_scl)
        _add_via(board, ni_scl, st_scl, via_dia, via_drill)
        _add_track(board, ni_scl, pcbnew.B_Cu, [via_scl, (56.0, 7.0), (st_scl[0], 7.0), st_scl], w)

    ni_sda = _net(board, "I2C0_SDA")
    via_sda = (57.0, p_sda[1])
    if not _track_exists(board, ni_sda.GetNetCode(), pcbnew.B_Cu, _mm(*via_sda), _mm(57.0, 6.5)):
        _via_stub(board, ni_sda, w, via_dia, via_drill, via_sda, p_sda)
        _add_via(board, ni_sda, st_sda, via_dia, via_drill)
        _add_track(board, ni_sda, pcbnew.B_Cu, [via_sda, (57.0, 6.5), (st_sda[0], 6.5), st_sda], w)


def _route_pico_no_jog(board):
    """PICO-direct nets whose destination sits on the *same side* of the
    row they break out from (never needs to cross the opposite row's own
    pad-Y) -- see task-14h-report.md's "no opposite-row jog" list.

    Two hazards recur through this whole function and drive the F_Cu/
    B_Cu choice per net:
      - Every PICO row's own breakout stub to J1B/J2B is a short F_Cu
        vertical sitting AT that row's own column, spanning row-Y to
        J1B/J2B-row-Y (row1: y 40.89-47.8; row2: y 15.6-23.11). Any F_Cu
        horizontal crossing that Y band hits every non-GND stub column it
        passes -- so a long F_Cu horizontal through that band is a
        non-starter (found the hard way: GP20/DEV_DP_PU_EN first tried on
        F_Cu and it collided with 3-4 sibling breakout stubs each).
      - I2C0_SCL/SDA (this function) and P3V3-stemma
        (_route_cluster_leftovers) are B_Cu with long vertical columns at
        x=56.0/57.0/43.0 spanning roughly y=6-27 -- any OTHER B_Cu run
        crossing through that Y band at one of those X values needs a
        brief F_Cu hop over it (_hop_col below), the horizontal-crossing
        mirror of _spike_to_trunk/_via_hop's vertical-crossing hops.
    """
    w_default = pcbnew.ToMM(
        board.GetDesignSettings().m_NetSettings.GetDefaultNetclass().GetTrackWidth()
    )

    # B_Cu column obstacles GP20/GP21 (below) must hop over (via the
    # module-level _hop_x, also used directly by _route_i2c0_stemma_bcu/
    # _route_cluster_leftovers for their own mutual crossings): P3V3-stemma
    # at 41.585 (isolated) and I2C0_SCL/SDA at 56.0/57.0 (only 1mm apart,
    # closer than two independent 0.7mm-margin hops would clear -- pre-
    # merged into one combined span, same fix as the SWD tree's own
    # SWDIO+NRESET double-hop). Each tuple is (lo, hi) of the hop's F_Cu
    # excursion, already inclusive of margin.
    # P3V3-stemma's column (41.585) sits exactly centered between two
    # PICO/J2B breakout-stub columns (GP19 40.315, GP18 42.855, both
    # F_Cu+B_Cu occupied their whole height) -- only 1.27mm each side, so
    # the hop margin can't be the generic 0.7mm (measured too close to
    # GP18/GP19's own stubs, DRC-confirmed); using the exact midpoints
    # (40.95, 42.22) instead splits the 1.27mm gap evenly, clearing both
    # P3V3's own line and the neighboring stub by 0.635mm each --enough
    # for the required via-radius(0.3)+halfwidth(0.1)+clearance(0.2)=0.6mm
    # floor, with slim (0.035mm) margin.
    _OBSTACLE_SPANS = [(40.95, 42.22), (56.0 - 0.7, 57.0 + 0.7)]

    def hop_horizontal(ni, via_dia, via_drill, pts_before, y, x_end, dest):
        """pts_before already ends at (x, y) for some x -- continues
        horizontally to x_end, hopping over any _OBSTACLE_SPANS the
        crossing touches, then into dest (a via there)."""
        x_start = pts_before[-1][0]
        lo, hi = min(x_start, x_end), max(x_start, x_end)
        spans = sorted((s for s in _OBSTACLE_SPANS if lo < s[0] and s[1] < hi),
                        reverse=(x_end < x_start))
        pts = list(pts_before)
        for span in spans:
            before, after = span if x_end > x_start else (span[1], span[0])
            _add_track(board, ni, pcbnew.B_Cu, pts + [(before, y)], w_default)
            _hop_x(board, ni, w_default, via_dia, via_drill, y, before, after)
            pts = [(after, y)]
        _add_track(board, ni, pcbnew.B_Cu, pts + [(x_end, y), dest], w_default)
        _add_via(board, ni, dest, via_dia, via_drill)

    def route_hopping(net_name, src_xy, y, x_end, dest_ref, dest_pad):
        """B_Cu from src_xy (a THT PICO pad -- no via needed there) down/
        up to height y, then hop_horizontal to x_end/dest_ref.dest_pad."""
        ni = _net(board, net_name)
        ncls = board.GetDesignSettings().m_NetSettings.GetEffectiveNetClass(net_name)
        via_dia = pcbnew.ToMM(ncls.GetViaDiameter())
        via_drill = pcbnew.ToMM(ncls.GetViaDrill())
        dest = _pos(_pad(board, dest_ref, dest_pad))
        if _track_exists(board, ni.GetNetCode(), pcbnew.B_Cu, _mm(*src_xy), _mm(src_xy[0], y)):
            return
        hop_horizontal(ni, via_dia, via_drill, [src_xy, (src_xy[0], y)], y, x_end, dest)

    # I2C0_SDA: PICO.11 -> the *existing* offset via _route_i2c0_stemma_bcu
    # already placed at (57.0,27.975) (that function's own via_sda, which
    # already has an F_Cu stub to U_INA219_ALT.6 -- reusing it, rather
    # than adding a second via directly on that pad, avoids a second via
    # within 0.65mm of INA219's own GND/SCL neighbor pads). Peels off at
    # y=26.0, but its horizontal still crosses I2C0_SCL's own long B_Cu
    # column at x=56.0 (west of this net's own target 57.0) -- hopped
    # (margin only needs to clear x=56.0, not also 57.0, since 57.0 is
    # this net's own destination, same-net copper needs no clearance).
    w_i2c = _class_width(board, "I2C0_SDA")
    ni_sda = _net(board, "I2C0_SDA")
    ncls_sda = board.GetDesignSettings().m_NetSettings.GetEffectiveNetClass("I2C0_SDA")
    via_dia_sda = pcbnew.ToMM(ncls_sda.GetViaDiameter())
    via_drill_sda = pcbnew.ToMM(ncls_sda.GetViaDrill())
    pico11 = _pos(_pad(board, "PICO", "11"))
    if not _track_exists(board, ni_sda.GetNetCode(), pcbnew.B_Cu, _mm(*pico11), _mm(pico11[0], 26.0)):
        _add_track(board, ni_sda, pcbnew.B_Cu, [pico11, (pico11[0], 26.0), (55.3, 26.0)], w_i2c)
        _hop_x(board, ni_sda, w_i2c, via_dia_sda, via_drill_sda, 26.0, 55.3, 56.7)
        _add_track(board, ni_sda, pcbnew.B_Cu, [(56.7, 26.0), (57.0, 26.0), (57.0, 27.975)], w_i2c)

    # I2C0_SCL: PICO.12 -> _route_i2c0_stemma_bcu's existing via_scl at
    # (56.0,27.325). Source column (30.155) is east of I2C0_SDA's
    # (27.615), so it never needs to cross SDA's column at all -- can
    # peel off deeper (26.6) without conflict.
    ni_scl = _net(board, "I2C0_SCL")
    pico12 = _pos(_pad(board, "PICO", "12"))
    _add_path_once(board, ni_scl, pcbnew.B_Cu,
                    [pico12, (pico12[0], 26.6), (56.0, 26.6), (56.0, 27.325)], w_i2c)

    # ISENSE: PICO.31 -> U_ISNS.1. B_Cu, own column 58.8 (west of
    # R_SHUNT's courtyard 62.275, clear). Its horizontal (y=25.0) sweeps
    # past x=56.0/57.0 -- I2C0_SCL/SDA's own long B_Cu columns (see
    # _route_i2c0_stemma_bcu, spanning roughly y=6-27) -- so it needs the
    # same combined hop those two hop over each other with. Two more
    # hazards:
    #   - The SWD tree's own NRESET pico_gap descent is a *diagonal*
    #     B_Cu run from PICO.30 (27.615,23.11) to (23.805,39.79) (see
    #     _route_swd_tree's NRESET leg) -- it crosses y=25.0 at
    #     x~=27.183, squarely inside this net's horizontal sweep (starts
    #     at 25.075). Hopped via a brief F_Cu excursion (26.5-27.9,
    #     comfortably either side of the crossing -- the diagonal's steep
    #     slope there means real clearance is much more than the margin
    #     alone suggests).
    #   - VBUS_SEL's own isns3 leg has an F_Cu vertical at x=62.0 (see
    #     _route_vbus_sel_5v_ladder) between R_SHUNT and U_ISNS.3 -- an
    #     F_Cu final stub from 58.8 straight into U_ISNS.1 (63.462) would
    #     cross it, so the B_Cu run continues past it (to x=63.0) before
    #     transitioning, leaving only a short (0.4625mm) F_Cu stub that
    #     never reaches back to x=62.0.
    pico31 = _pos(_pad(board, "PICO", "31"))
    isns1 = _pos(_pad(board, "U_ISNS", "1"))
    ni_isns = _net(board, "ISENSE")
    ncls_isns = board.GetDesignSettings().m_NetSettings.GetEffectiveNetClass("ISENSE")
    via_dia_d = pcbnew.ToMM(ncls_isns.GetViaDiameter())
    via_drill_d = pcbnew.ToMM(ncls_isns.GetViaDrill())
    if not _track_exists(board, ni_isns.GetNetCode(), pcbnew.B_Cu, _mm(*pico31), _mm(pico31[0], 25.0)):
        _add_track(board, ni_isns, pcbnew.B_Cu,
                   [pico31, (pico31[0], 25.0), (26.5, 25.0)], w_default)
        _hop_x(board, ni_isns, w_default, via_dia_d, via_drill_d, 25.0, 26.5, 27.9)
        _add_track(board, ni_isns, pcbnew.B_Cu, [(27.9, 25.0), (55.3, 25.0)], w_default)
        _hop_x(board, ni_isns, w_default, via_dia_d, via_drill_d, 25.0, 55.3, 57.7)
        _add_track(board, ni_isns, pcbnew.B_Cu,
                   [(57.7, 25.0), (58.8, 25.0), (58.8, isns1[1]), (63.0, isns1[1])], w_default)
        _add_via(board, ni_isns, (63.0, isns1[1]), via_dia_d, via_drill_d)
        _add_track(board, ni_isns, pcbnew.F_Cu, [(63.0, isns1[1]), isns1], w_default)

    # HOST_VBUS_FLT: PICO.20 -> U_HSW.3 directly (target y=39.15, south of
    # J1B's own breakout-stub band (40.89-47.8) -- wait, it's actually
    # BETWEEN PICO row1 (40.89) and that band's own start, i.e. north of
    # it -- and south of the I2C0/P3V3 B_Cu columns' span (they stop
    # around y=27) -- clear of both hazards, F_Cu is fine here.
    pico20 = _pos(_pad(board, "PICO", "20"))
    hsw3 = _pos(_pad(board, "U_HSW", "3"))
    _add_path_once(board, _net(board, "HOST_VBUS_FLT"), pcbnew.F_Cu,
                    [pico20, (pico20[0], hsw3[1]), hsw3],
                    _class_width(board, "HOST_VBUS_FLT"))

    # GP20: PICO.26 -> R_HDP.1. B_Cu (target y=19.0 sits inside the
    # row2-breakout-stub band 15.6-23.11 -- an F_Cu horizontal there hits
    # every sibling stub column it crosses, confirmed by DRC), hopping
    # I2C0_SCL/SDA/P3V3-stemma's columns on the way east.
    pico26 = _pos(_pad(board, "PICO", "26"))
    route_hopping("GP20", pico26, 19.0, 58.59, "R_HDP", "1")

    # GP21: PICO.27 -> R_HDM.1. Same B_Cu treatment at its own constant
    # y=21.0 -- GP20 stays at a *different* constant y (19.0) so the two
    # never cross on their own horizontals (R_HDP.1/R_HDM.1 sharing
    # x=58.59 doesn't matter either, for the same reason). BUT: GP20's
    # own PICO-to-y=19.0 descent (a vertical at x=37.775, spanning
    # y=19.0-23.11, plus its F_Cu breakout stub covering y=15.6-23.11 at
    # that same column) blocks GP21's horizontal from simply sweeping
    # past x=37.775 at y=21.0 -- on EITHER layer, since both F_Cu and
    # B_Cu are occupied there for that whole Y span (an F_Cu hop lands
    # right inside the F_Cu stub, DRC-confirmed -- swapping layers alone
    # doesn't help when BOTH are already occupied). Descends straight to
    # y=24.58 instead -- south of GP20's whole column presence (pad26's
    # own bbox bottom is 23.91) AND north of ISENSE's own horizontal run
    # (y=25.0) by just enough (0.42mm) to clear it as a plain track, and
    # south of the ROW2_HOP vias' own floor (23.96) by just enough
    # (0.62mm) to clear THEM too -- a genuinely tight [24.56,24.6] window
    # but wide enough for a plain track (no hop needed for pad26/GP20 at
    # all this way, since we start south of them from the outset). Stays
    # at y=24.58 only through x=49.205 (PICO's own pad21/22 gap -- 1.27mm
    # clear of both regardless of Y, unlike x=48.0 tried first, which sat
    # only 0.065mm off pad22's own column and put the connecting bend
    # only 0.89mm from it, short of the 1.1mm THT floor, DRC-confirmed)
    # -- past UART0_RX/BTN_USER's own ROW2_HOP vias (44.125/46.665) --
    # then dips to y=24.3 for the I2C0_SCL/SDA hop (56.0/57.0)
    # specifically, since 0.42mm was NOT enough separation from ISENSE's
    # OWN hop-vias over those same two columns (55.3/57.7,y=25.0): the
    # F_Cu bridge's own straight-line proximity to each (a perpendicular,
    # not diagonal, distance) came up only 0.02mm short, DRC-confirmed.
    # 24.3 clears pad21/NATIVE_VBUS_DET (50.475, needs >=1.1mm -- 24.3
    # gives 1.19mm) and ISENSE's vias (25.0, needs >=0.6mm -- 24.3 gives
    # 0.7mm); there's no ROW2_HOP-style floor constraint out at x=49-58
    # to conflict with either. NOT via the shared hop_horizontal helper
    # -- its (40.95,42.22) obstacle span assumes GP18/GP19 have no F_Cu
    # presence yet, true at y=19/21 but not here (GP18's own descent,
    # 23.11-40.29 at x=41.585, is already running by y=24.58) -- so this
    # hops ONLY the I2C0_SCL/SDA span. Final approach into R_HDM.1 from
    # the west at its own y=21.0 (the vertical drop there, 24.3->21.0,
    # stays well north of ISENSE's own run out to U_ISNS, x=58.8,
    # y=25.0-33.65 -- no Y overlap at all).
    pico27 = _pos(_pad(board, "PICO", "27"))
    ni_gp21 = _net(board, "GP21")
    ncls_gp21 = board.GetDesignSettings().m_NetSettings.GetEffectiveNetClass("GP21")
    via_dia_gp21 = pcbnew.ToMM(ncls_gp21.GetViaDiameter())
    via_drill_gp21 = pcbnew.ToMM(ncls_gp21.GetViaDrill())
    if not _track_exists(board, ni_gp21.GetNetCode(), pcbnew.B_Cu, _mm(*pico27), _mm(pico27[0], 24.58)):
        hdm1 = _pos(_pad(board, "R_HDM", "1"))
        _add_track(board, ni_gp21, pcbnew.B_Cu,
                   [pico27, (pico27[0], 24.58), (49.205, 24.58), (49.205, 24.3), (54.5, 24.3)], w_default)
        _add_via(board, ni_gp21, (54.5, 24.3), via_dia_gp21, via_drill_gp21)
        _add_track(board, ni_gp21, pcbnew.F_Cu, [(54.5, 24.3), (58.5, 24.3)], w_default)
        _add_via(board, ni_gp21, (58.5, 24.3), via_dia_gp21, via_drill_gp21)
        _add_track(board, ni_gp21, pcbnew.B_Cu,
                   [(58.5, 24.3), (58.59, 24.3), (58.59, 21.0)], w_default)
        _add_via(board, ni_gp21, (58.59, 21.0), via_dia_gp21, via_drill_gp21)

    # NATIVE_VBUS_DET: PICO.21 -> R_NVD_B.1 (not R_NVD_T.2 -- that pad's
    # own x, 52.9, sits under NVD_TOP's existing F_Cu run, y=9.51,
    # x=22.27-52.9). R_NVD_B's own pad1(NATIVE_VBUS_DET,y=8.49)/pad2
    # (GND,y=9.51) share x=54.5. Column x=50.475 (own PICO/J2B pin, both
    # J2B.1 and PICO.21 -- same net, free to touch) the whole way down:
    # F_Cu for y=17.0-23.11, transitioning to B_Cu at y=17.0 specifically
    # -- south of GP20/GP21's own B_Cu sweep (19.0/21.0 -- different
    # layer there anyway, so only their OWN Y matters if a via lands
    # nearby, and 17.0 is 2mm clear of both) and north of J2B.1's own
    # hole (15.6mm -- board's min hole-to-hole is 0.2495mm, needing
    # roughly 0.95mm center-to-center given the hole sizes involved; a
    # transition first tried at y=15.0 was only 0.6mm from that hole,
    # DRC-confirmed too close, and y=13.5 lands squarely on UART0_TX's
    # own new horizontal at that exact Y -- 17.0 clears the hole (1.4mm)
    # AND is well clear of P3V3's own B_Cu jog at y=18.0, x=41.585-55.3,
    # which also crosses this column (1.0mm away). Then B_Cu for
    # y=8.49-17.0 (clear of NVD_TOP's F_Cu run at y=9.51, which ALSO
    # spans this X -- different layer again). This column choice
    # (not the previous 57.3, east past LED_USER/J_UART) matters a lot
    # more than it looks: 57.3 sits in the same ~2mm pocket as I2C0_SCL/
    # SDA (56.0/57.0, B_Cu) AND LED_USER (56.3, F_Cu) AND J_UART.1 --
    # four obstacles within 3mm of each other with no room left for a
    # THIRD net (UART0_TX/UART0_RX/BTN_USER) to hop through on either
    # layer (confirmed by DRC: any hop margin wide enough to clear one
    # obstacle lands inside another). Staying on PICO's own column
    # sidesteps that whole pocket -- UART0_TX/UART0_RX/BTN_USER now cross
    # this net for free (their F_Cu vs its B_Cu, no hop needed at all,
    # see _route_pico_row_jog). Final horizontal at y=8.49 (pad1's own Y)
    # runs through R_NVD_T.2 (52.9,8.49) -- same net, fine to touch --
    # into a via-stub short of R_NVD_B.1 itself (pad2/GND is 1.02mm away
    # at 54.5,9.51, tight enough to prefer the offset-via pattern over a
    # via directly on the pad).
    pico21 = _pos(_pad(board, "PICO", "21"))
    nvdb1 = _pos(_pad(board, "R_NVD_B", "1"))
    ni_nvd = _net(board, "NATIVE_VBUS_DET")
    if not _track_exists(board, ni_nvd.GetNetCode(), pcbnew.F_Cu, _mm(*pico21), _mm(pico21[0], 17.0)):
        ncls_nvd = board.GetDesignSettings().m_NetSettings.GetEffectiveNetClass("NATIVE_VBUS_DET")
        via_dia_nvd = pcbnew.ToMM(ncls_nvd.GetViaDiameter())
        via_drill_nvd = pcbnew.ToMM(ncls_nvd.GetViaDrill())
        _add_track(board, ni_nvd, pcbnew.F_Cu, [pico21, (pico21[0], 17.0)], w_default)
        _add_via(board, ni_nvd, (pico21[0], 17.0), via_dia_nvd, via_drill_nvd)
        _add_track(board, ni_nvd, pcbnew.B_Cu,
                   [(pico21[0], 17.0), (pico21[0], nvdb1[1]), (54.0, nvdb1[1])], w_default)
        _add_via(board, ni_nvd, (54.0, nvdb1[1]), via_dia_nvd, via_drill_nvd)
        _add_track(board, ni_nvd, pcbnew.F_Cu, [(54.0, nvdb1[1]), nvdb1], w_default)

    # VBUS_NET: PICO.40 -> JP1.3. JP1.1/JP1.2/JP1.3 share y=10.655 -- peel
    # off north of the whole row (y=8.0, above JP1's own courtyard top
    # 8.84) before a final drop into pad3 at its own column.
    pico40 = _pos(_pad(board, "PICO", "40"))
    jp1_3 = _pos(_pad(board, "JP1", "3"))
    ni = _net(board, "VBUS_NET")
    if not _track_exists(board, ni.GetNetCode(), pcbnew.B_Cu, _mm(*pico40), _mm(pico40[0], 8.0)):
        _add_track(board, ni, pcbnew.B_Cu,
                   [pico40, (pico40[0], 8.0), (jp1_3[0], 8.0), jp1_3], w_default)
        # JP1 is THT -- lands directly on the pad, no via needed.

    # DEV_DP_PU_EN: PICO.15 -> R_DPU.2. B_Cu, straight at y=45.91 (R_DPU.2's
    # OWN Y) the whole way -- south of row1 (40.89) and past its own
    # breakout-stub band (40.89-47.8)? No -- 45.91 IS inside that band, so
    # this crosses J1B stub columns on F_Cu too (BTN_USER/UART0_TX/
    # UART0_RX/HOST_VBUS_FLT, confirmed by DRC) -- B_Cu is empty there.
    # Previously jogged through y=44.0 first then up to 45.91 at x=60.0,
    # but that intermediate vertical (60.0, 44.0->45.91) squatted on the
    # only Y-room GP18/GP19's own south-bound sweeps needed in this same
    # corridor -- going straight to 45.91 from the start needs no jog at
    # all (clear of PICO pad15/row1 by Y-distance alone, and doesn't
    # cross R_DPU.1/DEV_DP at 44.89, 1.02mm north) and frees that room.
    pico15 = _pos(_pad(board, "PICO", "15"))
    rdpu2 = _pos(_pad(board, "R_DPU", "2"))
    ni_dpu = _net(board, "DEV_DP_PU_EN")
    if not _track_exists(board, ni_dpu.GetNetCode(), pcbnew.B_Cu, _mm(*pico15), _mm(pico15[0], rdpu2[1])):
        _add_track(board, ni_dpu, pcbnew.B_Cu,
                   [pico15, (pico15[0], rdpu2[1]), (60.0, rdpu2[1])], w_default)
        _add_via(board, ni_dpu, (60.0, rdpu2[1]), via_dia_d, via_drill_d)
        _add_track(board, ni_dpu, pcbnew.F_Cu, [(60.0, rdpu2[1]), rdpu2], w_default)

    # R_HVEN_PD.1 <-> U_HSW.4 (HOST_VBUS_EN): local, F_Cu -- nearly
    # identical X (65.64 vs 65.638), short straight run across the
    # narrow gap between their courtyards.
    ni = _net(board, "HOST_VBUS_EN")
    w = _class_width(board, "HOST_VBUS_EN")
    rhven1 = _pos(_pad(board, "R_HVEN_PD", "1"))
    hsw4 = _pos(_pad(board, "U_HSW", "4"))
    _add_path_once(board, ni, pcbnew.F_Cu, [rhven1, hsw4], w)


def _route_pico_row_jog(board):
    """PICO-direct nets whose destination is on the OPPOSITE side of the
    row they break out from -- must cross the other row's own pad-Y (see
    task-14h-report.md's "needs opposite-row jog" list).

    F_Cu almost throughout -- NOT the all-B_Cu design tried first: two
    nets sharing a PICO column (e.g. GP18/row2 and UART0_RX/row1 both
    live at x=42.855, since row1 pad n and row2 pad 41-n share an X) but
    crossing in *opposite* directions inevitably overlap somewhere in the
    middle of the board on a single shared layer, no matter how the
    per-net "jog immediately" timing is tuned -- confirmed by DRC after
    the first attempt. Instead: F_Cu for the whole run, with only a brief
    B_Cu hop exactly across each blocking row's own pad band (PICO row1/
    row2 AND, if the target is beyond it, J1B/J2B's mirrored row) --
    since gap_x is always 1.27mm off the row's own pad center in X, the
    via only needs ~0.46mm Y-separation from that pad's own Y to clear it
    (1.27^2+dy^2 >= (0.85 pad r + 0.3 via r + 0.2 clearance)^2), so each
    hop is a short, tightly-targeted excursion, not a long one.
    """
    w_default = pcbnew.ToMM(
        board.GetDesignSettings().m_NetSettings.GetDefaultNetclass().GetTrackWidth()
    )
    ROW1_HOP = (40.89 - 0.6, 40.89 + 0.6)
    # ROW2_HOP uses +-0.85mm, NOT the usual +-0.6 -- its via sits short
    # of the needed clearance from row2's own neighboring GND pads
    # (verified via direct polygon-distance query: GND's PTH pad here is
    # NOT the plain 1.6mm circle other row2 pads use -- it's a "D" shape,
    # circular on top but flattened into a rectangle down its near side,
    # so the effective boundary near a gap-jog via is CLOSER than a
    # circle's radius would suggest and barely responds to extra Y
    # margin until fully past the flat edge, y=23.91 -- +-0.6/0.65/0.7
    # each fell short by 0.03/0.017/0.0126mm; +-0.85 (y=23.96) clears
    # with a real margin, 0.0185mm past the 0.2mm floor).
    ROW2_HOP = (23.11 - 0.85, 23.11 + 0.85)
    J2B_HOP = (15.6 - 0.6, 15.6 + 0.6)

    def cross(net_name, pico_pad, gap_a, gap_b, hops, waypoints, dest_ref, dest_pad,
              x_hops=()):
        """PICO.pico_pad -> F_Cu jog to (gap_x, pico_y) -> hop (B_Cu) over
        each (lo,hi) in hops -> waypoints (waypoints[0]'s x MUST be
        gap_x) -> ... -> dest. The whole run is F_Cu except the brief
        hops, and dest is F_Cu-native (SMD or THT) either way, so no via
        is ever needed at dest -- landing an F_Cu track directly on an
        F_Cu pad connects with no transition. x_hops: optional list of
        column X values (this net's OWN F_Cu column obstacles, e.g.
        another Group-2 net's post-hop vertical) to hop over -- via B_Cu
        briefly -- during the FINAL leg from waypoints[-1] to dest."""
        ni = _net(board, net_name)
        ncls = board.GetDesignSettings().m_NetSettings.GetEffectiveNetClass(net_name)
        via_dia = pcbnew.ToMM(ncls.GetViaDiameter())
        via_drill = pcbnew.ToMM(ncls.GetViaDrill())
        src = _pos(_pad(board, "PICO", pico_pad))
        gap_x = _gap_x(board, "PICO", gap_a, gap_b)
        dest = _pos(_pad(board, dest_ref, dest_pad))
        if _track_exists(board, ni.GetNetCode(), pcbnew.F_Cu, _mm(*src), _mm(gap_x, src[1])):
            return
        assert abs(waypoints[0][0] - gap_x) < 1e-6, f"{net_name}: waypoints[0].x must equal gap_x"
        target_y = waypoints[0][1]
        going_north = target_y < src[1]  # y decreases northward
        ordered = sorted(hops, reverse=going_north)
        _add_track(board, ni, pcbnew.F_Cu, [src, (gap_x, src[1])], w_default)
        cur_y = src[1]
        for lo, hi in ordered:
            y_before, y_after = (hi, lo) if going_north else (lo, hi)
            _add_track(board, ni, pcbnew.F_Cu, [(gap_x, cur_y), (gap_x, y_before)], w_default)
            _add_via(board, ni, (gap_x, y_before), via_dia, via_drill)
            _add_track(board, ni, pcbnew.B_Cu, [(gap_x, y_before), (gap_x, y_after)], w_default)
            _add_via(board, ni, (gap_x, y_after), via_dia, via_drill)
            cur_y = y_after
        pts = [(gap_x, cur_y), (gap_x, target_y)] + list(waypoints[1:])
        _add_track(board, ni, pcbnew.F_Cu, pts, w_default)
        final_y = pts[-1][1]
        final_x = pts[-1][0]
        cur_x = final_x
        for hx in sorted(x_hops, reverse=(dest[0] < final_x)):
            before, after = (hx + 0.7, hx - 0.7) if dest[0] < final_x else (hx - 0.7, hx + 0.7)
            _add_track(board, ni, pcbnew.F_Cu, [(cur_x, final_y), (before, final_y)], w_default)
            _add_via(board, ni, (before, final_y), via_dia, via_drill)
            _add_track(board, ni, pcbnew.B_Cu, [(before, final_y), (after, final_y)], w_default)
            _add_via(board, ni, (after, final_y), via_dia, via_drill)
            cur_x = after
        _add_track(board, ni, pcbnew.F_Cu, [(cur_x, final_y), dest], w_default)

    # --- South-bound (row2 -> south of row1) ---------------------------
    # GP18/GP19 both target R_DDP.1/R_DDM.1 (68.49,43.75/45.65), east of
    # EVERY J1B column (they stop at 50.475) -- an F_Cu horizontal at any
    # Y in the row1/J1B stub band (40.89-47.8) hits every column stub it
    # crosses (same issue DEV_VBUS_DET hit), so like that net, these
    # sweep east on B_Cu instead once past their own ROW1 hop. GP19 sits
    # at y=46.4 (clear of DEV_DP_PU_EN's own B_Cu run, 45.91, and of
    # J1B's own pad row, 47.8). GP18 needed a different ending: R_DDP.1
    # (43.75) sits in a genuinely packed pocket -- DEV_VBUS_DET's own P3V3
    # hop-via (66.15/67.85,y=42.8), HOST_VBUS_EN's plain track (y=43.5),
    # DEV_DP's own local tie (R_DPU.1->R_DDP.2,y=44.4), and R_DPU.1/
    # R_DPU.2 themselves (63.0, only 1.02mm pitch, no track fits directly
    # between them) all constrain any Y in [42.8,45.91] one way or
    # another. Landing a transition via right at R_DDP.1's own column
    # (68.49) squeezed against too many of these simultaneously (DRC-
    # confirmed repeatedly), and landing it midway at x=64.0 (still
    # inside DEV_DP's own tie span, 63.0-69.51) put the FINAL drop to
    # dest's Y right back on top of that tie (also DRC-confirmed -- a
    # drop's own X must be a real point on the tie's span check, not
    # just "east of R_DPU's pads"). Fixed by transitioning GP18 back to
    # F_Cu at x=62.0 instead -- west of R_DPU's pads (63.0, by 1.0mm,
    # clear of them regardless of Y) AND west of DEV_DP's tie span
    # entirely -- then dropping to dest's own Y (43.75) immediately,
    # still at x=62.0 (so the drop itself never touches the tie either),
    # before the final horizontal run at 43.75 into R_DDP.1: a plain
    # track needing only *track* clearance (0.4mm) from DEV_DP's tie,
    # not the stricter 0.6mm via floor (actual 0.65mm), and crossing
    # P3V3's B_Cu vertical at x=67.0 for free (different layer, no hop
    # needed once already on F_Cu). Both also hop P3V3 explicitly while
    # still on B_Cu if their transition doesn't beat it east first
    # (GP19's does not).
    def sweep_south(net_name, pico_pad, gap_a, gap_b, sweep_y, dest_ref, dest_pad,
                     lead_pts=(), hops=(), f_cu_transition_x=None, lead_hop_x=None):
        ni = _net(board, net_name)
        ncls = board.GetDesignSettings().m_NetSettings.GetEffectiveNetClass(net_name)
        via_dia = pcbnew.ToMM(ncls.GetViaDiameter())
        via_drill = pcbnew.ToMM(ncls.GetViaDrill())
        src = _pos(_pad(board, "PICO", pico_pad))
        gap_x = _gap_x(board, "PICO", gap_a, gap_b)
        dest = _pos(_pad(board, dest_ref, dest_pad))
        lo, hi = ROW1_HOP
        # Idempotence guard: check for the via at (gap_x, lo) specifically
        # -- both the lead_hop_x and plain branches below create it
        # unconditionally, so its presence is an exact proxy for "this
        # sweep already ran". `_net_has_tracks` is NOT safe here: PICO
        # row nets like GP18/GP19 already carry one F_Cu breakout-stub
        # track (from `_route_breakout_stubs`, called earlier in main())
        # before `sweep_south` ever runs, so it would report "has
        # tracks" and skip the sweep even on a fresh board (DRC/
        # unconnected-pad-confirmed -- this exact bug, tried first).
        # The ORIGINAL check here (`_track_exists` for an F_Cu segment
        # from `src` to `(gap_x, src[1])`) never matched the real first
        # segment either (which runs `src` straight to `(gap_x, lo)`,
        # not through `(gap_x, src[1])`), so it always returned False
        # and re-added a duplicate sweep on every re-run instead
        # (DRC/idempotence-confirmed).
        guard_pos = _mm(gap_x, lo)
        if any(t.Type() == pcbnew.PCB_VIA_T and t.GetNetCode() == ni.GetNetCode()
               and t.GetPosition() == guard_pos for t in board.GetTracks()):
            return
        if lead_hop_x is not None:
            # lead_pts is F_Cu, and so is the obstacle at lead_hop_x (e.g.
            # a Group-2 net's own gap-jog column) crossed between
            # lead_pts[0] and lead_pts[1] -- brief B_Cu bridge.
            lead_y = lead_pts[0][1]
            going_west = lead_pts[1][0] < lead_pts[0][0]
            before, after = ((lead_hop_x + 0.7, lead_hop_x - 0.7) if going_west
                              else (lead_hop_x - 0.7, lead_hop_x + 0.7))
            _add_track(board, ni, pcbnew.F_Cu, [src, lead_pts[0], (before, lead_y)], w_default)
            _add_via(board, ni, (before, lead_y), via_dia, via_drill)
            _add_track(board, ni, pcbnew.B_Cu, [(before, lead_y), (after, lead_y)], w_default)
            _add_via(board, ni, (after, lead_y), via_dia, via_drill)
            _add_track(board, ni, pcbnew.F_Cu,
                       [(after, lead_y)] + list(lead_pts[1:]) + [(gap_x, lo)], w_default)
        else:  # noqa: keep the plain-lead-pts path for callers without a hop
            _add_track(board, ni, pcbnew.F_Cu,
                       [src] + list(lead_pts) + [(gap_x, lo)], w_default)
        _add_via(board, ni, (gap_x, lo), via_dia, via_drill)
        _add_track(board, ni, pcbnew.B_Cu, [(gap_x, lo), (gap_x, hi)], w_default)
        _add_via(board, ni, (gap_x, hi), via_dia, via_drill)
        _add_track(board, ni, pcbnew.F_Cu, [(gap_x, hi), (gap_x, sweep_y)], w_default)
        _add_via(board, ni, (gap_x, sweep_y), via_dia, via_drill)
        cur_x = gap_x
        hop_list = list(hops) if f_cu_transition_x is not None else list(hops) + [67.0]
        for hx in hop_list:
            margin = 0.85 if hx == 67.0 else 0.7
            before, after = hx - margin, hx + margin
            _add_track(board, ni, pcbnew.B_Cu, [(cur_x, sweep_y), (before, sweep_y)], w_default)
            _add_via(board, ni, (before, sweep_y), via_dia, via_drill)
            _add_track(board, ni, pcbnew.F_Cu, [(before, sweep_y), (after, sweep_y)], w_default)
            _add_via(board, ni, (after, sweep_y), via_dia, via_drill)
            cur_x = after
        final_x = f_cu_transition_x if f_cu_transition_x is not None else dest[0]
        _add_track(board, ni, pcbnew.B_Cu, [(cur_x, sweep_y), (final_x, sweep_y)], w_default)
        _add_via(board, ni, (final_x, sweep_y), via_dia, via_drill)
        if f_cu_transition_x is not None:
            # Drop to dest's own Y immediately at the transition column
            # (west of R_DPU/DEV_DP's tie zone entirely), THEN run the
            # rest of the way at that Y -- landing the drop itself at
            # dest[0] instead (still inside the tie's own x-range) would
            # cut straight across DEV_DP's horizontal tie, DRC-confirmed.
            _add_track(board, ni, pcbnew.F_Cu,
                       [(final_x, sweep_y), (final_x, dest[1]), dest], w_default)
        else:
            _add_track(board, ni, pcbnew.F_Cu, [(final_x, sweep_y), (dest[0], sweep_y), dest], w_default)

    sweep_south("GP18", "24", "16", "17", 44.85, "R_DDP", "1", f_cu_transition_x=62.0)
    # GP19's initial jog detours south to y=31.0 first -- well past pad26
    # (bbox bottom 23.91), GP21's own y=25.5 sweep, and the whole dense
    # band of B_Cu horizontals packed into y=23.96-27.325 (ROW2_HOP vias,
    # ISENSE's own run at 25.0, I2C0_SDA's at 26.0, I2C0_SCL's at 26.6 --
    # each only 0.6-1.0mm apart, leaving no gap anywhere in that band for
    # a THIRD net's hop-via; DRC-confirmed shorting against I2C0_SDA when
    # this jog was still at y=25.7). y=31.0 sits in the genuinely empty
    # gap between I2C0_SCL's own vertical (ends at y=27.325) and DEV_
    # VBUS_DET's own east sweep (starts at y=35.0) -- and even though
    # UART0_TX's F_Cu column is present there too (needing the lead_hop_x
    # hop below), DEV_VBUS_DET's later crossing of this same X at y=35.0
    # is B_Cu, not F_Cu, so the two don't clash despite occupying the
    # same column. Crossing x=37.775 (pad26's own column) is clear
    # regardless of Y this far south (a straight jog at y=23.11, pad26's
    # own Y, would run right through its 0.8mm-radius THT copper instead,
    # DRC-confirmed -- pad26 sits between GP19's source column, 40.315,
    # and its reassigned gap, 36.505). Sweep at y=46.58, NOT 45.15 --
    # that hit DEV_DP_PU_EN's own column (37.775) TWICE: the mandatory
    # F_Cu J1B stub (40.89-47.8, any Y in GP19's range hits it) AND DEV_
    # DP_PU_EN's own custom B_Cu route (also 40.89-45.91, since GP19's
    # sweep is ALSO B_Cu) -- a same-layer hop can dodge one but not both
    # simultaneously (confirmed by DRC: the hop's own F_Cu bridge landed
    # inside the F_Cu stub). 46.58 clears DEV_DP_PU_EN's own transition
    # VIA too (60.0,45.91 -- its F_Cu stub into R_DPU.2 -- needs 0.6mm
    # via clearance, not just the 0.4mm track floor that a straight 46.4
    # gave against the line itself, DRC-confirmed) and stays south of
    # J1B's own pad top edge (46.95, needs <=46.65). The lead-in jog
    # (avoiding pad26, see above) also crosses UART0_TX's own column,
    # 39.045, on the way west to the gap -- hopped via lead_hop_x.
    sweep_south("GP19", "25", "14", "15", 46.58, "R_DDM", "1",
                lead_pts=[(40.315, 31.0), (36.505, 31.0)], lead_hop_x=39.045)

    # DEV_VBUS_DET: PICO.32 (col 22.535) -> gap8/9 (21.265, NOT gap9/10=
    # 23.805 -- that's the SWD tree's own NRESET pico_gap descent column,
    # `_NRESET_PICO_GAP`, a genuine collision) -> R_J9VD_B.1 (80.9,46.79).
    # NOT via cross(): row1/J1B share the same 2.54mm-pitch THT pads as
    # PICO's own rows (radius 0.8/0.85), and EVERY row1 column between
    # here and x=50.475 already carries a full-height F_Cu stub straight
    # down to its own J1B pad (verified by direct track dump -- BTN_USER,
    # DEV_DP_PU_EN, GP10, I2C0_SCL/SDA, GP6, GP7, HOST_VBUS_FLT, etc. all
    # do this) -- an F_Cu horizontal sweeping that many columns hits every
    # single one of them, and a Y near the J1B row itself (46.95-48.65,
    # its own pad top/bottom edges) hits the PADS directly on ANY layer
    # (THT copper). The one genuinely empty corridor is row1's own
    # pad-free gap (41.69 row1 bottom edge -> 46.95 J1B top edge) -- clear
    # of BOTH pad bands on EITHER layer, and clear of the F_Cu stubs too
    # since B_Cu is untouched by them. So: F_Cu down the gap8/9 column to
    # y=35.0, then straight onto B_Cu for the rest of the journey --
    # jogging east at y=35.0 (well north of row1, 40.89) clears GP10/
    # GP19/UART0_TX's own F_Cu columns for free (different layer; an
    # earlier F_Cu-all-the-way version crossed all three of them
    # directly, DRC-confirmed). Two B_Cu obstacles remain at y=35.0:
    # NRESET's own SWD-tree diagonal ((27.615,23.11)->(23.805,39.79),
    # crossing x~24.9 at this Y) and I2C0_SCL/SDA's own vertical descents
    # from row1 (30.155/27.615, spanning y=26.6/26.0 up to 40.89 -- NOT
    # confined further north the way their own horizontal jogs are,
    # DRC-confirmed) -- each hopped via a brief F_Cu excursion (+-0.7mm
    # for NRESET; I2C0_SCL/SDA combined into one span, 26.915-30.855,
    # since they're only 2.54mm apart). Continues on B_Cu through
    # x=39.045 (PICO row1's own pad15/16 gap -- 1.27mm clear of both
    # regardless of Y, unlike the flanking columns UART0_TX/DEV_DP_PU_EN
    # actually use) down to y=42.8 (mid-corridor) and straight into the
    # sweep east, hopping only P3V3's own vertical at x=67.0, then back
    # to F_Cu at x=80.9 for the final short drop into R_J9VD_B.1 --
    # comfortably north of R_J9VD_B.2/GND (47.81) and of J9_VBUS's own
    # hop-via cluster near (77.6,45.0-46.3), both well south of y=42.8.
    ni_dvd = _net(board, "DEV_VBUS_DET")
    ncls_dvd = board.GetDesignSettings().m_NetSettings.GetEffectiveNetClass("DEV_VBUS_DET")
    via_dia_dvd = pcbnew.ToMM(ncls_dvd.GetViaDiameter())
    via_drill_dvd = pcbnew.ToMM(ncls_dvd.GetViaDrill())
    pico32 = _pos(_pad(board, "PICO", "32"))
    gap_dvd = _gap_x(board, "PICO", "8", "9")
    if not _track_exists(board, ni_dvd.GetNetCode(), pcbnew.F_Cu, _mm(*pico32), _mm(gap_dvd, pico32[1])):
        rj9vdb1 = _pos(_pad(board, "R_J9VD_B", "1"))
        _add_track(board, ni_dvd, pcbnew.F_Cu,
                   [pico32, (gap_dvd, pico32[1]), (gap_dvd, 35.0)], w_default)
        _add_via(board, ni_dvd, (gap_dvd, 35.0), via_dia_dvd, via_drill_dvd)
        _add_track(board, ni_dvd, pcbnew.B_Cu, [(gap_dvd, 35.0), (24.9 - 0.7, 35.0)], w_default)
        _add_via(board, ni_dvd, (24.9 - 0.7, 35.0), via_dia_dvd, via_drill_dvd)
        _add_track(board, ni_dvd, pcbnew.F_Cu, [(24.9 - 0.7, 35.0), (24.9 + 0.7, 35.0)], w_default)
        _add_via(board, ni_dvd, (24.9 + 0.7, 35.0), via_dia_dvd, via_drill_dvd)
        _add_track(board, ni_dvd, pcbnew.B_Cu, [(24.9 + 0.7, 35.0), (27.615 - 0.7, 35.0)], w_default)
        _add_via(board, ni_dvd, (27.615 - 0.7, 35.0), via_dia_dvd, via_drill_dvd)
        _add_track(board, ni_dvd, pcbnew.F_Cu, [(27.615 - 0.7, 35.0), (30.155 + 0.7, 35.0)], w_default)
        _add_via(board, ni_dvd, (30.155 + 0.7, 35.0), via_dia_dvd, via_drill_dvd)
        _add_track(board, ni_dvd, pcbnew.B_Cu,
                   [(30.155 + 0.7, 35.0), (39.045, 35.0), (39.045, 42.8)], w_default)
        _add_track(board, ni_dvd, pcbnew.B_Cu, [(39.045, 42.8), (67.0 - 0.85, 42.8)], w_default)
        _add_via(board, ni_dvd, (67.0 - 0.85, 42.8), via_dia_dvd, via_drill_dvd)
        _add_track(board, ni_dvd, pcbnew.F_Cu, [(67.0 - 0.85, 42.8), (67.0 + 0.85, 42.8)], w_default)
        _add_via(board, ni_dvd, (67.0 + 0.85, 42.8), via_dia_dvd, via_drill_dvd)
        _add_track(board, ni_dvd, pcbnew.B_Cu, [(67.0 + 0.85, 42.8), (80.9, 42.8)], w_default)
        _add_via(board, ni_dvd, (80.9, 42.8), via_dia_dvd, via_drill_dvd)
        # Final vertical drop into R_J9VD_B.1 (80.9,46.79) crosses TWO
        # pre-existing F_Cu ties at that same X -- DEV_DP's ESD_D->J9.3
        # leg (y=45.0) and DEV_DM's ESD_D->J9.2 leg (y=45.65), only
        # 0.65mm apart -- one combined B_Cu bridge spanning both
        # (+-0.7mm margin each side, matching this net's other hops)
        # clears them together rather than two independent hops.
        _add_track(board, ni_dvd, pcbnew.F_Cu, [(80.9, 42.8), (80.9, 45.0 - 0.7)], w_default)
        _add_via(board, ni_dvd, (80.9, 45.0 - 0.7), via_dia_dvd, via_drill_dvd)
        _add_track(board, ni_dvd, pcbnew.B_Cu, [(80.9, 45.0 - 0.7), (80.9, 45.65 + 0.7)], w_default)
        _add_via(board, ni_dvd, (80.9, 45.65 + 0.7), via_dia_dvd, via_drill_dvd)
        _add_track(board, ni_dvd, pcbnew.F_Cu, [(80.9, 45.65 + 0.7), rj9vdb1], w_default)

    # --- North-bound (row1 -> north of row2) ----------------------------
    # GP10: PICO.14 (col 35.235) -> gap13/14 (33.965) -> hop ROW2 AND J2B
    # (target past J2B's y=15.6) -> R_LED_USER.1 (56.3,12.11). The final
    # horizontal (33.965->56.3 at y=12.11) crosses UART0_TX's (39.045)
    # and UART0_RX's (44.125) own post-hop verticals, which run down to
    # their own targets at y=10.655 -- y=12.11 is inside that span for
    # both, so hop over each (x_hops).
    cross("GP10", "14", "13", "14", [ROW2_HOP, J2B_HOP],
          [(33.965, 12.11)], "R_LED_USER", "1", x_hops=[39.045, 44.125])

    # UART0_TX, UART0_RX, and BTN_USER all sweep east at a roughly-
    # constant Y once past row2/J2B, and ALL three cross NATIVE_VBUS_DET's
    # own north-south column (x=57.3, spans y=7.0-15.0 -- see that net's
    # own routing below in _route_pico_no_jog) somewhere along that
    # sweep -- each needs a brief B_Cu hop there (+-0.7mm margin, same as
    # this file's other track hops). Not reachable via cross()'s x_hops
    # (those only cover the final leg, and this crossing happens mid-
    # sweep), so a small local helper mirrors cross()'s row-hop, then the
    # caller finishes the path by hand.
    def hop_north(net_name, pico_pad, gap_a, gap_b, target_y):
        """PICO.pico_pad -> F_Cu jog to gap_x -> hop ROW2_HOP then J2B_HOP
        (B_Cu) -> F_Cu down to target_y. Returns (ni, gap_x) so the
        caller can continue the path from (gap_x, target_y)."""
        ni = _net(board, net_name)
        ncls = board.GetDesignSettings().m_NetSettings.GetEffectiveNetClass(net_name)
        via_dia = pcbnew.ToMM(ncls.GetViaDiameter())
        via_drill = pcbnew.ToMM(ncls.GetViaDrill())
        src = _pos(_pad(board, "PICO", pico_pad))
        gap_x = _gap_x(board, "PICO", gap_a, gap_b)
        _add_track(board, ni, pcbnew.F_Cu, [src, (gap_x, src[1])], w_default)
        cur_y = src[1]
        for lo, hi in (ROW2_HOP, J2B_HOP):
            _add_track(board, ni, pcbnew.F_Cu, [(gap_x, cur_y), (gap_x, hi)], w_default)
            _add_via(board, ni, (gap_x, hi), via_dia, via_drill)
            _add_track(board, ni, pcbnew.B_Cu, [(gap_x, hi), (gap_x, lo)], w_default)
            _add_via(board, ni, (gap_x, lo), via_dia, via_drill)
            cur_y = lo
        _add_track(board, ni, pcbnew.F_Cu, [(gap_x, cur_y), (gap_x, target_y)], w_default)
        return ni, gap_x

    # NATIVE_VBUS_DET's own column is B_Cu south of J2B (see
    # _route_pico_no_jog) specifically so these three F_Cu nets cross it
    # for free -- no hop needed against it any more (an earlier version
    # hopped it at its old F_Cu column, 57.3, which sat in the same tiny
    # pocket as I2C0_SCL/SDA and LED_USER with no room for a third net to
    # thread through on either layer).

    # All three exit the J2B_HOP at the same Y (15.0) and fan out east on
    # F_Cu with overlapping horizontal spans -- their own target Y's
    # can't be picked independently (a 3-way circular conflict, same
    # species as the P3V3/I2C0_SCL/I2C0_SDA/J_STEMMA one from Group 1):
    # UART0_TX's span (39.045-59.26) contains BOTH UART0_RX's (44.125)
    # and BTN_USER's (46.665) own descent columns, so whichever of THEM
    # has to pass north of UART0_TX's Y on its own way down from 15.0
    # crosses it. Fixed by ordering all three monotonically by column:
    # UART0_TX (westmost column) gets the NORTHERNMOST target Y (12.9),
    # so neither UART0_RX's nor BTN_USER's later, shallower descent
    # (13.3/13.8, both >12.9) ever reaches back up to cross it; UART0_RX
    # (44.125) similarly sits north of BTN_USER's own descent (46.665).
    # 12.9 clears GP10's own horizontal (12.11, 0.79mm, needs >=0.4) and
    # R_LED_USER.1's pad (56.3,12.11, needs distance-from-center>=0.62mm,
    # actual 0.69mm).

    # UART0_TX: PICO.16 (col 40.315) -> gap15/16 (39.045, same gap GP19
    # used to use -- different layer/short-hop-only now, no conflict) ->
    # hop ROW2 AND J2B -> east at y=12.9 -> final short drop to 10.655 at
    # x=59.26 (J_UART.1's own column, THT -- no via).
    ju1 = _pos(_pad(board, "J_UART", "1"))
    if not _track_exists(board, _net(board, "UART0_TX").GetNetCode(), pcbnew.F_Cu,
                          _mm(40.315, 40.89), _mm(39.045, 40.89)):
        ni_tx, gap_tx = hop_north("UART0_TX", "16", "15", "16", 12.9)
        _add_track(board, ni_tx, pcbnew.F_Cu,
                   [(gap_tx, 12.9), (ju1[0], 12.9), ju1], w_default)

    # UART0_RX: PICO.17 (col 42.855) -> gap17/18 (44.125, same gap GP18
    # used to use) -> hop ROW2 AND J2B -> east at y=13.3 (0.4mm south of
    # UART0_TX's own y=12.9) -> continue to x=60.6 (0.49mm east of
    # J_UART.1's own bbox right edge 60.11, and comfortably south of its
    # pad top edge, 9.805, so no separate detour is needed here any more)
    # -> drop to 10.655 -> J_UART.2 (61.8,10.655, THT).
    ju2 = _pos(_pad(board, "J_UART", "2"))
    if not _track_exists(board, _net(board, "UART0_RX").GetNetCode(), pcbnew.F_Cu,
                          _mm(42.855, 40.89), _mm(44.125, 40.89)):
        ni_rx, gap_rx = hop_north("UART0_RX", "17", "17", "18", 13.3)
        _add_track(board, ni_rx, pcbnew.F_Cu,
                   [(gap_rx, 13.3), (60.6, 13.3), (60.6, 10.655), ju2], w_default)

    # BTN_USER: PICO.19 (col 47.935) -> gap18/19 (46.665) -> hop ROW2 AND
    # J2B -> north to y=13.8 (0.5mm south of UART0_RX's own y=13.3, and
    # clear of J_UART's courtyard bottom 12.47 and everything in the
    # J_STEMMA/I2C0/P3V3/R_NVD row, all south of y=13.8) -> east to
    # x=66.0 (clear of SW_USER's own pad2/GND column, 67.525) -> south
    # into SW_USER.1 (67.525,5.25) from the west at its own y (never
    # sweeping past pad2's y=9.75).
    su1 = _pos(_pad(board, "SW_USER", "1"))
    if not _track_exists(board, _net(board, "BTN_USER").GetNetCode(), pcbnew.F_Cu,
                          _mm(47.935, 40.89), _mm(46.665, 40.89)):
        ni_btn, gap_btn = hop_north("BTN_USER", "19", "18", "19", 13.8)
        _add_track(board, ni_btn, pcbnew.F_Cu,
                   [(gap_btn, 13.8), (66.0, 13.8), (66.0, su1[1]), su1], w_default)

    # HOST_VBUS_EN: PICO.22 (col 47.935) -> gap19/20 (49.205, the *other*
    # gap at this column -- BTN_USER above claims 46.665) -> U_HSW.4
    # (65.638,39.15). NOT via cross()'s straight-line approach: a direct
    # (49.205,39.15)->(65.638,39.15) horizontal runs dead on top of
    # HOST_VBUS_FLT's own (50.475,39.15)->(63.3625,39.15) leg (Group 1,
    # _route_pico_no_jog) for their entire shared span -- same Y, same
    # layer, straight short. A hop-based crossing of the FLT J1B-stub
    # column (x=50.475, spans y=40.89-47.8) at sweep-height y=43.3 was
    # tried first, but that hop's own vias (49.775/51.175) sit only
    # 0.5mm from DEV_VBUS_DET's sweep (y=42.8, which also crosses this X
    # range) -- short of the 0.6mm via-clearance floor, and there's no
    # slack left in [42.73,44.0] to fit DEV_VBUS_DET, this hop, AND
    # GP18's own sweep all at once. Simpler fix: cross x=50.475 while
    # still NORTH of the FLT stub's own Y-range entirely (y=35.0, well
    # above 40.89) -- nothing occupies that column above the stub there,
    # so the HORIZONTAL jog itself needs no hop. Descends the gap column
    # from row2 (23.11) to y=35.0, jogs east past x=50.475, then
    # continues down to y=43.5 (NOT 43.3 -- that plain track sat only
    # 0.5mm from DEV_VBUS_DET's own P3V3 hop-via, 66.15/67.85,y=42.8,
    # short of the 0.6mm via-clearance floor; 43.5 gives 0.7mm) at x=52.0
    # (NOT 51.175 -- that column's own vertical drop would still pass
    # through PICO pad20's Y, 40.89, only 0.7mm away, inside its 0.8mm
    # radius outright, DRC-confirmed; 52.0 is 1.525mm clear of pad20 and
    # west of R_HVEN_PD.2/GND's pad, 65.64,42.11, and of the FLT stub's
    # own column). This VERTICAL drop (35.0->39.85 at x=52.0) still
    # crosses HOST_VBUS_FLT's own horizontal approach into U_HSW.3
    # (y=39.15, x=50.475-63.362, which DOES include x=52.0) -- a second
    # brief hop (+-0.7mm in Y this time, crossing a horizontal obstacle)
    # clears it. From there, the run east STAYS at y=39.85 all the way
    # to x=67.0 -- NOT dropping down into GP18/DEV_DP/DEV_VBUS_DET's own
    # congested pocket (y=43-45) at all, since it doesn't need to: 39.85
    # clears U_HSW.3 itself (63.362,39.15, 0.7mm away) and everything
    # else near there (R_HVEN_PD's pads start at y=41.09, HOST_5V_IN's
    # own vertical stops at y=37.25) -- before a short final drop to
    # 39.15 at x=67.0 (P3V3's B_Cu vertical there doesn't matter --
    # different layer) and the westward approach into U_HSW.4 from the
    # EAST, never crossing pad3/FLT's own approach at x=63.3625. (An
    # earlier version continued down to y=43.5 first, matching GP18's
    # own final approach level too closely -- DRC-confirmed -- for no
    # reason, since hsw4's own Y, 39.15, never needed that detour.)
    pico22 = _pos(_pad(board, "PICO", "22"))
    ni_hven = _net(board, "HOST_VBUS_EN")
    ncls_hven = board.GetDesignSettings().m_NetSettings.GetEffectiveNetClass("HOST_VBUS_EN")
    via_dia_hven = pcbnew.ToMM(ncls_hven.GetViaDiameter())
    via_drill_hven = pcbnew.ToMM(ncls_hven.GetViaDrill())
    gap_hven = _gap_x(board, "PICO", "19", "20")
    if not _track_exists(board, ni_hven.GetNetCode(), pcbnew.F_Cu, _mm(*pico22), _mm(gap_hven, pico22[1])):
        hsw4 = _pos(_pad(board, "U_HSW", "4"))
        _add_track(board, ni_hven, pcbnew.F_Cu,
                   [pico22, (gap_hven, pico22[1]), (gap_hven, 35.0), (52.0, 35.0),
                    (52.0, 39.15 - 0.7)], w_default)
        _add_via(board, ni_hven, (52.0, 39.15 - 0.7), via_dia_hven, via_drill_hven)
        _add_track(board, ni_hven, pcbnew.B_Cu, [(52.0, 39.15 - 0.7), (52.0, 39.15 + 0.7)], w_default)
        _add_via(board, ni_hven, (52.0, 39.15 + 0.7), via_dia_hven, via_drill_hven)
        _add_track(board, ni_hven, pcbnew.F_Cu,
                   [(52.0, 39.15 + 0.7), (67.0, 39.15 + 0.7), (67.0, hsw4[1]), hsw4],
                   w_default)


def _route_cluster_leftovers(board):
    """A handful of single MST edges task-14h's own local-cluster passes
    missed on the first pass (found via DRC after the rest of the cluster
    work landed): DEV_DP's R_DPU.1 leg, HOST_VBUS's ESD_H.5 tap, J9_VBUS's
    R_J9VD_T.1->J9.1 leg, and P3V3's J_STEMMA.2 + U_ISNS.5->[SWD-tree P3V3
    via at J6] legs."""
    w_default = pcbnew.ToMM(
        board.GetDesignSettings().m_NetSettings.GetDefaultNetclass().GetTrackWidth()
    )

    # DEV_DP: R_DPU.1 (63.0,44.89) -> R_DDP.2 (69.51,43.75). Both R_DDP.1/
    # GP18 (bbox y 43.43-44.07) and R_DDM.1-2/GP19+DEV_DM (bbox y >=45.33)
    # block a naive approach -- but the direct y-range between R_DPU.1
    # (44.89) and R_DDP.2 (43.75) itself is entirely clear of both, so jog
    # north to y=44.4 (0.33mm clear of R_DDP.1's bottom edge, well short
    # of R_DDM's row) instead of south.
    ni = _net(board, "DEV_DP")
    w = _class_width(board, "DEV_DP")
    rdpu1 = _pos(_pad(board, "R_DPU", "1"))
    rddp2 = _pos(_pad(board, "R_DDP", "2"))
    _add_path_once(board, ni, pcbnew.F_Cu,
                    [rdpu1, (rdpu1[0], 44.4), (rddp2[0], 44.4), rddp2], w)

    # HOST_VBUS: J5.1 -> ESD_H.5. ESD_H's pad4(HOST_DM)/pad5(HOST_VBUS)/
    # pad6(HOST_DP) share x=67.838 -- jog to an intermediate x (69.0, in
    # the gap between ESD_H's and J5's own courtyards). That column also
    # crosses HOST_DM's own ESD_H.4->J5.2 tie (a "wall" at y=20.95
    # spanning x=67.838-71.365, the same shape as the DEV_DM one earlier)
    # -- hopped via a brief B_Cu excursion (empty there), same technique.
    ni = _net(board, "HOST_VBUS")
    w = _class_width(board, "HOST_VBUS")
    ncls = board.GetDesignSettings().m_NetSettings.GetEffectiveNetClass("HOST_VBUS")
    via_dia = pcbnew.ToMM(ncls.GetViaDiameter())
    via_drill = pcbnew.ToMM(ncls.GetViaDrill())
    j5_1 = _pos(_pad(board, "J5", "1"))
    esdh5 = _pos(_pad(board, "ESD_H", "5"))
    hop_x = 69.0
    hop_lo, hop_hi = 20.95 + 0.65, 20.95 - 0.65
    if not _track_exists(board, ni.GetNetCode(), pcbnew.F_Cu, _mm(*j5_1), _mm(hop_x, j5_1[1])):
        _add_track(board, ni, pcbnew.F_Cu, [j5_1, (hop_x, j5_1[1]), (hop_x, hop_lo)], w)
        _add_via(board, ni, (hop_x, hop_lo), via_dia, via_drill)
        _add_track(board, ni, pcbnew.B_Cu, [(hop_x, hop_lo), (hop_x, hop_hi)], w)
        _add_via(board, ni, (hop_x, hop_hi), via_dia, via_drill)
        _add_track(board, ni, pcbnew.F_Cu, [(hop_x, hop_hi), (hop_x, esdh5[1]), esdh5], w)

    # J9_VBUS: R_J9VD_T.1 -> J9.1. Same east-jog-around-pad2 technique as
    # _route_j9_vbus_esd_tap (a different offset, 1.6mm not 1.4mm, so this
    # call's first segment doesn't collide with that function's own first
    # segment on the idempotence check). Necked to Default width for the
    # final approach -- J9's own pad2 (DEV_DM, y=45.65) sits close enough
    # to pad1's y (46.3) that Power's 0.5mm round end-cap clips it.
    ni = _net(board, "J9_VBUS")
    r_t1 = _pos(_pad(board, "R_J9VD_T", "1"))
    j9_1 = _pos(_pad(board, "J9", "1"))
    east = (r_t1[0] + 1.6, r_t1[1])
    _add_path_once(board, ni, pcbnew.F_Cu,
                    [r_t1, east, (east[0], j9_1[1]), j9_1], w_default)

    # P3V3: U_INA219_ALT.4 -> J_STEMMA.2, B_Cu (empty), Default width (not
    # Power -- see _route_power_cluster_bcu's rationale). Column 41.585:
    # the midpoint gap between J2B pad15/GP19 (40.315) and pad16/GP18
    # (42.855) -- J2B is THT (B_Cu copper too), and its 2.54mm pitch
    # needs the same "land exactly on the gap" treatment as the trace
    # bundle's own J1B crossings (43.0, tried first, was only 0.145mm
    # from J2B pad16 -- direct collision).
    #
    # Peels off at y=5.0 -- NOT the 6-7 band right under J_STEMMA's pad
    # row (5.9): I2C0_SCL's and I2C0_SDA's own approach vias sit AT
    # (46.6,5.9) and (47.6,5.9), each with their own long B_Cu horizontal
    # arriving from the east (SCL at y=6.6/7.0ish, SDA at y=6.1/6.5ish,
    # see _route_i2c0_stemma_bcu) -- and this net's target (48.6) is EAST
    # of *both* of theirs, so a horizontal approach at any y in that band
    # crosses one or both vias' exclusion zones, and a final vertical
    # drop from any peel above that band into y=5.9 necessarily crosses
    # BOTH their horizontals (a genuine 3-way circular conflict: SCL's
    # horizontal spans over SDA's and this net's targets, SDA's spans
    # over this net's, and this net's spans over both of theirs -- no
    # Y-ordering resolves a cycle). Solved geometrically instead: staying
    # at y=5.0 (0.9mm *north* of the whole 5.9 pad row, comfortably
    # outside both vias' ~0.5mm exclusion and both nets' 6.1-7.0 band)
    # all the way across to x=48.6, THEN a short final drop straight down
    # into the pad -- a column no one else's copper occupies.
    ni = _net(board, "P3V3")
    ncls = board.GetDesignSettings().m_NetSettings.GetEffectiveNetClass("P3V3")
    via_dia = pcbnew.ToMM(ncls.GetViaDiameter())
    via_drill = pcbnew.ToMM(ncls.GetViaDrill())
    p_ina = _pos(_pad(board, "U_INA219_ALT", "4"))
    via_ina = (p_ina[0], p_ina[1] - 1.2)  # same via _route_power_cluster_bcu already placed
    st2 = _pos(_pad(board, "J_STEMMA", "2"))
    col = 41.585
    peel_y = 5.0
    cross_y = 18.0  # NOT via_ina's own y (26.125): I2C0_SDA's own hop
    # over I2C0_SCL's column, and ISENSE's own hop over the same
    # (55.3-57.7) span, both land close to y=26.0/25.0 -- via-to-via
    # clearance needs >=0.8mm separation (two 0.3mm-radius vias need
    # 0.2mm clearance between them: 0.3+0.3+0.2=0.8mm), and PICO row2's
    # own pad bbox (22.31-23.91, e.g. PICO.21/NATIVE_VBUS_DET at x=50.475
    # -- within this net's horizontal span) rules out anything in
    # 22.01-24.21 too. 18.0 clears all of that (below GP20's own target
    # y=19.0, so this net's final vertical drop at col=41.585, spanning
    # only down to peel_y=5.0, never reaches back up to 19.0/21.0 where
    # GP20/GP21 actually have copper -- confirmed no crossing despite the
    # x-overlap with their own horizontals).
    if not _track_exists(board, ni.GetNetCode(), pcbnew.B_Cu, _mm(*via_ina), _mm(via_ina[0], cross_y)):
        _add_track(board, ni, pcbnew.B_Cu, [via_ina, (via_ina[0], cross_y), (57.7, cross_y)], w_default)
        _hop_x(board, ni, w_default, via_dia, via_drill, cross_y, 57.7, 55.3)
        _add_track(board, ni, pcbnew.B_Cu,
                   [(55.3, cross_y), (col, cross_y), (col, peel_y), (st2[0], peel_y)], w_default)
        _add_via(board, ni, st2, via_dia, via_drill)
        _add_track(board, ni, pcbnew.B_Cu, [(st2[0], peel_y), st2], w_default)

    # P3V3: U_ISNS.5 -> the SWD tree's existing P3V3 via at J6.1
    # (49.86,61.15). B_Cu the whole way (matches the SWD tree's own P3V3
    # convention -- also Default width for the same reason). Jogs east
    # off U_ISNS's own column first (pad4/HOST_5V_IN sits directly south
    # at the same x), south through the open area below PICO row1, then
    # WEST at y=50.5 -- south of J1B's own THT breakout row (courtyard
    # bottom 49.645; this Y choice, not the column X, is what keeps this
    # path clear of J1B's row -- the horizontal at y=50.5 crosses many
    # J1B column X values but never J1B's actual Y span) -- to x=47.0.
    # NOT x=48.5: that's SWCLK's own J6 escape column (_SWCLK_ESCAPE_X),
    # occupied y=58.90-62.65. NOT x=49.86 either: J6's pin1/pin2 share
    # that X (pad1=P3V3 y=61.15, pad2=SWDIO y=57.25), so descending there
    # would clip pad2. x=47.0 clears both (>=1.36mm) and stays well east
    # of the trace bundle's own lane/landing footprint (x<=20.605) so it
    # can't touch the Task-15 pour-preservation corridor either. Only
    # then south, hopping the SWD tree's SWDIO (y=58.80) and NRESET
    # (y=59.42) B_Cu trunks in one F_Cu excursion (58.45 to 59.77 -- the
    # trunks are only 0.62mm apart, closer than two separate hops'
    # clearance needs, so one hop covers both, mirroring
    # _spike_to_trunk's technique), then a final short jog east into
    # J6.1's own column. Hop span 58.1-60.1 (not the SWD tree's own
    # 0.65mm _HOP_MM): that constant was tuned for Default-vs-Default
    # track+via geometry; this hop's via is P3V3's own class (also
    # 0.6mm dia, same physical size, so the same 0.6mm floor applies,
    # but the margin here needs to clear the NRESET/SWDIO pair's
    # *combined* span, not one trunk -- 0.7mm/0.68mm from each,
    # comfortably over the 0.6mm floor (0.3 via radius + 0.1 track
    # halfwidth + 0.2 clearance)."""
    p_isns = _pos(_pad(board, "U_ISNS", "5"))
    j6_p3v3 = _pos(_pad(board, "J6", "1"))
    if not _track_exists(board, ni.GetNetCode(), pcbnew.B_Cu, _mm(*p_isns), _mm(67.0, p_isns[1])):
        hop_col = 47.0
        hop_lo, hop_hi = 58.1, 60.1
        _add_track(board, ni, pcbnew.B_Cu, [
            p_isns, (67.0, p_isns[1]), (67.0, 50.5), (hop_col, 50.5), (hop_col, hop_lo),
        ], w_default)
        _add_via(board, ni, (hop_col, hop_lo), via_dia, via_drill)
        _add_track(board, ni, pcbnew.F_Cu, [(hop_col, hop_lo), (hop_col, hop_hi)], w_default)
        _add_via(board, ni, (hop_col, hop_hi), via_dia, via_drill)
        _add_track(board, ni, pcbnew.B_Cu,
                   [(hop_col, hop_hi), (hop_col, j6_p3v3[1]), j6_p3v3], w_default)


def _route_dev_dp_esd_j9(board):
    """ESD_D.6 (DEV_DP) -> J9.3: ESD_D's own pad5 (J9_VBUS, y=44.7) sits
    directly below pad6 (y=43.75, same x=78.638) -- jog east first (clear
    of pad5's column) before dropping to J9.3's y and heading into it."""
    ni = _net(board, "DEV_DP")
    w = _class_width(board, "DEV_DP")
    p0 = _pos(_pad(board, "ESD_D", "6"))
    p1 = _pos(_pad(board, "J9", "3"))
    pts = [p0, (79.8, p0[1]), (79.8, p1[1]), p1]
    _add_path_once(board, ni, pcbnew.F_Cu, pts, w)


def _route_j9_vbus_esd_tap(board):
    """R_J9VD_T.1 (J9_VBUS) -> ESD_D.5: R_J9VD_T's own pad1(J9_VBUS,y=47.81)
    /pad2(DEV_VBUS_DET,y=46.79) share x=82.6 -- exit east first (away from
    pad2). Then south (clear of R_J9VD's own courtyard and D_J9_BUSPWR's),
    west along y=49.0 to x=77.6, then north toward ESD_D.5's own y --
    crossing DEV_DM's y=45.65 "wall" along the way (R_DDM->ESD_D.3,
    ESD_D.3<->ESD_D.4, ESD_D.4->J9.2 together span the *entire*
    x=69.51-86.795, no gap), so that crossing hops briefly to B_Cu (empty
    there) and back via two vias, mirroring _spike_to_trunk. x=77.6 (not
    76.362, ESD_D.1/2/3's own column) clears ESD_D.2/GND's bbox (right
    edge 77.025) by >=0.5mm."""
    ni = _net(board, "J9_VBUS")
    w = _class_width(board, "J9_VBUS")
    ncls = board.GetDesignSettings().m_NetSettings.GetEffectiveNetClass("J9_VBUS")
    via_dia = pcbnew.ToMM(ncls.GetViaDiameter())
    via_drill = pcbnew.ToMM(ncls.GetViaDrill())
    p0 = _pos(_pad(board, "R_J9VD_T", "1"))
    p1 = _pos(_pad(board, "ESD_D", "5"))
    hop_x = 77.6
    east = (p0[0] + 1.4, p0[1])
    hop_lo, hop_hi = 45.65 - 0.65, 45.65 + 0.65
    if _track_exists(board, ni.GetNetCode(), pcbnew.F_Cu, _mm(*p0), _mm(*east)):
        return
    _add_track(board, ni, pcbnew.F_Cu, [p0, east, (east[0], 49.0), (hop_x, 49.0), (hop_x, hop_hi)], w)
    _add_via(board, ni, (hop_x, hop_hi), via_dia, via_drill)
    _add_track(board, ni, pcbnew.B_Cu, [(hop_x, hop_hi), (hop_x, hop_lo)], w)
    _add_via(board, ni, (hop_x, hop_lo), via_dia, via_drill)
    _add_track(board, ni, pcbnew.F_Cu, [(hop_x, hop_lo), (hop_x, p1[1]), p1], w)


def _route_vbus_sel_5v_ladder(board):
    """VBUS_SEL / HOST_5V_IN around R_SHUNT/U_ISNS/U_INA219_ALT/U_HSW:
    F_Cu, kept apart by construction. Each leg into a stacked-pad
    footprint (U_INA219_ALT's 4 pins at x=62.638, U_ISNS's 2 columns)
    approaches horizontally at exactly its own pad's y -- never sweeping
    vertically past a same-column neighbor. HOST_5V_IN's R_SHUNT->U_HSW
    spine is offset to x=67.3 (east of U_ISNS.5/pad5's bbox, R=66.4) so it
    doesn't clip that P3V3 pad while passing it; VBUS_SEL's R_SHUNT->
    U_ISNS.3 spine is offset to x=62.0 (west of U_ISNS.2/GND's bbox,
    L=62.8) for the same reason against that pad.
    The R_SHUNT->U_INA219_ALT legs (VBUS_SEL pad1, HOST_5V_IN pad2) are
    necked to Default width (0.2mm): Power class is 0.5mm, and a 0.5mm
    track running near INA219_ALT's own 0.65mm pin pitch doesn't clear its
    *other* stacked pins (P3V3/GND/HOST_5V_IN neighbors) -- same rationale
    as the SWD tree's P3V3 VTref taps necking down for a tight gap; this
    net's whole INA219_ALT leg is low-current-sense anyway, and
    INA219_ALT itself is DNP (never populated).
    JP1.2->R_LED_PWR.1 (VBUS_SEL, far northwest corner) is separate and
    routed on B_Cu below -- an F_Cu path there crosses JP1's own
    V5_JTRACE pad and the LED_PWR_A tie.
    """
    w_default = pcbnew.ToMM(
        board.GetDesignSettings().m_NetSettings.GetDefaultNetclass().GetTrackWidth()
    )
    ni_sel = _net(board, "VBUS_SEL")
    w_sel = _class_width(board, "VBUS_SEL")
    shunt1 = _pos(_pad(board, "R_SHUNT", "1"))
    ina1 = _pos(_pad(board, "U_INA219_ALT", "1"))
    isns3 = _pos(_pad(board, "U_ISNS", "3"))
    _add_path_once(board, ni_sel, pcbnew.F_Cu, [shunt1, (shunt1[0], ina1[1]), ina1], w_default)
    _add_path_once(board, ni_sel, pcbnew.F_Cu,
                    [shunt1, (62.0, shunt1[1]), (62.0, isns3[1]), isns3], w_sel)

    ni_5v = _net(board, "HOST_5V_IN")
    w_5v = _class_width(board, "HOST_5V_IN")
    shunt2 = _pos(_pad(board, "R_SHUNT", "2"))
    ina2 = _pos(_pad(board, "U_INA219_ALT", "2"))
    isns4 = _pos(_pad(board, "U_ISNS", "4"))
    hsw5 = _pos(_pad(board, "U_HSW", "5"))
    _add_path_once(board, ni_5v, pcbnew.F_Cu, [shunt2, (shunt2[0], ina2[1]), ina2], w_default)
    # isns4/hsw5 share the shunt2->(67.3,shunt2[1]) spine segment --
    # _add_path_once only checks each call's *first* segment, so it must be
    # added once on its own before the two branches (each branch's own
    # first segment, (67.3,shunt2[1])->its own y, is otherwise identical
    # between the two calls only in its start point, not its end point, so
    # this split isn't strictly required for correctness here -- but kept
    # explicit for clarity/reuse).
    spine = (67.3, shunt2[1])
    _add_path_once(board, ni_5v, pcbnew.F_Cu, [shunt2, spine], w_5v)
    _add_path_once(board, ni_5v, pcbnew.F_Cu, [spine, (67.3, isns4[1]), isns4], w_5v)
    _add_path_once(board, ni_5v, pcbnew.F_Cu, [spine, (67.3, hsw5[1]), hsw5], w_5v)

    # VBUS_SEL: JP1.2 (THT, no via needed) -> B_Cu -> single via at
    # R_LED_PWR.1 (SMD). Approaches from the south (y=13.0 > pad1's own
    # y=12.61) so it never sweeps past pad2 (LED_PWR_A, y=11.59, further
    # north).
    ncls = board.GetDesignSettings().m_NetSettings.GetEffectiveNetClass("VBUS_SEL")
    via_dia = pcbnew.ToMM(ncls.GetViaDiameter())
    via_drill = pcbnew.ToMM(ncls.GetViaDrill())
    jp1_2 = _pos(_pad(board, "JP1", "2"))
    rled = _pos(_pad(board, "R_LED_PWR", "1"))
    if not _track_exists(board, ni_sel.GetNetCode(), pcbnew.B_Cu, _mm(*jp1_2), _mm(jp1_2[0], 13.0)):
        south_y = 13.0
        _add_via(board, ni_sel, rled, via_dia, via_drill)
        _add_track(board, ni_sel, pcbnew.B_Cu,
                   [jp1_2, (jp1_2[0], south_y), (rled[0], south_y), rled], w_sel)


def _route_final_long_runs(board):
    """The last few non-GND pad-pairs: VBUS_NET's remaining connections
    (JP4.1, J8.1, D_J9_BUSPWR.2), V5_JTRACE (JP1.1 -> J3.11), and
    VBUS_SEL (U_INA219_ALT.1 -> the existing JP1.2/R_LED_PWR cluster).
    All three nets are Power netclass (0.5mm track, 0.25mm halfwidth) --
    every margin below accounts for that, not the 0.2mm Default width
    used everywhere else in this file.

    Review fix (Task 14i): a 1 oz/0.2mm neck is only 0.745A-rated (IPC-2221,
    10C rise) -- fine for a genuine tight-pitch crossing, marginal for
    VBUS_SEL's ~650-760mA worst case over any real length. VBUS_NET's and
    VBUS_SEL's own long vertical runs at x=16.185/31.425 cross PICO row2
    (y=23.11) and J2B's mirrored row (y=15.6) -- 1.6/1.7mm round pads on a
    2.54mm pitch, 1.27mm each side of the gap column, same geometry
    `_route_pico_row_jog` already resolved for vias (its ROW2_HOP/J2B_HOP
    margins) -- so only a short band around each row actually needs the
    0.2mm neck; the rest of each run goes back to full 0.5mm Power width.
    """
    ROW2_NECK_MM = (23.11 - 0.85, 23.11 + 0.85)  # matches _route_pico_row_jog's ROW2_HOP
    J2B_NECK_MM = (15.6 - 0.6, 15.6 + 0.6)        # matches _route_pico_row_jog's J2B_HOP
    # DRC-discovered (Task 14i): VBUS_NET's x=16.185 column also passes
    # close to two OTHER Power-class nets' own hop-vias -- V5_JTRACE's at
    # (15.5/16.9, 27.5) and VBUS_SEL's at (15.5, 13.0) -- both only
    # ~0.685-0.715mm away in X, just short of the 0.75mm a Power-width
    # track+via pair needs (0.3 via r + 0.25 track halfwidth + 0.2
    # clearance) at zero Y-offset; +-0.5mm clears both with margin.
    V5J_NECK_MM = (27.5 - 0.5, 27.5 + 0.5)
    SEL_HOP_NECK_MM = (13.0 - 0.5, 13.0 + 0.5)

    w_default = pcbnew.ToMM(
        board.GetDesignSettings().m_NetSettings.GetDefaultNetclass().GetTrackWidth()
    )

    def power_via(net_name):
        ncls = board.GetDesignSettings().m_NetSettings.GetEffectiveNetClass(net_name)
        return (pcbnew.ToMM(ncls.GetTrackWidth()), pcbnew.ToMM(ncls.GetViaDiameter()),
                pcbnew.ToMM(ncls.GetViaDrill()))

    # VBUS_NET: JP4.1 (19.73,10.655) -> JP1.3 (15.04,10.655, already wired
    # north to the PICO/J2B chain) -- a direct horizontal at their shared
    # Y, clear of NVD_TOP's own vertical (22.27,9.51-10.655, east of
    # both). Then JP4.1 -> J8.1 (30.7,5.36, SMD -- F_Cu only, unlike
    # every THT connector elsewhere in this file, so needs a via for the
    # B_Cu approach): loops north of NVD_TOP's own horizontal (22.27-
    # 52.9,y=9.51) at y=7.5 (clear of its vertical too, which stops at
    # 10.655) before dropping into J8.1 from the west, comfortably north
    # of J8's other pads (all at y<=5.36 further east).
    w_net, via_dia_net, via_drill_net = power_via("VBUS_NET")
    ni_net = _net(board, "VBUS_NET")
    jp4_1 = _pos(_pad(board, "JP4", "1"))
    jp1_3 = _pos(_pad(board, "JP1", "3"))
    j8_1 = _pos(_pad(board, "J8", "1"))
    _add_path_once(board, ni_net, pcbnew.B_Cu, [jp4_1, jp1_3], w_net)
    if not _track_exists(board, ni_net.GetNetCode(), pcbnew.B_Cu, _mm(*jp4_1), _mm(jp4_1[0], 7.5)):
        # Straight drop at J8.1's own x (30.7) grazes J8.2 (30.05,5.36,
        # 0.65mm away, DRC-confirmed short of the 0.2mm floor at Power
        # width); shifting the whole column east instead walks into J8's
        # OWN ground-shield pad (a scattered multi-region GND pad, one
        # region right at 31.8875,5.36, only 0.9mm from J8.2 with almost
        # no room for a 0.5mm-wide track between them). The fix is to
        # neck just the final vertical drop to Default width (0.2mm) --
        # halved clearance need fits the 0.3mm window between J8.2's
        # right edge and the shield's left edge, both centered on J8.1's
        # own column.
        _add_track(board, ni_net, pcbnew.B_Cu, [jp4_1, (jp4_1[0], 7.5), (j8_1[0], 7.5)], w_net)
        _add_via(board, ni_net, (j8_1[0], 7.5), via_dia_net, via_drill_net)
        _add_track(board, ni_net, pcbnew.F_Cu, [(j8_1[0], 7.5), j8_1], w_default)

    # VBUS_NET: D_J9_BUSPWR.2 (76.05,50.5, SMD -- F_Cu only) back to the
    # JP1.3 cluster, a long run around P3V3's own sprawling B_Cu tree
    # (which otherwise walls off most of the board's left/middle):
    #   1. F_Cu west a short way, clear of J9_VBUS's and NRESET's local
    #      copper near D_J9_BUSPWR itself.
    #   2. B_Cu north to y=49.2, then a brief F_Cu hop across P3V3's own
    #      east wall (x=67, spans y=33.65-50.5) at x=66.2-67.8 (+-0.8mm,
    #      Power-vs-Power clearance: 0.3 via radius+0.25 P3V3 halfwidth+
    #      0.2 clearance=0.75mm floor). y=49.2 clears J1B's own pad row
    #      (47.8, needs >=1.3mm -- 1.4mm here) AND U_HSW's whole pad
    #      cluster (37.25-39.15) by a wide margin -- an earlier version
    #      used y=39.5, only 0.35mm from U_HSW.4's own 1.325x0.6mm pad,
    #      DRC-confirmed too close (that pad's rectangular half-width,
    #      0.6625mm on the long axis, needs far more room than a simple
    #      0402's would).
    #   3. Continues west on B_Cu to x=33.965 (J1B's own gap between GND/
    #      GP10, 32.695/35.235 -- 1.27mm clear of both), necking to
    #      Default width there (see below) and turning north through
    #      J1B's row (47.8) and PICO's own mirrored row1 (40.89) at that
    #      same gap.
    #   4. North only as far as y=36.0 -- deliberately NOT down into
    #      GP18/GP19/DEV_VBUS_DET/DEV_DP_PU_EN's shared y=42.8-46.58 sweep
    #      band (every one of those runs B_Cu east past x=53, so ANY
    #      vertical crossing that band anywhere east of x=36.5 hits at
    #      least one of them -- DRC-confirmed the hard way) nor down into
    #      I2C0_SCL/SDA/ISENSE/DEV_VBUS_DET's own y=25.0-35.0 eastbound
    #      runs (same issue, one band lower). y=36.0 sits in the one
    #      genuinely empty gap between them.
    #   5. A single F_Cu hop at y=36.0, x=31.0-15.5, clearing I2C0_SCL's
    #      (30.155) and I2C0_SDA's (27.615) verticals AND NRESET's
    #      diagonal (which passes through ~x=24.7 at this y) all at once,
    #      landing west of all three -- pure layer-hop clearance, no
    #      pin-pitch row nearby, so full Power width (Task 14i review fix).
    #   6. B_Cu the rest of the way: to x=16.185 (PICO's own gap between
    #      AREF/GP28, 14.915/17.455 -- NOT x=21.265, DEV_VBUS_DET's own
    #      reserved column, which has a hop-via sitting right at y=35.0),
    #      north to y=9.3 (comfortably north of JP1's whole pin row,
    #      10.655), west to JP1.3's own column, then south onto the pad --
    #      approaching from directly above so it never sweeps past
    #      JP1.1/JP1.2's own Y. Full Power width throughout except two
    #      short Default-width bands where this column crosses PICO row2
    #      (y=23.11) and J2B's mirrored row (y=15.6) (Task 14i review fix).
    ni_dvd_net = ni_net
    d_j9 = _pos(_pad(board, "D_J9_BUSPWR", "2"))
    if not _track_exists(board, ni_dvd_net.GetNetCode(), pcbnew.F_Cu, _mm(*d_j9), _mm(70.0, d_j9[1])):
        _add_track(board, ni_dvd_net, pcbnew.F_Cu, [d_j9, (70.0, d_j9[1])], w_net)
        _add_via(board, ni_dvd_net, (70.0, d_j9[1]), via_dia_net, via_drill_net)
        _add_track(board, ni_dvd_net, pcbnew.B_Cu, [(70.0, d_j9[1]), (70.0, 49.2), (67.8, 49.2)], w_net)
        _add_via(board, ni_dvd_net, (67.8, 49.2), via_dia_net, via_drill_net)
        _add_track(board, ni_dvd_net, pcbnew.F_Cu, [(67.8, 49.2), (66.2, 49.2)], w_net)
        _add_via(board, ni_dvd_net, (66.2, 49.2), via_dia_net, via_drill_net)
        _add_track(board, ni_dvd_net, pcbnew.B_Cu, [(66.2, 49.2), (33.965, 49.2)], w_net)
        # Necks down to Default width (0.2mm, not Power's 0.5mm) for this
        # one leg -- the vertical at x=33.965 has to cross J1B's own row
        # (47.8, 1.7mm PTH pads on a uniform 2.54mm pitch) AND PICO's own
        # row1 (40.89), and its own half-pitch, 1.27mm, is JUST short of
        # the >=1.3mm a Power-class track/via needs from either
        # neighboring pad (DRC-confirmed, every candidate X in the row has
        # the identical shortfall) -- but comfortably clears the
        # >=1.15mm a Default-width track needs, matching this file's
        # established tight-pitch precedent (neck to Default for a short
        # low-current crossing). Everything downstream of here reverts to
        # full Power width except two short bands where the x=16.185
        # vertical (step 6) crosses row2/J2B in turn -- see Task 14i's
        # review-fix comments below.
        _add_track(board, ni_dvd_net, pcbnew.B_Cu,
                   [(33.965, 49.2), (33.965, 36.0), (31.0, 36.0)], w_default)
        _add_via(board, ni_dvd_net, (31.0, 36.0), via_dia_net, via_drill_net)
        # Review fix (Task 14i): this F_Cu hop is pure B_Cu-obstacle
        # clearance (step 5 above -- I2C0_SCL/I2C0_SDA/NRESET) with no
        # pin-pitch row anywhere nearby, unlike the B_Cu leg above (which
        # must stay Default width to cross J1B's row) -- runs at full
        # Power width.
        _add_track(board, ni_dvd_net, pcbnew.F_Cu, [(31.0, 36.0), (15.5, 36.0)], w_net)
        _add_via(board, ni_dvd_net, (15.5, 36.0), via_dia_net, via_drill_net)
        _add_track(board, ni_dvd_net, pcbnew.B_Cu, [(15.5, 36.0), (16.185, 36.0)], w_default)
        # Review fix (Task 14i): the long vertical only needs to neck down
        # to Default width where it actually crosses PICO row2 (23.11),
        # J2B's mirrored row (15.6), or the two other nets' hop-vias
        # (V5J_NECK_MM/SEL_HOP_NECK_MM, see docstring) -- full Power width
        # elsewhere.
        _add_track(board, ni_dvd_net, pcbnew.B_Cu, [(16.185, 36.0), (16.185, V5J_NECK_MM[1])], w_net)
        _add_track(board, ni_dvd_net, pcbnew.B_Cu, [(16.185, V5J_NECK_MM[1]), (16.185, V5J_NECK_MM[0])], w_default)
        _add_track(board, ni_dvd_net, pcbnew.B_Cu, [(16.185, V5J_NECK_MM[0]), (16.185, ROW2_NECK_MM[1])], w_net)
        _add_track(board, ni_dvd_net, pcbnew.B_Cu, [(16.185, ROW2_NECK_MM[1]), (16.185, ROW2_NECK_MM[0])], w_default)
        _add_track(board, ni_dvd_net, pcbnew.B_Cu, [(16.185, ROW2_NECK_MM[0]), (16.185, J2B_NECK_MM[1])], w_net)
        _add_track(board, ni_dvd_net, pcbnew.B_Cu, [(16.185, J2B_NECK_MM[1]), (16.185, J2B_NECK_MM[0])], w_default)
        _add_track(board, ni_dvd_net, pcbnew.B_Cu, [(16.185, J2B_NECK_MM[0]), (16.185, SEL_HOP_NECK_MM[1])], w_net)
        _add_track(board, ni_dvd_net, pcbnew.B_Cu, [(16.185, SEL_HOP_NECK_MM[1]), (16.185, SEL_HOP_NECK_MM[0])], w_default)
        _add_track(board, ni_dvd_net, pcbnew.B_Cu, [(16.185, SEL_HOP_NECK_MM[0]), (16.185, 9.3)], w_net)
        _add_track(board, ni_dvd_net, pcbnew.B_Cu, [(16.185, 9.3), (jp1_3[0], 9.3), jp1_3], w_default)

    # V5_JTRACE: JP1.1 (9.96,10.655) -> J3.11 (already has a short F_Cu
    # stub from its own side, 15.525,61.15 -> 16.795,61.15). J3.11 sits
    # deep inside the trace-bundle corridor (x 4.035-20.605); the whole
    # route stays Default width (the corridor gaps are too tight for
    # Power) and, whenever x is inside the corridor's own x-range, keeps
    # y either <27.5 (well north of the bundle's y=40.89 start) or
    # >57.25 (south of the bundle's whole footprint, past J3's own row1)
    # -- B_Cu is never present in the corridor for 27.5<=y<=57.25 at
    # x<20.605, matching the hard "B_Cu out of the corridor" rule.
    #   1. South at x=11.105 (PICO's own gap between P3V3_EN/P3V3,
    #      9.835/12.375), hopping VBUS_SEL's local tap (12.5,13.0)-
    #      (4.0,13.0) and P3V3's own diagonal (12.375,23.11->3.485,39.79,
    #      crosses x=11.105 around y=25.5) along the way.
    #   2. East at y=27.5 (still north of the corridor), hopping
    #      VBUS_NET's x=16.185 column and NRESET's diagonal + I2C0_SDA's
    #      vertical (both land around x=26-28) to reach x=28.885 (J1B's
    #      own I2C0_SDA/I2C0_SCL gap, 27.615/30.155).
    #   3. South through row1 (40.89) and J1B (47.8) at that same gap
    #      (x=28.885 is >20.605, outside the corridor's x-range, so this
    #      whole descent -- through the corridor's y-band too -- never
    #      needs the B_Cu-out-of-corridor rule at all) down to y=56.0,
    #      then west to x=22.0 -- still east of the corridor, hopping
    #      NRESET's own PICO-descent vertical (x=23.805) along the way.
    #   4. A last hop at x=22.0 (still >20.605) crossing SWDIO+NRESET's
    #      trunk (58.8/59.42) together, landing at y=60.0 -- already
    #      south of the trunk and north of J3's row2 (61.15).
    #   5. Only now (y>57.25, clear of the corridor's whole footprint)
    #      does the path cross into x<20.605: west at y=61.4 to
    #      x=15.525, then a final via + short F_Cu approach onto J3.11
    #      (SMD, F_Cu only).
    w_v5, via_dia_v5, via_drill_v5 = power_via("V5_JTRACE")
    ni_v5 = _net(board, "V5_JTRACE")
    jp1_1 = _pos(_pad(board, "JP1", "1"))
    if not _track_exists(board, ni_v5.GetNetCode(), pcbnew.B_Cu, _mm(*jp1_1), _mm(11.105, jp1_1[1])):
        _add_track(board, ni_v5, pcbnew.B_Cu, [jp1_1, (11.105, jp1_1[1]), (11.105, 12.15)], w_default)
        _add_via(board, ni_v5, (11.105, 12.15), via_dia_v5, via_drill_v5)
        # One continuous F_Cu run past both VBUS_SEL's Power-class tap
        # (y=13.0) and P3V3's own diagonal (12.375,23.11->3.485,39.79) --
        # both are B_Cu, so the F_Cu track itself needs no clearance from
        # either; only the two transition vias do, and DRC confirmed the
        # via-vs-diagonal perpendicular distance at this x (11.105) is
        # <0.75mm (Power via clearance) for any y in [23.9,27.09], so the
        # exit via has to clear that whole band, not just the diagonal's
        # own line -- landing at 27.5 (already needed for the next hop)
        # clears it with margin.
        _add_track(board, ni_v5, pcbnew.F_Cu, [(11.105, 12.15), (11.105, 27.5)], w_default)
        _add_via(board, ni_v5, (11.105, 27.5), via_dia_v5, via_drill_v5)
        _add_track(board, ni_v5, pcbnew.B_Cu,
                   [(11.105, 27.5), (15.5, 27.5)], w_default)
        _add_via(board, ni_v5, (15.5, 27.5), via_dia_v5, via_drill_v5)
        _add_track(board, ni_v5, pcbnew.F_Cu, [(15.5, 27.5), (16.9, 27.5)], w_default)
        _add_via(board, ni_v5, (16.9, 27.5), via_dia_v5, via_drill_v5)
        _add_track(board, ni_v5, pcbnew.B_Cu, [(16.9, 27.5), (25.9, 27.5)], w_default)
        _add_via(board, ni_v5, (25.9, 27.5), via_dia_v5, via_drill_v5)
        _add_track(board, ni_v5, pcbnew.F_Cu, [(25.9, 27.5), (28.3, 27.5)], w_default)
        _add_via(board, ni_v5, (28.3, 27.5), via_dia_v5, via_drill_v5)
        _add_track(board, ni_v5, pcbnew.B_Cu,
                   [(28.3, 27.5), (28.885, 27.5), (28.885, 56.0), (24.6, 56.0)], w_default)
        _add_via(board, ni_v5, (24.6, 56.0), via_dia_v5, via_drill_v5)
        _add_track(board, ni_v5, pcbnew.F_Cu, [(24.6, 56.0), (23.0, 56.0)], w_default)
        _add_via(board, ni_v5, (23.0, 56.0), via_dia_v5, via_drill_v5)
        _add_track(board, ni_v5, pcbnew.B_Cu,
                   [(23.0, 56.0), (22.0, 56.0), (22.0, 58.15)], w_default)
        _add_via(board, ni_v5, (22.0, 58.15), via_dia_v5, via_drill_v5)
        _add_track(board, ni_v5, pcbnew.F_Cu, [(22.0, 58.15), (22.0, 60.1)], w_default)
        _add_via(board, ni_v5, (22.0, 60.1), via_dia_v5, via_drill_v5)
        _add_track(board, ni_v5, pcbnew.B_Cu,
                   [(22.0, 60.1), (22.0, 61.4), (15.525, 61.4)], w_default)
        # J3.11 is SMD (F_Cu only, unlike every THT connector elsewhere
        # in this file) -- needs a via before the final short approach.
        _add_via(board, ni_v5, (15.525, 61.4), via_dia_v5, via_drill_v5)
        _add_track(board, ni_v5, pcbnew.F_Cu, [(15.525, 61.4), (15.525, 61.15)], w_default)

    # VBUS_SEL: U_INA219_ALT.1 -> R_SHUNT.1 -> U_ISNS.3 (63.4625,35.55,
    # already same-net F_Cu, part of the pre-existing local cluster) ->
    # the JP1.2/R_LED_PWR cluster. isns3 is already NORTH of PICO's row1
    # (40.89) and J1B (47.8) -- unlike VBUS_NET/V5_JTRACE this leg never
    # needs to cross either of those rows at all, so it stays north
    # throughout instead of detouring south around P3V3's east wall.
    #   1. via at isns3 (F_Cu->B_Cu), then B_Cu straight to y=34.4 -- NOT
    #      35.55 unchanged, since DEV_VBUS_DET's own east-west run sits
    #      right at y=35.0 (x=21.265-39.045, plus a vertical spur at
    #      x=39.045 continuing to y=42.8) and U_HSW.1's pad/via sits at
    #      (63.3625,37.25), only 0.1mm off isns3's own x -- y=34.4 clears
    #      both (0.6mm north of DEV_VBUS_DET's line, and moving away from
    #      U_HSW entirely).
    #   2. B_Cu west at that same y=34.4 to x=31.425 (I2C0_SCL/GND's own
    #      gap, 30.155/32.695 -- NOT x=33.965, VBUS_NET's own reserved
    #      column). GP10's and UART0_TX's F_Cu descents (x=33.965/39.045)
    #      and DEV_VBUS_DET's B_Cu vertical spur (x=39.045, y>=35.0) are
    #      all crossed for free -- the F_Cu ones via layer separation, the
    #      B_Cu spur because y=34.4 is north of its y=35.0 start. The
    #      DEV_VBUS_DET hop-via at (30.855,35.0) is close (dx=0.57) but
    #      the path turns south at x=31.425 before ever reaching x=30.855,
    #      so the real (dx,dy) distance to that via is 0.83mm, not 0.57 --
    #      an earlier version that dipped down to y=35.0 exactly at
    #      x=31.425 (to "cross" the line before turning) put a via
    #      directly in that via's 0.75mm danger circle; approaching at a
    #      constant y clear of the line instead needs no such dip.
    #   3. Continue south on x=31.425 through row2 (23.11) -- but a brief
    #      F_Cu hop first, y=27.4-24.4, clears I2C0_SCL/I2C0_SDA/ISENSE's
    #      own eastbound runs (y=26.6/26.0/25.0, all reaching x=55-60,
    #      well past 31.425) all at once.
    #   4. B_Cu the rest of the way: south through row2 and J2B (both via
    #      the same I2C0_SCL/GND gap, 1.27mm clear of each), to y=13.0
    #      (matching the existing JP1.2->R_LED_PWR cluster's own y), then
    #      a brief F_Cu hop over VBUS_NET's x=16.185 column before landing
    #      on the existing B_Cu run at (12.5,13.0).
    w_sel2, via_dia_sel2, via_drill_sel2 = power_via("VBUS_SEL")
    ni_sel2 = _net(board, "VBUS_SEL")
    isns3 = _pos(_pad(board, "U_ISNS", "3"))
    if not _track_exists(board, ni_sel2.GetNetCode(), pcbnew.B_Cu, _mm(*isns3), _mm(63.4625, 34.4)):
        _add_via(board, ni_sel2, isns3, via_dia_sel2, via_drill_sel2)
        _add_track(board, ni_sel2, pcbnew.B_Cu,
                   [isns3, (63.4625, 34.4), (31.425, 34.4), (31.425, 27.4)], w_sel2)
        _add_via(board, ni_sel2, (31.425, 27.4), via_dia_sel2, via_drill_sel2)
        _add_track(board, ni_sel2, pcbnew.F_Cu, [(31.425, 27.4), (31.425, 24.4)], w_sel2)
        _add_via(board, ni_sel2, (31.425, 24.4), via_dia_sel2, via_drill_sel2)
        # Necks to Default width for the same reason as VBUS_NET's own
        # final approach above -- the row2/J2B gap crossing (1.27mm each
        # side) is short of what a Power-class track needs. Review fix
        # (Task 14i): only the two short bands actually crossing row2/J2B
        # need the neck -- the rest of the vertical, and the y=13.0
        # horizontal run (clear of both rows), go back to full Power
        # width.
        _add_track(board, ni_sel2, pcbnew.B_Cu, [(31.425, 24.4), (31.425, ROW2_NECK_MM[1])], w_sel2)
        _add_track(board, ni_sel2, pcbnew.B_Cu, [(31.425, ROW2_NECK_MM[1]), (31.425, ROW2_NECK_MM[0])], w_default)
        _add_track(board, ni_sel2, pcbnew.B_Cu, [(31.425, ROW2_NECK_MM[0]), (31.425, J2B_NECK_MM[1])], w_sel2)
        _add_track(board, ni_sel2, pcbnew.B_Cu, [(31.425, J2B_NECK_MM[1]), (31.425, J2B_NECK_MM[0])], w_default)
        _add_track(board, ni_sel2, pcbnew.B_Cu,
                   [(31.425, J2B_NECK_MM[0]), (31.425, 13.0), (17.0, 13.0)], w_sel2)
        _add_via(board, ni_sel2, (17.0, 13.0), via_dia_sel2, via_drill_sel2)
        _add_track(board, ni_sel2, pcbnew.F_Cu, [(17.0, 13.0), (15.5, 13.0)], w_default)
        _add_via(board, ni_sel2, (15.5, 13.0), via_dia_sel2, via_drill_sel2)
        _add_track(board, ni_sel2, pcbnew.B_Cu, [(15.5, 13.0), (12.5, 13.0)], w_default)


def _widen_vbus_net(board):
    """Task 15a: VBUS_NET was left at Default width (0.2mm) over two legs
    Task 14i's power-trace widening pass (see its docstring above, and
    task-14i-report.md) never touched: the whole PICO.40->JP1.3 leg (a
    separate function, `_route_pico_no_jog`) and the x=33.965 vertical's
    full 13.2mm span in `_route_final_long_runs` (deliberately left
    narrow there, unsplit). Task 14i's rationale treated VBUS_NET as only
    carrying the Pico's own 100-300mA; it does not -- JP1.3 sits on
    VBUS_NET, so selecting USB on JP1 ties VBUS_SEL and VBUS_NET into the
    same node, carrying the combined 650-760mA worst case VBUS_SEL was
    already widened for. This mutates the existing Default-width track
    objects in place (`SetWidth`/`SetStart`/`SetEnd` -- never
    `BOARD.Remove()`), splitting only the one leg that crosses two pad
    rows (J1B's row, y=47.8, and PICO's row1, y=40.89) into narrow-at-
    crossing/wide-elsewhere bands, +-0.6mm half-width -- the same margin
    already proven for J2B_HOP/ROW1_HOP (a via's own clearance need,
    conservative for a bare track). DRC-verified clean (task-15-report.md).
    The J8 final-drop neck and the four already-established via/row
    crossing neck bands (ROW2_HOP, J2B_HOP, V5J_NECK_MM, SEL_HOP_NECK_MM)
    are untouched -- still genuine clearance-forced pinch points, same
    reasoning as VBUS_SEL's own remaining necks.

    Idempotent: every segment is located by its known (start, end)
    coordinates; a second run finds the already-widened/split geometry
    and no-ops (the pre-split full-span track no longer exists once
    shrunk, so its `find()` returns None)."""
    ni = _net(board, "VBUS_NET")
    nc = ni.GetNetCode()
    w_net = _class_width(board, "VBUS_NET")
    w_default = pcbnew.ToMM(
        board.GetDesignSettings().m_NetSettings.GetDefaultNetclass().GetTrackWidth()
    )

    def find(layer, p0, p1):
        for t in board.GetTracks():
            if t.GetClass() == "PCB_VIA" or t.GetNetCode() != nc or t.GetLayer() != layer:
                continue
            s, e = t.GetStart(), t.GetEnd()
            if (s == p0 and e == p1) or (s == p1 and e == p0):
                return t
        return None

    # Simple full-widen: DRC-confirmed no obstacle within Power-class
    # clearance of any of these at 0.5mm -- left at Default width
    # incidentally (not for a genuine clearance reason).
    for x0, y0, x1, y1 in [
        (2.215, 23.11, 2.215, 8.0),     # PICO.40 vertical
        (2.215, 8.0, 15.04, 8.0),       # peel-off row north of JP1
        (15.04, 8.0, 15.04, 10.655),    # JP1.3 final approach (PICO.40 leg)
        (15.04, 9.3, 15.04, 10.655),    # JP1.3 final approach (D_J9_BUSPWR leg)
        (16.185, 9.3, 15.04, 9.3),      # D_J9_BUSPWR leg's westward jog
        (33.965, 36.0, 31.0, 36.0),     # D_J9_BUSPWR leg's row-gap exit
        (15.5, 36.0, 16.185, 36.0),     # F_Cu/B_Cu layer-hop stub
    ]:
        t = find(pcbnew.B_Cu, _mm(x0, y0), _mm(x1, y1))
        if t is not None and pcbnew.ToMM(t.GetWidth()) < w_net:
            t.SetWidth(pcbnew.FromMM(w_net))

    # x=33.965 vertical (49.2->36.0): crosses J1B's row (47.8) AND PICO's
    # row1 (40.89) -- split into wide/narrow/wide/narrow/wide.
    j1b_lo, j1b_hi = 47.8 - 0.6, 47.8 + 0.6
    row1_lo, row1_hi = 40.89 - 0.6, 40.89 + 0.6
    p_top, p_bot = _mm(33.965, 49.2), _mm(33.965, 36.0)
    full = find(pcbnew.B_Cu, p_top, p_bot)
    if full is not None:
        full.SetStart(p_top)
        full.SetEnd(_mm(33.965, j1b_hi))
        full.SetWidth(pcbnew.FromMM(w_net))
        _add_track(board, ni, pcbnew.B_Cu, [(33.965, j1b_hi), (33.965, j1b_lo)], w_default)
        _add_track(board, ni, pcbnew.B_Cu, [(33.965, j1b_lo), (33.965, row1_hi)], w_net)
        _add_track(board, ni, pcbnew.B_Cu, [(33.965, row1_hi), (33.965, row1_lo)], w_default)
        _add_track(board, ni, pcbnew.B_Cu, [(33.965, row1_lo), (33.965, 36.0)], w_net)


def main():
    """Task 14f scope actually completed: trace bundle, guard nets, the
    SWD/NRESET/P3V3(VTref) tree, breakout stubs, and internal ties -- all
    DRC-clean (see .superpowers/sdd/task-14f-report.md). The rest of
    Task 14f's non-GND nets (power tree, USB legs, dividers, misc GPIO --
    65 pad-pairs) were attempted but not brought to a DRC-clean state in
    the time available and are intentionally NOT included here; see that
    report for the exact remaining pairs and lessons for a follow-up
    pass. GND stays unrouted throughout for Task 15's pour."""
    b = pcbnew.LoadBoard(BOARD_FILE)
    assert b is not None, f"LoadBoard({BOARD_FILE!r}) returned None"

    _route_trace_bundle(b)
    _route_swd_tree(b)
    _route_j10_taps(b)

    _route_breakout_stubs(b)
    _route_internal_ties(b)

    _route_local_ties(b)
    _route_vbus_sel_5v_ladder(b)
    _route_power_cluster_bcu(b)
    _route_i2c0_stemma_bcu(b)
    _route_dev_dp_esd_j9(b)
    _route_j9_vbus_esd_tap(b)
    _route_cluster_leftovers(b)
    _route_pico_no_jog(b)
    _route_pico_row_jog(b)
    _route_final_long_runs(b)
    _widen_vbus_net(b)

    pcbnew.SaveBoard(BOARD_FILE, b)
    pcbnew.GetSettingsManager().SaveProject()
    print(f"routed: tracks={len(list(b.GetTracks()))}")


if __name__ == "__main__":
    main()
