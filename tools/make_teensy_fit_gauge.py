"""
Emit a one-page fit gauge for the Teensy 4.1 pin rows.

Why this exists
---------------
The Teensy 4.1 pin span is a *published module dimension*, not a tolerance to
tune: 2.54 mm pitch, 58.42 mm centre-to-centre, on a 60.96 mm body. Those pads
are not something that gets nudged to match a printout, because every real
Teensy has them exactly there -- a footprint that has been widened to match a
mismeasured sheet is a footprint the real module no longer fits.

But "58.42 is right and your calipers are wrong" is not an answer either. The
disagreement is 0.84 mm on a 58 mm span, which is small enough that argument
cannot settle it and measurement can. This gauge is that measurement.

What it prints
--------------
Two pin rows at the *nominal* 2.54 mm pitch and 15.24 mm row spacing, with
calibration bars. Print at 100% on A4 with scaling off, sit the real Teensy (or
the bare header) on it and look.

    Pads line up            -> the footprint is right; the board needs nothing.
    Pads miss by ~0.8 mm    -> the real part is not nominal. Report it and the
                               footprint gets changed on purpose, with the
                               deviation recorded.
    Bars are not dead on    -> the sheet is not 1:1 and the test means nothing.
                               Fix the print first: make_calibration_sheet.py
"""

import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, "kicad-control-board", "jaiba.pretty",
                   "teensy_fit_gauge.svg")

# Nominal Teensy 4.1, from PJRC's published dimensions.
PITCH = 2.54
PINS_PER_ROW = 24
ROW_Y = 7.62                 # rows at +/- 7.62 -> 15.24 mm apart
NOMINAL_SPAN = (PINS_PER_ROW - 1) * PITCH   # 58.42 mm
POST = 0.64                  # standard square post

# The reading under investigation, drawn as a labelled span for comparison.
OBSERVED = 59.30

PAGE_W, PAGE_H = 150.0, 130.0


