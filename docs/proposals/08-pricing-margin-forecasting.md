# 08 · Pricing, margen y forecasting — la economía de cada gira

> Propuesta para Infinity Global Sports (IGS). Todo lo que se dice sobre la operación interna de IGS es **hipótesis** inferida de su sitio público y de cómo opera un tour operator de grupos; hay que validarlo con IGS antes de construir. Las cifras de impacto son **rangos con supuestos explícitos**, no promesas.

## 1. El problema

Un tour operator deportivo vende en **USD** (coaches de EE.UU.) y paga en **ARS, BRL y USD** (hoteles, micros, árbitros, canchas, estadios). Entre la cotización y la salida pasan **4 a 12 meses**. En ese tiempo:

- El costo real se mueve: inflación local, tipo de cambio, proveedores que repricean, grupos que cambian de tamaño.
- El margen se conoce recién al cerrar la gira, si es que alguien la cierra con números.
- Los cupos (bloqueos de hotel, micros, rivales de nivel) se comprometen antes de tener las inscripciones.
- La demanda tiene estacionalidad fuerte (spring break, verano boreal, Mundial Femenino 2027) y no se proyecta desde el pipeline.

**Hipótesis:** hoy esto vive en planillas por gira, con el margen estimado al cotizar y poco seguimiento después.

## 2. Qué ya tiene IGS OS (base real del repo)

| Pieza | Dónde | Qué hace hoy | Qué le falta para esta propuesta |
|---|---|---|---|
| Cotizador determinístico | `packages/py-common/src/igs_common/domain/pricing.py` | Suma costos por unidad (hotel por noche, micro y guía por día, árbitro por partido, cancha, experiencias), aplica margen fijo `DEFAULT_MARGIN = 0.22`, redondea, todo en `Decimal` | Margen por línea de producto, moneda de costo, fecha de la cotización |
| Proveedores | `db/models/catalog.py` (`providers`) | `kind`, ciudad, `unit_price_usd`, `unit` | Moneda original, historial de precios, vigencia, confiabilidad |
| Snapshot de precio por gira | `db/models/sales.py` → `trips.pricing` (JSONB) | Guarda la cotización al proponer | Costo real a medida que se confirma, desvío vs. cotización |
| Ítems de gira con estado | `trip_items` (pending → requested → confirmed → completed) | Sabemos qué proveedor se confirmó y cuándo (`requested_at`, `completed_at`) | Monto confirmado y moneda por ítem |
| Pipeline de leads | `/v1/leads`, kanban | Etapas, presupuesto por persona, fecha de viaje, tamaño de grupo | Probabilidad de cierre, fuente, motivo de pérdida estructurado (ya hay `lost_reason`) |
| Términos reales de IGS | fixtures + `public_chat.py` | US$95 de inscripción, cuotas de US$500, saldo 110 días antes | Proyección de cobranza por fecha |
| Flows durables | Temporal + `packages/flow-schema` | Esperas, escalamientos, aprobaciones | Flows de alerta de margen y de FX |

**Conclusión:** la mitad de la plomería existe. Lo que falta es **registrar el costo real y la moneda**, y poner analítica encima.

## 3. Propuestas

### 3.1 Costo real por gira y margen vivo — esfuerzo **M**

Cada ítem confirmado registra **monto, moneda, tipo de cambio del día y fuente** (factura, mail del proveedor, WhatsApp). El margen de la gira se recalcula en cada confirmación y se compara con el margen cotizado.

- **IA:** extracción estructurada del monto y la moneda desde el mail o PDF del proveedor (mismo patrón de extracción con cita textual verificada que ya usa Account 360). Nunca se guarda un monto sin la cita de dónde salió.
- **Vista:** en el detalle de la gira, "Margen cotizado 22% → margen hoy 17,4%", con el desvío por línea (hotel +US$1.900, micros +US$400).
- **Datos:** `trip_items.confirmed_amount`, `currency`, `fx_rate`, `source_ref`; tabla `fx_rates` diaria (BCRA / BCB / feed público).

