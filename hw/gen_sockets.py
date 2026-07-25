#!/usr/bin/env python3
"""Generate the custom Pico carrier footprint (Task 14d-fix, blind-bottom SMT).

pico2_trace:PicoSocket_2x20_SMD -- blind-bottom SMT female socket carrier for
    the Pico: 40 numbered SMD pads ("1".."40", matching the stock
    RaspberryPi_Pico_Common_THT pin numbering exactly -- the netlist/
    schematic/routing model keys off these numbers) offset laterally outward
    from each nominal pin position. NO through-holes of any kind: this is a
    blind-bottom socket (the Pico's male header pins bottom out INSIDE the
    socket body, never reaching the board), unlike Task 14d's
    PicoSocket_2x20_SMD_ThruHole, which drilled an NPTH clearance hole under
    every pin so a THT-style pin could pass through the board.

    J1B/J2B (breakout rows) no longer need a custom footprint at all -- they
    now point straight at the stock KiCad
    "PinSocket_1x20_P2.54mm_Vertical_SMD_Pin1Left" footprint (see
    hw/fp_lib.py); zero custom geometry there, zero land-pattern risk. This
    generator only produces the Pico carrier.

Per-pin geometry is NOT invented: pad size/shape/layers and the pad-center
offset from the nominal pin position are parsed verbatim from that same
stock breakout footprint (a real, fab-proven blind SMT-socket land pattern)
and replicated at the Pico's own pin grid:
  - Module.pretty/RaspberryPi_Pico_Common_THT.kicad_mod (pin grid, pads
    "1".."40")
  - Connector_PinSocket_2.54mm.pretty/PinSocket_1x20_P2.54mm_Vertical_SMD_Pin1Left.kicad_mod
    (pad size/shape/layers + offset-from-nominal-pin magnitude)
  - Connector_PinSocket_2.54mm.pretty/PinSocket_1x20_P2.54mm_Vertical.kicad_mod
    (the THT sibling of the SMD file above, used only to confirm the SMD
    pads' "nominal pin position" is x=0 in that footprint's local frame)

Geometry decisions (full writeup: .superpowers/sdd/task-14d-fix-report.md):
  - SMD pad: parsed verbatim from the stock breakout footprint -- rect,
    1.9 x 1.0mm (1.9mm = radial/outward width, 1.0mm = length along the
    pitch direction), F.Cu+F.Mask+F.Paste, pad center offset 1.65mm outward
    (away from the module's own centreline) from the nominal pin position --
    same numbers the stock part uses, just applied uniformly outward on both
    Pico rows instead of that part's own left/right zigzag stagger.
  - No NPTH/thru_hole pads anywhere -- blind-bottom socket, nothing needs to
    pass through the board.
  - F.SilkS: a body-outline rectangle per row (inner edge at the row's
    nominal pin line, outer edge just past the pad's outward copper edge),
    a pin-1 dot, and a "USB END" text marker so orientation is unambiguous
    without the pads themselves carrying a shape cue. The row rectangle's
    Y-extent is derived from the pad's own half-length + a fixed silk-to-
    copper clearance (fixes the Task 14d defect where a hardcoded Y-inset
    was smaller than the pad's half-length, so the silk line crossed pad
    copper -- DRC "silk_over_copper").
  - F.CrtYd: one rectangle per physical strip (2, one per row), covering the
    pad envelope with a 0.3mm margin plus a half-pitch (1.27mm) overhang at
    each end -- matches the stock THT footprints' own courtyard-overhang
    convention (unchanged from Task 14d).

Run: python3 hw/gen_sockets.py   (writes into pico2_trace.pretty/; safe to
re-run -- always regenerates the file from scratch, no in-place editing).
"""
import os
import re

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(REPO, "pico2_trace.pretty")

