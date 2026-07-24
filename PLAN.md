# Pico 2 Trace Motherboard — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a manufacturable KiCad 9 project (schematic + 2-layer PCB, DRC-clean, with gerbers/BOM/bring-up note) for the Pico 2 SWD+ETM trace motherboard specified in `DESIGN.md`.

**Architecture:** Connectivity is authored **once** as a Python single-source-of-truth (`hw/netlist.py`: a parts table + a nets table transcribed from `DESIGN.md`). That model (a) drives `pcbnew` scripting to instantiate footprints, nets, board outline, stackup, net classes, placement, the SI-critical routing, and the ground pour, and (b) emits a KiCad `.net` netlist used for ERC/BOM cross-checks and to draw the schematic. Verification is by `kicad-cli sch erc`, `kicad-cli pcb drc`, and Python assertions over the model/board. The visual schematic is drawn in eeschema from the netlist + the Adafruit reference schematics (KiCad imports Eagle `.lbr`/`.sch` via the GUI); Task 1 first attempts to automate schematic generation in a venv, and if that yields a KiCad-9-clean schematic it supersedes the manual draw.

**Tech Stack:** KiCad 9.0.2 (`kicad-cli`, `pcbnew` Python API), Python 3, KiCad stock symbol/footprint libraries, Adafruit `MBAdafruitBoards` Eagle libraries (reference), a project venv for optional schematic automation.

## Global Constraints

- **2 layers max**, FR4 1.6 mm. Bottom copper = continuous GND pour under the whole trace group.
- Target modules: **Pico 2 (RP2350A) and original Pico (RP2040)** — nothing may exceed RP2040 limits (e.g. no bare 5 V on a GPIO; VBUS-sense uses an 8.2 k/8.2 k divider).
- **Trace nets (GP1–GP5):** 27 Ω source series at the socket pins, runs < 30 mm, CLK↔data length-matched within a few mm, no other loading; MIPI-20 within ~3 cm of the socket. GP0/GP6 are GND-guard pins (removable jumpers).
- Pin map, connector list, and net topology are **exactly** as in `DESIGN.md` §4–§10 — that document is authoritative; this plan implements it.
- Every table written into any doc is column-aligned (`tools/align_md_tables.py`).
- Deliverables land in `~/code/jtrace/pico2_trace_motherboard/`; final schematic PDF + bring-up note also archived to the calibre library.

## File structure

| Path                        | Responsibility                                                            |
| --------------------------- | ------------------------------------------------------------------------- |
| `pico2_trace.kicad_pro`     | KiCad project file                                                        |
| `pico2_trace.kicad_sch`     | Schematic (root + hierarchical sheets)                                    |
| `pico2_trace.kicad_pcb`     | Board                                                                     |
| `pico2_trace.pretty/`       | Local footprint library (custom + copied-stock footprints)                |
| `sym/pico2_trace.kicad_sym` | Local symbol library (custom symbols: Pico module, connectors)            |
| `hw/netlist.py`             | Single source of truth: `PARTS` + `NETS`; emits `.net`; importable model  |
| `hw/build_board.py`         | `pcbnew` driver: footprints, nets, stackup, classes, outline, placement   |
| `hw/route_trace.py`         | `pcbnew` driver: SI-critical routing (trace bundle, guards, power) + pour |
| `hw/checks.py`              | Python assertions over `netlist.py` / the built board                     |
| `hw/fp_lib.py`              | Footprint resolution table (ref → library:footprint)                      |
| `tools/align_md_tables.py`  | (exists) markdown table aligner                                           |
| `docs/BOM.csv`              | Bill of materials (generated)                                             |
| `docs/BRINGUP.md`           | One-page bring-up note                                                    |
| `fab/`                      | Generated gerbers, drill, position files, 3D render                       |

---

### Task 1: Project scaffold, toolchain verification, schematic-automation spike

**Files:**
- Create: `pico2_trace.kicad_pro`, `pico2_trace.kicad_pcb` (empty board), `sym-lib-table`, `fp-lib-table`
- Create: `hw/spike_sch.py` (throwaway), `.venv/` (gitignored)
- Modify: `.gitignore` (add `.venv/`, `fab/`)

**Interfaces:**
- Produces: a valid empty KiCad project that `kicad-cli` accepts; a recorded decision `SCHEMATIC_MODE ∈ {auto, gui}` written to `docs/BRINGUP.md` (Toolchain section).

- [ ] **Step 1: Create the empty project + board via pcbnew**

