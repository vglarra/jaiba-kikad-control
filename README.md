# jaiba-kicad-control

KiCad project for the Jaiba hexa-drum's control board: three Teensy 4.1s in
sockets — one per hemisphere plus one for the UI — with a velostat **and** a
piezo front-end for every drum sensor, plus five loop-control sensors.

## System overview

```mermaid
graph LR
    R["Right hemisphere Teensy<br/>9 sensors x (velostat + piezo)<br/>USB-MIDI out"]
    L["Left hemisphere Teensy<br/>7 sensors x (velostat + piezo)<br/>+ 5 loop sensors via mux<br/>USB-MIDI out"]
    UI["UI Teensy<br/>ST7796 TFT + XPT2046 touch"]

    R -- "Serial1, crossed<br/>pins 0/1" --> UI
    L -- "Serial3, crossed<br/>pins 14/15" --> UI
```

Every sensor Teensy sends MIDI straight to the host over its own USB port; the
UART links carry calibration commands and live monitoring only. Each sensor
Teensy is a separate USB-MIDI device and the host merges them.

## The 18-analog-input ceiling

This is the constraint the whole layout follows.

A Teensy 4.1 has exactly **18 analog inputs**, and it is a hardware limit, not a
software one: the i.MX RT1062 has 18 ADC-capable pads and Teensy 4.1 breaks all
of them out. Pins 28–37 are *not* analog — the core's `pin_to_channel[]` table
returns `255` for them, and `analogRead()` returns 0.

```
A0  A1  A2  A3  A4  A5  A6  A7  A8  A9  A10 A11 A12 A13 A14 A15 A16 A17
14  15  16  17  18  19  20  21  22  23  24  25  26  27  38  39  40  41
```

Each drum sensor needs **two** analog inputs — one for its velostat layer, one
for its piezo layer — so:

| Board | Sensors | Analog pins | Spare |
|---|---|---|---|
| Right hemisphere | 9 dual-layer | 18/18 | 0 |
| Left hemisphere | 7 dual-layer + 5 loop | 15/18 | 3 |
| UI Teensy | — | 0/18 | 16 |
| **Total** | **16 dual-layer + 5 loop = 21** | | |

The five loop sensors cannot fit alongside the hemisphere sensors: 16 dual-layer
sensors already consume 32 of the two sensor Teensys' 36 analog pins, and the
left Teensy has only **4** spare — one short of five.

So the loop sensors are wired **velostat-only** (they need one pin each, not
two, because nothing needs their attack velocity) and **share a single ADC pin
through a CD74HC4067 16:1 multiplexer** on the left Teensy: `C0`–`C4` are the
loop sensors, `SIG` goes to one analog pin, `S0`–`S3` to four digital pins, and
`EN` is tied to ground so the mux is always enabled. That leaves **11 mux
channels free** for future pads.

**This costs the percussive pads nothing.** The mux is never in their signal
path — they keep dedicated ADC pins — and because the loop sensors leave the
percussive scan entirely, the fast loop actually gets *shorter* (7 pads instead
of the 9 that two dual-layer loop sensors would have made). The loop sensors can
be read on a slow `millis()` cadence since velostat control does not need a
high sample rate.

### Two more things that shape the layout

**The analog pins are lopsided across the two rows.** Fourteen of the eighteen
sit on ROW1 (pins 14–23 and 38–41); only four (24–27) are on ROW2. That is why
each sensor Teensy's 7 ROW1-only sensors are the ones that get dedicated pins,
and why the loop sensors (which need one pin each, not two) were the ones moved
behind the mux.

**Two ADCs.** Pins 26/27 (A12/A13) and 38/39 (A14/A15) are ADC2-only; the other
fourteen are ADC1. `analogRead()` handles the switching transparently, but it
matters if you ever want simultaneous sampling.

## Floorplan

The drum pad cables arrive at the **right-hand edge** of the board, and the three
Teensys' USB sockets point **left**, so the board splits into two regions:

```
   +----------------------------------------------------------+
   |  U_R  [buttons]                       colA         colB  |
   |  U_L  [buttons]   U_MUX             ||    ||      ||   || |
   |  U_UI [TFT]                         ||    ||      ||   || |
   |                                   (8 dual + 3    (8 dual +|
   |                                    loop rows)    2 loops) |
   +----------------------------------------------------------+
```

* **Left** — the three Teensys stacked vertically with their USB sockets facing
  left, each sensor Teensy with its cal/curve buttons below it, plus the mux and
  the TFT header.
* **Right** — every sensor connector, in **two columns of cells whose connectors
  face outward**: 21 connectors at x = 120 mm (11 of them) and x = 152 mm (10).
  The aisle between the columns is what lets a cable reach the inner one.
* **Buses** run vertically at x = 92 mm (3V3) and x = 100 mm (GND), between the
  two regions, where they clear every courtyard on both sides.

A cell's connector sits on the **right** of the cell, which is why
`sensor_cell(..., mirrored=True)` exists: it is a true mirror of the left-facing
variant about the cell's centre line, and mirroring is what keeps the internal
routing crossing-free.

**What this costs.** Gathering the connectors here makes each cell's two runs to
its Teensy long jumpers — roughly 30–130 mm instead of the ~15 mm they were when
the cells sat directly above ROW1. They are wire jumpers either way on a
single-sided board, but it is the main trade of this arrangement: the piezo ADC
node (about 5 kΩ source impedance) now travels the length of the board. If that
shows up as noise on the piezo channels, the fix is to keep the piezo front end
by the Teensy and move only the connector out to the edge.

## Board geometry

* **150 × 260 mm**, two copper layers in KiCad's stackup. Fixed by the enclosure,
  so it is a constraint rather than an outcome. Reaching 150 wide was a re-flow
  of the left region, not of the cell columns: the old layout had ~30 mm of dead
  space between the Teensys and the buses. The extra 20 mm of height went into
  the cell row pitch (25 → 27 mm) and the button cluster.
