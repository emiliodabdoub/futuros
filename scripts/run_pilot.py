"""Replay del piloto completo (experimento A, sin Jev): 10 sesiones × contratos seleccionados causalmente.

Pasos:
 1. Descubrir archivos diarios del job batch (data/raw/GLBX.MDP3/mbp-10/<job_id>/*.dbn.zst).
 2. Agregados vectorizados por día e instrumento (numpy): volumen de sesión completa, high/low RTH
    (09:30–16:00 NY) y volumen RTH, contrastables contra ohlcv-1m. → artifacts/pilot/daily_aggregates.json
 3. Por sesión del piloto y por root: select_contract con el volumen de la sesión anterior (ADR-002).
 4. Por (sesión, contrato): SessionRunner sobre la ventana 08:00–12:00 NY (warm-up incluido) con niveles del día anterior
    inyectados. Un proceso por tarea (multiprocessing). → artifacts/pilot/<fecha>/<contrato>.json
 5. Ledger de candidatos/outcomes (artifacts/pilot/candidates.jsonl) y reporte (artifacts/pilot/report.json).

Uso: .venv/Scripts/python scripts/run_pilot.py [--workers N] [--dates 2024-09-09,2024-09-10] [--only-aggregates]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import asdict
from datetime import date, datetime, time as dtime, timedelta, timezone
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402

from trading_scanner.clock import NEW_YORK, pilot_window, to_utc_ns  # noqa: E402
from trading_scanner.contracts import price_to_ticks  # noqa: E402
from trading_scanner.registry import ContractUnresolvedError, InstrumentCatalog, TradingCalendar, select_contract  # noqa: E402

NS = 1_000_000_000
MANIFEST = ROOT / "manifests" / "pilot-orderflow-v1.json"
OUT = ROOT / "artifacts" / "pilot"
PILOT_SESSIONS = [date(2024, 9, 9) + timedelta(days=i) for i in range(12)]
PILOT_SESSIONS = [d for d in PILOT_SESSIONS if d.weekday() < 5]  # 9–20 sep 2024


def log(msg: str) -> None:
    print(f"[{datetime.now(timezone.utc).isoformat(timespec='seconds')}] {msg}", flush=True)


# ---------- 1. archivos ----------
def discover_files(job_dir: Path) -> dict[date, Path]:
    import databento as db

    out: dict[date, Path] = {}
    for f in sorted(job_dir.rglob("*.dbn.zst")):
        m = re.search(r"(\d{8})", f.name)
        if m:
            d = datetime.strptime(m.group(1), "%Y%m%d").date()
        else:
            d = db.DBNStore.from_file(f).metadata.start // NS
            d = datetime.fromtimestamp(d, tz=timezone.utc).date()
        out[d] = f
    return out


# ---------- 2. agregados vectorizados ----------
def aggregate_file(args: tuple[str, str]) -> dict:
    """Por instrumento: volumen total del archivo, trades, volumen con agresor conocido, high/low/volumen RTH."""
    import databento as db

    path, day = Path(args[0]), date.fromisoformat(args[1])
    rth_s = to_utc_ns(day, dtime(9, 30), NEW_YORK)
    rth_e = to_utc_ns(day, dtime(16, 0), NEW_YORK)
    acc: dict[int, dict] = {}
    records = 0
    for arr in db.DBNStore.from_file(path).to_ndarray(count=1_000_000):
        records += len(arr)
        t = arr[arr["action"] == b"T"]
        if len(t) == 0:
            continue
        for inst in np.unique(t["instrument_id"]):
            m = t["instrument_id"] == inst
            tt = t[m]
            a = acc.setdefault(int(inst), {"volume": 0, "trades": 0, "known": 0, "rth_high": None, "rth_low": None, "rth_volume": 0,
                                           "first_ts": int(tt["ts_event"][0]), "last_ts": 0})
            a["volume"] += int(tt["size"].sum())
            a["trades"] += int(len(tt))
            a["known"] += int(tt["size"][tt["side"] != b"N"].sum())
            a["last_ts"] = int(tt["ts_event"][-1])
            r = tt[(tt["ts_event"] >= rth_s) & (tt["ts_event"] < rth_e)]
            if len(r):
                hi, lo = int(r["price"].max()), int(r["price"].min())
                a["rth_high"] = hi if a["rth_high"] is None else max(a["rth_high"], hi)
                a["rth_low"] = lo if a["rth_low"] is None else min(a["rth_low"], lo)
                a["rth_volume"] += int(r["size"].sum())
    return {"date": day.isoformat(), "file": str(path), "records": records, "instruments": acc}


class AggVolumes:
    def __init__(self, aggs: dict[str, dict], id_by_contract: dict[str, int]) -> None:
        self.aggs, self.ids = aggs, id_by_contract

    def session_volume(self, contract_id: str, session_date: date) -> int | None:
        day = self.aggs.get(session_date.isoformat())
        if not day:
            return None
        a = day["instruments"].get(str(self.ids.get(contract_id)))
        return int(a["volume"]) if a else None


# ---------- 4. replay por tarea ----------
def run_task(args: dict) -> dict:
    from trading_scanner.replay.session import SessionRunner, summarize

    day = date.fromisoformat(args["date"])
    cat = InstrumentCatalog.from_yaml_dir(ROOT / "configs" / "instruments")
    spec = cat.get(args["contract_id"])
    w = pilot_window(day)
    # 08:00 NY: warm-up de régimen (15 barras 5m = 75 min) y ATR 1m (60 barras) antes de la ventana 09:35
    start = to_utc_ns(day, dtime(8, 0), NEW_YORK)
    end = to_utc_ns(day, dtime(12, 0), NEW_YORK)
    prior = {args["contract_id"]: (args["prior_high_ticks"], args["prior_low_ticks"])} if args.get("prior_high_ticks") is not None else {}
    t0 = time.perf_counter()
    from trading_scanner.regimes import MacroCalendar
    macro = MacroCalendar.from_yaml(ROOT / "configs" / "sessions" / "macro_calendar_2024.yaml")
    sr = SessionRunner(w, prior_levels=prior, event_start_ns=start, event_end_ns=end, macro=macro)
    sr.add_contract(spec, args["instrument_id"], [Path(args["file"])])
    runs = sr.run()
    r = runs[args["contract_id"]]
    summ = summarize(runs)[args["contract_id"]]
    summ.update({"date": args["date"], "contract_id": args["contract_id"], "elapsed_s": round(time.perf_counter() - t0, 1),
                 "prior_levels_ticks": [args.get("prior_high_ticks"), args.get("prior_low_ticks")],
                 "skipped_time": r.stats.skipped_time})
    cands = []
    outs = {o.candidate_id: o for o in r.outcomes}
    for s in r.signals:
        o = outs.get(s.id)
        cands.append({"date": args["date"], "contract_id": s.contract_id, "signal": {**asdict(s), "level": {"kind": s.level.kind.value, "price_ticks": s.level.price_ticks, "merged_with": list(s.level.merged_with)}, "direction": s.direction.value},
                      "outcome": json.loads(o.model_dump_json()) if o else None})
    rejections = [{"date": args["date"], "contract_id": args["contract_id"], "level": t.level_id, "direction": t.direction.value, "at_ns": t.at_ns, "reason": t.reason} for t in r.lr.rejections]
    return {"summary": summ, "candidates": cands, "rejections": rejections}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=5)
    ap.add_argument("--dates", default=None)
    ap.add_argument("--only-aggregates", action="store_true")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    man = json.loads(MANIFEST.read_text(encoding="utf-8"))
    job_id = man["purchase"]["mbp-10"]["job_id"]
    files = discover_files(ROOT / "data" / "raw" / "GLBX.MDP3" / "mbp-10" / job_id)
    log(f"{len(files)} archivos diarios: {sorted(d.isoformat() for d in files)}")
    cat = InstrumentCatalog.from_yaml_dir(ROOT / "configs" / "instruments")
    cal = TradingCalendar.from_yaml(ROOT / "configs" / "sessions" / "cme_research.yaml")
    ids = {k: int(v) for k, v in man["candidate_contracts"].items()}

    # 2. agregados
    agg_path = OUT / "daily_aggregates.json"
    aggs = json.loads(agg_path.read_text(encoding="utf-8")) if agg_path.is_file() else {}
    todo = [(str(f), d.isoformat()) for d, f in sorted(files.items()) if d.isoformat() not in aggs]
    if todo:
        log(f"agregando {len(todo)} archivos con {a.workers} procesos")
        with Pool(a.workers) as pool:
            for res in pool.imap_unordered(aggregate_file, todo):
                aggs[res["date"]] = res
                log(f"  {res['date']}: {res['records']:,} registros, instrumentos {list(res['instruments'])}")
                agg_path.write_text(json.dumps(aggs, indent=1), encoding="utf-8")
    if a.only_aggregates:
        return 0

    # 3. selección causal + tareas
    vols = AggVolumes(aggs, ids)
    sessions = [date.fromisoformat(x) for x in a.dates.split(",")] if a.dates else PILOT_SESSIONS
    tasks, selections = [], {}
    for d in sessions:
        if not cal.is_pilot_session(d) or d not in files:
            log(f"  {d}: sin sesión de piloto/archivo")
            continue
        prev = cal.previous_session(d)
        for root in ("ES", "NQ", "GC"):
            try:
                sel = select_contract(root, d, cat, cal, vols)
            except ContractUnresolvedError as e:
                selections[f"{d}/{root}"] = {"error": str(e)}
                continue
            cid, spec = sel.contract_id, cat.get(sel.contract_id)
            pa = aggs.get(prev.isoformat(), {}).get("instruments", {}).get(str(ids[cid]))
            ph = price_to_ticks(str(pa["rth_high"] / 1e9), str(spec.tick_size)) if pa and pa["rth_high"] is not None else None
            pl = price_to_ticks(str(pa["rth_low"] / 1e9), str(spec.tick_size)) if pa and pa["rth_low"] is not None else None
            selections[f"{d}/{root}"] = {"contract_id": cid, "volume": sel.volume, "volume_date": sel.volume_session_date.isoformat(),
                                         "prior_high_ticks": ph, "prior_low_ticks": pl}
            tasks.append({"date": d.isoformat(), "contract_id": cid, "instrument_id": ids[cid], "file": str(files[d]),
                          "prior_high_ticks": ph, "prior_low_ticks": pl})
    (OUT / "selections.json").write_text(json.dumps(selections, indent=1), encoding="utf-8")
    log(f"{len(tasks)} tareas (sesión × contrato)")

    # 4. replay paralelo
    report, cand_path = {}, OUT / "candidates.jsonl"
    cand_path.write_text("", encoding="utf-8")
    rej_all = []
    with Pool(a.workers) as pool:
        for res in pool.imap_unordered(run_task, tasks):
            s = res["summary"]
            key = f"{s['date']}/{s['contract_id']}"
            report[key] = s
            (OUT / s["date"]).mkdir(exist_ok=True)
            (OUT / s["date"] / f"{s['contract_id']}.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
            with cand_path.open("a", encoding="utf-8") as fh:
                for c in res["candidates"]:
                    fh.write(json.dumps(c, default=str) + "\n")
            rej_all.extend(res["rejections"])
            log(f"  {key}: {s['trades']:,} trades, agresor {s['aggressor_known_pct']}%, bloqueos {s['blocked_epochs']}/{s['epochs']}, "
                f"señales {s['signals']}, outcomes {s['outcomes']}, pnl {s['pnl_usd_net']}, {s['elapsed_s']}s")
            (OUT / "report.json").write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    (OUT / "rejections.json").write_text(json.dumps(rej_all, indent=1), encoding="utf-8")
    log("listo")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