```bash
cd ~/code/jtrace/pico2_trace_motherboard
python3 - <<'PY'
import pcbnew
b = pcbnew.BOARD()
pcbnew.SaveBoard("pico2_trace.kicad_pcb", b)
print("board saved")
PY
printf '(kicad_project)\n' > /dev/null   # project file created next step
```

- [ ] **Step 2: Create a minimal project file and lib tables**

```bash
cat > pico2_trace.kicad_pro <<'EOF'
{ "board": {}, "meta": {"filename":"pico2_trace.kicad_pro","version":1}, "sheets": [], "libraries": {} }
EOF
printf '(fp_lib_table\n  (lib (name "pico2_trace")(type "KiCad")(uri "${KIPRJMOD}/pico2_trace.pretty")(options "")(descr ""))\n)\n' > fp-lib-table
printf '(sym_lib_table\n  (lib (name "pico2_trace")(type "KiCad")(uri "${KIPRJMOD}/sym/pico2_trace.kicad_sym")(options "")(descr ""))\n)\n' > sym-lib-table
mkdir -p pico2_trace.pretty sym hw fab docs
```

- [ ] **Step 3: Verify the board loads and DRC runs (baseline)**

Run: `kicad-cli pcb drc --exit-code-violations pico2_trace.kicad_pcb; echo "exit=$?"`
Expected: a DRC report prints, `exit=0` (empty board has no violations).

- [ ] **Step 4: Spike — can we auto-generate a KiCad-9 schematic in a venv?**

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -q skidl kinet 2>&1 | tail -2 || echo "PIP_FAILED"
python3 - <<'PY' 2>&1 | tail -5
try:
    import skidl; print("skidl", skidl.__version__)
    # minimal 2-part net → KiCad netlist
    from skidl import Part, Net, generate_netlist
    print("SKIDL_OK")
except Exception as e:
    print("SKIDL_UNAVAILABLE", e)
PY
deactivate
```

- [ ] **Step 5: Record the decision**

If Step 4 printed `SKIDL_OK` **and** a later smoke test (Task 9) confirms KiCad 9 opens the generated schematic, set `SCHEMATIC_MODE=auto`; otherwise `SCHEMATIC_MODE=gui`. Write the chosen mode + the pip/venv result into `docs/BRINGUP.md` under a `## Toolchain` heading.

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "scaffold: empty KiCad project, lib tables, toolchain spike result"
```

---

### Task 2: Local footprint & symbol libraries

**Files:**
- Create: `hw/fp_lib.py` (ref-class → `library:footprint` map)
- Create: custom footprints in `pico2_trace.pretty/` (see table)
- Create: `sym/pico2_trace.kicad_sym` (custom symbols: Pico module, MIPI-20, 2×5 Cortex, JST-SH, USB-A/micro-B, load switch, ESD, INA181)

**Interfaces:**
- Produces: `FP = {...}` in `hw/fp_lib.py` mapping every part class to a resolvable footprint; a symbol lib covering every custom part. Consumed by Tasks 3, 9, 10.

Footprint sourcing (KiCad stock unless noted; Adafruit `.lbr`/metro `.pretty` are references, imported via GUI only where stock is insufficient):

| Part                       | Footprint                                                            | Source                                                                                  |
| -------------------------- | -------------------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| Pico socket (inner+outer)  | `Module:RaspberryPi_Pico_Common_THT` (+ 2× `PinSocket_1x20_P2.54mm`) | stock                                                                                   |
| MIPI-20 (J3)               | `pico2_trace:FTSH-110-01-DV` (2×10 1.27 mm, keyed shroud)            | derive from stock `PinHeader_2x10_P1.27mm_Vertical_SMD`                                 |
| 2×5 Cortex (J6)            | `pico2_trace:FTSH-105-01-DV` (2×5 1.27 mm, keyed)                    | derive from stock `PinHeader_2x05_P1.27mm_Vertical_SMD` / metro `2X05_1.27MM_BOX_POSTS` |
| JST-SH 3-pin (J4, J7)      | `Connector_JST:JST_SH_SM03B-SRSS-TB_1x03-1MP_P1.00mm_Horizontal`     | stock                                                                                   |
| USB-A host (J5)            | `Connector_USB:USB_A_Molex_67643_Horizontal`                         | stock                                                                                   |
| micro-B (J8, J9)           | `Connector_USB:USB_Micro-B_Molex_47346-...`                          | stock                                                                                   |
| STEMMA-QT I2C              | `Connector_JST:JST_SH_SM04B-SRSS-TB_1x04-1MP_P1.00mm_Horizontal`     | stock (= Adafruit STEMMAQT); ref `stemmaqt_shift.sch`                                   |
| Load switch (host VBUS)    | `Package_TO_SOT_SMD:SOT-23-5`                                        | stock; ref `adafruit_power.lbr`                                                         |
| ESD array (USBLC6-2SC6)    | `Package_TO_SOT_SMD:SOT-23-6`                                        | stock                                                                                   |
| Current-sense amp (INA181) | `Package_TO_SOT_SMD:SOT-23-5`                                        | stock                                                                                   |
| Reset button SW1           | `Button_Switch_SMD:SW_SPST_...` (top-actuated 6 mm)                  | stock; ref `adafruit_electromech.lbr`                                                   |
| R/C 0402, LEDs 0603, shunt | stock `Resistor_SMD`, `LED_SMD`, `Capacitor_SMD`                     | stock                                                                                   |
| Jumpers JP1–JP4            | `Connector_PinHeader_2.54mm:PinHeader_1x0{2,3}_P2.54mm_Vertical`     | stock                                                                                   |

- [ ] **Step 1: Write `hw/fp_lib.py` with the resolution map** (one dict entry per row above, keyed by part class).
- [ ] **Step 2: Create the two custom shroud footprints** by copying the stock 1.27 mm SMD pin-header `.kicad_mod` into `pico2_trace.pretty/` and adding the keyed-shroud courtyard/silk + pin-1 marker (edit the s-expr; keep pad numbering 1–20 / 1–10).
- [ ] **Step 3: Verify every footprint resolves**

```bash
python3 - <<'PY'
import pcbnew, os
from hw.fp_lib import FP
for cls,(lib,fp) in FP.items():
    path = f"/usr/share/kicad/footprints/{lib}.pretty/{fp}.kicad_mod" if lib!="pico2_trace" else f"pico2_trace.pretty/{fp}.kicad_mod"
    assert os.path.exists(path) or lib=="Module", f"MISSING {cls}: {path}"
