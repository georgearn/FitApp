# FitApp — Freeletics-style workout app (Flet)

Browse an **exercise library** (step-by-step descriptions + an animated WebP
per exercise), filter by muscle group + equipment, build/save your own
workout variations, or let **Gemini** generate one for you. Built with
[Flet](https://flet.dev) so it compiles to a real Android APK.

## The exercise library (the foundation)

`data/exercises.json` — **1266 exercises** built by `tools/build_library.py`
from the WorkoutX library staged in `extras/library_by_zone.json` plus one
animated WebP per exercise in `assets/img/gifs_webp/<id>.webp`. Each entry
has:

```json
{
  "id": "...",
  "name": "...",
  "muscle": "Back",                       // primary group used for filtering
  "equipment": "Band",                    // primary label
  "equipment_list": ["Band"],
  "instructions": ["step 1 ...", "step 2 ..."],
  "frames": ["img/gifs_webp/<id>.webp"],  // local, offline
  "thumbnail": "img/thumbs/<id>.webp"     // static thumb for list rows
}
```

Muscle group comes from the library's own `zone` tag, mapped onto FitApp's
groups by `GROUP_OF` in `tools/gen_body.py` — the same mapping the body-map
diagram uses, so a tap on the diagram always matches the list.

### Images are bundled — the app works OFFLINE
`assets/img/gifs_webp/` (animated WebPs) and `assets/img/thumbs/` (static
list thumbnails) are stored locally (~130 MB). No internet needed to browse
or view exercises.

```
python tools/gen_thumbnails.py   # (re)generates assets/img/thumbs/ if missing entries
```

## Run it now

```
pip install -r requirements.txt   # flet==0.86.5
flet run main.py          # desktop window
flet run --web main.py    # browser; also loads on your phone over wifi
```

(There is no `fitapp/` subfolder — the app lives at the repo root: `main.py`,
`data_store.py`, `generator.py`, `ui_helpers.py`, `ai_workout.py`.)

### UI
Dark theme with a neon-cyan anatomical body and a floating pill tab bar.
The **Body** tab is a two-screen flow:

- **Screen 1 · Discovery Hub** — a search field + the large front/back body map.
  Tap a muscle *or* type a search and submit.
- **Screen 2 · Exercise List** — opens with a context header + a back arrow, a
  row of equipment filter chips, and the scrollable exercise cards. Tap a card
  → detail modal (animation, cues).

Three tabs:
- **Body** — the Hub → List flow above.
- **Workouts** — your saved workouts (with per-exercise suggested sets×reps).
- **Generate** — pick target muscles (or a preset) + available equipment, tap
  **Generate 3 variations** for the rule-based builder, **Shuffle** for
  different picks, **Save this** on the ones you like — or tap **Generate**
  with AI (Gemini) to have the model pick from the same library.

Saved workouts persist on the device via `page.shared_preferences`.

### Body diagram (Body tab)
Anatomical front + back muscle maps. Tap a muscle and the list jumps to (and
expands) that group; the tapped muscle turns blue. Tap again to clear.

- Art + tap-detection live in `body_data.py` (generated, self-contained).
- Reference copies in `extras/body/front.svg`, `back.svg`.
- Tapping is **pixel-accurate**: `gen_body.py` precomputes a hit-grid per view
  so the selected muscle matches exactly what's drawn.

Regenerate after editing the source data:
```
pip install cairosvg pillow
python tools/gen_body.py     # rewrites body_data.py + extras/body/*.svg
```

Source data: `data/bodymap_src.json`, adapted from **react-native-body-highlighter**
(MIT, © Hicham ELABBASSI). `GROUP_OF` inside `tools/gen_body.py` maps the fine
muscle slugs onto FitApp's groups — edit there to reassign a muscle.
`cairosvg`+`pillow` are needed only to regenerate, not to run the app.

### How the rule-based generator works
`generate_variations()` in `generator.py` filters the library to your
selected equipment + muscle groups, buckets by muscle, then round-robins
across groups so each variation is balanced and distinct. Small pools
degrade gracefully (fewer/shorter variations).

### AI workouts (Gemini)
`ai_workout.py` calls Google Gemini, constrained to only pick exercise ids
from the app's own library (so every returned move already has an
animation/description/equipment in the app). Needs a free API key from
https://aistudio.google.com/apikey.

### Equipment variations (e.g. Barbell Curl / Cable Curl / EZ Barbell Curl)
The browse list and search results show **one card per movement**, not one per
equipment version — an "N" chip with a swap icon appears when an exercise has
same-movement siblings on other equipment; tap it to see the full group and
jump straight to any variant's detail. If you filter the list by a specific
equipment, the collapse is bypassed so you see that exact variant directly.

Grouping is computed once, at data-build time, in `tools/build_library.py`
(`annotate_variants`): exercise names are stripped of their leading equipment
word (`_movement_key`), grouped by (movement, muscle), and — for any group
spanning 2+ equipment types — one member is picked as `is_primary` (preferring
Bodyweight, then Dumbbell, then Barbell, then Cable) with `variant_ids`
pointing at the rest; each variant carries `variant_of` back to the primary.
Re-run `tools/build_library.py` after any library rebuild to recompute it.

## Build the Android APK

One-time: install Flutter SDK + Android Studio. Then:

```
flet build apk           # output in build/apk/ — copy to phone, install
```

## Grow / re-curate the library

```
python tools/build_library.py            # rebuilds data/exercises.json from extras/library_by_zone.json
python tools/gen_thumbnails.py           # fills in any missing assets/img/thumbs/
```

## Credits / license
- Exercise data & images: WorkoutX library (staged in `extras/`).
- Body muscle map: **react-native-body-highlighter** (MIT, © Hicham ELABBASSI).
