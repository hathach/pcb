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
    a jumper, ...) needs a *different* net name on each side.
  - For a GPIO that reaches its function through a single source-series
    element (Rt1-5 for the trace bus, the 22R USB series resistors, the LED
    series resistors), PICO's own pin keeps a bare "GPn" net; the *far* side
    of that element carries the function name (e.g. "GP1" -Rt1-> "TRACECLK",
    "GP20" -R_HDP-> "HOST_DP"). PINMAP hops through that element to report
    the function name for the GPIO.
  - For a GPIO that *is itself* the function node -- guard pins tied straight
    to GND through a fitted jumper, or a resistor-divider midpoint (ISENSE,
    NATIVE_VBUS_DET, DEV_VBUS_DET, HOST_VBUS_EN/FLT, I2C/UART/button pins) --
    PICO's own pin should be named with the function directly (e.g. "GUARD",
    "NATIVE_VBUS_DET"). PINMAP only hops when exactly one 2-pin
    resistor/jumper touches the net and the far side isn't GND, so divider
    midpoints (which have two such neighbors: the top leg and the GND leg)
    and guard nets (whose one neighbor *is* GND) are correctly left alone.
"""

from __future__ import annotations

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

# --- Device D+ pull-up gate FET ---------------------------------------------
# SOT-23, KiCad Q_NMOS_GSD pad convention: 1=G, 2=S, 3=D.
_add(Part(
    "Q_DPU", "2N7002", "fet3",
    _pins("G", "S", "D"),
    padmap={"G": "1", "S": "2", "D": "3"},
))

# --- Trace source-series resistors (27R, at the Pico socket pins) ----------
for _ref in ("Rt1", "Rt2", "Rt3", "Rt4", "Rt5"):
    _add(Part(_ref, "27", "r0402", _pins("1", "2")))

# --- Reset debounce cap (100n, DNP per DESIGN "Reset") ----------------------
_add(Part("C_NRESET", "100n", "c0402", _pins("1", "2"), dnp=True))

# --- USB D+/D- series resistors (22R) --------------------------------------
_add(Part("R_HDP", "22", "r0402", _pins("1", "2")))   # host D+ series (GP20 -> HOST_DP)
_add(Part("R_HDM", "22", "r0402", _pins("1", "2")))   # host D- series (GP21 -> HOST_DM)
_add(Part("R_DDP", "22", "r0402", _pins("1", "2")))   # device D+ series (GP18 -> DEV_DP)
_add(Part("R_DDM", "22", "r0402", _pins("1", "2")))   # device D- series (GP19 -> DEV_DM)

# --- Host D+/D- pulldowns (15k) ------------------------------------------
_add(Part("R_HDP_PD", "15k", "r0402", _pins("1", "2")))   # HOST_DP -> GND
_add(Part("R_HDM_PD", "15k", "r0402", _pins("1", "2")))   # HOST_DM -> GND

# --- Device D+ pull-up (1.5k), gated by Q_DPU ------------------------------
_add(Part("R_DPU", "1.5k", "r0402", _pins("1", "2")))

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
# 0.1uF at the connector) --------------------------------------------------
_add(Part("C_HVBUS_BULK", "22u", "c0805", _pins("1", "2")))
_add(Part("C_HVBUS_100n", "100n", "c0402", _pins("1", "2")))

# --- Probe points --------------------------------------------------------
_add(Part("TP1", "TP", "testpoint", _pins("1")))
_add(Part("TP2", "TP", "testpoint", _pins("1")))
_add(Part("TP3", "TP", "testpoint", _pins("1")))

# --- DNP parts (DESIGN SS14 / brief G-7) ------------------------------------
# U_INA219_ALT: INA219 is SOT23-8, not in FP; borrows the isense (SOT-23-5)
# footprint as an accepted stand-in since the part is never populated.
_add(Part("U_INA219_ALT", "INA219", "isense", _numbered(5), dnp=True))
# D_J9_BUSPWR: optional J9-VBUS -> VBUS_NET bus-power diode (DESIGN SS8.2/SS14).
_add(Part("D_J9_BUSPWR", "1N4148W", "sod123", _pins("1", "2"), dnp=True))
# J_TRACE_TP: optional 1x6 100-mil test header on the five trace nets + GND.
_add(Part("J_TRACE_TP", "TRACE_TP", "hdr_1x06", _numbered(6), dnp=True))


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

# Guard pins (DESIGN SS5.4/SS6): GP0 (pin 1) / GP6 (pin 9) each get a 2-pin
# jumper straight to GND (default fitted). GPn *is* the function node here
# (no series element to a differently-named net), per the guard-net case in
# the module docstring.
PARTS["PICO"].pins.update({"1": "GP0", "9": "GP6"})
PARTS["JP2"].pins.update({"1": "GP0", "2": "GND"})
PARTS["JP3"].pins.update({"1": "GP6", "2": "GND"})


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


def _hop_label(net: str) -> str:
    """See the module docstring's net-naming convention: hop through a single
    2-pin resistor/fitted-jumper touching `net` (unless it lands on GND, or
    there's more than one such neighbor -- a divider midpoint has two)."""
    hits = []
    for part in PARTS.values():
        if part.fp_class not in _HOP_CLASSES:
            continue
        pair = _resistor_pair(part)
        if not pair or net not in pair:
            continue
        hits.append(pair[1] if pair[0] == net else pair[0])
    if len(hits) == 1 and hits[0] != "GND":
        return hits[0]
    return net


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