print("all footprints resolve")
PY
```
Expected: `all footprints resolve` (fix any MISSING by correcting the stock footprint name via `ls /usr/share/kicad/footprints/<lib>.pretty/`).

- [ ] **Step 4: Commit** — `git commit -am "lib: local footprint/symbol libraries + resolution map"`

---

### Task 3: Connectivity model — parts table

**Files:**
- Create: `hw/netlist.py` (start `PARTS`)
- Test: `hw/checks.py::test_parts`

**Interfaces:**
- Produces: `PARTS: dict[ref -> Part(ref, value, fp_class, pins:dict[padname->netname|None])]`. Consumed by all later tasks. Refs exactly match `DESIGN.md` §4/§6.

- [ ] **Step 1: Write `PARTS`** — one entry per component: the connectors J1,J1B,J2,J2B,J3–J9, JP1–JP4, SW1; the Pico socket; the load switch U(host), ESD arrays, INA181 U(sense), shunt; all R/C/LED; the trace series resistors Rt1–Rt5 (27 Ω); the VBUS-detect dividers; the D+ pull-up + gating FET. `fp_class` references keys from `hw/fp_lib.py`.
- [ ] **Step 2: Write the failing test**

```python
# hw/checks.py
from hw.netlist import PARTS
from hw.fp_lib import FP
def test_parts():
    need = {"J1","J1B","J2","J2B","J3","J4","J5","J6","J7","J8","J9",
            "JP1","JP2","JP3","JP4","SW1"}
    assert need <= set(PARTS), f"missing refs: {need - set(PARTS)}"
    for ref,p in PARTS.items():
        assert p.fp_class in FP, f"{ref}: unknown fp_class {p.fp_class}"
