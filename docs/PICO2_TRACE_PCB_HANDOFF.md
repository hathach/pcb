# Handoff: Pico 2 SWD + ETM-Trace Adapter PCB

Design a small PCB that a Raspberry Pi Pico 2 plugs into (or that plugs onto a
Pico 2) and presents a single ARM Cortex **Debug+ETM MIPI-20** connector
(Samtec FTSH-110, 0.05") carrying SWD + 4-bit parallel trace to a SEGGER
J-Trace. It replaces a fly-wire rig whose measured limits are documented
below — every number in this handoff was obtained on real hardware
(J-Trace PRO Cortex-M **V2**, nickname `jtrace`, Pico 2, TinyUSB cdc_msc).

## Why

Fly-wires cap the usable trace clock far below the chip's capability and
degrade with every handling cycle. Community consensus (Raspberry Pi forum
t=383655) and SEGGER's Pico 2 KB page agree: full-rate RP2350 trace needs a
proper trace board. SEGGER also state RP2350 streaming trace requires
**J-Trace PRO V3.0+**; our V2 measurements below are consistent with that.

## Electrical map (validated end-to-end on this rig)

RP2350 trace is **fixed** to these GPIOs (funcsel 9, bank 0 — no alternatives):

| Signal      | RP2350 GPIO | Pico 2 40-pin header pin | MIPI-20 pin |
|-------------|-------------|--------------------------|-------------|
| TRACECLK    | GPIO1       | 2                        | 12          |
| TRACEDATA0  | GPIO2       | 4                        | 14          |
| TRACEDATA1  | GPIO3       | 5                        | 16          |
| TRACEDATA2  | GPIO4       | 6                        | 18          |
| TRACEDATA3  | GPIO5       | 7                        | 20          |
| SWDIO       | dedicated   | 3-pin JST-SH DEBUG conn (center-right) | 2 |
| SWCLK       | dedicated   | 3-pin JST-SH DEBUG conn  | 4           |
| nRESET      | RUN         | 30                       | 10          |
| VTref 3V3   | 3V3_OUT     | 36                       | 1           |
| GND         | any GND     | 3, 8, 13, 18, 23, 28, 38 | 3,5,9,11,13,15,17,19 |
| SWO         | — none on RP2350 — leave MIPI-20 pin 6 NC | | 6 (NC) |

- MIPI-20 pin 7 is the connector key (NC), pin 8 NC (no TDI).
- **Route nRESET**: the bring-up relied on hardware pin reset (RESETPIN) to
  recover from states SYSRESETREQ cannot; J-Trace must be able to yank RUN.
- SWD comes from the Pico 2's JST-SH DEBUG connector (SWCLK/GND/SWDIO) — a
  JST-SH-3 footprint + short cable, or pogo pins, or solder pads. Do NOT
  share the trace ground return path exclusively; give SWD its own ground.

## Signal-integrity requirements (from measured failures)

Trace port is **DDR**: data on both edges of TRACECLK = clk_sys/2 (datasheet:
"the TPIU is a DDR output at half of clk_sys"). At the 150 MHz default that
is 75 MHz TRACECLK, 150 Mtransfer/s per pin, ~600 Mb/s total on 4 bits.

Measured on fly-wires (what the PCB must beat):

| TRACECLK | Result on fly-wires |
|----------|--------------------|
| 24 MHz (48 MHz core) | solid, any seating, full-width dense data |
| 30–36 MHz (60–72 core) | seating lottery: one seating did 72 5/5, the next failed |
| 40 MHz (80 core) | idle code only; dense data dies (width 4). Width 1 passes dense |
| 42+ MHz (84+ core) | dead at any sample timing (±6 ns global AND per-pin), any pad drive (2–12 mA, slow/fast slew), any width, any SWD speed — instant decode failure |

Failure modes to design against:
1. **Transition-density sensitivity**: deaths correlate with the USB
   enumeration burst (max data-line switching). One weak line (D1 in our
   rig, twice) drags the whole port down; per-line quality matters.
2. **Crosstalk/ground-return**: unshielded bundle without interleaved
   grounds was the core defect. The MIPI-20's alternating ground pins must
   be honored with a solid plane and short return loops.
3. **Edge rate**: J-Link programs the trace pads to 0x56 = 4 mA, slow slew,
   schmitt, pull-down, IE — and re-programs them at **every resume**, so the
   PCB must work with 4 mA/slow drive into its load. Do not design for a
   boosted drive; firmware pad overrides get overwritten mid-session.

Layout guidance (designer to verify): 50 Ω single-ended microstrip over a
continuous ground plane; series termination (~22–33 Ω, placed at the RP2350
end — i.e., as close to the Pico 2 header pins as the adapter can get) on
TRACECLK and D0–D3; length-match CLK vs data within a few mm (UI at 75 MHz
DDR is 6.7 ns — generous, but the fly-wire experience says don't spend the
margin); no stubs (the Pico 2 header pin itself is already a stub — keep
adapter traces minimal); keep the MIPI-20 within ~3 cm of the header.
SEGGER's own Pico 2 flywire guide and their trace-adapter reference designs
are the prior art to check.

## Probe constraints — set expectations

- **J-Trace PRO V2 (current rig)**: hard cliff just above 40 MHz TRACECLK
  regardless of signal quality levers we could test. On a clean PCB, expect
  reliable **width-4 dense-data at 40 MHz TRACECLK (80 MHz core)** — the PCB
  removes the seating lottery and the per-line weakness, not the cliff.
- **J-Trace PRO V3+** (SEGGER-required for RP2350 streaming): design target
  is full **75 MHz TRACECLK / 150 MHz core** (and the chip is commonly
  overclocked to 180 → 90 MHz TRACECLK; leave SI margin for it).
- SWD verified fine at 25 MHz (and 50 MHz) on the current rig; the PCB
  should treat 50 MHz SWD as routine.

## Firmware/BSP interface (already in the TinyUSB branch `claude/add-etm-trace-skill`)

- `-DTRACE_ETM=1` builds pin clk_sys via `board.cmake`
  (`hw/bsp/rp2040/boards/raspberry_pi_pico2/board.cmake`) — currently 48 MHz
  (fly-wire-safe). With the PCB, bump to 80 MHz on V2 (`SYS_CLK_KHZ=80000`,
  VCO 1440 MHz, postdiv 6/3) or 150 MHz on V3 (drop the block entirely).
  The clock must be pinned **from crt0** — any clock change after trace
  arms desyncs the decoder mid-stream.
- J-Link's **built-in** RP2350 script owns all chip-side trace config
  (ETM/funnel/TPIU/pin mux + pads) and re-arms at every resume. Never use a
  custom JLinkScript on RP2350 (it silently replaces the built-in one →
  "Required trace components for pin trace not found", zero trace).
- Firmware does only two things under TRACE_ETM (`hw/bsp/rp2040/family.c`):
  clears TIMER0/1 DBGPAUSE (else sleep_ms hangs after debug sessions) and
  keeps the UART console TX-only (GPIO1 = default UART0 RX = TRACECLK; the
  PCB must likewise not route GPIO1 to anything).
- GPIO1–5 must be completely free on the adapter: no pull resistors, no
  LEDs, no test-point loading beyond a via.

## Validation plan (run on this rig, ~30 min)

Tools already in the repo (`.claude/skills/etm-trace/`, use the skill):

1. Continuity + SEGGER demo sanity: `~/code/jtrace/RaspBerryPi_RP2350_M33_0_TraceExample`.
2. Ladder: idle counting-loop blinky at 48 → 80 (→ 120/150 if V3), one
   capture each: `etm_capture.py --board raspberry_pi_pico2 --probe jtrace
   --elf <blinky> --core-clock <N>`.
3. Dense data: TRACE_ETM cdc_msc ×3 at each passing rung (USB enumeration
   burst is the killer test; `lsusb -d cafe:` must stay up).
4. Wire/line bisect if anything fails: `--trace-width 1` (CLK+D0) vs `2` vs
   `4` isolates a bad line; per-line deskew exists via
   `--trace-timing d0,d1,d2,d3` (ps).
5. Accept: 3/3 default-flag captures with full totals at the target clock,
   then update `board.cmake` + `ozone/rp2350.jdebug` (VAR_TRACE_CORE_CLOCK)
   + the SKILL.md board table row together — they must agree.

## Deliverables

- Schematic + layout (KiCad preferred; schematics land in the calibre
  library when done), BOM, and a one-page bring-up note.
- Form factor decision (ask the user): (a) socket carrier the Pico 2 plugs
  into (two 1×20 female headers), (b) shield that plugs onto a
  male-pinned Pico 2, or (c) castellated-solder daughterboard. Keep the
  Pico 2's USB connector and BOOTSEL button accessible — the recovery flow
  (J-Link erase → BOOTSEL 2e8a:000f → picotool) depends on both.
- Optional extras worth asking about: JST-SH DEBUG passthrough, RUN button,
  a 100 mil test header on the five trace nets (unloaded — DNP by default).

## Reference material

- RP2350 datasheet (calibre library): TPIU DDR statement, funcsel 9 table,
  pads (0x56 decode: IE|4mA|schmitt|PDE|slow).
- SEGGER KB "Raspberry Pi Pico 2": V3.0+ requirement, "proper trace board".
- Forum thread forums.raspberrypi.com t=383655: community fly-wire failures
  at 75 MHz, pad-drive tuning advice, Digilent capture attempts.
- github.com/czietz/etm-trace-rp2350: DMA-based capture alternative (no
  pins) — useful cross-check that ETM config itself is sane.
- TinyUSB branch `claude/add-etm-trace-skill` (LOCAL): commits 11a4dd11d,
  d2df67187, f1b89b5b3, 55f5948eb, 01aa79c00 tell the full story; SKILL.md
  board note has the condensed lessons.