* Rows are **15.24 mm apart** (0.6"), pin span 58.42 mm, board 60.96 × 17.78 mm.
  (0.7" is the *board width*, not the row pitch — an earlier revision used
  17.78 mm as `ROW_GAP` and the sockets could not line up with a real Teensy.)
* Power buses run the full height at x = 66 mm (3V3) and x = 71 mm (GND).
  Neither bar is tapped by any track or pad — they are hand-soldered jumper
  rails, and the ground connection is the F.Cu pour. The channel they sit in is
  bounded by the wire-pad fan at x = 64.81 on the left and the sensor front-ends
  at 78.79 on the right, so a future move anywhere in 73–78 is clear.
* Mounting holes at 6 mm in from each corner.

## Sensor front-ends

Each sensor is one 4-pin connector (`3V3`, `VELO`, `PIEZO`, `GND`) plus its
divider parts, so a hemisphere's nine sensors are nine identical cells:

**Velostat layer** — the sheet is the top leg, the board's 100 Ω is the bottom:

```
3V3 ── velostat ──┬── VELO  (ADC pin)
                  │
                 100Ω
                  │
                 GND
```

**Piezo layer** — 10k/10k attenuator with a clamp diode:

```
PIEZO ── R1 (10k) ──┬── PSIG  (ADC pin)
                    │
                   R2 (10k)          1N4148
                    │                 │
                   GND      anode ────┴──── cathode → 3V3
```

The diode's **anode** faces the ADC node and its **cathode** faces 3.3 V. Note
that KiCad's `D_DO-35_SOD27_P7.62mm_Horizontal` numbers pad 1 as the *cathode*
— the earlier revision of this board had pad 1 on the ADC node, which
forward-biases the diode for any signal below ~2.6 V and clamps the piezo node
flat instead of protecting it.

## Pin tables (verified)

Read off a real Teensy 4.1, then cross-checked against a published Teensy 4.1
footprint and symbol pair (the two agree exactly). Index 0 is the end nearest
the USB connector.

```
ROW1: 5V, GND, 3V3, 23, 22, 21, 20, 19, 18, 17, 16, 15, 14, 13, GND, 41, 40, 39, 38, 37, 36, 35, 34, 33
ROW2: GND, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 3V3, 24, 25, 26, 27, 28, 29, 30, 31, 32
```

The 5 V pin is the pin PJRC calls VIN; there is no VIN pad in either main row.

### Copper sizes for home etching

This board is hand-etched — no solder mask, no plated barrels — so the copper is
deliberately far fatter than a fab would ask for. Three constants in
`jaiba_board_layout.py` drive it, and all three footprint generators read them,
so changing them keeps the library and the board in step:

```python
TRACK_W = 0.8          # signal
BUS_W   = 1.0          # power bus bar
PAD_DIA = 2.2          # every plated through-hole pad
```

What that produces on the finished board:

| feature | size |
|---|---|
| pad diameter, all plated pads | 2.2 mm |
| track width | 0.8 mm signal, 1.0 mm bus |
| **narrowest gap, pad to pad** | **0.34 mm** |
| narrowest gap, track to pad | 1.04 mm |
| narrowest gap, track to track | 1.74 mm |
| smallest annular ring | 0.55 mm |
| mounting holes | 3.2 mm NPTH, unplated (unchanged) |

**The 0.34 mm pad-to-pad gap is the etch limit.** It is not a one-off: it occurs
at every adjacent pair on every 2.54 mm header, which is most of the board. Two
2.2 mm pads on a 2.54 mm grid leave 2.54 − 2.2 = 0.34 mm, and at that pitch **no
track can pass between two pads at all** (2.54 − 2.2 − 0.8 < 0) — which is why
the cell routing goes around pads rather than between them.

That gap is comfortable for toner transfer *if* the toner adheres and you do not
over-etch; it is where a home board will bridge first if anything does. If it
does, change `PAD_DIA` and re-run the three footprint generators:

| `PAD_DIA` | pad-to-pad gap |
|---|---|
| 2.2 mm (current) | 0.34 mm |
| 2.0 mm | 0.54 mm |
| 1.8 mm | 0.74 mm |

The board outline and every part position are unaffected — only the pads change.

### Single-sided copper

The physical build is one copper layer, so nothing can cross anything else in
copper. KiCad has no single-layer stackup (it requires an even count, minimum
two), so the board is 2-layer in KiCad and single-sided is a *manufacturing*
decision: only `F.Cu` is fabricated, and everything the plan lists as a jumper
becomes an insulated wire on the component side.

The generator draws only what can never cross: the bus bars, the short
intra-cell links, the five loop-sensor wipers, and the seven TFT/touch signals
that run straight up from their header to the UI Teensy's ROW2. **57 jumper
links remain** — each channel's runs to its analog pin, every cell's 3V3/GND
taps, the buttons, the UART links, TFT SCK, and the mux's own power and signal
runs. Run **Inspect → DRC** to see them as ratsnest.

## Files

| Path | What it is |
|---|---|
| `jaiba_board_layout.py` | **Source of truth.** Pure-Python placement + net plan, no `pcbnew`. |
| `jaiba-kicad-controlboard.py` | Applies the plan via `pcbnew`; run inside KiCad's Scripting Console. |
| `kicad-control-board/jaiba.pretty/` | Project-local footprint library — self-contained, no KiCad system libs. |
| `kicad-control-board/*.kicad_pcb` | Generated board (150 × 260 mm, 281 footprints, 612 pads). |
| `tools/make_library.py` | Rebuilds `jaiba.pretty/` by lifting footprints out of the board. |
| `tools/make_teensy_footprint.py` | Generates `Teensy_4.1.kicad_mod` from PJRC's published dimensions. |
| `tools/make_module_footprint.py` | Generates `CD74HC4067_Module.kicad_mod` from caliper measurements, plus its 1:1 check sheet. |
| `tools/make_calibration_sheet.py` | Emits `calibration_1to1.svg` — the ruler that proves a print really is 1:1. |
| `tools/make_teensy_fit_gauge.py` | Emits `teensy_fit_gauge.svg` — nominal Teensy pin rows to lay the real part on. |
| `tools/emit_board.py` | Writes the `.kicad_pcb` from the plan **without** KiCad. |
| `tools/route_jumpers.py` | Pre-routes the wire jumpers onto B.Cu as a guide (see below). |
| `tools/check_pour.py` | Measures whether a ground pour would actually connect (see below). |
| `tools/preview_board.py` | Renders the board to an SVG so a floorplan change can be eyeballed without KiCad. |
| `tools/verify_board.py` | DRC-style geometry checker (plan or emitted board). |
| `tools/kicad_sexpr.py` | S-expression reader/writer, quote-preserving. |

## Regenerating the board

**With KiCad** — open the PCB Editor, open **Tools → Scripting Console**:

```python
exec(open(r'/path/to/jaiba-kicad-controlboard.py').read())
```

**Without KiCad** — the same board straight from the plan:

```bash
python3 tools/emit_board.py            # writes kicad-control-board.kicad_pcb
python3 tools/verify_board.py kicad-control-board/kicad-control-board.kicad_pcb
```

**Full rebuild from scratch** — if `jaiba.pretty/` is ever missing, this
regenerates every footprint before the board. Order matters: the library has to
exist before `emit_board.py` can read it.

```bash
python3 tools/make_library.py           # passives, lifted out of the board
python3 tools/make_teensy_footprint.py  # Teensy 4.1, from PJRC dimensions
python3 tools/make_module_footprint.py  # CD74HC4067 module, from caliper measurements
python3 tools/emit_board.py
python3 tools/route_jumpers.py          # optional: B.Cu jumper guide
python3 tools/verify_board.py kicad-control-board/kicad-control-board.kicad_pcb
```

`verify_board.py` checks that no pad or courtyard leaves the outline, no two
pads overlap, no courtyards collide, and no track breaks clearance from another
net, a pad, or a mounting hole. A clean run prints `RESULT: clean`.

**Footprint library.** `jaiba.pretty/` is committed and self-contained, so
neither route needs KiCad's system libraries or a configured install path.
`make_library.py` only needs re-running if you change the passives; it lifts
their geometry out of a board that KiCad wrote. `make_teensy_footprint.py`
generates the Teensy footprint from PJRC's published dimensions, and
`make_module_footprint.py` generates the mux module footprint from your caliper
measurements — it prints a 1:1 SVG sheet alongside, for checking against the
real board on paper.

**Format version.** The emitted board declares KiCad 9's format
(`20241229`). KiCad 9 and 10 both open it; a newer KiCad will offer to upgrade
it in place. The stackup, design rules and plot parameters in
`tools/emit_board.py`'s `BOARD_TEMPLATE` are captured verbatim from a
KiCad-written board — edit them there rather than by hand in the `.kicad_pcb`,
which is regenerated.

## Drum-cable solder pads

The drum cable takes all the movement, so each of its four lands on its own bare
copper pad rather than only on a 2.2 mm through-hole pad. **74 pads** — four per
dual-layer cell (3V3, VELO, PRAW, GND) and two per loop cell.

They are `SolderPad_1x01`: an **8.0 × 2.0 mm rectangle of exposed copper**
(`F.Cu` + `F.Mask` only — no paste layer, because there is no stencil), sitting
just outboard of each cell's connector and fed by a straight horizontal stub
from its pin. Per connection that is 3.8 mm² of through-hole pad plus 16.0 mm² of
rectangle — **19.8 mm², 5.2× the round pad alone** — and an **8 mm run of copper**
to solder the wire along rather than one small pad.

Two constraints shaped it:

* **They could not go beside the connector in X.** The passives are ~1 mm to its
  left and the cell edge 0.8 mm to its right, so every vertical channel inside
  the cell is blocked. Outboard of the connector is the only clear space — which
  also happens to be the side the drum cable arrives from.
* **2.0 mm tall, not more.** Adjacent pins are 2.54 mm apart, so the height is
  capped at ~2.34 mm before neighbouring courtyards touch. The 2.4 mm courtyard
  leaves 0.14 mm between them.
* **8 mm is the length limit in practice** — and only because of where the pads
  land, not a rule. At 8 mm the rightmost pad ends 9.5 mm short of the edge.

Being surface-mount, these add **no holes** — the drill count is unchanged.

The 8 mm length pushed the loop cells' jumper pads out of the strip they shared
with the drum pads, so those moved below (row pitch 8 → 11 mm) and column B moved
110 → 114 mm to keep the aisle between the columns. The left region absorbed the
rest of the squeeze to 150 mm wide, leaving both cell columns where they are.

## Wire landing pads

Soldering a jumper onto a pin that already holds a socket or a module pin puts
**two joints in one hole** and pours heat into the part. So every end of every
jumper gets a pad of its own, reached by a short F.Cu stub. **100 of them:**

| where | pads | why |
|---|---|---|
| beside the Teensys | 50 | 22 right, 23 left (it also carries the mux lines), 5 UI |
| beside the mux module | 13 | `C0`–`C4`, `SIG`, `S0`–`S3`, `EN`, `VCC`, `GND` |
| in the sensor cells | 32 | `VELO` and `PSIG` for each of the 16 dual-layer sensors |
| in the loop cells | 5 | `VELO` for each |

TFT pins 6–12 have none: they are already drawn in copper to the header.

**Beside the Teensys and the mux** the pads step *diagonally* — each one further
out from the pin row and further along than the last — so the wires comb out
instead of bunching at 2.54 mm pitch. Stubs cannot cross, provably: a stub always
ends left of where the next one starts (`i × 1.15 < 2.54 × (i+1)`). Consecutive
pads land about 3.9 mm apart. The mux's channel inputs fan up and its control
pins fan down, so the module's two rows don't fight for the same space.

**In the sensor cells** the two pads go on the sides their nodes already live on,
because putting both on the right makes the two routes *topologically cross* —
no planar routing can fix that:

```
        R_VELO                                          J_PAD  (3V3 VELO PRAW GND)
   ┌──────────────┐                                        │
   │   ○ VELO     │  <- velostat pad, in the free band      │
   ├──────────────┤     between R_VELO and R1               │
   │   R1    R2   │                                         │
   │              │                                         │
   │   D          │  ○ PSIG  <- piezo pad, crossed on y=18.5 │
   └──────────────┘
```

The cal/curve buttons moved to the right-hand side of each Teensy for this: their
pads were landing *inside* the switches. Being off to the side also puts them
somewhere a finger can reach.

The B.Cu jumper guide aims at these pads rather than at component leads, which is
where the wire physically goes.

## The B.Cu jumper guide

The board is single-sided, so the ~60 connections the generator leaves unrouted
become insulated wire jumpers on the component side. KiCad draws those as
straight ratsnest lines, which at this count is an unreadable spider web.

`tools/route_jumpers.py` lays a plausible *path* for each one on **B.Cu**. That
layer is not fabricated, so it is free to use as a map, and it is a faithful
model:

* every jumper ends on a through-hole pad, and THT pads exist on all copper
  layers, so **no vias are ever needed**;
* a B.Cu track cannot clash with the F.Cu copper — which is exactly right, since
  the real wires are insulated and cross traces freely;
* B.Cu coordinates map 1:1 onto the component side, so what you see in the normal
  top view is where the wire physically goes.

Routes are orthogonal paths on a 0.635 mm lattice, avoiding pads of other nets,
mounting holes and the board edge. **They are allowed to cross each other** —
forbidding that is not a real constraint for insulated wire, and enforcing it
strangled the few corridors into the Teensys. So the guide contains many
crossings on purpose.

> **When plotting for etching, select `F.Cu` only.** B.Cu now contains copper and
> must never be made. `kicad-cli pcb export gerbers` would export both.

The verifier knows about layers: it checks F.Cu strictly, and reports B.Cu
crossings as a count rather than as shorts. KiCad's own DRC will flag them —
exclude B.Cu, or just remember what that layer is.

## A note on file formatting

`emit_board.py` refuses to write a board whose quoting KiCad would reject. The
specific trap: KiCad's parser accepts a bare *symbol* almost anywhere — unquoted
`(layer F.Cu)` and bare uuids load fine — but a value that tokenises as a
**number** where it wants a symbol is fatal. `(generator_version 9.0)` produces
exactly one error, naming a line number and nothing else:

```
Expecting 'symbol' in '...kicad-control-board.kicad_pcb', line 27117, offset 22
```

The lint walks the tree before writing and reports the path to any such value,
so this surfaces as a build error instead of a KiCad load failure.

Worth knowing: `make_library.py` lifts the passive footprints **out of the
generated board**, so its formatting style feeds back into the library and then
into the next generation. That is self-correcting now that the emitter writes
canonically, but if the board file is ever hand-edited into a non-canonical
style, re-running the chain will propagate it.

## Encoder expansion headers

The UI Teensy has **26 free digital pins** broken out on three headers, so a knob
panel can be added without soldering onto a socket pin:

| | pins | carries |
|---|---|---|
| `J_ENC_A` | 10 | **GND, 3V3**, then Teensy 23, 22, 21, 20, 19, 18, 17, 16 |
| `J_ENC_B` | 9 | Teensy 41, 40, 39, 38, 37, 36, 35, 34, 33 |
| `J_ENC_C` | 9 | Teensy 24, 25, 26, 27, 28, 29, 30, 31, 32 |

All 16 analog-capable pins (16–27, 38–41) are included, plus 10 digital-only ones.
`J_ENC_A` carries the power, taken from the Teensy's own ROW1 GND and 3V3 pins, so
no bus has to be tapped — the encoder commons can share its GND.

**Why three headers and not one.** Each Teensy pin row is a wall: a track cannot
pass between two 2.2 mm pads on a 2.54 mm pitch, so nothing can reach ROW1 from
below. Each header therefore sits on the side of the row it serves, directly
above or below it, and **every trace is a straight vertical** — pin for pin, no
crossings, no jumpers, no vias.

`J_ENC_A` sits 5.5 mm higher than `J_ENC_B` to squeeze between two obstacles: the
mux's channel extension pads below it and the UART landing pad for pin 15 above.
The header courtyard is ±1.77 (it inherits the 1×02 shell), which is what makes
that window so narrow.

### If you use potentiometers instead

Encoders are digital and use no ADC. If you switch to pots, the same headers work
— each pot wiper goes to one pin, 3V3 and GND come from `J_ENC_A`. **16 of the 26
pins are analog-capable**, so there is no need for another multiplexer: the left
Teensy's CD74HC4067 also still has **11 spare channels**, read over the UART.

## The electrostatic shield

The copper fill on F.Cu is tied to **GND** and acts as a coplanar shield and
guard around the high-impedance piezo nodes.

**It has to be grounded.** Floating copper is the opposite of a shield: it
re-radiates and capacitively couples noise onto the very nodes it sits beside.
So the zone carries the ground net and no fragment may be left floating —
`island_removal_mode 2` makes KiCad drop any that reaches no ground pad.

The fragmentation that rules the fill out as a ground *return path* is fine for
a shield, because each piece only has to be grounded, not joined to the others:

```
SHIELD : 15 of 146 pour regions reach ground
         292.81 cm2 of useful shield      (75% of the board)
         4.52 cm2 floating -> removed     (1.2%, negligible)
```

Ground reaches each region through a thermal spoke from a ground pad, and those
pads are being wired anyway — so the shield needs no extra connections. It also
does some of that wiring for you: with the shield, ground forms 15 groups instead
of 31, so relying on it would cut the ground wires from 31 to about 14. That is
still the unpredictable road, so the board is built for the 31.

Roughly three quarters of the board is also bare laminate, and every square
millimetre of it is copper the etchant has to remove — so the shield shortens the
etch as a side effect. Settings live at the top of `tools/emit_board.py`:
clearance 0.40 mm (never tighter than the board's own 0.34 mm minimum feature),
min thickness 0.50 mm so no unetchable slivers are left.

> **The board file is written UNFILLED.** KiCad computes the fill itself, so
> **press B (Fill All Zones) before plotting**, or F.Cu plots with no fill at
> all. `verify_board.py` says so every time it runs.
>
> The committed `.kicad_pcb` *does* carry a filled pour, and a stored fill goes
> stale the moment geometry moves: the polygons still hold the clearance slot
> around wherever a track used to be. A stale fill around a *foreign* net's
> copper is a short, not a gap — which is exactly why the B press is not
> optional after any layout edit.

### What it is not

A **coplanar** shield lies on the same layer as the traces, so it cannot block
fields arriving from directly above them. It guards — it intercepts surface
leakage and shrinks the pickup area around the nodes — but it is not a true
planar shield.

That needs a ground plane on **B.Cu**, which means a two-layer board. It would
also eliminate the ground wiring and the whole jumper guide, because the routing
could move to the second layer. That is a different board, not a tweak.

The shield does add capacitance from the piezo node to ground. At the node's
5 kΩ (10k ‖ 10k) and on the order of 20 pF of coupling that is a pole near
1.6 MHz — three decades above audio, so it costs nothing in the signal band.

### Why it is not a ground pour

A pour looks like the obvious way to remove the ground jumpers. On a
**single-sided** board it does not work, and `tools/check_pour.py` measures why
rather than asserting it:

```
pour-able area : 261.4 cm2 of 390.0 cm2 (66.9%)
pour regions   : 367  (largest 12710 mm2)
thermal spokes : 263 pad-to-region links
!! ground is SPLIT into 33 separate pieces
   largest group: 40 of 92 ground pads
```

Every signal trace is a wall through the plane, and 596 of them partition it
whatever the clearance. Modelling thermal spokes matters a great deal — a pad
does not have to sit *in* the pour, a spoke crosses its clearance ring, and on a
2.54 mm pitch with 2.2 mm pads that is the only way most pads ever connect. It
took the count from 73 fragments down to 33, and no further.

So a pour would have replaced 63 ground wires with roughly 32, **unpredictably**:
there is no way to tell by eye which pads are already joined, and the fragments
form parallel ground paths right beside the high-impedance piezo nodes.

## Cutting the ground wiring in copper instead

Each dual-layer cell has **three** ground points — the connector's GND (with its
drum pad already stubbed to it), the piezo divider's GND, and the velostat
pulldown's GND. A short F.Cu run joins all three, going the long way round
because the pulldown's GND pad sits behind the piezo node with the psig feed
running down that same column:

```
RV.2 ─┐
      └─ x=3.4 down ── y=14 across ── R2.2 ── y=16.5 ── J.4
```

That takes ground from **63 wire connections to 31**. `3V3` is now the largest
remaining item at **42**, because the diode's 3V3 pad at (9.46, 21) sits in a
pocket: the psig feed runs across the cell at y=18.50 above it, the cell ends
40 mm... at y=22.25 below it, and the drum stubs wall off the right-hand side.
Joining it needs a cell re-layout rather than another trace.

## Open items

- [ ] **Firmware split.** `SensorFirmware_Arduino.ino` still runs 6 velostat
      (A0–A5) + 6 piezo (A6–A11) on a *single* sensor Teensy. This board has two
      hemisphere Teensys — 9 dual-layer sensors on the right, 7 on the left —
      so the sensor firmware needs a per-hemisphere variant (or a board-ID
      offset).
- [ ] **Loop-sensor firmware.** The left Teensy now drives the CD74HC4067's
      four select lines and reads `SIG`; the loop pads are velostat-only, so the
      per-pad piezo path (`analogRead(s.piezoPin)`, and `piezoPins[]` at setup)
      needs a "this pad has no piezo" guard. Read them on a slow `millis()`
      cadence, not in the percussive scan.
- [ ] **UI firmware only reads `Serial1`.** `Serial3` appears nowhere in either
      firmware, so the left-hemisphere link is dead copper until the UI reads
      it and merges two sensor streams.
- [x] **Printer measured and compensated — DONE.** The paper check is now
      trustworthy. Through the browser SVG path the bench enlarges by **1.3266**
      (the classic 96-vs-72 dpi mismatch): the sheet's own 100 mm bar came off at
      134 mm, then 99 mm once over-corrected at 1.34, and at **1.3266 it reads
      exactly 100 mm with the Teensy pin span matching a real header.** Both
      `jaiba.pretty/calibration_1to1.svg` and `jaiba.pretty/teensy_fit_gauge.svg`
      are generated at that factor:
      `python3 tools/make_calibration_sheet.py 1.3266`.
      Notes that matter for the next person:
      * The factor is the *pipeline's* own ratio (printed/true), not the
        correction — the emitter divides by it. Get the direction wrong and the
        error doubles instead of cancelling.
      * The board via KiCad → PDF → viewer is a **different** pipeline that
        *shrinks* (measured 0.9957 from a 58.42 → 58.15 mm row). Print the check
        sheet and the board through the same one, and re-measure the bar rather
        than reusing a factor.
      * 1.3266 is within 0.5 % of the `PRINTER_SCALE = 1.32` that
        `tools/make_module_footprint.py` has carried from a 50 mm bar. Same
        effect, two independent measurements.
- [x] **Teensy pad span — RESOLVED, no change made.** The real 24-pin header
      measures 58.40–58.50 mm and the design is 58.42 mm (2.54 mm pitch × 23):
      they agree, and once the print was compensated the row matched the real
      header exactly. Every apparent discrepancy along the way (59.2, 59.3) was
      the paper or the caliper convention — a standard 0.64 mm post row measures
      58.42 mm centre-to-centre but 59.06 mm outer-edge-to-outer-edge. Widening
      the pads to chase a print was the wrong fix and would have produced a
      footprint a real Teensy no longer fits (a 58.90 mm span implies a 2.561 mm
      pitch), because `TEENSY_PITCH` also drives the UART and mux landing-pad
      fans and the pitch-aligned TFT header. Fix the paper, not the copper.
- [ ] **Verify the module footprint before ordering.** `CD74HC4067_Module`
      is generated from caliper measurements; the two pin spans were confirmed
      at exactly 38.10 mm and 17.78 mm, but `row_spacing` (14.9 mm measured, vs
      the 15.24 mm 0.1″-grid value) is still unconfirmed. Print
      `jaiba.pretty/CD74HC4067_Module_1to1_printfix.svg` at 100%, check the
      100 mm bar, then lay the module on it — every pin must drop into a hole.
      That sheet is now generated at the confirmed 1.3266 factor, so a correct
      print needs no mental arithmetic; it carries a 100 mm bar, twice as long as
      the 50 mm one it used to have, so it resolves the factor better. Fixing
      `row_spacing` is one constant in `tools/make_module_footprint.py`; the
      board outline is unaffected.
- [ ] **There is no schematic.** `kicad-control-board.kicad_sch` is empty, so
      nets exist only in the PCB, there is no ERC, and "Update PCB from
      Schematic" would wipe the design.
- [ ] **Reconsider single-sided.** 37 analog channels plus the mux is a lot of
      wire jumpers; a normal 2-layer fab would route nearly all of them in
      copper.
- [ ] Confirm the Teensy footprint's row assignment (ROW1 at y = −7.62) against
      a real Teensy in KiCad's footprint viewer before ordering.
