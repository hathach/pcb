"""Placement coordinate table for Task 14g (revert to THT connectors:
pico_socket -> stock RaspberryPi_Pico_Common_THT (40 THT pads "1".."40",
ON-GRID at the nominal pin positions -- no more 1.65mm outward SMD offset),
breakout_1x20 -> stock PinSocket_1x20_P2.54mm_Vertical (THT, PIN-1-ANCHORED
-- unlike the SMD_Pin1Left variant it replaces, which anchored at the row's
geometric centre), hdr_1x02/hdr_1x03 -> stock PinHeader_1x0N_P2.54mm_Vertical
(THT, also pin-1-anchored). Every coordinate below was re-derived from the
*actual* on-board courtyard/pad geometry (queried via pcbnew, not guessed) --
see .superpowers/sdd/task-14g-report.md for the derivation. Coordinates for
parts whose footprint did NOT change and whose position does not depend on
PICO's own pad grid (Rt1-5 excepted -- see below) are carried over unchanged
from Task 14e's SMD-era table.

POS: dict[ref -> (x_mm, y_mm, rotation_deg)] for every PARTS ref except PICO
(placed by build_board.py's `_place_pico`); MH1-4 are placed by
`_add_mounting_holes` (inset from BOARD_W_MM/BOARD_H_MM).

Coordinate frame: origin (0,0) top-left, mm, Y-down. Built against
BOARD_W_MM=92, BOARD_H_MM=64 (build_board.py) -- PICO center y = 32. With the
reverted RaspberryPi_Pico_Common_THT, its own pad rows sit at y=40.89
(pads 1-20) and y=23.11 (pads 21-40), pad-grid x 2.215..50.475 (2.54mm pitch,
on-grid); courtyard x -1.0..52.94, y 20.415..43.585 -- this is *exactly* the
pre-Task-14d (Task 12/14c) THT geometry, since PICO's own footprint and
`_place_pico`'s courtyard-based placement formula were never touched by the
SMD detour. Re-derive POS if the board size or any footprint changes.

Vertical budget (bottom-side chain, PICO courtyard bottom 43.585 -> board
bottom 64): Rt row (courtyard 43.825..45.775, hard against PICO, UNCHANGED --
its X/Y values already land exactly on PICO's THT pad columns, 0.00mm error,
see the Rt note below) + J1B (courtyard 46.005..49.645, only 3.64mm
perpendicular-width now -- the *stock THT* footprint, not the SMD zigzag
Task 14e sized this budget around) + a 5.22mm gap (49.645..54.865) that now
comfortably fits the relocated JP2/JP3 guard jumpers (rot=90, 3.63mm tall)
plus the "unplug while tracing" silk text + the debug row's existing 54.865+
courtyard (J3/J6, unchanged, still at y=59.2). THT shrinks J1B enough that
the JP2/JP3-in-the-gap placement Task 14e's report ruled out for the fat SMD
footprint fits again. Board width unchanged at 92mm, under the 100mm JLC
tier.

Region notes (co-design against hw/route_trace.py, which reads all pad
positions at runtime -- the two files are a matched pair; 14f re-derives its
own lane constants against these coordinates):
  - Rt1-5: UNCHANGED (4.755/9.835/12.375/14.915/17.455, y=44.8, rot=90) --
    verified these already sit at EXACTLY the new THT PICO pad-grid X
    columns for pads 2/4/5/6/7 (0.00mm error) with the same "hard against"
    Y gap (~0.24mm from PICO's new courtyard bottom) as before. These
    coordinates were never touched by the SMD detour (Task 14e's own report:
    "Rt1-5 unchanged, hard against PICO") -- they were designed against this
    exact THT grid back in Task 12 and are simply correct again now that
    PICO is THT once more.
  - J1B/J2B: the reverted breakout footprint anchors at PIN 1, not the row
    centre -- so J1B's/J2B's POS *is* pad 1's world position outboard of
    PICO pad 1/pad 21 respectively (both stock parts share the identical
    2.54mm pitch and pad-1-first numbering convention as PICO's own THT
    grid, so every one of the 20 pads lands EXACTLY on its PICO partner's X,
    by construction -- not approximated). J1B = PICO pad "1" position
    (2.215, 40.89) + 6.91mm south -> (2.215, 47.8), rot=90 (row runs +X with
    increasing pad number, matching PICO pads 1->20 running west->east).
    J2B = PICO pad "21" position (50.475, 23.11) + 7.51mm north ->
    (50.475, 15.6), rot=270 (row runs -X with increasing pad number,
    matching PICO pads 21->40 running east->west). These are the exact
    values Task 12/14c's THT-era place.py used (git show 4fb3f47:hw/place.py)
    -- re-verified against fresh pcbnew geometry, not just copied blind.
  - JP1/JP4/J_UART (hdr_1x03/hdr_1x02, top power corner): Task 14e's SMD-era
    top-corner layout (J8/LED_PWR/MH1 arrangement) is kept as-is -- it fixed
    real stale-position defects (JP1 crowding the left edge/MH1) that were
    NOT caused by the SMD footprint and would reappear if this task blindly
    restored the pre-14d numbers. Only the header anchors move: the old
    _SMD_Pin1Left footprint anchored at the row's centre, so its pin "1" sat
    at a zigzag-offset world position; the new THT footprint's pin "1" *is*
    the anchor. New POS = old (Task 14e) pad-"1" world position exactly, so
    the row occupies the identical world rectangle as before (same pitch,
    same numbering direction), just without the SMD zigzag's perpendicular
    stagger (each row is now a straight, and physically slimmer, line) --
    verified this reproduces the old courtyard's L/R (row-direction) extent
    to the sub-mm, so no new collisions with MH1/J8/R_NVD/etc.
  - JP2/JP3 (GP0/GP6 guard jumpers): relocated into the J1B -> debug-row gap
    (now 5.22mm tall, see the vertical-budget note), rot=90 so each header's
    2.54mm pitch runs along X (3.63mm tall, fits the gap) instead of Y.
    Pin "1" (the guarded GPIO) anchors EXACTLY on its PICO partner's X: JP2 =
    PICO pad "1"/GP0's x (2.215), JP3 = PICO pad "9"/GP6's x (22.535), both
    at y=52.255 (vertically centred in the gap, 0.795mm clear of J1B above
    and the debug row below). Straight-line guard-trace runs collapse from
    the SMD-era's 42-50mm (JP2/JP3 relocated east of J1B's row-end, per Task
    14e's report) down to ~11.4mm (JP2) / ~11.9mm (JP3) -- see the gate
    report for the exact figures.
  - Debug row (J3/J4/J6/J7): UNCHANGED (footprint untouched, not PICO-grid-
    dependent) -- still >=10mm courtyard-to-courtyard, y=59.2. J3 x=14.89
    keeps the PICO-pad-"2" -> J3-pad-12 span well under the 30mm hard limit
    (recomputed for the new PICO pad "2" position -- see the gate report).
    SW1/C_NRESET unchanged.
  - Top peripherals (JP1/JP4/J8/J_STEMMA/LED pairs/R_NVD/J_UART) live in
    y<=13.6 (above J2B's new courtyard top). J8/J_STEMMA (true cable
    receptacles) keep >=10mm clear of each other; JP1/JP4/J_UART (vertical
    pin headers, no rigid plug body) are not held to that rule but still
    non-overlapping. JP1 shifted off the left edge and clear of MH1 (both
    were a stale-position defect, not new-footprint growth).
  - Host cluster (R_HDP/R_HDM/TP1/TP2/PDs/ESD_H) re-aligned to J5's real
    pad rows (HOST_DP y=19.0, HOST_DM y=21.0 -- GCT1046's own pad geometry,
    different from the old Molex-based assumption of 15.55/17.45).
  - TP1/TP2 sit symmetrically in-line on the host D+/D- rows (no stubs on
    data lines); TP3 (GND) taps the pour. J_TRACE_TP no longer exists
    (removed from the model -- stub-on-trace-net SI violation).
"""