```

- [ ] **Step 3: Run it** — `python3 -m pytest hw/checks.py::test_parts -q` → Expected: FAIL (PARTS incomplete), then iterate `PARTS` until PASS.
- [ ] **Step 4: Commit** — `git commit -am "netlist: parts table"`

---

### Task 4: Connectivity model — power & ground nets

**Files:** Modify `hw/netlist.py` (`NETS` power section); `hw/checks.py::test_power_nets`

**Interfaces:** Produces named nets `GND, VBUS_NET, V5_JTRACE, VSYS, P3V3, HOST_VBUS`. `VBUS_NET` = Pico pin 40 = J8 VBUS = external inject; `HOST_VBUS` = load-switch output → J5 VBUS.

- [ ] **Step 1: Add the power nets** per `DESIGN.md` §7/§8.1: JP1 selects `VBUS_NET`↔`V5_JTRACE`; `VBUS_NET`→load-switch in, `HOST_VBUS`=switch out→J5 VBUS (+bulk C); MIPI-20 pins 11/13→`V5_JTRACE`; Pico pin 40→`VBUS_NET`, pin 39→`VSYS`, pin 36→`P3V3`; power LED on `VBUS_NET`; every GND pin (Pico 3/8/13/18/23/28/33/38; MIPI-20 3/5/9/15/17/19; all connector grounds)→`GND`.
- [ ] **Step 2: Failing test**

```python
def test_power_nets():
    from hw.netlist import PARTS, net_pins
    assert net_pins("V5_JTRACE") >= {("J3","11"),("J3","13"),("JP1","1")}
    assert ("J5","VBUS") in net_pins("HOST_VBUS")
    assert ("U_HSW","VOUT") in net_pins("HOST_VBUS")   # load switch out
    assert ("PICO","40") in net_pins("VBUS_NET")
```

- [ ] **Step 3:** run → fix until PASS. **Step 4:** commit `"netlist: power & ground nets"`.

---

### Task 5: Connectivity model — debug & trace nets

**Files:** Modify `hw/netlist.py`; `hw/checks.py::test_trace_nets`

**Interfaces:** Produces `SWDIO, SWCLK, NRESET, VTREF, TRACECLK, TD0..TD3` and the per-trace source-side nets `GP1..GP5` (socket side of Rt).

- [ ] **Step 1:** Wire per `DESIGN.md` §5: SWDIO/SWCLK from J4+J7 fan to J3-pin2/4 and J6-pin2/4; `NRESET`=Pico pin30→J3-pin10, J6-pin10, SW1→GND; `VTREF`=Pico pin36→J3-pin1, J6-pin1. Trace: Pico pin2=`GP1`→Rt1→`TRACECLK`→J3-pin12; pins4/5/6/7=`GP2..GP5`→Rt2..Rt5→`TD0..TD3`→J3-pin14/16/18/20. Guards: JP2 (GP0↔GND), JP3 (GP6↔GND).
- [ ] **Step 2: Failing test**

```python
def test_trace_nets():
    from hw.netlist import net_pins, series_between
    for gp,td,rt,pin in [("GP1","TRACECLK","Rt1","12"),("GP2","TD0","Rt2","14"),
                         ("GP3","TD1","Rt3","16"),("GP4","TD2","Rt4","18"),("GP5","TD3","Rt5","20")]:
        assert series_between(gp, td, rt), f"{rt} not in series {gp}->{td}"
        assert ("J3",pin) in net_pins(td)
    for probe in ("SWDIO","SWCLK"):
        refs = {ref for ref,_ in net_pins(probe)}
        assert {"J3","J4","J6","J7"} <= refs, f"{probe} not on all debug conns: {refs}"
    assert ("SW1","1") in net_pins("NRESET")
```

- [ ] **Step 3:** run → fix. **Step 4:** commit `"netlist: debug & trace nets"`.

---

### Task 6: Connectivity model — USB host, USB device, VBUS-detect taps

**Files:** Modify `hw/netlist.py`; `hw/checks.py::test_usb_nets`

**Interfaces:** Produces `HOST_DP,HOST_DM` (GP20/21), `DEV_DP,DEV_DM` (GP18/19), `NATIVE_VBUS_DET`(GP16), `DEV_VBUS_DET`(GP27), and their divider/pulldown/series/ESD parts.

- [ ] **Step 1:** Per `DESIGN.md` §8/§9: host J5 D+=GP20/D−=GP21 via 22 Ω series, 15 kΩ pulldowns, ESD; host VBUS from load switch (enable=GP17, fault=GP15). Device J9 D+=GP18/D−=GP19 via series, ESD, 1.5 kΩ D+ pull-up through gating FET controlled by `DEV_VBUS_DET`; J9 VBUS→8.2k/8.2k→GP27. Native tap: `VBUS_NET`→8.2k/8.2k→GP16 through JP4. Current-sense shunt in `HOST_VBUS`→INA181→GP26.
- [ ] **Step 2: Failing test**

```python
def test_usb_nets():
    from hw.netlist import net_pins, series_between, divider_ratio
    assert divider_ratio("VBUS_NET","GP16") == (8200,8200)       # native detect tap
    assert divider_ratio("J9_VBUS","GP27") == (8200,8200)        # device detect
    assert series_between("GP20","HOST_DP_CONN", any_R=True)     # 22R series
    assert ("R_PD_HDP","2") in net_pins("GND")                   # 15k pulldown to GND
    assert ("U_HSW","EN") in net_pins("GP17") and ("U_HSW","FLG") in net_pins("GP15")
