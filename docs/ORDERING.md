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
| 4× jumper shunts, 2.54 mm | JP1–JP4 (fit JP2/JP3/JP4 by default; JP1 to taste)                            |
| JST-SH cable              | JST-SH→dupont (for J10) or JST-SH→JST-SH (for J7); ships with RPi Debug Probe |
| M3 screws/standoffs ×4    | MH1–MH4                                                                       |

All are LCSC items too — add to the same cart to combine shipping.

## 5. After ordering

- Note the JLC order number next to `fab/MANIFEST.txt` for traceability.
- On arrival: `docs/BRINGUP.md` — first-power checklist, jumper table, then
  the trace bring-up ladder (48 → 80 → 120 → 150 MHz core).
