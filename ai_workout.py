"""
AI workout builder — Google Gemini, constrained to the app's own exercise library.

The model may ONLY pick exercise ids we pass it, so every returned move has an
image, description, and equipment already in the app. Network call is plain
urllib (no extra deps). Pure helpers (build_prompt / parse_workout /
select_relevant) are testable offline; `generate` does the HTTP call.

Get a free key: https://aistudio.google.com/apikey
"""
import json
import re
import time
import urllib.request
import urllib.error

# "gemini-flash-latest" is Google's rolling alias for the current stable Flash
# model — it gets hot-swapped server-side as models are released/retired, so
# this survives future deprecations (unlike pinning e.g. "gemini-2.0-flash",
# which is what caused the 404 — that model was shut down).
DEFAULT_MODEL = "gemini-flash-latest"
_URL = "https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={k}"

# Cap how many exercises we ever hand to the model. A raw library can run into
# the thousands (each ~40-80 prompt tokens), and Gemini's free tier is rate-
# limited hard enough (RPM *and* tokens-per-minute, cut 50-80% in Dec 2025)
# that one oversized request can trip a 429 on its own — even though nothing
# looks like "overuse" in AI Studio, since that's a per-minute quota, not a
# running total. Trimming the catalog before every call is what actually
# fixes the errors this used to throw.
MAX_CATALOG = 150


def catalog_for(exercises):
    """Compact catalog handed to the model."""
    out = []
    for e in exercises:
        out.append({
            "id": e["id"],
            "name": e["name"],
            "muscle": e["muscle"],
            "equipment": e.get("equipment_list") or [e.get("equipment")],
            "level": e.get("level"),
        })
    return out


def select_relevant(goal, exercises, limit=MAX_CATALOG):
    """Narrow a (possibly huge) library down to `limit` exercises before it
    ever reaches the model. Every muscle group present in the library stays
    represented (round-robin base allocation) — within each group, exercises
    whose equipment/muscle is mentioned in the goal text are preferred."""
    if len(exercises) <= limit:
        return exercises

    goal_l = (goal or "").lower()
    words = {w for w in re.findall(r"[a-z]+", goal_l) if len(w) > 2}

    def score(e):
        hay = (e["muscle"] + " " + " ".join(e.get("equipment_list") or [])).lower()
        return sum(1 for w in words if w in hay)

    by_group = {}
    for e in exercises:
        by_group.setdefault(e["muscle"], []).append(e)
    for lst in by_group.values():
        lst.sort(key=score, reverse=True)  # goal-relevant exercises first, per group

    groups = list(by_group)
    picked, seen = [], set()
    i = 0
    while len(picked) < limit and groups:
        g = groups[i % len(groups)]
        lst = by_group[g]
        if lst:
            e = lst.pop(0)
            if e["id"] not in seen:
                seen.add(e["id"])
                picked.append(e)
        if not lst:
            groups.remove(g)
            continue
        i += 1
    return picked


def build_prompt(goal, catalog):
    return (
        "You are a fitness coach building ONE workout for a user.\n"
        "Choose exercises ONLY from the CATALOG below — use their exact \"id\" values. "
        "Do not invent exercises or ids.\n"
        "Respect the user's goal: equipment they have, muscles/areas they want, "
        "duration, and intensity. Pick 4-8 exercises, ordered sensibly.\n\n"
        "Return STRICT JSON, no prose, this exact shape:\n"
        '{"name": "short workout title", "note": "one short sentence", '
        '"exercises": [{"id": "<catalog id>", "sets": 3, "reps": "8-12", "rest_sec": 60}]}\n'
        "reps may be a rep range like \"8-12\" or a time like \"30s\".\n\n"
        f"USER GOAL: {goal}\n\n"
        f"CATALOG (JSON): {json.dumps(catalog)}"
    )


def parse_workout(text, valid_ids):
    """Parse model text -> {name, note, exercises:[{id,sets,reps,rest_sec}]},
    dropping any id not in valid_ids. Raises ValueError if nothing usable."""
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.strip("`")
        if t[:4].lower() == "json":
            t = t[4:]
    # tolerate leading/trailing junk around the JSON object
    i, j = t.find("{"), t.rfind("}")
    if i != -1 and j != -1:
        t = t[i:j + 1]
    data = json.loads(t)
    picks = []
    seen = set()
    for it in data.get("exercises", []):
        eid = it.get("id")
        if eid in valid_ids and eid not in seen:
            seen.add(eid)
            picks.append({
                "id": eid,
                "sets": it.get("sets", 3),
                "reps": str(it.get("reps", "10")),
                "rest_sec": it.get("rest_sec", 60),
            })
    if not picks:
        raise ValueError("Model returned no usable exercises.")
    return {"name": data.get("name", "AI Workout").strip() or "AI Workout",
            "note": (data.get("note") or "").strip(),
            "exercises": picks}


def generate(goal, exercises, api_key, model=DEFAULT_MODEL, timeout=45, retries=2):
    pool = select_relevant(goal, exercises)
    catalog = catalog_for(pool)
    body = {
        "contents": [{"parts": [{"text": build_prompt(goal, catalog)}]}],
        "generationConfig": {"response_mime_type": "application/json", "temperature": 0.7},
    }
    req_data = json.dumps(body).encode("utf-8")
    url = _URL.format(m=model, k=api_key)

    last_err = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(
            url, data=req_data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                resp = json.load(r)
            break
        except urllib.error.HTTPError as ex:
            detail = ex.read().decode("utf-8", "ignore")[:300]
            if ex.code == 429 and attempt < retries:
                last_err = ex
                time.sleep(2 * (attempt + 1))  # brief backoff, then retry once/twice
                continue
            if ex.code == 429:
                raise RuntimeError(
                    "Gemini rate limit hit (429). This is a free-tier requests/tokens-per-minute "
                    "cap, not overall overuse — it resets in under a minute. Wait ~30-60s and try "
                    "again, or check your quota at aistudio.google.com.")
            if ex.code == 404:
                raise RuntimeError(
                    f"Gemini error 404: model \"{model}\" not found — it was likely retired. "
                    f"Google updates DEFAULT_MODEL='gemini-flash-latest' in ai_workout.py "
                    f"automatically hot-swaps to the current stable model, so this shouldn't "
                    f"recur; if it does, check https://ai.google.dev/gemini-api/docs/models "
                    f"for the current model name. Detail: {detail}")
            raise RuntimeError(f"Gemini error {ex.code}: {detail}")
        except urllib.error.URLError as ex:
            raise RuntimeError(f"Network error: {ex.reason}")
    else:
        raise RuntimeError(f"Gemini rate limit hit (429) after {retries} retries: {last_err}")

    try:
        text = resp["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError):
        raise RuntimeError("Unexpected Gemini response (blocked or empty).")
    return parse_workout(text, {e["id"] for e in pool})
