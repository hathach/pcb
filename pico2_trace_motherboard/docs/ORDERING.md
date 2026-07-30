# JLCPCB Ordering Guide — Pico 2 Trace Motherboard REV A

Full assembly (SMT + through-hole). Board revision `6d67559`; files from commit
`e0a6686`. The three upload files are staged in `~/Desktop/jlcpcb-order/` and
live in the repo at `fab/pico2_trace_gerbers.zip`, `docs/BOM_jlc.csv`,
`docs/CPL_jlc.csv`. Gerber zip sha256 `abad617c…eaea9d7` (see `fab/MANIFEST.txt`).

## 1. PCB quote

1. jlcpcb.com → **Order now** → drag `pico2_trace_gerbers.zip` onto the upload box.
2. Wait for the preview render, then confirm it detected: **2 layers, 92 × 64 mm**,
   rounded-rect outline, 4 mounting holes.
3. Settings (everything not listed stays default):

| Setting             | Value                      | Note                                 |
| ------------------- | -------------------------- | ------------------------------------ |
| Base material       | FR-4                       |                                      |
| Layers              | 2                          | auto                                 |
| PCB Qty             | 5                          | minimum/cheapest tier                |
| Thickness           | **1.6 mm**                 | design assumes it                    |
| Outer copper weight | **1 oz**                   | trace ampacity was computed for 1 oz |
| Surface finish      | HASL (lead-free)           | ENIG optional, cosmetic              |
| Via covering        | Tented                     |                                      |
| Solder mask / silk  | any colour                 | green ships fastest                  |
| Remove order number | "Specify location" is free | or pay to remove                     |

## 2. PCB Assembly

1. Toggle **PCB Assembly**. Assembly side = **Top** (all 51 parts are top-side).
   Assembly qty **2 or 5** (2 = JLC minimum, halves part cost; 5 = all boards).
   If the UI distinguishes Economic vs Standard: these THT parts are listed by
   JLC as wave-solder compatible under both — accept whatever it selects, the
   live price is authoritative.
2. Next page → upload **BOM** = `BOM_jlc.csv`, **CPL** = `CPL_jlc.csv`.
3. **Parts matching page** — all 27 lines carry verified LCSC numbers and
   should auto-match. Check these specifically:
   - **Low-stock risks** (numbers seen at lookup, 2026-07-29): J8/J9 Molex
     micro-B `C132560` (~12 units — 5 boards need 10), J_STEMMA `C160404`
     (~59), J5 GCT USB-A `C6307429` (~54). If any shows out-of-stock:
     deselect that line and hand-solder it later, or use JLC **Global
     Sourcing** for it.
   - J3/J6 are **genuine Samtec** (`C20728453` / `C448647`, ~$5–8 ea). A cheap
     1.27 mm SMD keyed clone is acceptable ONLY if its drawing checks out:
     SMD termination (not THT), body small enough for the 0.67–0.70 mm
     neighbour gaps, keyed shroud.
   - ~20 Extended lines ⇒ ~$3/reel one-time setup ≈ $60. To trim, deselect
     connector lines and hand-solder those (each deselect saves $3 + part cost).
4. **Component placement preview — the critical screen.** JLC's rotation
   conventions differ from KiCad's; their preview is authoritative. Verify
   against `docs/board renders` / the repo renders:
   - `U_HSW`, `U_ISNS` (SOT-23-5), `ESD_H`, `ESD_D` (SOT-23-6): pin-1 corner.
   - `D_VSYS`, `D_J9_BUSPWR` (SOD-123): **cathode bar must match the silk bar**.
     D_VSYS cathode faces VSYS (toward the Pico row); D_J9_BUSPWR cathode
     faces VBUS_NET (away from J9).
   - `LED_PWR`, `LED_USER` (0603): cathode toward its GND resistor side.
   - `J5`/`J8`/`J9` receptacles: openings must face OFF the board edge.
   - `PICO1`/`PICO2`/`J1B`/`J2B` sockets and all pin headers: symmetric,
     rotation mechanically harmless — just confirm they sit ON their rows.
   Rotate anything wrong in their editor (it saves per-order).
5. Solder-paste/stencil and other assembly defaults: accept.

## 3. Checkout

- Review the order summary: bare-PCB ≈ $2–5, assembly fee + parts + Extended
  setup fees on top; shipping choice is yours.
- Save to cart → **you** click Buy/Pay.

## 4. Order separately (not assembly items)

| Item                      | Note                                                                          |
| ------------------------- | ----------------------------------------------------------------------------- |
| 1x03 pin header ×3/brd    | JP1/J_UART/J10 (C124376) — deselected from PCBA, hand-solder                  |
| 1x02 pin header ×3/brd    | JP2/JP3/JP4 (C124375) — deselected from PCBA, hand-solder                     |
| 4× jumper shunts, 2.54 mm | JP1–JP4 (fit JP2/JP3/JP4 by default; JP1 to taste)                            |
| JST-SH cable              | JST-SH→dupont (for J10) or JST-SH→JST-SH (for J7); ships with RPi Debug Probe |
| M3 screws/standoffs ×4    | MH1–MH4                                                                       |

Assembly-config history (2026-07-29/30 order sessions): deselecting ALL THT
header lines cut the Economic PCBA quote $82.17 → $71.63 per 2 boards (parts
−$3.53, hand-solder labor −$3.58, manual assembly −$3.43; lead time 2-3 d →
1-2 d; the $42.98 Extended-parts fee did NOT change — JLC charges it on
matched lines regardless of deselection). Final config per user decision:
**sockets (PICO1/PICO2/J1B/J2B) back IN** — the carrier is the point of the
board — **pin headers stay out** (trivial to hand-solder, and any single THT
line re-adds the ~$7 labor fees anyway, so keeping the 6 tiny headers out
costs nothing extra once the sockets are back).

