"""Placement coordinate table for Task 14c (92x64 compaction + co-designed
full placement).

POS: dict[ref -> (x_mm, y_mm, rotation_deg)] for every PARTS ref except PICO
(placed by build_board.py's `_place_pico`); MH1-4 are placed by
`_add_mounting_holes` (inset from BOARD_W_MM/BOARD_H_MM).

Coordinate frame: origin (0,0) top-left, mm, Y-down. Built against
BOARD_W_MM=92, BOARD_H_MM=64 (build_board.py) -- PICO center y = 32, so its
header rows land at y=22.61 (pads 21-40) and y=40.89 (pads 1-20); PICO
courtyard x -1.0..52.94, y 20.415..43.585. Re-derive POS if the board size
changes.

Vertical budget (why H=64, not the 62 the brief sketched): the bottom-side
chain is rigid -- PICO courtyard bottom (H/2+11.585) + Rt row + J1B row +
the trace bundle's meander/convergence band (J1B pad bottom +0.35 clear +
meander room, ending >= 3.05+3.15 above J3's north pad row) + J3's 8.67mm
courtyard + the 4-trunk SWD/NRESET/P3V3 B_Cu stack below the debug row
(south pads +1.6, 3x0.9 spacing) + 0.3 copper-to-edge. Summing minima gives
H >= H/2 + 31.18 -> H >= 62.4: 62 is infeasible without redesigning the
Task-13 bundle convergence, 64 leaves ~0.8mm of real margin. Max dim is the
92mm width -- under the 100mm JLC tier either way.

Region notes (co-design against hw/route_trace.py, which reads all pad
positions at runtime -- the two files are a matched pair):
  - Left block keeps Task 12/13's relative geometry (trace bundle + SWD tree
    re-derive identically): Rt row 44.8, J1B 47.8, J2B 15.6, debug row 55.8.
    J3..SW1 shift +1.505mm east so J3's courtyard clears MH3's (mounting
    holes track the corners). JP2/JP3 leave the debug row (no vertical room
    above MH3) for the J1B->J3 gap band, rotated 0 at y 51.6, next to the
    GP0/GP6 breakout columns they guard.
  - Debug-row south pads sit at y 58.95; SWD trunks land at y 60.55..63.25.
  - Top peripherals live in y<=13.7 (above J2B's courtyard): J8 (VBUS-in
    micro-B) moved to the TOP edge next to JP4/JP1 -- VBUS_NET's members are
    all in this corner, and the right edge cannot fit three connector bodies
    with 10mm gaps in H=64. J5/J9 keep the right edge (mating faces at
    x=92.15, >=10mm courtyard gap, MH2/MH4 cleared).
  - Right-side clusters are ordered so destination rows match PICO-row
    source order (kills Task 14's crossing conflicts): host D+/D- rows at
    y 15.55/17.45 continue straight into ESD_H/J5's own pad rows; device
    D+/D- rows at 43.75/45.65 match ESD_D/J9; the corridor columns at
    x 52.0..56.9 and the B_Cu rims at y 12.3..14.35 are lane assignments in
    route_trace.py, derived jointly with these coordinates.
  - TP1/TP2 sit symmetrically in-line on the host D+/D- rows (no stubs on
    data lines); TP3 (GND) taps the pour. J_TRACE_TP no longer exists
    (removed from the model -- stub-on-trace-net SI violation).
  - The 5 parts Task 14b left at (0,0) are placed: R_HVEN_PD at U_HSW.EN,
    C_NRESET beside SW1, U_INA219_ALT beside R_SHUNT (IN+/IN- facing it),
    D_J9_BUSPWR between the J9 cluster and the VBUS_NET run.
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

    # --- Breakout rows, pitch-aligned outboard of each PICO header row.
    "J1B": (2.215, 47.8, 90),
    "J2B": (50.475, 15.6, 270),

    # --- Guard jumpers: gap band between J1B and the debug row, beside the
    # GP0 (x 2.215) / GP6 (x 22.535) breakout columns. JP3's x also keeps
    # its pads >=0.45mm clear of VBUS_NET's F_Cu hop vias at x 20.3/22.3.
    "JP2": (2.815, 51.6, 0),
    "JP3": (25.0, 51.6, 0),

    # --- Debug connector row (y 55.8): +1.505mm east of the Task-12 xs so
    # J3's courtyard clears MH3's; C_NRESET rides just above SW1.
    "J3": (14.53, 55.8, 90),
    "J4": (31.5, 55.8, 0),
    "J6": (40.17, 55.8, 90),
    "J7": (48.84, 55.8, 0),
    "SW1": (58.83, 55.8, 0),
    "C_NRESET": (58.83, 51.4, 0),

    # --- Top-left power corner: JP1/JP4 unchanged x, J8 on the top edge
    # (mating face at y=-0.15), power LED pair west of JP4's pin column.
    "JP1": (2.215, 11.0, 90),
    "JP4": (12.0, 11.0, 90),
    "J8": (17.0, 3.745, 180),
    "LED_PWR": (10.2, 4.7, 270),
    "R_LED_PWR": (10.2, 7.4, 90),

    # --- Native-VBUS-detect divider, east of J_STEMMA's I2C feed columns
    # (x 26.3/28.9) so NVD_TOP's B_Cu run and the divider tie stay clear.
    "R_NVD_T": (30.8, 9.6, 90),
    "R_NVD_B": (32.4, 9.6, 270),

    # --- Top peripherals: dest x ordered to match the PICO-row gap columns
    # their nets emerge from (STEMMA 26.345/28.885, LED 33.965, UART
    # 39.045/41.585, button x 53.52 = SW_USER pad 1L).
    "J_STEMMA": (29.0, 3.4, 180),
    "LED_USER": (33.965, 8.6, 270),
    "R_LED_USER": (33.965, 11.6, 90),
    "J_UART": (38.0, 11.0, 90),
    "SW_USER": (57.5, 9.7, 0),

    # --- Host USB-A cluster: D+/D- rows y 15.55/17.45 run straight from
    # the series Rs through in-line TPs into ESD_H's flow-through pads and
    # on into J5.DP/DM; pulldowns tap vertically off the rows.
    "R_HDP": (67.5, 15.55, 0),
    "R_HDM": (67.5, 17.45, 0),
    "TP1": (70.1, 13.4, 0),
    "TP2": (70.1, 19.55, 0),
    "R_HDP_PD": (72.3, 13.7, 90),
    "R_HDM_PD": (72.3, 19.3, 270),
    "ESD_H": (73.6, 16.5, 0),
    "TP3": (74.35, 21.9, 0),
    "J5": (78.615, 20.0, 90),

    # --- Power cluster (shunt/current-sense/load-switch), x 60..79.
    "R_SHUNT": (64.6, 31.5, 0),
    "U_INA219_ALT": (61.5, 28.3, 180),
    "U_HSW": (64.5, 38.2, 0),
    "R_HVEN_PD": (65.64, 41.6, 270),
    "C_HVBUS_100n": (70.0, 27.55, 270),
    "C_HVBUS_BULK": (73.0, 27.62, 270),
    "U_ISNS": (64.6, 34.6, 0),

    # --- Device micro-B cluster: D+/D- rows y 43.75/45.65 into ESD_D/J9;
    # R_DPU on the corridor side; divider + DNP bus-power diode SE.
    "R_DPU": (63.0, 45.4, 270),
    "R_DDP": (69.0, 43.75, 0),
    "R_DDM": (69.0, 45.65, 0),
    "ESD_D": (77.5, 44.7, 0),
    "R_J9VD_B": (80.9, 47.3, 270),
    "R_J9VD_T": (82.6, 47.3, 90),
    "D_J9_BUSPWR": (77.7, 52.5, 180),
    "J9": (88.255, 45.0, 90),
}

# Trace silk (G-4): warning text in the J1B -> debug-row gap, centered under
# the GP1..GP5 breakout span.
TRACE_SILK_TEXT = "unplug while tracing"
TRACE_SILK_POS = (11.1, 50.6)
TRACE_SILK_SIZE_MM = 1.0
TRACE_SILK_THICKNESS_MM = 0.15


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
