"""
Build standalone front/back male body SVGs from the react-muscle-highlighter
dataset (soroojshehryar/react-muscle-highlighter, MIT), keeping EVERY muscle
group under its own name exactly as that resource defines it (no collapsing
into broader groups) — e.g. "chest", "obliques", "abs", "trapezius",
"upper-back", "lower-back", "gluteal", "hamstring", etc. stay separate.

Each region becomes its own <g id="<slug>" data-muscle="<slug>"><title>slug</title>
...paths...</g>, given a distinct fill so every group is visually identifiable,
plus a black-line body outline underneath. Includes the non-muscle anatomy
groups the resource also names (head, hair, hands, feet, ankles, knees, neck)
since it labels those too.

Input:  data/rmh_src.json  (scraped from the repo's assets/bodyFront.ts,
        assets/bodyBack.ts, components/SvgMaleWrapper.tsx)
Output: extras/body/muscle_highlighter_front.svg
        extras/body/muscle_highlighter_back.svg

    python tools/gen_muscle_highlighter_svg.py
"""
import json
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(BASE, "data", "rmh_src.json")
OUTDIR = os.path.join(BASE, "extras", "body")

OUTLINE_FILL = "#e7e2da"
OUTLINE_STROKE = "#22262b"

# One distinct color per muscle slug (shared across front/back where slugs repeat).
PALETTE = {
    "chest": "#ef5350", "obliques": "#ab47bc", "abs": "#ec407a",
    "biceps": "#42a5f5", "triceps": "#5c6bc0", "neck": "#8d6e63",
    "trapezius": "#7e57c2", "deltoids": "#26a69a", "adductors": "#66bb6a",
    "quadriceps": "#ffa726", "knees": "#bdbdbd", "tibialis": "#26c6da",
    "calves": "#ff7043", "forearm": "#29b6f6", "hands": "#9e9e9e",
    "ankles": "#8d6e63", "feet": "#78909c", "head": "#cfd8dc", "hair": "#6d4c41",
    "upper-back": "#5e35b1", "lower-back": "#3949ab", "gluteal": "#d4508a",
    "hamstring": "#fb8c00",
}
LABELS = {  # human-readable label kept alongside the resource's raw slug
    "chest": "Chest", "obliques": "Obliques", "abs": "Abs", "biceps": "Biceps",
    "triceps": "Triceps", "neck": "Neck", "trapezius": "Trapezius",
    "deltoids": "Deltoids", "adductors": "Adductors", "quadriceps": "Quadriceps",
    "knees": "Knees", "tibialis": "Tibialis", "calves": "Calves",
    "forearm": "Forearm", "hands": "Hands", "ankles": "Ankles", "feet": "Feet",
    "head": "Head", "hair": "Hair", "upper-back": "Upper Back",
    "lower-back": "Lower Back", "gluteal": "Gluteal", "hamstring": "Hamstring",
}


LEGEND_W = 210     # extra canvas width reserved for the legend column
ROW_H = 34
SWATCH = 18
FONT = 15


def build_svg(view, with_legend=True):
    x0, y0, w, h = [float(t) for t in view["viewBox"].split()]
    groups = [s for s in view["order"] if view["muscles"].get(s)]
    total_w = w + (LEGEND_W if with_legend else 0)

    S = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x0} {y0} {total_w} {h}" '
         f'width="{int(total_w)}" height="{int(h)}" font-family="Arial, sans-serif">']
    S.append(f'<rect x="{x0}" y="{y0}" width="{total_w}" height="{h}" fill="#ffffff"/>')
    S.append(f'<path d="{view["outline"]}" fill="{OUTLINE_FILL}" '
             f'stroke="{OUTLINE_STROKE}" stroke-width="2"/>')
    for slug in groups:
        paths = view["muscles"][slug]
        fill = PALETTE.get(slug, "#9e9e9e")
        label = LABELS.get(slug, slug)
        S.append(f'<g id="{slug}" data-muscle="{slug}"><title>{label}</title>')
        for p in paths:
            S.append(f'<path d="{p}" fill="{fill}" stroke="{OUTLINE_STROKE}" stroke-width="0.75"/>')
        S.append('</g>')

    if with_legend:
        lx = x0 + w + 24
        ly = y0 + 40
        rows_per_col = max(1, int((h - 80) // ROW_H))
        for i, slug in enumerate(groups):
            col, row = divmod(i, rows_per_col)
            cx = lx + col * (LEGEND_W // 1 if len(groups) <= rows_per_col else 150)
            cy = ly + row * ROW_H
            fill = PALETTE.get(slug, "#9e9e9e")
            label = LABELS.get(slug, slug)
            S.append(f'<rect x="{cx}" y="{cy}" width="{SWATCH}" height="{SWATCH}" rx="3" '
                     f'fill="{fill}" stroke="{OUTLINE_STROKE}" stroke-width="1"/>')
            S.append(f'<text x="{cx + SWATCH + 8}" y="{cy + SWATCH - 4}" '
                     f'font-size="{FONT}" fill="#1a1a1a">{label}</text>')
    S.append("</svg>")
    return "".join(S)


def main():
    data = json.load(open(SRC))
    os.makedirs(OUTDIR, exist_ok=True)
    for name in ("front", "back"):
        svg = build_svg(data[name])
        path = os.path.join(OUTDIR, f"muscle_highlighter_{name}.svg")
        open(path, "w", encoding="utf-8").write(svg)
        print(f"wrote {path}  ({len(data[name]['order'])} groups: "
              f"{', '.join(data[name]['order'])})")


if __name__ == "__main__":
    main()
