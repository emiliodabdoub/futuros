# Especificación del MVP — futuros y order flow

**Versión:** 1.0 · **Fecha:** 3 de octubre de 2026  
**Proyecto:** scanner multiinstrumento con Jev y modelo probabilístico calibrado.  
**Documento base:** [Plan técnico general](Plan_Tecnico_Trading_Multiinstrumento_Jev.md).  
**Protocolo complementario:** [Datos, accesos y validación](Protocolo_Datos_Validacion_v1.md).

## 1. Resultado de esta fase

Quedan definidas las decisiones de diseño necesarias para comenzar la ingeniería: universo, horarios, datos mínimos, primer setup, contratos de información, etiquetas y pruebas. Son una especificación de investigación; los umbrales numéricos no han demostrado rentabilidad.

**Confirmado por el usuario:** continuar con futuros y order flow. El usuario aún no tiene acceso a Databento ni a TypeSafe/Jev.

**Estado de la fase 0:** especificación documental terminada; factibilidad de proveedores pendiente de acceso, permisos, cotización y prueba. No se han adquirido datos, consultado APIs autenticadas, desarrollado el motor ni enviado órdenes.

El primer incremento será un replay simultáneo de ES/NQ/GC que detecte Liquidity Reversal y registre candidatos. Después se añadirá clasificación Jev, calibración y selección. La versión completa del MVP incluirá también Trend Continuation y Breakout, en experimentos separados.

## 2. Decisiones cerradas para investigación

| ID | Decisión v1 | Condición para cambiarla |
|---|---|---|
| D01 | ES, NQ y GC; contratos outright concretos | Nuevo experimento versionado |
| D02 | Ventana común de nuevas entradas: 09:35–11:30, America/New_York | Validación posterior de otras sesiones |
| D03 | Salida máxima por tiempo: 15 minutos; cierre de toda posición a las 11:45 | Nueva política de outcomes |
| D04 | Contexto de 1/5/15 minutos; detección por eventos | Benchmark y prueba causal |
| D05 | Databento como proveedor candidato; MBP-10 para piloto | Cobertura/licencia/costo comprobados |
| D06 | Liquidity Reversal primero; los otros dos después | No activarlos por falta de señales del primero |
| D07 | Un contrato por operación en simulación; una posición total | Modelo de impacto y riesgo validado |
| D08 | Jev clasifica; modelo local aprende outcomes | Ablación OOS y shadow |
| D09 | Sin selección por porcentaje de acierto aislado | EV neto y riesgo son obligatorios |
| D10 | Replay y paper; cuenta real deshabilitada | Gate futuro explícito |
| D11 | Plataforma/prop firm intercambiable | Elegir después de validar y confirmar acceso |
| D12 | Calendario macro bloquea entradas; noticias textuales posteriores | Histórico point-in-time disponible |

La ventana elegida es una decisión de alcance, no el horario oficial de negociación de estos contratos. En media jornada se excluye la sesión del piloto si no cabe la ventana completa. La interfaz mostrará también America/Hermosillo, con conversión por fecha; no se fijará una equivalencia horaria para todo el año.

### 2.1 Contratos y cambio de vencimiento

El catálogo almacenará `venue`, `root`, `expiry`, `tick_size`, `point_value`, `currency`, primera fecha de aviso cuando corresponda, vencimiento y calendario de negociación. La carga del registro debe comprobar que `tick_value = tick_size × point_value`.

Al inicio de cada sesión, escoger entre los próximos tres vencimientos outright elegibles el de mayor volumen en la sesión completa anterior, utilizando únicamente información disponible en ese momento. Excluir contratos a cinco o menos días hábiles de la primera fecha de aviso o último día de negociación, tomando el primero de ambos que aplique. Ante empate, escoger el vencimiento más cercano elegible. Sin metadata o volumen previo válido: `CONTRACT_UNRESOLVED`.

Congelar el contrato durante la sesión. Para el contrato elegido, sus niveles previos deben calcularse con su propia historia; no transferir niveles de una serie ajustada ni del vencimiento anterior. El período excluido es un control de investigación; el adaptador real deberá respetar cualquier límite más restrictivo del broker.

