"""Compara variantes del piloto (artifacts/pilot vs artifacts/pilot_<variante>): cobertura dentro de la
ventana de entradas por motivo de bloqueo, embudo LR y outcomes. Imprime Markdown.

Uso: .venv/Scripts/python scripts/compare_variants.py base rth-refs
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(variant: str) -> dict:
    d = ROOT / "artifacts" / ("pilot" if variant == "base" else f"pilot_{variant}")
    rep = json.loads((d / "report.json").read_text(encoding="utf-8"))
    rej = json.loads((d / "rejections.json").read_text(encoding="utf-8")) if (d / "rejections.json").is_file() else []
    cands = [json.loads(l) for l in (d / "candidates.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()] if (d / "candidates.jsonl").is_file() else []
    return {"report": rep, "rejections": rej, "candidates": cands}


def summarize(v: dict) -> dict:
    rep = v["report"]
    by_root: dict[str, Counter] = {"ES": Counter(), "NQ": Counter(), "GC": Counter()}
    win = Counter()
    for s in rep.values():
        root = s["contract_id"][:2]
        by_root[root]["window_epochs"] += s.get("window_epochs", 0)
        by_root[root]["window_blocked"] += s.get("window_blocked_epochs", 0)
        for k, n in s.get("window_block_reasons", {}).items():
            win[k] += n
            by_root[root][k] += n
    outs = Counter((c["outcome"] or {}).get("terminal_reason", "SIN_OUTCOME") for c in v["candidates"])
    pnl = sum((Decimal(str(c["outcome"]["PnL_USD"])) for c in v["candidates"] if c.get("outcome") and c["outcome"].get("PnL_USD") is not None), Decimal("0"))
    return {"by_root": by_root, "window_reasons": win, "signals": len(v["candidates"]),
            "rejections": Counter(r["reason"].split("(")[0] for r in v["rejections"]), "outcomes": outs, "pnl": pnl,
            "tasks": len(rep)}


def main() -> int:
    names = sys.argv[1:] or ["base", "rth-refs"]
    data = {n: summarize(load(n)) for n in names}
    print("| Métrica | " + " | ".join(names) + " |")
    print("|---|" + "---:|" * len(names))
    print("| Tareas | " + " | ".join(str(data[n]["tasks"]) for n in names) + " |")
    for root in ("ES", "NQ", "GC"):
        for n in names:
            pass
        row = []
        for n in names:
            b = data[n]["by_root"][root]
            row.append(f"{b['window_blocked']}/{b['window_epochs']} ({100 * b['window_blocked'] / b['window_epochs']:.1f}%)" if b["window_epochs"] else "—")
        print(f"| Epochs bloqueados en ventana {root} | " + " | ".join(row) + " |")
    reasons = sorted({k for n in names for k in data[n]["window_reasons"]})
    for k in reasons:
        print(f"| ventana · {k} | " + " | ".join(str(data[n]["window_reasons"].get(k, 0)) for n in names) + " |")
    print("| Señales READY | " + " | ".join(str(data[n]["signals"]) for n in names) + " |")
    rej = sorted({k for n in names for k in data[n]["rejections"]})
    for k in rej:
        print(f"| rechazo · {k} | " + " | ".join(str(data[n]["rejections"].get(k, 0)) for n in names) + " |")
    outs = sorted({k for n in names for k in data[n]["outcomes"]})
    for k in outs:
        print(f"| outcome · {k} | " + " | ".join(str(data[n]["outcomes"].get(k, 0)) for n in names) + " |")
    print("| P&L neto contrafactual (USD) | " + " | ".join(str(data[n]["pnl"]) for n in names) + " |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
