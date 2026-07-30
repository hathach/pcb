"""pcbnew driver: bottom + top GND pour and stitching vias (Task 15b).

Run: python3 hw/pour.py            # geometry only (zones, overrides, vias) -- no fill
     python3 hw/pour.py --fill     # fill the zones (MUST be its own process, see below)

GND is unrouted by design through Task 14 (~67 GND unconnected items) --
the pour carries it. This adds:

  - A B_Cu `GND` zone and an F_Cu `GND` zone, each covering the whole
    board, outline inset 0.3mm from Edge.Cuts (copper-to-edge clearance).
    F_Cu fragments around the existing top-layer routing -- expected.
  - Pad connection mode `ZONE_CONNECTION_THT_THERMAL` ("thermal reliefs
    for PTH only"): every THT GND pad gets 4 spokes (hand-solder
    friendly -- Pico socket, J1B/J2B, JP1-4, J_UART, J10, TP3), every SMD
    GND pad gets a solid connection (better for small reflow pads, no
    hand-soldering concern).
  - `_SOLID_OVERRIDE_PADS`: 4 THT pads where even a full 4-spoke thermal
    relief can't reach 2 spokes (DRC `starved_thermal`) because a
    Power-class track/via sits in the one open direction their 2.54mm
    row pitch leaves free -- forced to solid (electrical reliability
    over solder-ease for these 4 alone; every other THT GND pad keeps
    real thermal relief).
  - `_GND_STUBS` + their vias: 6 short hand-routed GND links for pads
    the zone fill geometrically cannot reach at all -- sub-0.2mm-clearance
    SMD pin pitch (U_INA219_ALT, U_ISNS) or a 1.27mm MIPI-20 connector
    row (J3) with no room for a via at any size, or two THT pads on the
    Task-14i VBUS_NET/J1B/PICO-row corridor (`x=45.395`) that the zone
    fill's own row-crossing necks isolate from each other.
  - Stitching vias tying F_Cu and B_Cu together: a ring around the
    trace-corridor bbox (x[4.035,20.605] y[40.89,57.25]) kept OUTSIDE it
    (perimeter, not interior -- the corridor's own bottom reference must
    stay unbroken), plus a board-wide spread, plus per-fragment fixes
    (every zone island not already touching a via/THT pad -- see
    `python3 -m hw.pour --fill` + task-15-report.md for how these were
    found: `ZONE.GetFilledPolysList()` outline-by-outline, skip the
    largest per layer, `SHAPE_LINE_CHAIN.PointInside()` to place a via
    inside each remainder).

Fill gotcha (verified, see PLAN.md's "Verified environment facts"):
`ZONE_FILLER(b).Fill()` segfaults on an in-memory-mutated board -- only
ever call it immediately after a fresh `LoadBoard`, in its own process.
`main()` (geometry) and `fill_zones()` (fill) are therefore two separate
entry points, never called from the same board object.

Idempotent throughout: `_add_gnd_zone` skips if a GND zone already
exists on that layer; `_apply_solid_overrides` sets are naturally
idempotent (same value twice is a no-op); `_add_gnd_stubs` uses the
`hw.route_trace` `_track_exists` skip-if-present check; `_add_stitching_vias`
skips any position (0.01mm tolerance) that already has a GND via. Never
`BOARD.Remove()` (see build_board.py's docstrings for why).
"""

from __future__ import annotations

import math
import os
import sys

if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pcbnew

from hw.route_trace import _add_track, _mm, _net, _track_exists

BOARD_FILE = "pico2_trace.kicad_pcb"

# --- Board outline geometry (hw/build_board.py's _draw_outline): rounded
# rect x:[0,92] y:[0,64], corner radius 3mm. Inset 0.3mm for copper-to-edge.
_BOARD_X0, _BOARD_Y0, _BOARD_X1, _BOARD_Y1, _BOARD_R = 0.0, 0.0, 92.0, 64.0, 3.0
_EDGE_INSET_MM = 0.3


