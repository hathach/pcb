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
  - Debug row (J3/J6/J7, plus a second JST-SH DEBUG connector later removed
    in Task 14i leaving its slot empty): UNCHANGED (footprint untouched,
    not PICO-grid-dependent) -- still >=10mm courtyard-to-courtyard,
    y=59.2. J3 x=14.89
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
    # The row's second JST-SH DEBUG connector was removed in Task 14i once
    # J10's dupont header made it redundant -- its slot (x=35.23) is left
    # empty on purpose, for extra clearance between J3 and J6.
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
    # J8 (Type-C swap, 2026-07-30): usb_c_pwr's F.Fab front lip is at local
    # +4.15 (vs the old micro-B's +3.85), so the anchor moves 3.9 -> 4.15 to
    # keep the mating face flush at the top edge (y ~= 0), same convention
    # as before. Probed pad rows after the move (rot 180 => board = anchor -
    # local): VBUS pair pads "1" at x 26.95/31.85, CC1 "2" at 30.65, CC2 "3"
    # at 27.65, GND "4" at 26.15/32.65, all y=8.195; NPTH pegs (26.51/32.29,
    # 6.75); shield PTH pairs (25.08/33.72, y 3.10 and 7.28). Courtyard spans
    # x 24.08-34.72, y 0-9.42 -- clear of JP4 pin 2's pad (22.27, 10.655) and
    # of C_P3V3_1's courtyard (x 27.26-28.74, y 10.6-11.4).
    "J8": (29.4, 4.15, 180),
    # R_CC1/R_CC2 (J8 Type-C Rd pull-downs): in the open pocket WEST of
    # J8's courtyard (west edge 24.08). South of the connector is walled
    # off: NVD_TOP is an F_Cu track at y=9.51 spanning x 22.27-52.9, and
    # the 0.49mm gap between J8's pad-row bottom (8.92) and that track
    # can't fit a 0.2mm route at 0.2mm clearance -- DRC-proven on the
    # first attempt, which parked these south of J8 and shorted/crossed
    # NVD_TOP. Their CC stubs instead exit the pad row NORTHWARD and run
    # west under the connector body (hw/route_trace, lanes y=5.25/5.7).
    # R_CC1 takes the WEST slot: its lane (5.25) is the north one, so its
    # final drop (x=21.3) must lie west of where R_CC2's south lane ends
    # (22.6) or the two would cross -- worked out with the lane geometry
    # in hw/route_trace. Rotation 270 puts pad "1" on the north end
    # (probed), facing those stubs; pad "2" (GND, south) is fed by the
    # F_Cu pour. Clear of JP4's pads (x>=21.42 start at y 9.805) by >2mm.
    "R_CC1": (21.3, 6.9, 270),
    "R_CC2": (22.6, 6.9, 270),
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
    # J5 (REV B fix): moved EAST 6.610mm so the receptacle mouth is flush
    # with the x=92 board edge. REV A placed this anchor from the pad rows
    # alone and never checked the mouth-to-edge dimension -- the fabricated
    # boards have the opening recessed 6.61mm inboard (F.Fab east edge
    # 85.39 vs edge 92.00), so a cable overmold fouls on the ledge in front
    # of it. J8/J9 got explicit flush-lip arithmetic; J5 predates that
    # convention. New anchor = 92.00 - 6.775 (its own anchor->F.Fab-east
    # offset) = 85.225. Only its own DP/DM/VBUS legs lengthen (~6.6mm,
    # harmless at PIO-USB full speed); nothing else moves -- the y-band
    # 12.7..27.3 east of x=78 holds only GND pour and stitching vias
    # (MH2 is at y=4, J9 at y=40..50). Guarded by
    # hw/checks.py::test_edge_connector_mouths.
    "J5": (85.225, 20.0, 90),

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
    # J9 Type-C swap (2026-07-30 second pass): the VBUS-detect divider
    # moves from the old (80.9/82.6, 47.3) pocket -- which the Type-C
    # courtyard (x>=82.58, y 39.68-50.32) now covers -- to the open band
    # SOUTH of the connector, joined by J9's CC pull-downs. Lane plan (all
    # DRC-derived in hw/route_trace._route_j9_typec): CC1 descends at
    # x=78.5 into R_CC3.1; CC2 descends on B_Cu at x=80.35 into R_CC4.1;
    # J9_VBUS descends at x=81.3 and joins the diode/T.1 web at y=53.4;
    # DEV_VBUS_DET arrives on B_Cu at x=86.2 into R_J9VD_B.1.
    # Rotations (probed): 270 puts pad "1" north, 90 puts it south.
    # CC3/CC4 sit 0.2mm+ south of D_J9_BUSPWR's courtyard (bottom ~51.6,
    # DRC-probed -- the first attempt at y 52.3/51.81 overlapped it).
    "R_J9VD_B": (82.0, 52.0, 270),   # pad1 north (51.49) = DEV_VBUS_DET
    "R_J9VD_T": (83.5, 52.0, 90),    # pad1 south (52.51) = J9_VBUS
    "R_CC3": (78.5, 53.1, 270),      # pad1 north (52.59) = J9_CC1
    "R_CC4": (80.35, 53.0, 270),     # pad1 north (52.49) = J9_CC2
    # Task 18: rotation flipped 180->0 to match the netlist.py pad-direction
    # fix (pad1=CATHODE/VBUS_NET, pad2=ANODE/J9_VBUS, was backwards). The
    # SOD-123 footprint's two pads are symmetric rectangles at local
    # (-1.65,0)/(+1.65,0) about this same center -- a 180 degree rotation
    # swaps which physical world location each pad NUMBER sits at (was:
    # pad1 east @79.35/pad2 west @76.05; now: pad1 west/pad2 east), which
    # combined with the netlist swap lands each NET on the exact same
    # physical copper as before (west=VBUS_NET, east=J9_VBUS, unchanged) --
    # zero routing geometry change, see route_trace.py's matching pad-
    # number swap.
    "D_J9_BUSPWR": (77.7, 50.5, 0),
    # J9 (Type-C swap): usb_c_dev's F.Fab front lip is at local +4.15; at
    # rot 90 (board = (ax + ly, ay - lx)) the lip lands at ax + 4.15, so
    # ax = 87.85 keeps it flush at the right edge (x=92... lip at 92.0).
    # Pad row at x = 83.805, pads spanning y 41.75-48.25 around ay=45.0;
    # NPTH pegs at (85.25, 42.11/47.89); shield PTH pairs at x 84.72 /
    # 88.9, y 40.68 & 49.32. Courtyard x 82.58-92, y 39.68-50.32.
    "J9": (87.85, 45.0, 90),

    # --- Task 18: VSYS feed diode + decoupling caps (pre-fab review).
    # D_VSYS sits in the open PICO/J2B row gap (courtyard-clear band
    # y=17.395-20.415, verified via pcbnew courtyard survey), close to
    # PICO pin 39's own X column -- rotation 0 (2.39mm tall) fits the
    # 3.02mm gap with 0.315mm clear top/bottom. x=4.9 (not pin 39's exact
    # 4.755): DRC-caught a 0.19mm clearance shortfall (needs 0.2mm)
    # between pad1 and the adjacent VBUS_NET vertical track at x=2.215;
    # +0.145mm gives real margin. Its VSYS leg still lands squarely on
    # J2B.19 (a waypoint, not the part's own X); its VBUS_SEL leg jogs
    # east (open gap territory) to the J2B pad37/pad38 half-pitch gap
    # column (x=8.565 -- NOT the nearer pad18/pad19 gap, which has a
    # pre-existing GND stitching via right in its path) before crossing
    # J2B's row -- see route_trace.py.
    "D_VSYS": (4.9, 18.905, 0),

    # C_P3V3_1: NOT in the PICO/J2B row gap near pin 36 -- three problems
    # ruled that whole corridor out (task-18-report.md has the full
    # bisection): (a) centred on P3V3's own column (x=12.375, rot=90)
    # shorted the GND pad against that 0.5mm track; (b) offset to
    # x=13.575 (rot=0) needed a tap crossing GP28/AREF's own breakout
    # columns; (c) even after fixing (a)/(b), DRC-caught a *zone*
    # `unconnected_items` fault -- the F.Cu GND zone's fill splits into
    # two regions that don't touch, reported at the board's own top-left
    # rounded-corner outline vertex (0.3,3.0), nowhere near this part.
    # Bisected: adding a second new GND pad anywhere in this gap corridor
    # (alongside C_P3V3_2, itself unavoidably new GND-bearing copper)
    # destabilises the zone-fill solver's global result at that distant,
    # already-marginal corner (MH1 + the rounded corner + VBUS_NET's own
    # track there) -- not fixable by relocating within the corridor, only
    # by leaving it. Placed instead in the open JP4<->J_STEMMA band
    # (tested clear of the zone fault), tapping P3V3's existing B_Cu run
    # at x=41.585 (the same one J_STEMMA's own VTref-adjacent supply
    # uses) -- see route_trace.py.
    "C_P3V3_1": (28.0, 11.0, 180),

    # C_P3V3_2: south of J_STEMMA, in the open band between J_STEMMA's own
    # courtyard (bottom 7.225) and J2B's row (top 13.755). Two long
    # horizontal F_Cu tracks cross this band at this X: NVD_TOP at y=9.51
    # (x=22.27-52.9) and GP10 at y=12.11 (x=33.965-56.3) -- DRC-caught
    # shorting/crossing at earlier y=10.2/11.5 attempts. rot=0 (not
    # 270/90): the pocket between them (y~10.09-11.53) is only 1.44mm
    # tall, too short for the diode-style 1.91mm rotated-90/270 footprint
    # height but comfortable for rot=0's 1.01mm height. Centred at
    # y=10.8. The P3V3 tap still has to physically cross NVD_TOP's own Y
    # to reach J_STEMMA.2 further north -- done as a B_Cu via-hop in
    # route_trace.py (same technique as every other same-layer-obstacle
    # crossing in this file), not by placement alone.
    "C_P3V3_2": (48.6, 10.8, 0),

    # C_HSW_IN: at U_HSW pin 5 (IN) -- TI recommends 0.1uF at IN; both
    # existing HVBUS caps are on the OUT side. The original spot
    # (67.5,39.2) collided with HOST_VBUS_EN's own track (runs right
    # through x=67.0, y=39.15-39.85, DRC-caught). Relocated south/east of
    # U_HSW/R_HVEN_PD's courtyards and clear of a GND stitching via at
    # (70,38) -- verified via a full corridor survey (task-18-report.md).
    # A short jog (see route_trace.py) reaches the HOST_5V_IN spine's own
    # end point at (67.300,37.250).
    "C_HSW_IN": (68.5, 41.0, 0),
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
# extra is needed there.
#
# Task 16: the original spot (38.0, 33.0) sat directly between PICO's two
# THT pad rows -- i.e. underneath the Pico module once one is plugged in,
# never visible at the bench. Moved to a permanently-visible spot in the
# open strip along the top edge (y<~3mm, clear of every part's courtyard --
# J_STEMMA ends x=52.045, SW_USER's courtyard doesn't start until y=3.99,
# LED_USER/R_LED_USER sit further south at y>=7 -- confirmed empty via a
# board-wide obstacle scan, not eyeballed). Shrunk slightly (1.5->1.2mm /
# 1.2->1.0mm) to fit the shallower band comfortably with real margin.
BOARD_NAME_TEXT = "PICO2 TRACE MB"
BOARD_NAME_POS = (64.0, 2.0)
BOARD_NAME_SIZE_MM = 1.2
BOARD_REV_TEXT = "REV B"
BOARD_REV_POS = (64.0, 4.3)
BOARD_REV_SIZE_MM = 1.0
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

