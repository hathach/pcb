"""Deterministic KiCad 9 schematic generator (Task 9, Path B).

Emits `pico2_trace.kicad_sch` directly as an s-expression file built from the
`hw.netlist` model (PARTS/NETS), rather than relying on SKiDL. Path A (SKiDL)
was spiked and rejected: SKiDL cannot create new symbols, so every stock part
(USB connectors, TPS2051B, INA180, USBLC6-2SC6, ...) would need a real KiCad
stock symbol whose *pin numbering* is verified to match this model's already-
committed padmaps (chosen from real datasheets in Task 3). That verification
is a real correctness risk for ~10 stock parts. Path B sidesteps it entirely:
every non-custom part uses a small generic lib symbol (one per pin-count) that
*we* define, so the schematic pin number is always exactly
`part.pad_number(pin)` -- the same value `emit_netlist()` writes to the
reference netlist -- by construction, not by hoping a stock symbol matches.

Layout: a plain grid ("shelf packing"), left-to-right/wrap, one symbol per
PARTS ref (DNP parts are skipped entirely, mirroring `emit_netlist`). Every
non-DNP pin gets a short wire stub ending in a `global_label` carrying the
*exact* net name (or a `no_connect` marker for pins in `part.nc`). Global
labels of the same text merge into one net across the whole (flat) sheet, so
no routing between parts is needed for netlist correctness -- see DESIGN
notes in the module docstring of `hw/netlist.py` for the net-naming
convention this mirrors exactly.

ERC notes (both netlist-neutral -- pin *number*/net assignment is unchanged,
only schematic-only ERC metadata):

* A handful of nets carry a `power_in` pin (from the fixed custom
  Pico_Module/MIPI20_DebugTrace/Cortex_Debug_10 symbols) with no `power_out`
  anywhere on that net (GND, VSYS, VBUS_NET, V5_JTRACE) -- KiCad's ERC wants
  one. All four get a stock `power:PWR_FLAG` (power_out) instance -- the
  standard "yes, I know" flag; unlike a named `power:GND`/`+3V3` symbol it
  does not imply a net name of its own, so it can't rename these nets (each
  already gets its real name from the ordinary per-pin global_label).
  These are the only pseudo-components (`#PWR00N` refs) added beyond the 48
  real parts; the netlist-parity checker strips `#`-prefixed refs.
* `sym/pico2_trace.kicad_sym`'s VTref pin on MIPI20_DebugTrace/Cortex_Debug_10
  was typed `power_out`, which put it in a "power output driving power
  output" ERC conflict with Pico_Module's real `power_out` 3V3 pin on the
  shared P3V3 net. KiCad's own stock `Connector:Conn_ARM_JTAG_SWD_10` types
  the same VTref pin `power_in` (it's a rail-sense pin, not a driven output)
  -- retyped to match that real convention.
"""

from __future__ import annotations

import re
import uuid

from hw.fp_lib import FP
from hw.netlist import PARTS

PROJECT = "pico2_trace"
OUT_PATH = "pico2_trace.kicad_sch"
SYM_LIB_PATH = "sym/pico2_trace.kicad_sym"

GRID = 1.27           # mm, KiCad's default connection grid -- every pin/wire
                      # endpoint we control is kept on this grid to avoid
                      # spurious "off connection grid" ERC warnings.
STUB = 5.08           # mm, pin -> label wire stub length (4 * GRID)
LABEL_ALLOW = 63.5    # mm, horizontal room reserved for label text (50 * GRID)
MAX_ROW_WIDTH = 762.0  # mm, shelf-packing wrap budget (600 * GRID)
MARGIN = 25.4         # mm, gap between packed cells (20 * GRID)
CELL_INSET_X = 5.08   # mm, generic-symbol origin inset from its cell's left edge
CELL_TOP = 12.7        # mm, generic-symbol origin inset from its cell's top edge
CELL_VMARGIN = 25.4    # mm, vertical margin added to every cell's pin span


def snap(v: float) -> float:
    return round(v / GRID) * GRID

CUSTOM_FP_CLASS = {"pico_socket": "Pico_Module", "mipi20": "MIPI20_DebugTrace", "cortex10": "Cortex_Debug_10"}


def u() -> str:
    return str(uuid.uuid4())


# --------------------------------------------------------------------------
# Indentation-tracking s-expr text builder
# --------------------------------------------------------------------------