```

- [ ] **Step 3:** run → fix. **Step 4:** commit `"netlist: USB host/device + VBUS-detect taps"`.

---

### Task 7: Connectivity model — peripherals + full pin-map assertion

**Files:** Modify `hw/netlist.py`; `hw/checks.py::test_pinmap`

**Interfaces:** Completes `NETS`. Produces the console/I2C/LED/button nets and a `PINMAP` derived from `PARTS["PICO"].pins`.

- [ ] **Step 1:** Per `DESIGN.md` §6/§10: UART0 GP12(TX)/GP13(RX)→J_UART; I2C0 GP8(SDA)/GP9(SCL)→STEMMA; user LED GP10→R→`GND`; power LED on `VBUS_NET`→R→`GND`; button SW... (SW1 is RUN); user button GP14→`GND`. Assert GP0/GP6=guards, GP1–5=trace, GP7/11/22/28=unused.
- [ ] **Step 2: Failing test** — assert the entire `DESIGN.md` §6 map exactly:

```python
def test_pinmap():
    from hw.netlist import PINMAP
    expect = {0:"GUARD",1:"TRACECLK",2:"TD0",3:"TD1",4:"TD2",5:"TD3",6:"GUARD",
              8:"I2C0_SDA",9:"I2C0_SCL",10:"LED_USER",12:"UART0_TX",13:"UART0_RX",
              14:"BTN_USER",15:"HOST_VBUS_FLT",16:"NATIVE_VBUS_DET",17:"HOST_VBUS_EN",
              18:"DEV_DP",19:"DEV_DM",20:"HOST_DP",21:"HOST_DM",26:"ISENSE",27:"DEV_VBUS_DET"}
    for gp,fn in expect.items():
        assert PINMAP[gp]==fn, f"GP{gp}: {PINMAP.get(gp)} != {fn}"
```

- [ ] **Step 3:** run → fix until the map matches `DESIGN.md` §6 exactly. **Step 4:** commit `"netlist: peripherals + pin-map lock"`.

---

### Task 8: Emit KiCad netlist + connectivity lint

**Files:** Modify `hw/netlist.py` (`emit_netlist()`); `hw/checks.py::test_lint`; output `pico2_trace.net`

**Interfaces:** Produces `pico2_trace.net` (KiCad netlist s-expr) consumed by Tasks 9 (schematic/BOM) and 10 (PCB build).

- [ ] **Step 1:** Implement `emit_netlist()` writing a KiCad `(export (version "E") (components…) (nets…))` file from `PARTS`/`NETS`.
- [ ] **Step 2: Failing test** — lint the model:

```python
def test_lint():
    from hw.netlist import PARTS, NETS, net_pins
    for name,pins in NETS.items():                      # no single-pin nets
        assert len(pins) >= 2, f"net {name} has {len(pins)} pin(s)"
    for ref,p in PARTS.items():                          # no floating pins (None) except documented NC
        nc = getattr(p,"nc",set())
        for pad,net in p.pins.items():
            assert net is not None or pad in nc, f"{ref}.{pad} unconnected"
