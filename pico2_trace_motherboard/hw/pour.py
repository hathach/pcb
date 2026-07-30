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
    # Task 18: D_VSYS's new VBUS_SEL leg crosses J2B's row through the
    # pad37/pad38 half-pitch gap, right next to J2B.18 -- DRC-confirmed
    # `starved_thermal` (down to 1 spoke) under normal thermal relief.
    ("J2B", "18"),
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
    # U_ISNS.2 <-> open F_Cu east of its 0.95mm-pitch column. Task 16:
    # endpoint nudged +0.25mm east (65.25->65.50) together with its via --
    # see the via-position comment below for why "east" (not the brief's
    # "west") is the direction with real DRC margin.
    ("F.Cu", (63.462, 34.6), (65.50, 34.65), 0.2),
    # J3.9 (MIPI-20, 1.27mm pitch) <-> a via placed essentially in-pad --
    # the only spot close to the connector's own tight pitch; same-net as
    # the pad it lands in, so pad clearance doesn't apply (Task 16: grown
    # to the board's standard 0.6mm/0.3mm size, DRC-clean up to >=1.2mm).
    ("F.Cu", (14.255, 61.15), (14.3, 61.2), 0.2),
    # PICO.3/J1B.3's own local F_Cu+B_Cu pocket (bbox inside the trace
    # corridor) isn't reached by the wider pour -- escapes north, just
    # outside the corridor bbox (y<40.89), to a legal via spot instead
    # of stitching the corridor interior.
    ("F.Cu", (7.295, 40.89), (7.295, 39.5), 0.2),
    # Task 18: bridges the B.Cu orphan pair (F.17/B.16, see
    # _STITCH_VIAS_FRAGMENT_FIX's (52.28,32.0)... (45.39,32.0) comment --
    # that via unions F.17<->B.16 but neither reaches the main GND network
    # on its own) to B.15/the main plane. A proper union-find over ALL
    # GND copper (vias union F<->B; GND tracks union same-layer; THT/
    # plated PADS union everything they touch, bridging layers too) found
    # this as the remaining gap -- "every island has a via" is NOT the
    # same test; an island can have a via and still be isolated if that
    # via's other-layer landing spot is itself isolated. See
    # task-18-report.md's "Correct future check" section.
    #
    # Direct paths all failed DRC clearance (checked programmatically,
    # not by eye, against every non-GND track/via/pad on the crossed
    # layer): BTN_USER's F.Cu track at y=13.8 (x 46.665-66.0) blocks from
    # the north; J2B.1/NATIVE_VBUS_DET's own pad+F.Cu column at
    # (50.475,15.6)/x=50.475 blocks a straight crossing; NATIVE_VBUS_DET's
    # F.Cu vertical (50.475, y 15.6-23.11) blocks a same-Y jog further
    # south. This 3-segment path threads the one surviving window: south
    # of BTN_USER's clearance (>=14.2) but north of J2B.1's clearance
    # (<=14.45) for the westward leg, then straight south through J2B's
    # own pad1/pad2 half-pitch gap column (x=49.205, clear of
    # NATIVE_VBUS_DET which is a different X) into B.15's own territory.
    ("F.Cu", (52.0, 15.0), (52.0, 14.3), 0.2),
    ("F.Cu", (52.0, 14.3), (49.205, 14.3), 0.2),
    ("F.Cu", (49.205, 14.3), (49.205, 16.9), 0.2),
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
    (63.3, 12.032), (10.332, 59.696), (51.617, 60.296),
    # (79.751, 46.451) -> (77.0, 53.0): the old spot is inside the J9
    # Type-C rebuild's tap/CC lane bundle (shorted the J9_VBUS B_Cu
    # vertical at x=79.7); the reshaped west-pocket island reaches the
    # south pocket, stitched there instead.
    (77.0, 53.0),
    # J9 Type-C south row: R_CC4.2's and R_J9VD_B.2's GND pockets are
    # boxed in by the CC/J9_VBUS/DEV_VBUS_DET lane bundle -- the F pour
    # slivers holding those pads reach no other GND copper (union-find
    # caught both). One via in each sliver grounds them through B_Cu.
    (80.33, 53.5), (82.4, 53.2),
    (73.401, 44.7), (23.805, 19.434), (18.935, 23.408), (26.345, 51.901),
    # Task 18: genuine orphan island inside the former "Antenna Copper
    # Keep Out" region (x 43.3-52.3, y 24.9-39.1, neutered in Task 14h) --
    # a ~1.32mm-wide x ~15.6mm-tall F.Cu GND sliver along PICO's own GND
    # column (pin18/pin23 share x=45.395) with no via or GND pad anywhere
    # in it, DRC-caught as `unconnected_items` (reported at the board's
    # unrelated top-left corner outline vertex -- KiCad anchors that
    # message at the zone's first outline point, not the fault location;
    # found instead by cross-referencing every F.Cu GND fill island's
    # bbox against every GND via/pad position). Probed the island's own
    # width profile before choosing this point: uniform 1.320mm for
    # nearly its whole length (y~25.2-39.2), narrowing to 0.980mm only
    # right at the top (near PICO.23's own clearance arc) -- (45.39,32.0)
    # sits mid-run at the uniform width, giving the standard 0.6mm via
    # (needs 1.0mm channel: 0.3 radius + 0.2 clearance each side) 0.16mm
    # clearance margin on each side. Grounds copper directly beneath the
    # seated Pico module -- a genuine reference-plane improvement, not
    # just a DRC fix.
    (45.39, 32.0),
    # Task 18, second orphan: per-island "has an anchor" isn't sufficient
    # -- connectivity is a graph over ALL GND copper (vias union F.Cu<->
    # B.Cu; GND tracks union same-layer islands; THT/plated PADS union
    # every island they touch, bridging layers too -- omitting pads
    # over-fragments the graph). A proper union-find (ring-sampled at
    # anchor radius + ~0.45mm, since a bare point-in-polygon test at a
    # pad/via CENTRE false-negatives on the thermal-gap/drill hole there)
    # found a second real orphan near J_STEMMA/J_UART/R_NVD/C_P3V3_2
    # (bbox x~48.76-55.70 y~9.03-11.51, ~10.6mm^2) -- exposed by Task 18's
    # own C_P3V3_2 placement reshaping the pour in that corner. Widest
    # horizontal run measured ~6.80mm at this point, enormous margin over
    # the 1.0mm a 0.6mm via needs. Island indices renumber on every
    # refill (do not hardcode "outline N" -- verify by union-find, not
    # index).
    (52.28, 10.43),
]

