"""Placement coordinate table for Task 12 (constrained placement + trace silk).

POS: dict[ref -> (x_mm, y_mm, rotation_deg)] for every non-DNP PARTS ref
except PICO (placed by build_board.py's `_place_pico`) -- MH1-4 aren't in
PARTS at all and are placed by build_board.py's `_add_mounting_holes`
(inset from whatever BOARD_W_MM/BOARD_H_MM currently is).

`apply(board)` is idempotent by construction: it looks each footprint up by
reference (already `Add()`-ed by `_add_footprints`) and overwrites its
position/rotation -- it never calls `BOARD.Add()`/`BOARD.Remove()`, so it
sidesteps the Remove() corruption documented in build_board.py's
`_add_footprints`/`_draw_outline` docstrings. Safe to call on every run.

Coordinate system matches build_board.py: origin (0,0) top-left, mm, KiCad's
Y-down convention. All numbers below were derived from the Task-11 PICO
geometry (USB end overhanging x=0, vertically centered on BOARD_H_MM) plus
each footprint's actual courtyard bounding box at its chosen rotation
(queried via pcbnew, not guessed) -- see task-12-report.md for the full
region-by-region derivation and a rectangle-overlap sanity sweep.

PICO header-row geometry this table was built against (BOARD_W_MM=110,
BOARD_H_MM=78 -- if either changes, re-derive):
  - bottom row (pads 1-20, the GP0-GP9-ish trace/guard pins): y = 47.89,
    x = 2.215 + (pad-1)*2.54 (pad 2 = GP1/TRACECLK src @ x=4.755, ...,
    pad 9 = GP6 guard @ x=22.535).
  - top row (pads 21-40): y = 30.11, x = 50.475 - (pad-21)*2.54
    (pad 40 = VBUS_NET @ x=2.215, "top-left").
  - PICO courtyard: x -1.0..52.94, y 27.415..50.585.

Regions:
  - Rt1-5 (27R trace source-series): directly below the bottom header row,
    each aligned under its own PICO pad (2/4/5/6/7 = GP1-5), before J1B --
    "hard against the socket trace pads on the socket side".
  - J1B / J2B: 1x20 breakout rows, pitch-aligned outboard of the bottom/top
    header rows respectively (rotated so the pin column runs along X,
    matching the header; J1B pad n <-> PICO pin n increasing x with J1B
    rotated 90, J2B pad n <-> PICO pin n+20 decreasing x with J2B rotated
    270 -- opposite handedness because the top row's physical pin order
    runs the other way, see hw/netlist.py's breakout-tie loop).
  - Debug connector group (below J1B): JP2, J3, JP3, J4, J6, J7, SW1 in one
    row, left to right -- JP2/JP3 flank J3 (near GP0/GP6 respectively), J3
    is leftmost of the four connectors to minimize the PICO-pad-2 -> J3
    span, J4/J6/J7 grouped alongside it, SW1 (reset) at the group's right
    end ("near the left/debug area").
  - Top region (above PICO): JP1 near pin 40/VBUS_NET (top-left), JP4 +
    its native-VBUS-detect divider (R_NVD_T/B) and the power LED nearby,
    then the STEMMA-QT / UART / user-button / user-LED peripheral group
    spread across the rest of the top edge.
  - Right column (x >= ~66, clear of both MH columns and the debug/top
    regions): J5 (USB-A host) with its ESD/series-R/pulldown/probe-point
    cluster and the load-switch/shunt/current-sense cluster; J8
    (power-only micro-B) below that; J9 (device micro-B) with its own
    ESD/series-R/pull-up/VBUS-divider cluster at the bottom.
"""

from __future__ import annotations

import os
import sys

if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pcbnew

