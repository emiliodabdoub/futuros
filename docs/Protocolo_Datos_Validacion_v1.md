# Protocolo de datos, accesos y validación — futuros y order flow

**Versión:** 1.0 · **Fecha:** 3 de octubre de 2026  
**Especificación asociada:** [MVP v1](Especificacion_MVP_v1.md).  
**Estado:** protocolo definido antes de realizar experimentos. Accesos Databento y Jev aún no disponibles. No se han comprado datos ni probado el sistema.

## 1. Qué haremos primero

1. Abrir las cuentas de proveedor y verificar elegibilidad/licencias.
2. Obtener una cotización reproducible de una muestra de datos.
3. Implementar ingestión y replay de esa muestra cuando comience la fase de ingeniería.
4. Auditar eventos, volumen, timestamps, features y señales antes de entrenar.
5. Ampliar historia solo si la muestra pasa las pruebas técnicas y el costo es aceptable.
6. Evaluar modelos con bloques temporales separados y luego registrar decisiones prospectivas.

La muestra sirve para comprobar ingeniería y factibilidad. Diez sesiones no bastan para afirmar una ventaja estadística o fijar probabilidades comerciales.

## 2. Accesos: pasos concretos para el usuario

### 2.1 Databento

1. Crear cuenta desde [Databento](https://databento.com/).
2. Completar el perfil y los acuerdos correspondientes al dataset CME Group. El tipo de uso declarado debe coincidir con el uso real.
3. Comprobar si se aplican los créditos iniciales y sus condiciones en el dashboard.
4. Crear una clave para investigación; guardarla en un gestor de secretos o variable local `DATABENTO_API_KEY` cuando exista la implementación.
5. Obtener estimate para los contratos outright y períodos descritos en la sección 3; no descargar el dataset completo por defecto.
6. Revisar específicamente permiso para transformar datos y enviar features derivadas a un proveedor externo de IA. Si no está claro, solicitar confirmación al proveedor.

Databento publica acceso histórico por consumo y créditos iniciales; las condiciones de cuenta y costo exacto deben verificarse en la cotización. [Precios y licencias](https://databento.com/pricing).

### 2.2 TypeSafe / Jev

1. Acceder al sitio oficial [TypeSafe](https://typesafe.ai/) y su [consola](https://console.typesafe.ai/).
2. Crear cuenta o solicitar acceso si la consola lo requiere.
3. Comprobar disponibilidad del modelo y condiciones de uso.
4. Crear clave y guardarla localmente como `TYPESAFE_API_KEY`; no pegarla en chat ni en el repositorio.
5. Primera prueba con estado sintético, sin datos financieros licenciados. Validar autenticación, tipos, modelo resuelto y consumo.
6. Solo después de verificar permisos del feed, probar estados derivados del mercado.

La documentación actual admite `jev-1.13.0`; fijar versión para experimentos. Registrar límites efectivos de la cuenta y no dar por garantizada una cuota de documentación pública. [Modelos](https://docs.typesafe.ai/models), [referencia API](https://docs.typesafe.ai/api).

### 2.3 Comprobaciones y evidencia

| Acceso | Evidencia requerida | Estado actual |
|---|---|---|
| Databento | Consulta metadata/estimate autenticada y acuerdos aplicables | Pendiente |
| Jev | Respuesta válida a estado sintético, versión y uso registrados | Pendiente |
| Datos hacia Jev | Licencia compatible o confirmación del proveedor | Pendiente |
| Broker/prop | No requerido para investigación inicial | Se decide después |

No se confunden registro, clave generada y servicio funcionando: las dos primeras no prueban una llamada exitosa. No se necesita una evaluación de prop firm para esta fase.

## 3. Solicitud de datos preparada

### 3.1 Muestra de ingeniería

**Sesiones de evaluación de componentes:** 9–20 de septiembre de 2024, diez días laborables nominales. Verificar calendario de bolsa y disponibilidad antes de convertirlos en manifiesto. Este período pertenece al bloque inicial de entrenamiento, no a un test reservado.

**Universo:** roots ES, NQ y GC; resolver vencimientos concretos con metadata y volumen previo. Excluir opciones, spreads, TAS y productos con nombres parecidos.

**Datos:** MBP-10 y definiciones; estado del mercado si existe para la cobertura contratada. Para presupuesto, consultar también MBP-1 y comparar tamaño/costo. No comprar ambos streams completos si uno basta para el experimento.

**Contexto:** además de las diez sesiones, incluir historia previa necesaria para selección de contrato y high/low anterior. No recortar el archivo a las horas de entradas: se necesita sesión completa para referencias, CVD/VWAP y volumen causal de selección.

**Ventana UTC exterior preliminar para cotizar:** desde `2024-09-05T00:00:00Z` hasta `2024-09-21T00:00:00Z`, fin exclusivo. Antes de descargar, materializar los intervalos por calendario de bolsa y contrato; documentar cualquier ampliación por warm-up o disponibilidad de metadata. No afirmar que todos los contratos cotizan continuamente dentro de esa ventana.

Si una sesión no está disponible, dejar registro y reemplazarla por la siguiente sesión válida dentro del bloque train de 2024. No escoger sustituto por ganancias, número de setups o volatilidad retrospectiva.

### 3.2 Formato de la cotización/manifiesto

```json
{
  "request_id": "pilot-orderflow-v1",
  "provider": "Databento",
  "dataset": "GLBX.MDP3",
  "dataset_verified": false,
  "schema": "mbp-10",
  "roots": ["ES", "NQ", "GC"],
  "resolved_contracts": [],
  "start_utc_inclusive": "2024-09-05T00:00:00Z",
  "end_utc_exclusive": "2024-09-21T00:00:00Z",
  "cost_estimate_usd": null,
  "estimated_bytes": null,
  "license_verified": false,
  "derived_data_external_processing_allowed": null,
  "download_status": "NOT_STARTED"
}
```

`GLBX.MDP3` es el identificador candidato que deberá comprobarse en metadata. La documentación del esquema por sí sola no demuestra permisos/cobertura de la cuenta. La lista de contratos vacía es un bloqueo deliberado de descarga; no se sustituye automáticamente por todos los símbolos del dataset.

Evidencia a guardar: fecha de estimate, inputs exactos, derechos aplicables, costo antes/después de créditos, bytes, formatos y confirmación de cobertura. No fijar precio total con base en promociones o en los créditos de otra cuenta.

### 3.3 Historial para investigación posterior

Objetivo de cobertura inicial: enero de 2024 a septiembre de 2026, más contexto anterior requerido. Cotizar por tramos y adquirir incrementalmente; esto no autoriza una compra total.

La profundidad de historia real se decide con costo y disponibilidad. Si no alcanza para el protocolo temporal, rediseñar ventanas **antes** de mirar resultados. Una compra reducida permite desarrollar, pero no hereda los criterios de validación de un dataset de varios años.

### 3.4 Almacenamiento

Raw inmutable en DBN u otro formato nativo acordado; curated en Parquet y manifiestos legibles. Separar fuente, schema, contrato y fecha. Hash SHA-256 por archivo y hash global del manifiesto. Mantener índices/metadata separados del contenido licenciado.

No subir archivos crudos al repositorio ni enviar automáticamente el libro completo a Jev. Calcular features localmente y compartir únicamente lo permitido por licencia. Retención y backups deberán caber en esa licencia.

## 4. Pruebas de aceptación de la muestra

| Control | Procedimiento | Aceptación |
|---|---|---|
| Símbolos | Comparar definitions con contratos resueltos | Cero opciones/spreads/productos incorrectos |
| Precios | Convertir unidades fuente a ticks exactos | Cero precios inválidos sin explicación |
| Volumen | Reconstruir trade volume y contrastar un agregado equivalente | Diferencia 0 cuando filtros/definiciones coincidan; toda diferencia explicada |
| Doble conteo | Revisar trades incluidos en MBP y stream auxiliar | Una sola contribución por evento económico según adapter |
| Libro | Evaluar orden bid/ask y cantidades tras cada evento completo | Anomalías marcadas y excluidas; no corregidas silenciosamente |
| Secuencia | Revisar canal/flags/filtros con semántica proveedor | Cero gaps reales sin identificar; no falsos gaps por filtrado |
| Agresor | BUY/SELL/UNKNOWN por volumen | >=95% conocido en ventanas que habiliten LR |
| Disponibilidad | Separar ts_event, ts_recv y simulación local | Ningún input posterior al snapshot |
| Rollover | Reconstruir decisión con volumen previo | Misma selección al ocultar datos futuros |
| Warm-up | Intentar operar sin historia requerida | NO TRADE con motivo, nunca ceros sintéticos |
| Reproducibilidad | Dos replays de igual manifest/config | Hashes de features/candidatos idénticos |
| Causalidad | Alterar toda observación posterior a t | Ningún cambio en decisiones disponibles antes de t |

Elegir al menos 20 eventos de ejemplo manualmente auditables: trades compradores/vendedores/desconocidos, cambios de cotización, reset y faltantes si existen. Añadir fixtures sintéticos para fallos que no ocurran en la muestra. Documentar en cada ejemplo fuente → evento normalizado → feature; no sustituir auditoría por una gráfica que parezca razonable.

Reportar dos porcentajes distintos: disponibilidad del feed y proporción de candidatos elegibles. Un día sin setups puede tener calidad perfecta. Un día de fallos no debe desaparecer del reporte porque no produjo trades.

## 5. Protocolo preregistrado de investigación

### 5.1 Hipótesis

H1: LR-v1 produce un conjunto de candidatos para el cual features de precio y flujo permiten estimar outcomes mejor que una tasa base establecida con train.

H2: agregar clasificaciones Jev mejora utilidad predictiva/económica después de latencia y costos, frente a la misma estrategia sin Jev.

H3: elegir entre candidatos simultáneos mediante EV/RAEV mejora la política frente a seleccionar por probabilidad de acierto o por orden fijo de instrumentos.

Estas hipótesis pueden fallar. No se exige que el proyecto encuentre una estrategia rentable para aceptar que la ingeniería sea correcta.

### 5.2 Unidades y denominadores

- Observación supervisada: candidato emitido por setup, aunque el selector lo rechace.
- Unidad de label: candidato + política de ejecución + perfil de costos/latencia.
- Unidad de decisión: epoch compartido por ES/NQ/GC.
- Unidad principal de evaluación económica: sesión completa de la política seleccionada, incluyendo ceros cuando no opera.
- Unidad de remuestreo: bloques consecutivos de sesiones con todos los mercados juntos.

No comparar únicamente el subconjunto que Jev aprobó con todos los candidatos del baseline. Reportar política completa, cobertura, faltantes, rechazos y costos de inferencia.

### 5.3 Ventanas temporales propuestas

Todas las fechas representan sesiones por calendario de bolsa, con extremos de mes completos. El código tendrá una sola asignación de split global por fecha para todos los contratos.

| Fold | Train | Calibración | Selección de política | Test |
|---|---|---|---|---|
| F1 | ene–dic 2024 | ene–feb 2025 | mar 2025 | abr–jun 2025 |
| F2 | ene 2024–jun 2025 | jul–ago 2025 | sep 2025 | oct–dic 2025 |
| F3 | ene 2024–dic 2025 | ene–feb 2026 | mar 2026 | abr–jun 2026 |
| Holdout final | Config/model family elegidos con F1–F3 | Reajuste descrito abajo | Congelación final | jul–sep 2026 |

Para holdout: elegir familia/hiperparámetros/política con evidencia F1–F3; ajustar un nuevo modelo hasta abril2026, calibrar en mayo2026 y elegir umbrales de una rejilla previamente registrada en junio2026. No observar julio–septiembre antes de sellar artefactos. Esos meses son un holdout histórico; no resuelven el posible conocimiento histórico de Jev.

Folds posteriores pueden entrenarse con datos que antes fueron test, pues ya pertenecen al pasado en esa simulación. Debe conservarse el reporte original: nunca recalcular F1 con modelo de F3 y llamarlo OOS.

### 5.4 Purga y embargo

- Registrar `label_start = emisión del candidato` y `label_end = salida/no-fill/invalidación`.
- Eliminar del bloque anterior cualquier muestra cuyo intervalo de outcome se solape con el siguiente bloque.
- Usar además una sesión completa sin nuevas muestras entre bloques para simplificar el primer experimento; se pueden leer sus eventos anteriores como warm-up causal, sin usar labels para ajustar.
- Si una etiqueta llega a un período mayor del esperado, purgar por su intervalo real y abrir incidente de política.
- Las ventanas de features que miran hacia atrás pueden atravesar la frontera: eso reproduce información disponible y no es leakage por sí mismo. Ajustes de escalado/selección siempre pertenecen al train.
- Un mismo día de ES/NQ/GC nunca aparece repartido aleatoriamente entre train y test.

### 5.5 Presupuesto de búsqueda

Primera ronda: mantener LR-v1 sin optimizar barreras/horarios. Comparar como máximo seis configuraciones predictivas: tasa base, tres regularizaciones de regresión multinomial y dos configuraciones del challenger tabular, definidas en un manifiesto antes de ejecutar.

Cada configuración se compara con y sin features Jev donde aplique. Esto cuenta como múltiples ensayos y se registra; no presentar solo al ganador. Si el challenger necesita demasiados parámetros, posponerlo y completar el baseline.

Umbral EV_R: rejilla {0.05, 0.10, 0.15}; coeficiente de cola λ: {0.05, 0.10, 0.20}; incertidumbre γ=1 fijo. Son nueve políticas por modelo, elegibles solo en bloque de selección de política. Reportar el número total de combinaciones. Elegir por utilidad neta diaria con restricción de drawdown, desempate hacia menor complejidad y mayor cobertura con calidad válida.

La política central de la especificación usa EV_R0.10 y λ0.10. Los otros puntos son sensibilidades preregistradas; cada selección queda en el bundle. No modificar LR para crear más operaciones después de ver test. Nuevas ideas se versionan y requieren nuevo período de confirmación.

## 6. Labels, métricas y criterios de decisión

### 6.1 Modelo base y calibración

Tasa base por setup/dirección con shrinkage hacia el total train. Regresión multinomial regularizada como primer modelo aprendido. Features y missing indicators definidos en especificación; normalización ajustada en train.

Calibración multiclass en bloque independiente: empezar con escalado de temperatura escalar sobre logits y elegir su valor minimizando log loss de calibración. Si una clase no aparece o el soporte es insuficiente, marcar calibración no válida; no inventar probabilidad cero. Sigmoid/isotonic quedan como alternativas de una ronda posterior con nueva validación.

El calibrador y el modelo se congelan juntos. Curvas de calibración, Brier y log loss deben acompañarse de recuentos: ninguna métrica aislada demuestra que las probabilidades de trading estén calibradas.

### 6.2 Métricas obligatorias

| Grupo | Métricas |
|---|---|
| Datos | Cobertura, gaps, unknown aggressor, tiempo inválido, exclusiones |
| Candidatos | Conteo por setup/mercado/dirección, no-fill, TTL, duplicados |
| Clasificación Jev | Distribuciones, insufficient, errores, latencia, modelo y costo |
| Probabilidad | Log loss, Brier multiclass, reliability one-vs-rest, soporte por bin |
| Economía | P&L neto diario, expectancyR/USD, costos, EV previsto vs realizado |
| Riesgo | DrawdownUSD/R, peor sesión, ES95, exposición, breaches |
| Ranking | Cobertura, top-1 por epoch, comparación emparejada con baselines |
| Operación | Retrasos, backlog, rechazos, reconciliaciones y trazabilidad |

Comparaciones de ranking: EV/RAEV frente a mayor `p_net_positive`, orden fijo ES→NQ→GC y baseline de solo un instrumento. Mismas oportunidades disponibles, una posición y mismos costos. No comparar con una selección retrospectiva omnisciente como si fuera alcanzable.

### 6.3 Intervalos y dependencia

Bootstrap emparejado de bloques móviles de cinco sesiones, con todos los instrumentos juntos y 2,000 réplicas; seed publicada. Sensibilidad con bloques de diez sesiones. Para expectancy, remuestrear numerador P&L y número de operaciones de cada bloque; no tratar cada tick como observación independiente.

La precisión del límite inferior por candidato vendrá del ensemble temporal/modelo y se contrastará por grupos; no prometer cobertura exacta individual. La confianza de Jev no reemplaza este cálculo.

### 6.4 Puertas de avance

**Ingeniería → entrenamiento:** todos los tests de causalidad pasan; datos/contratos/unidades válidos; etiquetas de referencia auditadas; ninguna salida ignorada por ser difícil de simular.

**Entrenamiento → shadow:** al menos tres folds completos y holdout evaluado una vez; mejora frente a baseline documentada; estimación neta y drawdown compatibles con el perfil paper; soporte suficiente. Como piso orientativo: 1,000 candidatos LR totales y 100 outcomes por segmento reportado; si no se alcanza, extender historia sin cambiar de estrategia por conveniencia.

**Shadow → paper conectado:** mínimo 30 sesiones y 100 operaciones cerradas de la política habilitada como piso operativo, extendiendo si faltan regímenes o precisión; cero incidentes críticos abiertos; costos/latencia coherentes con el simulador. Un scanner puede continuar shadow sin cumplir gate económico.

**Paper → evaluación de ejecución real:** límite inferior unilateral95% de expectancy neta >0 en evidencia pertinente; diferencias de múltiples ensayos documentadas; stress aceptable y permiso de plataforma confirmado. Ese intervalo nominal por sí solo no corrige haber escogido entre muchas estrategias: la defensa principal es holdout intacto más evidencia prospectiva, y cualquier corrección estadística empleada debe declararse.

Ningún gate permite saltar de un resultado retrospectivo Jev a live. Una prueba histórica puede estar contaminada por conocimiento previo del modelo externo aun cuando nuestro pipeline no use datos futuros.

## 7. Simulación de latencia, costos y fallos

### 7.1 Matriz de latencia inicial

Valores sintéticos de prueba, a sustituir por mediciones:

| Etapa | Base | Adverso |
|---|---:|---:|
| Distribución adicional tras recepción proveedor | 100ms | 300ms |
| Procesamiento local | 50ms | 150ms |
| Jev remoto | 500ms | 1,200ms |
| Envío de orden | 100ms | 300ms |
| Salida después de trigger | 100ms | 300ms |

Las esperas al próximo epoch de un segundo se simulan aparte. No sumar etapas dos veces si hay solapamiento medido. Respuesta más allá de TTL expira y reduce cobertura; no se ejecuta retrospectivamente a precio anterior.

En el baseline sin Jev publicar dos variantes: su latencia real mínima modelada y una con retraso equivalente a Jev. Comparar solo una ocultaría si la mejora viene de esperar o si se pierde por esperar.

### 7.2 Stress

- Comisión sintética USD6 y USD10 round-trip hasta contar con tarifa real.
- Slippage adicional adverso de 0,1,2 ticks por salida sobre libro; mostrar componentes para no duplicar spread.
- Top-of-book sin liquidez al llegar; IOC no-fill.
- Caída Jev del 1% y 5% de candidatos, y caída en bloque de 10min.
- Eventos fuera de orden y duplicados; libro reseteado; timestamps faltantes.
- Final de ventana con una posición abierta; salida antes de cierre operativo.
- Reinicio con orden de estado desconocido en fase paper conectada.

No se convierte un límite de precio protector en garantía de fill. Si no se puede valorar una salida por falta de datos, el reporte debe exponer el problema y bloquear aprobación económica hasta resolverlo o acotar su efecto con una política conservadora predefinida.

## 8. Calendario macro y noticias

Filtro inicial para todos los instrumentos: eventos USD de alta relevancia de una lista versionada — CPI, Employment Situation, decisión/comunicado de FOMC, PCE y GDP. Las fechas se obtienen del organismo emisor o de archivo licenciado. Esta lista es diseño de cobertura, no calendario verificado de eventos concretos.

Bloquear nuevas entradas desde 5min antes hasta 10min después de publicación; los eventos relevantes se registran con hora y disponibilidad. Mantener stops de posiciones existentes; la política v1 no añade salida anticipada por noticia porque la ventana/horario puede ya excluirla. Cualquier cambio de esa política genera labels nuevos.

Si la historia solo dispone del calendario final revisado, marcar `calendar_not_point_in_time`; esos resultados son exploratorios y deben tener sensibilidad sin ese filtro. Para prospectivo, archivar el calendario al comienzo de cada sesión y sus cambios cuando se reciben.

Noticias no programadas: no hay modelo textual activo en v1. El gate de volatilidad/market status sigue vigente. No afirmar que el sistema conoce todas las noticias porque usa un calendario.

## 9. Resultados y entregables de cada experimento

Cada run produce:

1. Manifiesto de datos/contratos/calendario y hashes.
2. Config de features, setup, órdenes, costos, latencias y ranking.
3. Dataset de candidatos completo, con rechazados/no-fill y ventanas de labels.
4. Cache de respuestas Jev con modelo y hora, respetando licencia.
5. Split report con intervalos purgados y razones de exclusión.
6. Artefactos de modelo/calibrador y cutoff de ajuste.
7. Ledger de candidatos contrafactuales y ledger de cartera seleccionada separados.
8. Métricas globales y segmentadas con incertidumbre y cobertura.
9. Informe de fallos/sensibilidad y conclusión: avanzar, continuar investigación o descartar hipótesis.

El informe incluirá un cuadro de evidencia:

| Afirmación | Evidencia necesaria |
|---|---|
| “Ingestión funciona” | Archivos reales procesados con controles de calidad |
| “Jev integrado” | Request autenticada y respuesta validada, no mock |
| “Replay causal” | Pruebas automatizadas y auditoría de timestamps |
| “Probabilidades calibradas” | Evaluación en datos separados y soporte declarado |
| “Jev aporta valor” | Comparación emparejada y confirmación prospectiva |
| “Ejecución funciona” | Órdenes/fills/reconciliación en entorno autorizado |
| “Apto para prop firm” | Reglas exactas de cuenta y permiso aplicable comprobados |

## 10. Lista de cierre de fase 0

- [x] Futuros y order flow confirmados como dirección.
- [x] ES/NQ/GC y ventana común seleccionados para investigación.
- [x] LR-v1 con reglas, estados y parámetros definidos.
- [x] TC-v1/BO-v1 especificados para incrementos posteriores.
- [x] Dataset piloto y política de selección de contratos definidos.
- [x] Separación temporal, baselines, búsqueda y métricas registradas.
- [x] Backlog de implementación con dependencias y aceptación preparado.
- [x] Cuentas Databento y TypeSafe creadas (3-oct-2026).
- [ ] Licencia y envío de derivados a IA verificados.
- [x] Cotización y cobertura de muestra confirmadas (3-oct-2026, ver `docs/ACCESOS-2026-10-03.md`).
- [x] Primera prueba autenticada de cada servicio completada (3-oct-2026, `scripts/check_access.py`).
- [ ] Muestra auditada y factibilidad real demostrada.

**Estado de salida:** preparados para verificar accesos y empezar ingeniería; la fase 0 completa sigue pendiente de sus comprobaciones externas. La primera acción del usuario es crear ambas cuentas. Después se podrán configurar las claves localmente y obtener la cotización sin exponer secretos en el chat.

## 11. Fuentes y alcance

Consultadas el 3 de octubre de 2026:

- [Databento: precios](https://databento.com/pricing) — histórico por consumo, créditos y condiciones generales.
- [Databento: MBP-10](https://databento.com/docs/schemas-and-data-formats/mbp-10) — contenido del esquema y campos.
- [Databento: MBP-1](https://databento.com/docs/schemas-and-data-formats/mbp-1) — alcance de la alternativa L1.
- [TypeSafe: modelos](https://docs.typesafe.ai/models) — versionado y condiciones técnicas publicadas.
- [TypeSafe: API](https://docs.typesafe.ai/api) — contrato de transporte para la prueba futura.
- [BLS: calendario de Employment Situation](https://www.bls.gov/schedule/news_release/empsit.htm) — ejemplo de fuente oficial de calendario.

Los calendarios experimentales, reglas de estrategia, cifras de simulación y umbrales son decisiones de investigación de este proyecto. Las fuentes no validan la rentabilidad ni los resultados, que todavía no existen.
