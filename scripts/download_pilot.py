"""Compra y descarga de la muestra piloto (opción A, confirmada por el usuario el 3-oct-2026).

- mbp-10 vía batch job (138 GB sin comprimir; DBN+zstd, un archivo por día) → data/raw/GLBX.MDP3/mbp-10/<job_id>/
- definition y status vía get_range (coste 0) → data/raw/GLBX.MDP3/{definition,status}/
- SHA-256 por archivo y actualización de manifests/pilot-orderflow-v1.json

Idempotente: si ya existe un job_id en el manifiesto NO vuelve a comprar; solo espera/descarga/hashea.
Uso: .venv/Scripts/python scripts/download_pilot.py [--no-wait]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from trading_scanner.secrets import DATABENTO, load_api_keys  # noqa: E402

MANIFEST = ROOT / "manifests" / "pilot-orderflow-v1.json"
RAW = ROOT / "data" / "raw"
SYMBOLS = ["ESU4", "ESZ4", "NQU4", "NQZ4", "GCZ4"]  # opción A: contratos activos
SMALL_SCHEMAS = ("definition", "status")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def save_manifest(m: dict) -> None:
    MANIFEST.write_text(json.dumps(m, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-wait", action="store_true", help="enviar el job y salir sin esperar")
    args = ap.parse_args()

    import databento as db

    client = db.Historical(load_api_keys(ROOT)[DATABENTO])
    m = load_manifest()
    ds, start, end = m["dataset"], m["start_utc_inclusive"], m["end_utc_exclusive"]
    m.setdefault("purchase", {})
    m["resolved_contracts"] = SYMBOLS
    m["stype_in"] = "raw_symbol"

    # 1) definition + status (coste 0) por get_range, directo a archivo.
    for schema in SMALL_SCHEMAS:
        out_dir = RAW / ds / schema
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / f"{ds}.{schema}.{start[:10]}_{end[:10]}.dbn.zst"
        if not out.exists():
            print(f"[{now()}] get_range {schema} -> {out.name}")
            client.timeseries.get_range(dataset=ds, start=start, end=end, symbols=SYMBOLS,
                                        schema=schema, stype_in="raw_symbol", path=out)
        m["purchase"][schema] = {"path": str(out.relative_to(ROOT)), "bytes": out.stat().st_size,
                                 "sha256": sha256(out), "fetched_at": now()}
        save_manifest(m)

    # 2) mbp-10 por batch job (idempotente).
    job = m["purchase"].get("mbp-10", {})
    if not job.get("job_id"):
        print(f"[{now()}] submit_job mbp-10 {SYMBOLS} {start}..{end}")
        res = client.batch.submit_job(dataset=ds, symbols=SYMBOLS, schema="mbp-10", start=start, end=end,
                                      encoding="dbn", compression="zstd", split_duration="day",
                                      stype_in="raw_symbol", delivery="download")
        job = {"job_id": res["id"], "submitted_at": now(), "cost_usd": res.get("cost_usd"),
               "billed_size": res.get("billed_size"), "state": res.get("state"), "files": {}}
        m["purchase"]["mbp-10"] = job
        m["download_status"] = "SUBMITTED"
        save_manifest(m)
        print(f"[{now()}] job {job['job_id']} cost_usd={job['cost_usd']} billed_size={job['billed_size']}")
    else:
        print(f"[{now()}] job existente {job['job_id']} (no se vuelve a comprar)")

    if args.no_wait:
        return 0

    # 3) Esperar a que termine.
    while True:
        jobs = {j["id"]: j for j in client.batch.list_jobs(states="queued,processing,done,expired")}
        j = jobs.get(job["job_id"])
        state = j["state"] if j else "unknown"
        job["state"] = state
        save_manifest(m)
        print(f"[{now()}] estado {state}")
        if state == "done":
            break
        if state in ("expired", "unknown"):
            print("job no utilizable:", state)
            return 1
        time.sleep(60)

    # 4) Descargar y hashear.
    out_dir = RAW / ds / "mbp-10" / job["job_id"]
    out_dir.mkdir(parents=True, exist_ok=True)
    m["download_status"] = "DOWNLOADING"
    save_manifest(m)
    print(f"[{now()}] descargando a {out_dir}")
    paths = client.batch.download(job_id=job["job_id"], output_dir=out_dir)
    total = 0
    for p in sorted(paths):
        if p.is_file():
            total += p.stat().st_size
            job["files"][p.name] = {"bytes": p.stat().st_size, "sha256": sha256(p)}
            print(f"  {p.name}  {p.stat().st_size/1e9:.2f} GB")
    job["downloaded_at"] = now()
    job["total_bytes_on_disk"] = total
    m["download_status"] = "DOWNLOADED"
    m["manifest_sha256"] = hashlib.sha256(
        json.dumps(job["files"], sort_keys=True).encode()).hexdigest()
    save_manifest(m)
    print(f"[{now()}] listo: {len(job['files'])} archivos, {total/1e9:.2f} GB en disco")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
