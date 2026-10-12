"""
Emit a self-checking 1:1 calibration sheet (SVG) for paper-checking footprints.

Why this exists
---------------
A paper check is only worth anything if the paper is actually 1:1. Every print
pipeline in this project can silently rescale:

  * a browser printing an SVG whose root width/height are in mm but which lands
    on the wrong paper size (classic 96 vs 72 dpi, or Letter-vs-A4 fit),
  * a print dialog left on "fit to page" / "shrink oversized pages",
  * a PDF viewer printing "fit to printable area".

None of those look wrong. A rescaled sheet looks perfectly normal and is
worthless, which is worse than no sheet at all -- hence the ruler.

The sheet declares width/height in millimetres that match the viewBox exactly,
so one SVG user unit is one millimetre and printing at 100% gives true size.

Using it
--------
    python3 tools/make_calibration_sheet.py           # true 1:1
    python3 tools/make_calibration_sheet.py 1.3266    # pre-compensated

Print at 100%, scaling OFF, A4, no borderless/scale-to-fit. Measure the 100 mm
ruler with calipers or a steel rule. If it is not 100 mm, the sheet is not 1:1;
the scale factor is measured/100, and passing it back in on the command line
produces a sheet that comes out true on that printer.

Measured on this project's bench -- TWO pipelines, opposite factors
------------------------------------------------------------------
CONFIRMED. The browser SVG path enlarges by **1.3266**. All three 1:1 sheets in
the repo are generated at that factor and each has been checked on its own
100 mm bar: this ruler, teensy_fit_gauge.svg, and the module's
CD74HC4067_Module_1to1_printfix.svg. The bar measures exactly 100 mm on all of
them, and the Teensy pin span matches a real header (58.40-58.50 mm against the
58.42 mm design span).

The SVG tools in this file and make_teensy_fit_gauge.py print through a
**browser**, and a browser printing an SVG whose root size is declared in
millimetres does not honour them: it treats the numbers as CSS pixels at 96 dpi
and rasterises at 72, so everything comes out 4/3 too big.

Ground truth: the sheet's own 100 mm bar, measured with calipers. Three rounds:

    compensate 1.0    -> bar measured 134 mm   (+34 %, the raw mismatch)
    compensate 1.34   -> bar measured  99 mm   (-1 %, over-corrected)
    compensate 1.3266 -> bar measures 100 mm   CONFIRMED, span matches the part

    pipeline factor = 1.3266

    python3 tools/make_calibration_sheet.py 1.3266
    python3 tools/make_teensy_fit_gauge.py 1.3266

A 1 %-per-round resolution was all these readings could support, and chasing
further would have been measuring the calipers: on printed lines they are worth
about 0.15 mm on a 100 mm bar. The board tolerates the residue easily -- 0.18 mm
of radial slack per hole against 0.29 mm worst-case shared between the end pins.

Note that 1.3266 is within 0.5 % of the PRINTER_SCALE = 1.32 that
make_module_footprint.py has carried all along, from a 50 mm bar. Two
independent bars, measured years apart, agreeing to half a percent: the
enlargement is real and stable, and the value to trust is the one your own
longest bar confirms.

The board itself is a different story. Plotted from KiCad as a PDF and printed
through the PDF viewer, the same 24-pin Teensy row (58.42 mm by construction)
came off at 58.15 mm against a real header measured at 58.40 mm -- a *shrink* of
0.43 %, factor 0.9957. So:

    browser SVG path   1.3266  (enlarges; 96-vs-72 dpi)
    KiCad PDF path     0.9957  (shrinks; viewer fit / paper)

Both are properties of the bench, not of the board, and neither changes the
copper. The trap: a check sheet printed through the wrong pipeline is 34 % off
while looking perfectly normal, and the two factors differ by 1.35x in effect.
Always print the check sheet and the board through the SAME pipeline, and
re-measure the 100 mm bar every time.

The factor is the PRINTER's own ratio (printed/true), not the correction: the
emitter divides the declared millimetres by it, so a factor above 1 shrinks the
declared page to compensate for an enlarging pipeline. Gear this the wrong way
and the error doubles instead of cancelling.

Older note, still true: make_module_footprint.py carries PRINTER_SCALE = 1.32
from an earlier 50 mm bar -- the same browser enlargement, measured with a
shorter bar. 1.34 is the same effect measured better; prefer it.
"""

import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, "kicad-control-board", "jaiba.pretty",
                   "calibration_1to1.svg")

# The rungs the user reads off the sheet, in true millimetres.
RUNGS = (10.0, 25.4, 50.0, 100.0)

# Longest dimension referenced on the sheet, used to size the page.
PAGE_W, PAGE_H = 140.0, 175.0