_STITCH_VIAS_SPREAD = [
    (6.0, 6.0), (6.0, 14.0), (6.0, 22.0), (6.0, 30.0),
    (14.0, 6.0), (14.0, 14.0), (14.0, 30.0),
    # (22.0, 6.0) -> (23.6, 6.9): the grid spot now sits between R_CC1/
    # R_CC2 and their CC stub drops (J8 Type-C swap, 2026-07-30) --
    # hole/clearance violations against both resistors' pad "1" and a
    # dangling F-side. The replacement sits in the open F_Cu pocket
    # between R_CC2's courtyard (east edge 23.0) and J8's body (west
    # edge 24.08), same fragment it was stitching.
    (23.6, 6.9), (22.0, 14.0), (22.0, 54.0),
    (30.0, 14.0), (30.0, 54.0),
    (38.0, 6.0), (38.0, 14.0), (38.0, 30.0), (41.0, 38.0), (38.0, 54.0),
    (46.0, 54.0),
    (54.0, 22.0), (54.0, 30.0), (54.0, 38.0), (54.0, 54.0),
    (62.0, 6.0), (62.0, 38.0), (62.0, 54.0),
    (70.0, 6.0), (70.0, 14.0), (70.0, 30.0), (70.0, 38.0), (70.0, 54.0),
    (78.0, 6.0), (78.0, 14.0), (78.0, 22.0), (78.0, 30.0), (78.0, 38.0), (78.0, 54.0),
    (86.0, 6.0), (86.0, 14.0), (86.0, 22.0), (86.0, 30.0), (86.0, 38.0), (86.0, 54.0),
]

