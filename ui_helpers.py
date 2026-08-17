"""Small stateless UI-building helpers shared across the app."""

import flet as ft


def no_image_placeholder(size):
    return ft.Container(
        ft.Icon(ft.Icons.IMAGE_NOT_SUPPORTED, color=ft.Colors.OUTLINE, size=size * 0.6),
        width=size, height=size, alignment=ft.Alignment.CENTER)


def thumb(e):
    src = e.get("thumbnail") or (e.get("frames") or [None])[0]
    if not src:
        return no_image_placeholder(56)
    return ft.Image(src=src, width=56, height=56, fit=ft.BoxFit.CONTAIN,
                    error_content=ft.Icon(ft.Icons.IMAGE_NOT_SUPPORTED, color=ft.Colors.OUTLINE))
