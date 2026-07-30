# hw/checks.py
import os
import sys

# Allow `python3 hw/checks.py ...` (the Task-9 brief's documented invocation)
# to find the `hw` package even though plain `python3 <script>` only puts the
# script's own directory (hw/), not the repo root, on sys.path. `-m pytest`
# and `import hw.checks` already work without this (pytest and Python's own
# package machinery insert the repo root themselves).
if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hw.netlist import PARTS
from hw.fp_lib import FP


def test_parts():
    need = {"PICO","J1B","J2B","J3","J5","J6","J7","J8","J9","J10","J_UART","J_STEMMA",
            "JP1","JP2","JP3","JP4","SW1","U_HSW","U_ISNS","TP1","TP2","TP3"}
    assert need <= set(PARTS), f"missing refs: {need - set(PARTS)}"
    assert len(PARTS["PICO"].pins) == 40
    for ref,p in PARTS.items():
        assert p.fp_class in FP, f"{ref}: unknown fp_class {p.fp_class}"


def test_power_nets():
    # NOTE: the brief's snippet used ("U_HSW","VOUT"); Task 3's committed
    # TPS2051B padmap names that logical pin "OUT" (see netlist.py padmap
    # comment) -- adjusted here to match the committed model, same intent.
    from hw.netlist import net_pins, PARTS
    assert net_pins("V5_JTRACE") >= {("J3","11"),("J3","13"),("JP1","1")}
    assert ("J5","VBUS") in net_pins("HOST_VBUS") and ("U_HSW","OUT") in net_pins("HOST_VBUS")
    assert ("PICO","40") in net_pins("VBUS_NET")
    for pad in ("35","37"):                       # no orphan power pins (G-2)
        assert PARTS["PICO"].pins[pad] is not None, f"PICO pin {pad} unassigned"


def test_trace_nets():
    from hw.netlist import net_pins, series_between
    for gp,td,rt,pin in [("GP1","TRACECLK","Rt1","12"),("GP2","TD0","Rt2","14"),
                         ("GP3","TD1","Rt3","16"),("GP4","TD2","Rt4","18"),("GP5","TD3","Rt5","20")]:
        assert series_between(gp, td, rt), f"{rt} not in series {gp}->{td}"
        assert ("J3",pin) in net_pins(td)
    for probe in ("SWDIO","SWCLK"):
        refs = {r for r,_ in net_pins(probe)}
        assert {"J3","J6","J7","J10"} <= refs, f"{probe} not on all debug conns: {refs}"
    assert ("SW1","1") in net_pins("NRESET")


def test_usb_nets():
    # NOTE: two adjustments to the brief's snippet (authorized, see task-6
    # report): (a) the committed U_HSW Part uses logical pin name "FLG" for
    # the fault/flag pin (not "OC" -- "OC" only appears in a datasheet-pin
    # comment); (b) the TP1 line is simplified to a plain membership assert.
    from hw.netlist import net_pins, series_between, divider_ratio, _PICO_GPIO_PAD
    assert divider_ratio("VBUS_NET","NATIVE_VBUS_DET") == (8200,8200)   # via JP4
    assert divider_ratio("J9_VBUS","DEV_VBUS_DET") == (8200,8200)
    assert series_between("GP20","HOST_DP")                              # 22R series (any R)
    assert ("U_HSW","EN") in net_pins("HOST_VBUS_EN") and ("U_HSW","FLG") in net_pins("HOST_VBUS_FLT")
    assert ("TP1","1") in net_pins("HOST_DP")   # probe point present
    # Review fix: Q_DPU (NMOS gated from the DEV_VBUS_DET divider midpoint)
    # was electrically unworkable as a pass-switch -- replaced by a firmware
    # soft-connect on GP11 (drive high = attach, Hi-Z = detach); the gate
    # decision now lives in firmware reading DEV_VBUS_DET (GP27), not in the
    # netlist. Pad for GP11 is derived from the model's own GPIO<->pad map,
    # not hand-counted.
    assert series_between("DEV_DP","DEV_DP_PU_EN","R_DPU")
    gp11_pad = next(pad for pad, gpio in _PICO_GPIO_PAD.items() if gpio == 11)
    assert ("PICO", gp11_pad) in net_pins("DEV_DP_PU_EN")


def test_pinmap():
    from hw.netlist import PARTS, PINMAP
    expect = {0:"GUARD",1:"TRACECLK",2:"TD0",3:"TD1",4:"TD2",5:"TD3",6:"GUARD",
              8:"I2C0_SDA",9:"I2C0_SCL",10:"LED_USER",12:"UART0_TX",13:"UART0_RX",
              14:"BTN_USER",15:"HOST_VBUS_FLT",16:"NATIVE_VBUS_DET",17:"HOST_VBUS_EN",
              18:"DEV_DP",19:"DEV_DM",20:"HOST_DP",21:"HOST_DM",26:"ISENSE",27:"DEV_VBUS_DET"}
    for gp,fn in expect.items():
        assert PINMAP[gp]==fn, f"GP{gp}: {PINMAP.get(gp)} != {fn}"
    # Electrical distinctness lock (review fix): both PINMAP labels are
    # "GUARD", but GP0's and GP6's guard jumpers are independent nodes -- the
    # underlying nets must never collapse to the same string.
    assert PARTS["PICO"].pins["1"] != PARTS["PICO"].pins["9"]


def test_lint():
    from hw.netlist import PARTS, NETS
    for name, pins in NETS.items():
        assert len(pins) >= 2, f"net {name} has {len(pins)} pin(s)"
    for ref, p in PARTS.items():
        for pad, net in p.pins.items():
            assert net is not None or pad in p.nc, f"{ref}.{pad} unconnected (not in nc)"


