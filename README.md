# futuros — scanner multiinstrumento (ES / NQ / GC)

Investigación de un scanner de futuros con order flow, replay causal y modelo probabilístico calibrado.
**Solo replay y paper. La cuenta real está deshabilitada por diseño (D10).**

## Documentos fuente (fase 0, cerrada el 3-oct-2026)

1. [Plan técnico](docs/Plan_Tecnico_Trading_Multiinstrumento_Jev.md) — arquitectura, EV/RAEV, roadmap.
2. [Especificación MVP v1](docs/Especificacion_MVP_v1.md) — decisiones D01–D12, LR-v1, EXEC-v1, contratos internos, backlog ENG-01..11.
3. [Protocolo de datos y validación v1](docs/Protocolo_Datos_Validacion_v1.md) — accesos, muestra piloto, pruebas de aceptación, folds, gates.

Decisiones de implementación: [docs/adr/](docs/adr/).

## Estado del backlog

| Ticket | Estado | Dónde |
|---|---|---|
| ENG-01 Contratos y reloj inyectable | hecho | `src/trading_scanner/contracts`, `src/trading_scanner/clock` |
| ENG-02 Registry y selección causal de contrato | hecho | `src/trading_scanner/registry` |
| ENG-03 Adapter Databento | hecho sobre fixture real de 1 min; validación sobre la muestra completa al terminar la descarga | `src/trading_scanner/adapters/market`, ADR-003 |
| ENG-04 Libro por F_LAST y quality gate | hecho (sintético + minuto real); validar en muestra completa | `src/trading_scanner/orderbook`, `src/trading_scanner/quality` |
| ENG-05 Replay causal, barras y features v1 | hecho (determinismo + futuro no cambia pasado); validar en muestra completa | `src/trading_scanner/replay`, `src/trading_scanner/features` |
| ENG-06 LR-v1 máquina de estados y candidatos READY | hecho (ejemplo positivo + 6 rechazos + cooldown/fusión/duplicados/conflicto/short) | `src/trading_scanner/setups/liquidity_reversal` |
| ENG-07 EXEC-v1 y labeler | siguiente | — |
| ENG-04..11 | pendiente | — |

Accesos pendientes del usuario (protocolo §2): cuenta Databento (`DATABENTO_API_KEY`) y cuenta TypeSafe/Jev (`TYPESAFE_API_KEY`). Nunca en el repo.

## Desarrollo

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
.venv/Scripts/python -m pytest
```

`data/` y `artifacts/` están ignorados por git: ahí van raw/curated y modelos/reportes. Los archivos de `configs/instruments/` llevan `metadata_verified: false` hasta contrastarlos con las definitions del proveedor (ENG-03).
