# Pico 2 Trace Motherboard — Bring-Up Note

## Board summary

92.0 × 64.0 mm (`Edge.Cuts` centreline; the 92.1 × 64.1 mm figure quoted
in earlier drafts is the bounding box, 0.1 mm bigger on each axis because
the outline is drawn with a 0.1 mm-wide stroke that extends 0.05 mm past
the centreline on every side), 2-layer FR4, 1.6 mm. Design-complete,
DRC-clean (0 unconnected; see "First-power checklist" below for the 2
accepted pre-existing silk violations).

**"Top = all signal routing, bottom = solid GND pour" is not what got
built — corrected here.** Measured directly off the board (`pcbnew`,
per-net/per-layer track length):

- **F.Cu is the one that's nearly a solid plane**: 3657.30 mm² of GND
  pour, 3430.96 mm² of it (94%) in one single island. Component
  placement and the five trace signals (`TRACECLK`/`TD0`–`TD3`) also
  live here.
- **B.Cu carries roughly half of all signal routing** — 1090.63 mm of
  the board's 2229.53 mm total track length (48.9%), including several
  of the "important" nets: `P3V3` 223.53 mm, `VBUS_NET` 131.19 mm,
  `NRESET` 99.81 mm, `VBUS_SEL` 80.25 mm, `I2C0_SDA`+`I2C0_SCL` 148.02 mm
  combined, `SWDIO` 67.39 mm. B.Cu's GND pour is correspondingly
  fragmented — 3730.16 mm² split across 18 islands, the largest only
  2328.38 mm² (62%) — a patchwork, not a plane.
- **What does hold**: the five trace nets are **100% F.Cu, with the
  nearest non-trace B.Cu track 1.27 mm away** (an `NRESET` segment) —
  zero B.Cu tracks pass within 1 mm of the bundle. The trace group's
  return-path reference is intact even though the "solid bottom plane"
  framing for the rest of the board was wrong.

| Ref          | Purpose                                                                |
| ------------ | ---------------------------------------------------------------------- |
| `PICO`       | Pico 2 / Pico socket (2× inner 1×20 THT female, hand-soldered)         |
| `J1B`, `J2B` | Per-pin breakout rows, pin-for-pin with the Pico header                |
| `J3`         | MIPI-20 Cortex Debug+ETM — SEGGER J-Trace (SWD + 4-bit parallel trace) |
| `J5`         | USB-A receptacle — PIO-USB **host** port (GP20/21)                     |
| `J6`         | Cortex Debug 2×5 — plain J-Link (SWD only, no trace)                   |
| `J7`         | JST-SH 3-pin — Raspberry Pi Debug Probe ("pico-debug") jack            |
| `J8`         | USB **Type-C**, power-only — 5 V input for host-stack work             |
| `J9`         | USB **Type-C** — PIO-USB **device** port (GP18/19)                     |
| `J10`        | 3-pin dupont header — SWD (SWCLK/GND/SWDIO)                            |
| `J_UART`     | UART0 console (GP12 TX / GP13 RX / GND)                                |
| `J_STEMMA`   | STEMMA-QT / Qwiic I2C0 (GP8 SDA / GP9 SCL)                             |
| `JP1`–`JP4`  | Jumpers — see the jumper table below                                   |
| `SW1`        | RUN reset button                                                       |
| `SW_USER`    | User button (GP14 → GND)                                               |
| `TP1`–`TP3`  | Probe points on the PIO-USB host D+/D−/GND                             |
| `MH1`–`MH4`  | M3 mounting holes                                                      |

## Jumper settings

| Jumper | Silk                         | Fitted position  | Meaning                                                                                                                                                                                                   |
| ------ | ---------------------------- | ---------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `JP1`  | `5V SEL` / `JTRACE` / `VBUS` | `1-2` = `JTRACE` | J-Trace's MIPI-20 5 V pins power `VBUS_SEL` — **and, via `D_VSYS`, the Pico itself** (`VBUS_SEL`→`D_VSYS`→`VSYS`); pin 40/`VBUS_NET` stays free, so the module's own micro-USB can act as an **OTG host** |
|        |                              | `2-3` = `VBUS`   | The board's own `VBUS_NET` (module micro-USB / J8 / ext-5 V) powers `VBUS_SEL` and the Pico (via pin 40, as before) — **this is the 5 V source select**                                                   |
| `JP2`  | `GUARD GP0`                  | fitted (default) | GP0 tied to GND (grounded guard next to TRACECLK)                                                                                                                                                         |
|        |                              | removed          | GP0 freed for other use                                                                                                                                                                                   |
| `JP3`  | `GUARD GP6`                  | fitted (default) | GP6 tied to GND (grounded guard next to the trace block)                                                                                                                                                  |
|        |                              | removed          | GP6 freed for other use                                                                                                                                                                                   |
| `JP4`  | `VBUS DET`                   | fitted (default) | Enables the native VBUS-detect tap (VBUS_NET → divider → GP16)                                                                                                                                            |
|        |                              | removed          | GP16 freed, tap disconnected                                                                                                                                                                              |