def test_breakout():
    # NOTE (controller ruling, corrects the brief): the brief's snippet
    # (`J1B.pins.get(n) or J2B.pins.get(n)` over "1".."40") can't work -- J1B
    # and J2B pads are each only keyed "1".."20" (breakout pad convention:
    # J1B pad n <-> PICO physical pin n for n in 1..20; J2B pad n <-> PICO
    # physical pin n+20, i.e. pad = physical - 20 for pins 21-40). Rewritten
    # to encode that convention directly instead of a lookup that always
    # misses for pins 21-40.
    from hw.netlist import PARTS
    pico = PARTS["PICO"].pins
    for n in range(1, 21):
        assert PARTS["J1B"].pins[str(n)] == pico[str(n)] is not None, \
            f"breakout J1B pad {n} not tied to PICO pin {n}"
    for n in range(21, 41):
        assert PARTS["J2B"].pins[str(n - 20)] == pico[str(n)] is not None, \
            f"breakout J2B pad {n - 20} not tied to PICO pin {n}"


# --------------------------------------------------------------------------
# Task 9: --compare-netlists -- authoritative schematic <-> reference-netlist
# cross-check. A tiny S-expression reader (not a regex scrape) so it doesn't
# care whether tokens are quoted -- our own hw.netlist.emit_netlist() writes
# bare atoms (e.g. `(ref J5)`), while `kicad-cli sch export netlist` quotes
# everything (`(ref "J5")`) and adds extra per-node fields like `(pintype
# ...)`; both parse to the same tree shape either way.
# --------------------------------------------------------------------------

def _tokenize(text: str) -> list[str]:
    tokens = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c.isspace():
            i += 1
        elif c in "()":
            tokens.append(c)
            i += 1
        elif c == '"':
            j = i + 1
            while j < n and text[j] != '"':
                j += 1
            tokens.append(text[i : j + 1])
            i = j + 1
        else:
            j = i
            while j < n and not text[j].isspace() and text[j] not in "()":
                j += 1
            tokens.append(text[i:j])
            i = j
    return tokens


def _parse_sexpr(tokens: list[str]):
    """tokens -> nested list tree; consumes a single balanced form starting
    at tokens[0] == '('."""
    it = iter(tokens)

    def read(tok):
        if tok == "(":
            items = []
            while True:
                t = next(it)
                if t == ")":
                    return items
                items.append(read(t))
        return tok.strip('"')

    return read(next(it))


def _find(tree, tag: str):
    """Yield every list node `tree` contains (recursively) whose first
    element equals `tag` (e.g. all `(net ...)` or `(node ...)` forms)."""
    if isinstance(tree, list):
        if tree and tree[0] == tag:
            yield tree
        for child in tree:
            yield from _find(child, tag)


def _field(node_list, tag: str):
    """First `(tag value ...)` sub-form's value, under a parsed list node."""
    for item in node_list:
        if isinstance(item, list) and item and item[0] == tag:
            return item[1]
    return None


def parse_netlist(path: str) -> dict[str, frozenset]:
    """KiCad E-format netlist -> {net_name: frozenset((ref, pin))}.

    Pseudo-components (refs starting with "#", e.g. `#PWR001` power-flag
    symbols) are stripped, and any net left with fewer than 2 real nodes is
    dropped -- that's exactly `kicad-cli sch export netlist`'s synthetic
    `unconnected-(...)` single-node nets for `no_connect`-flagged pins, which
    `emit_netlist()` never emits in the first place (see hw/netlist.py:
    every real net has >=2 pins, per test_lint).
    """
    text = open(path).read()
    tree = _parse_sexpr(_tokenize(text))
    nets = {}
    for net in _find(tree, "net"):
        name = _field(net, "name")
        nodes = set()
        for node in _find(net, "node"):
            ref = _field(node, "ref")
            pin = _field(node, "pin")
            if ref.startswith("#"):
                continue
            nodes.add((ref, pin))
        if len(nodes) < 2:
            continue
        nets[name] = frozenset(nodes)
    return nets


def compare_netlists(path_a: str, path_b: str) -> bool:
    nets_a = parse_netlist(path_a)
    nets_b = parse_netlist(path_b)

    parts_a = set(nets_a.values())
    parts_b = set(nets_b.values())

    if parts_a == parts_b:
        print("netlists match")
        return True

    only_a = parts_a - parts_b
    only_b = parts_b - parts_a

    def name_for(nets, part):
        for name, p in nets.items():
            if p == part:
                return name
        return "?"

    print("netlists DO NOT match")
    if only_a:
        print(f"-- partitions only in {path_a}:")
        for part in sorted(only_a, key=lambda p: name_for(nets_a, p)):
            print(f"   {name_for(nets_a, part)}: {sorted(part)}")
    if only_b:
        print(f"-- partitions only in {path_b}:")
        for part in sorted(only_b, key=lambda p: name_for(nets_b, p)):
            print(f"   {name_for(nets_b, part)}: {sorted(part)}")

    # Informational: same node-set, different net name (not a match failure).
    common = parts_a & parts_b
    for part in sorted(common, key=lambda p: name_for(nets_a, p)):
        na, nb = name_for(nets_a, part), name_for(nets_b, part)
        if na != nb:
            print(f"-- net name differs for identical nodes: {na!r} (in {path_a}) vs {nb!r} (in {path_b})")

    return False


if __name__ == "__main__":
    import argparse
    import sys

    ap = argparse.ArgumentParser()
    ap.add_argument("--compare-netlists", nargs=2, metavar=("A", "B"))
    args = ap.parse_args()

    if args.compare_netlists:
        ok = compare_netlists(*args.compare_netlists)
        sys.exit(0 if ok else 1)
    ap.print_help()