### 3.2 Margen por línea de producto — esfuerzo **S** (una vez que existe 3.1)

Agregado por línea: giras universitarias, clubes juveniles, colegios, camps en EE.UU., paquetes familiares del Mundial 2027, por país y por temporada. Responde: **¿qué vendemos que realmente deja plata?**

### 3.3 Pricing dinámico dentro de los términos publicados — esfuerzo **M**

**No cambiar las reglas públicas de IGS** (US$95 de inscripción, cuotas de US$500, saldo 110 días antes, reembolsos escalonados). Lo que sí se puede ajustar es el **precio del programa** al cotizar:

- **Early-bird:** descuento por cotizar con más de X meses, financiado por el costo más bajo de bloquear temprano.
- **Tamaño de grupo:** precio por persona escalonado (los costos fijos de micro, guía y árbitros se reparten), con la plaza gratis para el coach cada 15 jugadores que ya figura en las políticas de la KB (`fixtures/catalog.yaml`).
- **Temporada:** precio de spring break y del Mundial 2027 distinto al de temporada baja.
- **IA:** sugiere el precio y **explica por qué** ("+6% por fecha de alta demanda, −4% por grupo de 30"). Siempre lo aprueba una persona (flujo de aprobación existente).

### 3.4 Planificación de capacidad por temporada — esfuerzo **M**

Cruza el pipeline con los compromisos: bloqueos de hotel, micros y rivales por ciudad y semana.

- "Para la semana del 9 de marzo tenés 3 grupos en propuesta y bloqueos para 2: si cierran los 3, faltan 26 camas y un micro."
- "Hay 4 grupos femeninos U19 de nivel 7 en la misma semana y solo 2 rivales de ese nivel disponibles."
- Usa `find_opponents` y los proveedores ya modelados.

### 3.5 Forecast de demanda e ingresos desde el pipeline — esfuerzo **M**

Probabilidad de cierre por lead (etapa, días sin respuesta, fuente, si es cliente recurrente según Account 360, cotización rival detectada como riesgo) × valor esperado → **ingresos esperados por mes de salida** y **cobranza esperada por mes** (aplicando el calendario real de inscripción y cuotas).

- Primero un modelo simple y explicable (regresión logística o reglas), no una caja negra.
- Se valida contra el histórico de IGS cuando exista.

### 3.6 Score de confiabilidad de proveedores — esfuerzo **S**

Por proveedor: tiempo de respuesta a pedidos de confirmación (ya lo mide el flow `pre-departure-check`), cancelaciones, desvío entre precio cotizado y facturado, incidentes en gira. Se usa para elegir proveedor en el armado y para negociar.

### 3.7 Alertas de tipo de cambio — esfuerzo **S**

Cuando hay pagos grandes en ARS o BRL por delante (bloqueos de hotel, saldos), alerta si el tipo de cambio se mueve más de X% y sugiere **adelantar o esperar el pago** según el margen en juego. Es una **alerta de timing**, no una operación financiera: no se compran ni venden divisas desde el sistema.

## 4. KPIs

| KPI | Cómo se mide | Línea base |
|---|---|---|
| Desvío de margen (cotizado vs. real) por gira | 3.1 | A medir: hoy probablemente no se mide |
| Margen por línea de producto | 3.2 | A medir |
| Tasa de conversión de propuesta por rango de precio | pipeline + 3.3 | A medir |
| Ocupación de bloqueos de hotel (camas usadas / bloqueadas) | 3.4 | A medir |
| Error del forecast de ingresos a 90 días | 3.5 | — |
| Días de respuesta promedio por proveedor | 3.6 | Ya medible con el flow pre-salida |

## 5. Impacto esperado (rangos, con supuestos)

