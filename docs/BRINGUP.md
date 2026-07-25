# Pico 2 Trace Motherboard — Bring-Up Note

## Toolchain

**Verified 2026-07-24, KiCad 9.0.2.**

- `kicad-cli version` → `9.0.2`; `python3 -c "import pcbnew; print(pcbnew.Version())"` → `9.0.2` (system Python, no venv needed for `pcbnew`).
- Board scaffold: `pcbnew.BOARD()` scripted in-memory, placeholder 65×34 mm `Edge.Cuts` rectangle added, `SetCopperLayerCount(2)`, saved with `pcbnew.SaveBoard("pico2_trace.kicad_pcb", b)` — this also wrote a complete `pico2_trace.kicad_pro` / `.kicad_prl` (per `PLAN.md`, never hand-write the `.kicad_pro`).
- Baseline DRC gate (parsed JSON, per `PLAN.md` "Verified environment facts" — never trust exit code or stdout text):
  ```
  kicad-cli pcb drc --format json -o /tmp/drc.json pico2_trace.kicad_pcb
  python3 -c "import json;v=json.load(open('/tmp/drc.json'))['violations'];print('violations:',[x['type'] for x in v])"
  ```
  Result: `violations: []` (exit 0). Confirms the placeholder outline is required — DRC on an outline-less board would report `invalid_outline` and exit 5.

### SKiDL spike (Step 3/4 of Task 1)

Goal: determine whether SKiDL's `KICAD9` schematic target can be used to auto-generate the project schematic from `hw/netlist.py` later in the plan, or whether the schematic must be hand-drawn in eeschema.

- `python3 -m venv .venv && . .venv/bin/activate`
- `pip install -q skidl kinet2pcb kinparse` → succeeded (no `PIP_FAILED`). Installed `skidl==2.2.3` (`kinet2pcb`, `kinparse` also installed).
- Ran the generation spike inside the venv with `KICAD9_SYMBOL_DIR=/usr/share/kicad/symbols` exported:
  ```python
  import skidl
  from skidl import Part, Net, set_default_tool, KICAD9, generate_schematic
  set_default_tool(KICAD9)
  r1 = Part("Device", "R", value="8.2k", footprint="Resistor_SMD:R_0402_1005Metric")
  n = Net("N1"); n += r1[1]
  generate_schematic()
  ```
  Output: `SKIDL_GEN_OK ['skidl.kicad_sch']` — SKiDL wrote `./skidl.kicad_sch` (fixed filename `skidl.kicad_sch`, not project-name-based — a known SKiDL quirk, see below). SKiDL's own internal ERC pass on the generated file reported 1 error (`pin_not_connected` — expected, pin 2 of R1 was deliberately left dangling in the spike) and 2 warnings (`global_label_dangling`, `lib_symbol_mismatch` — a benign local-vs-library symbol note).
- Smoke-tested the generated file with the real KiCad 9 tool (outside the venv, system `kicad-cli`):
  ```
  kicad-cli sch erc skidl.kicad_sch; echo exit=$?
  ```
  Output: `Found 3 violations` / `exit=0` — matches SKiDL's own ERC count exactly (1 error + 2 warnings), and **`kicad-cli` parsed the file without a crash**. This is the pass/fail signal from the Task 1 brief: exit 0/5 and no parse crash → `auto`.

**Decision: `SCHEMATIC_MODE=auto`.** SKiDL 2.2.3 + `KICAD9` target produces a `.kicad_sch` that KiCad 9.0.2's own `kicad-cli sch erc` reads and checks cleanly. Later tasks may drive schematic generation from `hw/netlist.py` via SKiDL instead of hand-drawing in eeschema, falling back to manual drawing only for parts SKiDL can't express (see caveats below).

**Known SKiDL caveats to carry forward:**
- Output is a **flat** schematic (no hierarchical sheets) with **crude auto-placement** — fine for ERC/netlist purposes, not for a human-reviewable layout as-is.
- Output filename is fixed to `./skidl.kicad_sch` (actually `./<script-derived-name>.kicad_sch`, not the project name) — must be renamed/moved into place by the caller.
- Custom (non-stock) symbols must already exist in a resolvable library before generation; SKiDL does not create new symbols.

The spike's scratch outputs (`skidl.kicad_sch`, `skidl-erc.rpt`, `skidl.erc`, `skidl.log`, `skidl_REPL.*`) and the `.venv/` used to run it are not committed — see `.gitignore`.

## Board summary

92.1 × 64.1 mm, 2-layer FR4, 1.6 mm. Top = components + all signal routing;
bottom = solid GND pour under the trace group. Design-complete, DRC-clean
(0 unconnected; see "First-power checklist" below for the 2 accepted
pre-existing silk violations).