PICO_SRC = "/usr/share/kicad/footprints/Module.pretty/RaspberryPi_Pico_Common_THT.kicad_mod"
_SMD_DIR = "/usr/share/kicad/footprints/Connector_PinSocket_2.54mm.pretty"
SMD_PAD_SRC = f"{_SMD_DIR}/PinSocket_1x20_P2.54mm_Vertical_SMD_Pin1Left.kicad_mod"
THT_NOMINAL_SRC = f"{_SMD_DIR}/PinSocket_1x20_P2.54mm_Vertical.kicad_mod"

CRTYD_MARGIN_MM = 0.3
CRTYD_OVERHANG_MM = 1.27   # half pitch; matches stock THT courtyard convention
SILK_CLEARANCE_MM = 0.15   # silk kept this far clear of pad copper

_PICO_PAD_RE = re.compile(r'\(pad "(\d+)" thru_hole \w+\s*\n\s*\(at (-?[\d.]+) (-?[\d.]+)\)')
_THT_NOMINAL_RE = re.compile(r'\(pad "1" thru_hole \w+\s*\n\s*\(at (-?[\d.]+) (-?[\d.]+)\)')
_SMD_PAD_RE = re.compile(
    r'\(pad "(\d+)" smd (\w+)\s*\n'
    r'\s*\(at (-?[\d.]+) (-?[\d.]+)\)\s*\n'
    r'\s*\(size ([\d.]+) ([\d.]+)\)\s*\n'
    r'\s*\(layers ((?:"[^"]+"\s*)+)\)'
)


def _parse_pico_pad_positions(path: str) -> dict[str, tuple[float, float]]:
    """{pad_number: (x, y)} for every plated thru_hole pad in the stock Pico
    footprint -- the pin-grid source of truth, unchanged from Task 14d."""
    text = open(path).read()
    positions = {}
    for num, x, y in _PICO_PAD_RE.findall(text):
        positions[num] = (float(x), float(y))
    assert positions, f"no thru_hole pads parsed from {path}"
    return positions


def _parse_smd_pad_geometry() -> tuple[str, float, float, tuple[str, ...], float]:
    """(shape, size_x, size_y, layers, offset_mm) parsed verbatim from the
    stock breakout SMD footprint -- every one of its 20 pads must agree
    (single shape/size/layer-set, single |offset| magnitude from the
    nominal pin position) or this is not the uniform land pattern the
    docstring claims it is."""
    text = open(SMD_PAD_SRC).read()
    matches = _SMD_PAD_RE.findall(text)
    assert len(matches) == 20, f"expected 20 SMD pads in {SMD_PAD_SRC}, got {len(matches)}"

    nominal_x, _nominal_y = re.search(_THT_NOMINAL_RE, open(THT_NOMINAL_SRC).read()).groups()
    nominal_x = float(nominal_x)

    shapes = {m[1] for m in matches}
    sizes = {(m[4], m[5]) for m in matches}
    layer_sets = {m[6].strip() for m in matches}
    offsets = {round(abs(float(m[2]) - nominal_x), 6) for m in matches}
    assert len(shapes) == 1, f"non-uniform pad shape: {shapes}"
    assert len(sizes) == 1, f"non-uniform pad size: {sizes}"
    assert len(layer_sets) == 1, f"non-uniform pad layers: {layer_sets}"
    assert len(offsets) == 1, f"non-uniform pad offset: {offsets}"

    shape = shapes.pop()
    size_x, size_y = (float(v) for v in sizes.pop())
    layers = tuple(re.findall(r'"([^"]+)"', layer_sets.pop()))
    offset_mm = offsets.pop()
    return shape, size_x, size_y, layers, offset_mm


def _fmt(v: float) -> str:
    """Trim to KiCad's usual float style: no trailing .0, no float noise."""
    s = f"{v:.6f}".rstrip("0").rstrip(".")
    return s if s else "0"