from __future__ import annotations

import os
import sys

if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pcbnew

POS: dict[str, tuple[float, float, float]] = {
    # --- Trace source-series resistors (under PICO pads 2/4/5/6/7).
    "Rt1": (4.755, 44.8, 90),
    "Rt2": (9.835, 44.8, 90),
    "Rt3": (12.375, 44.8, 90),
    "Rt4": (14.915, 44.8, 90),
    "Rt5": (17.455, 44.8, 90),

    # --- Breakout rows: POS = pin "1"'s world position (stock footprint is
    # pin-1-anchored, not centre-anchored -- see module docstring). Every pad
    # lands exactly outboard of its PICO partner pad by construction.
    "J1B": (2.215, 47.8, 90),
    "J2B": (50.475, 15.6, 270),

    # --- Guard jumpers (GP0/GP6 -> GND): back in the J1B->debug-row gap
    # (fits again now that J1B's THT courtyard is only 3.64mm tall -- see
    # module docstring's vertical-budget note), rot=90 so the 2-pad row runs
    # along X. Pin "1" (the guarded GPIO) anchors exactly on PICO pad "1"/"9"
    # x respectively.
    "JP2": (2.215, 52.255, 90),
    "JP3": (22.535, 52.255, 90),

    # --- Debug connector row (y 59.2): >=10mm courtyard-to-courtyard so a
    # ribbon/JST plug can be gripped without fouling its neighbour. SW1
    # trails the row but drops to y 59.955 (its courtyard is 1.18mm shorter
    # than J3/J6's) to clear D_J9_BUSPWR above it; C_NRESET rides above SW1.
    "J3": (14.89, 59.2, 90),
    "J4": (35.23, 59.2, 0),
    "J6": (52.4, 59.2, 90),
    "J7": (69.57, 59.2, 0),
    "SW1": (79.06, 59.955, 0),
    "C_NRESET": (79.06, 55.395, 0),

    # --- J10 (Task 14h): dupont-wire SWD header, in the debug row's only
    # free X gap (J6 courtyard right edge 56.125 -> J7 courtyard left edge
    # 66.125, a 10mm span): rot=90 (pitch runs +X, matching J_UART/JP1/JP4)
    # puts J10's own courtyard at x 56.785-65.495 -- 0.66mm clear of J6 and
    # J7 on either side (no footprint-courtyard overlap).
    # Y is NOT the row's own y=59.2: that sits exactly in the 1.5mm
    # inter-row gap straddled by the existing SWDIO (B_Cu, y=58.80) and
    # NRESET (B_Cu, y=59.42) trunk lines, which run the *entire* width of
    # this gap (J6->J7) already -- a THT pad there (1.7mm dia, 0.85mm
    # radius) physically overlaps both trunks regardless of which net it's
    # on (confirmed via DRC: `shorting_items` NRESET-SWCLK and SWDIO-SWCLK,
    # plus solder_mask_bridge, when first tried at y=59.2). The board is
    # too short (64mm) to go south of the SWCLK/P3V3 F_Cu/B_Cu lanes
    # (y=62.65/62.90) with 0.5mm edge clearance to spare. Going north
    # instead: y=57.5 clears SWDIO (58.80) by 1.30mm and NRESET (59.42) by
    # 1.92mm -- both > the 1.15mm minimum (0.85mm pad radius + 0.2mm
    # clearance + 0.1mm track halfwidth) -- and that x/y cell is otherwise
    # empty (verified: only J6/J7 courtyards and the two trunk tracks
    # occupy this region; no other pads/tracks/vias). Re-verified via DRC
    # after the move: identical 7 pre-existing violations (5 clearance on
    # unrelated/DNP U_INA219_ALT + 2 silk_edge_clearance) as the unmodified
    # board, zero new ones.
    "J10": (58.6, 57.5, 90),

    # --- Top-left power corner: JP1 clear of the left edge/MH1 (a Task 14e
    # fix, unrelated to the THT revert -- kept); JP4 east of JP1; J8 on the
    # top edge (mating face at y ~= -0.1); power LED pair between JP1 and
    # JP4. JP1/JP4 POS = pin "1"'s Task-14e world position (row-direction
    # extent reproduced exactly -- see module docstring).
    "JP1": (9.96, 10.655, 90),
    "JP4": (19.73, 10.655, 90),
    "J8": (29.4, 3.9, 180),
    "LED_PWR": (4.0, 9.6, 270),
    "R_LED_PWR": (4.0, 12.1, 90),

    # --- Native-VBUS-detect divider, east of J_STEMMA.
    "R_NVD_T": (52.9, 9.0, 90),
    "R_NVD_B": (54.5, 9.0, 270),

    # --- Top peripherals: J_STEMMA >=10mm east of J8 (both real cable
    # receptacles, y<=7.2 so J2B's X-range is irrelevant to either); JP1/
    # JP4/J_UART (vertical headers, not held to the 10mm rule) all keep
    # y-extent <=12.46, clear of J2B's y=13.6 top with margin regardless of
    # x, so none of this row needs to dodge J2B's footprint horizontally.
    "J_STEMMA": (48.1, 3.9, 180),
    "LED_USER": (56.3, 8.6, 270),
    "R_LED_USER": (56.3, 11.6, 90),
    "J_UART": (59.26, 10.655, 90),
    "SW_USER": (71.5, 7.5, 0),

    # --- Host USB-A cluster: re-aligned to J5's real GCT1046 pad rows
    # (HOST_DP y=19.0, HOST_DM y=21.0 -- different from the old Molex-based
    # assumption of 15.55/17.45). Series Rs -> in-line TPs -> pulldowns ->
    # ESD_H's flow-through pads -> J5.DP/DM, all west of J5's own courtyard
    # (L=69.32).
    "R_HDP": (59.1, 19.0, 0),
    "R_HDM": (59.1, 21.0, 0),
    "TP1": (61.675, 16.5, 0),
    "TP2": (61.675, 23.5, 0),
    "R_HDP_PD": (63.79, 17.15, 90),
    "R_HDM_PD": (63.79, 22.85, 270),
    "ESD_H": (66.7, 20.0, 0),
    "TP3": (67.45, 25.4, 0),
    "J5": (78.615, 20.0, 90),

    # --- Power cluster (shunt/current-sense/load-switch), x 60..79.
    "R_SHUNT": (64.6, 31.5, 0),
    "U_INA219_ALT": (61.5, 28.3, 180),
    "U_HSW": (64.5, 38.2, 0),
    "R_HVEN_PD": (65.64, 41.6, 270),
    "C_HVBUS_100n": (70.0, 29.2, 270),
    "C_HVBUS_BULK": (73.0, 30.0, 270),
    "U_ISNS": (64.6, 34.6, 0),

    # --- Device micro-B cluster: D+/D- rows y 43.75/45.65 into ESD_D/J9;
    # R_DPU on the corridor side; divider + DNP bus-power diode SE.
    "R_DPU": (63.0, 45.4, 270),
    "R_DDP": (69.0, 43.75, 0),
    "R_DDM": (69.0, 45.65, 0),
    "ESD_D": (77.5, 44.7, 0),
    "R_J9VD_B": (80.9, 47.3, 270),
    "R_J9VD_T": (82.6, 47.3, 90),
    "D_J9_BUSPWR": (77.7, 50.5, 180),
    "J9": (88.255, 45.0, 90),
}