```

- [ ] **Step 3:** run → fix (mark true NC pins: MIPI-20 6/7/8, J8 D+/D−). **Step 4:**

```bash
python3 -c "import hw.netlist as n; n.emit_netlist('pico2_trace.net'); print('netlist written')"
```
Expected: `netlist written`; `grep -c '(net ' pico2_trace.net` > 30. **Step 5:** commit `"netlist: emit KiCad .net + connectivity lint"`.

---

### Task 9: Schematic (ERC-clean)

**Files:** Create `pico2_trace.kicad_sch` (+ hierarchical sheets `power/`, `debug_trace/`, `usb/`, `periph/`)

**Interfaces:** Consumes `pico2_trace.net` + `PARTS`/`NETS`. Produces an ERC-clean schematic and the schematic PDF.

- [ ] **Step 1 (SCHEMATIC_MODE=auto):** run the venv generator to emit `.kicad_sch` from the model; open-test with `kicad-cli sch export netlist` and confirm the exported netlist matches `pico2_trace.net` (same nets/pins). If it fails to open or mismatches → set `SCHEMATIC_MODE=gui` and continue at Step 2.
- [ ] **Step 1 (SCHEMATIC_MODE=gui):** In eeschema draw four hierarchical sheets, one per net group (Tasks 4–7), using the symbols from `sym/pico2_trace.kicad_sym` + KiCad stock, following the Adafruit reference schematics for sub-circuits: `stemmaqt_shift.sch` (STEMMA-QT), `adafruit_power.lbr` (load switch), `adafruit_electromech.lbr` (button). Label nets with the exact `NETS` names so ERC/BOM cross-check against `pico2_trace.net`.
- [ ] **Step 2: Run ERC**

Run: `kicad-cli sch erc --exit-code-violations pico2_trace.kicad_sch; echo exit=$?`
Expected: report with 0 errors (warnings for intentional NC allowed), `exit=0`.

- [ ] **Step 3: Cross-check the schematic netlist equals the model**

```bash
kicad-cli sch export netlist -o sch.net pico2_trace.kicad_sch
python3 hw/checks.py --compare-netlists sch.net pico2_trace.net
```
Expected: `netlists match` (same nodes per net).

- [ ] **Step 4: Export schematic PDF** — `kicad-cli sch export pdf -o docs/schematic.pdf pico2_trace.kicad_sch`
- [ ] **Step 5: Commit** — `git commit -am "sch: ERC-clean schematic + PDF"`

---

### Task 10: PCB — instantiate board from the model (stackup, nets, net classes)

**Files:** Create `hw/build_board.py`; modify `pico2_trace.kicad_pcb`

**Interfaces:** Consumes `PARTS`/`NETS` + `hw/fp_lib.py`. Produces a board with every footprint added, every net created and assigned to pads, a 2-layer stackup, and three net classes.

- [ ] **Step 1:** `build_board.py` — for each `PARTS` entry: `board.Add(pcbnew.FOOTPRINT)` loaded from its lib, create/lookup `pcbnew.NETINFO_ITEM` per net, `pad.SetNet(...)` per `p.pins`. Set 2-layer copper (`board.SetCopperLayerCount(2)`).
- [ ] **Step 2:** Add net classes via the board design settings: `Default` (0.25 mm / 0.2 mm clr), `Power` (0.5 mm) assigned to `GND,VBUS_NET,V5_JTRACE,VSYS,P3V3,HOST_VBUS`, `Trace` (0.3 mm / 0.25 mm clr) assigned to `TRACECLK,TD0..TD3`.
- [ ] **Step 3: Verify** 

```bash
python3 hw/build_board.py && python3 - <<'PY'
import pcbnew
b=pcbnew.LoadBoard("pico2_trace.kicad_pcb")
fps={f.GetReference() for f in b.GetFootprints()}
assert {"J1","J3","J5","J9","JP1","SW1"} <= fps, fps
nc={n.GetName() for n in b.GetNetClasses()} if hasattr(b,'GetNetClasses') else set()
print("footprints:",len(fps),"nets:",b.GetNetCount())
PY
```
Expected: all footprints present, net count matches `len(NETS)+1`.

- [ ] **Step 4: DRC (unrouted allowed, connectivity only)** — `kicad-cli pcb drc pico2_trace.kicad_pcb` prints unconnected items = ratsnest (expected pre-routing). **Step 5:** commit `"pcb: instantiate footprints, nets, net classes, 2-layer stackup"`.

---

### Task 11: PCB — board outline, mounting, Pico socket edge

**Files:** Modify `hw/build_board.py` (outline section)

**Interfaces:** Produces `Edge.Cuts` closed outline (~65 × 34 mm), 4× M3 mounting holes, Pico socket placed so its micro-USB + BOOTSEL overhang a board edge.

- [ ] **Step 1:** Draw the rectangular `Edge_Cuts` outline + 3 mm corner radii + 4 mounting holes via `pcbnew.PCB_SHAPE`/`AddHole`. Place the Pico socket footprint (`PICO`) with the USB end at the board edge (leave a keepout notch so the module's USB/BOOTSEL clear).
- [ ] **Step 2: Verify outline is closed**

```bash
python3 - <<'PY'
import pcbnew
b=pcbnew.LoadBoard("pico2_trace.kicad_pcb")
edges=[d for d in b.GetDrawings() if d.GetLayer()==pcbnew.Edge_Cuts]
assert edges, "no edge cuts"
bb=b.GetBoardEdgesBoundingBox(); print("board mm:", pcbnew.ToMM(bb.GetWidth()), pcbnew.ToMM(bb.GetHeight()))
PY
```
Expected: prints board size ≈ 65 × 34 mm.

- [ ] **Step 3:** commit `"pcb: board outline, mounting holes, Pico socket edge"`.

---

### Task 12: PCB — constrained placement

**Files:** Create `hw/place.py` (placement coordinates table); modify `hw/build_board.py` to apply it

**Interfaces:** Consumes the board; produces deterministic XY/rotation for every footprint honoring the physical constraints.

- [ ] **Step 1:** Encode placement in `hw/place.py` as `POS = {ref:(x_mm,y_mm,rot)}`: MIPI-20 (J3) within 30 mm of the Pico trace pins (2,4,5,6,7 side); J4/J6/J7 grouped with J3 on that edge; Rt1–Rt5 hard against the socket trace pins; JP2/JP3 guards flanking the trace pins; J5 (USB-A) + J8 (power) + J9 (device) on the opposite edge; STEMMA/UART/button/LED on the free edge; JP1 near the power pins; load switch + ESD by J5.
- [ ] **Step 2: Apply + verify no courtyard overlaps**

```bash
python3 hw/build_board.py --place && kicad-cli pcb drc --schematic-parity=no pico2_trace.kicad_pcb 2>&1 | grep -iE 'courtyard|overlap' || echo "no courtyard errors"
```
Expected: `no courtyard errors`.

- [ ] **Step 3: Verify trace-pin → MIPI-20 span < 30 mm**

```bash
python3 - <<'PY'
import pcbnew,math
b=pcbnew.LoadBoard("pico2_trace.kicad_pcb")
def pad(ref,pn):
    f=b.FindFootprintByReference(ref)
    return next(p.GetPosition() for p in f.Pads() if p.GetNumber()==pn)
