"""Constantes y utilidades puras del ecualizador de 10 bandas."""

from __future__ import annotations

import math

MIN_GAIN = -12.0
MAX_GAIN = 12.0
STEP_GAIN = 0.5

# Frecuencias mostradas en la interfaz (las bandas reales de GStreamer son
# 29, 59, 119, 237, 474, 947, 1889, 3770, 7523 y 15011 Hz).
FREQUENCIES: tuple[int, ...] = (29, 59, 119, 237, 474, 947, 1889, 3758, 7526, 15056)

PRESET_NAMES: tuple[str, ...] = (
    "Plano",
    "Graves",
    "Agudos",
    "Rock",
    "Pop",
    "Clásica",
    "Voz",
    "Personalizado",
)

PRESETS: dict[str, tuple[float, ...]] = {
    "Plano": (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
    "Graves": (7.0, 6.0, 5.0, 3.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0),
    "Agudos": (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 2.0, 4.0, 6.0, 7.0),
    "Rock": (5.0, 4.0, 3.0, 1.0, 0.0, -1.0, -1.0, 1.0, 3.0, 5.0),
    "Pop": (-1.0, 0.0, 2.0, 4.0, 4.0, 2.0, 0.0, -1.0, -2.0, -2.0),
    "Clásica": (3.0, 2.0, 1.0, 0.0, 0.0, 0.0, -1.0, -2.0, -3.0, -3.0),
    "Voz": (-3.0, -2.0, 0.0, 2.0, 4.0, 5.0, 4.0, 2.0, 0.0, -2.0),
}

CUSTOM_PRESET = "Personalizado"


def clamp_gain(value: float) -> float:
    """Limita a [-12, +12] dB y redondea al paso de 0,5 dB."""
    try:
        valor = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(valor):
        return 0.0
    valor = max(MIN_GAIN, min(MAX_GAIN, valor))
    if valor >= 0:
        pasos = math.floor(valor / STEP_GAIN + 0.5)
    else:
        pasos = math.ceil(valor / STEP_GAIN - 0.5)
    return pasos * STEP_GAIN


def sanitize_gains(values) -> list[float]:
    """Devuelve siempre 10 ganancias válidas."""
    resultado = [0.0] * len(FREQUENCIES)
    if not isinstance(values, (list, tuple)):
        return resultado
    for i, valor in enumerate(values[: len(resultado)]):
        resultado[i] = clamp_gain(valor)
    return resultado


def preset_gains(name: str) -> list[float] | None:
    """Ganancias de un preset; None para «Personalizado» o nombre inválido."""
    valores = PRESETS.get(name)
    if valores is None:
        return None
    return list(valores)


def format_db(value: float) -> str:
    valor = clamp_gain(value)
    if valor == 0:
        return "0,0 dB"
    texto = f"{valor:+.1f}".replace(".", ",")
    return f"{texto} dB"


def default_equalizer_state() -> dict:
    return {"enabled": True, "preset": "Plano", "gains": [0.0] * len(FREQUENCIES)}