def _rounded_rect_pts(x0, y0, x1, y1, r, segs_per_corner=16):
    """Points (mm), matching Edge.Cuts' own corner convention (each corner
    a quarter-circle radius r, traced clockwise: top-left, top-right,
    bottom-right, bottom-left)."""
    pts = []
    corners = [
        (x0 + r, y0 + r, 180, 270),
        (x1 - r, y0 + r, 270, 360),
        (x1 - r, y1 - r, 0, 90),
        (x0 + r, y1 - r, 90, 180),
    ]
    for cx, cy, a0, a1 in corners:
        for i in range(segs_per_corner + 1):
            a = math.radians(a0 + (a1 - a0) * i / segs_per_corner)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def _gnd_outline_pts():
    return _rounded_rect_pts(
        _BOARD_X0 + _EDGE_INSET_MM, _BOARD_Y0 + _EDGE_INSET_MM,
        _BOARD_X1 - _EDGE_INSET_MM, _BOARD_Y1 - _EDGE_INSET_MM,
        _BOARD_R - _EDGE_INSET_MM,
    )


_THERMAL_GAP_MM = 0.25
_THERMAL_SPOKE_MM = 0.35
_ZONE_MIN_THICKNESS_MM = 0.2


def _add_gnd_zone(board, layer):
    ni = board.FindNet("GND")
    for z in board.Zones():
        if z.GetLayer() == layer and z.GetNetname() == "GND":
            return z  # idempotent: already present
    z = pcbnew.ZONE(board)
    z.SetLayer(layer)
    z.SetNet(ni)
    z.SetZoneName("GND_" + board.GetLayerName(layer))
    outline = pcbnew.VECTOR_VECTOR2I()
    for x, y in _gnd_outline_pts():
        outline.append(_mm(x, y))
    z.AddPolygon(outline)
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_THT_THERMAL)
    z.SetThermalReliefGap(pcbnew.FromMM(_THERMAL_GAP_MM))
    z.SetThermalReliefSpokeWidth(pcbnew.FromMM(_THERMAL_SPOKE_MM))
    z.SetMinThickness(pcbnew.FromMM(_ZONE_MIN_THICKNESS_MM))
    z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    board.Add(z)
    return z


# 4 THT GND pads DRC-confirmed `starved_thermal` (fewer than the 2-spoke
# minimum) under normal thermal relief -- see module docstring. Forced solid.
# Plus J1B.3/J1B.8: with thermal relief, the whole J1B row's clearance/
# thermal-gap ring (10 pads at 2.54mm pitch, spanning the full trace-
# corridor width) pinches the B_Cu pour into two disjoint islands north
# and south of y=47.8, breaking the corridor's continuous bottom
# reference; solid at just these 2 GND columns restores one unbroken
# region the whole corridor length (verified: every TRACECLK/TD0-3/GP1-5
# sample point now lands in the same B_Cu outline).
_SOLID_OVERRIDE_PADS = [
    ("PICO", "13"), ("J1B", "13"), ("PICO", "28"), ("JP2", "2"),
    ("J1B", "3"), ("J1B", "8"),
]


def _apply_solid_overrides(board):
    for ref, num in _SOLID_OVERRIDE_PADS:
        for fp in board.GetFootprints():
            if fp.GetReference() != ref:
                continue
            for pad in fp.Pads():
                if pad.GetNumber() == num:
                    pad.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)


# Hand-routed GND links for pads the zone fill cannot reach at all --
# each entry: (layer, (x0,y0), (x1,y1), width_mm). See module docstring.
_GND_STUBS = [
    # U_INA219_ALT.3 <-> open F_Cu (0.65mm-pitch pins, west column clear).
    ("F.Cu", (62.6375, 27.975), (61.6, 27.975), 0.2),
    # U_INA219_ALT.7 <-> open F_Cu (same package, east column clear).
    ("F.Cu", (60.3625, 28.625), (61.3, 28.625), 0.2),
    # J2B.3 <-> PICO.23: shared column x=45.395, clear the whole span.
    ("F.Cu", (45.395, 15.6), (45.395, 23.11), 0.2),
    # PICO.23 <-> PICO.18: same column, extends the link across row1.
    ("F.Cu", (45.395, 23.11), (45.395, 40.89), 0.2),
    # U_ISNS.2 <-> open F_Cu east of its 0.95mm-pitch column.
    ("F.Cu", (63.462, 34.6), (65.25, 34.65), 0.2),
    # J3.9 (MIPI-20, 1.27mm pitch) <-> a via placed essentially in-pad --
    # the only spot standard board-minimum via clearance (0.5mm dia)
    # allows this close to the connector's own tight pitch.
    ("F.Cu", (14.255, 61.15), (14.3, 61.2), 0.2),
    # PICO.3/J1B.3's own local F_Cu+B_Cu pocket (bbox inside the trace
    # corridor) isn't reached by the wider pour -- escapes north, just
    # outside the corridor bbox (y<40.89), to a legal via spot instead
    # of stitching the corridor interior.
    ("F.Cu", (7.295, 40.89), (7.295, 39.5), 0.2),
]