# Trace silk (G-4): warning text in the J1B -> debug-row gap, centred in the
# clear window between the (Task 14g) relocated JP2/JP3 guard jumpers.
TRACE_SILK_TEXT = "unplug while tracing"
TRACE_SILK_POS = (13.65, 52.255)
TRACE_SILK_SIZE_MM = 0.8
TRACE_SILK_THICKNESS_MM = 0.15

# Board identification silk (Adafruit-practice pass, G-4): the reverted
# (Task 14g) stock RaspberryPi_Pico_Common_THT footprint already carries its
# own "USB Cable"/"Possible Antenna"/"Keep Out" orientation silk, so nothing
# extra is needed there. Placed in
# the open corridor between the host/power clusters (nothing else lives at
# x 50..60, y 30..40 -- that column is reserved for 14f's gap-crossing
# routing lanes, which live on copper layers and don't conflict with silk).
BOARD_NAME_TEXT = "PICO2 TRACE MB"
BOARD_NAME_POS = (38.0, 33.0)
BOARD_NAME_SIZE_MM = 1.5
BOARD_REV_TEXT = "REV A"
BOARD_REV_POS = (38.0, 35.6)
BOARD_REV_SIZE_MM = 1.2
BOARD_ID_THICKNESS_MM = 0.15

# Reference-designator silk pass (Task 14e): every ref shrinks to a compact,
# uniform size and is repositioned to the first collision-free spot found by
# a radial search around its own footprint's courtyard, in preference order
# N/NNE/NE/.../NNW (15-degree steps) x increasing standoff, tried at text
# angle 0 then 90 -- see `place_refs`.
REF_SIZE_MM = 0.8
REF_THICK_MM = 0.15
REF_SILK_CLEARANCE_MM = 0.15  # project's own board silk clearance rule is 0
REF_EDGE_MARGIN_MM = 0.4  # keep ref text well clear of Edge.Cuts


