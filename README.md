# FitApp

Workout app built with [Flet](https://flet.dev) (Python + Flutter) that compiles to an Android APK. It has an offline exercise library, a tappable anatomical body map, a rule-based workout generator, and optional AI-generated workouts.

## Features

- **Body tab**: search field plus a front/back muscle map. Tap a muscle or submit a search to open a filtered exercise list. Equipment chips are built from the results. Tap a card for the detail view (animation and step-by-step cues).
- **Equipment variations**: same-movement exercises that differ only by equipment (e.g. Barbell / Dumbbell Bench Press) collapse into one card with a variation chip. Filtering by a specific equipment shows that exact variant.
- **Workouts tab**: saved workouts with suggested sets × reps, persisted on-device.
- **Generate tab**: pick muscle groups (or a preset), per-group counts and equipment, then generate variations. Shuffle for new picks, save the ones you like.
- **AI workouts**: on-device Gemini Nano via `flet_aicore` (no network), or the Gemini API via `ai_workout.py` (free key from https://aistudio.google.com/apikey, entered in the app, never stored in the repo). The model can only pick ids from the app's own library.
- Follows the device light/dark setting. Works fully offline (except the Gemini API path).

## Project layout

| Path | Purpose |
| --- | --- |
| `main.py` | Flet UI and app entry point |
| `data_store.py` | Exercise library loading, muscle/equipment lists, presets, workout persistence |
| `generator.py` | Pure rule-based workout generator |
| `ai_workout.py` | Gemini prompt building, response parsing, HTTP call, on-device AI helper |
| `ui_helpers.py` | Shared thumbnail / placeholder widgets |
| `body_data.py` | Generated body-map SVG paths and tap hit-grid (do not edit by hand) |
| `flet_aicore/` | Local Flet extension wrapping Android AICore (Gemini Nano) |
| `data/exercises.json` | Exercise library (1266 entries, 15 muscle groups) |
| `data/bodymap_src.json` | Source muscle-map data for `body_data.py` |
| `assets/img/gifs_webp/` | Animated WebP per exercise |
| `assets/img/thumbs/` | Static thumbnail per exercise |
| `extras/library_by_zone.json` | Source library used by `tools/build_library.py` |
| `tools/` | Data and build scripts (see below) |

## Run

```
pip install -r requirements.txt
flet run main.py          # desktop window
flet run --web main.py    # browser
```

`flet_aicore` only takes effect in an Android build. Without it the on-device AI toggle is hidden.

## Build the Android APK

Install the Flutter SDK and Android Studio, then:

```
flet build apk            # output in build/apk/
```

`tools/build_apk.sh` and `tools/build_apk.ps1` wrap this with this machine's paths and UTF-8 console settings.

Settings live in `pyproject.toml`: `min_sdk_version = 31`, `arm64-v8a` only. The `flet-aicore` dependency there is a local file path; update it for your machine.

### Signing a release build

Keep the keystore outside the repo and never commit it or its password. Set these before `flet build apk`:

```
FLET_ANDROID_SIGNING_KEY_STORE
FLET_ANDROID_SIGNING_KEY_STORE_PASSWORD
FLET_ANDROID_SIGNING_KEY_PASSWORD
FLET_ANDROID_SIGNING_KEY_ALIAS
```

## Regenerating data

Only needed after changing sources. None of these run at app runtime.

```
pip install pillow svgelements

python tools/gen_bodymap_src.py   # data/bodymap_src.json from tools/vendor/react-muscle-highlighter
python tools/gen_body.py          # body_data.py + extras/body/front.svg, back.svg
python tools/gen_thumbnails.py    # assets/img/thumbs from assets/img/gifs_webp
python tools/build_library.py      # data/exercises.json from extras/library_by_zone.json
```

`GROUP_OF` in `tools/gen_body.py` maps fine muscle slugs onto the app's muscle groups and is also used by `build_library.py`. Edit it there to reassign a muscle. Equipment-variant grouping (`annotate_variants`) is computed in `tools/build_library.py`.

## Credits and licenses

- Exercise data and animations: © WorkoutX, https://workoutxapp.com/
- Body muscle map: [react-muscle-highlighter](https://github.com/soroojshehryar/react-muscle-highlighter) (MIT, © soroojshehryar)