_LAYER_MAP = {"F.Cu": pcbnew.F_Cu, "B.Cu": pcbnew.B_Cu}


def _add_gnd_stubs(board):
    ni = _net(board, "GND")
    for layer_name, p0, p1, width_mm in _GND_STUBS:
        layer = _LAYER_MAP[layer_name]
        if _track_exists(board, ni.GetNetCode(), layer, _mm(*p0), _mm(*p1)):
            continue
        _add_track(board, ni, layer, [p0, p1], width_mm)


# Standard stitching vias (0.6mm dia / 0.3mm drill, matching the rest of
# the board's via convention) -- three groups, all GND:
#   - ring: around the trace-corridor bbox (x[4.035,20.605] y[40.89,57.25]),
#     kept OUTSIDE it so the corridor's own bottom reference stays
#     unbroken (perimeter, not interior).
#   - fragment-fix: one via inside each zone-fill island (both layers)
#     that didn't already contain a via or THT GND pad (found via
#     `ZONE.GetFilledPolysList()` + `SHAPE_LINE_CHAIN.PointInside()`).
#   - spread: a coarse (8mm) grid across the rest of the board, collision-
#     filtered against every non-GND pad/track/via with a 3mm min via-via
#     spacing and comfortable board-edge/corner clearance.
_STITCH_VIAS_RING = [
    (5.535, 39.39), (9.035, 39.39), (12.535, 39.39), (16.035, 39.39), (19.535, 39.39),
    (5.535, 61.75), (19.535, 60.25), (3.035, 56.25),
    (21.605, 42.39), (21.605, 45.89), (21.605, 49.39),
]

#   NOTE: the fragment near PICO.3/J1B.3 (bbox ~x[5.4,9.2] y[40.9,46.8])
#   is fixed via a `_GND_STUBS` escape track instead of a via here --
#   its whole extent sits inside the trace-corridor bbox, and a via
#   there would violate "stitch the perimeter, not the interior".
_STITCH_VIAS_FRAGMENT_FIX = [
    (19.995, 19.434), (45.545, 41.878), (44.925, 16.787),
    (63.3, 12.032), (10.332, 59.696), (51.617, 60.296), (79.751, 46.451),
    (73.401, 44.7), (23.805, 19.434), (18.935, 23.408), (26.345, 51.901),
]

_STITCH_VIAS_SPREAD = [
    (6.0, 6.0), (6.0, 14.0), (6.0, 22.0), (6.0, 30.0),
    (14.0, 6.0), (14.0, 14.0), (14.0, 30.0),
    (22.0, 6.0), (22.0, 14.0), (22.0, 54.0),
    (30.0, 14.0), (30.0, 54.0),
    (38.0, 6.0), (38.0, 14.0), (38.0, 30.0), (41.0, 38.0), (38.0, 54.0),
    (46.0, 54.0),
    (54.0, 22.0), (54.0, 30.0), (54.0, 38.0), (54.0, 54.0),
    (62.0, 6.0), (62.0, 38.0), (62.0, 54.0),
    (70.0, 6.0), (70.0, 14.0), (70.0, 30.0), (70.0, 38.0), (70.0, 54.0),
    (78.0, 6.0), (78.0, 14.0), (78.0, 22.0), (78.0, 30.0), (78.0, 38.0), (78.0, 54.0),
    (86.0, 6.0), (86.0, 14.0), (86.0, 22.0), (86.0, 30.0), (86.0, 38.0), (86.0, 54.0),
]

