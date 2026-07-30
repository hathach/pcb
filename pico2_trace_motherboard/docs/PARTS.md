# Parts Evaluation Notes

Per user directive: reuse Adafruit components for similar circuits where
possible (source: `MBAdafruitBoards/SCHEMATIC_LAYOUT_RULES_AND_TOOLS.md`,
read + extracted during Task 14). This note records the three circuit
blocks surveyed against Adafruit's typical part choices, the sourcing
policy that survey pulled in, and a fab-cost alternate for the Samtec
debug-header shrouds. Verdicts below were ruled during the survey and are
carried into `hw/netlist.py`/`hw/fp_lib.py` as committed; this file just
documents *why*.

## 1. Host-VBUS load switch: TPS2051B (kept) vs Adafruit's AP22802

| Part     | Vendor      | Package  | Open-drain fault/flag output    | Verdict                    |
| -------- | ----------- | -------- | ------------------------------- | -------------------------- |
| TPS2051B | TI          | SOT-23-5 | Yes (`FLG`, active-low)         | **Kept** — used as `U_HSW` |
| AP22802  | Diodes Inc. | SOT-23-5 | No — `EN`/`IN`/`OUT`/`GND` only | Rejected                   |

AP22802 is the load switch Adafruit uses in most of their own USB-host/hub
boards, and is otherwise a fine fit (current-limited, thermal-shutdown,
same SOT-23-5 footprint as `U_HSW`'s `loadswitch` fp_class). It was
rejected here because it has no fault/flag pin: DESIGN §8.1 requires GP15
to read the host port's over-current condition (open-drain fault flag),
which is a hard functional requirement, not a nice-to-have. TPS2051B (and
the TPS2052B/TPS2053B family, and AP2211/MIC2005-class parts with a flag
output) keep that pin; AP22802-class parts don't. **TPS2051B stays.**

## 2. USB ESD protection: USBLC6-2SC6 (kept) vs Adafruit's PRTR5V0U2X

| Part        | Vendor | Package  | D+/D− pin layout                            | Verdict                            |
| ----------- | ------ | -------- | ------------------------------------------- | ---------------------------------- |
| USBLC6-2SC6 | ST     | SOT-23-6 | Flow-through (`IO1`/`IO1B` opposite sides)  | **Kept** — used as `ESD_H`/`ESD_D` |
| PRTR5V0U2X  | NXP    | SOT-23-6 | Not flow-through (I/O in and out same side) | Documented alt, not used           |

Both are common USB2 ESD-protection arrays in the same SOT-23-6 footprint
(`esd6` fp_class); PRTR5V0U2X is the part Adafruit reaches for most often.
USBLC6-2SC6 was kept because its pinout lets the D+/D− trace pass straight
through the package (see the `_ESD_PADMAP` comment in `hw/netlist.py`:
`IO1`/`IO1B` are the same internal channel, i.e. feed-through pads) instead
of doubling back to the same side — better signal integrity at USB2 full/
high speed, with no cost or availability penalty. PRTR5V0U2X remains a
documented alternate (drop-in footprint-compatible) if USBLC6-2SC6 ever
goes out of stock.

## 3. VBUS current sense: INA180 (analog, populated) + INA219 adopted as a realized DNP option

The populated part (`U_ISNS`, INA180A1DBVR, SOT-23-5, analog output to
GP26/ADC) is unchanged — DESIGN §10 already names INA180/INA181 as the
default. The survey's job here was the DNP alternative: INA219 (I2C
current/power monitor) is Adafruit's signature current-sense part (they
sell it as a standalone breakout and use it across many of their own
boards), and DESIGN §10/§14 already called it out as an optional
I2C-bus alternative that frees GP26. Task 14b **adopted** it as a fully
realized DNP part (`U_INA219_ALT`) instead of the earlier placeholder
(borrowed `isense` footprint, all 5 pins no-connect):

| Aspect    | Before (Task 3-14a)                          | After (Task 14b)                                                                                                 |
| --------- | -------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| Footprint | `isense` (SOT-23-5) stand-in — wrong package | `sot23-8` (`Package_TO_SOT_SMD:SOT-23-8`) — real INA219 package                                                  |
| Pins      | All 5 pins `nc`                              | All 8 pins wired (IN+/IN− across `R_SHUNT`, GND/VS on the rails, SDA/SCL on I2C0, A0/A1 grounded → address 0x40) |
| `dnp`     | `True`                                       | `True` (unchanged — never populated)                                                                             |

Pinout source: TI SBOS448 (INA219 datasheet), Figure 8-1, "DCN Package
8-Pin SOT-23, Top View": pad1=IN+, pad2=IN−, pad3=GND, pad4=VS, pad5=SCL,
pad6=SDA, pad7=A0, pad8=A1; address-pin table (same datasheet) gives 0x40
for A0=A1=GND.

## 4. Sourcing policy: LCSC-first, JLC Basic-parts priority

Per the fab-cost user directive: prefer parts that are easy to find and
cheap to source. Concretely, for every part choice going forward:

- Check LCSC stock/price first, before any other distributor.
- Prefer JLCPCB "Basic Parts" library selections over "Extended" parts —
  Basic parts carry no per-part assembly fee on a JLC SMT order.
- This is the same priority order Adafruit's own rulebook (§13) recommends
  for its community-manufacturable boards, which is why it's adopted here
  alongside the Adafruit component-reuse survey above.
- None of the three parts surveyed above are blocked by this policy —
  TPS2051B, USBLC6-2SC6, and INA219 (DNP) are all common, multi-distributor
  parts with LCSC stock under multiple manufacturers' equivalents.

## 5. Samtec FTSH ↔ cheap LCSC 1.27 mm keyed-shroud alternate (J3/J6)

`J3` (MIPI-20) and `J6` (Cortex Debug 10) use locally-converted footprints
(`pico2_trace:FTSH-110-01-DV` / `pico2_trace:FTSH-105-01-DV`, `hw/fp_lib.py`)
drawn from Samtec's FTSH-110-01-*-DV / FTSH-105-01-*-DV mechanical
drawings — Samtec parts are the known-good reference for pad geometry and
keying, so the *footprint* stays Samtec-drawn. For BOM sourcing, though,
Samtec is a premium/low-volume-friendly distributor; generic 1.27 mm-pitch
keyed/shrouded box headers (2×10 for J3, 2×5 for J6) from other
manufacturers are commonly stocked on LCSC at a fraction of the cost and
are pin/mechanically compatible with the same footprint, since the shroud
keying and 1.27 mm pitch are the only geometric constraints that matter
for our pads. Carried forward from Task 2's review note: **verify the
chosen LCSC alternate's pad drawing against the Samtec drawing before
fab** (mechanical fit, not just pinout) — this is a Task 17 BOM action
(picking and recording the specific LCSC part number), not resolved here.