## 8. J8 micro-B → USB Type-C (2026-07-30, pre-order board change)

`J8` (5V-IN power port) was rebuilt as USB Type-C before ordering: LCSC
**C165948** (HRO TYPE-C-31-M-12, JLC **Basic** — cheaper than the Molex
micro-B it replaces) + **R_CC1/R_CC2** 5.1 kΩ 0402 Rd pull-downs (LCSC
**C25905**, Basic; any in-stock 5.1k 0402 substitutes fine — the Type-C spec
allows ±10%). New fab zip + BOM_jlc/CPL_jlc regenerated — re-upload ALL
THREE files when re-ordering; the old Y-revisions in the JLC cart predate
this change. Gates at regeneration: DRC 0 unconnected + the 2 known silk
warnings only, ERC warnings-only, model↔schematic netlists match, GND pour
union-find = 1 component.

All are LCSC items too — add to the same cart to combine shipping.

## 5. After ordering

- Note the JLC order number next to `fab/MANIFEST.txt` for traceability.
- On arrival: `docs/BRINGUP.md` — first-power checklist, jumper table, then
  the trace bring-up ladder (48 → 80 → 120 → 150 MHz core).

## 6. Order-time part decisions (stock fluctuates — the live parts page arbitrates)

BOM primaries are the preferred parts. If the parts page shows a primary
out-of-stock, search the fallback (magnifier icon on that row). Prefer
primary whenever both are buyable.

| Line             | Primary (preferred)            | Fallback (verified)                        | Rule                                    |
| ---------------- | ------------------------------ | ------------------------------------------ | --------------------------------------- |
| J3 2x10 1.27mm   | C41360882 XUNPU (measured fit) | C20728453 Samtec (+$16)                    | primary; Samtec only if XUNPU dry (360) |
| J6 2x5 1.27mm    | C3975188 HCTL (measured fit)   | C448647 Samtec (+$7)                       | primary                                 |
| 100n 0402        | C1525 (Basic)                  | C307331 Samsung 50V (Basic)                | either                                  |
| 22u 0805         | C45783 (Basic)                 | C6119898 HRE (Ext)                         | primary if buyable                      |
| 22R 0402         | C25092 (Basic)                 | C114765 Yageo (Ext)                        | primary if buyable                      |
| 1.5k 0402        | C25867 (Basic)                 | C114759 Yageo (Ext)                        | primary if buyable                      |
| 15k 0402         | C25756 (Basic)                 | C114761 Yageo (Ext)                        | primary if buyable                      |
| 100k 0402        | C25741 (Basic)                 | C60491 Yageo (Ext)                         | primary if buyable                      |
| 1k 0402          | C11702 (Basic)                 | C106235 Yageo (Ext)                        | primary if buyable                      |
| 8.2k 0402        | C413094 Panasonic (Ext)        | C25924 (Basic, if recovered)               | fallback preferred if back in stock     |
| ESD SOT-23-6     | C7519 ST genuine (Ext)         | C2687116 UMW clone (Ext, pin-1 unverified) | primary                                 |
| LED 0603 green   | C12624 (Ext)                   | C2289 yellow-green (Ext, hue differs)      | primary                                 |
| Buttons B3S-1000 | C2733655 Omron (Ext)           | C180420 Omron B3S-1000P (same land)        | either (same part, diff packaging)      |
| 1x03 header      | C124376 Ckmtw (Ext)            | C49257 BOOMELE (Ext)                       | either                                  |
| 1x20 socket x4   | C124410 Ckmtw (Ext)            | C2905423 Kinghelm 8.5mm (Ext)              | either                                  |
| Micro-B J8/J9    | C132560 Molex genuine (Ext)    | none verified — Global Sourcing if dry     | primary (13k stock at last check)       |
| STEMMA           | C51940130 XYECONN (measured)   | C160404 JST genuine (if recovered)         | either; genuine preferred if buyable    |

## 7. Live-session substitutions (2nd parts-page snapshot, 11 flagged rows)

The UI's part picker (magnifier per row) shows live warehouse stock inline —
it outranks every external lookup. Universal escape: DESELECT the row and
hand-solder that part (recommended outright for J8/J9 — no verified clone).

| Flagged row      | Take in picker                                      |
| ---------------- | --------------------------------------------------- |
| 100n C1525       | C307331 (Samsung 50V, Basic) or any 0402 X7R 100n   |
| 22R C25092       | C114765 Yageo                                       |
| 15k C25756       | C114761 Yageo                                       |
| 1k C11702        | C106235 Yageo                                       |
| 8.2k C413094     | search "8.2k 0402 1%", any in stock                 |
| LED C12624       | any green 0603 (C2289 = yellow-green hue)           |
| ESD C7519        | C2687116 UMW clone                                  |
| 1x03 C124376     | C49257 BOOMELE                                      |
| Sockets C124410  | C2905423 Kinghelm 8.5mm                             |
| Buttons C2733655 | C180420 Omron B3S-1000P (same land)                 |
| J8/J9 C132560    | exact Molex 47346 only; else DESELECT + hand-solder |

Before substituting, hover one ⚠ icon: if the tooltip says "confirm"/"check"
rather than out-of-stock, those rows may only need their checkbox ticked.