d=pad("PICO","2").Distance(pad("J3","12"))  # socket TRACECLK pin to MIPI-20 pin 12
print("CLK span mm:", pcbnew.ToMM(d)); assert pcbnew.ToMM(d) < 30
PY
```
Expected: span < 30 mm. **Step 4:** commit `"pcb: constrained placement (trace <30mm, debug edge, USB edge)"`.

---

### Task 13: PCB — route the SI-critical nets

**Files:** Create `hw/route_trace.py`

**Interfaces:** Consumes the placed board; routes TRACECLK+TD0–TD3 (through Rt at the socket), SWDIO/SWCLK, NRESET, VTREF on the top layer.

- [ ] **Step 1:** In `route_trace.py`, route each trace net as a short top-layer polyline socket-pin → Rt pad → MIPI-20 pad using `pcbnew.PCB_TRACK` on `Trace` net class; keep the five runs parallel and equalize lengths (pad extra length with a small trombone if needed). Route SWD/nRESET/VTref to J3+J6.
- [ ] **Step 2: Verify lengths matched + on-layer**

```bash
python3 - <<'PY'
import pcbnew
b=pcbnew.LoadBoard("pico2_trace.kicad_pcb")
def length(net):
    nc=b.GetNetcodeFromNetname(net)
    return pcbnew.ToMM(sum(t.GetLength() for t in b.GetTracks() if t.GetNetCode()==nc))
