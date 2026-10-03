"""Informe del piloto (protocolo §9) a partir de artifacts/pilot/*: calidad de datos por sesión y
contrato, embudo LR (transiciones/rechazos), outcomes y P&L contrafactual, selección de contratos y cuadro
de evidencia. Escribe artifacts/pilot/REPORT.md. No infiere ventaja estadística: 10 sesiones no bastan.

Uso: .venv/Scripts/python scripts/pilot_report.py
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "pilot"


def load_jsonl(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()] if p.is_file() else []


def main() -> int:
    report = json.loads((OUT / "report.json").read_text(encoding="utf-8")) if (OUT / "report.json").is_file() else {}
    sel = json.loads((OUT / "selections.json").read_text(encoding="utf-8")) if (OUT / "selections.json").is_file() else {}
    aggs = json.loads((OUT / "daily_aggregates.json").read_text(encoding="utf-8")) if (OUT / "daily_aggregates.json").is_file() else {}
    cands = load_jsonl(OUT / "candidates.jsonl")
    rejs = json.loads((OUT / "rejections.json").read_text(encoding="utf-8")) if (OUT / "rejections.json").is_file() else []
    man = json.loads((ROOT / "manifests" / "pilot-orderflow-v1.json").read_text(encoding="utf-8"))

    L: list[str] = []
    L.append("# Informe del piloto — experimento A (LR-v1 sin Jev)\n")
    L.append(f"Manifiesto `{man['request_id']}` · job `{man.get('purchase', {}).get('mbp-10', {}).get('job_id')}` · "
             f"ventana {man['start_utc_inclusive']} → {man['end_utc_exclusive']} · esquema {man['schema']} · "
             f"días degradados: {man.get('dataset_condition', {}).get('degraded_days')}\n")
    L.append("Resultado de ingeniería sobre 10 sesiones. **No es evidencia de ventaja estadística** (protocolo §1).\n")

    # ---- datos
    L.append("## 1. Datos por sesión y contrato (ventana 08:00–12:00 NY)\n")
    L.append("| Sesión | Contrato | Registros | Trades | Volumen | Agresor conocido % | Resets | Fuera de rejilla | Saltos seq | Epochs bloqueados | Motivos de bloqueo | Barras 1m | Revisiones tardías | s |")
    L.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|")
    for key in sorted(report):
        s = report[key]
        L.append(f"| {s['date']} | {s['contract_id']} | {s['records']:,} | {s['trades']:,} | {s['volume']:,} | {s['aggressor_known_pct']} | {s['resets']} | {s['off_grid']} | "
                 f"{s['sequence_jumps']:,} | {s['blocked_epochs']}/{s['epochs']} | {s['block_reasons']} | {s['bars_1m']} | {s['late_revisions_1m']} | {s['elapsed_s']} |")
    L.append("")

    # ---- contraste de volumen de sesión completa vs agregados
    L.append("## 2. Selección causal de contrato y niveles del día anterior\n")
    L.append("| Sesión/root | Contrato | Volumen sesión previa | Fecha volumen | Prior high (ticks) | Prior low (ticks) |")
    L.append("|---|---|---:|---|---:|---:|")
    for k in sorted(sel):
        v = sel[k]
        if "error" in v:
            L.append(f"| {k} | — | — | — | {v['error']} | |")
        else:
            L.append(f"| {k} | {v['contract_id']} | {v['volume']:,} | {v['volume_date']} | {v['prior_high_ticks']} | {v['prior_low_ticks']} |")
    L.append("")

    L.append("## 3. Agregados diarios (sesión completa, todos los instrumentos del archivo)\n")
    L.append("| Fecha | Registros | Instrumento | Volumen | Trades | Agresor conocido % | RTH high | RTH low | RTH vol |")
    L.append("|---|---:|---|---:|---:|---:|---:|---:|---:|")
    for d in sorted(aggs):
        a = aggs[d]
        for inst, x in sorted(a["instruments"].items()):
            pct = round(100 * x["known"] / x["volume"], 3) if x["volume"] else None
            L.append(f"| {d} | {a['records']:,} | {inst} | {x['volume']:,} | {x['trades']:,} | {pct} | {x['rth_high']} | {x['rth_low']} | {x['rth_volume']:,} |")
    L.append("")

    # ---- embudo LR
    L.append("## 4. Embudo Liquidity Reversal\n")
    rej_by = Counter(r["reason"].split("(")[0] for r in rejs)
    L.append(f"Transiciones totales: {sum(s['lr_transitions'] for s in report.values())} · señales READY: {len(cands)} · rechazos: {len(rejs)}\n")
    L.append("| Motivo de rechazo | n |\n|---|---:|")
    for k, n in rej_by.most_common():
        L.append(f"| {k} | {n} |")
    L.append("")

    # ---- outcomes
    L.append("## 5. Outcomes contrafactuales (ledger por contrato, EXEC-v1, comisión sintética 6 USD)\n")
    by_reason = Counter((c["outcome"] or {}).get("terminal_reason", "SIN_OUTCOME") for c in cands)
    L.append("| Terminal | n |\n|---|---:|")
    for k, n in by_reason.most_common():
        L.append(f"| {k} | {n} |")
    pnl = [Decimal(str(c["outcome"]["PnL_USD"])) for c in cands if c.get("outcome") and c["outcome"].get("PnL_USD") is not None]
    if pnl:
        wins = sum(1 for x in pnl if x > 0)
        L.append(f"\nTrades con P&L: {len(pnl)} · netos positivos: {wins} · P&L neto total: {sum(pnl)} USD · media: {sum(pnl) / len(pnl):.2f} USD · "
                 f"peor: {min(pnl)} · mejor: {max(pnl)}\n")
    by_dir = Counter(c["signal"]["direction"] for c in cands)
    by_c = Counter(c["contract_id"] for c in cands)
    L.append(f"Por dirección: {dict(by_dir)} · por contrato: {dict(by_c)}\n")
    if cands:
        L.append("| Sesión | Contrato | Dir | Nivel | Trigger | Stop | Riesgo | Delta5s | Vol rel | Terminal | Fill | Exit | P&L USD | P&L R | MAE | MFE | Flags |")
        L.append("|---|---|---|---|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---|")
        for c in cands:
            s, o = c["signal"], c.get("outcome") or {}
            dq = o.get("data_quality", {})
            L.append(f"| {c['date']} | {c['contract_id']} | {s['direction']} | {s['level']['kind']}@{s['level']['price_ticks']} | {s['trigger_price_ticks']} | {s['stop_ticks']} | "
                     f"{s['risk_ticks_at_trigger']} | {s['delta_ratio_5s']:+.2f} | {s['volume_5s_rel_median']:.2f} | {o.get('terminal_reason', '—')} | {o.get('fill_price_ticks', '—')} | "
                     f"{o.get('exit_price_ticks', '—')} | {o.get('PnL_USD', '—')} | {o.get('PnL_R', '—')} | {dq.get('mae_ticks', '—')} | {dq.get('mfe_ticks', '—')} | {o.get('ambiguity_flags', [])} |")
    L.append("")

    # ---- evidencia
    L.append("## 6. Cuadro de evidencia (protocolo §9)\n")
    agg_ok = all(all(x["known"] <= x["volume"] for x in a["instruments"].values()) for a in aggs.values())
    L.append("| Afirmación | Evidencia | Estado |\n|---|---|---|")
    L.append(f"| Ingestión funciona | {len(report)} sesión-contrato procesadas con quality gate; agregados vs ohlcv-1m pendiente de contraste externo | {'OK' if report else 'PENDIENTE'} |")
    L.append(f"| Replay causal | tests de determinismo y futuro-no-cambia-pasado en suite; mismo motor en el piloto | OK (suite) |")
    L.append(f"| Jev integrado | request autenticada con estado sintético (3-oct-2026); datos reales bloqueados por licencia | PARCIAL |")
    L.append(f"| Probabilidades calibradas | sin dataset suficiente ({len(cands)} candidatos) | NO |")
    L.append(f"| Jev aporta valor | experimento B no ejecutado | NO |")
    L.append(f"| Ejecución funciona | simulada (EXEC-v1); nada real | SIMULADA |")
    L.append(f"| Agregados consistentes | agresor conocido <= volumen en todos los instrumentos | {'OK' if agg_ok else 'REVISAR'} |")
    (OUT / "REPORT.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"informe: {OUT / 'REPORT.md'} ({len(report)} sesión-contrato, {len(cands)} candidatos)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