def _mm(x: float, y: float) -> "pcbnew.VECTOR2I":
    return pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y))


def apply(board) -> None:
    """Set position + rotation on every ref in POS.

    Idempotent: looks up each footprint by reference and overwrites
    SetPosition/SetOrientationDegrees -- never Add()s or Remove()s, so
    re-running produces byte-for-byte identical placement.
    """
    for ref, (x, y, rot) in POS.items():
        fp = board.FindFootprintByReference(ref)
        assert fp is not None, f"place.py: no footprint {ref!r} on board"
        fp.SetPosition(_mm(x, y))
        fp.SetOrientationDegrees(rot)


def add_trace_silk(board) -> None:
    """Add (or update in place) the "unplug while tracing" F.SilkS text.

    Idempotent: reuses the existing PCB_TEXT with this exact string if one
    is already on the board instead of adding a duplicate.
    """
    import pcbnew as _pcbnew

    texts = [
        d for d in board.GetDrawings()
        if isinstance(d, _pcbnew.PCB_TEXT) and d.GetText() == TRACE_SILK_TEXT
    ]
    txt = texts[0] if texts else _pcbnew.PCB_TEXT(board)
    if not texts:
        board.Add(txt)
    txt.SetText(TRACE_SILK_TEXT)
    txt.SetLayer(_pcbnew.F_SilkS)
    txt.SetTextSize(_mm(TRACE_SILK_SIZE_MM, TRACE_SILK_SIZE_MM))
    txt.SetTextThickness(_pcbnew.FromMM(TRACE_SILK_THICKNESS_MM))
    txt.SetPosition(_mm(*TRACE_SILK_POS))