class Sx:
    def __init__(self) -> None:
        self.lines: list[str] = []
        self.depth = 0

    def raw(self, text: str) -> None:
        indent = "\t" * self.depth
        for ln in text.splitlines():
            self.lines.append(indent + ln if ln else ln)

    def open(self, text: str) -> None:
        self.lines.append("\t" * self.depth + text)
        self.depth += 1

    def close(self, text: str = ")") -> None:
        self.depth -= 1
        self.lines.append("\t" * self.depth + text)

    def line(self, text: str) -> None:
        self.lines.append("\t" * self.depth + text)

    def text(self) -> str:
        return "\n".join(self.lines) + "\n"


def prop(sx: Sx, name: str, value: str, x: float, y: float, hide: bool = False) -> None:
    sx.open(f'(property "{name}" "{value}"')
    sx.line(f"(at {x:g} {y:g} 0)")
    sx.open("(effects")
    sx.open("(font")
    sx.line("(size 1.27 1.27)")
    sx.close()
    if hide:
        sx.line("(hide yes)")
    sx.close()
    sx.close()


# --------------------------------------------------------------------------
# Custom symbol reuse (Pico_Module / MIPI20_DebugTrace / Cortex_Debug_10)
# --------------------------------------------------------------------------

def _extract_block(text: str, name: str) -> str:
    idx = text.index(f'(symbol "{name}"')
    depth = 0
    i = idx
    while True:
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return text[idx : i + 1]
        i += 1


def _extract_pins(block: str) -> dict[str, dict]:
    pat = re.compile(
        r'\(pin (\w+) \w+\s*\n\s*\(at ([\-0-9.]+) ([\-0-9.]+) (\d+)\)\s*\n\s*\(length[^\n]*\)\s*\n\s*\(name "([^"]+)"'
        r'.*?\(number "([^"]+)"',
        re.S,
    )
    out = {}
    for t, x, y, rot, name, num in pat.findall(block):
        out[num] = {"type": t, "x": float(x), "y": float(y), "rot": int(rot), "name": name}
    return out


with open(SYM_LIB_PATH) as _f:
    _SYMLIB_TEXT = _f.read()

CUSTOM_BLOCKS = {name: _extract_block(_SYMLIB_TEXT, name) for name in CUSTOM_FP_CLASS.values()}
CUSTOM_PINS = {name: _extract_pins(blk) for name, blk in CUSTOM_BLOCKS.items()}
CUSTOM_YSPAN = {name: (max(p["y"] for p in pins.values()) - min(p["y"] for p in pins.values())) for name, pins in CUSTOM_PINS.items()}


# --------------------------------------------------------------------------
# Generic per-pin-count symbols
# --------------------------------------------------------------------------

GENERIC_COUNTS = sorted({len(p.pins) for p in PARTS.values() if not p.dnp} - {40, 20, 10} | {20})
# 20 is shared: J1B/J2B (generic) AND J3 (custom, also 20 pins) -- keep a
# generic 20-pin symbol available for J1B/J2B regardless of J3's custom one.


def generic_lib_id(n: int) -> str:
    return f"gen:GEN{n}"


def emit_generic_symbol(sx: Sx, n: int, name: str | None = None) -> None:
    """Emit one generic N-pin symbol. `name` is the symbol's own top-level
    name: `gen:GENn` when embedding into a schematic's lib_symbols cache,
    or bare `GENn` when writing the standalone sym/gen.kicad_sym library."""
    lib_id = name if name is not None else generic_lib_id(n)
    top = (n - 1) * 2.54
    sx.open(f'(symbol "{lib_id}"')
    sx.open("(pin_names")
    sx.line("(offset 0.508)")
    sx.close()
    sx.line("(exclude_from_sim no)")
    sx.line("(in_bom yes)")
    sx.line("(on_board yes)")
    prop(sx, "Reference", "REF", 0, 4.0)
    prop(sx, "Value", "VAL", 0, -top - 4.0)
    prop(sx, "Footprint", "", 0, 0, hide=True)
    prop(sx, "Datasheet", "", 0, 0, hide=True)
    sx.open(f'(symbol "GEN{n}_0_1"')
    sx.open("(rectangle")
    sx.line("(start -6 2)")
    sx.line(f"(end -1 {-top - 2:g})")
    sx.open("(stroke")
    sx.line("(width 0.254)")
    sx.line("(type default)")
    sx.close()
    sx.open("(fill")
    sx.line("(type none)")
    sx.close()
    sx.close()
    sx.close()
    sx.open(f'(symbol "GEN{n}_1_1"')
    for k in range(n):
        y = -k * 2.54
        sx.open("(pin passive line")
        sx.line(f"(at 0 {y:g} 180)")
        sx.line("(length 2.54)")
        sx.open('(name "~"')
        sx.open("(effects")
        sx.open("(font")
        sx.line("(size 1.27 1.27)")
        sx.close()
        sx.close()
        sx.close()
        sx.open(f'(number "{k + 1}"')
        sx.open("(effects")
        sx.open("(font")
        sx.line("(size 1.27 1.27)")
        sx.close()
        sx.close()
        sx.close()
        sx.close()
    sx.close()
    sx.line("(embedded_fonts no)")
    sx.close()


