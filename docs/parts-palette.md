# Verified parts palette (LCSC / JLCPCB)

Every part below was sourced, tier-checked, and assembled (or explicitly
audited) for pico2_trace_motherboard, JLC order W2026073018593887
(2026-07-30). Stock and tier drift — the live parts page arbitrates — but
these are proven starting points. Basic tier = no per-line loading fee;
Extended ≈ $3/line.

## Connectors

| Part                      | LCSC              | Tier  | Notes                                                                                                         |
| ------------------------- | ----------------- | ----- | ------------------------------------------------------------------------------------------------------------- |
| USB Type-C 16P receptacle | C165948           | Basic | HRO TYPE-C-31-M-12; audited lands in `lib/pcb.pretty/` (PWR + DEV renumbers); 5A across paralleled VBUS beams |
| USB-A receptacle (host)   | C6307429          | Ext   | GCT USB1046, SMD signals + 2 THT posts                                                                        |
| JST-SH 3-pin horizontal   | C160403           | Ext   | debug-probe jack (SM03B-SRSS-TB)                                                                              |
| JST-SH 4-pin horizontal   | C51940130         | Ext   | STEMMA-QT (XYECONN clone, measured fit); C160404 = JST genuine alt                                            |
| 2x10 1.27mm bare header   | C41360882         | Ext   | XUNPU, measured fit for FTSH-110 land (MIPI-20); Samtec C20728453 +$16                                        |
| 2x5 1.27mm bare header    | C3975188          | Ext   | HCTL, measured fit for FTSH-105 land; Samtec C448647 +$7                                                      |
| 1x20 socket 2.54 THT      | C124410           | Ext   | Ckmtw B-2200S20P; carrier sockets                                                                             |
| 1x03 / 1x02 header THT    | C124376 / C124375 | Ext   | Ckmtw jumper/UART/SWD headers                                                                                 |

## ICs

| Part                 | LCSC    | Tier | Notes                                            |
| -------------------- | ------- | ---- | ------------------------------------------------ |
| TPS2051B load switch | C24593  | Ext  | host VBUS switching, active-high EN, FLG         |
| INA180A1 sense amp   | C122228 | Ext  | 20V/V, with 0.1Ω 1206 shunt C844896              |
| USBLC6-2SC6 ESD      | C7519   | Ext  | ST genuine; UMW clone C2687116 (pin1 unverified) |

## Passives / misc (0402 unless noted)

| Value                   | LCSC            | Tier  | Notes                                    |
| ----------------------- | --------------- | ----- | ---------------------------------------- |
| 100n 16V                | C1525           | Basic | C307331 Samsung 50V alt                  |
| 22u 0805                | C45783          | Basic |                                          |
| 22R                     | C25092          | Basic | USB series                               |
| 27R                     | C25100          | Ext   | trace source-series                      |
| 1k / 1.5k               | C11702 / C25867 | Basic |                                          |
| 5.1k                    | C25905          | Basic | Type-C CC Rd (±10% allowed by spec)      |
| 8.2k                    | C413094         | Ext   | Panasonic; Basic C25924 was industry-dry |
| 15k / 100k              | C25756 / C25741 | Basic |                                          |
| LED 0603 green          | C12624          | Ext   | C2289 = yellow-green hue alt             |
| B3S-1000 button         | C2733655        | Ext   | C180420 = same part, other packaging     |
| B5819W schottky SOD-123 | C8598           | Basic | diode-OR feeds                           |
| 1N4148W SOD-123         | —               | —     | DNP bus-power option slot                |

## JLC fee behavior (proven 2026-07-30)

- Deselecting a matched BOM line does NOT remove its Extended loading fee.
- ANY THT line present brings back the hand-solder (~$3.6) + manual
  assembly (~$2.6-3.4) block — partial THT deselection saves almost
  nothing once one THT line is in.
- Economic PCBA requires green solder mask (red had no compatible
  material type).
- PCBA qty 2 vs 5 is chosen in the assembly form / cart, not the PCB qty.