def add_board_id_silk(board) -> None:
    """Add (or update in place) the board-name + revision F.SilkS texts.

    Same reuse-by-exact-text idempotence pattern as `add_trace_silk`.
    """
    import pcbnew as _pcbnew

    def _text(s, pos, size_mm):
        existing = [
            d for d in board.GetDrawings()
            if isinstance(d, _pcbnew.PCB_TEXT) and d.GetText() == s
        ]
        txt = existing[0] if existing else _pcbnew.PCB_TEXT(board)
        if not existing:
            board.Add(txt)
        txt.SetText(s)
        txt.SetLayer(_pcbnew.F_SilkS)
        txt.SetTextSize(_mm(size_mm, size_mm))
        txt.SetTextThickness(_pcbnew.FromMM(BOARD_ID_THICKNESS_MM))
        txt.SetPosition(_mm(*pos))

    _text(BOARD_NAME_TEXT, BOARD_NAME_POS, BOARD_NAME_SIZE_MM)
    _text(BOARD_REV_TEXT, BOARD_REV_POS, BOARD_REV_SIZE_MM)


def _expand(bb: "pcbnew.BOX2I", mm: float) -> "pcbnew.BOX2I":
    b2 = pcbnew.BOX2I(bb.GetPosition(), bb.GetSize())
    b2.Inflate(pcbnew.FromMM(mm))
    return b2