| Palanca | Rango | Supuestos |
|---|---|---|
| Recuperar margen erosionado por costos no seguidos | **+1 a +4 puntos de margen** | Desvíos de costo de 3–8% entre cotización y salida sin seguimiento hoy; la mitad se recupera repreciando a tiempo o negociando |
| Pricing por tamaño de grupo y temporada | **+2 a +5% de ingreso por gira** | Hoy el precio por persona no varía (o varía poco) con el tamaño ni la temporada |
| Menos camas bloqueadas sin usar | **−20 a −40% de penalidades por liberación** | IGS bloquea hoteles antes de cerrar grupos y paga o pierde por cupos no usados |
| Forecast de cobranza | **Visibilidad 90 días**, sin impacto directo en margen | Requiere que los pagos se registren en el sistema |

Ejemplo de órdenes de magnitud: si IGS hiciera **40 giras al año a US$70.000 de facturación promedio** (24 viajeros × ~US$2.900), son **US$2,8 M**. Un punto de margen son **US$28.000 al año**. Son números hipotéticos para dimensionar; los reales salen de las preguntas del punto 8.

## 6. Riesgos

- **Pricing opaco que daña la confianza del coach.** Los coaches universitarios comparan propuestas y hablan entre ellos. Mitigación: la propuesta muestra un precio de paquete claro (como ya hace la demo) y las reglas de descuento son públicas (early-bird, tamaño de grupo), nunca precios distintos sin razón para el mismo producto.
- **Datos insuficientes al inicio.** Sin histórico, el forecast es ruido. Mitigación: empezar con reglas explicables y mejorar con cada temporada.
- **Extracción de montos equivocada.** Mitigación: cita textual obligatoria y aprobación humana antes de impactar el margen.
- **FX como asesoramiento financiero.** Mitigación: solo alertas de timing, sin operar divisas ni recomendar instrumentos.
- **Carga operativa.** Si registrar el costo real cuesta más que la planilla, nadie lo hace. Mitigación: que el registro salga del mail o la factura que ya reciben (extracción), no de tipear.

## 7. Quick win: primeros 30 días con una planilla + IA

Sin construir nada todavía:

1. **Semana 1:** una Google Sheet por temporada con una fila por ítem confirmado: gira, proveedor, tipo, monto, moneda, fecha, link al mail. Columnas calculadas: USD al tipo de cambio del día y desvío contra la cotización.
2. **Semana 2:** un prompt de extracción (el mismo del sistema) que, pegándole el mail o PDF del proveedor, devuelve la fila lista para la planilla con la cita textual.
3. **Semana 3:** un resumen semanal generado por IA sobre la planilla: "3 giras bajaron más de 3 puntos de margen; la causa principal es el hotel de Palermo (+11%)".
4. **Semana 4:** revisar con la dirección de IGS qué giras pierden margen y por qué. Esa planilla es el dataset para importar a IGS OS (tabla `trip_item_costs`) cuando se construya 3.1.

**Resultado:** en un mes, IGS sabe por primera vez su margen real por gira, sin cambiar herramientas.

## 8. Preguntas para validar con IGS

1. ¿Cuántas giras y viajeros hacen por año, y cuál es el precio promedio por persona?
2. ¿Cómo calculan hoy el margen y cuándo se enteran del margen real de una gira?
3. ¿En qué moneda pagan a cada tipo de proveedor y cuánto les movió el tipo de cambio la última temporada?
4. ¿Bloquean hoteles antes de cerrar grupos? ¿Cuánto pierden por cupos no usados?
5. ¿El precio por persona hoy varía por tamaño de grupo o temporada?

## 9. Orden sugerido

3.1 costo real y margen vivo → 3.6 confiabilidad de proveedores → 3.2 margen por línea → 3.4 capacidad → 3.7 alertas FX → 3.5 forecast → 3.3 pricing dinámico (último, porque necesita datos y toca la confianza del coach).