L={n:length(n) for n in ["TRACECLK","TD0","TD1","TD2","TD3"]}
print(L); assert max(L.values())-min(L.values()) < 3, "CLK/data mismatch >3mm"
assert all(v<30 for v in L.values())
PY
```
Expected: all < 30 mm, spread < 3 mm. **Step 3:** commit `"pcb: route length-matched trace bundle + SWD"`.

---

### Task 14: PCB — route power + USB pairs + guards

**Files:** Modify `hw/route_trace.py` (power/USB section)

**Interfaces:** Routes VBUS_NET/HOST_VBUS/VSYS/P3V3 (Power class), the host+device D± pairs (short, with series R + ESD + pulldowns adjacent), guards GP0/GP6 to GND.

- [ ] **Step 1:** Route power nets on top (wide, Power class); route each USB D± pair tightly coupled from the GPIO series R → ESD → receptacle; connect JP2/JP3 guard pins to the GND pour.
- [ ] **Step 2: Verify ratsnest reduced to bulk signals only**

```bash
python3 - <<'PY'
import pcbnew
b=pcbnew.LoadBoard("pico2_trace.kicad_pcb"); b.BuildConnectivity()
un=b.GetConnectivity().GetUnconnectedCount()
print("unconnected pads:", un)   # remaining = bulk periph nets for GUI/Freerouting finish
PY
```
Expected: prints a small count (trace/power/USB done; note remaining for interactive finish). **Step 3:** commit `"pcb: route power, USB pairs, guards"`.

- [ ] **Step 4 (interactive finish, documented):** In pcbnew GUI (or Freerouting via exported `.dsn`) route the remaining low-speed peripheral nets (I2C, UART, LED, button, current-sense). This is the one non-scripted step — the SI-critical work is already done and locked. Record it in `docs/BRINGUP.md`.

---

### Task 15: PCB — bottom ground pour + stitching

**Files:** Modify `hw/route_trace.py` (zone section)

**Interfaces:** Produces a bottom-layer `GND` zone (whole board) + top `GND` fill + stitching vias under/around the trace group.

- [ ] **Step 1:** Add a `pcbnew.ZONE` on B.Cu tied to `GND` covering the board; add a top-layer GND fill; add a grid of GND stitching vias in the trace region; `pcbnew.ZONE_FILLER(b).Fill(...)`.
- [ ] **Step 2: Verify GND is one connected pour under the trace**

```bash
python3 - <<'PY'
import pcbnew
b=pcbnew.LoadBoard("pico2_trace.kicad_pcb")
z=[z for z in b.Zones() if z.GetNetname()=="GND" and z.GetLayer()==pcbnew.B_Cu]
assert z and z[0].GetFilledArea()>0, "bottom GND not filled"
print("bottom GND filled area mm2:", pcbnew.ToMM(pcbnew.ToMM(z[0].GetFilledArea())))
PY
```
Expected: nonzero filled area. **Step 3:** commit `"pcb: bottom GND pour + stitching vias"`.

---

### Task 16: Full DRC clean

**Files:** none (verification + fixes in `hw/route_trace.py`/`place.py`)

- [ ] **Step 1: Run DRC**

Run: `kicad-cli pcb drc --schematic-parity=yes --exit-code-violations pico2_trace.kicad_pcb -o docs/drc.rpt; echo exit=$?`
Expected: `exit=0` (0 violations). Any remaining unconnected items must be only the documented Task-14 interactive nets — otherwise fix and re-run.

- [ ] **Step 2:** If violations exist, fix in the placement/route scripts and re-run until clean. **Step 3:** commit `"pcb: DRC clean"`.

---

### Task 17: Fabrication outputs, BOM, 3D render, bring-up note

**Files:** Create `docs/BOM.csv`, `docs/BRINGUP.md`, `fab/*`, `docs/board.png`

- [ ] **Step 1: Gerbers + drill + position**

```bash
kicad-cli pcb export gerbers -o fab/ pico2_trace.kicad_pcb
kicad-cli pcb export drill   -o fab/ pico2_trace.kicad_pcb
kicad-cli pcb export pos -o fab/pos.csv --format csv --units mm pico2_trace.kicad_pcb
```
Expected: `fab/` populated with `.gbr`/`.drl`/`pos.csv`.

- [ ] **Step 2: BOM** — `kicad-cli sch export bom -o docs/BOM.csv pico2_trace.kicad_sch` (or from the model if `SCHEMATIC_MODE=gui` produced no grouped BOM: generate from `PARTS`).
- [ ] **Step 3: 3D render** — `kicad-cli pcb render -o docs/board.png --side top --quality high pico2_trace.kicad_pcb`
- [ ] **Step 4: Bring-up note** — write `docs/BRINGUP.md`: power-up order, JP1/JP2/JP3/JP4 default states, the §9 native-VBUS-detect test recipe, the trace validation ladder (`DESIGN.md` §13), and the Task-14 interactive-routing record.
- [ ] **Step 5: Archive** — copy `docs/schematic.pdf` + `docs/BRINGUP.md` to the calibre library. **Step 6:** commit `"fab: gerbers, drill, pos, BOM, 3D render, bring-up note"`.

---

## Self-review notes (author)

- **Spec coverage:** every `DESIGN.md` section maps to a task — §3 form factor→T11/12, §4 connectors→T2/3, §5 trace→T5/13, §6 pin map→T7, §7 power→T4/14, §8 USB→T6/14, §9 native VBUS-detect tap→T6, §10 peripherals→T7/14, §11 BSP→(firmware, out of PCB scope; captured in BRINGUP), §12 deliverables→T17, §13 validation→BRINGUP, §14 DNP→T3 (marked DNP in PARTS).
- **Known non-automated step:** Task 14 Step 4 (bulk low-speed routing) and, if the Task-1 spike fails, Task 9 schematic drawing are interactive KiCad-GUI steps — flagged explicitly, with everything SI-critical scripted and verified.
- **Ordering:** netlist (T3–8) is the single source; schematic (T9) and PCB (T10–16) both derive from it and are cross-checked against `pico2_trace.net`.