POS: dict[str, tuple[float, float, float]] = {
    # --- Rt1-5: trace source-series resistors, hard against the socket
    # trace pads (PICO pads 2/4/5/6/7 = GP1-5), before J1B.
    "Rt1": (4.755, 52.3, 90),
    "Rt2": (9.835, 52.3, 90),
    "Rt3": (12.375, 52.3, 90),
    "Rt4": (14.915, 52.3, 90),
    "Rt5": (17.455, 52.3, 90),

    # --- Breakout rows, pitch-aligned outboard of each header row.
    "J1B": (2.215, 56.0, 90),
    "J2B": (50.475, 22.6, 270),

    # --- Debug connector group (below J1B): JP2/JP3 flank J3, J4/J6/J7
    # grouped alongside; SW1 (reset) at the right end.
    "JP2": (2.815, 64.0, 0),
    "J3": (13.025, 64.0, 90),
    "JP3": (23.235, 64.0, 0),
    "J4": (29.995, 64.0, 0),
    "J6": (38.665, 64.0, 90),
    "J7": (47.335, 64.0, 0),
    "SW1": (57.325, 64.0, 0),

    # --- Top region: JP1 near pin 40 (VBUS_NET), JP4 + native-VBUS-detect
    # divider and the power LED nearby, then the peripheral group.
    "JP1": (2.215, 11.0, 90),
    "JP4": (12.0, 11.0, 90),
    "R_NVD_T": (18.0, 9.5, 0),
    "R_NVD_B": (18.0, 12.5, 0),
    "LED_PWR": (22.0, 9.5, 0),
    "R_LED_PWR": (22.0, 12.0, 0),
    "J_STEMMA": (29.0, 10.0, 0),
    "J_UART": (38.0, 11.0, 90),
    "SW_USER": (51.0, 11.0, 0),
    "LED_USER": (59.0, 10.0, 0),
    "R_LED_USER": (59.0, 13.0, 0),

    # --- Right column: J5 (USB-A host) + its cluster.
    "J5": (98.0, 15.0, 0),
    "R_HDP": (72.0, 13.0, 0),
    "R_HDM": (72.0, 18.0, 0),
    "R_HDP_PD": (77.0, 13.0, 0),
    "R_HDM_PD": (77.0, 18.0, 0),
    "ESD_H": (82.0, 15.5, 0),
    "TP1": (87.0, 11.0, 0),
    "TP2": (87.0, 20.0, 0),
    "TP3": (87.0, 15.5, 0),
    "R_SHUNT": (73.0, 36.0, 0),
    "U_HSW": (79.0, 36.0, 0),
    "U_ISNS": (73.0, 42.0, 0),
    "C_HVBUS_BULK": (79.0, 42.0, 0),
    "C_HVBUS_100n": (85.0, 42.0, 0),

    # --- Right column: J8 (power-only micro-B).
    "J8": (98.0, 38.0, 0),

    # --- Right column: J9 (device micro-B) + its cluster.
    "J9": (98.0, 58.0, 0),
    "R_DDP": (72.0, 56.0, 0),
    "R_DDM": (72.0, 60.0, 0),
    "ESD_D": (77.0, 58.0, 0),
    "R_DPU": (83.0, 56.0, 0),
    "R_J9VD_T": (83.0, 60.0, 0),
    "R_J9VD_B": (83.0, 64.0, 0),
}

# Trace silk (G-4): small warning text near the J1B breakout pads that carry
# GP1-5 (the untermintated/source side of the trace bus -- Rt1-5 sit between
# these breakout pads and TRACECLK/TD0-3, so a wire on the breakout side is
# directly on the sensitive line). Sits in the gap between J1B's courtyard
# (bottom edge ~57.84) and the debug connector row (top edge ~59.67),
# centered under the GP1(x=4.755)..GP5(x=17.455) pad span.
TRACE_SILK_TEXT = "unplug while tracing"
TRACE_SILK_POS = (11.1, 58.75)
TRACE_SILK_SIZE_MM = 1.0
TRACE_SILK_THICKNESS_MM = 0.15


def _mm(x: float, y: float) -> "pcbnew.VECTOR2I":
    return pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y))


def apply(board) -> None:
    """Set position + rotation on every ref in POS.

    Idempotent: looks up each footprint by reference (already present on
    the board via `_add_footprints`) and overwrites SetPosition/
    SetOrientationDegrees -- never Add()s or Remove()s anything, so
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
    is already on the board (matched by text content, not identity) instead
    of adding a duplicate -- same skip-if-present pattern as
    build_board.py's other idempotent adders, and for the same reason
    (never BOARD.Remove() on a populated board).
    """
    import pcbnew as _pcbnew  # local alias avoids shadowing warnings below

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