# --------------------------------------------------------------------------
# Stock power symbol (power:PWR_FLAG) -- verbatim, standard KiCad definition
# --------------------------------------------------------------------------

# Copied verbatim from this system's /usr/share/kicad/symbols/power.kicad_sym
# (KiCad 9.0.2) so ERC's "library symbol mismatch" check doesn't flag our
# embedded copy against the real stock one.
PWR_FLAG_SYMBOL = """(symbol "power:PWR_FLAG"
\t(power)
\t(pin_numbers
\t\t(hide yes)
\t)
\t(pin_names
\t\t(offset 0)
\t\t(hide yes)
\t)
\t(exclude_from_sim no)
\t(in_bom yes)
\t(on_board yes)
\t(property "Reference" "#FLG"
\t\t(at 0 1.905 0)
\t\t(effects
\t\t\t(font
\t\t\t\t(size 1.27 1.27)
\t\t\t)
\t\t\t(hide yes)
\t\t)
\t)
\t(property "Value" "PWR_FLAG"
\t\t(at 0 3.81 0)
\t\t(effects
\t\t\t(font
\t\t\t\t(size 1.27 1.27)
\t\t\t)
\t\t)
\t)
\t(property "Footprint" ""
\t\t(at 0 0 0)
\t\t(effects
\t\t\t(font
\t\t\t\t(size 1.27 1.27)
\t\t\t)
\t\t\t(hide yes)
\t\t)
\t)
\t(property "Datasheet" "~"
\t\t(at 0 0 0)
\t\t(effects
\t\t\t(font
\t\t\t\t(size 1.27 1.27)
\t\t\t)
\t\t\t(hide yes)
\t\t)
\t)
\t(property "Description" "Special symbol for telling ERC where power comes from"
\t\t(at 0 0 0)
\t\t(effects
\t\t\t(font
\t\t\t\t(size 1.27 1.27)
\t\t\t)
\t\t\t(hide yes)
\t\t)
\t)
\t(property "ki_keywords" "flag power"
\t\t(at 0 0 0)
\t\t(effects
\t\t\t(font
\t\t\t\t(size 1.27 1.27)
\t\t\t)
\t\t\t(hide yes)
\t\t)
\t)
\t(symbol "PWR_FLAG_0_0"
\t\t(pin power_out line
\t\t\t(at 0 0 90)
\t\t\t(length 0)
\t\t\t(name "~"
\t\t\t\t(effects
\t\t\t\t\t(font
\t\t\t\t\t\t(size 1.27 1.27)
\t\t\t\t\t)
\t\t\t\t)
\t\t\t)
\t\t\t(number "1"
\t\t\t\t(effects
\t\t\t\t\t(font
\t\t\t\t\t\t(size 1.27 1.27)
\t\t\t\t\t)
\t\t\t\t)
\t\t\t)
\t\t)
\t)
\t(symbol "PWR_FLAG_0_1"
\t\t(polyline
\t\t\t(pts
\t\t\t\t(xy 0 0) (xy 0 1.27) (xy -1.016 1.905) (xy 0 2.54) (xy 1.016 1.905) (xy 0 1.27)
\t\t\t)
\t\t\t(stroke
\t\t\t\t(width 0)
\t\t\t\t(type default)
\t\t\t)
\t\t\t(fill
\t\t\t\t(type none)
\t\t\t)
\t\t)
\t)
\t(embedded_fonts no)
)"""

# Nets that need an explicit power driver for ERC (power_in pin, from a fixed
# custom symbol, with no power_out anywhere on that same net -- see module
# docstring). Each gets a power:PWR_FLAG instance; the net keeps its real
# name via the ordinary per-pin global_label (PWR_FLAG doesn't imply one).
POWER_FLAG_NETS = ["GND", "VSYS", "VBUS_NET", "V5_JTRACE"]