## Power rules

- **Exactly one hard 5 V source on `VBUS_NET` at a time.** `VBUS_NET` is
  a single hard-tied node (Pico pin 40 = module micro-USB VBUS = J8 =
  external-5 V injection) — it cannot be diode-isolated or
  switch-broken, so doubling up sources on it (e.g. the module's own
  micro-USB plugged into a PC *and* J8 powered) is a real short between
  two supplies. This is unchanged by the additions below.
- **`D_VSYS` (added, always populated)** diode-ORs the JP1-selected rail
  (`VBUS_SEL`) into the Pico's `VSYS` pin, in parallel with the Pico
  module's own internal VBUS→VSYS Schottky. The two diodes form a
  genuine diode-OR into `VSYS`: whichever supply (module micro-USB via
  pin 40, or the JP1-selected rail via `D_VSYS`) is actually present
  wins, and neither can back-feed the other — **no jumper position or
  cable combination can make two supplies fight**, which is a safer
  arrangement than the original `DESIGN.md` §7 spec (a hard tie between
  J-Trace 5 V and `VBUS_NET`). The ~0.3 V Schottky forward drop on
  `VSYS` is harmless — the Pico's `VSYS` input accepts 1.8–5.5 V.
- **`JP1 = JTRACE`**: J-Trace's MIPI-20 5 V pins feed `VBUS_SEL` (and,
  through the host load switch, `J5`) **and now power the Pico via
  `D_VSYS`→`VSYS`**, while `VBUS_NET`/pin 40 stays free — which **frees
  the Pico's own micro-USB to act as an OTG host** (its VBUS is then
  sourced from pin 40 instead of being an input).
- **`JP1 = VBUS`**: the board runs from the module micro-USB (device),
  J8, or an external-VBUS injection; `VBUS_SEL` and `VBUS_NET` are the
  same node in this position (shorted by the jumper), so `D_VSYS` and
  the Pico's own internal diode simply conduct in parallel from the same
  source — harmless. J-Trace's 5 V pins are disconnected from
  `VBUS_SEL`.
- J-Trace's 5 V rail is current-limited (a few hundred mA) — for
  anything power-hungry downstream, use J8 or a strong USB supply
  instead.
- `LED_PWR` (the power LED) sits on `VBUS_SEL`, so it indicates
  whichever rail JP1 has selected — **this reading is now correct** for
  both jumper positions, since JP1=JTRACE actually powers the whole
  board (Pico included) rather than just the host port.

## As-built additions (commit `6d67559`)

Four parts added, none of them change any existing net's *function*,
only add feed/bypass paths:

- **`D_VSYS`** (B5819W Schottky, SOD-123): pad 1 (cathode) = `VSYS`,
  pad 2 (anode) = `VBUS_SEL`. See "Power rules" above.
- **`C_P3V3_1`**, **`C_P3V3_2`** (100 nF/16 V, 0402): `P3V3` → `GND`
  decoupling — one near Pico pin 36 (the 3V3 output), one at
  `J_STEMMA`'s 3V3 tap.
- **`C_HSW_IN`** (100 nF/16 V, 0402): `HOST_5V_IN` → `GND`, at `U_HSW`
  pin 5 (IN) — TI's recommended input bypass for the TPS2051B load
  switch.
- **`J5` pad 5** (the USB-A receptacle's 2 mechanical mounting-post
  pads) is now tied to `GND` (previously unconnected) — proper shield
  grounding for the host port.

Adding the 4 new footprints reshaped the ground pour enough to strand
**two GND-pour islands** from the main plane (caught by DRC
`unconnected_items`, not by visual inspection — see the comments around
`_STITCH_VIAS_FRAGMENT_FIX`/`_STITCH_VIAS_PAD_ESCAPE` in `hw/pour.py`
for the full graph-connectivity diagnosis). Healed with:
- a stitching via at `(45.39, 32.0)` — grounds copper directly under the
  seated Pico module, near PICO pin 23;