# Pad-escape vias for three of the `_GND_STUBS` above (U_INA219_ALT.3/.7,
# PICO.3/J1B.3's corridor-adjacent pocket) -- standard 0.6mm size, just
# not part of the ring/fragment-fix/spread groups since they exist to
# land a stub track, not to stitch a fragment.
_STITCH_VIAS_PAD_ESCAPE = [(61.6, 27.975), (61.3, 28.625), (7.295, 39.5)]

_STITCH_VIA_DIA_MM = 0.6
_STITCH_VIA_DRILL_MM = 0.3

# Pad-escape vias paired with two of the `_GND_STUBS` above, sized to the
# board's DRC-enforced minimum (0.5mm dia / 0.3mm drill) -- the standard
# 0.6mm via does not clear the tight copper around U_ISNS.2 / J3.9 even
# from their own stub tracks' landing points.
_STITCH_VIAS_MIN_SIZE = [(14.3, 61.2), (65.25, 34.65)]
_MIN_VIA_DIA_MM = 0.5
_MIN_VIA_DRILL_MM = 0.3


def _has_gnd_via(board, gnd_netcode, x, y, tol=0.01):
    for t in board.GetTracks():
        if isinstance(t, pcbnew.PCB_VIA) and t.GetNetCode() == gnd_netcode:
            p = t.GetPosition()
            if abs(pcbnew.ToMM(p.x) - x) < tol and abs(pcbnew.ToMM(p.y) - y) < tol:
                return True
    return False


def _add_via_at(board, ni, x, y, dia_mm, drill_mm):
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(_mm(x, y))
    v.SetViaType(pcbnew.VIATYPE_THROUGH)
    v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    v.SetWidth(pcbnew.F_Cu, pcbnew.FromMM(dia_mm))
    v.SetDrill(pcbnew.FromMM(drill_mm))
    v.SetNet(ni)
    board.Add(v)


def _add_stitching_vias(board):
    ni = _net(board, "GND")
    nc = ni.GetNetCode()
    all_std = (_STITCH_VIAS_RING + _STITCH_VIAS_FRAGMENT_FIX + _STITCH_VIAS_SPREAD
               + _STITCH_VIAS_PAD_ESCAPE)
    for x, y in all_std:
        if _has_gnd_via(board, nc, x, y):
            continue
        _add_via_at(board, ni, x, y, _STITCH_VIA_DIA_MM, _STITCH_VIA_DRILL_MM)
    for x, y in _STITCH_VIAS_MIN_SIZE:
        if _has_gnd_via(board, nc, x, y):
            continue
        _add_via_at(board, ni, x, y, _MIN_VIA_DIA_MM, _MIN_VIA_DRILL_MM)


def add_pour(board):
    _add_gnd_zone(board, pcbnew.B_Cu)
    _add_gnd_zone(board, pcbnew.F_Cu)
    _apply_solid_overrides(board)
    _add_gnd_stubs(board)
    _add_stitching_vias(board)


def main():
    b = pcbnew.LoadBoard(BOARD_FILE)
    assert b is not None, f"LoadBoard({BOARD_FILE!r}) returned None"
    add_pour(b)
    pcbnew.SaveBoard(BOARD_FILE, b)
    gnd_nc = b.GetNetcodeFromNetname("GND")
    n_vias = sum(1 for t in b.GetTracks() if isinstance(t, pcbnew.PCB_VIA) and t.GetNetCode() == gnd_nc)
    print(f"pour: zones={len(list(b.Zones()))} gnd_vias={n_vias}")


def fill_zones():
    """MUST be its own process/fresh LoadBoard -- ZONE_FILLER.Fill()
    segfaults on an in-memory-mutated board (verified gotcha)."""
    b = pcbnew.LoadBoard(BOARD_FILE)
    assert b is not None, f"LoadBoard({BOARD_FILE!r}) returned None"
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    pcbnew.SaveBoard(BOARD_FILE, b)
    print("filled")


if __name__ == "__main__":
    if "--fill" in sys.argv:
        fill_zones()
    else:
        main()
