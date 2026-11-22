"""Look and feel for the GUI: colours, fonts and small styled-widget helpers.

Colours are (light mode, dark mode) pairs, which customtkinter switches between
automatically. Change the palette here and the whole interface follows.
"""
from __future__ import annotations

import tkinter.font as tkfont

import customtkinter as ctk

# ---------- palette ----------
BG = ("#F6F7F9", "#14161B")            # window background
SURFACE = ("#FFFFFF", "#1C1F26")       # panels, rows, inputs
SIDEBAR = ("#FFFFFF", "#101216")
HOVER = ("#EEF0F4", "#262A33")         # hover fill and quiet tracks
BORDER = ("#E2E5EB", "#2C313B")
TEXT = ("#171A21", "#ECEEF3")
MUTED = ("#667085", "#98A1B3")

ACCENT = ("#0E7490", "#4FC3E0")
ACCENT_HOVER = ("#0B5C73", "#79D3EA")
ACCENT_SOFT = ("#E1F2F6", "#16303A")   # selected-item background
ON_ACCENT = ("#FFFFFF", "#06222B")     # text drawn on an accent fill

RED = ("#C93B3B", "#FF7A7A")
AMBER = ("#9A6200", "#F2B84B")
GREEN = ("#2F855A", "#5CC48A")
SLATE = ("#8B94A7", "#7A8396")         # low priority

RADIUS_CONTROL = 8
RADIUS_PANEL = 12
CONTROL_HEIGHT = 36

# First installed family wins. Inter gives the cleanest result if the user has it.
SANS_CANDIDATES = ("Inter", "Segoe UI Variable Text", "Segoe UI", "SF Pro Text",
                   "Helvetica Neue", "Noto Sans", "Cantarell", "DejaVu Sans")
MONO_CANDIDATES = ("Cascadia Mono", "Consolas", "SF Mono", "Menlo", "DejaVu Sans Mono", "Courier New")

_families = {"sans": "Roboto", "mono": "Courier"}
_font_cache: dict[tuple, ctk.CTkFont] = {}


def _first_available(candidates: tuple[str, ...], fallback: str) -> str:
    installed = set(tkfont.families())
    return next((name for name in candidates if name in installed), fallback)


def apply_theme() -> None:
    """Patch customtkinter's default theme. Needs a Tk root to exist (it reads installed fonts)."""
    ctk.set_default_color_theme("blue")  # start from a complete theme, then override
    _families["sans"] = _first_available(SANS_CANDIDATES, "Roboto")
    _families["mono"] = _first_available(MONO_CANDIDATES, "Courier")
    _font_cache.clear()

    t = ctk.ThemeManager.theme
    t["CTkFont"].update(family=_families["sans"], size=13)
    t["CTk"].update(fg_color=BG)
    t["CTkLabel"].update(text_color=TEXT)
    t["CTkFrame"].update(fg_color=SURFACE, top_fg_color=SURFACE, border_color=BORDER,
                         corner_radius=RADIUS_PANEL)
    t["CTkButton"].update(corner_radius=RADIUS_CONTROL, fg_color=ACCENT, hover_color=ACCENT_HOVER,
                          text_color=ON_ACCENT, border_color=BORDER)
    t["CTkEntry"].update(corner_radius=RADIUS_CONTROL, border_width=1, fg_color=SURFACE,
                         border_color=BORDER, text_color=TEXT, placeholder_text_color=MUTED)
    t["CTkComboBox"].update(corner_radius=RADIUS_CONTROL, border_width=1, fg_color=SURFACE,
                            border_color=BORDER, button_color=HOVER, button_hover_color=BORDER,
                            text_color=TEXT)
    t["CTkOptionMenu"].update(corner_radius=RADIUS_CONTROL, fg_color=HOVER, button_color=HOVER,
                              button_hover_color=BORDER, text_color=TEXT)
    t["DropdownMenu"].update(fg_color=SURFACE, hover_color=HOVER, text_color=TEXT)
    t["CTkSegmentedButton"].update(corner_radius=RADIUS_CONTROL, border_width=3, fg_color=HOVER,
                                   unselected_color=HOVER, unselected_hover_color=BORDER,
                                   selected_color=SURFACE, selected_hover_color=SURFACE,
                                   text_color=TEXT)
    t["CTkSwitch"].update(fg_color=("#CBD0DA", "#3A404C"), progress_color=ACCENT,
                          button_color=("#FFFFFF", "#ECEEF3"), button_hover_color=("#FFFFFF", "#ECEEF3"),
                          text_color=TEXT)
    t["CTkCheckBox"].update(corner_radius=5, border_width=2, fg_color=ACCENT, hover_color=ACCENT_HOVER,
                            border_color=("#B7BECC", "#4A5160"), checkmark_color=ON_ACCENT, text_color=TEXT)
    t["CTkTextbox"].update(corner_radius=RADIUS_CONTROL, border_width=1, fg_color=SURFACE,
                           border_color=BORDER, text_color=TEXT,
                           scrollbar_button_color=("#C9CED8", "#3A404C"),
                           scrollbar_button_hover_color=("#A9B0BE", "#505867"))
    t["CTkScrollbar"].update(button_color=("#C9CED8", "#3A404C"), button_hover_color=("#A9B0BE", "#505867"))
    t["CTkScrollableFrame"].update(label_fg_color=HOVER)


