"""Exercise library data, workout persistence, and small exercise-record helpers."""

import json
import os

BASE = os.path.dirname(__file__)
with open(os.path.join(BASE, "data", "exercises.json"), "r", encoding="utf-8") as f:
    EXERCISES = json.load(f)

MUSCLES = ["Chest", "Upper Back", "Traps", "Lower Back", "Shoulders", "Neck", "Biceps", "Triceps",
           "Forearms", "Legs", "Adductors", "Calves", "Glutes", "Core", "Obliques"]
MUSCLES = [m for m in MUSCLES if any(e["muscle"] == m for e in EXERCISES)]

EQUIP_PRIORITY = ["Bodyweight", "Dumbbell", "Barbell", "Cable", "Kettlebell", "Band",
                  "Resistance Band", "Leverage Machine", "Smith Machine"]
_all_equip = {q for e in EXERCISES for q in e.get("equipment_list", [])}
EQUIPMENT = [q for q in EQUIP_PRIORITY if q in _all_equip] + \
    sorted(_all_equip - set(EQUIP_PRIORITY))

PRESETS = {
    "Full body": MUSCLES,
    "Upper body": ["Chest", "Upper Back", "Traps", "Lower Back", "Shoulders", "Neck", "Biceps",
                   "Triceps", "Forearms"],
    "Lower body": ["Legs", "Calves", "Glutes"],
    "Push": ["Chest", "Shoulders", "Triceps"],
    "Pull": ["Upper Back", "Traps", "Biceps", "Forearms"],
    "Core": ["Core", "Obliques"],
    "Arms": ["Biceps", "Triceps", "Forearms"],
    "Back": ["Upper Back", "Traps", "Lower Back"],
    "CrossFit": ["Legs", "Glutes", "Core", "Chest", "Shoulders", "Upper Back", "Traps"],
}
WORKOUTS_KEY = "workouts_v1"


async def load_workouts(page):
    raw = await page.shared_preferences.get(WORKOUTS_KEY)
    try:
        return json.loads(raw) if raw else []
    except Exception:
        return []


async def save_workouts(page, workouts):
    await page.shared_preferences.set(WORKOUTS_KEY, json.dumps(workouts))


def ex_by_id(eid):
    return next((e for e in EXERCISES if e["id"] == eid), None)


def eq_list(e):
    return e.get("equipment_list") or [e.get("equipment")]


def reps_for(e):
    cat = (e.get("category") or "").lower()
    if cat in ("plyometrics", "cardio"):
        return "3 × 30s"
    return {"beginner": "3 × 12", "intermediate": "4 × 10", "expert": "4 × 8"}.get(
        e.get("level"), "3 × 10")
