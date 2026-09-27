"""
Rasterise the ground pour and check it actually connects the ground.

KiCad fills zones itself, and this does not try to replace that. What it answers
is the question a fill cannot: on a SINGLE-SIDED board the pour is carved up by
every trace, and an island with no ground on it is dead copper that KiCad
removes -- along with anything relying on it.

A pad does not have to sit in the pour to join it: KiCad connects it with
thermal spokes, which cross the pad's own clearance ring. That matters a lot
here, because on a 2.54 mm pitch with 2.2 mm pads the neighbours' clearance
rings cover the gap between them, so almost no pad touches pour directly. So the
model is:

    OPEN    pourable -- the plane fills here
    CLEAR   inside a clearance ring: no copper, but a spoke may cross
    COPPER  foreign copper, or off-board: impassable
    GND     ground copper

Pour regions are flood-filled from OPEN, then pads, tracks and regions are
unioned -- a spoke joining a pad to a region, a ground track touching one. The
answer is whether that leaves the ground in one piece.

    python3 tools/check_pour.py [board.kicad_pcb]
"""

import collections
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import verify_board as V          # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_BOARD = os.path.join(REPO, "kicad-control-board", "kicad-control-board.kicad_pcb")

PITCH = 0.2              # default raster resolution, mm
CLEARANCE = 0.35         # pour-to-foreign-copper, matching the etch limit
EDGE_CLEARANCE = 0.5
HOLE_CLEARANCE = 0.25
THERMAL_GAP = 0.35       # must match the emitted zone
MIN_THICKNESS = 0.50     # must match FILL_MIN_THICKNESS in emit_board.py
SPOKE_REACH = 1.0        # how far past the pad a spoke may look for pour