- a 3-segment F.Cu bridge stub with transition vias at `(52.0, 15.0)`
  and `(49.205, 16.9)` — near `J_STEMMA`/`J_UART`/`R_NVD`/`C_P3V3_2`.

Both mechanisms live in `hw/pour.py` (`_STITCH_VIAS_FRAGMENT_FIX`,
`_GND_STUBS`, `_STITCH_VIAS_PAD_ESCAPE`). Verified with a union-find
over all GND copper (vias, same-layer tracks, and pads, since THT/plated
pads bridge F.Cu↔B.Cu just like vias do): **connected components = 1**
(38 F.Cu+B.Cu islands, 7387.46 mm² combined).

## The 5 SWD entry points

Five connectors reach the same shared SWDIO/SWCLK/GND net: `J3` (MIPI-20),
`J6` (Cortex 2×5), `J7` (JST-SH), `J10` (3-pin dupont) — plus the Pico's own
onboard JST-SH debug port, which is the *source* the other four fan out
from, not a redundant sixth entry point.

- **One probe at a time.** All four board-side connectors are wired in
  parallel on the same net — driving two probes simultaneously is a bus
  fight, not a "pick either" situation.
- **`J10` or `J7` must be cabled to the Pico's own onboard JST-SH debug
  port for any of the four connectors to reach the target at all.** The
  board only fans the SWD signals *out*; nothing on the board generates
  them. Without that one jumper cable in place, `J3`/`J6`/`J7`/`J10` are
  all dead.
- The Pico's onboard debug port is JST-SH 1.0 mm — so a `J10` (dupont) →
  Pico cable needs a **JST-SH-to-dupont** cable (this ships with the
  Raspberry Pi Debug Probe). A `J7` → Pico cable is JST-SH-to-JST-SH
  (also ships with the Debug Probe).

## Assembly notes

- **Full assembly (SMT + THT) is the chosen JLC ordering option.** JLCPCB's
  hand-soldering ("plug-in") service places the THT parts — the Pico
  socket rows (`PICO1`/`PICO2`), `J1B`, `J2B`, `JP1`–`JP4`, `J_UART`,
  `J10` — alongside the SMT reflow parts in one JLC assembly order. See
  `docs/BOM_jlc.csv`/`docs/CPL_jlc.csv` for the full assembly BOM/CPL and
  `docs/BOM.csv` for per-part sourcing notes.
