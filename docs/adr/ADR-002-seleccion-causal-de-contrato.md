# ADR-002 — Selección causal de contrato y calendario (ENG-02)

**Fecha:** 2026-10-03 · **Estado:** aceptada · **Spec:** MVP v1 §2.1

## Regla implementada

Al inicio de la sesión `S` para un root:

1. Candidatos: contratos outright del root con `expiry >= S` (ordenados por vencimiento).
2. Elegibilidad: se excluye un contrato si el número de **sesiones de bolsa estrictamente posteriores a `S` hasta e incluyendo su `cutoff`** es `<= 5`, con `cutoff = min(first_notice_date, last_trading_date)` entre los que existan. Un contrato con `cutoff < S` también se excluye.
3. Se toman los **tres primeros elegibles** por vencimiento.
4. Volumen: se consulta **solo** la sesión completa anterior a `S` (`calendar.previous_session(S)`). La fuente de volumen recibe esa fecha explícita; el selector nunca pide `S` ni fechas posteriores. Un test lo verifica con una fuente que explota si se le pide el futuro.
5. Gana el mayor volumen; empate → vencimiento más cercano.
6. Sin candidatos, sin metadata (`tick_size`/`point_value`/fechas) o sin ningún volumen válido (> 0) → `ContractUnresolvedError` con código `CONTRACT_UNRESOLVED`. No hay fallback silencioso al front month.
7. El resultado (`ContractSelection`) es inmutable y lleva la lista de considerados, el volumen usado y la fecha de volumen, para auditoría.

## Calendario

`TradingCalendar` = lunes–viernes menos `holidays`, con `half_days` marcados. Es un calendario de **investigación**: las fechas de festivos y medias jornadas se cargan de `configs/sessions/*.yaml` y deben contrastarse con el calendario oficial de CME antes de materializar manifiestos (protocolo §3.1). En media jornada la sesión se excluye del piloto si no cabe la ventana 09:35–11:30 NY (D02); el calendario lo expone con `is_pilot_session`.

## Consecuencias

- El "5 días hábiles" se interpreta como sesiones del calendario del proyecto, no días naturales.
- El adaptador de broker real deberá respetar límites más restrictivos; esta regla es control de investigación.
- Los niveles previos (F08) se calculan con la historia del contrato elegido; el selector expone `contract_id` y no una serie continua.
