# ADR-001 — Unidades, tiempo y validación de contratos (ENG-01)

**Fecha:** 2026-10-03 · **Estado:** aceptada

## Decisiones

1. **Precio en ticks enteros.** Todo precio interno es `int` en ticks del contrato. La conversión `Decimal → ticks` es exacta y falla si el precio no cae en la rejilla del `tick_size`; nunca se redondea en silencio. Volumen en contratos enteros; duración en segundos; timestamps en nanosegundos UTC (`int`).
2. **`Decimal` para metadata monetaria.** `tick_size`, `point_value`, `tick_value` son `Decimal`. El registro rechaza un contrato si `tick_value != tick_size × point_value` (spec §2.1).
3. **`null` significa ausencia.** Ningún modelo convierte `None` en 0. Los ratios con denominador 0 son `None` con `missing_reason`.
4. **Invariante de disponibilidad.** `available_at_ns >= ts_event_ns` en todo `MarketEvent`. Un evento no puede estar disponible antes de ocurrir. Si la disponibilidad es estimada, el flag `availability_estimated` va en `quality_flags`.
5. **Libro cruzado no se corrige.** Los validadores de contrato comprueban tipos y unidades; las anomalías de mercado (precios cruzados, tamaños raros) son trabajo del quality gate (ENG-04), que las marca y excluye, no las arregla.
6. **Reloj inyectable.** Ningún módulo llama `time.time()`/`datetime.now()`. Reciben un `Clock` (`SystemClock`, `ManualClock`, `ReplayClock`). El `ReplayClock` solo avanza con `available_at_ns`.
7. **Zonas horarias por fecha.** Las ventanas se definen en `America/New_York` y se convierten a UTC por fecha con `zoneinfo`; `America/Hermosillo` es solo presentación. No existe un offset fijo anual (spec §2).
8. **Modelos inmutables.** Los contratos internos (`Candidate`, `Decision`, `Outcome`, …) son `frozen=True`; una corrección crea una versión nueva, no muta la anterior.

## Consecuencias

- Los tests de ENG-01 verifican rejilla de ticks, identidad tick_value, DST (marzo/noviembre) y que `None` sobreviva la serialización.
- Cualquier módulo que necesite "ahora" declara su dependencia del reloj en el constructor.

## Nota de entorno

`zoneinfo` en Windows no trae base de datos de zonas horarias: `tzdata` es dependencia obligatoria del paquete (sin ella `ZoneInfo("America/New_York")` falla al importar el reloj).
