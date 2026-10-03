"""Adapter TypeSafe/Jev (ENG-08, spec §8). Transporte verificado el 3-oct-2026:
POST https://api.typesafe.ai/v1/systemone, Bearer, body {model, state, questions}; respuesta
{model, answers{qid:{type, choice|score, probabilities, confidence}}, usage{input_tokens, output_tokens}}.

Reglas: una petición por candidato con todas las preguntas; deadline 1.5 s; sin retry para candidatos
vivos; caché por (state_hash, questions_hash, model) para que un replay repetido no vuelva a pagar;
se valida que todas las opciones estén, que la distribución sume 1 (±1e-6) y no haya NaN;
`insufficient` se conserva, no se renormaliza. El estado enviado NO lleva cuenta, capital ni credenciales.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from trading_scanner.contracts import ClassificationResult, FeatureSnapshot
from trading_scanner.setups.liquidity_reversal import LRSignal

JEV_URL = "https://api.typesafe.ai/v1/systemone"
NS = 1_000_000_000


@dataclass(frozen=True)
class JevConfig:
    model: str = "jev-1.13.0"
    deadline_s: float = 1.5
    url: str = JEV_URL
    cache_dir: Path | None = None
    simulated_latency_ns: int = 500_000_000  # replay: la respuesta "existe" en requested_at + latencia modelada


@dataclass
class JevResponse:
    ok: bool
    status: int | None
    payload: dict[str, Any] | None
    elapsed_ms: int
    from_cache: bool = False
    error: str | None = None


def _h(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def questions_hash(questions: dict[str, Any]) -> str:
    return _h(questions)[:16]


def state_hash(state: dict[str, Any]) -> str:
    return _h(state)[:16]


FORBIDDEN_STATE_KEYS = {"account", "balance", "capital", "api_key", "token", "password", "order", "execute"}


def build_state(sig: LRSignal, snap: FeatureSnapshot, bars_1m: list[dict[str, float]], depth: dict[str, Any] | None,
                quality: dict[str, Any]) -> dict[str, Any]:
    """Estado §8.2: lado propuesto, nivel y antigüedad, ATR, sweep/reclaim, 12 barras 1m normalizadas,
    retornos, deltas, volumen relativo, VWAP, 5 niveles de profundidad, imbalance y calidad. Unidades explícitas."""
    v = snap.values
    state = {
        "candidate_id": sig.id,
        "proposed_side": sig.direction.value,
        "units": {"price": "ticks", "volume": "contracts", "time": "seconds"},
        "level": {"price_ticks": sig.level.price_ticks, "kind": sig.level.kind.value},
        "atr_1m_ticks": sig.atr_1m_ticks_frozen,
        "sweep": {"extreme_ticks": sig.sweep_extreme_ticks, "depth_ticks": abs(sig.level.price_ticks - sig.sweep_extreme_ticks)},
        "reclaim": {"price_ticks": sig.reclaim_price_ticks, "trigger_price_ticks": sig.trigger_price_ticks},
        "delta_5s": v.get("F05_delta_ratio_5s"), "delta_10s": v.get("F05_delta_ratio_10s"), "delta_60s": v.get("F05_delta_ratio_60s"),
        "volume_5s_rel_median": sig.volume_5s_rel_median,
        "vwap_distance_ticks": (sig.trigger_price_ticks - v["F07_vwap_session"]) if v.get("F07_vwap_session") is not None else None,
        "bars_1m": bars_1m[-12:],
        "depth_levels": depth,
        "depth_imbalance_5": v.get("F11_depth_imbalance_5"),
        "quality": quality,
        "missing": sorted(snap.missing_reasons),
    }
    bad = FORBIDDEN_STATE_KEYS & {k.lower() for k in state}
    if bad:
        raise ValueError(f"estado con campos prohibidos: {bad}")
    return state


def validate_answers(answers: dict[str, Any] | None, questions: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    if not answers:
        return ["sin answers"]
    for qid, q in questions.items():
        a = answers.get(qid)
        if not a:
            problems.append(f"{qid}: sin respuesta")
            continue
        probs = a.get("probabilities") or {}
        if q["type"] == "choice":
            missing = set(q["criteria"]) - set(probs)
            if missing:
                problems.append(f"{qid}: faltan opciones {sorted(missing)}")
        if q["type"] == "score" and len(probs) != len(q["criteria"]):
            problems.append(f"{qid}: niveles de score incompletos")
        vals = [float(x) for x in probs.values()]
        if any(math.isnan(x) for x in vals):
            problems.append(f"{qid}: NaN")
        elif probs and abs(sum(vals) - 1.0) > 1e-6:
            problems.append(f"{qid}: suma {sum(vals)}")
    return problems


class JevClient:
    def __init__(self, api_key: str | None, questions: dict[str, Any], cfg: JevConfig | None = None,
                 transport: Callable[[dict[str, Any], float], JevResponse] | None = None) -> None:
        self.cfg = cfg or JevConfig()
        self.questions = questions
        self.qhash = questions_hash(questions)
        self._key = api_key
        self._transport = transport or self._http
        self._mem: dict[str, dict[str, Any]] = {}
        if self.cfg.cache_dir:
            self.cfg.cache_dir.mkdir(parents=True, exist_ok=True)
        self.calls = 0
        self.cache_hits = 0

    # ---- caché -----------------------------------------------------------------------------------
    def _cache_key(self, shash: str) -> str:
        return f"{self.cfg.model}.{self.qhash}.{shash}"

    def _cache_get(self, key: str) -> dict[str, Any] | None:
        if key in self._mem:
            return self._mem[key]
        if self.cfg.cache_dir:
            p = self.cfg.cache_dir / f"{key}.json"
            if p.is_file():
                data = json.loads(p.read_text(encoding="utf-8"))
                self._mem[key] = data
                return data
        return None

    def _cache_put(self, key: str, data: dict[str, Any]) -> None:
        self._mem[key] = data
        if self.cfg.cache_dir:
            (self.cfg.cache_dir / f"{key}.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    # ---- transporte ------------------------------------------------------------------------------
    def _http(self, body: dict[str, Any], timeout_s: float) -> JevResponse:
        import requests

        if not self._key:
            return JevResponse(False, None, None, 0, error="NO_KEY")
        t0 = time.perf_counter()
        try:
            r = requests.post(self.cfg.url, json=body, headers={"Authorization": f"Bearer {self._key}"}, timeout=timeout_s)
        except requests.Timeout:
            return JevResponse(False, None, None, round((time.perf_counter() - t0) * 1000), error="TIMEOUT")
        except requests.RequestException as e:  # noqa: PERF203
            return JevResponse(False, None, None, round((time.perf_counter() - t0) * 1000), error=f"NETWORK:{type(e).__name__}")
        ms = round((time.perf_counter() - t0) * 1000)
        try:
            payload = r.json()
        except ValueError:
            payload = None
        return JevResponse(r.ok, r.status_code, payload, ms, error=None if r.ok else f"HTTP_{r.status_code}")

    # ---- clasificación ---------------------------------------------------------------------------
    def classify(self, candidate_id: str, state: dict[str, Any], requested_at_ns: int, *, result_id: str) -> ClassificationResult:
        """Una llamada por candidato. En replay `received_at = requested_at + latencia modelada` (o real si
        se midió, la mayor de las dos), nunca antes. Sin retry: si falla, el candidato B se rechaza."""
        shash = state_hash(state)
        key = self._cache_key(shash)
        cached = self._cache_get(key)
        if cached is not None:
            self.cache_hits += 1
            resp = JevResponse(True, 200, cached, 0, from_cache=True)
        else:
            self.calls += 1
            resp = self._transport({"model": self.cfg.model, "state": state, "questions": self.questions}, self.cfg.deadline_s)
            if resp.ok and resp.payload:
                self._cache_put(key, resp.payload)
        latency_ns = max(self.cfg.simulated_latency_ns, resp.elapsed_ms * 1_000_000)
        received = requested_at_ns + latency_ns
        if not resp.ok or not resp.payload:
            return ClassificationResult(id=result_id, candidate_id=candidate_id, state_hash=shash, questions_hash=self.qhash,
                                        requested_model=self.cfg.model, requested_at_ns=requested_at_ns,
                                        received_at_ns=received if resp.status else None,
                                        validation_status="FAILED", failure_reason=resp.error or "UNKNOWN")
        problems = validate_answers(resp.payload.get("answers"), self.questions)
        dists = {qid: {str(k): float(v) for k, v in (a.get("probabilities") or {}).items()}
                 for qid, a in (resp.payload.get("answers") or {}).items()}
        conf = {qid: float(a["confidence"]) for qid, a in (resp.payload.get("answers") or {}).items() if "confidence" in a}
        usage = {k: int(v) for k, v in (resp.payload.get("usage") or {}).items()}
        if latency_ns > int(self.cfg.deadline_s * NS):
            problems.append(f"deadline {self.cfg.deadline_s}s excedido")
        return ClassificationResult(
            id=result_id, candidate_id=candidate_id, state_hash=shash, questions_hash=self.qhash,
            requested_model=self.cfg.model, resolved_model=resp.payload.get("model"),
            requested_at_ns=requested_at_ns, received_at_ns=received, distributions=dists, confidence_fields=conf,
            validation_status="OK" if not problems else "INVALID", usage=usage,
            failure_reason=None if not problems else "; ".join(problems),
        )
