"""
Generate a KiCad footprint for a CD74HC4067 16-channel mux *breakout module*.

Why this is a generator and not a checked-in footprint
------------------------------------------------------
Breakout modules are not standardised. Vendors ship electrically identical
boards with different outlines and pin-row spacings -- the listings and photos
for this module disagree by a millimetre or two. A footprint built from a photo
would look plausible and be wrong, and a wrong module footprint cannot be fixed
once the board is made. So the geometry is measured, not guessed, and
`validate()` cross-checks the numbers before anything is written.

How the measurements are taken (calipers, module component-side up with the
16-pin row on the left and the "C15" silkscreen at the top):

    +X runs toward the top of that view, +Y toward the 8-pin row.
    Origin is the centre of the module board.

      L  board_length     top edge -> bottom edge
      W  board_width      left edge -> right edge
      S  row_spacing      centre-to-centre of the two pin rows
      A  c15_from_top     top edge -> centre of the C15 pad
      B  sig_from_top     top edge -> centre of the SIG pad
      hole_dia            mounting hole diameter, only if holes are used
      holes               (distance from top edge, distance from left edge)

Accuracy: 0.1 in (2.54 mm) headers tolerate about half a millimetre, so
measurements to the nearest 0.5 mm are fine.

MEASURED on the real module:
    L = 41.5, W = 17.8, S = 14.9
    A standard 0.1 in socket header fits the pins, so the pitch is 2.54 mm --
    16 pins span 38.10 mm, which matches the 41.5 mm board. (At 2.0 mm they
    would span only 30 mm and leave ~5.7 mm empty at each end.)
    Silkscreen confirmed: left column top-to-bottom C15..C0; right column
    top-to-bottom SIG, S3, S2, S1, S0, EN, VCC, GND.
    Both rows are centred along the board, so A and B are derived from L rather
    than from a caliper reading to a hole centre. The reported A = 0.5 mm is
    impossible -- a 1.7 mm pad centred 0.5 mm from the edge would overhang the
    board by 0.35 mm -- and the derived pair keeps A - B at the structural
    -10.16 mm.

Run:  python3 tools/make_module_footprint.py
"""

import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kicad_sexpr as ks  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIBDIR = os.path.join(REPO, "kicad-control-board", "jaiba.pretty")

PITCH = 2.54
N_ROW_A = 16          # C0..C15
N_ROW_B = 8           # SIG, S3, S2, S1, S0, EN, VCC, GND

# ---------------------------------------------------------------------------
# False blocks emission. Set True once validate() is happy with YOUR numbers.
# ---------------------------------------------------------------------------
VERIFIED = True

# Measured printer scale: printed size / true size. A 50 mm calibration bar came
# off the printer at 66 mm, so 66/50 = 1.32. (Close to 4/3 = 1.333, the classic
# 96 dpi vs 72 dpi mismatch in a browser/print pipeline.)
#
# This is a property of one printer, not of the board, so it never affects the
# footprint -- it only decides whether a paper check is meaningful. Leave at 1.0
# to emit a true 1:1 sheet, or set it to your measured factor to also emit a
# pre-compensated sheet that comes out correct on that printer.
PRINTER_SCALE = 1.32

MY_MODULE = dict(
    name="CD74HC4067_Module",

    # --- measurements ------------------------------------------------------
    board_length=40.5,      # L, measured (re-measured: 41.5 was too long)
    board_width=17.9,       # W, measured
    row_spacing=14.9,       # S, measured. Nearest 0.1 in-grid value is 15.24;
                            # each row is its own header, so either is buildable
                            # -- settle it with a correctly-scaled printout.
    c15_from_top=1.20,      # derived: (40.5 - 38.10) / 2, rows centred
    sig_from_top=11.36,     # derived: (40.5 - 17.78) / 2, rows centred
    hole_dia=3.2,           # only used when holes is non-empty
    # Left empty on purpose: the module is held by its two pin headers. Each
    # entry would be one mounting hole as (mm down from the top edge, mm in from
    # the left edge) -- two independent edge-referenced measurements, nothing to
    # do with C15.
    holes=[],

    # --- confirmed against the silkscreen ----------------------------------
    row_a=["C15", "C14", "C13", "C12", "C11", "C10", "C9", "C8",
           "C7", "C6", "C5", "C4", "C3", "C2", "C1", "C0"],
    row_b=["SIG", "S3", "S2", "S1", "S0", "EN", "VCC", "GND"],

    # --- pad style (0.1 in header) -----------------------------------------
    pad_dia=2.2,      # keep in step with jaiba_board_layout.PAD_DIA
    drill=1.0,
    socket=True,            # pads sized for a female header the module plugs into
)


