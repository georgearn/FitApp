"""
Rebuild data/exercises.json from the WorkoutX library staged in extras/
(library_by_zone.json) + assets/img/gifs_webp/<id>.webp — one animated WebP per exercise,
already converted, no gif_to_webp.py step needed).

Also picks up a static thumbnail per exercise from assets/img/thumbs/<id>.webp
(or .png) — cheap to render in the exercise list, vs. decoding the full
animation per row. tools/gen_thumbnails.py can (re)generate these as PNG if
assets/img/thumbs/ is missing entries; hand-provided webp thumbnails there
take priority.

Muscle group comes from the library's own `zone` tag (library_by_zone.json's
addition over workoutx_library.json — the same fine muscle-slug vocabulary the
body-map diagram uses, e.g. "trapezius", "upper-back", "adductors"), run
through gen_body.py's own GROUP_OF so an exercise's muscle group is *always*
exactly the body-map zone it's tappable under — one mapping, defined once,
instead of a second hand-maintained table here that could drift from it.

Input : extras/library_by_zone.json + assets/img/gifs_webp/*.webp
Output: data/exercises.json

    python tools/build_library.py
    python tools/gen_thumbnails.py
"""
import json
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(BASE, "extras", "library_by_zone.json")
WEBP_DIR = os.path.join(BASE, "assets", "img", "gifs_webp")
THUMB_DIR = os.path.join(BASE, "assets", "img", "thumbs")
OUT = os.path.join(BASE, "data", "exercises.json")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gen_body import GROUP_OF  # zone slug -> FitApp muscle group, single source of truth

EQUIPMENT_LABELS = {
    "Body Weight": "Bodyweight",
    "Ez Barbell": "EZ Barbell",
    "Bosu Ball": "Bosu Ball",
}


def equipment_list(raw):
    parts = [p.strip() for p in raw.split(",")]
    return [EQUIPMENT_LABELS.get(p, p) for p in parts]


# ---------------------------------------------------------------------------
# Group same-movement exercises that differ only by equipment (e.g. "Barbell
# Bench Press" / "Dumbbell Bench Press" / "Smith Machine Bench Press") so the
# app can show one primary card with an "N variations" chip instead of
# flooding the list with near-duplicates. Purely a display grouping — every
# exercise stays a full independent record with its own animation/steps.
# ---------------------------------------------------------------------------
import re

_EQUIP_WORDS = sorted({
    "Barbell", "Dumbbell", "Ez Barbell", "EZ Barbell", "Cable", "Kettlebell", "Band", "Bands",
    "Resistance Band", "Smith", "Smith Machine", "Leverage Machine", "Lever", "Bodyweight",
    "Stability Ball", "Bosu Ball", "Exercise Ball", "Weighted", "Assisted", "Sled", "Machine",
    "Suspension", "TRX", "Plate",
}, key=len, reverse=True)
_EQUIP_PREFIX = re.compile(r"^(?:" + "|".join(re.escape(w) for w in _EQUIP_WORDS) + r")\b[\s\-]*",
                           re.IGNORECASE)
_EQUIP_RANK = {"Bodyweight": 0, "Dumbbell": 1, "Barbell": 2, "Cable": 3}


def _movement_key(name):
    n = re.sub(r"\s*\(.*?\)\s*$", "", name).strip()  # drop trailing "(...)" qualifiers
    stripped = _EQUIP_PREFIX.sub("", n).strip()
    return (stripped or n).lower()


def annotate_variants(exercises):
    groups = {}
    for e in exercises:
        key = (_movement_key(e["name"]), e["muscle"])
        groups.setdefault(key, []).append(e)

    for members in groups.values():
        if len({m["equipment"] for m in members}) < 2:
            continue  # not a real equipment-variant group
        members.sort(key=lambda m: (_EQUIP_RANK.get(m["equipment"], 9), len(m["name"]), m["name"]))
        primary, variants = members[0], members[1:]
        primary["is_primary"] = True
        primary["variant_ids"] = [m["id"] for m in variants]
        for v in variants:
            v["is_primary"] = False
            v["variant_of"] = primary["id"]
    for e in exercises:
        e.setdefault("is_primary", True)  # ungrouped exercises are their own primary


def main():
    data = json.load(open(SRC, encoding="utf-8"))
    have_webp = set(os.listdir(WEBP_DIR)) if os.path.isdir(WEBP_DIR) else set()
    have_thumb = set(os.listdir(THUMB_DIR)) if os.path.isdir(THUMB_DIR) else set()

    out = []
    skipped_no_muscle = 0
    for x in data:
        muscle = GROUP_OF.get(x.get("zone"))
        if not muscle:
            skipped_no_muscle += 1
            continue

        xid = x["id"]
        eq_list = equipment_list(x["equipment"]) if x.get("equipment") else ["Bodyweight"]
        webp = f"{xid}.webp"
        frames = [f"img/gifs_webp/{webp}"] if webp in have_webp else []
        thumb = next((f"{xid}.{ext}" for ext in ("webp", "png") if f"{xid}.{ext}" in have_thumb), None)
        thumbnail = f"img/thumbs/{thumb}" if thumb else (frames[0] if frames else None)

        out.append({
            "id": xid,
            "name": x["name"],
            "muscle": muscle,
            "zone": x.get("zone"),
            "muscles_primary": [x["target"]] if x.get("target") else [],
            "muscles_secondary": x.get("secondaryMuscles", []),
            "equipment": eq_list[0],
            "equipment_list": eq_list,
            "instructions": x.get("instructions", []),
            "frames": frames,
            "thumbnail": thumbnail,
            "attribution": "© WorkoutX — https://workoutxapp.com/",
            "source": "workoutxapp.com",
            "category": x.get("category"),
            "difficulty": x.get("difficulty"),
            "mechanic": x.get("mechanic"),
            "force": x.get("force"),
            "met": x.get("met"),
            "caloriesPerMinute": x.get("caloriesPerMinute"),
            "description": x.get("description"),
            "isUnilateral": x.get("isUnilateral"),
            "recommendedSets": x.get("recommendedSets"),
            "recommendedReps": x.get("recommendedReps"),
        })

    annotate_variants(out)

    out.sort(key=lambda e: (e["muscle"], e["equipment"], e["name"]))
    json.dump(out, open(OUT, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print(f"Wrote {len(out)} exercises to {OUT} ({skipped_no_muscle} skipped, no mapped muscle)")
    no_gif = sum(1 for e in out if not e["frames"])
    print(f"{no_gif} exercises have no webp on disk (will show placeholder icon)")
    no_thumb = sum(1 for e in out if not e["thumbnail"])
    print(f"{no_thumb} exercises have no thumbnail (run tools/gen_thumbnails.py first for full coverage)")
    import collections
    print("by muscle:", dict(collections.Counter(e["muscle"] for e in out)))
    eqc = collections.Counter(q for e in out for q in e["equipment_list"])
    print("by equipment (multi):", dict(eqc))


if __name__ == "__main__":
    main()