# Task 16b: the one genuinely crowded region on the board (per the task-16
# report's "6/52 refs >3mm from their own courtyard" finding) -- the Rt
# source-resistor row wedged hard against PICO/J1B, plus its two
# neighbouring two-part clusters that share the same tight real estate
# (R_LED_PWR/LED_PWR in the top-left corner, R_NVD_T/R_NVD_B east of
# J_STEMMA). `place_refs` places this set first (worst static crowding
# first), ahead of the other 43 refs, which keep their original
# alphabetical order -- see `place_refs`'s docstring for why the reorder is
# scoped to just this cluster instead of a full 52-ref reorder.
_CROWDED_CLUSTER = ["Rt1", "Rt2", "Rt3", "Rt4", "Rt5", "R_LED_PWR", "LED_PWR", "R_NVD_T", "R_NVD_B"]


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


# Function-label silk pass (Task 16, user request): the board already had
# correct refdes but no legend saying what each connector/jumper *does* --
# JP1 in particular (the 5V source selector) needs to be readable at the
# bench without a schematic in hand. Every (text, x, y, justify) entry
# below was hand-placed against real pad/courtyard/existing-silk geometry
# (queried via pcbnew, same discipline as the POS table) in the open silk
# real estate immediately around each connector, then verified by a full
# DRC pass (see task-16-report.md) -- not eyeballed. `H`/`L`/`R` = KiCad's
# CENTER/LEFT/RIGHT text justify (position = the justified anchor point,
# not a bounding-box corner). Called *before* `place_refs` so the refdes
# search (which already treats existing F.SilkS board text as an obstacle)
# naturally routes ref designators around these labels instead of the
# other way around.
FUNC_LABEL_SIZE_MM = 0.8
FUNC_LABEL_THICK_MM = 0.15

