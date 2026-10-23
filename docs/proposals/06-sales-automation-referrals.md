# 06 · Motor de ventas con IA: outbound, reactivación y referidos

> **Supuesto central (a validar con IGS):** hoy la mayor parte de las ventas de IGS llegan por inbound (formulario `/plan-a-tour`, que pregunta *"How did you hear about us?"* con opciones *Referral*, *Returning Customer* y *AI Assistant*), y no hay un proceso outbound sistemático. Todo lo que sigue sobre la operación interna de IGS es **hipótesis**.

## 1. El problema

- Quienes compran son los **coaches y athletic directors** de programas universitarios (NCAA D1/D2/D3, NAIA), clubes juveniles (ECNL, academias) y private schools de EE.UU.
- Su presupuesto sigue un calendario muy predecible:
  - aprobación del presupuesto anual (primavera/verano);
  - ventanas de viaje: spring break, junio, foreign tour cada 4 años según las reglas NCAA de giras al exterior;
  - recaudación de fondos con las familias.
- Una gira se decide entre **6 y 12 meses antes**. Si IGS no está en la conversación cuando el coach arma el plan del año siguiente, la venta se va a un competidor.
- Los clientes satisfechos y sus referidos son el canal más barato, pero probablemente no se trabajan de forma sistemática. El formulario los mide, pero nadie los "activa".

## 2. La propuesta en una línea

Un **copiloto de ventas** dentro de IGS OS que:
1. arma y mantiene la lista de programas objetivo;
2. sabe **cuándo** contactar a cada uno según su calendario de presupuesto;
3. redacta mensajes personalizados que **una persona aprueba antes de enviar**;
4. reactiva a los clientes anteriores a partir de las señales de la ficha 360;
5. convierte a cada cliente feliz en un canal de referidos medible.

## 3. Componentes

### 3.1 Lista de programas objetivo (Target List)
- **Fuentes públicas:**
  - directorios NCAA/NAIA de programas por deporte y división;
  - sitios de athletics de cada universidad (staff directory: head coach, assistants, director of operations);
  - listas de clubes ECNL/GA y de private schools con programa de soccer.
- **Enriquecimiento con IA:**
  - división y conferencia, nivel estimado (score 1–10, el mismo que usa el planificador de giras), deporte y género;
  - historial de giras al exterior (notas de prensa del athletics site), fecha probable del próximo foreign tour y quién decide.
- **Modelo:** `accounts` + `stakeholders` (ficha 360) con `status = prospect`. No hace falta un sistema nuevo.
- **Higiene:** se dedupea por dominio y nombre de programa. Cada dato lleva su fuente (URL) y su fecha. Los datos de menores no se tocan.

### 3.2 Timing por calendario ("cuándo hablar")
- **Reglas fijas, no LLM**, para el disparador:
  - *N meses antes de la ventana de viaje típica*;
  - *después de un evento público* (clasificó a nacionales, nuevo head coach);
  - *aniversario de la última gira* para recurrentes.
- **Ejecución:** flows durables de Temporal con disparador `cron` o por fecha (`wait until`). Es el mismo motor que ya corre `pre-departure-check`.

### 3.3 Outreach personalizado con aprobación humana
- El agente redacta el primer mensaje y la secuencia de seguimiento usando:
  - nivel y resultados del programa;
  - rivales de su nivel disponibles en el destino;
  - testimonios de programas similares, siempre con su permiso;
  - una idea concreta de itinerario.
- **Nada sale sin aprobación.** Cada envío pasa por la bandeja de aprobaciones existente, con la vista previa exacta y el `payload_hash`. Ops puede aprobar en lote solo los mensajes de bajo riesgo, por ejemplo un segundo seguimiento con plantilla ya aprobada.
- **Secuencia típica:** día 0 intro → día 4 caso de un programa similar → día 10 itinerario de ejemplo → día 21 cierre ("¿lo vemos el año que viene?"). Se corta sola si el coach responde, agenda o pide no recibir más.
- **Agendado:** link de reunión (Calendly/Google Calendar). El agente propone horarios en la zona del coach, en US time.

### 3.4 Reactivación de clientes (Returning Customer)
Usa las señales de la ficha 360:
- gira completada hace 11–30 meses;
- salud verde y sentimiento positivo del decisor;
- un coach nuevo en el programa, que es un riesgo y también una oportunidad;
- un compromiso pendiente ("volvemos en 2028").

Con eso el flow arma una propuesta de "próxima gira" con un destino distinto (Brasil o Costa Rica si fueron a Argentina) y la deja para aprobación.

### 3.5 Programa de referidos
- **Link personal y trackeado** por coach, padre o director (`/plan-a-tour?ref=<código>`). El lead queda atribuido en `leads.source = referral` con el código.
- **Recompensa** al confirmar la gira referida, como crédito en la próxima gira, upgrade de experiencia o donación al programa. Hay que revisar compliance: para programas NCAA, mejor beneficios al programa que regalos personales.
- **Momento de pedirlo:** el flow `post-match-report` y el cierre de gira lo piden en el pico de satisfacción, con 1 a 3 nombres de colegas sugeridos por el agente a partir de su conferencia.
- **Panel de referidos:** quién refirió, cuánto convirtió y cuánto falta para la recompensa.

### 3.6 Análisis de ganadas y perdidas
- Cada lead cerrado registra el motivo: precio, fechas, competidor (con la cotización registrada como riesgo en la ficha 360) o presupuesto.
- Un resumen mensual lo genera el LLM a partir de las interacciones, con citas: por qué perdemos, a qué competidores, en qué nivel o división.
- La **salud de la cuenta** y la probabilidad de cierre siguen siendo por reglas. El LLM solo resume y explica.

## 4. Compliance y riesgos

