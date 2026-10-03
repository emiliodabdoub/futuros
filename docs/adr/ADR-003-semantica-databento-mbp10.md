# ADR-003 — Semántica del feed Databento MBP-10 y su mapeo a MarketEvent (ENG-03)

**Fecha:** 2026-10-03 · **Estado:** aceptada · **Evidencia:** fixture real ESU4 2024-09-10 13:30–13:31 UTC
(47,146 registros, 3,013 trades, 9,471 contratos) contrastado con los esquemas `ohlcv-1m` y `trades` del mismo minuto.

## Hechos verificados sobre datos reales

| Pregunta de la spec §3.2 | Resultado |
|---|---|
| ¿Los niveles de un registro de trade son el estado anterior o posterior? | **Anterior.** En 2,957 trades el libro del registro T coincide con el registro previo; en 0 con el siguiente; 56 ambiguos (sin cambio en el mejor nivel). El registro de libro que sigue al trade lleva `F_LAST` y es el estado posterior. |
| ¿Hay doble conteo si sumamos trades de MBP-10? | **No**, contando solo `action == T`: 9,471 = volumen `ohlcv-1m` = Σ `trades`. No se añade otro stream de trades. |
| ¿Agresor? | `side` del trade: `B` = comprador agresor → BUY; `A` = vendedor agresor → SELL; `N` → UNKNOWN. 100% conocido en el fixture. Nunca se infiere con cotizaciones posteriores. |
| ¿Precios en rejilla? | 0 precios fuera de la rejilla de 0.25. Precios en punto fijo 1e-9; `UNDEF_PRICE` marca nivel vacío. |
| ¿Orden y tiempo? | `ts_recv >= ts_event` en todos; `sequence` monótono. Flags vistos: 128 (`F_LAST`) en libro, 0 en trades. |
| `side == N` fuera de trades | Aparece en A/C/M (73/48/2); se mapea a BOOK sin agresor. Pendiente ENG-04: clasificar si son órdenes implícitas. |

## Decisiones de mapeo

1. `action` A/C/M/F/N → `BOOK`; T → `TRADE`; R → `RESET`. Un TRADE sin precio válido se degrada a `CORRECTION` con flag `TRADE_PRICE_UNDEF` en lugar de perderse.
2. Los registros BOOK no llevan `price_ticks` ni `size_contracts`: el precio del registro es el nivel tocado, no un trade.
3. Niveles con `UNDEF_PRICE` o tamaño 0 se omiten; se conservan hasta 10 por lado con `order_count`.
4. `available_at_ns = max(ts_recv, ts_event) + retraso_de_distribución` (100 ms base, 300 ms adverso, protocolo §7.1). `ts_recv` es recepción del proveedor, no nuestra; no se marca `availability_estimated`.
5. Flags trasladados a `quality_flags`: `F_LAST`, `F_SNAPSHOT`, `F_BAD_TS_RECV`, `F_MAYBE_BAD_BOOK`, más `BOOK_IS_PRE_TRADE` en trades y `PRICE_OFF_GRID` si cualquier precio no cae en la rejilla.
6. `raw_partition_hash` = primeros 16 hex del SHA-256 del archivo DBN. El hash completo vive en el manifiesto.
7. El adapter **no corrige nada**: libro cruzado, gaps de `sequence` y resets se marcan y los decide el quality gate (ENG-04).

## Consecuencias

- El límite de evento para el replay es `F_LAST`: las barras/features deben consumir hasta el registro con `F_LAST` antes de considerar el libro consistente.
- `status` se mapea aparte (`iter_status_events`) con `IS_TRADING`/`IS_QUOTING`; los cierres diarios de 21:00Z aparecen como `is_trading = N`.
- El fixture y los archivos raw son datos licenciados: viven en `data/` fuera de git; los tests de integración se omiten si no están.

## Rendimiento (medido 3-oct-2026 sobre el fixture de 47,146 registros)

| Etapa | Antes | Después | Cambio |
|---|---:|---:|---|
| Adapter → MarketEvent | 7,000 ev/s | ~30,000 ev/s | `to_ndarray(count=250k)` + columnas `.tolist()`; `BookLevel` pasa de modelo pydantic a `NamedTuple` (20 por evento); siempre con validación pydantic (más rápida que `model_construct`) |
| QualityGate + FeatureEngine | 3,800 ev/s | ~150,000 ev/s | sumas acumuladas de la ventana de agresor en vez de recorrer la deque en cada evento |

Estimación para la muestra: ES ≈ 47k registros/min en RTH → ventana 09:00–11:45 NY ≈ 8M eventos ≈ 5 min por contrato-día; 5 contratos × 10 sesiones ≈ 2 h en serie, ~30 min con un proceso por contrato. El adapter acepta `start_ns`/`end_ns` para saltar registros fuera de la ventana antes de construir el evento.
