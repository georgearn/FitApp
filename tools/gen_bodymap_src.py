"""Rebuild data/bodymap_src.json from the vendored source in tools/vendor/react-muscle-highlighter/
(bodyFront.ts, bodyBack.ts, SvgMaleWrapper.tsx — MIT, (c) soroojshehryar,
https://github.com/soroojshehryar/react-muscle-highlighter). These three files are the
permanent local backup of the muscle-map source; re-run this any time bodymap_src.json
needs rebuilding. Follow with tools/gen_body.py to bake body_data.py + assets/body/*.svg.

    python tools/gen_bodymap_src.py
    python tools/gen_body.py
"""
import json
import os
import re

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENDOR = os.path.join(BASE, "tools", "vendor", "react-muscle-highlighter")

SLUG_RE = re.compile(r'slug:\s*"([\w-]+)"')
PATH_ARRAY_RE = re.compile(r'(left|right|common)\s*:\s*\[(.*?)\]', re.S)
STR_RE = re.compile(r'"((?:[^"\\]|\\.)*)"')
OUTLINE_RE = re.compile(r'd="([^"]*)"\s*\n\s*aria-label="male-body-outline-(front|back)"')


def parse_ts(path):
    src = open(path, encoding="utf-8").read()
    blocks = re.split(r'\n  \{\n', src)
    muscles = {}
    for b in blocks:
        m = SLUG_RE.search(b)
        if not m:
            continue
        slug = m.group(1)
        paths = []
        for side_m in PATH_ARRAY_RE.finditer(b):
            paths += [s.replace('\\"', '"') for s in STR_RE.findall(side_m.group(2))]
        muscles.setdefault(slug, []).extend(paths)
    return muscles


def extract_outlines():
    src = open(os.path.join(VENDOR, "SvgMaleWrapper.tsx"), encoding="utf-8").read()
    outlines = {}
    for m in OUTLINE_RE.finditer(src):
        outlines[m.group(2)] = m.group(1)
    return outlines


def main():
    front_muscles = parse_ts(os.path.join(VENDOR, "bodyFront.ts"))
    back_muscles = parse_ts(os.path.join(VENDOR, "bodyBack.ts"))
    outlines = extract_outlines()

    out = {
        "front": {"viewBox": "0 0 724 1448", "outline": outlines["front"], "muscles": front_muscles},
        "back": {"viewBox": "724 0 724 1448", "outline": outlines["back"], "muscles": back_muscles},
    }
    for name, v in out.items():
        print(name, "slugs:", sorted(v["muscles"]))
    dst = os.path.join(BASE, "data", "bodymap_src.json")
    json.dump(out, open(dst, "w", encoding="utf-8"), indent=1)
    print("wrote", dst)


if __name__ == "__main__":
    main()
