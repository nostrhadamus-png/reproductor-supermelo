"""Sistema de apariencia: paletas, validación y generación de CSS.

Este módulo no importa GTK: toda la lógica (datos, contraste y CSS) es pura y
se puede probar sin pantalla. La interfaz solo llama a estas funciones.
"""

from __future__ import annotations

import re

SCHEMES = ("system", "light", "dark")
SCHEME_LABELS = {
    "system": "Sistema",
    "light": "Claro",
    "dark": "Oscuro",
}

DEFAULT_SCHEME = "system"
DEFAULT_PALETTE = "default"

PALETTE_ORDER = (
    "default",
    "ocean",
    "forest",
    "atardecer",
    "orquidea",
    "medianoche",
)

COLOR_TOKENS = (
    "window_bg_color",
    "window_fg_color",
    "view_bg_color",
    "view_fg_color",
    "headerbar_bg_color",
    "headerbar_fg_color",
    "card_bg_color",
    "card_fg_color",
    "accent_bg_color",
    "accent_fg_color",
    "accent_color",
)

CONTRAST_PAIRS = (
    ("window_fg_color", "window_bg_color"),
    ("view_fg_color", "view_bg_color"),
    ("headerbar_fg_color", "headerbar_bg_color"),
    ("card_fg_color", "card_bg_color"),
    ("accent_fg_color", "accent_bg_color"),
)

MIN_CONTRAST = 4.5

# Colores de referencia de Adwaita. No se emiten para la paleta
# "Predeterminada" (esa sigue al sistema); se usan para comprobar contraste.
DEFAULT_REFERENCE = {
    "light": {
        "window_bg_color": "#fafafa",
        "window_fg_color": "#2e3436",
        "view_bg_color": "#ffffff",
        "view_fg_color": "#2e3436",
        "headerbar_bg_color": "#ebebeb",
        "headerbar_fg_color": "#2e3436",
        "card_bg_color": "#ffffff",
        "card_fg_color": "#2e3436",
    },
    "dark": {
        "window_bg_color": "#242424",
        "window_fg_color": "#ffffff",
        "view_bg_color": "#1e1e1e",
        "view_fg_color": "#ffffff",
        "headerbar_bg_color": "#303030",
        "headerbar_fg_color": "#ffffff",
        "card_bg_color": "#303030",
        "card_fg_color": "#ffffff",
    },
}

SYSTEM_ACCENTS = (
    "#3584e4",
    "#2190a4",
    "#3a944a",
    "#e5a50a",
    "#c64600",
    "#ed5b00",
    "#e01b24",
    "#c061cb",
    "#9141ac",
    "#6f8396",
)