# Task 16b fix: KiCad's silk_edge_clearance DRC rule only evaluates
# PCB_SHAPE items against Edge.Cuts, never PCB_TEXT glyph geometry -- so a
# hand-placed label (like "GUARD GP0" above, which overhung the left board
# edge by 0.093mm) has no automated gate. `place_refs` already solves this
# for reference designators with a `safe_area` clamp; give function labels
# the same one, at the board's copper-to-edge margin (matches hw/pour.py's
# 0.3mm zone inset) rather than place_refs' own 0.4mm ref-specific margin.
FUNC_LABEL_EDGE_MARGIN_MM = 0.3

FUNC_LABELS: list[tuple[str, float, float, int]] = [
    # JP1 (5V source selector): title + pin-1/pin-3 end labels. Pin 1 =
    # V5_JTRACE, pin 2 = VBUS_SEL (common), pin 3 = VBUS_NET; shunt 1-2 =
    # J-Trace powered, 2-3 = USB powered.
    ("5V SEL", 12.5, 8.55, 0),      # H, above the row
    ("JTRACE", 10.6, 12.85, 2),     # R, right edge at pin 1 (x=9.96)
    ("VBUS", 14.4, 12.85, 1),       # L, left edge at pin 3 (x=15.04)
    # JP2/JP3 guard jumpers, JP4 VBUS-detect jumper.
    ("GUARD GP0", 3.5, 50.0, 0),
    ("GUARD GP6", 23.75, 50.0, 0),
    ("VBUS DET", 21.0, 8.55, 0),
    # Connectors.
    ("USB HOST", 80.0, 11.6, 0),    # J5
    # "5V IN" moved off J8's body (Type-C courtyard now reaches y=9.42 and
    # its pad row sits at y=8.195 where the label used to be) to the open
    # silk band west of R_CC2's courtyard (which starts at x~20.9), one
    # row above "VBUS DET" (18.1-23.9, y 7.95-9.15).
    ("5V IN", 16.3, 6.3, 0),        # J8 (west of the Type-C body + R_CCs)
    # "USB DEV" moved clear of J9's Type-C body (courtyard now y>=39.68 at
    # x>=82.58 -- the old spot sat on the shell).
    ("USB DEV", 87.3, 38.9, 0),     # J9 (above the Type-C body)
    ("ETM TRACE", 14.89, 54.3, 0),  # J3
    ("SWD", 52.4, 54.3, 0),         # J6
    ("PROBE", 69.57, 54.3, 0),      # J7
    ("SWD", 61.14, 54.3, 0),        # J10 title
    ("CLK", 58.6, 60.0, 0),         # J10 pin 1
    ("G", 61.14, 60.0, 0),          # J10 pin 2
    ("IO", 63.68, 60.0, 0),         # J10 pin 3
    ("TX", 59.26, 12.9, 0),         # J_UART pin 1
    ("RX", 61.8, 12.9, 0),          # J_UART pin 2
    ("G", 64.34, 12.9, 0),          # J_UART pin 3
    ("QT", 48.1, 7.7, 0),           # J_STEMMA
    ("D+", 61.675, 14.6, 0),        # TP1
    ("D-", 61.675, 25.5, 0),        # TP2
    ("G", 69.3, 25.4, 0),           # TP3
    # Task 18 pre-fab review: SW1/SW_USER had only a bare refdes, no
    # function label. Placed in verified-clear open bands (see
    # task-18-report.md) -- RESET north of SW1, between D_J9_BUSPWR
    # (bottom 51.695) and C_NRESET (top 54.89); USER north of SW_USER, in
    # the open strip along the top board edge.
    # "RESET" moved west: the old (79.06,53.0) spot now collides with
    # R_CC3/R_CC4's mask openings and the J9_VBUS spine.
    ("RESET", 75.2, 54.2, 0),       # SW1
    # x=74.0 (not SW_USER's own centre, 71.5): the board-name text
    # ("PICO2 TRACE MB") spans x=56.3-71.7 at this same y-band -- DRC-
    # caught silk_overlap at 71.5. 74.0 clears it with margin.
    ("USER", 74.0, 2.2, 0),         # SW_USER
]