| Ref          | Purpose                                                                |
| ------------ | ---------------------------------------------------------------------- |
| `PICO`       | Pico 2 / Pico socket (2× inner 1×20 THT female, hand-soldered)         |
| `J1B`, `J2B` | Per-pin breakout rows, pin-for-pin with the Pico header                |
| `J3`         | MIPI-20 Cortex Debug+ETM — SEGGER J-Trace (SWD + 4-bit parallel trace) |
| `J5`         | USB-A receptacle — PIO-USB **host** port (GP20/21)                     |
| `J6`         | Cortex Debug 2×5 — plain J-Link (SWD only, no trace)                   |
| `J7`         | JST-SH 3-pin — Raspberry Pi Debug Probe ("pico-debug") jack            |
| `J8`         | micro-B, power-only — 5 V input for host-stack work                    |
| `J9`         | micro-B — PIO-USB **device** port (GP18/19)                            |
| `J10`        | 3-pin dupont header — SWD (SWCLK/GND/SWDIO)                            |
| `J_UART`     | UART0 console (GP12 TX / GP13 RX / GND)                                |
| `J_STEMMA`   | STEMMA-QT / Qwiic I2C0 (GP8 SDA / GP9 SCL)                             |
| `JP1`–`JP4`  | Jumpers — see the jumper table below                                   |
| `SW1`        | RUN reset button                                                       |
| `SW_USER`    | User button (GP14 → GND)                                               |
| `TP1`–`TP3`  | Probe points on the PIO-USB host D+/D−/GND                             |

## Jumper settings

| Jumper | Silk                         | Fitted position  | Meaning                                                                                                        |
| ------ | ---------------------------- | ---------------- | -------------------------------------------------------------------------------------------------------------- |
| `JP1`  | `5V SEL` / `JTRACE` / `VBUS` | `1-2` = `JTRACE` | J-Trace's MIPI-20 5 V pins power the board's VBUS_SEL rail                                                     |
|        |                              | `2-3` = `VBUS`   | The board's own VBUS net (module micro-USB / J8 / ext-5 V) powers VBUS_SEL — **this is the 5 V source select** |
| `JP2`  | `GUARD GP0`                  | fitted (default) | GP0 tied to GND (grounded guard next to TRACECLK)                                                              |
|        |                              | removed          | GP0 freed for other use                                                                                        |
| `JP3`  | `GUARD GP6`                  | fitted (default) | GP6 tied to GND (grounded guard next to the trace block)                                                       |
|        |                              | removed          | GP6 freed for other use                                                                                        |
| `JP4`  | `VBUS DET`                   | fitted (default) | Enables the native VBUS-detect tap (VBUS_NET → divider → GP16)                                                 |
|        |                              | removed          | GP16 freed, tap disconnected                                                                                   |

## Power rules

- **Exactly one hard 5 V source on the VBUS net at a time.** VBUS_NET is a
  single hard-tied node (Pico pin 40 = module micro-USB VBUS = J8 = external-
  5 V injection) — it cannot be diode-isolated or switch-broken, so doubling
  up sources (e.g. the module's own micro-USB plugged into a PC *and* J8
  powered) is a real short between two supplies.
- `JP1` keeps the J-Trace 5 V supply electrically separate from the USB
  side: with `JP1 = JTRACE`, the J-Trace's MIPI-20 5 V pins feed VBUS_SEL
  (and, through the host load switch, `J5`), while VBUS_NET stays free —
  which **frees the Pico's own micro-USB to act as an OTG host** (its VBUS
  is then sourced from Pico pin 40 instead of being an input).
- With `JP1 = VBUS`, the board runs from the module micro-USB (device), J8,
  or an external-VBUS injection — J-Trace's 5 V pins are disconnected from
  VBUS_SEL.
- J-Trace's 5 V rail is current-limited (a few hundred mA) — for anything
  power-hungry downstream, use J8 or a strong USB supply instead.

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

- All THT parts (`PICO` socket, `J1B`, `J2B`, `JP1`–`JP4`, `J_UART`, `J10`,
  + `J5`'s 2 mechanical mounting posts) are hand-soldered by the user —
  see `docs/BOM.csv` for per-part sourcing.
- GND pads on THT parts use thermal relief spokes rather than a solid
  copper flood, so they solder normally with a hand iron (a solid-flood tie
  into the ground plane would act as a heatsink and make hand-soldering
  those pads difficult or impossible).
- Everything else is SMT, reflow or hand-soldered as the assembler prefers.

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
**V2 is rated to 150 MHz TRACECLK** — the ~40 MHz cliff recorded in the
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
      foul neighbouring connectors on the debug edge.
- [ ] `J3`/`J6` shroud is **keyed** so the J-Trace ribbon cannot be
      inserted backwards.
- [x] Board ≤100 mm on its longest edge (92.1 mm) — qualifies for JLC's
      cheap prototype tier.
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
| Host VBUS enable                                | GP17       |
| Host VBUS fault (open-drain)                    | GP15       |
| `ISENSE` — VBUS current-sense (ADC)             | GP26       |
| User LED                                        | GP10       |
| User button                                     | GP14       |

Keep GP0/GP6 as inputs whenever their guard jumper is fitted (driving them
against a grounded guard is a short). GP1–GP5 carry nothing else — no
pulls, LEDs, or other loading beyond the trace path.