# --------------------------------------------------------------------------
# Layout: shelf packing
# --------------------------------------------------------------------------

def part_kind(ref: str, fp_class: str) -> str | None:
    return CUSTOM_FP_CLASS.get(fp_class)


def cell_size(ref: str) -> tuple[float, float, int]:
    """(width, height, n_pins) for a part's packed cell."""
    p = PARTS[ref]
    n = len(p.pins)
    kind = part_kind(ref, p.fp_class)
    if kind is not None:
        width = 2 * (16.54 + STUB + LABEL_ALLOW)
        height = CUSTOM_YSPAN[kind] + CELL_VMARGIN
    else:
        width = CELL_INSET_X + STUB + LABEL_ALLOW
        height = (n - 1) * 2.54 + CELL_VMARGIN
    return width, height, n


def pack(refs: list[str]) -> dict[str, tuple[float, float]]:
    """ref -> (origin_x, origin_y), shelf-packed left to right, wrapping rows.

    Every returned origin is snapped to `GRID` so that generic-symbol pins
    (whose local offsets are already grid-aligned) land exactly on the
    connection grid regardless of any fractional drift accumulated from a
    custom symbol's cell width earlier in the same row.
    """
    origins: dict[str, tuple[float, float]] = {}
    x = MARGIN
    row_y = MARGIN
    row_h = 0.0
    for ref in refs:
        w, h, _n = cell_size(ref)
        if x + w > MAX_ROW_WIDTH and x > MARGIN:
            x = MARGIN
            row_y += row_h + MARGIN
            row_h = 0.0
        kind = part_kind(ref, PARTS[ref].fp_class)
        if kind is not None:
            ox = snap(x + w / 2)
            oy = snap(row_y + h / 2)
        else:
            ox = snap(x + CELL_INSET_X)
            oy = snap(row_y + CELL_TOP)
        origins[ref] = (ox, oy)
        x += w + MARGIN
        row_h = max(row_h, h)
    return origins, (x if row_h == 0 else MAX_ROW_WIDTH), row_y + row_h + MARGIN


# --------------------------------------------------------------------------
# Main generation
# --------------------------------------------------------------------------

