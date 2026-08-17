# REV B — change log and open items

**REV A is the fabricated hardware** (JLCPCB `W2026073018593887`, 2026-07-30,
5 PCB / 2 assembled). Those boards are on the bench and match git tag
**`rev-a-pico2`**. The working tree has since advanced to REV B, which has
**not been ordered**. The silkscreen revision string tracks this
(`hw/place.py: BOARD_REV_TEXT`), so the two are never confusable in hand.

## Fixed in REV B

### J5 USB-A mouth was 6.61 mm inboard of the board edge

Found on the REV A hardware at bring-up. The receptacle opening sat 6.61 mm
inside the x=92 edge (F.Fab east 85.39), leaving a ledge of bare board in
front of it, so a cable's overmold fouls before the plug seats. Only pour
and two stitching vias occupied that strip, so REV A boards can be rescued
by filing a notch from x≈85.4 to the edge across y≈11–29 (no signals, no
mounting holes there — MH2 is at y=4, J9 at y=40–50).

Root cause: J5's anchor was derived from its **pad rows** (to line up with
the R_HDP/R_HDM/TP/ESD_H chain at y=19.0/21.0) and the mouth-to-edge
dimension was never asserted. J8 and J9 were placed with explicit flush-lip
arithmetic; J5 predated that convention. Nothing caught it: DRC has no such
rule, and the pre-order checklist's "openings must face off the board edge"
was a human eyeball on the fab's render.

Fix: anchor `78.615 → 85.225` (its own anchor→F.Fab-east offset is 6.775,
so 92.00 − 6.775). Mouth now lands exactly at 92.00. The change is
surgical — semantic diff vs `rev-a-pico2` shows **only**: J5 moved, 7
tracks re-routed on HOST_DP/HOST_DM/HOST_VBUS, one GND stitching via
relocated (78.0,22.0)→(75.0,26.0) because J5's HOST_DM pad landed 1.0 mm
from it, and the REV silk string.

Regression guard added: `hw/checks.py::test_edge_connector_mouths` asserts
every edge-facing receptacle's F.Fab mouth is within 1.0 mm of its board
edge. Verified non-vacuous — it fires on REV A's J5 (6.61 mm) and passes
J8/J9 (0.45 mm each).

## Cost reduction for the next order — where the money actually is

Board **area is not a lever**: JLC's 2-layer prototype price is one flat
tier up to 100 × 100 mm, and 92 × 64 mm sits inside it. The REV A invoice
line was `PCB $2.00` for 5 pieces, with `Panel: $0.00` and
`Large Size: $0.00`. Shrinking the outline saves exactly $0.

The real drivers, from the REV A quote (PCBA $79.47 of the $81.27 total):

| Line item                  | REV A  | Lever                                          |
| -------------------------- | ------ | ---------------------------------------------- |
| Extended components fee    | $42.98 | ~15 Extended lines × ~$3 — swap lines to Basic |
| Components (26 items, ×2)  | $17.65 | scales with assembly qty                       |
| Setup + stencil            | $9.71  | fixed per order — amortize over more boards    |
| Hand-solder + manual (THT) | $7.01  | fixed once any THT line is assembled           |

**Biggest lever — assemble 5 instead of 2.** The setup, stencil and the
whole $42.98 Extended fee are charged *per order*, not per board. Quoted
during the REV A session: qty 2 = $82.17 ($41.09/board), qty 5 = $105.43
($21.09/board). Nearly half the per-board cost for 28% more money.

**Second lever — Extended → Basic swaps.** Candidates to re-check on the
live parts page at order time (tiers drift; verify, don't assume):

| Line                      | Current                     | Note                                                   |
| ------------------------- | --------------------------- | ------------------------------------------------------ |
| 27R 0402 (RT1–RT5)        | C25100                      | plain E24 value — a Basic 0402 27R is likely available |
| 8.2k 0402 (VBUS dividers) | C413094                     | Basic C25924 was industry-dry at REV A time; re-check  |
| LED green 0603            | C12624                      | JLC stocks Basic 0603 LEDs; hue may differ             |
| 1x20 socket / headers     | C124410 / C124376 / C124375 | check Basic THT equivalents with identical land        |

Do **not** chase these: the 0.1 Ω 1206 shunt (C844896 — tolerance feeds
current-sense accuracy), the B3S-1000 button (C2733655 — land-pattern
specific), and the ICs/connectors (USBLC6, INA180, TPS2051B, USB-C, USB-A,
JST-SH, 1.27 mm headers), which have no Basic equivalents.

## Open advisories (from the pre-order audit, not defects)

- **DEV_DP bridge asymmetry** — J9's D+ orientation bridge is ~6.3 mm over
  two vias on B.Cu while D− is a ~3.1 mm F.Cu rail, because the Type-C
  D+/D− pad pairs interleave. Irrelevant at PIO-USB full speed; would
  matter at 480 Mbps.
- **VBUS_NET necks to 0.2 mm for 3.4 mm at J8** — forced by the 0.25 mm gap
  to the adjacent netless pad. Fine below ~1.5 A; widen the B.Cu side or
  add a parallel via if the bench load grows.
- **J8/J9 mouths sit 0.45 mm inside their edges** (the connector body, not
  the courtyard, is what's flush). No problem observed on REV A hardware;
  the new guard's 1.0 mm tolerance accepts it deliberately.
- **`PICO1`/`PICO2` exist only in the BOM/CPL**, not on the board or silk —
  they are the two halves of the single `PICO` socket footprint, split so
  JLC assembles both 1×20 rows. An assembler cannot locate them by silk.
  Consider real per-row footprints in a future revision.
- **U_INA219_ALT, D_J9_BUSPWR, C_NRESET are DNP by design** and correctly
  absent from the JLC BOM. The empty footprints on REV A hardware are
  expected, not assembly errors. Host current sensing runs through the
  populated R_SHUNT → U_ISNS (INA180A1, ×20) → GP26 path, scale 2.0 V/A.
