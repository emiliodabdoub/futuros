"""Carga de claves de API en tiempo de ejecución. Nunca se imprimen ni se registran (protocolo §2).

Orden de búsqueda: variables de entorno → `.env` → `secrets.txt` en la raíz del repo.
Formatos aceptados por línea: `KEY=valor`, `KEY: valor`, `export KEY=valor`; se ignoran comentarios.
Si el archivo no usa los nombres canónicos, se buscan líneas que contengan "databento" o "typesafe".
"""

from __future__ import annotations

import os
import re
from pathlib import Path

DATABENTO = "DATABENTO_API_KEY"
TYPESAFE = "TYPESAFE_API_KEY"
_ALIASES = {DATABENTO: ("databento",), TYPESAFE: ("typesafe", "jev")}
_LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z0-9_ .\-]+?)\s*[=:]\s*['\"]?([^'\"\s#]+)['\"]?\s*(?:#.*)?$")


def _parse(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        m = _LINE.match(raw)
        if not m:
            continue
        name, value = m.group(1).strip(), m.group(2).strip()
        out[name] = value
    return out


def _lookup(parsed: dict[str, str], canonical: str) -> str | None:
    if canonical in parsed:
        return parsed[canonical]
    for name, value in parsed.items():
        low = name.lower()
        if any(a in low for a in _ALIASES[canonical]):
            return value
    return None


def load_api_keys(repo_root: Path | None = None) -> dict[str, str | None]:
    root = repo_root or Path(__file__).resolve().parents[2]
    keys: dict[str, str | None] = {DATABENTO: os.environ.get(DATABENTO), TYPESAFE: os.environ.get(TYPESAFE)}
    for fname in (".env", "secrets.txt"):
        p = root / fname
        if not p.is_file():
            continue
        parsed = _parse(p)
        for k in keys:
            if keys[k] is None:
                keys[k] = _lookup(parsed, k)
    return keys


def mask(value: str | None) -> str:
    if not value:
        return "<ausente>"
    return f"{value[:4]}…{value[-2:]} (len={len(value)})" if len(value) > 8 else "***"
