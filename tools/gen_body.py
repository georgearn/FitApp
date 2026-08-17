"""
Generate the anatomical body diagram module (body_data.py) + static SVGs from
the vendored muscle-map data (data/bodymap_src.json, derived from the MIT-licensed
react-muscle-highlighter by soroojshehryar).

- Maps the library's fine muscle slugs onto FitApp's 9 muscle groups.
- Bakes all SVG paths into body_data.py (self-contained, no runtime deps).
- Precomputes a pixel-accurate tap hit-grid per view (front/back) so tapping a
  muscle selects exactly that muscle, matching what's drawn.

    pip install svgpathtools pillow
    python tools/gen_body.py
"""
import json
import os
from PIL import Image, ImageDraw
from svgelements import Path as SvgPath

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(BASE, "data", "bodymap_src.json")

GROUP_OF = {
    "chest": "Chest",
    "abs": "Core", "obliques": "Obliques",
    "deltoids": "Shoulders",
    "neck": "Neck",
    "biceps": "Biceps",
    "triceps": "Triceps",
    "forearm": "Forearms",
    "trapezius": "Traps", "upper-back": "Upper Back", "lower-back": "Lower Back",
    "gluteal": "Glutes",
    "quadriceps": "Legs", "hamstring": "Legs", "calves": "Calves",
    "adductors": "Adductors", "tibialis": "Calves",
}
DECORATIVE = {"head", "hair", "hands", "feet", "ankles", "knees"}

# palettes — same neon-cyan accent in both, dark or light card/body background.
# accent stays identical across themes by design; only the surface it sits on
# (and the stroke drawn around the glowing selected muscle, for contrast) differ.
PALETTES = {
    "dark": {
        "bg": "#0c1116", "basefill": "#0e1c22", "outline": "#39c6d9",
        "muscle": "#16303a", "accent": "#28e5ff", "accent_stroke": "#bff8ff",
    },
    "light": {
        "bg": "#f3f7f8", "basefill": "#e6eef0", "outline": "#0e93a3",
        "muscle": "#d2e3e6", "accent": "#28e5ff", "accent_stroke": "#0a4d57",
    },
}
GRID_S = 8  # px per grid cell for hit detection
_ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyz"  # 1 char per group in the hit-grid


def vb_parts(vb):
    return [float(v) for v in vb.split()]


def group_paths(view):
    """Return {group: [paths]} for highlightable groups, and [decor paths]."""
    groups, decor = {}, []
    for slug, paths in view["muscles"].items():
        if slug in DECORATIVE:
            decor += paths
        elif slug in GROUP_OF:
            groups.setdefault(GROUP_OF[slug], []).extend(paths)
    return groups, decor


def svg_document(view, groups, decor, highlighted=None, size=None, palette=PALETTES["dark"]):
    x0, y0, w, h = vb_parts(view["viewBox"])
    W = size[0] if size else int(w)
    H = size[1] if size else int(h)
    bg, basefill, outline, muscle, accent, accent_stroke = (
        palette["bg"], palette["basefill"], palette["outline"], palette["muscle"],
        palette["accent"], palette["accent_stroke"])
    S = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view["viewBox"]}" '
         f'width="{W}" height="{H}">']
    S.append(f'<rect x="{x0}" y="{y0}" width="{w}" height="{h}" rx="28" fill="{bg}"/>')
    S.append(f'<path d="{view["outline"]}" fill="{basefill}" stroke="{outline}" '
             f'stroke-width="2.4" stroke-opacity="0.9"/>')
    for p in decor:
        S.append(f'<path d="{p}" fill="{basefill}" stroke="{outline}" '
                 f'stroke-width="1" stroke-opacity="0.5"/>')
    for grp, paths in groups.items():
        if grp == highlighted:
            continue
        for p in paths:
            S.append(f'<path d="{p}" fill="{muscle}" stroke="{outline}" '
                     f'stroke-width="0.8" stroke-opacity="0.55"/>')
    if highlighted and highlighted in groups:
        for p in groups[highlighted]:      # soft halo
            S.append(f'<path d="{p}" fill="none" stroke="{accent}" '
                     f'stroke-width="10" stroke-opacity="0.25"/>')
        for p in groups[highlighted]:      # solid glow
            S.append(f'<path d="{p}" fill="{accent}" fill-opacity="0.9" '
                     f'stroke="{accent_stroke}" stroke-width="1.2"/>')
    S.append("</svg>")
    return "".join(S)


_SEG_SAMPLES = 12  # points per curve segment — grid-cell granularity, not display quality


def _rasterize(paths, x0, y0, gw, gh):
    """Fill an SVG path list into a (gw x gh) grid-space mask, pure Python
    (flatten each path's subpaths to polygons via svgelements, no native cairo).

    Samples each segment's own .point(t) directly (O(1), closed-form) instead of
    the top-level Path.point(t), which re-searches arc-length across the whole
    path on every call and is catastrophically slow (~20s+ per path on a body
    outline with dozens of curve segments)."""
    img = Image.new("L", (gw, gh), 0)
    draw = ImageDraw.Draw(img)
    for p in paths:
        path = SvgPath(p)
        poly = []
        for seg in path.segments():
            kind = type(seg).__name__
            if kind == "Move":
                if len(poly) >= 3:
                    draw.polygon(poly, fill=255)
                poly = []
                pt = seg.end
                poly.append(((pt.x - x0) / GRID_S, (pt.y - y0) / GRID_S))
            elif kind == "Close":
                continue
            else:
                for i in range(1, _SEG_SAMPLES + 1):
                    pt = seg.point(i / _SEG_SAMPLES)
                    poly.append(((pt.x - x0) / GRID_S, (pt.y - y0) / GRID_S))
        if len(poly) >= 3:
            draw.polygon(poly, fill=255)
    return img


