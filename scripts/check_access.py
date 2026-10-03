"""Primera prueba autenticada de cada proveedor (protocolo §2.3). Solo lectura: metadata, estimate y
una llamada Jev con estado SINTÉTICO. No descarga datos ni envía datos licenciados.

Las claves se leen en tiempo de ejecución (trading_scanner.secrets) y nunca se imprimen ni se guardan.
Resultados sin secretos en manifests/access_check.json y manifests/pilot-orderflow-v1.estimate.json.

Uso:  .venv/Scripts/python scripts/check_access.py [--skip-databento] [--skip-jev]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from trading_scanner.secrets import DATABENTO, TYPESAFE, load_api_keys, mask  # noqa: E402

MANIFEST = ROOT / "manifests" / "pilot-orderflow-v1.json"
ESTIMATE = ROOT / "manifests" / "pilot-orderflow-v1.estimate.json"
REPORT = ROOT / "manifests" / "access_check.json"
RUBRICS = ROOT / "configs" / "questions" / "lr_v1_rubrics.json"

JEV_URL = "https://api.typesafe.ai/v1/systemone"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def check_databento(key: str) -> dict:
    import databento as db

    man = json.loads(MANIFEST.read_text(encoding="utf-8"))
    dataset, start, end = man["dataset"], man["start_utc_inclusive"], man["end_utc_exclusive"]
    client = db.Historical(key)
    out: dict = {"checked_at": _now(), "dataset": dataset, "start": start, "end": end}

    datasets = client.metadata.list_datasets()
    out["dataset_in_account"] = dataset in datasets
    out["datasets_count"] = len(datasets)
    out["dataset_range"] = client.metadata.get_dataset_range(dataset)
    schemas = client.metadata.list_schemas(dataset)
    out["schemas"] = {s: (s in schemas) for s in ("mbp-10", "mbp-1", "trades", "definition", "status")}

    parents = [f"{r}.FUT" for r in man["roots"]]
    res = client.symbology.resolve(
        dataset=dataset, symbols=parents, stype_in="parent", stype_out="instrument_id",
        start_date=start[:10], end_date=end[:10],
    )
    out["symbology"] = {
        "parents": parents,
        "resolved_count": {p: len(v) for p, v in res.get("result", {}).items()},
        "not_found": res.get("not_found", []),
        "partial": res.get("partial", []),
    }

    out["estimates"] = {}
    for schema in ("mbp-10", "mbp-1", "definition"):
        try:
            cost = client.metadata.get_cost(dataset=dataset, start=start, end=end, symbols=parents,
                                            schema=schema, stype_in="parent")
            size = client.metadata.get_billable_size(dataset=dataset, start=start, end=end,
                                                     symbols=parents, schema=schema, stype_in="parent")
            out["estimates"][schema] = {"cost_usd": cost, "billable_bytes": size}
        except Exception as e:  # noqa: BLE001
            out["estimates"][schema] = {"error": f"{type(e).__name__}: {e}"}

    # Actualizar manifiesto: sigue sin descargar y con resolved_contracts vacío a propósito.
    man["dataset_verified"] = bool(out["dataset_in_account"] and out["schemas"]["mbp-10"])
    est = out["estimates"].get("mbp-10", {})
    man["cost_estimate_usd"] = est.get("cost_usd")
    man["estimated_bytes"] = est.get("billable_bytes")
    man["estimate_checked_at"] = out["checked_at"]
    MANIFEST.write_text(json.dumps(man, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    ESTIMATE.write_text(json.dumps(out, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    return out


def check_jev(key: str) -> dict:
    import requests

    rub = json.loads(RUBRICS.read_text(encoding="utf-8"))
    # Estado sintético (ejemplo §5.4 de la spec): nivel 20000 ticks, sweep 3 ticks, reclaim, delta +0.25.
    state = {
        "candidate_id": "SYNTHETIC-0001",
        "proposed_side": "LONG",
        "units": {"price": "ticks", "volume": "contracts", "time": "seconds"},
        "level": {"price_ticks": 20000, "kind": "prior_day_low", "age_s": 5400},
        "atr_1m_ticks": 20,
        "sweep": {"depth_ticks": 3, "duration_s": 8, "extreme_ticks": 19997},
        "reclaim": {"price_ticks": 20001, "seconds_after_sweep": 8, "move_after_reclaim_ticks": 2},
        "delta_5s": 0.25, "delta_10s": 0.18, "delta_60s": 0.05,
        "volume_5s_rel_median": 1.4,
        "vwap_distance_ticks": -6,
        "ret_5m": -0.0012, "ret_15m": -0.0030,
        "bars_1m": [
            {"o": 0.00, "h": 0.20, "l": -0.10, "c": 0.10}, {"o": 0.10, "h": 0.15, "l": -0.20, "c": -0.15},
            {"o": -0.15, "h": -0.05, "l": -0.40, "c": -0.35}, {"o": -0.35, "h": -0.30, "l": -0.60, "c": -0.55},
            {"o": -0.55, "h": -0.45, "l": -0.70, "c": -0.65}, {"o": -0.65, "h": -0.60, "l": -0.90, "c": -0.85},
            {"o": -0.85, "h": -0.80, "l": -1.00, "c": -0.95}, {"o": -0.95, "h": -0.90, "l": -1.10, "c": -1.05},
            {"o": -1.05, "h": -1.00, "l": -1.20, "c": -1.15}, {"o": -1.15, "h": -1.05, "l": -1.30, "c": -1.10},
            {"o": -1.10, "h": -0.95, "l": -1.35, "c": -1.00}, {"o": -1.00, "h": -0.85, "l": -1.05, "c": -0.90}
        ],
        "depth_levels": {"bid": [[20000, 120], [19999, 95], [19998, 80], [19997, 60], [19996, 50]],
                         "ask": [[20001, 40], [20002, 55], [20003, 70], [20004, 90], [20005, 100]]},
        "depth_imbalance_5": 0.26,
        "quality": {"aggressor_known_pct": 99.1, "flags": []},
        "note": "synthetic engineering state; not market data",
    }
    body = {"model": rub["requested_model"], "state": state, "questions": rub["questions"]}
    t0 = time.perf_counter()
    r = requests.post(JEV_URL, json=body, headers={"Authorization": f"Bearer {key}"}, timeout=30)
    latency_ms = round((time.perf_counter() - t0) * 1000)
    out: dict = {"checked_at": _now(), "http_status": r.status_code, "latency_ms": latency_ms,
                 "requested_model": rub["requested_model"], "rubric_version": rub["rubric_version"]}
    try:
        payload = r.json()
    except ValueError:
        payload = {"raw": r.text[:500]}
    if r.ok:
        out["resolved_model"] = payload.get("model")
        out["usage"] = payload.get("usage")
        out["answers"] = payload.get("answers")
        # Validación spec §8.3: todas las opciones, suma ≈ 1, sin NaN.
        problems = []
        for qid, q in rub["questions"].items():
            a = (payload.get("answers") or {}).get(qid)
            if not a:
                problems.append(f"{qid}: sin respuesta")
                continue
            probs = a.get("probabilities") or {}
            if q["type"] == "choice":
                missing = set(q["criteria"]) - set(probs)
                if missing:
                    problems.append(f"{qid}: faltan opciones {sorted(missing)}")
            if probs:
                s = sum(float(v) for v in probs.values())
                if abs(s - 1.0) > 1e-6:
                    problems.append(f"{qid}: suma de probabilidades {s}")
                if any(v != v for v in probs.values()):
                    problems.append(f"{qid}: NaN")
        out["validation_problems"] = problems
    else:
        out["error"] = payload
    (ROOT / "artifacts").mkdir(exist_ok=True)
    (ROOT / "artifacts" / "jev_synthetic_check.json").write_text(
        json.dumps({"request": body, "response": payload, "meta": out}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-databento", action="store_true")
    ap.add_argument("--skip-jev", action="store_true")
    args = ap.parse_args()

    keys = load_api_keys(ROOT)
    print(f"{DATABENTO}: {mask(keys[DATABENTO])}")
    print(f"{TYPESAFE}: {mask(keys[TYPESAFE])}")
    report: dict = {"run_at": _now()}

    if not args.skip_databento:
        if not keys[DATABENTO]:
            report["databento"] = {"status": "NO_KEY"}
        else:
            try:
                report["databento"] = {"status": "OK", **check_databento(keys[DATABENTO])}
            except Exception as e:  # noqa: BLE001
                report["databento"] = {"status": "ERROR", "error": f"{type(e).__name__}: {e}"}
    if not args.skip_jev:
        if not keys[TYPESAFE]:
            report["jev"] = {"status": "NO_KEY"}
        else:
            try:
                res = check_jev(keys[TYPESAFE])
                res["status"] = "OK" if res["http_status"] == 200 else "HTTP_ERROR"
                report["jev"] = res
            except Exception as e:  # noqa: BLE001
                report["jev"] = {"status": "ERROR", "error": f"{type(e).__name__}: {e}"}

    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