def u():
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# validation -- runs before anything is written
# ---------------------------------------------------------------------------

def validate(m):
    """Cross-check the caliper numbers. Returns a list of (level, message)."""
    out = []
    L, W, S = m["board_length"], m["board_width"], m["row_spacing"]
    A, B = m["c15_from_top"], m["sig_from_top"]
    r = m["pad_dia"] / 2.0
    span_a = (N_ROW_A - 1) * PITCH     # 38.10
    span_b = (N_ROW_B - 1) * PITCH     # 17.78

    def err(msg):
        out.append(("error", msg))

    def warn(msg):
        out.append(("warn", msg))

    if A < r:
        err(f"c15_from_top={A} puts the C15 pad off the board (pad radius {r}).")
    if B < r:
        err(f"sig_from_top={B} puts the SIG pad off the board (pad radius {r}).")
    end_a = A + span_a
    end_b = B + span_b
    if end_a > L - r:
        err(f"16-pin row runs {end_a:.2f} mm from the top edge but the board is "
            f"only {L} mm long -- it does not fit. (A row of 16 at 2.54 mm pitch "
            f"spans {span_a:.2f} mm, so L must be at least {span_a + 2 * r:.1f} mm.)")
    if end_b > L - r:
        err(f"8-pin row runs {end_b:.2f} mm from the top edge but the board is "
            f"only {L} mm long -- it does not fit.")
    if end_a < L - r - 5.0:
        warn(f"16-pin row ends {L - end_a:.1f} mm short of the bottom edge; "
             f"check c15_from_top against the silkscreen.")
    if S + m["pad_dia"] > W:
        err(f"row_spacing={S} plus pad diameter {m['pad_dia']} exceeds the "
            f"{W} mm board width -- the rows cannot fit.")

    # The pin grid is on 2.54 mm, so the row-to-row span is a fixed quantity.
    # These are the two values the listings and photos disagree over.
    if not any(abs(S - v) < 0.6 for v in (15.24, 17.78)):
        warn(f"row_spacing={S} is neither 15.24 mm (0.6 in) nor 17.78 mm (0.7 in), "
             f"the two values this module is built with. Re-measure?")

    off = A - B
    if abs(off) < 0.5:
        warn("c15_from_top and sig_from_top are nearly equal, so the two rows "
             "would start level -- the module's 8-pin row is offset end-ways.")

    for i, (ht, hl) in enumerate(m["holes"]):
        if not (0 <= ht <= L) or not (0 <= hl <= W):
            err(f"hole {i + 1} at ({ht}, {hl}) is outside the {L} x {W} mm board.")
            continue
        hy = -W / 2.0 + hl
        if abs(hy - (-S / 2.0)) < r + m["hole_dia"] / 2.0:
            warn(f"hole {i + 1} is close to the 16-pin row.")
        if abs(hy - S / 2.0) < r + m["hole_dia"] / 2.0:
            warn(f"hole {i + 1} is close to the 8-pin row.")

    names = m["row_a"] + m["row_b"]
    if len(set(names)) != len(names):
        dupes = sorted({n for n in names if names.count(n) > 1})
        err(f"duplicate pin names {dupes} -- each pad must be unique.")
    if len(m["row_a"]) != N_ROW_A or len(m["row_b"]) != N_ROW_B:
        err(f"expected {N_ROW_A} channel pins and {N_ROW_B} control pins, "
            f"got {len(m['row_a'])} and {len(m['row_b'])}.")
    return out


