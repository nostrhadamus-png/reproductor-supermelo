"""Persistencia local del estado con escritura atómica (JSON)."""

from __future__ import annotations

import json
import math
import os
import tempfile
from pathlib import Path

from .equalizer import PRESET_NAMES, default_equalizer_state, sanitize_gains

APP_NAME = "reproductor-melo"

DEFAULT_STATE = {
    "order": [],
    "last_song": None,
    "selected_song": None,
    "volume": 1.0,
    "position": 0.0,
    "equalizer": default_equalizer_state(),
}


def _default_state() -> dict:
    """Copia nueva, sin compartir los diccionarios anidados."""
    estado = dict(DEFAULT_STATE)
    estado["order"] = []
    estado["equalizer"] = default_equalizer_state()
    return estado


def data_dir() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return Path(base) / APP_NAME


def default_state_path() -> Path:
    return data_dir() / "state.json"


def _clamp(value: float, minimo: float, maximo: float) -> float:
    return max(minimo, min(maximo, value))


def _normalize(raw) -> dict:
    estado = _default_state()
    if not isinstance(raw, dict):
        return estado

    orden = raw.get("order")
    if isinstance(orden, list):
        vistas = set()
        limpio = []
        for item in orden:
            if isinstance(item, str) and item and item not in vistas:
                limpio.append(item)
                vistas.add(item)
        estado["order"] = limpio

    for clave in ("last_song", "selected_song"):
        valor = raw.get(clave)
        if isinstance(valor, str) and valor:
            estado[clave] = valor

    try:
        volumen = float(raw.get("volume", 1.0))
        estado["volume"] = _clamp(volumen, 0.0, 1.0) if math.isfinite(volumen) else 1.0
    except (TypeError, ValueError):
        estado["volume"] = 1.0

    try:
        posicion = float(raw.get("position", 0.0))
        estado["position"] = max(0.0, posicion) if math.isfinite(posicion) else 0.0
    except (TypeError, ValueError):
        estado["position"] = 0.0

    eq_guardado = raw.get("equalizer")
    if isinstance(eq_guardado, dict):
        eq = estado["equalizer"]
        if isinstance(eq_guardado.get("enabled"), bool):
            eq["enabled"] = eq_guardado["enabled"]
        preset = eq_guardado.get("preset")
        if isinstance(preset, str) and preset in PRESET_NAMES:
            eq["preset"] = preset
        eq["gains"] = sanitize_gains(eq_guardado.get("gains"))

    return estado


def load_state(path: Path | str | None = None) -> dict:
    ruta = Path(path) if path else default_state_path()
    try:
        with open(ruta, "r", encoding="utf-8") as f:
            return _normalize(json.load(f))
    except (OSError, ValueError, UnicodeDecodeError):
        return _default_state()


def save_state(state: dict, path: Path | str | None = None) -> bool:
    """Escribe en un temporal y lo renombra; nunca corrompe el estado previo."""
    ruta = Path(path) if path else default_state_path()
    try:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        fd, temporal = tempfile.mkstemp(prefix=".state-", suffix=".tmp", dir=str(ruta.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(_normalize(state), f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temporal, ruta)
        except BaseException:
            try:
                os.unlink(temporal)
            except OSError:
                pass
            raise
        return True
    except OSError:
        return False