## 3. Datos mínimos y disponibilidad temporal

### 3.1 Fuente canónica

Piloto propuesto: `MBP-10` para trades y los diez mejores niveles, más definiciones y estado del mercado cuando estén disponibles. Databento documenta que MBP-10 contiene cambios del libro y trades; por eso no sumaremos otra vez un stream separado de trades. [Esquema oficial](https://databento.com/docs/schemas-and-data-formats/mbp-10).

MBP-1 será un modo de menor capacidad si necesitamos reducir costos: conserva trades y mejor bid/ask, pero deshabilita features de profundidad. No se mezclarán sus resultados con la variante MBP-10 bajo el mismo nombre de modelo. [Esquema oficial](https://databento.com/docs/schemas-and-data-formats/mbp-1).

MBO se reserva para estudiar colas y reconstrucción por orden después de comprobar que aporta valor. La primera política usará entradas y salidas que toman liquidez, evitando afirmar fills de órdenes pasivas sin un modelo de cola.

### 3.2 Contrato del evento normalizado

```text
MarketEvent
  schema_version: string
  source: string
  dataset: string
  contract_id: string
  channel_id: int | null
  sequence: int | null
  record_index: int
  ts_event_ns: int
  ts_vendor_recv_ns: int | null
  ts_local_recv_ns: int | null
  available_at_ns: int
  event_type: TRADE | BOOK | STATUS | RESET | CORRECTION
  price_ticks: int | null
  size_contracts: int | null
  aggressor: BUY | SELL | UNKNOWN
  bid_levels: list[price_ticks, size_contracts, order_count]
  ask_levels: list[price_ticks, size_contracts, order_count]
  quality_flags: list[string]
  raw_partition_hash: string
```

Los flags de final de evento y el orden dentro de cada mensaje se conservan. El adapter debe verificar si los niveles representan el estado anterior o posterior a un trade; no inferir el agresor con cotizaciones posteriores. No asumir que saltos de secuencia en un stream filtrado por instrumento son pérdida de paquetes: contrastar la semántica de canal y filtros del proveedor.

### 3.3 Tiempo causal

- En vivo, `available_at = recepción local + normalización completada`.
- En replay, usar recepción del proveedor más retraso sintético de distribución; este timestamp no se presenta como recepción histórica de nuestro equipo.
- Sin recepción histórica, usar tiempo de evento más retraso modelado y marcar `availability_estimated=true`.
- Orden global del replay por disponibilidad; desempates por fuente/canal/secuencia/índice. Preservar orden del mismo canal.
- Las barras usan intervalos `[inicio, fin)`. Se finalizan con un margen de 250 ms en el piloto. Un evento posterior al margen no reescribe una decisión ya tomada.
- Datos tardíos se conservan como revisión, con flag. Medir porcentaje y sensibilidad a margen de 100/500 ms.
- En una llamada Jev, el snapshot queda congelado; la respuesta solo existe cuando llega o cuando vence el retraso modelado.

### 3.4 Calidad operativa

Un libro sin cambios puede seguir siendo válido: su edad por sí sola no demuestra desconexión. Usar heartbeat/conexión/estado de canal; durante esta ventana activa bloquear un contrato si no hay ningún evento suyo durante 5 segundos. Registrar que es un umbral operativo, no una prueba universal de feed caído.

Bloquear candidatos si hay reset sin recuperación, precios cruzados persistentes, tick inválido, cantidad negativa, metadata incompleta o menos de 95% de volumen con agresor conocido en la ventana necesaria. Tras gap, recuperar estado y recalentar las ventanas afectadas. Si compromete ATR/régimen o referencias del día, excluir el resto de la sesión de ese contrato.

## 4. Catálogo mínimo de features

Usar tick como unidad de precio en reglas, contratos para volumen y segundos para duración. `null` indica ausencia; no sustituirlo por cero.

| ID | Definición v1 | Disponibilidad |
|---|---|---|
| F01 | Último trade, mejor bid/ask, spread en ticks | Evento disponible |
| F02 | OHLC y volumen 1m/5m/15m | Barra finalizada |
| F03 | ATR14 simple de true range en barras 1m completas | 15 cierres mínimos; 60 barras para warm-up global |
| F04 | `delta(w) = buy_volume(w) - sell_volume(w)` | Ventanas trailing 5/10/60s |
| F05 | `delta_ratio(w) = delta(w)/(buy+sell)` | Denominador > 0 y calidad de agresor válida |
| F06 | CVD desde inicio de sesión de bolsa | Solo delta conocido; unknown separado |
| F07 | VWAP de trades desde inicio de sesión | Precio × tamaño, hasta as-of |
| F08 | High/low del día anterior en ventana 09:30–16:00 NY | Historia completa del contrato elegido |
| F09 | High/low de opening range 09:30–09:35 NY | A partir de 09:35:00.250 |
| F10 | Distancia a nivel/VWAP, en ticks y ATR | Snapshot causal |
| F11 | Imbalance depth de los primeros 5 niveles | `(bid_qty-ask_qty)/(bid_qty+ask_qty)` |
| F12 | Mediana de imbalance depth en 1 segundo | Mínimo 5 observaciones; ponderación por tiempo |
| F13 | Efficiency ratio de 12 cierres 5m | Movimiento neto / suma de movimientos absolutos |
| F14 | Pendiente: `(close_5m[t]-close_5m[t-6])/ATR_5m14` | Barras completas |
| F15 | Volumen 5s relativo a mediana de bloques previos 5s en 30min | Excluir bloque actual; mínimo 100 bloques válidos |
| F16 | Volumen de agresor contra nivel desde inicio de sweep | Se congela al reclaim |
| F17 | Duración y profundidad de sweep | Estado del setup |
| F18 | Footprint por tick de barra 1m completa | Trades asignados causalmente |
| F19 | Tiempo hasta/since macro, categoría, bloqueo | Calendario conocido as-of |
| F20 | Retornos 5m relativos ES/NQ y correlación trailing | Misma disponibilidad y ventanas completas |

ATR: `TR = max(high-low, abs(high-prev_close), abs(low-prev_close))`; usar media simple de los últimos 14 TR, sin cambiar a Wilder silenciosamente. Para ratios, denominador 0 implica missing o estado neutro documentado.

Footprint diagnóstico: imbalance diagonal comprador si `buy(p)/sell(p-tick) >= 3` y ambos lados tienen volumen positivo y suma >= 10 contratos; vendedor simétrico. Tres niveles consecutivos forman un stacked imbalance. Cero en denominador se registra por separado. Estos parámetros no bloquean el setup inicial y su utilidad se evaluará por ablación.

### 4.1 Régimen determinista inicial

`TREND_UP` si F13 >= 0.35 y F14 >= 1; `TREND_DOWN` si F13 >= 0.35 y F14 <= -1; `RANGE` si F13 <= 0.20; resto `TRANSITION`. Falta de warm-up produce `UNKNOWN`.

Confirmar un cambio con dos cierres consecutivos 5m; no reemplazar retroactivamente los estados anteriores. Volatilidad shock si el TR de la última barra 1m supera 3 × ATR previo a esa barra. El shock bloquea entradas durante 5 minutos, extendidos si vuelve a ocurrir.

Este régimen es baseline. La clasificación Jev se almacena aparte; no puede cambiar los hechos de las features ni la hora de confirmación.

## 5. Liquidity Reversal: reglas ejecutables LR-v1

### 5.1 Convenciones y parámetros

Para long, buscar barrida de un nivel bajo y reclaim al alza. Para short invertir signos y bid/ask. En la primera versión solo se usan high/low del día anterior y del opening range; no swings discrecionales.

| Parámetro | Valor de investigación |
|---|---|
| Proximidad para armar | `max(2 ticks, ceil(0.25 × ATR1m_ticks))` |
| Penetración mínima | 2 ticks |
| Penetración máxima | `floor(0.75 × ATR1m_ticks)` |
| Tiempo para reclaim | 30 segundos desde primer cruce |
| Reclaim long | Un trade al menos 1 tick encima del nivel |
| Confirmación de flujo | Delta ratio 5s >= +0.20 long; <= -0.20 short |
| Volumen en esos 5s | >= 50% de mediana de bloques 5s previos de F15 |
| Confirmación de movimiento | Trade 2 ticks más allá del precio de reclaim en dirección favorable |
| Ventana de confirmación | 10 segundos después del reclaim |
| Stop | Extremo del sweep ± buffer de 2 ticks |
| Riesgo de precio admisible | 4 ticks a `ceil(1.5 × ATR1m_ticks)` |
| Target | 2 veces el riesgo de precio desde fill real |
| Tiempo máximo tras fill | 15 minutos |
| Cooldown mismo nivel/dirección | 10 minutos; máximo 2 intentos por día |
| TTL candidato | 2 segundos desde confirmación |

ATR y límites de penetración se congelan al armar el nivel. Si máximo < mínimo no se arma. Los ratios y volúmenes de confirmación se evalúan en el instante del trigger; no dependen de una vela futura.

### 5.2 Máquina de estados

1. **IDLE:** verificar sesión, referencias, warm-up, calendario y calidad. Para long, el precio debe estar arriba del nivel bajo al armar; para short, debajo del nivel alto.
2. **ARMED:** nivel identificado y distancia dentro del límite. Expira a los 5 minutos si no hay sweep. Congelar nivel, ATR y límites. Si dos niveles están a <= 2 ticks, fusionarlos: prioridad día anterior y guardar las dos referencias.
3. **SWEPT:** primer trade que cruza al menos 2 ticks. Guardar tiempo y extremo. Invalidar inmediatamente si penetra más que el máximo o no recupera en 30 segundos.
4. **RECLAIMED:** primer trade >= nivel+1 tick para long; <= nivel-1 para short. Guardar precio/tiempo y congelar extremo del sweep. Si antes del trigger se extiende ese extremo, invalidar; no moverlo a conveniencia.
5. **READY:** en los próximos 10 segundos coinciden movimiento favorable de 2 ticks, volumen mínimo y delta a favor. Verificar riesgo/spread y ausencia de bloqueo; crear candidato inmutable.
6. **PENDING_CLASSIFICATION:** consultar Jev; comparar respuesta con snapshot original. Si llega después del TTL o el precio se alejó > 2 ticks de referencia, expirar.
7. **SELECTED/REJECTED:** ranking y risk engine registran decisión. Un candidato rechazado también tiene outcome contrafactual para investigación.
8. **CONSUMED/EXPIRED/INVALIDATED:** iniciar cooldown. No reciclar mismo evento con IDs nuevos.

Máximo spread para nueva entrada: ES 2 ticks, NQ 3, GC 3. Son límites iniciales por contrastar en la muestra, no spreads observados.

Depth imbalance, proxy de absorción, divergencia CVD y footprint entran inicialmente como features explicativas. La regla mínima exige flujo agresor y recuperación de precio; no obliga a que Jev declare “absorción”. Así podemos medir su aporte sin descartar de antemano los casos donde no coincide con nuestras reglas.

### 5.3 Invalidation y duplicados

- Barrida y reclaim fuera de ventana, shock, evento macro bloqueado o calidad insuficiente invalidan el candidato.
- Un `UNKNOWN` en régimen por falta de datos bloquea; tendencia contraria por sí sola no bloquea LR-v1 y se evalúa como contexto.
- Un candidato por contrato/dirección/evento. Niveles no fusionados que disparen al mismo tiempo compiten; elegir el más antiguo armado y registrar los demás como duplicados del evento.
- Long y short READY simultáneos sobre el mismo contrato → `CONFLICTING_SETUPS` y abstención para ese contrato en ese epoch.

### 5.4 Ejemplo sintético de aceptación

Nivel bajo = 20,000 ticks; ATR = 20 ticks. Arma desde arriba. Trade a 19,997 → sweep de 3 ticks; en 8 segundos retorna a 20,001. Cuatro segundos después llega a 20,003, delta ratio 5s = +0.25 y volumen suficiente → READY. Stop = 19,995. Si se llena a 20,004, riesgo = 9 ticks y target = 20,022. Las comisiones y el slippage de salida pueden hacer que el resultado neto sea distinto de +2R o -1R.

Casos negativos obligatorios: sin reclaim en 30s; profundidad 16 ticks con ATR20; delta contrario; agresor desconocido >5%; respuesta Jev tardía; nuevo mínimo después de reclaim. Cada uno debe terminar sin orden y con motivo distinto.

## 6. Setups posteriores, definidos pero deshabilitados al inicio

No se evaluarán como sustitutos elegidos tras observar pérdidas de LR. Cada alta genera una versión y su propio registro de búsqueda.

### 6.1 Trend Continuation TC-v1

- Precondición: `TREND_UP/DOWN` confirmado; 60 minutos de contexto válidos.
- Al cierre de una barra 1m, definir impulso con las últimas 5 barras: desplazamiento direccional neto >= 1.5 × ATR1m de antes de esas barras y efficiency ratio de cierres >= 0.60.
- Congelar origen, extremo y tamaño del impulso. Elegir el primer impulso elegible mientras no exista uno armado; no desplazar su origen después.
- En las siguientes 5 barras, pullback de 25–60% del impulso; invalidar por >60% o vencimiento.
- Una vez dentro de esa banda, trigger por trade que supere high de la última barra 1m completa para long, o low para short, más 1 tick, con delta ratio5s a favor >=0.20 en magnitud y volumen de confirmación de LR.
- El extremo del pullback se congela al trigger. Stop 2 ticks detrás, target 2R, máximo 15min y riesgo/spread/TTL de LR.
- Sin retest adicional, trailing stop ni piramidación. Un intento por impulso; cooldown10min.

### 6.2 Breakout BO-v1

- Cada minuto completo, evaluar las 15 barras previas de 1m, sin incluir la barra en formación.
- Armar un rango cuando anchura <= 2 × ATR14 y efficiency ratio de esos cierres <=0.25. Congelar high/low y ATR; no mover el rango una vez armado.
- Expirar si no rompe en 10min. Ruptura: trade >= high+2 ticks para long o <= low-2 para short.
- Exigir 5 segundos completos de aceptación: todos los trades posteriores a ruptura hasta confirmación permanecen fuera del límite, mínimo 5 trades, delta ratio5s a favor >=0.20 y volumen5s >= mediana previa de F15.
- Si reentra antes de confirmar, invalidar ese intento. Para nuevo rango se requiere cooldown10min.
- Stop long = high-2 ticks; short = low+2 ticks. Aplicar límites de riesgo, target2R y tiempo de LR. Un stop excesivamente estrecho rechaza, no se amplía después de ver resultado.

## 7. Política de ejecución simulada EXEC-v1

### 7.1 Entradas

Un contrato, orden marketable-limit IOC. Long: límite = ask disponible al enviar + 2 ticks; short: bid - 2 ticks. Al llegar tras latencia, consumir los niveles ejecutables hasta ese límite. Cantidad disponible insuficiente para un contrato → NO_FILL. No descansar en cola ni perseguir el precio; reintento deshabilitado.

Stop absoluto predefinido en candidato; tras fill calcular distancia real y rechazar exposición adicional si dejó de cumplir presupuesto. La simulación debe reflejar que un fill ya recibido no puede borrarse: si fill inesperado viola límites, cerrar y registrar `EMERGENCY_EXIT`, con su P&L. El target se calcula desde fill siguiendo la fórmula 2R fijada antes del envío.

### 7.2 Salidas y barreras

Usar salidas sintéticas que toman liquidez para evitar fills pasivos inventados:

- Long: stop activa al observar bid <= stop; target activa con bid >= target.
- Short: stop activa al observar ask >= stop; target activa con ask <= target.
- Después del trigger aplicar retraso de salida y ejecutar contra libro disponible. No garantizar precio de barrera.
- TIME_EXIT al llegar a 15min o 11:45 NY, lo primero; ejecutar también con retraso/costos.
- Si coinciden triggers en un timestamp con orden desconocido, prioridad conservadora stop → time → target. Guardar flag de ambigüedad.

Estas reglas definen el simulador, no afirman cómo disparará un stop de un broker. Integrar bracket real exige verificar trigger, OCO y protección y reevaluar la política con esa semántica.

### 7.3 Fricción y labels

Inicialmente explorar comisión round-trip de USD6 por contrato **solo como escenario sintético de ingeniería**, no tarifa de broker. Stress con USD10 y con 1/2 ticks adicionales adversos por salida. Las métricas con este placeholder no permiten promoción live. Sustituir por tarifa vigente de cuenta antes de evaluación económica final.

Spread ya está en bid/ask; no restarlo dos veces. Slippage se registra como diferencia con referencia, más impacto adicional solo cuando corresponda. En gap más allá de los diez niveles o sin libro fiable: `UNPRICED_EXIT`, no asumir fill a último precio. Reportar intervalos afectados y sensibilidades; ninguna política se aprueba con exposiciones sin salida contabilizable.

Etiquetas: `TARGET_TRIGGERED`, `STOP_TRIGGERED`, `TIME_EXIT`, `EMERGENCY_EXIT`, `NO_FILL`, `INVALID_DATA`. Guardar aparte `net_positive`, P&L_USD, P&L_R, MAE/MFE y tiempos. La barrera que dispara no garantiza el signo del P&L.

## 8. Jev: integración cerrada para el piloto

### 8.1 Modelo y condiciones

La documentación consultada lista `jev-1.13.0`, permite seleccionar versión y señala que la adaptación se hace mediante estado/preguntas, sin fine-tuning por cliente. Fijaremos ese ID si está disponible al abrir la cuenta; un cambio requiere nuevo experimento. [Fuente oficial](https://docs.typesafe.ai/models).

Las preguntas se escribirán en inglés para la prueba inicial; la UI será en español. El paquete guardará rubricas, respuestas y modelo resuelto. Acceso y latencia siguen sin probarse.

### 8.2 Estado enviado

`candidate_id` interno, lado propuesto, nivel y su antigüedad, ATR, sweep/reclaim, últimas doce barras1m normalizadas, retornos5m/15m, delta5/10/60s, volumen relativo, VWAP, cinco niveles agregados de profundidad, imbalance y calidad. Indicar unidades y faltantes. Sin datos de cuenta, capital, credenciales ni instrucciones de ejecución.

Presupuesto inicial de 4,000 tokens por petición; medición real pendiente. Una petición por candidato con todas las preguntas; no una petición por tick. Deadline1.5s y TTL2s. Sin retry para candidatos vivos; retries offline permitidos con registro.

### 8.3 Rubricas v1

| Pregunta | Tipo | Opciones / criterio |
|---|---|---|
| context_structure | Choice | uptrend, downtrend, range, transition, insufficient_data; describir continuidad de máximos/mínimos y retornos dados |
| absorption_evidence | Choice | buyer_absorption, seller_absorption, neither, insufficient_data; alto flujo agresor con desplazamiento limitado y recuperación; no inferir identidad |
| flow_alignment | Choice | supports, opposes, mixed, insufficient_data; evaluar exclusivamente lado propuesto vs ventanas de delta |
| reversal_quality | Score | 0: barrida sin recuperación; 1: recuperación débil/contradictoria; 2: recuperación y flujo alineados; 3: recuperación sostenida con movimiento y contexto compatibles |
| evidence_sufficiency | Choice | sufficient, partial, insufficient; evaluar datos presentes y vigentes, no atractivo financiero |

Cada pregunta debe mencionar explícitamente campos y lado; no depender del ID de pregunta para transmitir significado. Score es escala ordinal, no porcentaje de acierto. Una pregunta no puede leer respuestas de otra en la misma llamada.

La respuesta normalizada preserva distribución completa y confianza cuando exista. Validar todas las opciones, suma con tolerancia1e-6 y ausencia de NaN. `insufficient` no se cambia por neutral ni se renormaliza eliminándolo.

### 8.4 Ablación y fallback

Experimento A: cuantitativo sin Jev. B: mismas features + distribuciones Jev; mismo universo de candidatos y splits. Comparar además baseline A con retraso artificial igual a B para separar aporte de clasificación del costo de esperar.

Si Jev falla, candidato B expira/rechaza. A continúa solo como rama de investigación identificada; no sustituir silenciosamente B. Operación final escogerá una rama validada y registrada, sin cambiarla según cuál ganó ayer.

El conocimiento histórico de Jev no puede verificarse con un backtest convencional. Resultados retrospectivos B se consideran exploratorios; mantener prueba prospectiva con rubricas congeladas antes de inferir mejora económica.

## 9. Modelo, selección y riesgo

### 9.1 Qué se estima

Separar modelo de fill del de outcomes tras fill. Modelo inicial de outcomes multinomial regularizado; challenger tabular solo tras baseline. Conservar TIME_EXIT y EMERGENCY_EXIT; si una clase carece de soporte, bloquear promoción o usar una agrupación definida antes del test.

EV se calcula desde distribución de P&L neto y probabilidad de fill condicionadas a política. Modelar medias por outcome con shrinkage hacia dataset train; TIME_EXIT no equivale a cero. No usar ganancias medias de test para calcular EV de test. Calibración exclusivamente en bloque independiente.

### 9.2 Ranking v1

Epoch cada segundo. Tomar candidatos cuya respuesta esté disponible y TTL no haya expirado. Revalidar cotización, calidad, bloqueos y estado de cuenta. Registrar candidatos ausentes por timeout; no describir el ranking como completo si un instrumento quedó sin datos.

Con una posición global, la correlación no permite abrir ES y NQ a la vez. Conservar retornos y grupos para analizar concentración y para la ampliación posterior. Ranking inicial por unidad de riesgo:

```text
R_price_USD = distancia entrada-stop × valor monetario por tick
EV_R = EV_net_USD / R_price_USD
tail_R = ExpectedShortfall95(max(0, -net_PnL_USD)) / R_price_USD
uncertainty_R = max(0, EV_R - lower95_EV_R)
RAEV_R = EV_R - 0.10 × tail_R - uncertainty_R
```

Expected Shortfall usa la media del peor 5% de pérdidas con convención de cuantiles declarada. `lower95` procede de ensembles/bootstrap temporal del train/calibration; no es un intervalo garantizado para un trade individual. Si no hay soporte para cola/uncertainty → NO TRADE.

Umbrales de investigación: EV_R >=0.10, lower95_EV_R >0, RAEV_R >0 y demás vetos. Empate a <=0.01R: menor costo relativo, luego menor riesgo_USD por contrato y finalmente orden fijo ES/NQ/GC. Congelar esta política antes de test; λ0.10 y thresholds son hipótesis, no óptimos conocidos.

### 9.3 Riesgo paper

Perfil sintético para pruebas: presupuesto de pérdida acumulada USD5,000; límite interno diario USD500; máximo riesgo planificado por trade USD100 incluidas comisiones y reserva de salida. Si un contrato mini no cabe, abstenerse. No fraccionar contratos ni atribuir fills de micros usando el libro del mini.

El ledger por contrato sin estos límites se conserva para investigación; el ledger seleccionable aplica el perfil paper y puede tener muy pocos trades. Si posteriormente se eligen MES/MNQ/MGC, adquirir sus datos y validar la política de ejecución correspondiente.

Stops pueden superar presupuesto en gaps. Daily gate incluye P&L realizado, unrealized liquidable, fees y reservas. Alcanzar pérdida diaria → bloquear entradas y cerrar posición según política; no esperar señal de Jev. No martingale, averaging-down, simultaneidad ni gestión de cuentas de terceros.

## 10. Contratos internos y registro

```text
FeatureSnapshot:
  id, as_of, max_input_available_at, feature_version,
  contract_spec_version, values, units, missing_reasons, quality

Candidate:
  id, source_event_id, snapshot_id, contract_id, setup_version,
  direction, level_id, stop_ticks, target_rule, entry_policy,
  created_at, expires_at, state_history

ClassificationResult:
  id, candidate_id, state_hash, questions_hash, requested_model,
  resolved_model, requested_at, received_at, distributions,
  confidence_fields, validation_status, usage, failure_reason

Prediction:
  id, candidate_id, model_bundle_id, calibration_id,
  p_fill, p_outcomes_given_fill, p_net_positive_given_fill,
  EV_USD, EV_R, lower95_EV_R, tail_R, RAEV_R, support_status

Decision:
  epoch, candidate_ids, excluded_reasons, ordered_scores,
  selected_id_or_null, action, risk_snapshot_id, policy_hash

Outcome:
  candidate_id, execution_policy_hash, simulated_or_observed,
  fill_at, fill_price, trigger_at, exit_at, exit_price,
  terminal_reason, net_positive, costs, PnL_USD, PnL_R,
  label_start, label_end, data_quality, ambiguity_flags
```

Un hash de ejecución incluye costos/latencias, no solo código del setup. Las correcciones de labels crean una versión; los reportes anteriores mantienen manifiesto original. Rechazos y no-fills se conservan para explicar cobertura.

## 11. Backlog listo para la siguiente fase

| Ticket | Entregable de implementación | Dependencia | Prueba de aceptación |
|---|---|---|---|
| ENG-01 | Contratos y reloj inyectable | Este documento | Validación de unidades/tiempo |
| ENG-02 | Registry y selección causal de contrato | Metadata de muestra | Roll sin volumen futuro |
| ENG-03 | Adapter Databento y manifiestos | Acceso y licencia | Sin doble conteo; mapping exacto |
| ENG-04 | Normalización y quality gate | ENG-03 | Resets/gaps/stream filtrado |
| ENG-05 | Barras/features/replay | ENG-01/04 | Futuro no cambia pasado |
| ENG-06 | LR-v1 y eventos READY | ENG-05 | Ejemplo positivo y seis rechazos |
| ENG-07 | EXEC-v1 y labeler | ENG-04/06 | IOC/no-fill/gap/timeout |
| ENG-08 | Jev adapter/cache/rubricas | Acceso Jev, permiso datos | Deadline/versiones/faltantes |
| ENG-09 | Dataset/split/calibración | Outcomes suficientes | Purga global y test aislado |
| ENG-10 | Selector/riesgo/dashboard | ENG-09 | NO TRADE y ledger concurrente |
| ENG-11 | TC-v1 y BO-v1 | LR revisado; protocolo extendido | Sin reutilizar holdout consumido |

Los tickets describen trabajo futuro; no son componentes ya construidos. Una vez cumplidos accesos y factibilidad, el primer sprint implementará ENG-01 a ENG-05 y un replay de muestra, sin exigir rentabilidad como criterio de ingeniería.

## 12. Cierre y trazabilidad

Decisiones ya resueltas: futuros/order flow, ES/NQ/GC, proveedor candidato, horario acotado, LR primero, políticas explícitas y separación de investigación/ejecución. Pendientes externos: acceso a ambas APIs, licencia de datos derivados hacia Jev, costo real de muestra y semántica exacta del feed en prueba.

Fuentes consultadas el 3 de octubre de 2026:

- [Databento MBP-10](https://databento.com/docs/schemas-and-data-formats/mbp-10): cobertura del esquema; no demuestra disponibilidad contratada.
- [Databento MBP-1](https://databento.com/docs/schemas-and-data-formats/mbp-1): alternativa con mejor bid/ask.
- [TypeSafe Models](https://docs.typesafe.ai/models): modelo/versionado y adaptación mediante preguntas.
- [CME Gold](https://www.cmegroup.com/markets/metals/precious/gold-futures.html): identificación de GC y familia; metadata efectiva se verificará al ingerir.

Todos los parámetros y procedimientos propios de este documento son propuestas de diseño. Solo el protocolo complementario establece cómo convertirlos en evidencia comprobada.
