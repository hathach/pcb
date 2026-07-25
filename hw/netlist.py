"""Connectivity model: parts table + graph helpers.

Single source of truth for schematic/PCB work (Tasks 4-9 wire it up; this file
only *defines the parts* and the machinery later tasks use to assign/query
nets). See DESIGN.md SS4/SS6 (connectors + GPIO map) and hw/fp_lib.py (the 21+2
footprint classes every Part.fp_class must resolve against).

Net-naming convention relied on by PINMAP / divider_ratio / series_between
(binding for Tasks 4-7, documented here so later edits don't have to
rediscover it):
  - A "net" is a single Python string; two Part pins sharing that string are
    the same electrical node. Anything separated by a component (a resistor,
    a jumper, ...) needs a *different* net name on each side. This holds even
    when PINMAP reports the same *label* for two pins: GP0's and GP6's guard
    jumpers (JP2/JP3) are electrically independent, so their nets must never
    share a literal string, even though both are labeled "GUARD" (below).
  - For a GPIO that reaches its function through a single source-series
    element (Rt1-5 for the trace bus, the 22R USB series resistors, the LED
    series resistors), PICO's own pin keeps a bare "GPn" net; the *far* side
    of that element carries the function name (e.g. "GP1" -Rt1-> "TRACECLK",
    "GP20" -R_HDP-> "HOST_DP"). PINMAP hops through that element to report
    the function name for the GPIO.
  - Guard pins (GP0/GP6) are the same source-series shape with GND on the far
    side: PICO's own pin keeps a bare "GPn" net (distinct per pin) and a
    fitted 2-pin jumper (JP2/JP3) goes straight to GND. Since "GND" isn't a
    function name, PINMAP derives the literal label "GUARD" for this shape
    instead of hopping to it.
  - For a GPIO that *is itself* the function node -- a resistor-divider
    midpoint (ISENSE, NATIVE_VBUS_DET, DEV_VBUS_DET), or a pin with no series
    element at all (HOST_VBUS_EN/FLT, I2C/UART/button pins, DEV_DP_PU_EN) --
    PICO's own pin should be named with the function directly (e.g.
    "NATIVE_VBUS_DET"). PINMAP only ever hops (source-series or guard) when
    the PICO-side net itself is a bare "GPn"-style name; that keeps divider
    midpoints (two hop-class neighbors: top leg + GND leg) out of the
    one-neighbor hop path, and stops a named function net from hopping just
    because a resistor happens to be its only neighbor (e.g. DEV_DP_PU_EN
    must NOT hop to "DEV_DP" through R_DPU -- R_DPU is a pull-up, not a
    source-series element on DEV_DP_PU_EN's own GPIO).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field

from hw.fp_lib import FP


@dataclass
class Part:
    ref: str
    value: str
    fp_class: str
    pins: dict[str, str | None]
    nc: set[str] = field(default_factory=set)
    dnp: bool = False
    # logical pin name -> footprint pad number; None means `pins` is already
    # keyed by pad number (the identity mapping used by simple parts).
    padmap: dict[str, str] | None = None

    def pad_number(self, pin: str) -> str:
        """Footprint pad number for a logical pin name (identity if no padmap)."""
        if self.padmap is None:
            return pin
        return self.padmap.get(pin, pin)

    def pad_nets(self) -> list[tuple[str, str]]:
        """(footprint pad number, net name) for every connected pin -- the
        same pin-name -> pad-number translation `emit_netlist` applies via
        `pad_number`, factored here so `build_board.py` uses the identical
        rule (nc'd / unassigned pins are omitted)."""
        return [(self.pad_number(pin), net) for pin, net in self.pins.items() if net is not None]


def _pins(*names: str) -> dict[str, str | None]:
    return {n: None for n in names}


def _numbered(n: int, start: int = 1) -> dict[str, str | None]:
    return {str(i): None for i in range(start, start + n)}


# --------------------------------------------------------------------------
# PARTS
# --------------------------------------------------------------------------
# Simple parts (headers, sockets, plain resistors/caps/LEDs, test points) key
# `pins` by footprint pad number directly (padmap=None). A handful of parts
# whose datasheet pinout matters get logical names + a padmap documenting the
# real pad order (comments cite the datasheet figure consulted).

PARTS: dict[str, Part] = {}


def _add(part: Part) -> None:
    assert part.ref not in PARTS, f"duplicate ref {part.ref}"
    PARTS[part.ref] = part


# --- Pico module + breakouts -----------------------------------------------
_add(Part("PICO", "Pico2", "pico_socket", _numbered(40)))
_add(Part("J1B", "BREAKOUT", "breakout_1x20", _numbered(20)))   # pads 1-20 <-> PICO pins 1-20
_add(Part("J2B", "BREAKOUT", "breakout_1x20", _numbered(20)))   # pads 1-20 <-> PICO pins 21-40 (Task 7)

# --- Debug connectors --------------------------------------------------
_add(Part("J3", "MIPI-20", "mipi20", _numbered(20)))
_add(Part("J4", "JST-SH-3 DEBUG", "jst_sh3", _pins("1", "2", "3")))     # SWCLK/GND/SWDIO, DESIGN SS5.3
_add(Part("J6", "CORTEX-10", "cortex10", _numbered(10)))
_add(Part("J7", "JST-SH-3 DEBUG_PROBE", "jst_sh3", _pins("1", "2", "3")))
_add(Part("SW1", "RESET", "button", _pins("1", "2")))

# --- USB connectors ------------------------------------------------------
# J5 USB-A (Molex 67643): standard USB-A pinout, pad 5 is the mechanical
# shield tab (not modeled -- no logical net needed for it).
_add(Part(
    "J5", "USB-A HOST", "usb_a",
    _pins("VBUS", "DM", "DP", "GND"),
    padmap={"VBUS": "1", "DM": "2", "DP": "3", "GND": "4"},
))
_add(Part("J8", "USB-MICROB PWR", "usb_microb", _numbered(6)))   # 1 VBUS,2 D-,3 D+,4 ID,5 GND,6 shield
_add(Part("J9", "USB-MICROB DEV", "usb_microb", _numbered(6)))

# --- Peripherals -----------------------------------------------------------
_add(Part("J_UART", "UART0", "hdr_1x03", _pins("1", "2", "3")))          # TX/RX/GND
_add(Part("J_STEMMA", "STEMMA-QT", "jst_sh4", _pins("1", "2", "3", "4")))  # GND/3V3/SDA/SCL (Adafruit order)
# SW_USER (Task 7): Task 3 only created SW1 (RESET) -- no user-button part
# existed yet, so it's added here per DESIGN SS10 (1 user button, GP14->GND).
_add(Part("SW_USER", "USER", "button", _pins("1", "2")))

# --- Jumpers -----------------------------------------------------------
_add(Part("JP1", "5V SEL", "hdr_1x03", _pins("1", "2", "3")))
_add(Part("JP2", "GP0 GUARD", "hdr_1x02", _pins("1", "2")))
_add(Part("JP3", "GP6 GUARD", "hdr_1x02", _pins("1", "2")))
_add(Part("JP4", "VBUS_DET EN", "hdr_1x02", _pins("1", "2")))

# --- Host-VBUS load switch --------------------------------------------------
# TPS2051B, SOT-23-5 (DBV), per TI datasheet SLVS514P Figure 5-1 (TPS2041B and
# TPS2051B / DBV Package 5-Pin SOT-23 top view), TPS2051B column: pad1=OUT,
# pad2=GND, pad3=OC (open-drain overcurrent/fault, active-low), pad4=EN
# (active-high for the TPS205xB series), pad5=IN.
_add(Part(
    "U_HSW", "TPS2051B", "loadswitch",
    _pins("GND", "IN", "EN", "FLG", "OUT"),
    padmap={"GND": "2", "IN": "5", "EN": "4", "FLG": "3", "OUT": "1"},
))

# --- ESD arrays --------------------------------------------------------
# USBLC6-2SC6, SOT-23-6, per ruling: IO1/GND/IO2/IO2B/VBUS/IO1B -> pads 1..6.
_ESD_PADMAP = {"IO1": "1", "GND": "2", "IO2": "3", "IO2B": "4", "VBUS": "5", "IO1B": "6"}
_add(Part("ESD_H", "USBLC6-2SC6", "esd6", _pins("IO1", "GND", "IO2", "IO2B", "VBUS", "IO1B"), padmap=dict(_ESD_PADMAP)))
_add(Part("ESD_D", "USBLC6-2SC6", "esd6", _pins("IO1", "GND", "IO2", "IO2B", "VBUS", "IO1B"), padmap=dict(_ESD_PADMAP)))

# --- Current sense -------------------------------------------------------
# DESIGN SS10 allows "INA181/INA180"; the isense fp_class (Task 2) is
# SOT-23-5, which is INA180's package (INA181 needs a 6th REF pin, SOT-23-6)
# -- so U_ISNS is populated as an INA180 (no external REF, output referenced
# to GND, which is what this circuit needs). Per TI SBOS741H Figure 6-1
# (INA180: DBV Package 5-Pin SOT-23, Pinout A): pad1=OUT, pad2=GND,
# pad3=IN+, pad4=IN-, pad5=VS.
_add(Part(
    "U_ISNS", "INA180A1DBVR", "isense",
    _pins("GND", "IN+", "IN-", "OUT", "VS"),
    padmap={"GND": "2", "IN+": "3", "IN-": "4", "OUT": "1", "VS": "5"},
))
_add(Part("R_SHUNT", "0.1", "shunt", _pins("1", "2")))

# --- Trace source-series resistors (27R, at the Pico socket pins) ----------
for _ref in ("Rt1", "Rt2", "Rt3", "Rt4", "Rt5"):
    _add(Part(_ref, "27", "r0402", _pins("1", "2")))

# --- Reset debounce cap (100n, DNP per DESIGN "Reset") ----------------------
# Value carries its voltage rating (Task 14b, Adafruit schematic rule: every
# capacitor value states a voltage rating) -- resistor values are untouched,
# _parse_ohms depends on those staying bare numeric+suffix.
_add(Part("C_NRESET", "100n/16V", "c0402", _pins("1", "2"), dnp=True))

# --- USB D+/D- series resistors (22R) --------------------------------------
_add(Part("R_HDP", "22", "r0402", _pins("1", "2")))   # host D+ series (GP20 -> HOST_DP)
_add(Part("R_HDM", "22", "r0402", _pins("1", "2")))   # host D- series (GP21 -> HOST_DM)
_add(Part("R_DDP", "22", "r0402", _pins("1", "2")))   # device D+ series (GP18 -> DEV_DP)
_add(Part("R_DDM", "22", "r0402", _pins("1", "2")))   # device D- series (GP19 -> DEV_DM)

# --- Host D+/D- pulldowns (15k) ------------------------------------------
_add(Part("R_HDP_PD", "15k", "r0402", _pins("1", "2")))   # HOST_DP -> GND
_add(Part("R_HDM_PD", "15k", "r0402", _pins("1", "2")))   # HOST_DM -> GND

# --- Device D+ pull-up (1.5k), firmware soft-connect via GP11 --------------
_add(Part("R_DPU", "1.5k", "r0402", _pins("1", "2")))

# --- Host-VBUS-EN pulldown (100k) -- Task 14b -------------------------------
# Defines the TPS2051B (U_HSW) EN pin state at boot: RP2350-E9 makes the
# chip's internal GPIO pull-downs unreliable before firmware configures the
# pin, so a real external pulldown is needed to guarantee EN (GP17) defaults
# low (load switch OFF) rather than floating, until firmware drives it high.
_add(Part("R_HVEN_PD", "100k", "r0402", _pins("1", "2")))

# --- VBUS-detect dividers (8.2k/8.2k each) ----------------------------------
_add(Part("R_NVD_T", "8.2k", "r0402", _pins("1", "2")))   # native VBUS-detect divider, top leg (thru JP4)
_add(Part("R_NVD_B", "8.2k", "r0402", _pins("1", "2")))   # native VBUS-detect divider, bottom leg (-> GND)
_add(Part("R_J9VD_T", "8.2k", "r0402", _pins("1", "2")))  # J9 VBUS-detect divider, top leg
_add(Part("R_J9VD_B", "8.2k", "r0402", _pins("1", "2")))  # J9 VBUS-detect divider, bottom leg (-> GND)

# --- LEDs + series resistors -------------------------------------------
# Placeholder 1k series value; final current-limit value is a BOM tuning
# detail (Task 17), not a connectivity concern.
_add(Part("LED_USER", "LED", "led0603", _pins("1", "2")))
_add(Part("LED_PWR", "LED", "led0603", _pins("1", "2")))
_add(Part("R_LED_USER", "1k", "r0402", _pins("1", "2")))
_add(Part("R_LED_PWR", "1k", "r0402", _pins("1", "2")))

# --- Host-VBUS bulk/decoupling caps (Task 4; DESIGN SS8.1: 10-22uF bulk +
# 0.1uF at the connector) -- values carry voltage ratings (Task 14b, Adafruit
# schematic rule: every capacitor value states a voltage rating) -----------
_add(Part("C_HVBUS_BULK", "22u/10V", "c0805", _pins("1", "2")))
_add(Part("C_HVBUS_100n", "100n/16V", "c0402", _pins("1", "2")))

# --- Probe points --------------------------------------------------------
_add(Part("TP1", "TP", "testpoint", _pins("1")))
_add(Part("TP2", "TP", "testpoint", _pins("1")))
_add(Part("TP3", "TP", "testpoint", _pins("1")))

# --- DNP parts (DESIGN SS14 / brief G-7; Task 14b realizes these Adafruit-
# style: real footprint + fully wired + dnp=True, replacing the earlier
# "footprint stand-in, all pins nc" placeholders) ---------------------------
# U_INA219_ALT: INA219, SOT-23-8 (TI DCN package), per TI SBOS448 Figure 8-1
# ("DCN Package 8-Pin SOT-23, Top View"): pad1=IN+, pad2=IN-, pad3=GND,
# pad4=VS, pad5=SCL, pad6=SDA, pad7=A0, pad8=A1.
_add(Part(
    "U_INA219_ALT", "INA219", "sot23-8",
    _pins("IN+", "IN-", "GND", "VS", "SCL", "SDA", "A0", "A1"),
    padmap={"IN+": "1", "IN-": "2", "GND": "3", "VS": "4", "SCL": "5", "SDA": "6", "A0": "7", "A1": "8"},
    dnp=True,
))
# D_J9_BUSPWR: optional J9-VBUS -> VBUS_NET bus-power diode (DESIGN SS8.2/SS14).
_add(Part("D_J9_BUSPWR", "1N4148W", "sod123", _pins("1", "2"), dnp=True))
# J_TRACE_TP: REMOVED in Task 14c (SI ruling). Its pads sat directly on
# TRACECLK/TD0-3 -- as a DNP header hanging off the length-matched bundle it
# is a stub on every SI-critical net, which DESIGN SS5.4 forbids ("no other
# loading"). Routing the bundle *through* its pads (the stubless alternative)
# would have put six 1.7mm THT pads inside the tuned convergence and forced a
# total re-derivation for no populated-board benefit. Removal was
# pre-authorized by the Task 14c brief.


# --------------------------------------------------------------------------
# Task 4: power & ground nets
# --------------------------------------------------------------------------
# JP1 (DESIGN SS7): pin1=V5_JTRACE (J-Trace 5V), pin3=VBUS_NET (the single
# hard-tied USB-side node: PICO pin 40 / module micro-USB / J8 / external-5V
# injection -- never switch-broken), pin2=VBUS_SEL is JP1's *selected*
# output (board 5V rail) that feeds the host load switch + power LED.
PARTS["JP1"].pins.update({"1": "V5_JTRACE", "2": "VBUS_SEL", "3": "VBUS_NET"})

PARTS["PICO"].pins.update({
    "40": "VBUS_NET",   # SS7: hard-tied USB-side node, never switched
    "39": "VSYS",
    "36": "P3V3",
    "35": "AREF",       # fixes G-2
    "37": "P3V3_EN",    # fixes G-2
    "3": "GND", "8": "GND", "13": "GND", "18": "GND",
    "23": "GND", "28": "GND", "33": "GND", "38": "GND",
})

PARTS["J3"].pins.update({
    "11": "V5_JTRACE", "13": "V5_JTRACE",
    "3": "GND", "5": "GND", "9": "GND", "15": "GND", "17": "GND", "19": "GND",
})

# Host load switch (SS8.1): VBUS_SEL -> IN, OUT -> HOST_VBUS -> J5 VBUS.
# EN/FLG (GP17/GP15) stay None -- Task 6.
# NOTE (Task 6): IN's net is retargeted from VBUS_SEL to HOST_5V_IN below --
# Task 6 inserts R_SHUNT upstream of IN for current sensing (SS10). This
# test's assertions don't cover IN's net so the change is safe (verified).
PARTS["U_HSW"].pins.update({"IN": "VBUS_SEL", "OUT": "HOST_VBUS", "GND": "GND"})
PARTS["J5"].pins.update({"VBUS": "HOST_VBUS", "GND": "GND"})

# HOST_VBUS bulk + decoupling caps at the connector (SS8.1).
PARTS["C_HVBUS_BULK"].pins.update({"1": "HOST_VBUS", "2": "GND"})
PARTS["C_HVBUS_100n"].pins.update({"1": "HOST_VBUS", "2": "GND"})

PARTS["J8"].pins.update({"1": "VBUS_NET", "5": "GND"})   # micro-B PWR: 1=VBUS,5=GND

# Debug-jack + peripheral + ESD grounds (signal pins left for their own tasks).
PARTS["J4"].pins["2"] = "GND"          # JST-SH-3 DEBUG: 1=SWCLK,2=GND,3=SWDIO
PARTS["J7"].pins["2"] = "GND"          # mirrors J4
PARTS["J_UART"].pins["3"] = "GND"      # 1=TX,2=RX,3=GND
PARTS["J_STEMMA"].pins["1"] = "GND"    # Adafruit order: 1=GND,2=3V3,3=SDA,4=SCL
PARTS["ESD_H"].pins["GND"] = "GND"
PARTS["ESD_D"].pins["GND"] = "GND"
PARTS["SW1"].pins["2"] = "GND"         # RESET button: 1->NRESET (Task 5), 2->GND

# Power LED: VBUS_SEL -> R_LED_PWR -> LED_PWR anode; cathode -> GND. LED pad
# numbering follows the KiCad "LED" symbol default (pad1=K/cathode,
# pad2=A/anode) -- keep LED_USER (Task 7) consistent with this convention.
PARTS["R_LED_PWR"].pins.update({"1": "VBUS_SEL", "2": "LED_PWR_A"})
PARTS["LED_PWR"].pins.update({"2": "LED_PWR_A", "1": "GND"})


# --------------------------------------------------------------------------
# Task 5: debug & trace nets
# --------------------------------------------------------------------------
# VTREF ruling: there is no separate "VTREF" net -- PICO "36" is already on
# P3V3 (Task 4). J3/J6 pin 1 (VTref) just join that same net.
PARTS["J3"].pins["1"] = "P3V3"
PARTS["J6"].pins["1"] = "P3V3"

# SWD fan-out (DESIGN SS5.1-5.3): J4/J7 (SWCLK/GND/SWDIO, GND done in Task 4)
# and J3/J6 pins 2/4 all share the SWDIO/SWCLK nets.
PARTS["J4"].pins.update({"1": "SWCLK", "3": "SWDIO"})
PARTS["J7"].pins.update({"1": "SWCLK", "3": "SWDIO"})
PARTS["J3"].pins.update({"2": "SWDIO", "4": "SWCLK"})
PARTS["J6"].pins.update({"2": "SWDIO", "4": "SWCLK"})

# J6 grounds deferred from Task 4 (ruling): pins 3/5/9 -> GND.
PARTS["J6"].pins.update({"3": "GND", "5": "GND", "9": "GND"})

# NRESET (DESIGN SS5.1/5.2: nRESET = RUN, pin 30): PICO -> J3/J6 pin 10 ->
# SW1 side 1; SW1 side 2 -> GND (Task 4). Debounce cap across SW1.
PARTS["PICO"].pins["30"] = "NRESET"
PARTS["J3"].pins["10"] = "NRESET"
PARTS["J6"].pins["10"] = "NRESET"
PARTS["SW1"].pins["1"] = "NRESET"
PARTS["C_NRESET"].pins.update({"1": "NRESET", "2": "GND"})

# SWO/KEY/TDI: RP2350 has no SWO, KEY/TDI are unused on this bus -- NC on
# both debug connectors (DESIGN SS5.1/5.2, pins 6/7/8).
PARTS["J3"].nc |= {"6", "7", "8"}
PARTS["J6"].nc |= {"6", "7", "8"}

# Trace chain (DESIGN SS5.1/5.4): PICO GPn -> Rtn (27R source series,
# fitted at the socket pin) -> function net -> J3. GPn stays a bare net on
# the PICO/socket side per the module net-naming convention.
PARTS["PICO"].pins.update({"2": "GP1", "4": "GP2", "5": "GP3", "6": "GP4", "7": "GP5"})
PARTS["Rt1"].pins.update({"1": "GP1", "2": "TRACECLK"})
PARTS["Rt2"].pins.update({"1": "GP2", "2": "TD0"})
PARTS["Rt3"].pins.update({"1": "GP3", "2": "TD1"})
PARTS["Rt4"].pins.update({"1": "GP4", "2": "TD2"})
PARTS["Rt5"].pins.update({"1": "GP5", "2": "TD3"})
PARTS["J3"].pins.update({"12": "TRACECLK", "14": "TD0", "16": "TD1", "18": "TD2", "20": "TD3"})

# Guard pins (DESIGN SS5.4/SS6): GP0 (pin 1) / GP6 (pin 9) each get their own
# 2-pin jumper straight to GND (JP2/JP3, default fitted). These are two
# independent guard nodes -- one net name = one electrical net, so they must
# NOT share a literal string (review fix: an earlier pass renamed both to the
# literal "GUARD", which shorts GP0 to GP6 in the model; with a jumper
# removed, its pin must stay an independent breakout, per DESIGN SS5.4).
# PICO keeps a bare "GPn" net on each guard pin (same shape as the
# source-series convention, GND on the far side instead of a function net);
# PINMAP's hop heuristic derives the literal "GUARD" label for this shape
# (single fitted jumper neighbor landing on GND) instead of the net name
# itself having to carry it.
PARTS["PICO"].pins.update({"1": "GP0", "9": "GP6"})
PARTS["JP2"].pins.update({"1": "GP0", "2": "GND"})
PARTS["JP3"].pins.update({"1": "GP6", "2": "GND"})


# --------------------------------------------------------------------------
# Task 6: USB host, USB device, VBUS-detect taps
# --------------------------------------------------------------------------

# --- Host port (DESIGN SS8.1): PICO GP20/GP21 -> 22R series -> HOST_DP/DM ->
# J5, with 15k pulldowns and ESD_H across the pair. GPn stays a bare net on
# the PICO/socket side (source-series convention, same as the trace bus).
PARTS["PICO"].pins.update({"26": "GP20", "27": "GP21"})
PARTS["R_HDP"].pins.update({"1": "GP20", "2": "HOST_DP"})
PARTS["R_HDM"].pins.update({"1": "GP21", "2": "HOST_DM"})
PARTS["R_HDP_PD"].pins.update({"1": "HOST_DP", "2": "GND"})
PARTS["R_HDM_PD"].pins.update({"1": "HOST_DM", "2": "GND"})
PARTS["J5"].pins.update({"DP": "HOST_DP", "DM": "HOST_DM"})
# ESD_H: IO1/IO1B are the same internal channel (feed-through pads), likewise
# IO2/IO2B -- so one channel per line: IO1/IO1B -> HOST_DP, IO2/IO2B -> HOST_DM.
PARTS["ESD_H"].pins.update({
    "IO1": "HOST_DP", "IO1B": "HOST_DP",
    "IO2": "HOST_DM", "IO2B": "HOST_DM",
    "VBUS": "HOST_VBUS",
})
# Probe points (DESIGN SS8.1, fixes G-3): TP1/TP2/TP3 on D+/D-/GND at the port.
PARTS["TP1"].pins["1"] = "HOST_DP"
PARTS["TP2"].pins["1"] = "HOST_DM"
PARTS["TP3"].pins["1"] = "GND"

# --- Host VBUS switch control (DESIGN SS6/SS8.1): EN/FLG *are* the function
# node on the PICO side (no series element), per the guard-net docstring case.
PARTS["PICO"].pins.update({"22": "HOST_VBUS_EN", "20": "HOST_VBUS_FLT"})
PARTS["U_HSW"].pins.update({"EN": "HOST_VBUS_EN", "FLG": "HOST_VBUS_FLT"})

# --- Current sense (DESIGN SS8.1/SS10): shunt placed *upstream* of U_HSW so
# it measures switch + downstream draw without disturbing HOST_VBUS (Task 4's
# wiring, unchanged): VBUS_SEL -> R_SHUNT -> HOST_5V_IN -> U_HSW IN. U_ISNS
# senses across the shunt; OUT is itself the GP26 ADC function node (no
# series element between them, so no hop -- same pattern as ISENSE/NATIVE_
# VBUS_DET/DEV_VBUS_DET in the module docstring).
PARTS["R_SHUNT"].pins.update({"1": "VBUS_SEL", "2": "HOST_5V_IN"})
PARTS["U_HSW"].pins["IN"] = "HOST_5V_IN"
PARTS["U_ISNS"].pins.update({
    "IN+": "VBUS_SEL", "IN-": "HOST_5V_IN",
    "OUT": "ISENSE", "VS": "P3V3", "GND": "GND",
})
PARTS["PICO"].pins["31"] = "ISENSE"

# --- Device port (DESIGN SS8.2): PICO GP18/GP19 -> 22R series -> DEV_DP/DM ->
# J9, with ESD_D across the pair. J9 numbering follows J8's convention
# (1 VBUS, 2 D-, 3 D+, 4 ID, 5 GND, 6 shield); ID stays unassigned (device-
# only connector, same treatment as J8's untouched D+/D-/ID/shield in Task 4).
PARTS["PICO"].pins.update({"24": "GP18", "25": "GP19"})
PARTS["R_DDP"].pins.update({"1": "GP18", "2": "DEV_DP"})
PARTS["R_DDM"].pins.update({"1": "GP19", "2": "DEV_DM"})
PARTS["ESD_D"].pins.update({
    "IO1": "DEV_DP", "IO1B": "DEV_DP",
    "IO2": "DEV_DM", "IO2B": "DEV_DM",
    "VBUS": "J9_VBUS",
})
PARTS["J9"].pins.update({"1": "J9_VBUS", "2": "DEV_DM", "3": "DEV_DP", "5": "GND", "6": "GND"})

# --- Device VBUS-detect divider (DESIGN SS8.2): J9_VBUS -> 8.2k/8.2k -> GND,
# midpoint = DEV_VBUS_DET = GP27 (divider midpoint, itself the function node).
PARTS["R_J9VD_T"].pins.update({"1": "J9_VBUS", "2": "DEV_VBUS_DET"})
PARTS["R_J9VD_B"].pins.update({"1": "DEV_VBUS_DET", "2": "GND"})
PARTS["PICO"].pins["32"] = "DEV_VBUS_DET"

# --- Device D+ pull-up gate (review fix): a gate FET driven from the
# DEV_VBUS_DET divider midpoint (~2.5V) is a source-follower, not a switch --
# it can only pull D+ to ~Vgate-Vth (~1.7V), below the >=3.0V FS-attach
# threshold, and its body diode leaks D+ -> the pull-up net whenever D+ is
# driven high. No FET part choice fixes a gate-voltage ceiling, so DESIGN
# SS8.2 now specifies firmware-driven soft-connect (sanctioned alternative:
# "small FET or firmware-driven"): R_DPU (1.5k) sits DEV_DP -> DEV_DP_PU_EN,
# and firmware drives GP11 high (3.3V) to present the pull-up or
# reconfigures it to Hi-Z input to soft-disconnect. The gate decision (host
# VBUS actually present) comes from firmware reading DEV_VBUS_DET (GP27),
# not from any netlist-level gating.
PARTS["R_DPU"].pins.update({"1": "DEV_DP", "2": "DEV_DP_PU_EN"})
PARTS["PICO"].pins["15"] = "DEV_DP_PU_EN"   # GP11 (pad 15 per _PICO_GPIO_PAD)

# --- Native VBUS-detect hardware test tap (DESIGN SS9): VBUS_NET -> JP4 ->
# 8.2k/8.2k -> GND, midpoint = NATIVE_VBUS_DET = GP16. JP4 (fitted by default)
# is the divider's top-leg jumper so divider_ratio hops it transparently.
PARTS["JP4"].pins.update({"1": "VBUS_NET", "2": "NVD_TOP"})
PARTS["R_NVD_T"].pins.update({"1": "NVD_TOP", "2": "NATIVE_VBUS_DET"})
PARTS["R_NVD_B"].pins.update({"1": "NATIVE_VBUS_DET", "2": "GND"})
PARTS["PICO"].pins["21"] = "NATIVE_VBUS_DET"

# --- DNP odds and ends -------------------------------------------------
# D_J9_BUSPWR (DNP, SOD-123 diode default pad1=A/pad2=K): documents the
# optional J9-VBUS -> VBUS_NET bus-power path per the direction ruling --
# anode on J9_VBUS, cathode on VBUS_NET, so host VBUS could only ever feed
# the board rail, never backfeed the host connector. Never populated (dnp),
# so it can't bridge the two nets in the graph helpers.
PARTS["D_J9_BUSPWR"].pins.update({"1": "J9_VBUS", "2": "VBUS_NET"})
# U_INA219_ALT wiring: see Task 14b section below (module footer) -- it now
# gets real net assignments instead of an all-nc placeholder.


# --------------------------------------------------------------------------
# Task 7: peripherals, spares, breakout ties, pin-map lock
# --------------------------------------------------------------------------

# --- UART0 console (DESIGN SS10/SS6): GP12/GP13 -> J_UART (GND done Task 4).
# Direct function nodes (no series element), like the guard/I2C/button cases.
PARTS["PICO"].pins.update({"16": "UART0_TX", "17": "UART0_RX"})
PARTS["J_UART"].pins.update({"1": "UART0_TX", "2": "UART0_RX"})

# --- STEMMA-QT / Qwiic I2C0 (DESIGN SS10): GP8/GP9 -> J_STEMMA; pad2=P3V3
# deferred from Task 4 (GND already done there).
PARTS["PICO"].pins.update({"11": "I2C0_SDA", "12": "I2C0_SCL"})
PARTS["J_STEMMA"].pins.update({"2": "P3V3", "3": "I2C0_SDA", "4": "I2C0_SCL"})

# --- User LED (DESIGN SS10): GP10 -> R_LED_USER (series, Task 3 part) ->
# LED_USER anode -> cathode -> GND. Source-series convention: PICO keeps the
# bare "GP10" net, the resistor's far side carries the function name so
# PINMAP hops through it -- mirrors Rt1-5/R_HDP/R_HDM. LED pad numbering
# follows the KiCad "LED" symbol default (pad1=K/cathode, pad2=A/anode),
# same as LED_PWR (Task 4). Unlike LED_PWR's "LED_PWR_A" (no GPIO hops
# through it, so the suffix is just documentation), LED_USER's anode net is
# named exactly "LED_USER" (no suffix) because that's the literal string
# _hop_label must return for PINMAP[10] to read "LED_USER".
PARTS["PICO"].pins["14"] = "GP10"
PARTS["R_LED_USER"].pins.update({"1": "GP10", "2": "LED_USER"})
PARTS["LED_USER"].pins.update({"1": "GND", "2": "LED_USER"})

# --- User button (DESIGN SS10): GP14 -> SW_USER -> GND. Direct function
# node (no series element), like SW1/RESET.
PARTS["PICO"].pins["19"] = "BTN_USER"
PARTS["SW_USER"].pins.update({"1": "BTN_USER", "2": "GND"})

# --- Spare / breakout-only pins (DESIGN SS6): GP7/GP22/GP28 exist only on
# PICO + the breakout pads -- no other component touches them, so each just
# gets its own bare "GPn" net (the breakout tie loop below mirrors it out).
PARTS["PICO"].pins.update({"10": "GP7", "29": "GP22", "34": "GP28"})

# --- Breakout ties (fixes G-1): every one of PICO's 40 pads must now be
# non-None (asserted by test_pinmap/test_breakout indirectly); tie J1B/J2B
# pin-for-pin per the corrected pad convention (task-7 controller ruling,
# corrects the brief's test): J1B pads "1".."20" <-> PICO physical pins
# 1-20; J2B pads "1".."20" <-> PICO physical pins 21-40 (pad = physical -
# 20). Implemented as a loop over PARTS["PICO"].pins so it can't drift from
# whatever the model actually wired.
for _pico_pad, _net in PARTS["PICO"].pins.items():
    _n = int(_pico_pad)
    if _n <= 20:
        PARTS["J1B"].pins[str(_n)] = _net
    else:
        PARTS["J2B"].pins[str(_n - 20)] = _net


# --------------------------------------------------------------------------
# Task 8: connectivity lint -- nc entries + wiring fixes found by test_lint
# --------------------------------------------------------------------------
# J8 (DESIGN SS7 table: "power-only (VBUS+GND; D+/D- NC)"): D-/D+/ID are
# genuinely unused on this power-only micro-B -- no-connect, not a bug.
PARTS["J8"].nc |= {"2", "3", "4"}

# J8 shield (pad 6, per the Task-3 comment "6 shield"): wiring bug, not a
# legitimate nc. J9 is the same usb_microb footprint and Task 6 already ties
# its shield pad to GND (PARTS["J9"].pins["6"] = "GND"); J8 never got the
# matching tie in Task 4. Fixed here for consistency instead of nc'ing it.
PARTS["J8"].pins["6"] = "GND"

# J9 ID (DESIGN SS8.2: self-powered, detect-only device port -- no OTG role
# for this connector): genuinely unused, no-connect.
PARTS["J9"].nc |= {"4"}

# --------------------------------------------------------------------------
# Task 14b: model pass -- Adafruit-style DNP realization (footprint present +
# wired + dnp=True, replacing the earlier "stand-in footprint, all pins nc"
# placeholders), HOST_VBUS_EN pulldown, capacitor voltage ratings. See
# hw/build_board.py for the matching board-side DNP-attribute + netclass
# work (J9_VBUS added to the Power pattern list).
# --------------------------------------------------------------------------

# --- Host-VBUS-EN pulldown wiring (see PARTS declaration above for the
# rationale): HOST_VBUS_EN -> GND.
PARTS["R_HVEN_PD"].pins.update({"1": "HOST_VBUS_EN", "2": "GND"})

# --- U_INA219_ALT wiring (Adafruit-style DNP realization -- see PARTS
# declaration above for the SOT-23-8 padmap/datasheet source): parallels
# U_ISNS across the same shunt (IN+/IN- on R_SHUNT's own VBUS_SEL/
# HOST_5V_IN nets), GND/VS on the board rails, SDA/SCL on the existing I2C0
# bus; A0/A1 both grounded -> I2C address 0x40 (TI SBOS448 Table 2, "Serial
# Bus Address" -- both address pins low).
PARTS["U_INA219_ALT"].pins.update({
    "IN+": "VBUS_SEL", "IN-": "HOST_5V_IN", "GND": "GND", "VS": "P3V3",
    "SDA": "I2C0_SDA", "SCL": "I2C0_SCL", "A0": "GND", "A1": "GND",
})


# --------------------------------------------------------------------------
# Derived: NETS / net_pins
# --------------------------------------------------------------------------

def _compute_nets() -> dict[str, set[tuple[str, str]]]:
    nets: dict[str, set[tuple[str, str]]] = {}
    for ref, part in PARTS.items():
        for pad, net in part.pins.items():
            if net is not None:
                nets.setdefault(net, set()).add((ref, pad))
    return nets


class _NetsView(Mapping):
    """dict[str, set[(ref, pad)]] view, always recomputed from PARTS."""

    def __getitem__(self, key):
        return _compute_nets()[key]

    def __iter__(self):
        return iter(_compute_nets())

    def __len__(self):
        return len(_compute_nets())


NETS = _NetsView()


def net_pins(net: str) -> set[tuple[str, str]]:
    """All (ref, pad) pairs assigned to `net`."""
    return _compute_nets().get(net, set())


# --------------------------------------------------------------------------
# Helpers: series_between, divider_ratio
# --------------------------------------------------------------------------

_RESISTOR_CLASSES = {"r0402", "shunt"}
_JUMPER_CLASSES = {"hdr_1x02"}


def _resistor_pair(part: Part) -> tuple[str, str] | None:
    """The two distinct nets on a *fitted* 2-pin resistor/jumper, else None.

    A dnp part is never populated, so it can never bridge two nets.
    """
    if part.dnp or len(part.pins) != 2:
        return None
    vals = list(part.pins.values())
    if None in vals or vals[0] == vals[1]:
        return None
    return vals[0], vals[1]


def series_between(net_a: str, net_b: str, r_ref: str | None = None) -> bool:
    """True iff a single 2-pin resistor bridges net_a and net_b.

    Any resistor-class part qualifies when r_ref is None; otherwise exactly
    that ref must be the bridge (and need not be resistor-classed -- e.g. a
    jumper ref can be checked too).
    """
    for ref, part in PARTS.items():
        if r_ref is not None:
            if ref != r_ref:
                continue
        elif part.fp_class not in _RESISTOR_CLASSES:
            continue
        pair = _resistor_pair(part)
        if pair and {pair[0], pair[1]} == {net_a, net_b}:
            return True
    return False


def _parse_ohms(value: str) -> float | int:
    """Parse a resistor value string ("8.2k", "27", "1.5k", "15k") to ohms."""
    s = value.strip()
    suffix = {"k": 1e3, "K": 1e3, "m": 1e-3, "M": 1e6}
    mult = 1.0
    if s and s[-1] in suffix:
        mult = suffix[s[-1]]
        s = s[:-1]
    n = float(s) * mult
    return int(n) if n == int(n) else n


def _jumper_neighbor(net: str) -> str | None:
    """The net on the far side of a *fitted* 2-pin jumper touching `net`, if
    exactly one such jumper exists; else None."""
    found = None
    for part in PARTS.values():
        if part.fp_class not in _JUMPER_CLASSES:
            continue
        pair = _resistor_pair(part)
        if not pair or net not in pair:
            continue
        other = pair[1] if pair[0] == net else pair[0]
        if found is not None and found != other:
            return None  # ambiguous
        found = other
    return found


def divider_ratio(top_net: str, mid_net: str) -> tuple[float | int, float | int]:
    """(r_top_ohms, r_bot_ohms) for top_net -R-> mid_net -R-> GND.

    Transparently traverses a single fitted 2-pin jumper (e.g. JP4) that
    sits in the top leg between top_net and the top resistor.
    """
    top_candidates = {top_net}
    hop = _jumper_neighbor(top_net)
    if hop is not None:
        top_candidates.add(hop)

    r_top = r_bot = None
    for part in PARTS.values():
        if part.fp_class not in _RESISTOR_CLASSES:
            continue
        pair = _resistor_pair(part)
        if not pair or mid_net not in pair:
            continue
        other = pair[1] if pair[0] == mid_net else pair[0]
        if other in top_candidates:
            r_top = _parse_ohms(part.value)
        elif other == "GND":
            r_bot = _parse_ohms(part.value)
    if r_top is None or r_bot is None:
        raise ValueError(f"divider_ratio({top_net!r}, {mid_net!r}): resistors not found")
    return (r_top, r_bot)


# --------------------------------------------------------------------------
# PINMAP: GPIO -> function label, derived from PARTS["PICO"].pins
# --------------------------------------------------------------------------

# Pico / Pico 2 physical pinout: footprint pad number -> GPIO number, for
# every pad that carries a GPIO (fixed silicon/board fact, not a per-task
# wiring decision -- cross-checked against the stock RaspberryPi_Pico symbol
# in Task 2 and against DESIGN.md SS5/SS6).
_PICO_GPIO_PAD: dict[str, int] = {
    "1": 0, "2": 1, "4": 2, "5": 3, "6": 4, "7": 5, "9": 6, "10": 7,
    "11": 8, "12": 9, "14": 10, "15": 11, "16": 12, "17": 13, "19": 14,
    "20": 15, "21": 16, "22": 17, "24": 18, "25": 19, "26": 20, "27": 21,
    "29": 22, "31": 26, "32": 27, "34": 28,
}

_HOP_CLASSES = _RESISTOR_CLASSES | _JUMPER_CLASSES

# Bare "GPn"-style net name -- see the module docstring: PINMAP only ever
# hops (source-series or guard) when the PICO-side net itself looks like
# this, never for a named function net (e.g. DEV_DP_PU_EN) that merely
# happens to have a single resistor/jumper neighbor.
_BARE_GPIO_RE = re.compile(r"^GP\d+$")


def _hop_label(net: str) -> str:
    """See the module docstring's net-naming convention: hop through a single
    2-pin resistor/fitted-jumper touching `net`, but only when `net` is a bare
    "GPn"-style name. A single neighbor that isn't GND reports the far side's
    function name (GP1 -Rt1-> TRACECLK). A single *jumper* neighbor that *is*
    GND reports the literal "GUARD" label (GP0/GP6 via JP2/JP3) -- GND isn't a
    function name, so the label has to be derived rather than hopped-to.
    Anything else (zero neighbors, more than one -- a divider midpoint has a
    top leg + a GND leg -- a non-jumper landing on GND, or `net` not being a
    bare GPn) leaves the net name unchanged."""
    if not _BARE_GPIO_RE.match(net):
        return net
    hits = []
    for part in PARTS.values():
        if part.fp_class not in _HOP_CLASSES:
            continue
        pair = _resistor_pair(part)
        if not pair or net not in pair:
            continue
        other = pair[1] if pair[0] == net else pair[0]
        hits.append((other, part.fp_class))
    if len(hits) != 1:
        return net
    other, fp_class = hits[0]
    if other == "GND":
        return "GUARD" if fp_class in _JUMPER_CLASSES else net
    return other


def _compute_pinmap() -> dict[int, str]:
    pico_pins = PARTS["PICO"].pins
    result: dict[int, str] = {}
    for pad, gpio in _PICO_GPIO_PAD.items():
        net = pico_pins.get(pad)
        if net is not None:
            result[gpio] = _hop_label(net)
    return result


class _PinMapView(Mapping):
    """dict[int, str] view, always recomputed from PARTS["PICO"].pins."""

    def __getitem__(self, key):
        return _compute_pinmap()[key]

    def __iter__(self):
        return iter(_compute_pinmap())

    def __len__(self):
        return len(_compute_pinmap())


PINMAP = _PinMapView()


# --------------------------------------------------------------------------
# Task 8: emit_netlist -- KiCad-style netlist export for the schematic
# cross-check (Task 9 compares this against `kicad-cli sch export netlist`)
# --------------------------------------------------------------------------

def emit_netlist(path: str) -> None:
    """Write a KiCad E-format s-expression netlist derived from PARTS/NETS.

    Task 14b (Adafruit-style DNP realization): DNP parts are now INCLUDED,
    same as any other part -- a `(comp ...)` entry (with a nested `(property
    (name "dnp") (value "yes"))`, mirroring how `kicad-cli sch export
    netlist` marks a schematic symbol's `(dnp yes)` instance attribute) and
    their pins' `(node ...)` entries on every net they touch. This matches
    `hw/gen_sch.py`, which now places DNP parts as real symbol instances
    (footprint present + wired + flagged `(dnp yes)`) instead of omitting
    them -- so the reference netlist this function writes and the schematic-
    exported netlist stay comparable pad-for-pad (`--compare-netlists`).
    Pin numbers are footprint pad numbers: each logical pin name is
    translated through the part's padmap (identity if the part has none).
    """
    lines = ['(export (version "E")']

    lines.append("  (components")
    for ref in sorted(PARTS):
        p = PARTS[ref]
        lib, fp = FP[p.fp_class]
        if p.dnp:
            lines.append(f'    (comp (ref {ref}) (value "{p.value}") (footprint {lib}:{fp})')
            lines.append('      (property (name "dnp") (value "yes"))')
            lines.append("    )")
        else:
            lines.append(f'    (comp (ref {ref}) (value "{p.value}") (footprint {lib}:{fp}))')
    lines.append("  )")

    lines.append("  (nets")
    code = 0
    for name in sorted(NETS):
        nodes = sorted((ref, PARTS[ref].pad_number(pad)) for ref, pad in NETS[name])
        if not nodes:
            continue  # shouldn't happen -- every net has >=1 member by construction
        code += 1
        lines.append(f'    (net (code {code}) (name "{name}")')
        for ref, pad_no in nodes:
            lines.append(f"      (node (ref {ref}) (pin {pad_no}))")
        lines.append("    )")
    lines.append("  )")

    lines.append(")")

    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