# ---------------------------------------------------------------------------
# geometry
# ---------------------------------------------------------------------------

def pad_positions(m):
    """Absolute (x, y) for every module pin, plus the mounting holes."""
    L, W, S = m["board_length"], m["board_width"], m["row_spacing"]
    A, B = m["c15_from_top"], m["sig_from_top"]
    pads = []
    for i, name in enumerate(m["row_a"]):
        pads.append((name, L / 2.0 - A - i * PITCH, -S / 2.0))
    for i, name in enumerate(m["row_b"]):
        pads.append((name, L / 2.0 - B - i * PITCH, S / 2.0))
    holes = [(L / 2.0 - ht, -W / 2.0 + hl) for ht, hl in m["holes"]]
    return pads, holes


def build(m):
    L, W = m["board_length"], m["board_width"]
    hl, hw = L / 2.0, W / 2.0
    pads, holes = pad_positions(m)

    out = [f'(footprint "{m["name"]}"',
           "\t(version 20241229)",
           '\t(generator "jaiba-make_module_footprint")',
           '\t(generator_version "9.0")',
           '\t(layer "F.Cu")',
           '\t(descr "CD74HC4067 16-channel analog multiplexer breakout module. '
           f'{L} x {W} mm, {m["row_spacing"]} mm row spacing, 2.54 mm pitch. '
           'Pads are named by module pin so they map onto the CD74HC4067 symbol.")',
           '\t(tags "CD74HC4067 mux multiplexer breakout module")',
           "\t(attr through_hole)"]

    def prop(key, val, y, layer, hide=False):
        out.append(f'\t(property "{key}" "{val}"\n\t\t(at 0 {y} 0)\n'
                   f'\t\t(layer "{layer}")\n'
                   + ("\t\t(hide yes)\n" if hide else "")
                   + f'\t\t(uuid "{u()}")\n'
                   '\t\t(effects (font (size 1 1) (thickness 0.15)))\n\t)')

    prop("Reference", "U", -hw - 1.6, "F.SilkS")
    prop("Value", m["name"], hw + 1.6, "F.Fab")
    prop("Datasheet", "https://www.ti.com/lit/ds/symlink/cd74hc4067.pdf", 0, "F.Fab", hide=True)

    def line(x1, y1, x2, y2, layer, w=0.12):
        out.append(f'\t(fp_line\n\t\t(start {round(x1, 3)} {round(y1, 3)})\n'
                   f'\t\t(end {round(x2, 3)} {round(y2, 3)})\n'
                   f'\t\t(stroke (width {w}) (type solid))\n'
                   f'\t\t(layer "{layer}")\n\t\t(uuid "{u()}")\n\t)')

    def rect(x1, y1, x2, y2, layer, w=0.12):
        line(x1, y1, x2, y1, layer, w)
        line(x2, y1, x2, y2, layer, w)
        line(x2, y2, x1, y2, layer, w)
        line(x1, y2, x1, y1, layer, w)

    rect(-hl - 0.25, -hw - 0.25, hl + 0.25, hw + 0.25, "F.CrtYd", 0.05)
    rect(-hl, -hw, hl, hw, "F.Fab", 0.1)
    rect(-hl, -hw, hl, hw, "F.SilkS")
    cx15, cy15 = pads[0][1], pads[0][2]
    out.append(f'\t(fp_circle\n\t\t(center {round(cx15, 3)} {round(cy15 - 2.2, 3)})\n'
               f'\t\t(end {round(cx15, 3)} {round(cy15 - 1.2, 3)})\n'
               f'\t\t(stroke (width 0.3) (type solid))\n\t\t(fill no)\n'
               f'\t\t(layer "F.SilkS")\n\t\t(uuid "{u()}")\n\t)')

    for name, x, y in pads:
        out.append(f'\t(pad "{name}" thru_hole circle\n'
                   f'\t\t(at {round(x, 2)} {round(y, 2)})\n'
                   f'\t\t(size {m["pad_dia"]} {m["pad_dia"]})\n'
                   f'\t\t(drill {m["drill"]})\n'
                   '\t\t(layers "*.Cu" "*.Mask")\n'
                   '\t\t(remove_unused_layers no)\n'
                   f'\t\t(uuid "{u()}")\n\t)')

    for hx, hy in holes:
        out.append(f'\t(pad "" np_thru_hole circle\n'
                   f'\t\t(at {round(hx, 2)} {round(hy, 2)})\n'
                   f'\t\t(size {m["hole_dia"]} {m["hole_dia"]})\n'
                   f'\t\t(drill {m["hole_dia"]})\n'
                   '\t\t(layers "*.Cu" "*.Mask")\n'
                   f'\t\t(uuid "{u()}")\n\t)')

    out.append(")")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# 1:1 printout -- the definitive check for a module footprint