def build_hitgrid(view, groups):
    import time
    x0, y0, w, h = vb_parts(view["viewBox"])
    gw, gh = int(w // GRID_S), int(h // GRID_S)
    # order groups largest-first so smaller muscles overwrite (win) overlaps
    masks = {}
    for grp, paths in groups.items():
        t0 = time.time()
        im = _rasterize(paths, x0, y0, gw, gh)
        masks[grp] = (im.load(), sum(1 for px in im.getdata() if px > 40))
        print(f"  {grp}: {len(paths)} paths, {time.time()-t0:.1f}s", flush=True)
    order = sorted(masks, key=lambda g: -masks[g][1])
    labels = sorted(groups)
    if len(labels) > len(_ALPHABET):
        raise ValueError(f"{len(labels)} groups exceeds {len(_ALPHABET)}-char grid alphabet")
    idx = {g: _ALPHABET[i] for i, g in enumerate(labels)}
    grid = [["."] * gw for _ in range(gh)]
    for grp in order:
        px, _ = masks[grp]
        for yy in range(gh):
            for xx in range(gw):
                if px[xx, yy] > 40:
                    grid[yy][xx] = idx[grp]
    return {"gw": gw, "gh": gh, "x0": x0, "y0": y0, "s": GRID_S,
            "labels": labels, "rows": ["".join(r) for r in grid]}


TEMPLATE = '''"""AUTO-GENERATED by tools/gen_body.py — do not edit by hand.
Anatomical front/back muscle map. Data adapted from react-muscle-highlighter
(MIT, (c) soroojshehryar). Highlightable groups: {glist}."""

_PALETTES = {palettes!r}
VIEWS = {views!r}
_HIT = {hit!r}


def body_svg(view, highlighted=None, dark=True):
    v = VIEWS[view]
    p = _PALETTES["dark" if dark else "light"]
    x0, y0, w, h = [float(t) for t in v["viewBox"].split()]
    S = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{{v["viewBox"]}}" width="{{int(w)}}" height="{{int(h)}}">']
    S.append(f'<path d="{{v["outline"]}}" fill="{{p["basefill"]}}" stroke="{{p["outline"]}}" stroke-width="2.4" stroke-opacity="0.9"/>')
    for seg in v["decor"]:
        S.append(f'<path d="{{seg}}" fill="{{p["basefill"]}}" stroke="{{p["outline"]}}" stroke-width="1" stroke-opacity="0.5"/>')
    hi = None
    for grp, paths in v["groups"]:
        if grp == highlighted:
            hi = paths
            continue
        for seg in paths:
            S.append(f'<path d="{{seg}}" fill="{{p["muscle"]}}" stroke="{{p["outline"]}}" stroke-width="0.8" stroke-opacity="0.55"/>')
    if hi:
        for seg in hi:
            S.append(f'<path d="{{seg}}" fill="none" stroke="{{p["accent"]}}" stroke-width="10" stroke-opacity="0.25"/>')
        for seg in hi:
            S.append(f'<path d="{{seg}}" fill="{{p["accent"]}}" fill-opacity="0.9" stroke="{{p["accent_stroke"]}}" stroke-width="1.2"/>')
    S.append("</svg>")
    return "".join(S)


def view_size(view):
    _, _, w, h = [float(t) for t in VIEWS[view]["viewBox"].split()]
    return w, h


def body_hit(view, x, y):
    """x,y in the view's SVG coordinate space -> muscle group label or None."""
    g = _HIT[view]
    gx = int((x - g["x0"]) / g["s"])
    gy = int((y - g["y0"]) / g["s"])
    if 0 <= gy < g["gh"] and 0 <= gx < g["gw"]:
        c = g["rows"][gy][gx]
        if c != ".":
            return g["labels"][int(c, 36)]
    return None
'''


def main():
    data = json.load(open(SRC))
    views = {}
    hit = {}
    for name in ("front", "back"):
        print(f"view: {name}", flush=True)
        v = data[name]
        groups, decor = group_paths(v)
        views[name] = {"viewBox": v["viewBox"], "outline": v["outline"],
                       "decor": decor, "groups": sorted(groups.items())}
        hit[name] = build_hitgrid(v, groups)
    glist = sorted({g for n in views for g, _ in views[n]["groups"]})
    body_py = TEMPLATE.format(glist=", ".join(glist), palettes=PALETTES,
                              views=views, hit=hit)
    open(os.path.join(BASE, "body_data.py"), "w", encoding="utf-8").write(body_py)

    bdir = os.path.join(BASE, "extras", "body")
    os.makedirs(bdir, exist_ok=True)
    for name in ("front", "back"):
        v = data[name]
        groups, decor = group_paths(v)
        open(os.path.join(bdir, f"{name}.svg"), "w", encoding="utf-8").write(
            svg_document(v, dict(sorted(groups.items())), decor))
    print("wrote body_data.py + extras/body/front.svg, back.svg")
    print("groups:", glist)


if __name__ == "__main__":
    main()
