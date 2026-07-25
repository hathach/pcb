"""Placement coordinate table for Task 14e (re-placement for the SMT
footprints introduced in Task 14d/14d-fix: PicoSocket_2x20_SMD with pads
offset 1.65mm outward from the pin grid, J1B/J2B stock
PinSocket_1x20_..._SMD_Pin1Left (zigzag +-1.65mm, symmetric about the row
centre -- NOT pin-1-anchored like the old custom footprint), J5
USB_A_Receptacle_GCT_USB1046, JP1-4/J_UART stock _SMD_Pin1Left headers.
Every coordinate below was re-derived from the *actual* on-board courtyard/
pad geometry (queried via pcbnew, not guessed) -- see
.superpowers/sdd/task-14e-report.md for the derivation and the full
region-by-region rationale.

POS: dict[ref -> (x_mm, y_mm, rotation_deg)] for every PARTS ref except PICO
(placed by build_board.py's `_place_pico`); MH1-4 are placed by
`_add_mounting_holes` (inset from BOARD_W_MM/BOARD_H_MM).

Coordinate frame: origin (0,0) top-left, mm, Y-down. Built against
BOARD_W_MM=92, BOARD_H_MM=64 (build_board.py) -- PICO center y = 32. With the
new PicoSocket_2x20_SMD, its own pad rows sit at y=42.515 (pads 1-20) and
y=21.435 (pads 21-40), pad-grid x 0.315..48.575 (centre x=24.445); courtyard
x -1.0..49.89, y 20.19..43.81. Re-derive POS if the board size or any
footprint changes.

Vertical budget (bottom-side chain, PICO courtyard bottom 43.81 -> board
bottom 64, 20.19mm total): Rt row (1.95mm, hard against PICO) + 0.3mm gap +
J1B (6.29mm, its real courtyard perpendicular width -- the stock zigzag
footprint is ~3x fatter than Task 14c's custom outward-offset one) + 0.3mm
gap + the debug row's 8.67mm courtyard (J3/J6, the tallest of the group) =
17.31mm, leaving ~2.9mm to the board edge. This is why JP2/JP3 (each another
6.17mm-tall band) do NOT fit as a 5th stacked band in this column -- see the
JP2/JP3 note below for where they actually landed. Board width unchanged at
92mm, under the 100mm JLC tier.

Region notes (co-design against hw/route_trace.py, which reads all pad
positions at runtime -- the two files are a matched pair; 14f re-derives its
own lane constants against these coordinates):
  - J1B/J2B: X-CENTRE MUST equal PICO's pad-grid centre (24.445) -- the stock
    footprint's anchor is the row's geometric centre, not pin 1 (Task 14d-fix
    kept the OLD custom-footprint anchor convention in the stale POS values,
    which put J1B/J2B's pad columns ~22-26mm off from PICO's own columns,
    part of J1B even landing off the left board edge). J1B sits outboard
    (south) of PICO row1 at y=49.22; J2B outboard (north) of row2 at
    y=16.745. Rt1-5 unchanged (already hard against PICO, no collision).
  - JP2/JP3 (GP0/GP6 guard jumpers): do NOT fit in the J1B->debug-row gap (see
    vertical-budget note above) or beside Rt1-5 (any Y-band spanning Rt's
    columns is inside J1B's own 48mm-wide footprint) -- relocated east of
    J1B's row-end, same Y-band as J1B (rot=0, minimises their Y-footprint),
    at x=54.245/61.455 (JP3 also dropped 0.54mm to clear R_DPU, the device
    cluster's nearest part). A longer GP0/GP6 guard trace in 14f is the
    trade-off.
  - Debug row (J3/J4/J6/J7): spaced >=10mm courtyard-to-courtyard (new hard
    invariant -- plug-grip room), y=59.2. The vertical budget's ~2.7mm of
    unused slack (board bottom 64 minus the row's minimum-gap position of
    57.0) is spent here rather than left idle, opening a real gap between
    J1B and the debug row for the "unplug while tracing" silk text (moved
    from its old y=50.6, now inside J1B's much taller footprint, to
    y=53.6). J3 x=14.89 keeps the PICO-pad-2 -> J3-pad-12 span well under
    the 25mm target. SW1 (button, not a plug connector, exempt from the
    10mm rule) trails at x=79.06 but drops further to y=59.955 -- its
    shorter 7.49mm courtyard clears the device cluster's D_J9_BUSPWR above
    it. C_NRESET rides just above SW1.
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

    # --- Breakout rows: X-centre = PICO's pad-grid centre (24.445), so every
    # pad lands directly outboard of its PICO/socket pad (stock footprint's
    # anchor is the row centre, not pin 1 -- see module docstring).
    "J1B": (24.445, 49.22, 90),
    "J2B": (24.445, 16.745, 270),

    # --- Guard jumpers (GP0/GP6 -> GND): relocated east of J1B's row-end,
    # same Y-band as J1B -- no vertical room remains beside Rt1-5 or in the
    # J1B->debug-row gap now that J1B's real courtyard is 6.29mm tall (see
    # module docstring's vertical-budget note).
    "JP2": (54.245, 49.22, 0),
    "JP3": (61.455, 49.76, 0),

    # --- Debug connector row (y 57.0): >=10mm courtyard-to-courtyard so a
    # ribbon/JST plug can be gripped without fouling its neighbour. SW1
    # trails the row but drops to y 59.955 (its courtyard is 1.18mm shorter
    # than J3/J6's) to clear D_J9_BUSPWR above it; C_NRESET rides above SW1.
    "J3": (14.89, 59.2, 90),
    "J4": (35.23, 59.2, 0),
    "J6": (52.4, 59.2, 90),
    "J7": (69.57, 59.2, 0),
    "SW1": (79.06, 59.955, 0),
    "C_NRESET": (79.06, 55.395, 0),

    # --- Top-left power corner: JP1 shifted off the left edge (its SMD
    # pads were spilling past Edge.Cuts at the old x=2.215) and clear of
    # MH1 (below it, not beside); JP4 east of JP1; J8 on the top edge
    # (mating face at y ~= -0.1); power LED pair between JP1 and JP4.
    "JP1": (12.5, 9.0, 90),
    "JP4": (21.0, 9.0, 90),
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
    "J_UART": (61.8, 9.0, 90),
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

# Trace silk (G-4): warning text in the J1B -> debug-row gap, centered under
# the GP1..GP5 breakout span.
TRACE_SILK_TEXT = "unplug while tracing"
TRACE_SILK_POS = (11.1, 53.6)
TRACE_SILK_SIZE_MM = 1.0
TRACE_SILK_THICKNESS_MM = 0.15

# Board identification silk (Adafruit-practice pass, G-4): the Pico carrier's
# own footprint (pico2_trace:PicoSocket_2x20_SMD) already carries a pin-1 dot
# + "USB END" orientation label, so nothing extra is needed there. Placed in
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
