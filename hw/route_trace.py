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
# (SWCLK is shallow and spans wider -- J3/J4/J6/J7 -- so keeping it
# shallow means P3V3, which only touches J3/J6, needs just a single hop
# where its J6 spike must pass SWCLK's line).
_SWD_TREE = {
    "SWDIO": [("J3", "2"), ("J4", "3"), ("J6", "2"), ("J7", "3")],
    "SWCLK": [("J3", "4"), ("J4", "1"), ("J6", "4"), ("J7", "1")],
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
_ROW_CLEAR_Y = 58.90     # south of J3/J4/J6/J7's north-row pad bottom
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
    """B_Cu trunk at _SWD_LANE_Y[net_name], via-per-node (J3/J4/J6/J7/SW1
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
    """SWCLK: plain F_Cu throughout, no vias -- J3/J4/J6/J7 pads are all
    F_Cu-only SMD. Skips the tight inter-row gap (SWDIO/NRESET's B_Cu
    territory -- different layer, so no clearance conflict either way,
    but the gap has no room left regardless) and descends straight to
    the south-of-south-row band (_SWD_LANE_Y['SWCLK'], the *shallow* F_Cu
    lane -- P3V3 hops over it, see _route_p3v3_swd). J3/J6's columns
    (10.445/51.13) sit directly above a south-row GND pad at the *same*
    x, so those two nodes jog to a connector-clear column
    (_SWCLK_ESCAPE_X) while still between the rows (open, unconstrained
    by row pad pitch) before continuing down; J4/J7 are simple single-row
    headers with nothing blocking below, so they descend directly."""
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

    _route_breakout_stubs(b)
    _route_internal_ties(b)

    pcbnew.SaveBoard(BOARD_FILE, b)
    pcbnew.GetSettingsManager().SaveProject()
    print(f"routed: tracks={len(list(b.GetTracks()))}")


if __name__ == "__main__":
    main()