def _smd_pad(num: str, x: float, y: float, outward_sign: float,
             shape: str, size_x: float, size_y: float, layers: tuple[str, ...],
             offset_mm: float) -> str:
    pad_cx = x + outward_sign * offset_mm
    layer_list = " ".join(f'"{l}"' for l in layers)
    return (
        f'\t(pad "{num}" smd {shape}\n'
        f"\t\t(at {_fmt(pad_cx)} {_fmt(y)})\n"
        f"\t\t(size {_fmt(size_x)} {_fmt(size_y)})\n"
        f"\t\t(layers {layer_list})\n"
        f"\t)\n"
    )


def _silk_rect(x0: float, y0: float, x1: float, y1: float) -> str:
    pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
    lines = []
    for (ax, ay), (bx, by) in zip(pts, pts[1:]):
        lines.append(
            "\t(fp_line\n"
            f"\t\t(start {_fmt(ax)} {_fmt(ay)})\n"
            f"\t\t(end {_fmt(bx)} {_fmt(by)})\n"
            "\t\t(stroke\n\t\t\t(width 0.12)\n\t\t\t(type solid)\n\t\t)\n"
            '\t\t(layer "F.SilkS")\n'
            "\t)\n"
        )
    return "".join(lines)


def _crtyd_rect(x0: float, y0: float, x1: float, y1: float) -> str:
    pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
    lines = []
    for (ax, ay), (bx, by) in zip(pts, pts[1:]):
        lines.append(
            "\t(fp_line\n"
            f"\t\t(start {_fmt(ax)} {_fmt(ay)})\n"
            f"\t\t(end {_fmt(bx)} {_fmt(by)})\n"
            "\t\t(stroke\n\t\t\t(width 0.05)\n\t\t\t(type solid)\n\t\t)\n"
            '\t\t(layer "F.CrtYd")\n'
            "\t)\n"
        )
    return "".join(lines)


def _pin1_dot(x: float, y: float, outward_sign: float, offset_mm: float, size_x: float) -> str:
    """Small filled silk dot beyond pin 1's pad -- same visual role as the
    stock Pico/FTSH footprints' own pin-1 marks."""
    cx = x + outward_sign * (offset_mm + size_x / 2 + 0.4)
    return (
        "\t(fp_circle\n"
        f"\t\t(center {_fmt(cx)} {_fmt(y)})\n"
        f"\t\t(end {_fmt(cx + 0.25)} {_fmt(y)})\n"
        "\t\t(stroke\n\t\t\t(width 0.12)\n\t\t\t(type solid)\n\t\t)\n"
        "\t\t(fill solid)\n"
        '\t\t(layer "F.SilkS")\n'
        "\t)\n"
    )


def _property(name: str, value: str, x: float, y: float, layer: str) -> str:
    return (
        f'\t(property "{name}" "{value}"\n'
        f"\t\t(at {_fmt(x)} {_fmt(y)} 0)\n"
        f'\t\t(layer "{layer}")\n'
        "\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 1 1)\n\t\t\t\t(thickness 0.15)\n\t\t\t)\n\t\t)\n"
        "\t)\n"
    )