# ---------------------------------------------------------------------------

def emit_svg(m, path, compensate=1.0, label=""):
    """Write a 1:1 SVG of the module outline and pin grid.

    The width/height attributes are in millimetres and match the viewBox
    exactly, so one SVG user unit is one millimetre and printing at 100% gives
    true size. Getting that wrong silently letterboxes the drawing and the
    printout stops being 1:1, which defeats the whole point.

    `compensate` pre-divides the declared physical size so that a printer which
    scales by that factor produces a true-size sheet. The viewBox is untouched,
    so the calibration bar stays 50 user units no matter what.

    Print with scaling OFF, lay the real module on the paper and confirm every
    pin drops into a hole.
    """
    L, W = m["board_length"], m["board_width"]
    half_l, half_w = L / 2.0, W / 2.0
    pads, holes = pad_positions(m)
    r_pad, r_drill = m["pad_dia"] / 2.0, m["drill"] / 2.0
    q = chr(34)

    # Symmetric viewBox, wide enough for the 50 mm calibration bar below.
    vw = max(L + 16.0, 56.0)
    mt, mb = 10.0, 16.0
    vh = W + mt + mb
    vx, vy = -vw / 2.0, -half_w - mt

    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           f'<svg xmlns="http://www.w3.org/2000/svg" '
           f'width="{vw / compensate:.3f}mm" height="{vh / compensate:.3f}mm" '
           f'viewBox="{vx:.3f} {vy:.3f} {vw:.3f} {vh:.3f}">',
           '<g font-family="monospace" font-size="1.3" fill="black">',
           f'<rect x="{-half_l:.3f}" y="{-half_w:.3f}" '
           f'width="{L:.3f}" height="{W:.3f}" '
           'fill="none" stroke="black" stroke-width="0.25"/>']

    for name, x, y in pads:
        out.append(f'<circle cx="{x:.3f}" cy="{y:.3f}" r="{r_pad:.3f}" '
                   'fill="none" stroke="black" stroke-width="0.12"/>')
        out.append(f'<circle cx="{x:.3f}" cy="{y:.3f}" r="{r_drill:.3f}" '
                   'fill="none" stroke="black" stroke-width="0.12"/>')
        if name in ("C15", "C0", "SIG", "GND"):
            out.append(f'<text x="{x:.3f}" y="{y - 1.7:.3f}" '
                       f'text-anchor="middle">{name}</text>')

    for hx, hy in holes:
        out.append(f'<circle cx="{hx:.3f}" cy="{hy:.3f}" '
                   f'r={q}{m["hole_dia"] / 2.0:.3f}{q} '
                   'fill="none" stroke="black" stroke-width="0.25"/>')

    ty = -half_w - 7.0
    for i, text in enumerate((
            f'{m["name"]}  {L} x {W} mm  rows {m["row_spacing"]} mm',
            'top: C0..C15 (16)    bottom: GND..SIG (8)',
            label or 'print at 100%, no "fit to page" -- then check the bar below')):
        out.append(f'<text x="0" y="{ty + i * 2.0:.3f}" '
                   f'text-anchor="middle">{text}</text>')

    # Calibration bar. Print dialogs silently rescale far more often than they
    # should, and a rescaled 1:1 sheet is worthless -- worse, it looks fine.
    # Measuring this bar turns any printout into a self-checking one.
    bar_len = 50.0
    bar_y = half_w + 4.0
    out.append(f'<line x1="{-bar_len / 2:.3f}" y1="{bar_y:.3f}" '
               f'x2="{bar_len / 2:.3f}" y2="{bar_y:.3f}" '
               'stroke="black" stroke-width="0.35"/>')
    for k in range(6):
        bx = -bar_len / 2 + k * bar_len / 5.0
        out.append(f'<line x1="{bx:.3f}" y1="{bar_y - 1.5:.3f}" '
                   f'x2="{bx:.3f}" y2="{bar_y + 1.5:.3f}" '
                   'stroke="black" stroke-width="0.35"/>')
    out.append(f'<text x="0" y="{bar_y + 4.0:.3f}" text-anchor="middle">'
               f'THIS BAR MUST MEASURE EXACTLY {bar_len:.0f} mm</text>')

    out.append('</g></svg>')
    open(path, "w", encoding="utf-8").write("\n".join(out) + "\n")


