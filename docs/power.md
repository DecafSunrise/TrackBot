# Power System

## Power Budget

### Estimated Draw by Component

| Component | Idle | Typical Load | Peak |
|---|---|---|---|
| LattePanda Sigma (i5-1340P) | 7 W | 45 W | 75 W |
| OAK-D-Lite (USB powered) | 0.6 W | 3 W | 5 W |
| 2× DC motors (small chassis) | 0 W | 15 W | 40 W |
| USB microphone | 0.1 W | 0.5 W | 1 W |
| USB audio / WiFi | 0.5 W | 1 W | 2 W |
| **Total** | **~8 W** | **~65 W** | **~120 W** |

### Why 18 V Power-Tool Batteries Work

| Requirement | 18 V Tool Battery |
|---|---|
| Sigma input range | 12–20 V DC → 18 V nominal (20 V hot off charger) is perfect |
| Sigma needs ≥90 W | A 5 Ah tool battery delivers 90 Wh — 1+ hour runtime |
| Motor spikes | Tool batteries are designed for 30 A+ loads (drills/saws) |
| Built-in protection | BMS handles over-discharge, over-current, short-circuit |

### The Voltage Problem (Motors vs. Sigma)

Most small DC gearmotors are **rated for 6 V or 12 V**. Running them at 18 V will overspeed them by 1.5–3× and may damage the gearbox or burn the windings.

**Solution:** Use a DC-DC buck converter to step the battery voltage down for the motors.

## Wiring Diagram

```
                        ┌─────────────────────────────────────────┐
                        │             TRACKBOT POWER               │
                        └─────────────────────────────────────────┘

    18V Tool Battery (4S Li-ion, nominal 18V, hot ~20V)
              │
              ├── [10A fuse] ──► Sigma DC barrel jack (18V direct)
              │                     Accepts 12-20V, 90W+ required
              │
              └── [10A fuse] ──► Buck converter 18V→12V (or 6V)
                                      │
                                      ├── [motor rail 12V]
                                      │      │
                                      │      ▼
                                      │  Motor Driver ──► M1, M2
                                      │
                                      └── [optional] 5V USB rail
                                             │
                                             ▼
                                        5V peripherals
```

## Components Needed

| Item | Example | Est. Cost |
|---|---|---|
| Battery terminal adapter | "DeWalt battery to XT60" or 3D-printed | $10–20 |
| Buck converter (motor) | DROK 12V 15A adjustable step-down | $15 |
| Buck converter (5V rail, optional) | LM2596 module | $8 |
| Panel-mount XT60 connectors | 2× XT60 bulkhead | $6 |
| Inline fuse holders + 10A fuses | 2× ATO blade fuse holder | $8 |
| 30A master kill switch | Blue Sea 3001 or generic | $8 |
| 14–16 AWG silicone wire | Red + black, 3m each | $10 |
| Power distribution terminal block | 4-position barrier strip | $5 |
| **Total** | | **~$80** |

## Runtime Estimates

Light use: Sigma idle (7 W) + OAK-D streaming (3 W) + motors off.
Heavy use: Sigma under load (45 W) + motors climbing (40 W).

### Single 18V Battery

| Capacity | Idle | Cruising | Heavy (stall/climb) |
|---|---|---|---|
| 2.0 Ah (36 Wh) | 45 min | 25 min | 12 min |
| 3.0 Ah (54 Wh) | 1.1 hr | 35 min | 18 min |
| 5.0 Ah (90 Wh) | 1.9 hr | 1.0 hr | 30 min |
| 9.0 Ah (162 Wh) | 3.4 hr | 1.9 hr | 55 min |

### Two Batteries in Parallel

With the hot-swap diode setup, double the above.

## Hot-Swap Parallel (Optional)

Wire both battery ports with Schottky diodes so the higher voltage battery powers the system. You can swap the dead one without powering down.

```
Battery 1 ─┬──[[10A Schottky]]──┬── 18V Bus
           │                    │
Battery 2 ─┴──[[10A Schottky]]──┘
```

Schottky diodes drop ~0.4 V (vs. 0.7 V for standard silicon). Use **rated for 10 A+** (e.g., MBR1045 or a TO-220 package on a heatsink).

## Safety Rules

1. **Fuse both battery positive lines** within 5 cm of the terminal
2. **Master kill switch** on the main positive bus, reachable from outside the chassis
3. **Star ground** — all grounds meet at one point (not daisy-chained)
4. **Keep motor power and SBC power separate** electrically (different buck regulators)
5. **Twisted pair** for encoder wires to reject motor EMI
6. **14 AWG minimum** for main power, 18 AWG for encoders