PALETTES = {
    "default": {
        "label": "Predeterminada",
        "light": None,
        "dark": None,
    },
    "ocean": {
        "label": "Océano",
        "light": {
            "window_bg_color": "#f3f7fb",
            "window_fg_color": "#142033",
            "view_bg_color": "#ffffff",
            "view_fg_color": "#142033",
            "headerbar_bg_color": "#e3edf7",
            "headerbar_fg_color": "#142033",
            "card_bg_color": "#ffffff",
            "card_fg_color": "#142033",
            "accent_bg_color": "#0b5cad",
            "accent_fg_color": "#ffffff",
            "accent_color": "#0b5cad",
        },
        "dark": {
            "window_bg_color": "#101b2a",
            "window_fg_color": "#eaf2fb",
            "view_bg_color": "#0b1420",
            "view_fg_color": "#eaf2fb",
            "headerbar_bg_color": "#17263a",
            "headerbar_fg_color": "#eaf2fb",
            "card_bg_color": "#17263a",
            "card_fg_color": "#eaf2fb",
            "accent_bg_color": "#59b6ff",
            "accent_fg_color": "#06131f",
            "accent_color": "#7cc7ff",
        },
    },
    "forest": {
        "label": "Bosque",
        "light": {
            "window_bg_color": "#f3f8f2",
            "window_fg_color": "#142114",
            "view_bg_color": "#ffffff",
            "view_fg_color": "#142114",
            "headerbar_bg_color": "#e2efe1",
            "headerbar_fg_color": "#142114",
            "card_bg_color": "#ffffff",
            "card_fg_color": "#142114",
            "accent_bg_color": "#166b32",
            "accent_fg_color": "#ffffff",
            "accent_color": "#166b32",
        },
        "dark": {
            "window_bg_color": "#0f1a12",
            "window_fg_color": "#e8f4e9",
            "view_bg_color": "#0a130d",
            "view_fg_color": "#e8f4e9",
            "headerbar_bg_color": "#17271c",
            "headerbar_fg_color": "#e8f4e9",
            "card_bg_color": "#17271c",
            "card_fg_color": "#e8f4e9",
            "accent_bg_color": "#63d98a",
            "accent_fg_color": "#06150b",
            "accent_color": "#82e6a4",
        },
    },
    "atardecer": {
        "label": "Atardecer",
        "light": {
            "window_bg_color": "#fdf5f0",
            "window_fg_color": "#2a1611",
            "view_bg_color": "#ffffff",
            "view_fg_color": "#2a1611",
            "headerbar_bg_color": "#f8e6da",
            "headerbar_fg_color": "#2a1611",
            "card_bg_color": "#ffffff",
            "card_fg_color": "#2a1611",
            "accent_bg_color": "#a63a12",
            "accent_fg_color": "#ffffff",
            "accent_color": "#a63a12",
        },
        "dark": {
            "window_bg_color": "#1e130f",
            "window_fg_color": "#fbece5",
            "view_bg_color": "#170e0b",
            "view_fg_color": "#fbece5",
            "headerbar_bg_color": "#2a1a14",
            "headerbar_fg_color": "#fbece5",
            "card_bg_color": "#2a1a14",
            "card_fg_color": "#fbece5",
            "accent_bg_color": "#ff9c63",
            "accent_fg_color": "#241006",
            "accent_color": "#ffb489",
        },
    },
    "orquidea": {
        "label": "Orquídea",
        "light": {
            "window_bg_color": "#f9f4fc",
            "window_fg_color": "#21142b",
            "view_bg_color": "#ffffff",
            "view_fg_color": "#21142b",
            "headerbar_bg_color": "#efe2f8",
            "headerbar_fg_color": "#21142b",
            "card_bg_color": "#ffffff",
            "card_fg_color": "#21142b",
            "accent_bg_color": "#5e2a8c",
            "accent_fg_color": "#ffffff",
            "accent_color": "#5e2a8c",
        },
        "dark": {
            "window_bg_color": "#1b1224",
            "window_fg_color": "#f2eafa",
            "view_bg_color": "#140d1b",
            "view_fg_color": "#f2eafa",
            "headerbar_bg_color": "#251832",
            "headerbar_fg_color": "#f2eafa",
            "card_bg_color": "#251832",
            "card_fg_color": "#f2eafa",
            "accent_bg_color": "#d29bff",
            "accent_fg_color": "#1c0b2b",
            "accent_color": "#e0b8ff",
        },
    },
    "medianoche": {
        "label": "Medianoche",
        "light": {
            "window_bg_color": "#f2f6f8",
            "window_fg_color": "#102026",
            "view_bg_color": "#ffffff",
            "view_fg_color": "#102026",
            "headerbar_bg_color": "#e1eaee",
            "headerbar_fg_color": "#102026",
            "card_bg_color": "#ffffff",
            "card_fg_color": "#102026",
            "accent_bg_color": "#00697a",
            "accent_fg_color": "#ffffff",
            "accent_color": "#00697a",
        },
        "dark": {
            "window_bg_color": "#0b1418",
            "window_fg_color": "#e6f4f7",
            "view_bg_color": "#070f12",
            "view_fg_color": "#e6f4f7",
            "headerbar_bg_color": "#101e24",
            "headerbar_fg_color": "#e6f4f7",
            "card_bg_color": "#101e24",
            "card_fg_color": "#e6f4f7",
            "accent_bg_color": "#4fd8e8",
            "accent_fg_color": "#04171a",
            "accent_color": "#7ce7f2",
        },
    },
}

_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def validate_scheme(value) -> str:
    if isinstance(value, str) and value in SCHEMES:
        return value
    return DEFAULT_SCHEME


def validate_palette(value) -> str:
    if isinstance(value, str) and value in PALETTES:
        return value
    return DEFAULT_PALETTE


def valid_hex(value) -> bool:
    return isinstance(value, str) and bool(_HEX_RE.match(value))


def _rgb(value: str) -> tuple[float, float, float]:
    if not valid_hex(value):
        raise ValueError(f"color no válido: {value!r}")
    return tuple(int(value[i : i + 2], 16) / 255.0 for i in (1, 3, 5))