# JP1 pin-1 marker: small filled dot just outside the header's own left
# rail (x=8.52), clear of both the pad (left edge ~9.11) and the "JTRACE"
# label below it.
JP1_PIN1_MARKER_POS = (8.2, 10.655)
JP1_PIN1_MARKER_RADIUS_MM = 0.15


def _clamp_text_to_safe_area(txt, safe_area) -> None:
    """Shift `txt`'s position (preserving its size/angle/justify) so its
    glyph bounding box lies fully inside `safe_area`. A no-op if the text
    is already inside. See `FUNC_LABEL_EDGE_MARGIN_MM`'s docstring for why
    this exists -- DRC does not check this for PCB_TEXT."""
    import pcbnew as _pcbnew

    bb = txt.GetBoundingBox()
    dx = dy = 0
    if bb.GetLeft() < safe_area.GetLeft():
        dx = safe_area.GetLeft() - bb.GetLeft()
    elif bb.GetRight() > safe_area.GetRight():
        dx = safe_area.GetRight() - bb.GetRight()
    if bb.GetTop() < safe_area.GetTop():
        dy = safe_area.GetTop() - bb.GetTop()
    elif bb.GetBottom() > safe_area.GetBottom():
        dy = safe_area.GetBottom() - bb.GetBottom()
    if dx or dy:
        txt.SetPosition(txt.GetPosition() + _pcbnew.VECTOR2I(dx, dy))


