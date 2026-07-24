# Pico 2 SWD + ETM-Trace Motherboard — Design Spec

- **Status:** design approved, pending implementation (KiCad schematic + layout)
- **Date:** 2026-07-24
- **Target probe:** SEGGER J-Trace PRO Cortex-M (V2 today; V3+ for full-rate RP2350 streaming)
- **Target module:** Raspberry Pi **Pico 2** (RP2350A) — also mechanically/pin compatible with the original **Pico** (RP2040); the design must not break RP2040 use.

## 1. Purpose

A carrier "motherboard" that a Pico / Pico 2 plugs into. It does two jobs:

1. **Trace/debug adapter** — presents a proper ARM Cortex **Debug+ETM MIPI-20** connector (SWD + 4-bit parallel trace) to a SEGGER J-Trace, replacing the fly-wire rig whose measured limits are in `PICO2_TRACE_PCB_HANDOFF.md`. It also offers a plain 2×5 Cortex-Debug header and two 3-pin JST-SH debug jacks, so a plain J-Link or a Raspberry Pi Debug Probe can drive the same SWD.
2. **TinyUSB dev/test bench** — exercises TinyUSB on both USB back-ends: the RP2350 **native** USB controller (the module's micro-USB, device or OTG-host) and **PIO-USB** (a USB-A host port and a micro-B device port on GPIOs), plus the peripherals and observability needed to develop and debug them.

Prior art consulted: SEGGER STM32H7/STM32F407 Trace Reference Board schematics (calibre library), the existing `metro_m7_1011_trace` KiCad board, the Adafruit `MBAdafruitBoards` Eagle libraries, and the RP2350 / Pico 2 datasheets.

## 2. Goals & non-goals

**Goals**
- 2 layers max. Solid bottom ground plane for trace return.
- Socket carrier: Pico 2 removable; its micro-USB and BOOTSEL stay accessible (recovery flow depends on both).
- One-probe-at-a-time debug hub: J-Trace (MIPI-20), plain J-Link (2×5), or Pi Debug Probe (JST-SH), all reaching the Pico's SWD.
- Full-rate-capable trace routing (source-terminated, short, guarded) — beat the fly-wire seating lottery.
- Two PIO-USB roles (host + device) + native USB, with power flexible enough to run each case.
- Bench observability: USB probe points, host VBUS switching + current sense, UART console independent of the USB-under-test.

**Non-goals (explicitly excluded, YAGNI)**
- No microSD / MSC storage (dropped by decision).
- No I2S audio codec (UAC2), no Ethernet PHY (net class), no RGB/NeoPixel.
- No second PIO-USB *host* port (GPIO32/33 don't exist on RP2350A anyway).

## 3. Form factor & stackup

- **PCB:** 2-layer FR4, 1.6 mm. Top = components + all signal routing; **bottom = solid GND pour** (continuous under the entire trace group). Approx. 60 × 30 mm (may grow; not size-constrained).
- **Socket carrier, "double-female" (Cytron Maker-Pi-Pico style):** per side, an **inner** 1×20 female socket the Pico plugs into, plus an **outer** 1×20 female **breakout** row net-tied pin-for-pin, so every one of the 40 pins is available for jumper wires. Placed on the KiCad `Module:RaspberryPi_Pico_Common_THT` outline (correct 0.1″ pitch, 0.7″ row spacing, USB/BOOTSEL silk). Inner sockets = `Connector_PinSocket_2.54mm:PinSocket_1x20_P2.54mm_Vertical` ×2; outer breakout = same. Concrete socket part: Sullins PPTC201LFBN-RC or equiv.
- Pico 2 keeps male 0.1″ headers (pins down) and lifts out. Micro-USB + BOOTSEL overhang the board edge.

## 4. Connectors & jumpers (reference designators)

| Ref | Part | Purpose |
|-----|------|---------|
| J1, J2 | 1×20 female socket ×2 (inner) | Pico 2 socket |
| J1B, J2B | 1×20 female socket ×2 (outer) | per-pin breakout |
| J3 | MIPI-20 Cortex Debug+ETM, 2×10 1.27 mm shrouded/keyed (Samtec ASP-152705-01 / FTSH-110-01-L-DV-K) | J-Trace: SWD + 4-bit ETM |
| J4 | JST-SH 1.0 mm 3-pin, right-angle | cable to the Pico 2 DEBUG port (brings SWD onto the board) |
| J5 | USB-A receptacle, THT right-angle | PIO-USB **host** port |
| J6 | 2×5 1.27 mm Cortex Debug (Conn_ARM_JTAG_SWD_10 / FTSH-105-01-L-DV-K) | plain J-Link: SWD only |
| J7 | JST-SH 1.0 mm 3-pin, right-angle | Raspberry Pi **Debug Probe** ("pico-debug") jack, mirrors J4 |
| J8 | micro-B receptacle, **power-only** (VBUS+GND; D+/D− NC) | 5 V input for host-stack work |
| J9 | micro-B receptacle | PIO-USB **device** port |
| JP1 | 3-pin header + shunt | board 5 V source select: VBUS-net ↔ J-Trace 5 V |
| JP2, JP3 | 2-pin header + shunt (default fitted) | GP0 / GP6 GND **guard** jumpers |
| JP4 | 2-pin header + shunt (default fitted) | native VBUS-detect tap enable → GP16 (§9) |
| SW1 | tactile button, top-mount, medium | RUN reset |

Debug connectors J3/J4/J6/J7 grouped on one board edge so the shared SWD fan-out stays short.

## 5. Debug/trace signal maps

### 5.1 MIPI-20 (J3), per the SEGGER J-Trace pinout (image-authoritative; verified against SEGGER STM32H7 ref board)

| Pin | Net | Source | | Pin | Net | Source |
|--|--|--|--|--|--|--|
| 1 | VTref | Pico 3V3_OUT (pin 36) | | 2 | SWDIO | JST-SH DEBUG (J4) |
| 3 | GND | | | 4 | SWCLK | JST-SH DEBUG (J4) |
| 5 | GND | | | 6 | SWO | **NC** (RP2350 has none) |
| 7 | KEY | NC | | 8 | TDI | **NC** |
| 9 | GND | (GNDDetect → GND, per SEGGER ref board) | | 10 | nRESET | RUN (pin 30) |
| 11 | **5V-Supply** | J-Trace 5 V → JP1 | | 12 | TRACECLK | GP1 (pin 2) via Rterm |
| 13 | **5V-Supply** | J-Trace 5 V → JP1 | | 14 | TRACEDATA0 | GP2 (pin 4) via Rterm |
| 15 | GND | | | 16 | TRACEDATA1 | GP3 (pin 5) via Rterm |
| 17 | GND | | | 18 | TRACEDATA2 | GP4 (pin 6) via Rterm |
| 19 | GND | | | 20 | TRACEDATA3 | GP5 (pin 7) via Rterm |

### 5.2 Cortex Debug 2×5 (J6) — plain J-Link

Signals identical to MIPI-20 pins 1–10, wired in parallel on the shared SWD net: 1 VTref, 2 SWDIO, 3 GND, 4 SWCLK, 5 GND, 6 SWO(NC), 7 KEY, 8 TDI(NC), 9 GND, 10 nRESET. No 5 V pin.

### 5.3 SWD source (J4 / J7)

Both JST-SH 3-pin, pinout **SWCLK / GND / SWDIO** (Raspberry Pi debug standard). J4 cables to the Pico 2's DEBUG port; J7 accepts a Pi Debug Probe. Both land on the shared SWDIO/SWCLK/GND net that feeds J3 pin 2/4 and J6 pin 2/4. **One probe connected at a time.**

### 5.4 Trace signal integrity

- **Source series termination 27 Ω** (0402) on TRACECLK + TRACEDATA0–3, placed at the Pico socket pins (the breakout tap is on the socket-side of Rterm, so Rterm isolates it from the line).
- Traces ≈ 0.3 mm, **runs < 30 mm**, CLK↔data length-matched within a few mm, no stubs. Not chasing exact 50 Ω (impractical on 2-layer 1.6 mm); solid bottom GND + short length + source termination is sufficient for the V2 40 MHz cliff and good for V3.
- GND stitching vias around the trace group. MIPI-20 within ~3 cm of the socket.
- **GP1–GP5 carry nothing else** — no pulls, LEDs, or loading beyond a via/breakout. The five outer breakout females for GP1–GP5 are silk-marked **"unplug while tracing"** (a wire there is a fat antenna on a 40–75 MHz line).
- **Guard pins:** GP0 (pin 1, directly against TRACECLK, no GND between) and GP6 (pin 9) each have a 2-pin **removable jumper to GND** (JP2/JP3, default fitted). Fitted = grounded guard (GND on both sides of TRACECLK); their breakout females double as scope/sniffer GND next to the trace bus. Removed = pin freed. Rule: with a guard fitted, keep that GPIO an input.

## 6. GPIO pin map (Pico/Pico 2, RP2350A header)

| GPIO | Function | Notes |
|--|--|--|
| 0 | GND guard (JP2) | pin 1, next to TRACECLK; jumper to GND, default on |
| 1 | TRACECLK | funcsel 9 (CORESIGHT); also default UART0 RX — **not routed to UART** |
| 2–5 | TRACEDATA0–3 | funcsel 9 |
| 6 | GND guard (JP3) | pin 9, next to trace block; jumper to GND, default on |
| 7 | spare | |
| 8 | I2C0 SDA (STEMMA-QT) | moved off GP6/7 to keep active signals away from trace |
| 9 | I2C0 SCL (STEMMA-QT) | |
| 10 | user LED | |
| 11 | spare | |
| 12 | UART0 TX (console) | remapped off GP0/1 → **full-duplex console during trace** |
| 13 | UART0 RX (console) | |
| 14 | user button | to GND |
| 15 | host VBUS fault | load-switch open-drain flag; `OVERCURR_DETECT`-capable pin |
| 16 | native VBUS-detect tap | `VBUS_DETECT`-capable; 8.2k/8.2k from VBUS net via JP-gate |
| 17 | host VBUS enable | load-switch enable; `VBUS_EN`-capable pin |
| 18 | PIO-USB device D+ (J9) | |
| 19 | PIO-USB device D− (J9) | |
| 20 | PIO-USB host D+ (J5) | |
| 21 | PIO-USB host D− (J5) | |
| 22 | spare | |
| 26 | VBUS current-sense (ADC) | shunt + INA181 amp output |
| 27 | J9 device VBUS-detect | plain GPIO, 8.2k/8.2k divider |
| 28 | spare | ADC-capable |

Module-internal pins (not on header, unusable by the carrier): GP23 (SMPS PS), GP24 (VBUS sense), GP25 (LED), GP29 (VSYS/3 ADC).

Placement rationale for USB-mux pins: GP15/16/17 sit on `OVERCURR_DETECT` / `VBUS_DETECT` / `VBUS_EN`-capable pins (funcsel `0x0a`, which rotates by GPIO mod 3), so the native controller's hardware VBUS enable/detect/overcurrent can be funcsel-tested later — while normally serving as plain GPIOs.

## 7. Power architecture

- **VBUS net = Pico pin 40** = the module's micro-USB VBUS = J8 power-USB = external-5V breakout injection. All one node (the micro-USB VBUS is an *input* as device / *output* as OTG host, so it must be a hard bidirectional tie — cannot be diode-isolated or switch-broken).
- **JP1 (3-pin)** selects the board 5 V: **USB side (VBUS net) ↔ J-Trace 5 V (MIPI-20 pins 11/13).**
  - `JP1 = USB`: board runs from the module micro-USB (device), or J8, or external-VBUS.
  - `JP1 = JTRACE`: J-Trace 5 V drives the VBUS net; the module micro-USB is freed to be an **OTG host** (its VBUS is now sourced from pin 40); Pico powered via pin 40 → onboard VBUS→VSYS diode → VSYS → 3V3.
- **Rule:** exactly one hard 5 V source on the VBUS net at a time (module-USB-from-PC, J8, external-VBUS, or J-Trace). JP1 keeps J-Trace off the USB side; the user avoids doubling the USB-side sources.
- **J-Trace 5 V is current-limited** (a few hundred mA) — hungry downstream devices → use J8 or a strong USB supply.
- The VBUS net also feeds the **PIO-USB host (J5) VBUS** through the host load switch (§8.1).
- **VSYS** remains reachable on the breakout female for independent bench powering — used when testing native VBUS-detect transitions (§9).

## 8. USB ports

### 8.1 PIO-USB host (J5) — GPIO20 (D+) / GPIO21 (D−)
- 22 Ω series (0 Ω option) at the GPIOs; **15 kΩ pulldowns** on D+/D− at the receptacle; **ESD array** (USBLC6-2SC6 class).
- **VBUS via a current-limited load switch** (TPS2051B / AP22653 / MIC2005 class): enable = GP17, open-drain fault = GP15, 10–22 µF bulk + 0.1 µF at the connector. (Replaces the earlier plain polyfuse; the switch's current limit + fault flag give host over-current control/observability.)
- **Probe points:** TP pads on D+/D− + GND at the port for the ataradov sniffer / scope.

### 8.2 PIO-USB device (J9, micro-B) — GPIO18 (D+) / GPIO19 (D−)
- Series R + **ESD array** on D+/D−.
- **1.5 kΩ D+ pull-up to 3V3, gated** (small FET or firmware-driven) by the VBUS-detect so the board only signals "attached" when a host's VBUS is present (board is often self-powered, so 3V3 is up regardless).
- **VBUS-detect:** 8.2 kΩ/8.2 kΩ divider from J9 VBUS → **GP27** (plain GPIO, read by the PIO-USB stack). Divider chosen so the pin sees ~2.5 V (logic-high, < 3.3 V so RP2040-safe, < 3.63 V so within the RP2350 unpowered-failsafe for hot-plug-while-off; R_bottom = 8.2 kΩ satisfies the RP2350-E9 external-pulldown requirement).
- Default **detect-only** (self-powered). Optional (DNP) diode from J9 VBUS to the VBUS net if bus-powered device operation is ever wanted.

### 8.3 Native USB (module micro-USB)
- Device (into a PC) or OTG host (§7, `JP1 = JTRACE`). VBUS = pin 40. VBUS-detect for the native *device* controller is handled on-module (GP24 SIO + R10/R1) / by `USB_PWR` override — nothing added.

## 9. Native VBUS-detect hardware test tap

To exercise the RP2350 native controller's **hardware** VBUS_DETECT (`SIE_STATUS.VBUS_DETECTED` + interrupt), not just the software override:
- **8.2 kΩ/8.2 kΩ divider from the VBUS net → GP16** (a `VBUS_DETECT`-capable pin, funcsel `0x0a`), through **JP4** (2-pin header, default fitted) to enable the tap (keeps GP16 free otherwise).
- Firmware sets GP16 funcsel = `0x0a`; the controller then senses VBUS in hardware.
- **Test methodology:** power the board from **VSYS** (breakout female), `JP1` off J-Trace and J8 unplugged, then plug/unplug the module micro-USB to a host to drive pin 40 (= VBUS net) high/low and confirm the detect + interrupt follow. (Powering from VBUS instead would make VBUS un-droppable without killing the board.)
- Note the RP2350 quirk this exercises: on the module, GP24 (wired to VBUS) funcsel `0x0a` = `OVERCURR_DETECT`, and GP25 (which can do `VBUS_DETECT`) is the LED with no VBUS — so the module can't hardware-detect VBUS on its own pins; this header tap is what makes the test possible.

## 10. Peripherals / bench aids

- **UART0 console header** — 3-pin TX/RX/GND on GP12/13 (funcsel `0x02` = UART0). Matches the SDK default `uart0`, full-duplex during trace.
- **STEMMA-QT / Qwiic I2C** — JST-SH 4-pin on I2C0 GP8/9 (Adafruit `STEMMAQT` footprint).
- **1 user button** (GP14 → GND), **1 user LED** (GP10), **1 power LED** on the 5 V rail.
- **VBUS current-sense** — high-side shunt (~0.1 Ω) + INA181/INA180 amp → GP26 (ADC). (Alt, DNP option: INA219 on the I2C bus — richer, frees GP26.)

## 11. Firmware / BSP implications (`hw/bsp/rp2040/boards/raspberry_pi_pico2`, branch `claude/add-etm-trace-skill`)
- UART0 remapped: `PICO_DEFAULT_UART=0`, `..._TX_PIN=12`, `..._RX_PIN=13`. GP0/GP1 no longer UART; GP1 = TRACECLK only.
- Trace on GP1–GP5 (funcsel 9) owned by the J-Link built-in RP2350 script; **no custom JLinkScript**. Keep GP1 unrouted to non-trace functions (satisfied).
- GP0 / GP6 are GND-guard pins: keep as inputs (do not drive).
- PIO-USB host on GP20/21; PIO-USB device on GP18/19.
- Host VBUS: enable GP17, fault GP15 (usable as plain GPIO or funcsel `VBUS_EN`/`OVERCURR_DETECT`).
- Native VBUS-detect test: GP16 funcsel `0x0a`.
- J9 device VBUS-detect on GP27; gate the D+ pull-up on it.
- Existing TRACE_ETM firmware (clears TIMER0/1 DBGPAUSE, TX-only console) still applies, except the console is now full-duplex on GP12/13.

## 12. Deliverables & files

Project root: `~/code/jtrace/pico2_trace_motherboard/` (its own git repo; siblings are per-board).
- KiCad 9 project (`.kicad_pro/.kicad_sch/.kicad_pcb`) + a local `.pretty` for converted Adafruit / metro footprints.
- BOM (`docs/BOM.csv`).
- One-page bring-up note (`docs/BRINGUP.md`).
- Final schematic PDF + bring-up note also archived to the calibre library when done.

Footprint sources: KiCad stock (MIPI-20 = `PinHeader_2x10_P1.27mm_Vertical_SMD` refined to FTSH-110/ASP-152705; 2×5 = `PinHeader_2x05_P1.27mm_Vertical_SMD`; USB-A, JST-SH, PinSocket, USB micro-B); Adafruit Eagle `.lbr` (STEMMA-QT, load switch, ESD, tactile) imported into the local `.pretty`; metro_m7 `.pretty` (boxed 2×5, JST-SH) for reuse.

## 13. Validation plan (per handoff, on the J-Trace rig, ~30 min)
1. Continuity + SEGGER demo: `~/code/jtrace/RaspBerryPi_RP2350_M33_0_TraceExample`.
2. Ladder blinky 48 → 80 MHz core (→120/150 on V3), one `etm_capture.py` each.
3. Dense data: TRACE_ETM cdc_msc ×3 per passing rung (USB-enumeration burst = the killer test).
4. Wire/line bisect on failure (`--trace-width 1/2/4`, `--trace-timing`).
5. Accept: 3/3 full-total captures at target clock; update `board.cmake` + `ozone/rp2350.jdebug` + the SKILL.md board row together.
6. USB bench checks: native device enum (cafe:*), PIO-USB host enum of a plugged device, PIO-USB device enum into a PC, native OTG host (JP1=JTRACE), host VBUS switch on/off + over-current flag, native hardware VBUS-detect (§9), UART0 console, I2C peripheral.

## 14. Open / DNP items
- Optional DNP 1×6 100-mil test header on the five trace nets (the outer breakout females already serve this).
- INA219-over-I2C as an alternative to the analog current-sense (DNP footprint).
- J9 bus-power diode (DNP).
- 22 Ω PIO-host series resistors may be populated 0 Ω if signalling is clean.