| Tema | Regla / riesgo | Cómo se cubre |
|---|---|---|
| **CAN-SPAM** | Identificación real, dirección física, opt-out en cada mail, procesarlo en 10 días hábiles, asunto no engañoso | Plantilla con footer fijo; `unsubscribe` → flag en `stakeholders` que bloquea toda secuencia; asuntos aprobados por ops |
| **NCAA** | Las reglas de contacto con **recruits** (atletas menores en reclutamiento) no aplican a vender a coaches adultos, pero **nunca** se contacta a atletas ni a menores | El motor solo escribe a staff adulto con email institucional; los menores no entran a la lista |
| **Foreign tours NCAA** | Los programas tienen reglas de frecuencia y financiamiento para giras al exterior | El timing usa la ventana permitida; la propuesta lo menciona sin dar asesoramiento legal |
| **Reputación de envío** | Spam, rebotes y quejas queman el dominio | Dominio o subdominio de envío separado con SPF/DKIM/DMARC; warm-up; tope diario por buzón; se pausa solo si los rebotes superan 3% o las quejas el 0,1% |
| **Datos públicos** | Scraping de sitios de athletics | Solo directorios públicos de staff; respetar robots/ToS; guardar la fuente; borrar si piden |
| **Tono** | Mensajes "de IA" genéricos | Las personas aprueban; se mide la tasa de respuesta por plantilla y se retira lo que no funciona |

## 5. Números (rangos con supuestos explícitos)

Supuestos para una temporada:
- 1.200 programas objetivo en las divisiones y deportes donde IGS ya vende.
- 60% con contacto válido.
- Tasa de respuesta del 4–10% con mensajes personalizados.
- 30–50% de las respuestas agenda una llamada.
- 15–30% de las llamadas se convierte en gira en 6–12 meses.

| Etapa | Bajo | Alto |
|---|---|---|
| Contactados | 720 | 720 |
| Respuestas | 29 | 72 |
| Reuniones | 9 | 36 |
| Giras nuevas | **1** | **11** |

**Reactivación:** de 40 clientes de los últimos 3 años, con 20–35% de recompra → **8 a 14 giras**.

**Referidos:** 0,3–0,8 referidos por gira completada, con 20–40% de cierre. Con 30 giras por año → **2 a 10 giras**.

> Ticket orientativo: la demo usa unos US$2.900 por viajero con 24 viajeros, unos US$70.000 por gira. **Validar con IGS el volumen real, el ticket y el margen antes de usar estas cifras.**

Lo más valioso suele ser la **reactivación y los referidos**: mayor tasa, menor costo y menos riesgo de reputación que el outbound frío.

## 6. KPIs

- **Tiempo de respuesta** a un lead inbound (objetivo: menos de 1 hora hábil), lo que ya resuelve el flow `inbound-inquiry`.
- **Outbound:** tasa de respuesta por plantilla y segmento; reuniones por cada 100 contactados; costo por reunión.
- **Pipeline:** valor por etapa y conversión por etapa (`leads.status`).
- **Reactivación:** porcentaje de clientes elegibles contactados y recompra.
- **Referidos:** links activos, leads referidos, conversión y recompensas pagadas.
- **Reputación:** rebotes, quejas y bajas, con alertas.
- **Ganadas/perdidas:** distribución de motivos y competidores.

## 7. Cómo reusa IGS OS

| Necesidad | Ya existe | Falta |
|---|---|---|
| Programas y personas | `accounts`, `stakeholders`, `interactions` (ficha 360) | Estado `prospect` en la UI, import de la lista enriquecida |
| Leads y pipeline | `GET/PATCH /v1/leads`, kanban, `lost_reason` | Campo `source` + `ref_code`, atribución de referidos |
| Timing y secuencias | Flows durables en Temporal (`wait`, cron, eventos), outbox | Nodo `send_email` real (proveedor transaccional), secuencias con corte por respuesta |
| Redacción con aprobación | Agente con tools, aprobaciones con `payload_hash`, auditoría | Plantillas versionadas y aprobación en lote para bajo riesgo |
| Reactivación | Salud por reglas, hechos con citas | Regla "elegible para recompra" + flow de propuesta |
| Ganadas/perdidas | Interacciones con citas, LLM extractor | Reporte mensual |
| Copiloto | Drawer + MCP con las mismas tools | Prompts sugeridos de ventas ("¿a quién llamo esta semana?") |

## 8. Esfuerzo (S/M/L)

| Pieza | Tamaño |
|---|---|
| Atribución de referidos (`ref` en el formulario, `leads.source`) + panel | **S** |
| Reactivación (regla + flow + aprobación) | **S** |
| Secuencias de seguimiento sobre flows existentes + envío real con opt-out | **M** |
| Lista objetivo enriquecida (scraping responsable + enriquecimiento + dedupe) | **M** |
| Outreach personalizado con plantillas versionadas y métricas | **M** |
| Ganadas/perdidas mensual | **S** |
| Infra de envío (dominio, SPF/DKIM/DMARC, warm-up, monitoreo) | **S** (técnico) + tiempo calendario de warm-up |

**Orden recomendado:** 1) referidos y reactivación (rápido y de bajo riesgo), 2) seguimiento de inbound, 3) outbound frío, solo después de calentar el dominio.

## 9. Preguntas para IGS

1. ¿Qué porcentaje de las giras de hoy viene de recompra y de referidos? ¿Lo miden?
2. ¿Tienen un CRM o una lista de clientes y coaches? ¿En qué herramienta?
3. ¿Qué divisiones y deportes quieren crecer: D1 femenino, clubes ECNL, private schools?
4. ¿Hay un incentivo de referidos hoy? ¿Qué es aceptable para programas NCAA?
5. ¿Quién aprobaría los mensajes salientes y cuánto volumen por semana es razonable?