def add_function_labels(board) -> None:
    """Add (or update in place) every connector/jumper function label in
    `FUNC_LABELS`, plus JP1's pin-1 marker dot.

    Idempotent: matched by (exact text, position within 1mm) rather than
    text alone -- several labels share the same string ("SWD" x2, "G" x3)
    at different positions, so a text-only match (as `add_trace_silk`/
    `add_board_id_silk` use, safe there since those strings are unique)
    would conflate them.

    Task 16b: every placed/updated text is clamped inside a board-edge
    safe area (`_clamp_text_to_safe_area`) before this function returns --
    see `FUNC_LABEL_EDGE_MARGIN_MM`.
    """
    import pcbnew as _pcbnew

    H, L, R = (
        _pcbnew.GR_TEXT_H_ALIGN_CENTER,
        _pcbnew.GR_TEXT_H_ALIGN_LEFT,
        _pcbnew.GR_TEXT_H_ALIGN_RIGHT,
    )
    justify_map = {0: H, 1: L, 2: R}

    m = FUNC_LABEL_EDGE_MARGIN_MM
    safe_area = _pcbnew.BOX2I(
        _pcbnew.VECTOR2I(_pcbnew.FromMM(m), _pcbnew.FromMM(m)),
        _pcbnew.VECTOR2I(_pcbnew.FromMM(92.0 - 2 * m), _pcbnew.FromMM(64.0 - 2 * m)),
    )

    def _existing_text(text, x, y, tol=1.0):
        for d in board.GetDrawings():
            if isinstance(d, _pcbnew.PCB_TEXT) and d.GetLayer() == _pcbnew.F_SilkS and d.GetText() == text:
                p = d.GetPosition()
                if abs(_pcbnew.ToMM(p.x) - x) < tol and abs(_pcbnew.ToMM(p.y) - y) < tol:
                    return d
        return None

    for text, x, y, justify_code in FUNC_LABELS:
        txt = _existing_text(text, x, y)
        if txt is None:
            txt = _pcbnew.PCB_TEXT(board)
            board.Add(txt)
        txt.SetText(text)
        txt.SetLayer(_pcbnew.F_SilkS)
        txt.SetTextSize(_mm(FUNC_LABEL_SIZE_MM, FUNC_LABEL_SIZE_MM))
        txt.SetTextThickness(_pcbnew.FromMM(FUNC_LABEL_THICK_MM))
        txt.SetPosition(_mm(x, y))
        txt.SetHorizJustify(justify_map[justify_code])
        _clamp_text_to_safe_area(txt, safe_area)

    mk = None
    mx, my = JP1_PIN1_MARKER_POS
    for d in board.GetDrawings():
        if (isinstance(d, _pcbnew.PCB_SHAPE) and d.GetLayer() == _pcbnew.F_SilkS
                and d.GetShape() == _pcbnew.SHAPE_T_CIRCLE):
            p = d.GetCenter()
            if abs(_pcbnew.ToMM(p.x) - mx) < 1.0 and abs(_pcbnew.ToMM(p.y) - my) < 1.0:
                mk = d
                break
    if mk is None:
        mk = _pcbnew.PCB_SHAPE(board)
        board.Add(mk)
    mk.SetShape(_pcbnew.SHAPE_T_CIRCLE)
    mk.SetFilled(True)
    mk.SetLayer(_pcbnew.F_SilkS)
    mk.SetWidth(_pcbnew.FromMM(0.05))
    mk.SetCenter(_mm(mx, my))
    mk.SetEnd(_mm(mx + JP1_PIN1_MARKER_RADIUS_MM, my))


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

    Task 16 fix: the search radius used to be the courtyard bbox's
    circumscribed-circle radius (`hypot(halfW, halfH)`), applied uniformly
    in every direction. That is correct for a square-ish part but badly
    wrong for an oblong one -- e.g. J1B/J2B's 51.89x3.64mm courtyard has a
    circumscribed radius of ~26mm (the corner-to-centre distance) even
    though its own half-height is only 1.82mm, so a ray searching "north"
    still stepped out a full ~26mm before the old code even started
    looking for free space, landing the ref tens of mm away despite a spot
    0.15mm off the row being free the whole time (confirmed: PICO/J1B/J2B
    refs were 50+/26+/13+mm from their own part). Fixed by computing, per
    search ray, the actual distance from the courtyard centre to *that
    ray's* intersection with the (axis-aligned) courtyard rectangle --
    short in the near-perpendicular directions, long only along the
    diagonals, same as a human eyeballing "just outside this box" would
    place it. If no direction/distance in the ladder is collision-free
    (should not happen in practice -- see the report), the ref is hidden
    (`SetVisible(False)`) rather than exiled across the board.

    Task 16b fix: refs used to be processed in plain alphabetical order, so
    in a genuinely crowded corridor (Rt2-Rt5/J1B, and the R_LED_PWR/
    LED_PWR corner) whichever ref happened to sort first claimed the
    nearest free spot even when it had many equally-good alternatives,
    pushing a later, equally- or more-constrained ref further out once its
    neighbours were already obstacles (6/52 refs ended up >3mm from their
    own courtyard -- see task-16 report). The search itself is unchanged;
    only the processing order changes, and only for that known corridor:
    `_CROWDED_CLUSTER` (the Rt row + its two neighbouring clusters) is
    placed first -- ordered worst-static-crowding-first via the same ray
    search run against just the static board obstacles (pads + existing
    silk, i.e. how tight this ref's neighbourhood is on its own, before
    any ref text exists) -- so those refs get first claim on the corridor's
    scarce room. Every other ref keeps its original alphabetical relative
    order and runs after, unchanged.

    A full global reorder (every ref by static-crowding score) was tried
    first and rejected: it fixed the 6 flagged refs but, by reshuffling
    *all* 52 refs' relative order, silently pushed an unrelated ref
    (R_HDM_PD, in the host-cluster corner) from comfortably under 1mm to
    3.86mm -- worse than any single offender it fixed. Scoping the reorder
    to the one genuinely crowded corridor avoids touching placement order
    anywhere else on the board.
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

    def _search(txt, cx, ccy, half_w, half_h, obstacles):
        """Unchanged ray search: try each angle/distance/direction rung in
        order, return (bbox, dist_rung) of the first spot inside
        `safe_area` that clears every obstacle in `obstacles`, or
        (None, None) if the whole ladder is exhausted. Leaves `txt`
        positioned at the returned (or last-tried) spot."""
        for angle in (0, 90):
            txt.SetTextAngle(_pcbnew.EDA_ANGLE(angle, _pcbnew.DEGREES_T))
            for dist in dists:
                for dx, dy in dirs:
                    # Distance from the courtyard centre to this ray's own
                    # rectangle-boundary crossing (not the fixed
                    # circumscribed-circle radius -- see docstring).
                    tx = half_w / abs(dx) if abs(dx) > 1e-9 else math.inf
                    ty = half_h / abs(dy) if abs(dy) > 1e-9 else math.inf
                    edge = min(tx, ty)
                    r = edge + dist
                    txt.SetPosition(_mm(cx + dx * r, ccy + dy * r))
                    bb = txt.GetBoundingBox()
                    if not safe_area.Contains(bb):
                        continue
                    if any(bb.Intersects(o) for o in obstacles):
                        continue
                    return bb, dist
        return None, None

    refs0 = sorted(fp.GetReference() for fp in board.GetFootprints() if not fp.GetReference().startswith("MH"))

    def _courtyard_geom(ref):
        fp = board.FindFootprintByReference(ref)
        txt = fp.Reference()
        txt.SetTextSize(_mm(REF_SIZE_MM, REF_SIZE_MM))
        txt.SetTextThickness(_pcbnew.FromMM(REF_THICK_MM))
        fp.BuildCourtyardCaches()
        cy = fp.GetCourtyard(_pcbnew.F_CrtYd).BBox()
        cx = _pcbnew.ToMM((cy.GetLeft() + cy.GetRight()) // 2)
        ccy = _pcbnew.ToMM((cy.GetTop() + cy.GetBottom()) // 2)
        half_w = _pcbnew.ToMM(cy.GetWidth()) / 2.0
        half_h = _pcbnew.ToMM(cy.GetHeight()) / 2.0
        return fp, txt, cx, ccy, half_w, half_h

    # Crowding pre-pass (Task 16b, scoped to the known-crowded corridor --
    # see docstring): rank _CROWDED_CLUSTER by static-obstacles-only score,
    # worst first, and place that cluster ahead of everyone else. Every
    # other ref keeps its original alphabetical order, unchanged.
    static_obstacles = pad_obstacles + silk_obstacles
    scores: dict[str, float] = {}
    for ref in _CROWDED_CLUSTER:
        _, txt, cx, ccy, half_w, half_h = _courtyard_geom(ref)
        _, dist = _search(txt, cx, ccy, half_w, half_h, static_obstacles)
        scores[ref] = dist if dist is not None else math.inf
    priority = sorted((r for r in refs0 if r in scores), key=lambda r: (-scores[r], r))
    refs = priority + [r for r in refs0 if r not in scores]

    placed_boxes = []
    relocated = []
    omitted = []
    for ref in refs:
        fp, txt, cx, ccy, half_w, half_h = _courtyard_geom(ref)
        bb, _dist = _search(txt, cx, ccy, half_w, half_h, static_obstacles + placed_boxes)

        if bb is not None:
            placed_boxes.append(_expand(bb, REF_SILK_CLEARANCE_MM))
            relocated.append(ref)
        else:
            txt.SetVisible(False)
            omitted.append(ref)

    for ref in ["MH1", "MH2", "MH3", "MH4"]:
        board.FindFootprintByReference(ref).Reference().SetVisible(False)

    print(f"place_refs: relocated={len(relocated)} omitted={omitted}")
    return relocated, omitted