# Reference dimensions worth re-checking on paper, straight from the design.
TEENSY_ROW_SPAN = 58.42      # 24 pads at 2.54 mm pitch, centre-to-centre
TEENSY_ROW_GAP = 15.24       # the two Teensy rows, centre-to-centre
HEADER_PITCH = 2.54


def build(compensate=1.0):
    q = '"'
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           f'<svg xmlns="http://www.w3.org/2000/svg" '
           f'width="{PAGE_W / compensate:.4f}mm" '
           f'height="{PAGE_H / compensate:.4f}mm" '
           f'viewBox="0 0 {PAGE_W:.4f} {PAGE_H:.4f}">',
           '<g font-family="monospace" font-size="3.2" fill="black">']

    y = 12.0

    # --- title -------------------------------------------------------------
    for line, size in (
            ("1:1 CALIBRATION SHEET", 5.0),
            ("print at 100%, scaling OFF, A4, no fit-to-page", 3.2),
            ("then measure the bars below before trusting any paper check", 3.2)):
        out.append(f'<text x="8" y="{y:.3f}" font-size="{size}">{line}</text>')
        y += size + 2.5

    y += 4.0

    # --- measurement bars --------------------------------------------------
    out.append(f'<text x="8" y="{y:.3f}" font-size="4">'
               'MEASURE THESE. EACH MUST MATCH ITS LABEL EXACTLY.</text>')
    y += 6.0

    for length in RUNGS:
        out.append(f'<text x="8" y="{y + 1.2:.3f}">{length:g} mm</text>')
        x0, x1 = 30.0, 30.0 + length
        out.append(f'<line x1="{x0:.4f}" y1="{y:.4f}" '
                   f'x2="{x1:.4f}" y2="{y:.4f}" '
                   'stroke="black" stroke-width="0.4"/>')
        # End ticks, tall enough to read with a rule or calipers.
        for xt in (x0, x1):
            out.append(f'<line x1="{xt:.4f}" y1="{y - 3.0:.4f}" '
                       f'x2="{xt:.4f}" y2="{y + 3.0:.4f}" '
                       'stroke="black" stroke-width="0.4"/>')
        # Intermediate ticks every 10 mm so a misread is obvious.
        n = int(length // 10)
        for k in range(1, n + 1):
            xt = x0 + k * 10.0
            out.append(f'<line x1="{xt:.4f}" y1="{y - 1.8:.4f}" '
                       f'x2="{xt:.4f}" y2="{y + 1.8:.4f}" '
                       'stroke="black" stroke-width="0.4"/>')
        y += 11.0

    y += 2.0

    # --- the 50 mm print bar used elsewhere in this project ---------------
    out.append(f'<text x="8" y="{y:.3f}" font-size="4">'
               'THIS BAR MUST MEASURE EXACTLY 50 mm</text>')
    y += 5.0
    x0, x1 = 30.0, 80.0
    out.append(f'<line x1="{x0:.4f}" y1="{y:.4f}" x2="{x1:.4f}" y2="{y:.4f}" '
               'stroke="black" stroke-width="0.5"/>')
    for k in range(6):
        xt = x0 + k * 10.0
        out.append(f'<line x1="{xt:.4f}" y1="{y - 2.5:.4f}" '
                   f'x2="{xt:.4f}" y2="{y + 2.5:.4f}" '
                   'stroke="black" stroke-width="0.5"/>')
    y += 12.0

    # --- 2.54 mm header gauge ---------------------------------------------
    out.append(f'<text x="8" y="{y:.3f}" font-size="4">'
               'HEADER GAUGE: lay the real header on this, pins must land on '
               'every tick</text>')
    y += 5.0
    for k in range(11):
        xt = 30.0 + k * HEADER_PITCH
        out.append(f'<line x1="{xt:.4f}" y1="{y - 3.0:.4f}" '
                   f'x2="{xt:.4f}" y2="{y + 3.0:.4f}" '
                   'stroke="black" stroke-width="0.4"/>')
    out.append(f'<line x1="30.0000" y1="{y - 4.5:.4f}" '
               f'x2="{30.0 + 10 * HEADER_PITCH:.4f}" y2="{y - 4.5:.4f}" '
               'stroke="black" stroke-width="0.2"/>')
    out.append(f'<text x="{30.0 + 10 * HEADER_PITCH + 4:.4f}" '
               f'y="{y + 1.2:.4f}" font-size="3.2">'
               f'10 x {HEADER_PITCH} = {10 * HEADER_PITCH:.2f} mm</text>')
    y += 10.0

    # --- 10-pitch verification strip --------------------------------------
    # The only defensible way to check a header against paper: measure the
    # SAME convention on both. Centre-to-centre over 11 pins is exactly
    # 25.40 mm; edge-to-edge adds one post width, so a caliper placed on the
    # outer faces reads larger for a perfectly good header. Mixing the two
    # conventions manufactures a phantom 1.3% error, which is exactly what
    # this sheet is here to rule out.
    out.append(f'<text x="8" y="{y:.3f}" font-size="4">'
               '10-PITCH CHECK: put the real header here, then measure the '
               'same way you measured it before</text>')
    y += 6.0

    x0 = 30.0
    x1 = x0 + 10 * HEADER_PITCH
    for k in range(11):
        xt = x0 + k * HEADER_PITCH
        out.append(f'<line x1="{xt:.4f}" y1="{y - 4.0:.4f}" '
                   f'x2="{xt:.4f}" y2="{y + 4.0:.4f}" '
                   'stroke="black" stroke-width="0.4"/>')
    # The two conventions, drawn so neither can be confused for the other.
    out.append(f'<line x1="{x0:.4f}" y1="{y - 6.5:.4f}" '
               f'x2="{x1:.4f}" y2="{y - 6.5:.4f}" '
               'stroke="black" stroke-width="0.5"/>')
    out.append(f'<line x1="{x0:.4f}" y1="{y - 6.5:.4f}" '
               f'x2="{x0:.4f}" y2="{y - 4.6:.4f}" '
               'stroke="black" stroke-width="0.5"/>')
    out.append(f'<line x1="{x1:.4f}" y1="{y - 6.5:.4f}" '
               f'x2="{x1:.4f}" y2="{y - 4.6:.4f}" '
               'stroke="black" stroke-width="0.5"/>')
    out.append(f'<text x="{x0 - 2:.4f}" y="{y - 8.0:.4f}" text-anchor="end" '
               f'font-size="3.2">centre to centre = 25.40 mm</text>')

    post = 0.64   # standard square post, the usual 2.54 mm header
    out.append(f'<line x1="{x0 - post / 2:.4f}" y1="{y + 6.5:.4f}" '
               f'x2="{x1 + post / 2:.4f}" y2="{y + 6.5:.4f}" '
               'stroke="black" stroke-width="0.5"/>')
    out.append(f'<text x="{x0 - 2:.4f}" y="{y + 10.5:.4f}" text-anchor="end" '
               f'font-size="3.2">'
               f'outer edge to outer edge = {10 * HEADER_PITCH + post:.2f} mm '
               f'(with {post} mm posts)</text>')
    y += 16.0

    # --- reference dimensions from the design ------------------------------
    out.append(f'<text x="8" y="{y:.3f}" font-size="4">'
               'REFERENCE DIMENSIONS FROM THE BOARD FILE</text>')
    y += 5.5
    for label, value in (
            ("Teensy 4.1 one pin row, first to last pad", TEENSY_ROW_SPAN),
            ("Teensy 4.1 row 1 to row 2", TEENSY_ROW_GAP),
            ("Pin header pitch", HEADER_PITCH)):
        out.append(f'<text x="8" y="{y:.3f}">{label}</text>')
        out.append(f'<text x="112" y="{y:.3f}" text-anchor="end">'
                   f'{value:.2f} mm</text>')
        y += 4.5

    y += 3.0
    out.append(f'<text x="8" y="{y:.3f}" font-size="3.2">'
               'Board outline is 150.00 x 260.00 mm (too big for one A4 sheet '
               '-- this sheet is the ruler, not the board).</text>')

    out.append('</g></svg>')
    return "\n".join(out) + "\n"


def main():
    import sys
    compensate = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0
    if compensate <= 0:
        raise SystemExit("compensation factor must be positive")
    if not 0.5 <= compensate <= 1.5:
        raise SystemExit(
            f"{compensate:g} is not a plausible printer factor.\n"
            "A factor outside 0.5..1.5 usually means the wrong bar was "
            "measured, or a bar was measured in the wrong units -- recheck "
            "the 100 mm bar before overriding this.")
    svg = build(compensate)
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(svg)
    print("wrote", os.path.relpath(OUT, REPO))
    print(f"  declared page {PAGE_W / compensate:.2f} x "
          f"{PAGE_H / compensate:.2f} mm "
          f"(compensation {compensate:g}, {'true 1:1' if compensate == 1.0 else 'pre-scaled'})")
    print("  print at 100%, scaling OFF, A4, no fit-to-page")
    print("  then measure the bars -- if the 100 mm bar is not 100 mm,")
    print("  the factor is measured/100; pass it back in and re-print")


if __name__ == "__main__":
    main()
