# FitApp — mini workout app (Flet) — NO-AI BACKUP

This is a **backup copy with the Gemini "Generate with AI" feature removed**.
No `ai_workout.py`, no network calls, no API key anywhere in this folder.
Everything else — body map, search, exercise library, rule-based Generate
(muscle/equipment/preset → variations) — is identical to the main `fitapp/`.
Use this if you want a version that never talks to the internet, or as a
fallback if the AI feature ever needs disabling.

Browse an **exercise library** (with step-by-step descriptions and a 2-frame
looping animation), filter by muscle group + equipment, and build/save your own
workout variations. Built with [Flet](https://flet.dev) so it compiles to a real
Android APK.

## The exercise library (the foundation)

`data/exercises.json` — **68 curated exercises** pulled from
[free-exercise-db](https://github.com/yuhonas/free-exercise-db) (public domain).
Each entry has:

```json
{
  "id": "Upright_Row_-_With_Bands",
  "name": "Upright Row - With Bands",
  "muscle": "Back",                       // primary group used for filtering
  "muscles_primary": ["traps"],
  "muscles_secondary": ["shoulders"],
  "equipment": "Band (handles)",          // primary label
  "equipment_list": ["Band (handles)"],   // full set: Barbell | Dumbbell |
                                          //   Band (handles) | Band (plain) | Mat | Bodyweight
  "category": "strength",
  "level": "beginner",
  "instructions": ["step 1 ...", "step 2 ..."],   // the description
  "frames": ["https://.../0.jpg", "https://.../1.jpg"]  // 2-frame animation
}
```

Coverage: Chest, Back, Shoulders, Biceps, Triceps, Forearms, Legs, Glutes, Core
across Barbell / Dumbbell / Band / Bodyweight.

### About the animation
free-exercise-db ships **two images per exercise** (start + end pose). The app
loops them back and forth (~0.7s) — a simple but clear "animation". True smooth
motion (GIF/video) would be a later upgrade and needs per-exercise media.

### Images are bundled — the app works OFFLINE
All 136 frames are stored locally in `assets/img/<id>/` (~8 MB) and `frames` in
`exercises.json` point at those local paths. No internet needed. Each entry also
keeps `frames_remote` (the source URLs) so images can be re-fetched after a
rebuild:

```
python tools/download_assets.py   # refills assets/img/ from frames_remote
```

### The `res/` folder you gave
Those 1986 PNGs were a *style example*. They're scrambled/unlabeled and
incomplete, so they are **not** the library source — free-exercise-db is. The
raw dump stays in `../res/` for reference only; nothing depends on it.

## Run it now

```
pip install flet==0.24.1
cd fitapp
flet run main.py          # desktop window
flet run --web main.py    # browser; also loads on your phone over wifi
```

### UI (neon overhaul)
Dark theme with a neon-cyan anatomical body and a **floating pill tab bar**
(not full-width). The **Body** tab is a two-screen flow:

- **Screen 1 · Discovery Hub** — a search field + the large front/back body map.
  Tap a muscle *or* type a search and submit.
- **Screen 2 · Exercise List** — opens with a context header (`Chest Exercises`
  or `Results for "press"`) + a back arrow, a row of equipment filter chips
  (`All / Barbell / Dumbbell / …`, built from what the context actually contains),
  and the scrollable exercise cards. Tap a card → detail modal (animation, cues).

(The reference's top heart-rate/kcal stat pills are cosmetic to a live workout
session and were left out — no fake data. Easy to add if you wire up a session.)

Three tabs:
- **Body** — the Hub → List flow above.
- **Workouts** — your saved workouts (with per-exercise suggested sets×reps).
- **Generate** — pick target muscles (or a preset) + available equipment, tap
  **Generate 3 variations**. It auto-builds 2-3 balanced variations from the
  library, **Shuffle** for different picks, **Save this** on the ones you like.

Saved workouts persist on the device via client storage.

### Body diagram (Exercises tab)
Anatomical front + back muscle maps sit at the top of the Exercises tab — a
defined muscular figure on a dark card, like the Freeletics reference. Tap a
muscle and the list jumps to (and expands) that group; the tapped muscle turns
blue. Tap again to clear.

- Art + tap-detection live in `body_data.py` (generated, self-contained).
- Static copies in `assets/body/front.svg`, `back.svg`.
- Tapping is **pixel-accurate**: `gen_body.py` precomputes a hit-grid per view
  so the selected muscle matches exactly what's drawn (no rough rectangles).

Regenerate after editing the source data:
```
pip install cairosvg pillow
python tools/gen_body.py     # rewrites body_data.py + assets/body/*.svg
```

Source data: `data/bodymap_src.json`, adapted from **react-native-body-highlighter**
(MIT, © Hicham ELABBASSI). The fine muscle slugs are mapped onto FitApp's 9
groups in `GROUP_OF` inside `tools/gen_body.py` — edit there to reassign a muscle.
Front shows Chest/Shoulders/Biceps/Triceps/Forearms/Core/Legs/Back; back shows
Back/Shoulders/Triceps/Forearms/Glutes/Legs — all 9 groups across the two views.
`cairosvg`+`pillow` are needed only to regenerate, not to run the app.

### How the generator works
`generate_variations()` in `main.py` filters the library to your selected
equipment + muscle groups, buckets by muscle, then round-robins across groups
(with a per-variation offset) so each variation is balanced and distinct. Small
pools degrade gracefully (fewer/shorter variations). It's a pure function — the
same one an AI-workout feature would call after the model returns exercise ids.

### Equipment variations (e.g. Barbell Curl / Cable Curl / EZ Barbell Curl)
The browse list and search results show **one card per movement**, not one per
equipment version — a small **"N" chip with a swap icon** appears when an
exercise has same-movement siblings on other equipment; tap it to see the full
group and jump straight to any variant's detail. If you filter the list by a
specific equipment (e.g. "Cable"), the collapse is bypassed so you see that
exact variant directly instead of the group's default primary.

Grouping is computed once, at data-build time, in `tools/build_library.py`
(`annotate_variants`): exercise names are stripped of their leading equipment
word (`_movement_key`), grouped by (movement, muscle), and — for any group
spanning 2+ equipment types — one member is picked as `is_primary` (preferring
Bodyweight, then Dumbbell, then Barbell, then Cable) with `variant_ids`
pointing at the rest; each variant carries `variant_of` back to the primary.
Re-run `tools/build_library.py` after any library rebuild to recompute it.

### Equipment split (bands & mat)
`equipment_list` distinguishes **Band (handles)** (tube band) from **Band
(plain)** (loop/therapy band), and tags floor moves with **Mat**. free-exercise-db
only has a generic "bands" tag, so the split is inferred by keywords in
`tools/build_library.py` (`PLAIN_BAND_HINTS`, `MAT_HINTS`) — tweak those lists,
or hand-correct `equipment_list` on any exercise.

## Build the Android APK

One-time: install Flutter SDK + Android Studio. Then:

```
cd fitapp
flet build apk           # output in build/apk/ — copy to phone, install
```

## Grow / re-curate the library

```
cd fitapp
python tools/build_library.py            # rebuilds data/exercises.json (68)
python tools/build_library.py --per-eq 3 # bigger set (~100+)
```

`data/free-exercise-db.full.json` is the full 873-exercise source. Edit the
`GROUPS` / `PER_EQ` knobs in `tools/build_library.py` to change the mix.

### Add YOUR missing-equipment exercises (band-with-handles, plain band, etc.)
free-exercise-db has a generic "bands" tag and can't tell *handles* from a
*plain* band, and has no "mat" category. Add those by hand — append rows to
`data/exercises.json`:

```json
{ "id": "band_pull_apart", "name": "Band Pull-Apart", "muscle": "Back",
  "muscles_primary": ["traps"], "muscles_secondary": ["shoulders"],
  "equipment": "Band", "level": "beginner",
  "instructions": ["Hold band at shoulder width...", "Pull apart..."],
  "frames": ["https://your-image-0.jpg", "https://your-image-1.jpg"] }
```

(Want a distinct "Band w/ handles" vs "Plain band" equipment split, or a "Mat"
tag? Easy to add to the schema + filters — just ask.)

## AI workouts — not in this copy

The main `fitapp/` has a "Generate with AI" button (Google Gemini). This backup
has it fully removed — no `ai_workout.py`, no network code, no key prompt. The
rule-based **Generate** tab (pick muscles/equipment/preset → get variations)
still works exactly the same, entirely offline.

## Credits / license
- Exercise data & images: **free-exercise-db** (Unlicense / public domain).
- Body muscle map: **react-native-body-highlighter** (MIT, © Hicham ELABBASSI).
```
```