def main() -> None:
    non_dnp = sorted(ref for ref, p in PARTS.items() if not p.dnp)
    origins, _max_x, max_y = pack(non_dnp)

    # Power-flag pseudo-parts get their own trailing shelf row (all offsets
    # kept as multiples of GRID, same reasoning as pack()).
    flag_specs = [("PWR_FLAG", n) for n in POWER_FLAG_NETS]
    flag_x = MARGIN
    flag_y = max_y
    flag_origins = []
    for kind, net in flag_specs:
        flag_origins.append((kind, net, (flag_x, flag_y + 12.7)))
        flag_x += 38.1
    total_h = flag_y + 38.1 + MARGIN
    total_w = MAX_ROW_WIDTH + MARGIN

    root_uuid = u()
    sx = Sx()
    sx.open("(kicad_sch")
    sx.line("(version 20250114)")
    sx.line('(generator "hw/gen_sch.py")')
    sx.line('(generator_version "9.0")')
    sx.line(f'(uuid "{root_uuid}")')
    sx.line(f'(paper "User" {total_w:.2f} {total_h:.2f})')
    sx.open("(title_block")
    sx.line('(title "pico2_trace motherboard")')
    sx.line('(comment 1 "Machine-generated grid schematic -- see DESIGN.md for the human-readable design.")')
    sx.close()

    # --- lib_symbols -------------------------------------------------
    sx.open("(lib_symbols")
    for name, blk in CUSTOM_BLOCKS.items():
        prefixed = blk.replace(f'(symbol "{name}"', f'(symbol "pico2_trace:{name}"', 1)
        sx.raw(prefixed)
    for n in GENERIC_COUNTS:
        emit_generic_symbol(sx, n)
    sx.raw(PWR_FLAG_SYMBOL)
    sx.close()

    # --- symbol instances + per-pin wires/labels/no_connects ---------
    wires_labels_ncs = Sx()
    wires_labels_ncs.depth = sx.depth

    ref_y_top = {}  # for Reference/Value property placement offsets

    for ref in non_dnp:
        p = PARTS[ref]
        n = len(p.pins)
        kind = part_kind(ref, p.fp_class)
        ox, oy = origins[ref]
        lib_id = f"pico2_trace:{kind}" if kind else generic_lib_id(n)
        lib_fp, fp_name = FP[p.fp_class]
        footprint = f"{lib_fp}:{fp_name}"

        sx.open("(symbol")
        sx.line(f'(lib_id "{lib_id}")')
        sx.line(f"(at {ox:g} {oy:g} 0)")
        sx.line("(unit 1)")
        sx.line("(exclude_from_sim no)")
        sx.line("(in_bom yes)")
        sx.line("(on_board yes)")
        sx.line("(dnp no)")
        sym_uuid = u()
        sx.line(f'(uuid "{sym_uuid}")')
        if kind is not None:
            ref_y = oy - CUSTOM_YSPAN[kind] / 2 - 6
            val_y = oy + CUSTOM_YSPAN[kind] / 2 + 6
        else:
            ref_y = oy - 12
            val_y = oy + (n - 1) * 2.54 + 8
        prop(sx, "Reference", ref, ox, ref_y)
        prop(sx, "Value", p.value, ox, val_y)
        prop(sx, "Footprint", footprint, ox, oy, hide=True)
        prop(sx, "Datasheet", "", ox, oy, hide=True)

        pin_uuids = {}
        if kind is not None:
            pin_defs = CUSTOM_PINS[kind]
            pin_numbers = sorted(pin_defs, key=int)
        else:
            pin_defs = None
            pin_numbers = [str(i) for i in range(1, n + 1)]
        for num in pin_numbers:
            puid = u()
            pin_uuids[num] = puid
            sx.line(f'(pin "{num}"')
            sx.depth += 1
            sx.line(f'(uuid "{puid}")')
            sx.depth -= 1
            sx.line(")")

        sx.open("(instances")
        sx.open(f'(project "{PROJECT}"')
        sx.open(f'(path "/{root_uuid}"')
        sx.line(f'(reference "{ref}")')
        sx.line("(unit 1)")
        sx.close()
        sx.close()
        sx.close()
        sx.close()  # (symbol

        # -- pins: wire stub + global_label, or no_connect --
        for key, net in p.pins.items():
            padnum = p.pad_number(key)
            if kind is not None:
                # KiCad negates Y when placing a symbol instance: lib_symbols
                # pin coordinates are authored Y-up (library/editor space),
                # while the schematic page is Y-down -- see module docstring.
                pdef = pin_defs[padnum]
                px, py = ox + pdef["x"], oy - pdef["y"]
                dx = STUB if pdef["x"] >= 0 else -STUB
                sx_, sy_ = px + dx, py
            else:
                idx = int(padnum) - 1
                px, py = ox, oy + idx * 2.54
                sx_, sy_ = px + STUB, py

            if key in p.nc:
                wires_labels_ncs.open("(no_connect")
                wires_labels_ncs.line(f"(at {px:g} {py:g})")
                wires_labels_ncs.line(f'(uuid "{u()}")')
                wires_labels_ncs.close()
                continue
            if net is None:
                continue  # shouldn't happen for non-DNP parts (test_lint invariant)

            wires_labels_ncs.open("(wire")
            wires_labels_ncs.open("(pts")
            wires_labels_ncs.line(f"(xy {px:g} {py:g}) (xy {sx_:g} {sy_:g})")
            wires_labels_ncs.close()
            wires_labels_ncs.open("(stroke")
            wires_labels_ncs.line("(width 0)")
            wires_labels_ncs.line("(type default)")
            wires_labels_ncs.close()
            wires_labels_ncs.line(f'(uuid "{u()}")')
            wires_labels_ncs.close()

            wires_labels_ncs.open(f'(global_label "{net}"')
            wires_labels_ncs.line("(shape passive)")
            wires_labels_ncs.line(f"(at {sx_:g} {sy_:g} 0)")
            wires_labels_ncs.open("(effects")
            wires_labels_ncs.open("(font")
            wires_labels_ncs.line("(size 1.27 1.27)")
            wires_labels_ncs.close()
            wires_labels_ncs.close()
            wires_labels_ncs.line(f'(uuid "{u()}")')
            wires_labels_ncs.close()

    # --- power-flag pseudo-parts (ERC drivers for GND/VSYS/VBUS_NET/V5_JTRACE)
    flag_n = 0
    for kind, net, (fx, fy) in flag_origins:
        flag_n += 1
        ref = f"#PWR{flag_n:03d}"
        lib_id = f"power:{kind}"
        sx.open("(symbol")
        sx.line(f'(lib_id "{lib_id}")')
        sx.line(f"(at {fx:g} {fy:g} 0)")
        sx.line("(unit 1)")
        sx.line("(exclude_from_sim no)")
        sx.line("(in_bom yes)")
        sx.line("(on_board yes)")
        sx.line("(dnp no)")
        sym_uuid = u()
        sx.line(f'(uuid "{sym_uuid}")')
        prop(sx, "Reference", ref, fx, fy - 6.35, hide=True)
        prop(sx, "Value", kind, fx, fy - 3.81)
        prop(sx, "Footprint", "", fx, fy, hide=True)
        prop(sx, "Datasheet", "", fx, fy, hide=True)
        puid = u()
        sx.line('(pin "1"')
        sx.depth += 1
        sx.line(f'(uuid "{puid}")')
        sx.depth -= 1
        sx.line(")")
        sx.open("(instances")
        sx.open(f'(project "{PROJECT}"')
        sx.open(f'(path "/{root_uuid}"')
        sx.line(f'(reference "{ref}")')
        sx.line("(unit 1)")
        sx.close()
        sx.close()
        sx.close()
        sx.close()

        px, py = fx, fy
        sxp, syp = px, py + STUB
        wires_labels_ncs.open("(wire")
        wires_labels_ncs.open("(pts")
        wires_labels_ncs.line(f"(xy {px:g} {py:g}) (xy {sxp:g} {syp:g})")
        wires_labels_ncs.close()
        wires_labels_ncs.open("(stroke")
        wires_labels_ncs.line("(width 0)")
        wires_labels_ncs.line("(type default)")
        wires_labels_ncs.close()
        wires_labels_ncs.line(f'(uuid "{u()}")')
        wires_labels_ncs.close()

        wires_labels_ncs.open(f'(global_label "{net}"')
        wires_labels_ncs.line("(shape passive)")
        wires_labels_ncs.line(f"(at {sxp:g} {syp:g} 90)")
        wires_labels_ncs.open("(effects")
        wires_labels_ncs.open("(font")
        wires_labels_ncs.line("(size 1.27 1.27)")
        wires_labels_ncs.close()
        wires_labels_ncs.close()
        wires_labels_ncs.line(f'(uuid "{u()}")')
        wires_labels_ncs.close()

    for ln in wires_labels_ncs.lines:
        sx.lines.append(ln)

    sx.open("(sheet_instances")
    sx.open('(path "/"')
    sx.line('(page "1")')
    sx.close()
    sx.close()
    sx.line("(embedded_fonts no)")
    sx.close()  # (kicad_sch

    with open(OUT_PATH, "w") as f:
        f.write(sx.text())
    print(f"wrote {OUT_PATH}: {len(non_dnp)} parts, {flag_n} power flags")

    write_gen_symbol_lib()
    ensure_gen_lib_table_entry()