def gen_pico_socket() -> str:
    pins = _parse_pico_pad_positions(PICO_SRC)
    shape, size_x, size_y, layers, offset_mm = _parse_smd_pad_geometry()

    row1 = sorted(int(n) for n in pins if pins[n][0] == min(x for x, _ in pins.values()))
    row2 = sorted(int(n) for n in pins if pins[n][0] == max(x for x, _ in pins.values()))
    x_left = min(x for x, _ in pins.values())
    x_right = max(x for x, _ in pins.values())
    y_lo = min(y for _, y in pins.values())
    y_hi = max(y for _, y in pins.values())
    cx = (x_left + x_right) / 2

    body = ['(footprint "PicoSocket_2x20_SMD"\n']
    body.append("\t(version 20241229)\n")
    body.append('\t(generator "pico2_trace/hw/gen_sockets.py")\n')
    body.append('\t(layer "F.Cu")\n')
    body.append(
        '\t(descr "Blind-bottom SMT female socket carrier for a Raspberry Pi Pico 2 (two 1x20 '
        '2.54mm SMD socket strips, pins bottom out inside the socket -- NO through-holes), pad '
        'numbering \\\"1\\\"..\\\"40\\\" matches stock RaspberryPi_Pico_Common_THT physical pin '
        'numbers. Pin grid from RaspberryPi_Pico_Common_THT.kicad_mod; pad size/shape/layers and '
        'outward offset from the nominal pin position reused verbatim from stock '
        'PinSocket_1x20_P2.54mm_Vertical_SMD_Pin1Left.kicad_mod.")\n'
    )
    body.append('\t(tags "Raspberry Pi Pico 2 SMD socket carrier blind bottom no through holes")\n')
    body.append(_property("Reference", "REF**", cx, y_lo - 4.6, "F.SilkS"))
    body.append(_property("Value", "PicoSocket_2x20_SMD", cx, y_hi + 3.3, "F.Fab"))
    body.append("\t(attr smd)\n")

    # Body-outline silk per row: inner edge at the row's nominal pin line,
    # outer edge just past the pad's outward copper edge, Y-extent derived
    # from the pad's own half-length + SILK_CLEARANCE_MM (never smaller than
    # the pad, unlike Task 14d's hardcoded inset -- that's the silk-over-
    # copper fix). Plus pin-1 dot and a "USB END" text marker (pins "1"/"40"
    # sit at y_lo -- the near-USB end, per build_board.py's own verified
    # Pico orientation finding).
    silk_y0 = y_lo - (size_y / 2 + SILK_CLEARANCE_MM)
    silk_y1 = y_hi + (size_y / 2 + SILK_CLEARANCE_MM)
    for row_x in (x_left, x_right):
        sign = -1.0 if row_x == x_left else 1.0
        outer = row_x + sign * (offset_mm + size_x / 2 + SILK_CLEARANCE_MM)
        x0, x1 = (outer, row_x) if sign < 0 else (row_x, outer)
        body.append(_silk_rect(x0, silk_y0, x1, silk_y1))

    body.append(_pin1_dot(x_left, y_lo, -1.0, offset_mm, size_x))
    body.append(
        '\t(fp_text user "USB END"\n'
        f"\t\t(at {_fmt(cx)} {_fmt(y_lo - 1.8)} 0)\n"
        '\t\t(layer "F.SilkS")\n'
        "\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 0.8 0.8)\n\t\t\t\t(thickness 0.12)\n\t\t\t)\n\t\t)\n"
        "\t)\n"
    )

    # Courtyard: one rectangle per physical socket strip.
    for row_x in (x_left, x_right):
        sign = -1.0 if row_x == x_left else 1.0
        pad_outer = row_x + sign * (offset_mm + size_x / 2)
        inner = row_x - sign * CRTYD_MARGIN_MM
        outer = pad_outer + sign * CRTYD_MARGIN_MM
        x0, x1 = (outer, inner) if sign < 0 else (inner, outer)
        body.append(_crtyd_rect(x0, y_lo - CRTYD_OVERHANG_MM, x1, y_hi + CRTYD_OVERHANG_MM))

    # Pads: SMD only (numbered, carries the net), no holes of any kind --
    # numbers taken verbatim from the source THT footprint.
    for num in [str(n) for n in row1] + [str(n) for n in row2]:
        x, y = pins[num]
        sign = -1.0 if x == x_left else 1.0
        body.append(_smd_pad(num, x, y, sign, shape, size_x, size_y, layers, offset_mm))

    body.append("\t(embedded_fonts no)\n")
    body.append(")\n")
    return "".join(body)


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "PicoSocket_2x20_SMD.kicad_mod"), "w") as f:
        f.write(gen_pico_socket())
    print("wrote PicoSocket_2x20_SMD.kicad_mod")


if __name__ == "__main__":
    main()