def font(size: int = 13, weight: str = "normal") -> ctk.CTkFont:
    key = (_families["sans"], size, weight)
    if key not in _font_cache:
        _font_cache[key] = ctk.CTkFont(family=_families["sans"], size=size, weight=weight)
    return _font_cache[key]


def mono(size: int = 13) -> ctk.CTkFont:
    key = (_families["mono"], size, "normal")
    if key not in _font_cache:
        _font_cache[key] = ctk.CTkFont(family=_families["mono"], size=size)
    return _font_cache[key]


# ---------- widget helpers ----------
def label(parent, text: str = "", size: int = 13, weight: str = "normal", color=None, **kw) -> ctk.CTkLabel:
    kw.setdefault("anchor", "w")
    if color is not None:
        kw["text_color"] = color
    return ctk.CTkLabel(parent, text=text, font=font(size, weight), **kw)


def caption(parent, text: str, **kw) -> ctk.CTkLabel:
    return label(parent, text, size=12, color=MUTED, **kw)


def box(parent, **kw) -> ctk.CTkFrame:
    """A frame that sizes to its content. (customtkinter frames default to 200 px tall.)"""
    kw.setdefault("width", 0)
    kw.setdefault("height", 0)
    return ctk.CTkFrame(parent, **kw)


def panel(parent, **kw) -> ctk.CTkFrame:
    kw.setdefault("fg_color", SURFACE)
    return box(parent, border_width=1, border_color=BORDER, corner_radius=RADIUS_PANEL, **kw)


def primary_button(parent, text: str, command=None, **kw) -> ctk.CTkButton:
    kw.setdefault("height", CONTROL_HEIGHT)
    return ctk.CTkButton(parent, text=text, command=command, font=font(13, "bold"), **kw)


def ghost_button(parent, text: str, command=None, accent: bool = False, **kw) -> ctk.CTkButton:
    kw.setdefault("height", CONTROL_HEIGHT)
    return ctk.CTkButton(parent, text=text, command=command, font=font(13), fg_color="transparent",
                         border_width=1, border_color=BORDER, hover_color=HOVER,
                         text_color=ACCENT if accent else TEXT, **kw)


def entry(parent, placeholder: str = "", width: int = 140, **kw) -> ctk.CTkEntry:
    return ctk.CTkEntry(parent, placeholder_text=placeholder, width=width, height=CONTROL_HEIGHT, **kw)


def menu(parent, values: list[str], width: int = 120, **kw) -> ctk.CTkOptionMenu:
    return ctk.CTkOptionMenu(parent, values=values, width=width, height=CONTROL_HEIGHT,
                             dropdown_font=font(13), font=font(13), **kw)
