"""
Generate the project-local Teensy 4.1 footprint.

The footprint is built from PJRC's published dimensions
(https://www.pjrc.com/teensy/dimensions.html) rather than copied from a
third-party library, so the project carries no external licence and can emit a
modern-format footprint with pads *named by Teensy pin*.

Verified dimensions:
    board            60.96 x 17.78 mm
    pin pitch        2.54 mm
    pin span         58.42 mm  (23 gaps)
    row spacing      15.24 mm  (0.6 in)
    finished holes   0.965 mm

The row ordering matches jaiba_board_layout.TEENSY_ROW1 / TEENSY_ROW2, so the
footprint and the layout plan cannot drift apart:

    ROW1  y = -7.62 : 5V, GND, 3V3, 23, 22 ... 13, GND, 41 ... 33
    ROW2  y = +7.62 : GND, 0, 1 ... 12, 3V3, 24 ... 32

Pads are numbered by pin name. Repeated pins (GND x3, 3V3 x2) deliberately
share a pad number so KiCad ties them to one net. The USB connector sits at the
-X end, marked on the silkscreen.

Run:  python3 tools/make_teensy_footprint.py
"""

import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import jaiba_board_layout as L  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIBDIR = os.path.join(REPO, "kicad-control-board", "jaiba.pretty")
NAME = "Teensy_4.1"

PITCH = L.TEENSY_PITCH
HALF = L.TEENSY_HALF_SPAN
ROW_Y = L.TEENSY_ROW_Y
HALF_LEN = 60.96 / 2
HALF_WID = 17.78 / 2
DRILL = 1.02
PAD = L.PAD_DIA


def u():
    return str(uuid.uuid4())


def build():
    out = [f'(footprint "{NAME}"',
           "\t(version 20241229)",
           '\t(generator "jaiba-make_teensy_footprint")',
           '\t(generator_version "9.0")',
           '\t(layer "F.Cu")',
           '\t(descr "PJRC Teensy 4.1: 2x24 pin rows on 2.54mm pitch, rows 15.24mm apart, board 60.96 x 17.78mm. Generated from PJRC published dimensions. USB connector at the -X end. Pads are named by Teensy pin (0-41, GND, 3V3, 5V=VIN); repeated GND/3V3 pads share a number on purpose so KiCad ties them to one net.")',
           '\t(tags "teensy teensy41 microcontroller module socket")',
           "\t(attr through_hole)"]

    def prop(key, val, y, layer, hide=False):
        out.append(f'\t(property "{key}" "{val}"\n'
                   f'\t\t(at 0 {y} 0)\n'
                   f'\t\t(layer "{layer}")\n'
                   + ("\t\t(hide yes)\n" if hide else "")
                   + f'\t\t(uuid "{u()}")\n'
                   f'\t\t(effects (font (size 1 1) (thickness 0.15)))\n\t)')

    prop("Reference", "J", -11.43, "F.SilkS")
    prop("Value", NAME, 11.43, "F.Fab")
    prop("Datasheet", "https://www.pjrc.com/store/teensy41.html", 0, "F.Fab", hide=True)

    def line(x1, y1, x2, y2, layer, w=0.12):
        out.append(f'\t(fp_line\n\t\t(start {x1} {y1})\n\t\t(end {x2} {y2})\n'
                   f'\t\t(stroke (width {w}) (type solid))\n'
                   f'\t\t(layer "{layer}")\n\t\t(uuid "{u()}")\n\t)')

    def rect(x1, y1, x2, y2, layer, w=0.12):
        line(x1, y1, x2, y1, layer, w)
        line(x2, y1, x2, y2, layer, w)
        line(x2, y2, x1, y2, layer, w)
        line(x1, y2, x1, y1, layer, w)

    rect(-HALF_LEN - 0.25, -HALF_WID - 0.25, HALF_LEN + 0.25, HALF_WID + 0.25, "F.CrtYd", 0.05)
    rect(-HALF_LEN, -HALF_WID, HALF_LEN, HALF_WID, "F.Fab", 0.1)

    # silkscreen outline, broken where the USB connector sits (-X end)
    line(-HALF_LEN + 6.0, -HALF_WID, HALF_LEN, -HALF_WID, "F.SilkS")
    line(HALF_LEN, -HALF_WID, HALF_LEN, HALF_WID, "F.SilkS")
    line(HALF_LEN, HALF_WID, -HALF_LEN + 6.0, HALF_WID, "F.SilkS")
    line(-HALF_LEN, -3.5, -HALF_LEN + 6.0, -3.5, "F.SilkS")
    line(-HALF_LEN, 3.5, -HALF_LEN + 6.0, 3.5, "F.SilkS")
    line(-HALF_LEN, -3.5, -HALF_LEN, 3.5, "F.SilkS")
    line(-HALF_LEN + 6.0, -HALF_WID, -HALF_LEN + 6.0, -3.5, "F.SilkS")
    line(-HALF_LEN + 6.0, 3.5, -HALF_LEN + 6.0, HALF_WID, "F.SilkS")
    out.append(f'\t(fp_circle\n\t\t(center {-HALF - 2.2} {ROW_Y})\n'
               f'\t\t(end {-HALF - 1.2} {ROW_Y})\n'
               f'\t\t(stroke (width 0.3) (type solid))\n\t\t(fill no)\n'
               f'\t\t(layer "F.SilkS")\n\t\t(uuid "{u()}")\n\t)')

    pads = [(n, -HALF + i * PITCH, -ROW_Y, i == 0)
            for i, n in enumerate(L.TEENSY_ROW1)]
    pads += [(n, -HALF + i * PITCH, ROW_Y, i == 0)
             for i, n in enumerate(L.TEENSY_ROW2)]

    for num, x, y, marker in pads:
        shape = "rect" if marker else "circle"
        out.append(f'\t(pad "{num}" thru_hole {shape}\n'
                   f'\t\t(at {round(x, 2)} {round(y, 2)})\n'
                   f'\t\t(size {PAD} {PAD})\n\t\t(drill {DRILL})\n'
                   f'\t\t(layers "*.Cu" "*.Mask")\n'
                   f'\t\t(remove_unused_layers no)\n\t\t(uuid "{u()}")\n\t)')

    out.append(")")
    return "\n".join(out) + "\n"


def main():
    os.makedirs(LIBDIR, exist_ok=True)
    path = os.path.join(LIBDIR, NAME + ".kicad_mod")
    open(path, "w", encoding="utf-8").write(build())
    print("wrote", os.path.relpath(path, REPO))
    print(f"  {len(L.TEENSY_ROW1) + len(L.TEENSY_ROW2)} pads, "
          f"row spacing {2 * ROW_Y} mm, pin span {2 * HALF} mm")


if __name__ == "__main__":
    main()