def relative_luminance(value: str) -> float:
    canales = []
    for canal in _rgb(value):
        if canal <= 0.04045:
            canales.append(canal / 12.92)
        else:
            canales.append(((canal + 0.055) / 1.055) ** 2.4)
    r, g, b = canales
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(foreground: str, background: str) -> float:
    alto, bajo = sorted(
        (relative_luminance(foreground), relative_luminance(background)),
        reverse=True,
    )
    return (alto + 0.05) / (bajo + 0.05)


def best_foreground(background: str) -> str:
    """Blanco o negro, el que más contraste tenga sobre ``background``."""
    if not valid_hex(background):
        return "#ffffff"
    return max(("#ffffff", "#000000"), key=lambda color: contrast_ratio(color, background))


def effective_scheme(scheme: str, system_dark: bool) -> str:
    elegido = validate_scheme(scheme)
    if elegido == "system":
        return "dark" if system_dark else "light"
    return elegido


def palette_tokens(
    palette: str,
    scheme: str,
    system_accent: str | None = None,
    system_dark: bool = False,
) -> dict:
    """Tokens que la app debe emitir por CSS para la paleta elegida.

    "Predeterminada" no redefine fondos ni acento: sigue al sistema. Solo
    ajusta ``accent_fg_color`` al color de texto con más contraste sobre el
    acento real, para cumplir AA también con acentos del escritorio.
    """
    paleta = validate_palette(palette)
    variante = effective_scheme(scheme, system_dark)
    if paleta == DEFAULT_PALETTE:
        if valid_hex(system_accent):
            return {"accent_fg_color": best_foreground(system_accent)}
        return {}
    return dict(PALETTES[paleta][variante])


def palette_preview(
    palette: str,
    scheme: str,
    system_accent: str | None = None,
    system_dark: bool = False,
) -> tuple[str, str, str]:
    """Devuelve (fondo, texto, acento) para la muestra de la paleta."""
    paleta = validate_palette(palette)
    variante = effective_scheme(scheme, system_dark)
    if paleta == DEFAULT_PALETTE:
        base = DEFAULT_REFERENCE[variante]
        acento = system_accent if valid_hex(system_accent) else "#3584e4"
        return base["window_bg_color"], base["window_fg_color"], acento
    tokens = PALETTES[paleta][variante]
    return (
        tokens["window_bg_color"],
        tokens["window_fg_color"],
        tokens["accent_bg_color"],
    )


def generate_css(
    palette: str,
    scheme: str,
    system_accent: str | None = None,
    system_dark: bool = False,
) -> str:
    tokens = palette_tokens(palette, scheme, system_accent, system_dark)
    lineas = ["/* Apariencia generada por reproductor.theme */"]
    for token in COLOR_TOKENS:
        if token in tokens:
            lineas.append(f"@define-color {token} {tokens[token]};")
    return "\n".join(lineas) + "\n"


def contrast_problems() -> list[tuple[str, str, str, float]]:
    """Recorre todas las paletas y variantes; devuelve las que no llegan a AA."""
    fallos = []
    for paleta, datos in PALETTES.items():
        for variante in ("light", "dark"):
            if paleta == DEFAULT_PALETTE:
                tokens = dict(DEFAULT_REFERENCE[variante])
                for acento in SYSTEM_ACCENTS:
                    tokens["accent_bg_color"] = acento
                    tokens["accent_fg_color"] = best_foreground(acento)
                    tokens["accent_color"] = acento
                    for fg, bg in CONTRAST_PAIRS:
                        valor = contrast_ratio(tokens[fg], tokens[bg])
                        if valor < MIN_CONTRAST:
                            fallos.append((paleta, variante, f"{fg}/{bg}", valor))
            else:
                tokens = datos[variante]
                for fg, bg in CONTRAST_PAIRS:
                    valor = contrast_ratio(tokens[fg], tokens[bg])
                    if valor < MIN_CONTRAST:
                        fallos.append((paleta, variante, f"{fg}/{bg}", valor))
                for bg in ("window_bg_color", "view_bg_color"):
                    valor = contrast_ratio(tokens["accent_color"], tokens[bg])
                    if valor < MIN_CONTRAST:
                        fallos.append((paleta, variante, f"accent_color/{bg}", valor))
    return fallos
