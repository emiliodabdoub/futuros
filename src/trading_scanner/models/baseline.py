"""Modelo base, calibración por temperatura y métricas (protocolo §6.1–§6.2, ENG-09).

- BaseRateModel: tasa base por (setup, dirección) con shrinkage hacia el total de train:
  p_g = (n_g·f_g + k·f_total) / (n_g + k). Nunca probabilidad 0: suavizado aditivo mínimo.
- TemperatureScaler: escalar T sobre logits, elegido minimizando log loss en el bloque de calibración
  (búsqueda en rejilla logarítmica, determinista). Calibración inválida si una clase no tiene soporte.
- Métricas: log loss, Brier multiclass, ECE one-vs-rest con bins y recuentos declarados.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

EPS = 1e-9


@dataclass
class BaseRateModel:
    classes: list[str]
    shrink_k: float = 20.0
    _total: np.ndarray | None = None
    _groups: dict[str, tuple[int, np.ndarray]] = field(default_factory=dict)

    def fit(self, groups: list[str], labels: list[str]) -> "BaseRateModel":
        idx = {c: i for i, c in enumerate(self.classes)}
        y = np.array([idx[l] for l in labels])
        counts = np.bincount(y, minlength=len(self.classes)).astype(float) + 0.5  # suavizado aditivo
        self._total = counts / counts.sum()
        for g in set(groups):
            mask = np.array([gg == g for gg in groups])
            cg = np.bincount(y[mask], minlength=len(self.classes)).astype(float)
            n = int(mask.sum())
            self._groups[g] = (n, cg)
        return self

    def predict_proba(self, group: str) -> np.ndarray:
        assert self._total is not None, "fit primero"
        n, cg = self._groups.get(group, (0, np.zeros(len(self.classes))))
        p = (cg + self.shrink_k * self._total) / (n + self.shrink_k)
        return p / p.sum()

    def support(self, group: str) -> int:
        return self._groups.get(group, (0, None))[0]


def _softmax(z: np.ndarray) -> np.ndarray:
    z = z - z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


def log_loss(p: np.ndarray, y: np.ndarray) -> float:
    return float(-np.mean(np.log(np.clip(p[np.arange(len(y)), y], EPS, 1.0))))


def brier_multiclass(p: np.ndarray, y: np.ndarray) -> float:
    onehot = np.zeros_like(p)
    onehot[np.arange(len(y)), y] = 1.0
    return float(np.mean(np.sum((p - onehot) ** 2, axis=1)))


def ece(p: np.ndarray, y: np.ndarray, n_bins: int = 10) -> tuple[float, list[dict]]:
    """ECE one-vs-rest promediado por clase, con recuentos por bin (no aprobar segmentos sin soporte)."""
    total = 0.0
    bins_out: list[dict] = []
    k = p.shape[1]
    edges = np.linspace(0, 1, n_bins + 1)
    for c in range(k):
        pc, yc = p[:, c], (y == c).astype(float)
        e_c = 0.0
        for i in range(n_bins):
            m = (pc >= edges[i]) & (pc < edges[i + 1] if i < n_bins - 1 else pc <= edges[i + 1])
            n = int(m.sum())
            if n == 0:
                continue
            conf, acc = float(pc[m].mean()), float(yc[m].mean())
            e_c += n / len(pc) * abs(conf - acc)
            bins_out.append({"class": c, "bin": i, "n": n, "confidence": conf, "accuracy": acc})
        total += e_c
    return total / k, bins_out


@dataclass
class TemperatureScaler:
    temperature: float = 1.0
    valid: bool = False
    reason: str | None = None

    def fit(self, logits: np.ndarray, y: np.ndarray, n_classes: int) -> "TemperatureScaler":
        present = np.bincount(y, minlength=n_classes)
        if (present == 0).any():
            self.valid, self.reason = False, f"clases sin soporte en calibración: {np.where(present == 0)[0].tolist()}"
            return self
        grid = np.exp(np.linspace(np.log(0.05), np.log(20.0), 241))
        losses = [log_loss(_softmax(logits / t), y) for t in grid]
        self.temperature = float(grid[int(np.argmin(losses))])
        self.valid, self.reason = True, None
        return self

    def transform(self, logits: np.ndarray) -> np.ndarray:
        if not self.valid:
            raise RuntimeError(f"calibración no válida: {self.reason}")
        return _softmax(logits / self.temperature)
