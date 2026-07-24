# hw/checks.py
from hw.netlist import PARTS
from hw.fp_lib import FP


def test_parts():
    need = {"PICO","J1B","J2B","J3","J4","J5","J6","J7","J8","J9","J_UART","J_STEMMA",
            "JP1","JP2","JP3","JP4","SW1","U_HSW","Q_DPU","U_ISNS","TP1","TP2","TP3"}
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