# Pad-escape vias for five of the `_GND_STUBS` above (U_INA219_ALT.3/.7,
# PICO.3/J1B.3's corridor-adjacent pocket, J3.9, U_ISNS.2) -- standard
# 0.6mm size, just not part of the ring/fragment-fix/spread groups since
# they exist to land a stub track, not to stitch a fragment.
#
# J3.9 (14.3, 61.2) and U_ISNS.2 were originally undersized at the board's
# 0.5mm/0.3mm DRC-floor size (Task 15) -- the only two vias on the board
# below the standard 0.6mm/0.3mm size, both with < 0.15mm annular ring.
# Task 16 grew both to the standard 0.6mm/0.3mm size:
#   - J3.9: enlarged in place (14.3, 61.2 unchanged) -- DRC-clean at this
#     spot up to >=1.2mm dia (same-net-as-pad, so pad clearance doesn't
#     apply; nearest other-net copper is J3.11's pad, ~0.855mm away).
#   - U_ISNS.2: enlarging in place at 65.25 passes DRC at *exactly* 0.600mm
#     with zero margin (fails at 0.605mm) against the HOST_VBUS 0.5mm B_Cu
#     track running x=64.500 y=[28.72,37.25] immediately to its west. DRC
#     measurement (not the west-nudge originally suggested, which collides:
#     the track's east edge is 64.75, only 0.25mm from the via's un-grown
#     centre, so moving toward it shortens the gap and produces a
#     `shorting_items` violation at 0.6mm) shows the real margin lies
#     *east*: nudging the via to (65.50, 34.65) -- +0.25mm away from
#     HOST_VBUS, toward the open gap before U_ISNS's own pads 4/5 at
#     x=65.7375 -- keeps DRC clean up to 0.8mm dia (0.9mm is where pad 4,
#     HOST_5V_IN, becomes the binding constraint instead), i.e. the 0.6mm
#     target now has real margin on both sides. Its `_GND_STUBS` escape
#     track was moved to the same new endpoint.
_STITCH_VIAS_PAD_ESCAPE = [
    (61.6, 27.975), (61.3, 28.625), (7.295, 39.5), (14.3, 61.2), (65.50, 34.65),
    # Task 18: the two transition vias for the B.16<->B.15 bridge stub
    # above (F.Cu<->B.Cu at each end) -- clearance verified
    # programmatically against every non-GND track/via/pad on both
    # layers before placing (task-18-report.md).
    (52.0, 15.0), (49.205, 16.9),
]

_STITCH_VIA_DIA_MM = 0.6
_STITCH_VIA_DRILL_MM = 0.3


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


# Task 16 migration: on the pre-Task-16 board file, J3.9's and U_ISNS.2's
# vias (and U_ISNS.2's connecting stub track) already exist at their old
# Task-15 spec (0.5mm/0.3mm; U_ISNS.2 at x=65.25). Mutates those existing
# objects in place (never Remove/Add -- see PLAN.md's "Verified environment
# facts") to the new spec above. On a board that doesn't have them yet
# (a genuine from-scratch build), each inner loop simply finds nothing and
# no-ops -- `_add_gnd_stubs`/`_add_stitching_vias` then create the new
# geometry directly from the already-updated `_GND_STUBS`/
# `_STITCH_VIAS_PAD_ESCAPE` tables. Either path converges on the same
# final state.
_LEGACY_MIN_VIAS_MIGRATION = [
    # (old_x, old_y, new_x, new_y) -- J3.9 unchanged, U_ISNS.2 nudged east.
    (14.3, 61.2, 14.3, 61.2),
    (65.25, 34.65, 65.50, 34.65),
]


def _fix_legacy_min_vias(board):
    ni = _net(board, "GND")
    nc = ni.GetNetCode()
    for old_x, old_y, new_x, new_y in _LEGACY_MIN_VIAS_MIGRATION:
        for t in board.GetTracks():
            if isinstance(t, pcbnew.PCB_VIA) and t.GetNetCode() == nc:
                p = t.GetPosition()
                if abs(pcbnew.ToMM(p.x) - old_x) < 0.01 and abs(pcbnew.ToMM(p.y) - old_y) < 0.01:
                    t.SetPosition(_mm(new_x, new_y))
                    t.SetWidth(pcbnew.F_Cu, pcbnew.FromMM(_STITCH_VIA_DIA_MM))
                    t.SetDrill(pcbnew.FromMM(_STITCH_VIA_DRILL_MM))
            elif isinstance(t, pcbnew.PCB_TRACK) and t.GetNetCode() == nc:
                e = t.GetEnd()
                ex, ey = pcbnew.ToMM(e.x), pcbnew.ToMM(e.y)
                if abs(ex - old_x) < 0.01 and abs(ey - old_y) < 0.01:
                    t.SetEnd(_mm(new_x, new_y))


def add_pour(board):
    _add_gnd_zone(board, pcbnew.B_Cu)
    _add_gnd_zone(board, pcbnew.F_Cu)
    _apply_solid_overrides(board)
    _fix_legacy_min_vias(board)
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
