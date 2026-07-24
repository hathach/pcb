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
