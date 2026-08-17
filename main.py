"""
FitApp (no-AI backup) — mini Freeletics-style workout app (Flet).

This is a stripped copy of fitapp/ with the Gemini "Generate with AI" feature
removed entirely — no network calls, no API key, no ai_workout.py. Everything
else (body map, search, exercise library, rule-based Generate) is identical.

  1. Browse an exercise library, grouped by muscle group, filter by equipment.
  2. Each exercise: 2-frame looping animation + step-by-step description.
  3. GENERATE 2-3 workout variations from your criteria (target muscles /
     available equipment / preset), then save the ones you like.

Library: data/exercises.json, built by tools/build_library.py from the
WorkoutX library staged in assets/img/ (workoutx_library.json +
gifs_webp/<id>.webp). Animated WebPs bundled locally — works offline.
List rows show a static thumbnail (tools/gen_thumbnails.py); the detail
view plays the full animation.

Run:    flet run main.py   |   flet run --web main.py
Build:  flet build apk      (see README.md)
"""

import asyncio
import base64
import os
import random
from datetime import datetime
import flet as ft

from data_store import (
    BASE, EXERCISES, MUSCLES, EQUIPMENT, PRESETS, WORKOUTS_KEY,
    load_workouts, save_workouts, ex_by_id, eq_list, reps_for,
)
from generator import generate_variations
from ui_helpers import no_image_placeholder, thumb

import ai_workout


# ---------------------------------------------------------------------------
# Anatomical front/back body diagram (MuscleWiki-style). Tap a muscle to jump
# to its section in the Exercises list. The art lives in body_data.py (generated
# by tools/gen_body.py); static SVGs are also in assets/body/. body_data uses a
# 724x1448 SVG viewBox — we display it smaller (sized to fit the screen, see
# fit_body_size() in main()) and scale tap coords to match.
# ---------------------------------------------------------------------------
from body_data import VIEWS, body_svg, body_hit, view_size

_fw, _fh = view_size("front")
_BODY_ASPECT = _fh / _fw                        # keep aspect (724x1448 -> ~2:1)
BODY_W_MAX = 300                                # cap for tall/roomy screens

ACCENT = "#28e5ff"        # neon cyan — same accent in light or dark mode
# Everything else uses Flet's theme-aware Colors.* tokens (resolved against
# page.theme/dark_theme below, live-swapped by Flutter itself when
# page.theme_mode is SYSTEM) instead of fixed hex, so the app follows the
# device's light/dark setting rather than being permanently dark.
BG_APP = ft.Colors.SURFACE
CARD_BG = ft.Colors.SURFACE_CONTAINER_HIGH
CARD_BORDER = ft.Colors.OUTLINE_VARIANT