GEN_SYM_PATH = "sym/gen.kicad_sym"
SYM_LIB_TABLE_PATH = "sym-lib-table"


def write_gen_symbol_lib() -> None:
    """Standalone sym/gen.kicad_sym holding the generic per-pin-count symbols,
    so the project's sym-lib-table can resolve the "gen" library instead of
    relying solely on the schematic's embedded lib_symbols cache (avoids the
    ERC "configuration does not include library" warning)."""
    gx = Sx()
    gx.open("(kicad_symbol_lib")
    gx.line("(version 20241209)")
    gx.line('(generator "hw/gen_sch.py")')
    gx.line('(generator_version "9.0")')
    for n in GENERIC_COUNTS:
        emit_generic_symbol(gx, n, name=f"GEN{n}")
    gx.close()
    with open(GEN_SYM_PATH, "w") as f:
        f.write(gx.text())
    print(f"wrote {GEN_SYM_PATH}: {len(GENERIC_COUNTS)} generic symbols")


def ensure_gen_lib_table_entry() -> None:
    with open(SYM_LIB_TABLE_PATH) as f:
        table = f.read()
    if '(name "gen")' in table:
        return
    entry = '  (lib (name "gen")(type "KiCad")(uri "${KIPRJMOD}/sym/gen.kicad_sym")(options "")(descr ""))\n'
    table = table.rstrip("\n")
    assert table.endswith(")")
    table = table[:-1].rstrip("\n") + "\n" + entry + ")\n"
    with open(SYM_LIB_TABLE_PATH, "w") as f:
        f.write(table)
    print(f"updated {SYM_LIB_TABLE_PATH}: added 'gen' library")


if __name__ == "__main__":
    main()