def build(compensate=1.0):
    half = NOMINAL_SPAN / 2.0
    cx, cy = PAGE_W / 2.0, 62.0
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           f'<svg xmlns="http://www.w3.org/2000/svg" '
           f'width="{PAGE_W / compensate:.4f}mm" '
           f'height="{PAGE_H / compensate:.4f}mm" '
           f'viewBox="0 0 {PAGE_W:.4f} {PAGE_H:.4f}">',
           '<g font-family="monospace" font-size="3.2" fill="black">']

    out.append(f'<text x="8" y="12" font-size="5">'
               'TEENSY 4.1 PIN ROW FIT GAUGE</text>')
    out.append(f'<text x="8" y="18">'
               'nominal 2.54 mm pitch, 58.42 mm centre-to-centre, '
               'rows 15.24 mm apart</text>')

    # --- the two pin rows, drawn as drilled pads would sit ----------------
    for ry in (-ROW_Y, ROW_Y):
        for i in range(PINS_PER_ROW):
            x = cx - half + i * PITCH
            y = cy + ry
            # pad ring (1.0 mm hole in a 2.2 mm pad, same as the board)
            out.append(f'<circle cx="{x:.4f}" cy="{y:.4f}" r="1.100" '
                       'fill="none" stroke="black" stroke-width="0.12"/>')
            out.append(f'<circle cx="{x:.4f}" cy="{y:.4f}" r="0.500" '
                       'fill="none" stroke="black" stroke-width="0.12"/>')

    # --- span dimension lines --------------------------------------------
    y1 = cy - ROW_Y - 6.0
    out.append(f'<line x1="{cx - half:.4f}" y1="{y1:.4f}" '
               f'x2="{cx + half:.4f}" y2="{y1:.4f}" '
               'stroke="black" stroke-width="0.4"/>')
    for xt in (cx - half, cx + half):
        out.append(f'<line x1="{xt:.4f}" y1="{y1 - 2.5:.4f}" '
                   f'x2="{xt:.4f}" y2="{y1 + 2.5:.4f}" '
                   'stroke="black" stroke-width="0.4"/>')
    out.append(f'<text x="{cx:.4f}" y="{y1 - 3.0:.4f}" text-anchor="middle">'
               f'nominal span {NOMINAL_SPAN:.2f} mm, centre to centre</text>')

    # The observed span, drawn on the same centres so any visible offset is
    # the whole disagreement at a glance.
    y2 = cy + ROW_Y + 8.0
    oh = OBSERVED / 2.0
    out.append(f'<line x1="{cx - oh:.4f}" y1="{y2:.4f}" '
               f'x2="{cx + oh:.4f}" y2="{y2:.4f}" '
               'stroke="black" stroke-width="0.4"/>')
    for xt in (cx - oh, cx + oh):
        out.append(f'<line x1="{xt:.4f}" y1="{y2 - 2.5:.4f}" '
                   f'x2="{xt:.4f}" y2="{y2 + 2.5:.4f}" '
                   'stroke="black" stroke-width="0.4"/>')
        # tick back to the nominal pin centre
    out.append(f'<text x="{cx:.4f}" y="{y2 + 5.5:.4f}" text-anchor="middle">'
               f'the disputed reading, {OBSERVED:.2f} mm '
               f'(+{(OBSERVED - NOMINAL_SPAN) / 2:.2f} mm each end)</text>')

    # --- calibration bars --------------------------------------------------
    y3 = PAGE_H - 34.0
    out.append(f'<text x="8" y="{y3 - 4:.4f}" font-size="4">'
               'MEASURE THIS FIRST -- if it is not 100 mm the gauge is '
               'meaningless</text>')
    x0 = 25.0
    out.append(f'<line x1="{x0:.4f}" y1="{y3:.4f}" x2="{x0 + 100:.4f}" '
               f'y2="{y3:.4f}" stroke="black" stroke-width="0.5"/>')
    for k in range(11):
        xt = x0 + k * 10.0
        out.append(f'<line x1="{xt:.4f}" y1="{y3 - 2.5:.4f}" '
                   f'x2="{xt:.4f}" y2="{y3 + 2.5:.4f}" '
                   'stroke="black" stroke-width="0.5"/>')
    out.append(f'<text x="{x0 + 50:.4f}" y="{y3 + 7:.4f}" '
               'text-anchor="middle">100 mm</text>')

    y4 = y3 + 16.0
    out.append(f'<line x1="{x0:.4f}" y1="{y4:.4f}" '
               f'x2="{x0 + NOMINAL_SPAN:.4f}" y2="{y4:.4f}" '
               'stroke="black" stroke-width="0.5"/>')
    for k in (0, 23):
        xt = x0 + k * PITCH
        out.append(f'<line x1="{xt:.4f}" y1="{y4 - 2.5:.4f}" '
                   f'x2="{xt:.4f}" y2="{y4 + 2.5:.4f}" '
                   'stroke="black" stroke-width="0.5"/>')
    out.append(f'<text x="{x0 + NOMINAL_SPAN / 2:.4f}" y="{y4 + 7:.4f}" '
               f'text-anchor="middle">'
               f'24-pin row, pin 1 to pin 24 = {NOMINAL_SPAN:.2f} mm</text>')

    out.append('</g></svg>')
    return "\n".join(out) + "\n"


def main():
    import sys
    compensate = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0
    if not 0.5 <= compensate <= 1.5:
        raise SystemExit(f"{compensate:g} is not a plausible printer factor.")
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(build(compensate))
    print("wrote", os.path.relpath(OUT, REPO))
    print(f"  page {PAGE_W / compensate:.2f} x {PAGE_H / compensate:.2f} mm "
          f"(compensation {compensate:g})")
    print(f"  pins at the nominal {PITCH} mm pitch, span {NOMINAL_SPAN:.2f} mm")
    print("  print A4, 100%, scaling OFF; check the 100 mm bar BEFORE reading")
    print("  anything into the pin alignment")


if __name__ == "__main__":
    main()