def main(page: ft.Page):
    page.title = "FitApp"
    page.theme_mode = ft.ThemeMode.SYSTEM
    page.theme = ft.Theme(color_scheme_seed=ACCENT)
    page.dark_theme = ft.Theme(color_scheme_seed=ACCENT)
    page.bgcolor = BG_APP
    page.padding = 0
    state = {"equipment": "All"}

    def is_dark_now():
        b = page.platform_brightness
        return b is None or b == ft.Brightness.DARK

    # ---------- exercise detail (animated GIF + description) ----------
    def open_detail(e):
        frames = e.get("frames", [])
        img = (ft.Image(src=frames[0], width=300, height=300, fit=ft.BoxFit.CONTAIN,
                        error_content=ft.Icon(ft.Icons.IMAGE_NOT_SUPPORTED, size=48,
                                              color=ft.Colors.OUTLINE))
               if frames else no_image_placeholder(300))

        steps = e.get("instructions", []) or ["No description available."]
        step_col = ft.Column(
            [ft.Row([ft.Text(f"{i+1}.", weight=ft.FontWeight.BOLD, width=22),
                     ft.Text(s, expand=True)], vertical_alignment=ft.CrossAxisAlignment.START)
             for i, s in enumerate(steps)], spacing=6)
        sec = ", ".join(e.get("muscles_secondary", [])) or "—"
        meta = ft.Text(
            f"Target: {e['muscle']}  ·  Equipment: {', '.join(eq_list(e))}\n"
            f"Also works: {sec}\n"
            f"suggested {reps_for(e)}",
            size=12, color=ft.Colors.ON_SURFACE_VARIANT)
        attribution = ft.Text(e.get("attribution", ""), size=9, color=ft.Colors.OUTLINE)

        def close(_):
            page.pop_dialog()

        group = variant_group_of(e)
        sibling_count = len(group) - 1
        body = [img, attribution, meta]
        if sibling_count > 0:
            body.append(ft.Container(
                ft.Row([ft.Icon(ft.Icons.SWAP_HORIZ, size=15, color=ACCENT),
                        ft.Text(f"{sibling_count} equipment variation{'s' if sibling_count != 1 else ''}",
                                size=12, weight=ft.FontWeight.BOLD, color=ACCENT),
                        ft.Icon(ft.Icons.CHEVRON_RIGHT, size=15, color=ACCENT)],
                       spacing=4, tight=True, alignment=ft.MainAxisAlignment.CENTER),
                on_click=lambda _, x=e: open_variant_picker(x, replace_current=True), ink=True,
                padding=ft.Padding.symmetric(horizontal=10, vertical=7), border_radius=16,
                bgcolor=ft.Colors.with_opacity(0.14, ACCENT)))
        body += [ft.Divider(), ft.Text("How to do it", weight=ft.FontWeight.BOLD), step_col]

        dlg = ft.AlertDialog(
            title=ft.Text(e["name"]),
            content=ft.Container(
                ft.Column(body, tight=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                          scroll=ft.ScrollMode.AUTO),
                width=340, height=560),
            actions=[ft.TextButton("Close", on_click=close)])
        page.show_dialog(dlg)

    # ---------- reusable multi-select equipment picker ----------
    def open_equipment_picker(current, on_apply, title="Equipment"):
        picked = set(current)
        checks = []

        def toggle(q, val):
            if val:
                picked.add(q)
            else:
                picked.discard(q)

        for q in EQUIPMENT:
            checks.append(ft.Checkbox(label=q, value=q in picked,
                                      on_change=lambda ev, x=q: toggle(x, ev.control.value)))

        def cancel(_):
            page.pop_dialog()

        def apply(_):
            on_apply(picked)
            page.pop_dialog()

        def clear(_):
            on_apply(set())
            page.pop_dialog()

        dlg = ft.AlertDialog(
            title=ft.Text(title),
            content=ft.Container(
                ft.Column(checks, spacing=2, tight=True, scroll=ft.ScrollMode.AUTO),
                width=300, height=420),
            actions=[ft.TextButton("Clear", on_click=clear),
                     ft.TextButton("Cancel", on_click=cancel),
                     ft.FilledButton("Apply", on_click=apply)])
        page.show_dialog(dlg)

    # ---------- reusable single-select "pill" filter (matches search-field height exactly —
    # a Material Dropdown's own minimum touch-target size ignores an explicit height) ----------
    def open_single_select(options, current, on_apply, title):
        def pick(v):
            page.pop_dialog()
            on_apply(v)

        rows = [
            ft.Container(
                ft.Text(v, color=ft.Colors.ON_PRIMARY if v == current else ft.Colors.ON_SURFACE),
                on_click=lambda _, x=v: pick(x), padding=10, border_radius=8,
                bgcolor=ft.Colors.PRIMARY if v == current else CARD_BG)
            for v in options
        ]
        dlg = ft.AlertDialog(
            title=ft.Text(title),
            content=ft.Container(ft.Column(rows, spacing=4, tight=True, scroll=ft.ScrollMode.AUTO),
                                 width=260, height=380),
            actions=[ft.TextButton("Cancel", on_click=lambda _: page.pop_dialog())])
        page.show_dialog(dlg)

    def filter_pill(text_ctl, on_click, width=140):
        return ft.Container(
            ft.Row([text_ctl, ft.Icon(ft.Icons.ARROW_DROP_DOWN, size=18,
                                      color=ft.Colors.ON_SURFACE_VARIANT)],
                  alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            on_click=on_click, width=width, height=44,
            padding=ft.Padding.symmetric(horizontal=10), border_radius=6,
            bgcolor=CARD_BG, border=ft.Border.all(1, CARD_BORDER),
            alignment=ft.Alignment.CENTER_LEFT)

    # ---------- reusable multi-select exercise picker (search + muscle filter) ----------
    def open_exercise_picker(current_ids, on_apply, title="Add exercises"):
        picked = list(current_ids)
        filt = {"q": "", "muscle": "All"}
        list_col = ft.ListView(spacing=6, height=320)
        count_txt = ft.Text("", size=12, color=ft.Colors.ON_SURFACE_VARIANT)

        def toggle(eid, val):
            if val and eid not in picked:
                picked.append(eid)
            elif not val and eid in picked:
                picked.remove(eid)
            count_txt.value = f"{len(picked)} selected"
            page.update()

        def matches(e):
            if filt["muscle"] != "All" and e["muscle"] != filt["muscle"]:
                return False
            q = filt["q"]
            if not q:
                return True
            hay = f"{e['name']} {e['muscle']}".lower()
            return q in hay

        def render():
            items = [e for e in EXERCISES if matches(e)]
            list_col.controls = [
                ft.Container(
                    ft.Row([thumb(e),
                            ft.Column([ft.Text(e["name"], size=13, weight=ft.FontWeight.W_500),
                                       ft.Text(f"{e['muscle']} · {', '.join(eq_list(e))}", size=11,
                                               color=ft.Colors.ON_SURFACE_VARIANT)],
                                      spacing=0, expand=True),
                            ft.Checkbox(value=e["id"] in picked,
                                       on_change=lambda ev, x=e["id"]: toggle(x, ev.control.value))],
                           vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    padding=6, border_radius=8, bgcolor=CARD_BG)
                for e in items
            ] or [ft.Text("No exercises match.", size=12, color=ft.Colors.ON_SURFACE_VARIANT)]
            count_txt.value = f"{len(picked)} selected"
            page.update()

        def on_search(ev):
            filt["q"] = (ev.control.value or "").strip().lower()
            render()

        muscle_btn_txt = ft.Text("All", size=13)

        def on_muscle(m):
            filt["muscle"] = m
            muscle_btn_txt.value = m
            render()

        def open_muscle_filter(_):
            open_single_select(["All"] + MUSCLES, filt["muscle"], on_muscle, title="Muscle group")

        search_field = ft.TextField(hint_text="Search exercises…", dense=True, expand=True, height=44,
                                    text_size=13, content_padding=ft.Padding.symmetric(horizontal=10, vertical=10),
                                    prefix_icon=ft.Icons.SEARCH, on_change=on_search)
        muscle_pill = filter_pill(muscle_btn_txt, open_muscle_filter)

        def cancel(_):
            page.pop_dialog()

        def confirm(_):
            page.pop_dialog()
            on_apply(picked)

        render()
        dlg = ft.AlertDialog(
            title=ft.Text(title),
            scrollable=True,
            content=ft.Container(
                ft.Column([ft.Row([search_field, muscle_pill],
                                  vertical_alignment=ft.CrossAxisAlignment.CENTER),
                          count_txt, list_col],
                          spacing=8, tight=True),
                width=360, height=460),
            actions=[ft.TextButton("Cancel", on_click=cancel),
                     ft.FilledButton("Done", on_click=confirm)])
        page.show_dialog(dlg)

    def variant_group_of(e):
        """Full sibling list (including e's own group) for any exercise that's
        part of an equipment-variant group — regardless of whether e itself is
        the primary or one of the variants. Returns [] if e isn't grouped."""
        if e.get("variant_ids"):
            base = e
        elif e.get("variant_of"):
            base = ex_by_id(e["variant_of"])
        else:
            return []
        if not base:
            return []
        ids = [base["id"]] + base.get("variant_ids", [])
        return [x for x in (ex_by_id(i) for i in ids) if x]

    def open_variant_picker(e, replace_current=False):
        """`replace_current=True` when opened from inside another open dialog
        (the detail view's variations chip) — closes that dialog too on pick,
        instead of leaving it stacked underneath the new detail dialog."""
        group = variant_group_of(e)
        if not group:
            return

        def pick(x):
            page.pop_dialog()
            if replace_current:
                page.pop_dialog()
            open_detail(x)

        rows = [ft.Container(
            ft.Row([thumb(x),
                    ft.Column([ft.Text(x["name"], size=13, weight=ft.FontWeight.W_500),
                               ft.Text(", ".join(eq_list(x)), size=11,
                                       color=ft.Colors.ON_SURFACE_VARIANT)], spacing=0, expand=True),
                    ft.Icon(ft.Icons.CHEVRON_RIGHT, size=18, color=ft.Colors.ON_SURFACE_VARIANT)],
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
            on_click=lambda _, x=x: pick(x), ink=True, padding=8, border_radius=10,
            bgcolor=ft.Colors.with_opacity(0.14, ACCENT) if x["id"] == e["id"] else CARD_BG,
            border=ft.Border.all(1, CARD_BORDER))
            for x in group]
        dlg = ft.AlertDialog(
            title=ft.Text("Variations"),
            content=ft.Container(ft.Column(rows, spacing=6, scroll=ft.ScrollMode.AUTO), width=320, height=min(420, 70 * len(group))),
            actions=[ft.TextButton("Close", on_click=lambda _: page.pop_dialog())])
        page.show_dialog(dlg)

    def exercise_row(e):
        group = variant_group_of(e)
        sibling_count = len(group) - 1
        controls = [
            thumb(e),
            ft.Column([ft.Text(e["name"], weight=ft.FontWeight.BOLD),
                       ft.Text(f"{e['muscle']} · {', '.join(eq_list(e))}", size=12,
                               color=ft.Colors.ON_SURFACE_VARIANT)], spacing=2, expand=True),
        ]
        if sibling_count > 0:
            controls.append(ft.Container(
                ft.Row([ft.Icon(ft.Icons.SWAP_HORIZ, size=13, color=ACCENT),
                        ft.Text(f"{sibling_count}", size=11, weight=ft.FontWeight.BOLD, color=ACCENT)],
                       spacing=2, tight=True),
                tooltip=f"{sibling_count} equipment variation{'s' if sibling_count != 1 else ''}",
                on_click=lambda _, x=e: open_variant_picker(x),
                padding=ft.Padding.symmetric(horizontal=8, vertical=5), border_radius=14,
                bgcolor=ft.Colors.with_opacity(0.14, ACCENT)))
        controls.append(ft.Icon(ft.Icons.CHEVRON_RIGHT, color=ft.Colors.ON_SURFACE_VARIANT))
        return ft.Container(
            ft.Row(controls, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            on_click=lambda _, x=e: open_detail(x),
            ink=True, padding=10, border_radius=14, bgcolor=CARD_BG,
            border=ft.Border.all(1, CARD_BORDER))

    # ---------- EXERCISES: Discovery Hub  ->  filtered List ----------
    state["view"] = "front"
    state["focus"] = None
    state["list_title"] = ""
    state["list_src"] = []
    state["list_equip"] = set()

    state["body_w"], state["body_h"] = BODY_W_MAX, int(BODY_W_MAX * _BODY_ASPECT)
    body_img = ft.Image(src="", width=state["body_w"], height=state["body_h"], fit=ft.BoxFit.CONTAIN)

    def fit_body_size():
        # Size the body diagram to whatever's actually left after the search
        # row, front/back switch, hint text, spacing, and the floating bottom
        # nav — so the whole hub screen fits without scrolling instead of the
        # diagram's fixed 300x600 pushing everything else off-screen on
        # shorter devices.
        reserved = 340
        avail_h = max(200, min(BODY_W_MAX * 2, int((page.height or 800) - reserved)))
        return int(avail_h / _BODY_ASPECT), avail_h

    def resize_body(_=None):
        w, h = fit_body_size()
        if (w, h) != (state["body_w"], state["body_h"]):
            state["body_w"], state["body_h"] = w, h
            body_img.width, body_img.height = w, h
            page.update()

    def on_body_tap(e: ft.TapEvent):
        if not e.local_position:
            return
        view = state["view"]
        x0, _y0, vw, vh = [float(t) for t in VIEWS[view]["viewBox"].split()]
        sx = x0 + e.local_position.x * vw / state["body_w"]
        sy = e.local_position.y * vh / state["body_h"]
        label = body_hit(view, sx, sy)
        if label:
            open_muscle(label)

    body_gd = ft.GestureDetector(content=body_img, on_tap_down=on_body_tap)
    page.on_resize = resize_body

    def refresh_body():
        svg_b64 = base64.b64encode(
            body_svg(state["view"], state["focus"], dark=is_dark_now()).encode("utf-8")).decode("ascii")
        body_img.src = f"data:image/svg+xml;base64,{svg_b64}"
        page.update()

    def on_brightness_change(_=None):
        refresh_body()

    page.on_platform_brightness_change = on_brightness_change

    def set_view(ev):
        state["view"] = ev.control.selected.copy().pop()
        state["focus"] = None
        refresh_body()

    view_switch = ft.SegmentedButton(
        selected=["front"], on_change=set_view,
        segments=[ft.Segment(value="front", label="Front"),
                  ft.Segment(value="back", label="Back")])

    search_field = ft.TextField(
        hint_text="Search exercises…", expand=True, dense=True,
        prefix_icon=ft.Icons.SEARCH, border_radius=24,
        on_submit=lambda e: do_search(e.control.value))

    hub_view = ft.Column(
        [ft.Container(ft.Row([search_field]), padding=ft.Padding.symmetric(horizontal=14, vertical=6)),
         ft.Container(view_switch, alignment=ft.Alignment.CENTER),
         ft.Container(body_gd, alignment=ft.Alignment.CENTER, padding=ft.Padding.only(top=6)),
         ft.Container(ft.Text("Tap a muscle to see its exercises", size=12,
                      color=ft.Colors.ON_SURFACE_VARIANT),
                      alignment=ft.Alignment.CENTER, padding=ft.Padding.only(top=4))],
        spacing=4, expand=True, scroll=ft.ScrollMode.AUTO,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER)

    # ----- filtered list screen -----
    # Uses Flet's documented route-based navigation (page.on_route_change +
    # page.go()) rather than direct page.views mutation — a prior attempt
    # at manually pushing/popping page.views produced a blank screen on
    # Android back gesture; this is the canonical pattern instead.
    list_title_txt = ft.Text("", weight=ft.FontWeight.BOLD, size=18, expand=True)
    list_equip_btn_txt = ft.Text("Equipment: any", size=12)
    list_cards = ft.ListView(expand=True, spacing=8,
                             padding=ft.Padding.symmetric(horizontal=12, vertical=6))

    def pop_list_view(_=None):
        page.go("/")

    def apply_list_equip(picked):
        state["list_equip"] = picked
        render_list()

    def open_list_equip_picker(_):
        open_equipment_picker(state["list_equip"], apply_list_equip,
                              title=f"Equipment for {state['list_title']}")

    def render_list():
        eq = state["list_equip"]
        items = [e for e in state["list_src"] if not eq or (set(eq_list(e)) & eq)]
        if not eq:
            # No equipment filter: collapse equipment-variant groups down to
            # their primary exercise (e.g. show "Bench Press" once, not once
            # per barbell/dumbbell/smith-machine version) — the variations
            # chip on that row surfaces the rest. An active equipment filter
            # bypasses this so e.g. filtering to "Cable" still surfaces the
            # cable variant directly, not just the group's default primary.
            items = [e for e in items if e.get("is_primary", True)]
        list_title_txt.value = state["list_title"]
        list_equip_btn_txt.value = ("Equipment: any" if not eq
                                    else f"Equipment: {len(eq)} selected")
        list_cards.controls = ([exercise_row(e) for e in items] or
                               [ft.Container(ft.Text("No exercises for this filter.",
                                             color=ft.Colors.ON_SURFACE_VARIANT), padding=20)])
        page.update()

    list_view = ft.Column(
        [ft.Container(ft.Row([ft.IconButton(ft.Icons.ARROW_BACK, on_click=pop_list_view),
                              list_title_txt]),
                      padding=ft.Padding.only(left=2, right=12, top=6)),
         ft.Container(
             ft.Container(
                 ft.Row([list_equip_btn_txt, ft.Icon(ft.Icons.ARROW_DROP_DOWN, size=18)],
                        tight=True),
                 on_click=open_list_equip_picker, padding=ft.Padding.symmetric(horizontal=13, vertical=7),
                 border_radius=20, bgcolor=CARD_BG, border=ft.Border.all(1, CARD_BORDER)),
             padding=ft.Padding.symmetric(horizontal=12)),
         list_cards],
        expand=True)

    ex_root = ft.Container(hub_view, expand=True)

    def show_hub():
        state["focus"] = None
        ex_root.content = hub_view
        resize_body()
        refresh_body()

    def push_list_view():
        page.go("/list")

    def open_muscle(m):
        state["focus"] = m
        refresh_body()
        state["list_title"] = f"{m} Exercises"
        state["list_src"] = [e for e in EXERCISES if e["muscle"] == m]
        state["list_equip"] = set()
        render_list()
        push_list_view()

    def do_search(q):
        q = (q or "").strip()
        if not q:
            return
        ql = q.lower()

        def hit(e):
            hay = " ".join([e["name"], " ".join(e.get("aliases", [])), e["muscle"],
                            " ".join(e.get("muscles_primary", []))]).lower()
            return ql in hay
        state["list_title"] = f"Results for “{q}”"
        state["list_src"] = [e for e in EXERCISES if hit(e)]
        state["list_equip"] = set()
        render_list()
        push_list_view()

    exercises_tab = ex_root

    # ---------- WORKOUTS TAB ----------
    workouts_view = ft.ListView(expand=True, spacing=10, padding=10)

    async def refresh_workouts():
        wks = await load_workouts(page)
        workouts_view.controls = ([workout_card(w, i) for i, w in enumerate(wks)]
                                  or [ft.Text("No workouts yet. Go to Generate.",
                                              color=ft.Colors.ON_SURFACE_VARIANT)])
        page.update()

    async def delete_workout(idx):
        wks = await load_workouts(page)
        if 0 <= idx < len(wks):
            wks.pop(idx)
            await save_workouts(page, wks)
            await refresh_workouts()

    async def update_workout(idx, name, ids):
        wks = await load_workouts(page)
        if 0 <= idx < len(wks):
            wks[idx]["name"] = name
            wks[idx]["exercises"] = ids
            await save_workouts(page, wks)
            await refresh_workouts()

    def open_edit_workout(idx, w):
        edit_ids = list(w["exercises"])
        name_field = ft.TextField(label="Workout name", value=w["name"], autofocus=True)
        list_box = ft.ListView(spacing=6, height=320)

        def remove_id(eid):
            if eid in edit_ids:
                edit_ids.remove(eid)
            rebuild()

        def rebuild():
            items = [ex_by_id(i) for i in edit_ids]
            items = [e for e in items if e]
            list_box.controls = [
                ft.Row([thumb(e),
                        ft.Column([ft.Text(e["name"], size=13, weight=ft.FontWeight.W_500),
                                   ft.Text(e["muscle"], size=11, color=ft.Colors.ON_SURFACE_VARIANT)],
                                  spacing=0, expand=True),
                        ft.IconButton(ft.Icons.CLOSE, icon_size=18,
                                      on_click=lambda _, x=e["id"]: remove_id(x))],
                       vertical_alignment=ft.CrossAxisAlignment.CENTER)
                for e in items
            ] or [ft.Text("No exercises. Tap “+ Add exercises”.", size=12,
                          color=ft.Colors.ON_SURFACE_VARIANT)]
            page.update()

        def apply_add(ids):
            edit_ids[:] = ids
            rebuild()

        def open_add(_):
            open_exercise_picker(edit_ids, apply_add, title="Add exercises")

        def cancel(_):
            page.pop_dialog()

        def confirm(_):
            page.pop_dialog()
            name = name_field.value.strip() or w["name"]
            page.run_task(update_workout, idx, name, edit_ids)

        rebuild()
        dlg = ft.AlertDialog(
            title=ft.Text("Edit workout"),
            scrollable=True,
            content=ft.Container(
                ft.Column([
                    name_field,
                    ft.Row([ft.Text("Exercises", weight=ft.FontWeight.BOLD, expand=True),
                           ft.TextButton("+ Add exercises", on_click=open_add)]),
                    list_box,
                ], spacing=8, tight=True),
                width=360, height=460),
            actions=[ft.TextButton("Cancel", on_click=cancel),
                     ft.FilledButton("Save", on_click=confirm)])
        page.show_dialog(dlg)

    def format_saved_at(iso):
        if not iso:
            return None
        try:
            return datetime.fromisoformat(iso).strftime("%b %d, %Y · %I:%M %p").replace(" 0", " ")
        except ValueError:
            return None

    def workout_card(w, idx):
        rows = []
        for x in w["exercises"]:
            e = ex_by_id(x)
            if not e:
                continue
            rows.append(ft.Row([thumb(e),
                                ft.Column([ft.Text(e["name"], size=13, weight=ft.FontWeight.W_500),
                                           ft.Text(reps_for(e), size=11,
                                                   color=ft.Colors.ON_SURFACE_VARIANT)],
                                          spacing=0, expand=True),
                                ft.IconButton(ft.Icons.INFO_OUTLINE, icon_size=18,
                                              on_click=lambda _, x=e: open_detail(x))],
                               vertical_alignment=ft.CrossAxisAlignment.CENTER))
        saved_at = format_saved_at(w.get("created_at"))
        meta_line = f"{len(w['exercises'])} exercises"
        if saved_at:
            meta_line += f"  ·  Saved {saved_at}"
        return ft.Container(
            ft.Column([
                ft.Row([ft.Text(w["name"], weight=ft.FontWeight.BOLD, size=16, expand=True),
                        ft.IconButton(ft.Icons.EDIT_OUTLINED,
                                      on_click=lambda _, i=idx, x=w: open_edit_workout(i, x)),
                        ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_color=ft.Colors.ERROR,
                                      on_click=lambda _, i=idx: page.run_task(delete_workout, i))]),
                ft.Text(meta_line, size=12, color=ft.Colors.ON_SURFACE_VARIANT),
                *rows], spacing=6),
            padding=12, border_radius=10, bgcolor=ft.Colors.with_opacity(0.10, ft.Colors.PRIMARY),
            border=ft.Border.all(1, ft.Colors.with_opacity(0.35, ft.Colors.PRIMARY)))

    # ---------- GENERATE TAB ----------
    # Flow: 1) how many variations, 2) which muscle groups, 3) per group: how
    # many exercises + which equipment (defaults to "any" until you pick).
    gen = {"variations": 3, "selected": [], "specs": {}}
    DEFAULT_COUNT = 2
    MAX_COUNT = 8

    muscle_chips_box = ft.Row(wrap=True, spacing=6, run_spacing=6)
    spec_cards_box = ft.Column(spacing=8)
    results = ft.Column(spacing=12)

    def chip(label, selected, on_click):
        return ft.Container(
            ft.Text(label, size=12,
                    color=ft.Colors.ON_PRIMARY if selected else ft.Colors.ON_SURFACE),
            on_click=on_click, padding=ft.Padding.symmetric(horizontal=12, vertical=7),
            border_radius=20,
            bgcolor=ft.Colors.PRIMARY if selected else ft.Colors.SURFACE_CONTAINER_HIGH)

    def rebuild_muscle_chips():
        muscle_chips_box.controls = [
            chip(m, m in gen["selected"], lambda _, x=m: toggle_muscle_select(x)) for m in MUSCLES]
        page.update()

    def toggle_muscle_select(m):
        if m in gen["selected"]:
            gen["selected"].remove(m)
            gen["specs"].pop(m, None)
        else:
            gen["selected"].append(m)
            gen["specs"][m] = {"count": DEFAULT_COUNT, "equipment": set()}
        rebuild_muscle_chips()
        rebuild_spec_cards()

    def remove_muscle(m):
        if m in gen["selected"]:
            gen["selected"].remove(m)
        gen["specs"].pop(m, None)
        rebuild_muscle_chips()
        rebuild_spec_cards()

    def set_spec_count(m, delta):
        spec = gen["specs"][m]
        spec["count"] = max(1, min(MAX_COUNT, spec["count"] + delta))
        rebuild_spec_cards()

    def apply_spec_equip(m, picked):
        if m in gen["specs"]:
            gen["specs"][m]["equipment"] = picked
        rebuild_spec_cards()

    def open_spec_equip(m):
        open_equipment_picker(gen["specs"][m]["equipment"],
                              lambda picked: apply_spec_equip(m, picked),
                              title=f"Equipment for {m}")

    def spec_card(m):
        spec = gen["specs"][m]
        eqn = len(spec["equipment"])
        eq_label = "Equipment: any" if eqn == 0 else f"Equipment: {eqn} selected"
        return ft.Container(
            ft.Column([
                ft.Row([ft.Text(m, weight=ft.FontWeight.BOLD, expand=True),
                        ft.IconButton(ft.Icons.CLOSE, icon_size=18,
                                      on_click=lambda _, x=m: remove_muscle(x))]),
                ft.Row([
                    ft.Text("Exercises:", size=12, color=ft.Colors.ON_SURFACE_VARIANT),
                    ft.IconButton(ft.Icons.REMOVE_CIRCLE_OUTLINE, icon_size=18,
                                  disabled=spec["count"] <= 1,
                                  on_click=lambda _, x=m: set_spec_count(x, -1)),
                    ft.Text(str(spec["count"]), weight=ft.FontWeight.BOLD),
                    ft.IconButton(ft.Icons.ADD_CIRCLE_OUTLINE, icon_size=18,
                                  disabled=spec["count"] >= MAX_COUNT,
                                  on_click=lambda _, x=m: set_spec_count(x, 1)),
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Container(
                    ft.Row([ft.Text(eq_label, size=12),
                           ft.Icon(ft.Icons.ARROW_DROP_DOWN, size=16)], tight=True),
                    on_click=lambda _, x=m: open_spec_equip(x),
                    padding=ft.Padding.symmetric(horizontal=10, vertical=5), border_radius=16,
                    bgcolor=CARD_BG, border=ft.Border.all(1, CARD_BORDER)),
            ], spacing=6),
            padding=10, border_radius=10, bgcolor=ft.Colors.with_opacity(0.08, ft.Colors.PRIMARY),
            border=ft.Border.all(1, ft.Colors.with_opacity(0.3, ft.Colors.PRIMARY)))

    def rebuild_spec_cards():
        spec_cards_box.controls = [spec_card(m) for m in gen["selected"]] or [
            ft.Text("Pick muscle groups above to configure them.", size=12,
                    color=ft.Colors.ON_SURFACE_VARIANT)]
        page.update()

    def apply_preset(ev):
        name = ev.control.value
        if name in PRESETS:
            gen["selected"] = list(PRESETS[name])
            gen["specs"] = {m: {"count": DEFAULT_COUNT, "equipment": set()} for m in gen["selected"]}
            rebuild_muscle_chips()
            rebuild_spec_cards()

    def set_variations(ev):
        gen["variations"] = int(ev.control.value)

    async def save_variation(picks, label):
        wks = await load_workouts(page)
        wks.append({"name": label, "created_at": datetime.now().isoformat(),
                    "exercises": [e["id"] for e in picks],
                    "meta": {m: {"count": s["count"], "equipment": sorted(s["equipment"])}
                             for m, s in gen["specs"].items()}})
        await save_workouts(page, wks)
        page.show_dialog(ft.SnackBar(ft.Text(f'Saved "{label}"')))
        await refresh_workouts()

    def open_save_dialog(picks, default_label):
        name_field = ft.TextField(label="Workout name", value=default_label, autofocus=True)

        def cancel(_):
            page.pop_dialog()

        def confirm(_):
            page.pop_dialog()
            label = name_field.value.strip() or default_label
            page.run_task(save_variation, picks, label)

        dlg = ft.AlertDialog(
            title=ft.Text("Save workout"),
            content=ft.Container(name_field, width=300),
            actions=[ft.TextButton("Cancel", on_click=cancel),
                     ft.FilledButton("Save", on_click=confirm)],
            on_dismiss=cancel)
        page.show_dialog(dlg)

    def variation_card(picks, num):
        msel = ", ".join(f"{m} × {s['count']}" for m, s in gen["specs"].items())
        label = f"Variation {num} — {msel}"
        rows = [ft.Row([thumb(e),
                        ft.Column([ft.Text(e["name"], size=13, weight=ft.FontWeight.W_500),
                                   ft.Text(f"{e['muscle']} · {reps_for(e)}", size=11,
                                           color=ft.Colors.ON_SURFACE_VARIANT)], spacing=0, expand=True),
                        ft.IconButton(ft.Icons.INFO_OUTLINE, icon_size=18,
                                      on_click=lambda _, x=e: open_detail(x))],
                       vertical_alignment=ft.CrossAxisAlignment.CENTER) for e in picks]
        return ft.Container(
            ft.Column([
                ft.Text(f"Variation {num}", weight=ft.FontWeight.BOLD, size=16),
                ft.Text(f"{len(picks)} exercises", size=11, color=ft.Colors.ON_SURFACE_VARIANT),
                *rows,
                ft.FilledButton("Save this", icon=ft.Icons.SAVE,
                                on_click=lambda _, p=picks, l=label: open_save_dialog(p, l))],
                spacing=6),
            padding=12, border_radius=10, bgcolor=ft.Colors.with_opacity(0.10, ft.Colors.TERTIARY),
            border=ft.Border.all(1, ft.Colors.with_opacity(0.35, ft.Colors.TERTIARY)))

    def do_generate(_=None, seed=None):
        variations = generate_variations(EXERCISES, gen["specs"], n=gen["variations"], seed=seed)
        if not variations:
            results.controls = [ft.Text(
                "Pick at least one muscle group and check its equipment filter "
                "isn't excluding everything available.", color=ft.Colors.ERROR)]
        else:
            results.controls = [variation_card(v, i + 1) for i, v in enumerate(variations)]
        page.update()

    preset_dd = ft.Dropdown(label="Preset", on_select=apply_preset, expand=True,
                            options=[ft.DropdownOption(p) for p in PRESETS])
    variations_dd = ft.Dropdown(label="Variations", value="3", on_select=set_variations, width=120,
                                options=[ft.DropdownOption(x) for x in ["1", "2", "3", "4", "5"]])

    def reset_generator(_=None):
        gen["selected"] = []
        gen["specs"] = {}
        gen["variations"] = 3
        preset_dd.value = None
        variations_dd.value = "3"
        results.controls = []
        rebuild_muscle_chips()
        rebuild_spec_cards()
        page.update()

    auto_section = ft.Column([
        ft.Container(ft.Row([preset_dd, variations_dd,
                             ft.IconButton(ft.Icons.RESTART_ALT, tooltip="Reset",
                                          on_click=reset_generator)]), padding=10),
        ft.Container(ft.Text("1. Muscle groups", weight=ft.FontWeight.BOLD, size=13),
                     padding=ft.Padding.only(left=14, top=6)),
        ft.Container(muscle_chips_box, padding=ft.Padding.symmetric(horizontal=12)),
        ft.Container(ft.Text("2. Exercises & equipment per group",
                     weight=ft.FontWeight.BOLD, size=13),
                     padding=ft.Padding.only(left=14, top=6)),
        ft.Container(spec_cards_box, padding=ft.Padding.symmetric(horizontal=12)),
        ft.Container(ft.Row([
            ft.FilledButton("Generate", icon=ft.Icons.AUTO_AWESOME,
                            on_click=lambda _: do_generate(seed=None), expand=True),
            ft.OutlinedButton("Shuffle", icon=ft.Icons.REFRESH,
                              on_click=lambda _: do_generate(seed=random.randint(1, 99999))),
        ]), padding=ft.Padding.only(left=10, right=10, top=6)),
        ft.Divider(),
        ft.Container(results, padding=ft.Padding.symmetric(horizontal=10)),
    ], expand=True, scroll=ft.ScrollMode.AUTO)

    # ---------- manual generator: hand-pick exercises into a workout ----------
    manual_picks = []
    manual_list_box = ft.Column(spacing=8)

    def manual_row(e):
        return ft.Row([thumb(e),
                       ft.Column([ft.Text(e["name"], size=13, weight=ft.FontWeight.W_500),
                                  ft.Text(f"{e['muscle']} · {reps_for(e)}", size=11,
                                          color=ft.Colors.ON_SURFACE_VARIANT)], spacing=0, expand=True),
                       ft.IconButton(ft.Icons.CLOSE, icon_size=18,
                                     on_click=lambda _, x=e["id"]: remove_manual_pick(x))],
                      vertical_alignment=ft.CrossAxisAlignment.CENTER)

    def rebuild_manual_list():
        items = [ex_by_id(i) for i in manual_picks]
        items = [e for e in items if e]
        manual_list_box.controls = [manual_row(e) for e in items] or [
            ft.Text("No exercises yet. Tap “+ Add exercises”.", size=12,
                    color=ft.Colors.ON_SURFACE_VARIANT)]
        page.update()

    def remove_manual_pick(eid):
        if eid in manual_picks:
            manual_picks.remove(eid)
        rebuild_manual_list()

    def apply_manual_picks(ids):
        manual_picks[:] = ids
        rebuild_manual_list()

    def open_manual_picker(_=None):
        open_exercise_picker(manual_picks, apply_manual_picks, title="Add exercises")

    def save_manual(_):
        items = [ex_by_id(i) for i in manual_picks]
        items = [e for e in items if e]
        if not items:
            page.show_dialog(ft.SnackBar(ft.Text("Add at least one exercise first.")))
            return
        open_save_dialog(items, "Custom workout")

    def reset_manual(_=None):
        manual_picks.clear()
        rebuild_manual_list()

    manual_section = ft.Column([
        ft.Container(ft.Row([
            ft.FilledButton("+ Add exercises", icon=ft.Icons.ADD, on_click=open_manual_picker, expand=True),
            ft.IconButton(ft.Icons.RESTART_ALT, tooltip="Clear", on_click=reset_manual),
        ]), padding=10),
        ft.Container(manual_list_box, padding=ft.Padding.symmetric(horizontal=12)),
        ft.Container(ft.FilledButton("Save workout", icon=ft.Icons.SAVE, on_click=save_manual, expand=True),
                     padding=ft.Padding.only(left=10, right=10, top=10)),
    ], expand=True, scroll=ft.ScrollMode.AUTO)

    # ---------- AI generator: Google Gemini, constrained to our library ----------
    ai_results = ft.Column(spacing=12)

    async def save_ai_workout(w):
        wks = await load_workouts(page)
        wks.append({"name": w["name"], "created_at": datetime.now().isoformat(),
                    "exercises": [it["id"] for it in w["exercises"]],
                    "plan": w["exercises"], "meta": {"ai": True, "note": w.get("note", "")}})
        await save_workouts(page, wks)
        page.show_dialog(ft.SnackBar(ft.Text(f'Saved "{w["name"]}"')))
        await refresh_workouts()

    def ai_result_card(w):
        rows = []
        for it in w["exercises"]:
            e = ex_by_id(it["id"])
            if not e:
                continue
            rows.append(ft.Row(
                [thumb(e),
                 ft.Column([ft.Text(e["name"], size=13, weight=ft.FontWeight.W_500),
                            ft.Text(f"{e['muscle']} · {it['sets']}×{it['reps']} · "
                                    f"rest {it['rest_sec']}s", size=11,
                                    color=ft.Colors.ON_SURFACE_VARIANT)], spacing=0, expand=True),
                 ft.IconButton(ft.Icons.INFO_OUTLINE, icon_size=18,
                               on_click=lambda _, x=e: open_detail(x))],
                vertical_alignment=ft.CrossAxisAlignment.CENTER))
        return ft.Container(
            ft.Column([
                ft.Row([ft.Icon(ft.Icons.AUTO_AWESOME, color=ACCENT, size=18),
                        ft.Text(w["name"], weight=ft.FontWeight.BOLD, size=16, expand=True)]),
                ft.Text(w.get("note", ""), size=11, color=ft.Colors.ON_SURFACE_VARIANT),
                *rows,
                ft.FilledButton("Save workout", icon=ft.Icons.SAVE,
                                on_click=lambda _, x=w: page.run_task(save_ai_workout, x))],
                spacing=6),
            padding=12, border_radius=10, bgcolor=ft.Colors.with_opacity(0.10, ACCENT),
            border=ft.Border.all(1, ft.Colors.with_opacity(0.5, ACCENT)))

    goal_field = ft.TextField(
        label="What do you want to achieve?", multiline=True, min_lines=2, max_lines=4,
        hint_text="e.g. 35-min upper-body pump, dumbbells + bands, hypertrophy")
    key_field = ft.TextField(label="Google Gemini API key", password=True, can_reveal_password=True)
    ai_status = ft.Text("", size=12, color=ft.Colors.ON_SURFACE_VARIANT)
    ai_build_btn = ft.FilledButton("Build workout with AI", icon=ft.Icons.AUTO_AWESOME)

    async def _prefill_key():
        k = await page.shared_preferences.get("gemini_key")
        if k:
            key_field.value = k
            page.update()

    async def _run_ai(_):
        goal = (goal_field.value or "").strip()
        key = (key_field.value or "").strip()
        if not goal or not key:
            ai_status.value = "Enter a goal and your API key."
            page.update()
            return
        await page.shared_preferences.set("gemini_key", key)
        ai_status.value = "Thinking… building your workout"
        ai_build_btn.disabled = True
        page.update()
        try:
            w = await asyncio.to_thread(ai_workout.generate, goal, EXERCISES, key)
        except Exception as ex:
            ai_status.value = f"Failed: {ex}"
            ai_build_btn.disabled = False
            page.update()
            return
        ai_status.value = ""
        ai_build_btn.disabled = False
        ai_results.controls.insert(0, ai_result_card(w))
        page.update()

    ai_build_btn.on_click = lambda e: page.run_task(_run_ai, e)
    page.run_task(_prefill_key)

    ai_section = ft.Column([
        ft.Container(ft.Column([
            goal_field, key_field,
            ft.Text("Free key: aistudio.google.com/apikey", size=10, color=ft.Colors.OUTLINE),
            ai_status, ai_build_btn], spacing=10), padding=10),
        ft.Divider(),
        ft.Container(ai_results, padding=ft.Padding.symmetric(horizontal=10)),
    ], expand=True, scroll=ft.ScrollMode.AUTO)

    gen_body_area = ft.Container(auto_section, expand=True)

    def set_gen_mode(ev):
        mode = ev.control.selected.copy().pop()
        gen_body_area.content = {"auto": auto_section, "ai": ai_section,
                                 "manual": manual_section}[mode]
        page.update()

    def _seg_label(text):
        return ft.Container(ft.Text(text, size=13, text_align=ft.TextAlign.CENTER),
                            width=54, alignment=ft.Alignment.CENTER)

    gen_mode_switch = ft.SegmentedButton(
        selected=["auto"], on_change=set_gen_mode, width=300,
        show_selected_icon=False,
        segments=[ft.Segment(value="auto", label=_seg_label("Auto")),
                  ft.Segment(value="ai", label=_seg_label("AI")),
                  ft.Segment(value="manual", label=_seg_label("Manual"))])

    generate_tab = ft.Column([
        ft.Container(gen_mode_switch, padding=ft.Padding.only(left=10, top=10)),
        gen_body_area,
    ], expand=True)

    # ---------- floating tab bar (not full-width) ----------
    body = ft.Container(exercises_tab, expand=True)
    state["tab"] = 0
    NAV = [("Body", ft.Icons.ACCESSIBILITY_NEW),
           ("Workouts", ft.Icons.LIST_ALT),
           ("Generate", ft.Icons.AUTO_AWESOME)]
    nav_row = ft.Row(spacing=10, alignment=ft.MainAxisAlignment.CENTER, tight=True)

    def render_nav():
        cells = []
        for i, (lbl, ic) in enumerate(NAV):
            active = state["tab"] == i
            col = ACCENT if active else ft.Colors.ON_SURFACE_VARIANT
            cells.append(ft.Container(
                ft.Column([ft.Icon(ic, size=26, color=col),
                           ft.Text(lbl, size=11, color=col)],
                          spacing=3, tight=True,
                          horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                on_click=lambda _, x=i: switch_to(x),
                padding=ft.Padding.symmetric(horizontal=28, vertical=10), border_radius=24,
                bgcolor=ft.Colors.with_opacity(0.14, ACCENT) if active else None))
        nav_row.controls = cells

    def switch_to(index):
        state["tab"] = index
        if index == 0:
            show_hub(); body.content = exercises_tab
        elif index == 1:
            body.content = workouts_view
            page.run_task(refresh_workouts)
        else:
            rebuild_muscle_chips(); rebuild_spec_cards(); body.content = generate_tab
        render_nav()
        page.update()

    render_nav()
    # Theme-aware pill background: a translucent tint of the *current* surface
    # color (dark surface in dark mode, light surface in light mode) rather
    # than a hardcoded dark hex — otherwise the nav stayed dark in light mode.
    nav_pill = ft.Container(
        nav_row, padding=ft.Padding.symmetric(horizontal=16, vertical=8), border_radius=38,
        bgcolor=ft.Colors.with_opacity(0.90, ft.Colors.SURFACE_CONTAINER_HIGH),
        border=ft.Border.all(1, ft.Colors.with_opacity(0.45, ACCENT)),
        shadow=ft.BoxShadow(blur_radius=28, spread_radius=1,
                            color=ft.Colors.with_opacity(0.25, ft.Colors.SHADOW)))
    # Positioned directly in the Stack (left/right/bottom), NOT wrapped in an
    # expand=True Container — that would cover (and intercept taps on) the
    # entire screen, since Flet Containers absorb pointer events by default
    # even with no on_click of their own (see Container.ignore_interactions).
    floating_nav = ft.Row([nav_pill], alignment=ft.MainAxisAlignment.CENTER,
                          left=0, right=0, bottom=22)

    content = ft.SafeArea(
        ft.Container(body, padding=ft.Padding.only(bottom=96), expand=True), expand=True)
    root_stack = ft.Stack([content, floating_nav], expand=True)

    def route_change(_):
        page.views.clear()
        page.views.append(ft.View(route="/", controls=[root_stack], padding=0, bgcolor=BG_APP))
        if page.route == "/list":
            page.views.append(ft.View(route="/list", controls=[ft.SafeArea(list_view, expand=True)],
                                      padding=0, bgcolor=BG_APP))
        page.update()

    def view_pop(e: ft.ViewPopEvent):
        # on_view_pop also fires when the exercise-detail dialog is dismissed
        # via back gesture (not just our page.views routes). e.view is only
        # set when the event genuinely matches an entry in page.views, so
        # this ignores dialog dismisses instead of also popping the
        # exercise-list route underneath the dialog in the same back-press.
        if e.view is None or len(page.views) < 2:
            return
        page.views.pop()
        page.go(page.views[-1].route)

    page.on_route_change = route_change
    page.on_view_pop = view_pop
    show_hub()

    # ---------- splash screen (gym.jpg, shown briefly on launch) ----------
    splash_view = ft.View(
        route="/",
        padding=0,
        bgcolor="#171B24",
        controls=[ft.Container(
            ft.Image(src="gym.jpg", fit=ft.BoxFit.CONTAIN, expand=True),
            alignment=ft.Alignment.CENTER, expand=True)])

    async def show_splash_then_app():
        page.views.append(splash_view)
        page.update()
        await asyncio.sleep(1.5)
        # Call route_change directly rather than page.go("/") — if page.route
        # already defaults to "/", page.go() is a same-route no-op that never
        # fires on_route_change, leaving page.views at its untouched empty
        # default (blank screen on launch).
        route_change(None)
        # show_hub()'s very first resize_body() call (line ~1003, before this
        # splash even started) can land before the platform reports real
        # page.height, sizing the body diagram off a fallback guess. Real
        # dimensions are always settled by now — resize for real once the
        # splash hands off to the actual UI, so the hub screen fits without
        # scrolling instead of being sized for a guess.
        resize_body()

    page.run_task(show_splash_then_app)


if __name__ == "__main__":
    ft.run(main, assets_dir="assets")