def place_refs(board) -> None:
    """Shrink every part's reference designator to REF_SIZE_MM and move it
    to the first collision-free spot on a radial search around its own
    footprint's courtyard (see the module-level constants above).

    Deterministic + idempotent: refs are processed in a fixed (sorted)
    order, each accepted placement becomes an obstacle for the refs after
    it, and re-running from the same footprint positions retraces the same
    search and lands on the same spot every time. MH1-4 (mounting holes,
    no functional need to label) get their reference silk hidden instead.
    """
    import math

    import pcbnew as _pcbnew

    pad_obstacles = []
    silk_obstacles = []
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            pad_obstacles.append(_expand(pad.GetBoundingBox(), REF_SILK_CLEARANCE_MM))
        for item in fp.GraphicalItems():
            if item.GetLayerName() == "F.Silkscreen":
                silk_obstacles.append(_expand(item.GetBoundingBox(), REF_SILK_CLEARANCE_MM))
    for d in board.GetDrawings():
        if isinstance(d, _pcbnew.PCB_TEXT) and d.GetLayer() == _pcbnew.F_SilkS:
            silk_obstacles.append(_expand(d.GetBoundingBox(), REF_SILK_CLEARANCE_MM))

    m = REF_EDGE_MARGIN_MM
    safe_area = _pcbnew.BOX2I(
        _pcbnew.VECTOR2I(_pcbnew.FromMM(m), _pcbnew.FromMM(m)),
        _pcbnew.VECTOR2I(_pcbnew.FromMM(92.0 - 2 * m), _pcbnew.FromMM(64.0 - 2 * m)),
    )

    dirs = [(math.cos(math.radians(a)), math.sin(math.radians(a))) for a in range(0, 360, 15)]
    dists = [0.15, 0.4, 0.8, 1.3, 1.9, 2.6, 3.4, 4.3, 5.3]

    placed_boxes = []
    refs = sorted(fp.GetReference() for fp in board.GetFootprints() if not fp.GetReference().startswith("MH"))
    for ref in refs:
        fp = board.FindFootprintByReference(ref)
        txt = fp.Reference()
        txt.SetTextSize(_mm(REF_SIZE_MM, REF_SIZE_MM))
        txt.SetTextThickness(_pcbnew.FromMM(REF_THICK_MM))
        fp.BuildCourtyardCaches()
        cy = fp.GetCourtyard(_pcbnew.F_CrtYd).BBox()
        cx = _pcbnew.ToMM((cy.GetLeft() + cy.GetRight()) // 2)
        ccy = _pcbnew.ToMM((cy.GetTop() + cy.GetBottom()) // 2)
        diag = math.hypot(_pcbnew.ToMM(cy.GetWidth()) / 2.0, _pcbnew.ToMM(cy.GetHeight()) / 2.0)

        found = False
        bb = None
        for angle in (0, 90):
            txt.SetTextAngle(_pcbnew.EDA_ANGLE(angle, _pcbnew.DEGREES_T))
            for dist in dists:
                for dx, dy in dirs:
                    txt.SetPosition(_mm(cx + dx * (diag + dist), ccy + dy * (diag + dist)))
                    bb = txt.GetBoundingBox()
                    if not safe_area.Contains(bb):
                        continue
                    if any(bb.Intersects(o) for o in pad_obstacles + silk_obstacles + placed_boxes):
                        continue
                    found = True
                    break
                if found:
                    break
            if found:
                break
        assert found, f"place_refs: no collision-free spot found for {ref!r}"
        placed_boxes.append(_expand(bb, REF_SILK_CLEARANCE_MM))

    for ref in ["MH1", "MH2", "MH3", "MH4"]:
        board.FindFootprintByReference(ref).Reference().SetVisible(False)
