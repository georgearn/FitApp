"""Pure workout generator (no UI) — testable on its own."""

import random

from data_store import eq_list


def generate_variations(pool, muscle_specs, n=3, seed=None):
    """Return up to n lists of exercises, each drawing exactly
    muscle_specs[muscle]["count"] distinct exercises from that muscle group
    (fewer if the group + its own equipment filter doesn't have enough).
    Variations are made as distinct from each other as the pool allows.

    muscle_specs: {muscle_name: {"count": int, "equipment": set_of_str}}.
    Only groups with count > 0 are included; an empty/falsy equipment set
    means "any equipment" for that group.
    """
    specs = {m: s for m, s in muscle_specs.items() if s.get("count", 0) > 0}
    if not specs:
        return []

    rng = random.Random(seed)
    by_group = {}
    for m, spec in specs.items():
        eqset = set(spec.get("equipment") or [])
        cands = [e for e in pool if e["muscle"] == m
                and (not eqset or (set(eq_list(e)) & eqset))]
        rng.shuffle(cands)
        by_group[m] = cands

    variations = []
    for v in range(n):
        # rotate each muscle's shuffled list by v*take so consecutive
        # variations draw different exercises, then take `count` of them
        picks = []
        for m, spec in specs.items():
            lst = by_group.get(m)
            if not lst:
                continue
            take = min(spec["count"], len(lst))
            start = (v * take) % len(lst)
            rotated = lst[start:] + lst[:start]
            picks.extend(rotated[:take])
        if picks:
            variations.append(picks)
    return variations
