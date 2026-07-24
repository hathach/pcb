# hw/checks.py
from hw.netlist import PARTS
from hw.fp_lib import FP


def test_parts():
    need = {"PICO","J1B","J2B","J3","J4","J5","J6","J7","J8","J9","J_UART","J_STEMMA",
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
        assert {"J3","J4","J6","J7"} <= refs, f"{probe} not on all debug conns: {refs}"
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