OPEN, CLEAR, COPPER, GND = 0, 1, 2, 3


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_BOARD
    # allow sweeping the fill clearance and the raster without editing the file
    clearance = float(sys.argv[2]) if len(sys.argv) > 2 else CLEARANCE
    pitch = float(sys.argv[3]) if len(sys.argv) > 3 else PITCH
    placed, tracks, W, H, _ = V.from_board(path)

    nx, ny = int(W / pitch) + 1, int(H / pitch) + 1
    grid = bytearray(nx * ny)          # starts OPEN

    def idx(ix, iy):
        return iy * nx + ix

    def to_cell(x, y):
        return min(max(int(x / pitch), 0), nx - 1), min(max(int(y / pitch), 0), ny - 1)

    def paint(cx, cy, rad, value, only_if=None, into=None):
        target = grid if into is None else into
        x0, y0 = int((cx - rad) / pitch), int((cy - rad) / pitch)
        x1, y1 = int((cx + rad) / pitch) + 1, int((cy + rad) / pitch) + 1
        for iy in range(max(0, y0), min(ny, y1)):
            for ix in range(max(0, x0), min(nx, x1)):
                if math.hypot(ix * pitch - cx, iy * pitch - cy) <= rad:
                    i = idx(ix, iy)
                    if only_if is None or target[i] in only_if:
                        target[i] = value

    def paint_seg(x1, y1, x2, y2, rad, value, only_if=None, into=None):
        n = max(1, int(math.hypot(x2 - x1, y2 - y1) / (pitch / 2)))
        for k in range(n + 1):
            t = k / n
            paint(x1 + (x2 - x1) * t, y1 + (y2 - y1) * t, rad, value, only_if, into)

    pads = [p for f in placed for p in f["pads"]]
    holes = [p for f in placed if f["name"].startswith("MountingHole") for p in f["pads"]]
    gnd_pads = [p for p in pads if p["net"] == "GND"]
    gnd_tracks = [t for t in tracks if t["net"] == "GND"]
    other_pads = [p for p in pads if p["net"] != "GND"]
    other_tracks = [t for t in tracks if t["net"] != "GND"]

    # clearance rings first, then real copper on top of them, then ground copper
    for p in other_pads:
        paint(p["gx"], p["gy"], max(p["w"], p["h"]) / 2 + clearance, CLEAR, only_if=(OPEN,))
    for t in other_tracks:
        paint_seg(t["x1"], t["y1"], t["x2"], t["y2"], t["width"] / 2 + clearance,
                  CLEAR, only_if=(OPEN,))
    for p in other_pads:
        paint(p["gx"], p["gy"], max(p["w"], p["h"]) / 2, COPPER)
    for t in other_tracks:
        paint_seg(t["x1"], t["y1"], t["x2"], t["y2"], t["width"] / 2, COPPER)
    for p in gnd_pads:
        paint(p["gx"], p["gy"], max(p["w"], p["h"]) / 2, GND)
    for t in gnd_tracks:
        paint_seg(t["x1"], t["y1"], t["x2"], t["y2"], t["width"] / 2, GND)
    for h in holes:
        paint(h["gx"], h["gy"], (h["drill"] or 3.2) / 2 + HOLE_CLEARANCE, COPPER)
    for iy in range(ny):
        if iy * pitch < EDGE_CLEARANCE or iy * pitch > H - EDGE_CLEARANCE:
            for ix in range(nx):
                grid[idx(ix, iy)] = COPPER
    for ix in range(nx):
        if ix * pitch < EDGE_CLEARANCE or ix * pitch > W - EDGE_CLEARANCE:
            for iy in range(ny):
                grid[idx(ix, iy)] = COPPER

    # --- pour regions ------------------------------------------------------
    comp = [-1] * len(grid)
    regions = []
    for start in range(len(grid)):
        if grid[start] != OPEN or comp[start] >= 0:
            continue
        cid = len(regions)
        size = 0
        q = collections.deque([start])
        comp[start] = cid
        while q:
            i = q.popleft()
            size += 1
            ix, iy = i % nx, i // nx
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                jx, jy = ix + dx, iy + dy
                if 0 <= jx < nx and 0 <= jy < ny:
                    j = idx(jx, jy)
                    if comp[j] < 0 and grid[j] == OPEN:
                        comp[j] = cid
                        q.append(j)
        regions.append(size)

    # --- union find over: pads, tracks, regions ----------------------------
    parent = {}

    def find(a):
        parent.setdefault(a, a)
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for i, p in enumerate(gnd_pads):
        union(("pad", i), ("pad", i))
    for i, t in enumerate(gnd_tracks):
        union(("trk", i), ("trk", i))

    spoke_hits = 0
    for i, p in enumerate(gnd_pads):
        r = max(p["w"], p["h"]) / 2
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            reach = r
            while reach <= r + THERMAL_GAP + SPOKE_REACH:
                ix, iy = to_cell(p["gx"] + dx * reach, p["gy"] + dy * reach)
                v = grid[idx(ix, iy)]
                if v == COPPER:
                    break
                if v == OPEN:
                    union(("pad", i), ("region", comp[idx(ix, iy)]))
                    spoke_hits += 1
                    break
                reach += pitch
        # a ground pad overlapping another ground shape is already joined
        for j, q in enumerate(gnd_pads):
            if i != j and math.hypot(p["gx"] - q["gx"], p["gy"] - q["gy"]) <= 2.2:
                union(("pad", i), ("pad", j))

    for i, t in enumerate(gnd_tracks):
        n = max(1, int(math.hypot(t["x2"] - t["x1"], t["y2"] - t["y1"]) / pitch))
        for k in range(n + 1):
            s = k / n
            ix, iy = to_cell(t["x1"] + (t["x2"] - t["x1"]) * s,
                             t["y1"] + (t["y2"] - t["y1"]) * s)
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                jx, jy = ix + dx, iy + dy
                if 0 <= jx < nx and 0 <= jy < ny and comp[idx(jx, jy)] >= 0:
                    union(("trk", i), ("region", comp[idx(jx, jy)]))

    groups = collections.defaultdict(set)
    for i in range(len(gnd_pads)):
        groups[find(("pad", i))].add(i)

    # A no-net fill must clear EVERY pad and track, ground included -- it has no
    # net, so nothing merges with it. The grid above deliberately merges ground
    # copper, because that is right for a ground pour. So build a second grid
    # for the fill.
    fillgrid = bytearray(grid)
    for p in gnd_pads:
        paint(p["gx"], p["gy"], max(p["w"], p["h"]) / 2 + clearance, CLEAR, into=fillgrid)
    for t in gnd_tracks:
        paint_seg(t["x1"], t["y1"], t["x2"], t["y2"],
                  t["width"] / 2 + clearance, CLEAR, into=fillgrid)
    open_fill = sum(1 for v in fillgrid if v == OPEN)
    open_cells = sum(1 for v in grid if v == OPEN)

    # How much of that a fill would actually keep. A fill with no net gets no
    # thermal spokes and no island removal based on connectivity -- KiCad just
    # drops anything narrower than min_thickness. Approximate that with a
    # separable erosion of half the minimum thickness in each axis.
    er = max(1, int(round(MIN_THICKNESS / 2 / pitch)))
    tmp = bytearray(len(fillgrid))
    for iy in range(ny):
        row = iy * nx
        for ix in range(er, nx - er):
            if all(fillgrid[row + ix + d] == OPEN for d in range(-er, er + 1)):
                tmp[row + ix] = 1
    solid = 0
    for ix in range(er, nx - er):
        for iy in range(er, ny - er):
            if all(tmp[(iy + d) * nx + ix] for d in range(-er, er + 1)):
                solid += 1

    print(f"board            : {W:.1f} x {H:.1f} mm at {pitch} mm raster")
    board_cells = (W / pitch) * (H / pitch)
    print(f"COPPER FILL      : {solid * pitch * pitch / 100:.1f} cm2 retained "
          f"({100 * solid / board_cells:.1f}% of the board), at clearance {clearance} mm")
    print(f"                   {100 - 100 * solid / board_cells:.1f}% of the copper still "
          f"has to be etched away.")
    print(f"pour-able area   : {open_cells * pitch * pitch / 100:.1f} cm2 of "
          f"{W * H / 100:.1f} cm2 ({100 * open_cells / len(grid):.1f}%)")
    print(f"fill open area   : {open_fill * pitch * pitch / 100:.1f} cm2 before min_thickness")
    print(f"pour regions     : {len(regions)} "
          f"(largest {max(regions) * pitch * pitch:.1f} mm2)")
    print(f"ground pads      : {len(gnd_pads)}   ground tracks: {len(gnd_tracks)}")
    print(f"thermal spokes   : {spoke_hits} pad-to-region links")
    print()

    if len(groups) == 1:
        print("  ground is ONE piece -- every ground pad connects, in copper alone.")
        print("  The jumpers to ground can go.")
    else:
        print(f"  ground is SPLIT into {len(groups)} separate pieces.")
        print("     That is fine for a SHIELD (each piece just has to be grounded)")
        print("     and fatal for a return path. It needs ground routing or")
        print("     stitching jumpers between the groups.")
        for root, members in sorted(groups.items(), key=lambda kv: -len(kv[1]))[:6]:
            print(f"     group with {len(members):3d} ground pads")

    # --- shield integrity ---------------------------------------------------
    # A shield fragment that reaches no ground is floating copper: not merely
    # useless, actively worse, because it re-radiates onto whatever it sits
    # beside. KiCad drops those (island_removal_mode 2), which punches holes in
    # the shield, so the area lost matters.
    pad_roots = {find(("pad", i)) for i in range(len(gnd_pads))}
    live_ids = {r for r in range(len(regions)) if find(("region", r)) in pad_roots}
    live_area = sum(regions[r] for r in live_ids) * pitch * pitch
    dead_area = sum(regions[r] for r in range(len(regions))
                    if r not in live_ids) * pitch * pitch
    print()
    print(f"SHIELD           : {len(live_ids)} of {len(regions)} pour regions reach "
          f"ground")
    print(f"                   {live_area / 100:.2f} cm2 of useful shield")
    print(f"                   {dead_area / 100:.2f} cm2 floating -> removed by "
          f"island_removal_mode 2")
    return 0 if len(live_ids) > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