def main():
    m = MY_MODULE
    issues = validate(m)
    errors = [msg for lvl, msg in issues if lvl == "error"]
    warns = [msg for lvl, msg in issues if lvl == "warn"]

    if issues:
        print("Measurement check:")
        for msg in errors:
            print(f"  ERROR  {msg}")
        for msg in warns:
            print(f"  warn   {msg}")
        print()

    if errors:
        print("Refusing to write a footprint from inconsistent measurements.")
        return 1

    if not VERIFIED:
        print("Measurements are self-consistent, but VERIFIED is still False, so")
        print("nothing was written. Set VERIFIED = True at the top of this file")
        print("once you are confident in the numbers, then re-run.")
        return 1

    os.makedirs(LIBDIR, exist_ok=True)
    path = os.path.join(LIBDIR, m["name"] + ".kicad_mod")
    open(path, "w", encoding="utf-8").write(build(m))

    pads, holes = pad_positions(m)
    xs = [p[1] for p in pads]
    ys = [p[2] for p in pads]
    print("wrote", os.path.relpath(path, REPO))
    print(f"  {len(pads)} pins + {len(holes)} mounting holes, "
          f"{m['board_length']} x {m['board_width']} mm")
    print(f"  pin grid x {min(xs):.2f}..{max(xs):.2f}, y {min(ys):.2f}..{max(ys):.2f}")

    svg_path = path.replace(".kicad_mod", "_1to1.svg")
    emit_svg(m, svg_path)
    print("wrote", os.path.relpath(svg_path, REPO))

    if abs(PRINTER_SCALE - 1.0) > 1e-6:
        fixed = path.replace(".kicad_mod", "_1to1_printfix.svg")
        emit_svg(m, fixed, compensate=PRINTER_SCALE,
                 label=f'PRE-COMPENSATED for a printer that scales x{PRINTER_SCALE:g}'
                       ' -- measure the bar')
        print("wrote", os.path.relpath(fixed, REPO))

    print()
    print("  PRINT AT 100% WITH SCALING OFF, then measure the 50 mm bar.")
    print("  If the bar is not 50 mm, the print is not 1:1 and the fit test")
    print("  means nothing -- set PRINTER_SCALE to (measured / 50) and re-run")
    print("  to get a _printfix sheet. Once the bar reads 50 mm, lay the real")
    print("  module on the paper and check every pin drops into a hole.")
    print("  Then: place it in the plan, and run tools/verify_board.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