- The hand-solder list below now only applies **if ordering bare boards**
  (no assembly service) instead:
  - All THT parts (`PICO` socket, `J1B`, `J2B`, `JP1`–`JP4`, `J_UART`,
    `J10`, + `J5`'s 2 mechanical mounting posts) would be hand-soldered by
    the user — see `docs/BOM.csv` for per-part sourcing.
- GND pads on THT parts use thermal relief spokes rather than a solid
  copper flood, so they solder normally with a hand iron (a solid-flood tie
  into the ground plane would act as a heatsink and make hand-soldering
  those pads difficult or impossible) — this also helps JLC's hand-solder
  line for the same reason.
- Everything else is SMT, reflow or hand-soldered as the assembler prefers.
- If JLC's ordering UI forces **Standard** (not Economic) PCBA once THT
  parts are in the BOM, that's expected on some JLC configurations —
  proceed with Standard. (JLCPCB's own parts-library listing for the three
  new THT connectors marks them wave-solder-compatible under both Economic
  and Standard PCBA, so Economic may also be offered; either way, confirm
  whichever assembly type JLC selects at checkout.)

## First-power checklist

1. **Visual inspection** — no solder bridges, especially on the 1.27 mm
   `J3`/`J6` shroud pads and the 0.1 Ω `R_SHUNT` (1206). Confirm the 2
   accepted `silk_edge_clearance` DRC violations are cosmetic only (silk
   text clipped by the board edge — re-verify with `kicad-cli pcb drc
   --format json` if in doubt; expect exactly those 2 and 0 unconnected).
2. **Continuity check** — VBUS_NET, GND, P3V3 not shorted to each other
   before powering.
3. Seat the Pico (or Pico 2) in the socket, `JP1 = VBUS`, `JP2`/`JP3`
   fitted (guards on), `JP4` fitted (VBUS-detect tap enabled).
4. Power from the module's own micro-USB (device, from a PC). Confirm the
   power LED (`LED_PWR`) lights.
5. Probe `P3V3` at a breakout pin — expect 3.3 V.
6. Attach a probe to `J7` or `J10` (cabled to the Pico's onboard debug
   port, per above) and read the SWD target ID (e.g.
   `JLinkExe -device RP2350 -if SWD -speed 4000` → `id`, or `openocd`
   equivalent). Confirms SWD fan-out end to end before trusting `J3`/`J6`.
7. Confirm USB enumeration: plug the module micro-USB into a PC and check
   `lsusb`/Device Manager for the expected VID:PID of whatever firmware is
   loaded.

## Trace bring-up ladder

**This section supersedes stale guidance in `DESIGN.md`.** The J-Trace PRO
V2 is **in-spec to 100 MHz TRACECLK, ~120 MHz achievable with sampling-delay
tuning** (SEGGER's own published V2 best; the 150 MHz on current product
pages is V3/V4 hardware). The ~40 MHz cliff recorded in the
original fly-wire handoff (`PICO2_TRACE_PCB_HANDOFF.md`) was a *fly-wire
signal-integrity limit, not a probe limit*. This PCB (source-terminated,
short, GND-guarded — see DESIGN.md §5.4) should be pushed well past that
old cliff.

Run the ladder at **48 → 80 → 120 → 150 MHz core** (TRACECLK = core/2, so
24/40/60/75 MHz TRACECLK), capturing at each rung with the repo's
`etm-trace` skill:

1. Idle blinky first at each rung — confirms the link is alive before
   loading it.
2. Then `TRACE_ETM` `cdc_msc` at each passing rung — **the USB enumeration
   burst is the killer test** (dense, bursty trace data; far more demanding
   than blinky's steady low rate).
3. On failure, bisect with `--trace-width 1/2/4` and `--trace-timing` (per
   DESIGN.md §13's validation plan) before concluding the rung is bad —
   narrow the fault to a specific trace line or a timing margin instead of
   a blanket "clock too high."
4. Accept a rung at 3/3 full-total captures; record the final achieved
   rate here and in the `etm-trace` skill's board table.

### Result (2026-08-21, first bring-up)

**PASS at 180 MHz core / 90 MHz TRACECLK, width 4** — beyond the ladder's
top rung, on the same J-Trace PRO V2. The one required setting is **data
sampling +5 ns** (`Project.SetTraceTiming (5000, 5000, 5000, 5000)`,
committed in the TinyUSB ozone reference): under the cdc_msc enumeration
burst the eye passes at +4000..+5000 ps (3/3 each) and is dead at
<= +3000 ps; TD=0 (the fly-wire's working value at 24 MHz TRACECLK) does
not decode at 90 MHz. Zero overflow across all passing runs, 15M
fetches/10 s full-quality profiles. Intermediate rungs (80/120/150) were
skipped — 48 smoke-passed, then straight to the 180 MHz goal.

Known flake: an occasional *instant* unknown-packet death (offset
~0x10-0x6C) right as the stream arms, while the bootrom still runs on its
boot clock — retry the capture; it is not a board or timing fault. The
"Known SI limitation" below (J1B return-path gaps) never surfaced: no
mid-stream decode failures in any accepted run.

### TRACECLK ceiling (2026-08-21, same session)

The headroom ladder was run the same day: **120 MHz TRACECLK (240 MHz
core, vreg 1.15 V) is the maximum** — cdc_msc 3/3 at TD +3500 with 12 mA
fast-slew pads asserted pre-PLL-switch. **>= 125 MHz TRACECLK is a hard
probe wall**: 125/130/140/150 MHz TRACECLK all failed at every sample
delay (full-UI 500 ps sweep at 125), at trace width 1, and with fast
pads — a razor edge between 120 (≈2 ns open eye) and 125 MHz (closed)
consistent with the V2's real capability, not with this board's SI (which
the wall's sharpness exonerates: board-limited eyes close gradually).
Post-hoc spec check: SEGGER's in-spec max trace clock is 100 MHz, and
their only published faster V2 number is "up to 120 MHz ... with a slight
adjustment of sampling delays in J-Trace PRO V2" (J-Trace Isolator page)
— this rig reproduced that number exactly; the "150 MHz" this document's
earlier revision attributed to the V2 is the V3/V4 product-page figure.
A V3+ probe is the lever if >120 MHz TRACECLK is ever truly needed. The
board itself is clean at every rate the probe can sample.

## Known SI limitation (document honestly)

The bottom GND pour has **~0.9–1.2 mm gaps directly beneath all five trace
signals** where they cross `J1B`'s through-hole row: 1.7 mm THT pads at
2.54 mm pitch leave ~0.22 mm of pour between pads, below the 0.2 mm minimum
fill thickness, so the zone filler prunes that band rather than leaving a
sliver of unsupported copper.

This forces a return-path detour around each gap. Worst case is **TD2 at
≈5.25 mm**; TRACECLK/TD0 are ≈0.15–0.2 mm; TD1/TD3 are ≈2.7 mm. Assessed
**acceptable**: the crossing is perpendicular to the trace bundle (not a
running-parallel gap), and the worst-case detour is ~30 ps against 1–2 ns
signal edges. **Listed here as suspect #1 if high-rate trace decode fails**
— the fix, if ever needed, is to relocate or thin the `J1B` breakout row so
it no longer crosses the trace group.

Separately: the 2-layer stackup means **no controlled 50 Ω impedance**
anywhere on the board (a 4-layer stackup would be needed for that). The
trace runs are electrically short (~24 mm, ~144 ps one-way) so reflections
are dominated by the 27 Ω source termination at the Pico socket pins, not
by the uncontrolled-impedance trace geometry.

## Pre-fab checklist

Confirm before ordering:

- [ ] `J3`/`J6` shrouded-header sourcing: the chosen part is **SMD, not
      THT** — many cheap 1.27 mm shrouded headers are THT and will not fit.
- [ ] `J3`/`J6` shroud body size checked against the FTSH-110/FTSH-105
      drawing the footprint is dimensioned from — a larger clone body can
      foul neighbouring connectors on the debug edge (measured margin:
      `J6`↔`J10` courtyard gap is 0.700 mm, `J10`↔`J7` is 0.670 mm).
- [ ] `J3`/`J6` shroud is **keyed** so the J-Trace ribbon cannot be
      inserted backwards.
- [x] Board ≤100 mm on its longest edge (92.1 mm bbox / 92.0 mm
      centreline) — qualifies for JLC's cheap prototype tier.
- [x] 2-layer.

## Firmware / BSP interface

GPIO map (`hw/bsp/rp2040/boards/raspberry_pi_pico2`, see DESIGN.md §6/§11
for the full rationale):

| Function                                        | GPIO(s)    |
| ----------------------------------------------- | ---------- |
| Trace (TRACECLK/TD0–3, funcsel 9)               | GP1–GP5    |
| GND guards (`JP2`/`JP3`)                        | GP0, GP6   |
| UART0 console (TX/RX)                           | GP12, GP13 |
| I2C0 (STEMMA-QT, SDA/SCL)                       | GP8, GP9   |
| PIO-USB host (D+/D−, `J5`)                      | GP20, GP21 |
| PIO-USB device (D+/D−, `J9`)                    | GP18, GP19 |
| `DEV_DP_PU_EN` — device D+ pull-up soft-connect | GP11       |
| Native VBUS-detect tap                          | GP16       |
| J9 device VBUS-detect                           | GP27       |

> GP27 threshold note (2026-07-30 review): with J9 unplugged, driving
> DEV_DP high (or enabling the GP11 pull-up) back-feeds `J9_VBUS` to
> ~2.6 V through ESD_D's I/O→VBUS steering diode, putting ~1.3 V on
> GP27. Treat "VBUS present" as `GP27 ≥ ~2 V` (divider gives 2.5 V at
> a real 5 V VBUS), never "nonzero".
| Host VBUS enable                                | GP17       |
| Host VBUS fault (open-drain)                    | GP15       |
| `ISENSE` — VBUS current-sense (ADC)             | GP26       |
| User LED                                        | GP10       |
| User button                                     | GP14       |

Keep GP0/GP6 as inputs whenever their guard jumper is fitted (driving them
against a grounded guard is a short). GP1–GP5 carry nothing else — no
pulls, LEDs, or other loading beyond the trace path.

`GP15` (`HOST_VBUS_FLT`) is the load switch's open-drain fault output
with **no external pull-up on the board** — the net ties only `PICO.20`
and `U_HSW.FLG`, nothing else. Firmware must enable the RP2350's
**internal** pull-up on this pin to read it; left as a bare input it will
float.
