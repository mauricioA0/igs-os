# Casos de uso reales — IGS OS para Infinity Global Sports

> Basado en lo que IGS publica en infinityglobalsports.com (relevado el 2026-10-22) y mapeado a lo que hoy existe en este repo. Los **dolores actuales son hipótesis** (marcadas ⚠️) inferidas del sitio: hay que validarlas con el equipo de IGS antes de afirmarlas.

## Lo que el sitio dice de la operación (y por qué importa)

| Hecho publicado | Fuente | Implicancia para IGS OS |
|---|---|---|
| El formulario "Plan a Tour" pide solo programa, rol, teléfono, ventana de viaje y "cómo nos conociste" — **no pide deporte, destino, nivel, tamaño del grupo ni presupuesto** | `/plan-a-tour` | La calificación la hace una persona después. Un agente que califica en la conversación ahorra ese ida y vuelta |
| Promesa: *"respond with sample itinerary options within 1 business day"* | `/plan-a-tour` | El SLA de respuesta es un KPI explícito; un borrador de propuesta automático lo vuelve minutos |
| "How did you hear about us?" incluye *Referral*, *Returning Customer* y *AI Assistant (ChatGPT, Gemini…)* | `/plan-a-tour` | Referidos y clientes recurrentes son canales medidos → Account 360 tiene valor directo |
| Roles del formulario: Head Coach, Assistant Coach, Director of Coaching, Executive Director, **Athletic Director, Head of School** | `/plan-a-tour`, `/private-school-sports-tours` | Hay varios stakeholders por cuenta y quien escribe no siempre decide → stakeholders/decisor en Account 360 |
| Grupos de 20–35 viajeros, planificación ideal 12–18 meses antes; colegios necesitan "school calendars and approvals" | `/college-soccer-tours`, `/private-school-sports-tours` | Ciclos de venta largos con muchas interacciones → memoria institucional por cliente |
| Itinerario tipo 9 días en Buenos Aires: 2 entrenamientos en academias pro, hasta 3 amistosos vs "pro academy or top club youth sides", Bombonera/Monumental, tango | `/college-soccer-tours`, `/youth-club-soccer-tours` | Coincide con el planificador del repo (llegada/partida, sin partidos consecutivos, rival por nivel) |
| *"Face Argentine and Brazilian club teams carefully matched to your level, age group, and competitive goals"* | Home | El matching de rivales por nivel es una promesa central de la marca |
| Youth club desde U13: parent briefing, *"daily staff updates"*, 24/7, chaperones bilingües; materiales de fundraising | `/youth-club-soccer-tours` | Comunicación recurrente con padres de menores → flows + reglas de datos de menores |
| Términos: fee de inscripción US$95 no reembolsable; plan manual US$500 a 30 días, US$500 a 90 días, saldo 110 días antes; reembolsos escalonados (150/110/45 días); seguro hasta 21 días antes; menores: <15 con adulto, poder limitado para el group leader | `/terms-and-conditions` | Muchos vencimientos por viajero = seguimiento de pagos y documentos automatizable. **La demo ya usa estos términos reales** (fee de inscripción, cuotas y saldo a 110 días) |
| Family Experience: *"built around the US Women's National Team at the 2027 FIFA Women's World Cup. Wherever Team USA goes, we go."* | Home, `/family-experiences`, `/brazil-2027-womens-soccer-tours` | Producto B2C de alto volumen con itinerario que depende del fixture → flows disparados por eventos |
| Otros productos: AFA Soccer Camps USA verano 2027 (8–18 años, 17 ciudades, waitlist, feedback individual por jugador), Superclásico 2027 giveaway, Infinity Cup, rugby, hockey, vóley, básquet, España y Costa Rica | `/individual-experiences/usa-camps`, rutas del sitio | Portafolio amplio para un equipo de ~25 personas (CEO/COO fundadores, ~15 SDR/AE) → automatizar lo repetitivo |
| Oficinas en Buenos Aires, Nueva York y Denver; CEO y fundador: **Emilio Di Marco** | `/about` | Equipo distribuido entre zonas horarias → aprobaciones asincrónicas y trazabilidad |

## Casos de uso

Leyenda de prioridad (MoSCoW para el demo y el v1): **M** must · **S** should · **C** could · **W** won't (por ahora).

---

### UC-01 · College coach inquiry → proposal in minutes
**Fuente:** `/plan-a-tour`, `/college-soccer-tours` · **Prioridad: M** · **Demo: ⭐**

- **Actores:** Head Coach universitario (EE.UU.), agente concierge, coordinador/a de ventas (aprobador).
- **Trigger:** el coach escribe desde el sitio (o desde el widget) — hoy entra por el formulario de 5 campos.
- **Dolor actual ⚠️:** el formulario no captura deporte, nivel, tamaño ni presupuesto; un SDR tiene que llamar o escribir para calificar antes de armar opciones, contra un SLA de "1 business day".
- **Flujo en IGS OS:**
  1. Chat público → `POST /v1/public/chat/conversations` inicia el flow `inbound-inquiry` (Temporal, `packages/flow-schema/examples/inbound-inquiry.json`).
  2. Nodos conversacionales capturan sport, género, categoría, nivel, viajeros, fechas, duración y presupuesto (una pregunta por turno, `/chat`).
  3. Acción `create_lead` → lead en `/ops/leads` (`GET /v1/leads`).
  4. Acción `draft_trip` → `igs_common.domain.planner.plan_itinerary` arma el itinerario con rivales ±1 nivel y precio (`pricing.quote`).
  5. Nodo `approval` → aparece en `/ops/approvals` con el texto exacto a enviar y su huella (`POST /v1/approvals/{id}/decision` con `payload_hash`).
  6. Al aprobar, `send_proposal`; el coach ve `/proposal/{ref}` (inglés, precio por paquete, CTA "Reserve").
- **Gap:** captura de roles/decisor en el chat; envío real por email/WhatsApp (hoy outbox); multi-idioma del concierge fuera de EN/ES.
- **Métrica de valor:** tiempo de primera propuesta (de "1 día hábil" a minutos + revisión humana); % de leads calificados sin llamada.

---

### UC-02 · Youth club team with parents of minors
**Fuente:** `/youth-club-soccer-tours`, `/terms-and-conditions` (sección menores) · **Prioridad: M**

- **Actores:** Director of Coaching del club, padres/tutores, tour leader, ops.
- **Trigger:** gira U15/U17 confirmada; empiezan los briefings y la recolección de autorizaciones.
- **Dolor actual ⚠️:** "parent briefing" y "daily staff updates" por grupos de WhatsApp/email; documentación de menores (poder limitado, fichas médicas, pasaportes) perseguida a mano por viajero.
- **Flujo en IGS OS:**
  1. Account 360 del club (`/ops/accounts/{id}`) con stakeholders (DOC, tesorero, *parent_liaison* — rol existente en el modelo).
  2. Flow de pre-salida (`pre-departure-check.json`) adaptado: checklist por viajero, recordatorios escalonados.
  3. Mensajes a padres siempre por aprobación (`request_approval` / tool class *write-external*).
- **Gap:** portal del viaje para familias (diseñado en `docs/design/coach-experience.md`, no construido); almacén cifrado de datos de menores separado del LLM (definido en `docs/architecture/security.md` §3.7, no implementado); roster por viajero.
- **Métrica:** % de documentación completa a 30/21 días; horas de seguimiento manual por gira.

---

### UC-03 · Women's World Cup 2027 family package
**Fuente:** Home ("Women's World Cup 2027 · Brazil", "Follow Team USA in Brazil"), `/family-experiences` · **Prioridad: S** · **Demo: ⭐ (como visión)**

- **Actores:** familias fans de la USWNT (B2C), ops, agente concierge.
- **Trigger:** se publica el fixture / la USWNT avanza de fase → cambia la ciudad del próximo partido.
- **Dolor actual ⚠️:** itinerarios que dependen del resultado ("Wherever Team USA goes, we go") obligan a re-planificar hoteles, vuelos internos y entradas para muchas familias en 48–72 h.
- **Flujo en IGS OS:**
  1. Evento de dominio (`POST /v1/events`, ej. `team.advanced`) dispara un flow por familia (`outbox` → `OutboxDispatcher`, workflow id idempotente).
  2. Nodo `map` (implementado en el worker) recorre las reservas afectadas y propone cambios.
  3. Cada cambio con costo pasa por aprobación; el copiloto resume "qué familias faltan confirmar".
- **Gap:** producto/catálogo B2C (familias, entradas, vuelos), integración con proveedores de entradas; precios dinámicos. Hoy el modelo está pensado para equipos.
- **Métrica:** tiempo de re-planificación tras un resultado; reservas re-acomodadas sin error.

---

### UC-04 · Provider confirmations 30 days before departure
**Fuente:** itinerarios con hotel, transporte, academias y estadios (`/college-soccer-tours`); términos: "depend on third-party providers" · **Prioridad: M** · **Demo: ⭐**

- **Actores:** ops coordinator, proveedores (hotel, micro, árbitros, academias).
- **Trigger:** `trip.status_changed` → confirmed, y espera durable hasta 30 días antes.
- **Dolor actual ⚠️:** confirmaciones por WhatsApp/planillas; lo que nadie reconfirmó aparece el día del partido.
- **Flujo en IGS OS:** `pre-departure-check.json` → `wait` durable hasta la fecha → `list_trip_items` → `request_provider_confirmations` → `wait` 48 h → `create_ops_task` para lo no confirmado; ops confirma con `PATCH /v1/trips/{id}/items/{item}` (`/ops/trips/{id}`, acciones por ítem); "Hoy" (`/ops`) muestra la cola de atención.
- **Gap:** canal real hacia proveedores (email/WhatsApp con respuesta parseada); portal de proveedor.
- **Métrica:** % de ítems confirmados a 25 días; incidentes por falta de confirmación.

---

### UC-05 · On-tour incident (match cancelled, bus late)
**Fuente:** "24/7 in-country support", "clear emergency protocols" (`/private-school-sports-tours`); términos: "Itineraries are subject to change… substitute activities of comparable value" · **Prioridad: S**

- **Actores:** tour director en la calle, ops en Buenos Aires, coach.
- **Trigger:** el rival suspende o el micro no llega.
- **Dolor actual ⚠️:** se resuelve por teléfono; queda poco registro de qué se cambió y quién avisó al coach.
- **Flujo en IGS OS:** el copiloto (`POST /v1/copilot/turns`) busca rivales alternativos por nivel (`find_opponents` vía planner) y propone `update_trip_item` / `cancel_trip_item` (aprobación si es externo); el cambio emite `trip_item.status_changed` y queda en auditoría.
- **Gap:** tabla `incidents` existe en la base pero **sin API ni pantalla**; modo campo mobile (propuesta V1 P1); sustitución automática con precio equivalente.
- **Métrica:** tiempo de resolución; % de incidentes con aviso al coach registrado.

---

### UC-06 · Post-match report to the coach
**Fuente:** home: "Pre-match scouting reports", "Post-match performance analysis", "Video analysis & review" · **Prioridad: S** · **Demo: ⭐**

- **Actores:** tour director/analista, agente, coach.
- **Trigger:** el ítem del partido pasa a `completed` con resultado (`PATCH /v1/trips/{id}/items/{item}`).
- **Dolor actual ⚠️:** el reporte se redacta a mano después de cada partido, en inglés, en medio de la logística.
- **Flujo en IGS OS:** `post-match-report.json` (trigger `trip_item.status_changed`) → `knowledge_search` + agente en modo tarea con salida estructurada → email al coach (con rama de error a ops).
- **Gap:** ingestión de notas/video del partido; envío real; plantilla de marca.
- **Métrica:** reportes enviados dentro de 12 h del partido; tiempo del staff por reporte.

---

### UC-07 · Opponent matching by level and age group
**Fuente:** home: "carefully matched to your level, age group, and competitive goals"; "pro academy or top club youth sides" · **Prioridad: M** · **Demo: ⭐**

- **Actores:** ventas/ops, coach (pide "un partido exigente").
- **Trigger:** armado o ajuste de un itinerario.
- **Dolor actual ⚠️:** depende de la agenda y la memoria de una o dos personas del equipo local.
- **Flujo en IGS OS:** `plan_itinerary` filtra deporte, género, categoría y ciudad, y elige rivales a ±1 nivel (configurable), nunca dos partidos seguidos ni el mismo rival dos veces; el detalle de la gira muestra el nivel del rival vs. el del equipo; "cambiar rival" desde `/ops/trips/{id}`.
- **Gap:** disponibilidad real de los clubes (calendario), historial de resultados para recalibrar niveles.
- **Métrica:** diferencia de goles promedio (competitividad), satisfacción del coach con los rivales.

---

### UC-08 · Multi-country tour (Argentina + Brazil)
**Fuente:** home: "Train. Compete. Experience." en Argentina y Brasil; rutas `/soccer-argentina`, `/soccer-brazil`, `/volleyball-brazil` · **Prioridad: C**

- **Actores:** coach, ventas.
- **Trigger:** "queremos 6 días en Buenos Aires y 4 en Río".
- **Dolor actual ⚠️:** combina dos equipos locales y dos monedas/proveedores.
- **Flujo en IGS OS:** hoy se arma como dos giras o a mano; el catálogo ya tiene rivales, experiencias y proveedores de Río y San José.
- **Gap:** el planificador trabaja **una sola ciudad** (`TeamProfile.city`); faltan tramos, vuelo interno y precio combinado.
- **Métrica:** propuestas multi-país enviadas; margen por gira combinada.

---

### UC-09 · Deposits and payment plan follow-up
**Fuente:** `/terms-and-conditions` (fee US$95, plan manual US$500/30 d · US$500/90 d · saldo a 110 d, late fee US$100, cancelación a 30 días de mora) · **Prioridad: M**

- **Actores:** finanzas/ops, cada viajero o su familia, coach/AD.
- **Trigger:** vencimientos por viajero.
- **Dolor actual ⚠️:** con 20–35 viajeros por gira y tres planes de pago, el seguimiento de mora es manual y sensible.
- **Flujo en IGS OS:** "Reserve" en la propuesta crea una aprobación `request_deposit` (`POST /v1/public/proposals/{ref}/reserve`); la salud de la cuenta pasa a ámbar/rojo por saldo vencido (reglas deterministas, `igs_common.accounts.health`); recordatorios como flow con `wait` hasta cada vencimiento.
- **Hecho (2026-10-23):** calendario de pagos con los términos reales, riesgos por gira (`list_payment_risks`), recordatorios diarios redactados con IA y validados contra los datos, siempre en la bandeja de aprobaciones, y salud de Account 360 alimentada por el calendario. Ver `docs/architecture/payments.md`.
- **Gap:** pagos por viajero individual (hoy el libro es por gira, vía importador), integración con la pasarela, mails a padres en giras juveniles.
- **Métrica:** días de mora promedio; cancelaciones por falta de pago.

---

### UC-10 · Returning client: "how is this account doing?"
**Fuente:** "How did you hear about us?" → *Returning Customer*; testimonios de programas recurrentes (Gustavus Adolphus, UW Oshkosh, DME Academy) · **Prioridad: M** · **Demo: ⭐**

- **Actores:** AE que retoma la cuenta, CEO/COO.
- **Trigger:** vuelve a escribir un programa que ya viajó, o se acerca la reunión de presupuesto.
- **Dolor actual ⚠️:** el historial vive en mails y en la cabeza de quien lo atendió.
- **Flujo en IGS OS:** `/ops/accounts/{id}`: salud con motivo (reglas), stakeholders con influencia y sentimiento, compromisos y riesgos con fuente; `POST /v1/accounts/{id}/ask` responde con citas o dice que no sabe; copiloto ⌘J / MCP `get_account_brief`, `search_account_history`, `list_stakeholders`.
- **Gap:** ingesta automática de email/WhatsApp reales (hoy interacciones del seed); CRM sync.
- **Métrica:** tiempo para prepararse antes de una llamada; tasa de recompra.

---

### UC-11 · Referral from a happy program
**Fuente:** *Referral / Word of Mouth* en el formulario; testimonios de coaches y padres · **Prioridad: S**

- **Actores:** coach que recomienda, nuevo prospecto, AE.
- **Trigger:** un lead llega con source = referral.
- **Dolor actual ⚠️:** se pierde quién recomendó a quién y no se agradece ni se mide.
- **Flujo en IGS OS:** `leads.source` ya modela `referral`; las interacciones del seed registran referencias cruzadas (Northfield → Maple Grove); el agente puede citar al referente en la primera respuesta.
- **Gap:** relación explícita cuenta→cuenta referida, programa de incentivos, flow de agradecimiento.
- **Métrica:** % de leads por referido y su tasa de cierre.

---

### UC-12 · New ops staff onboarding with institutional knowledge (RAG)
**Fuente:** "45+ years of combined experience", equipo de ~25 personas con muchos SDR/AE (`/about`); términos y políticas extensos (`/terms-and-conditions`) · **Prioridad: S** · **Demo: ⭐**

- **Actores:** SDR/AE o coordinador nuevo.
- **Trigger:** "¿qué pasa si cancelan a 60 días?", "¿qué incluye el paquete colegio?".
- **Dolor actual ⚠️:** las respuestas dependen de preguntarle a alguien senior.
- **Flujo en IGS OS:** base de conocimiento indexada (BGE-M3 híbrido + reranker, `igs_common.rag`), `search_knowledge` en copiloto y MCP, respuestas con citas; cuarentena de contenido sospechoso al ingerir.
- **Gap:** cargar los documentos reales de IGS (T&C, contratos de proveedores, guías); pantalla de Conocimiento (diseñada, no construida).
- **Métrica:** preguntas resueltas sin escalar; tiempo hasta que un SDR nuevo cotiza solo.

---

### UC-13 · Private school decision with multiple approvers
**Fuente:** `/private-school-sports-tours` ("Athletic Directors, Heads of School", "school calendars and approvals", "12 to 18 months") · **Prioridad: S**

- **Actores:** coach (champion), Athletic Director y Head of School (decisores), finanzas del colegio.
- **Trigger:** propuesta enviada; el colegio entra en su circuito de aprobación.
- **Dolor actual ⚠️:** el deal se enfría porque el coach no logra mover al AD; IGS no ve quién bloquea.
- **Flujo en IGS OS:** stakeholders con rol (`athletic_director`, `decision_maker`, `champion`), aviso de "decisor sin contacto hace >21 días" en la salud de la cuenta; el copiloto sugiere el próximo paso.
- **Gap:** materiales por rol (seguridad para el Head of School, presupuesto para finanzas), recordatorios por stakeholder.
- **Métrica:** ciclo de venta (días de propuesta a seña).

---

### UC-14 · AFA Soccer Camps USA — waitlist to enrollment
**Fuente:** `/individual-experiences/usa-camps` (8–18 años, 17 ciudades, "JOIN THE WAITLIST", feedback individual por jugador) · **Prioridad: W (fuera del v0)**

- **Actores:** padres de jugadores individuales, coordinación de camps.
- **Trigger:** se abren fechas por ciudad.
- **Dolor actual ⚠️:** waitlist sin segmentar por ciudad/edad y feedback individual escrito a mano.
- **Flujo en IGS OS:** un flow por ciudad con `map` sobre la waitlist; el agente redacta el feedback individual ("strength, development area and recommendation") desde las notas del coach, siempre con aprobación.
- **Gap:** modelo de inscripción individual (no equipo), pagos B2C.
- **Métrica:** conversión waitlist → inscripción; tiempo por feedback.

## Matriz caso de uso → capacidad

✅ existe y se ve en el demo · 🟡 existe parcial / con datos de demo · ⬜ no existe

| Capacidad (dónde vive) | 01 | 02 | 03 | 04 | 05 | 06 | 07 | 08 | 09 | 10 | 11 | 12 | 13 | 14 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Chat público + flow conversacional (`/chat`, `public_chat.py`, `inbound-inquiry`) | ✅ | 🟡 | 🟡 | | | | | | | | 🟡 | | | 🟡 |
| Planificador + precio (`domain/planner.py`, `pricing.py`) | ✅ | ✅ | ⬜ | | 🟡 | | ✅ | ⬜ | 🟡 | | | | | |
| Propuesta pública + Reserve (`/proposal/[id]`) | ✅ | ✅ | ⬜ | | | | | 🟡 | ✅ | | | | ✅ | |
| Aprobaciones con huella (`/ops/approvals`, `approvals.py`) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | | | ✅ | | | | | ✅ |
| Flows durables + eventos (Temporal, `executions.py`, outbox) | ✅ | ✅ | ✅ | ✅ | 🟡 | ✅ | | | 🟡 | | 🟡 | | | 🟡 |
| Ítems de gira con estado (`PATCH /v1/trips/.../items/...`, `/ops/trips/[id]`) | | ✅ | | ✅ | ✅ | ✅ | ✅ | | | | | | | |
| Account 360: salud, stakeholders, hechos citados, ask (`/ops/accounts`) | 🟡 | ✅ | | | | | | | ✅ | ✅ | ✅ | | ✅ | |
| RAG con citas (`igs_common.rag`, `search_knowledge`) | 🟡 | | | | | ✅ | | | | ✅ | | ✅ | | |
| Copiloto ⌘J + MCP (16 tools) | 🟡 | ✅ | ✅ | ✅ | ✅ | | ✅ | | | ✅ | | ✅ | ✅ | |
| Leads kanban (`/ops/leads`, `/v1/leads`) | ✅ | | | | | | | | | | ✅ | | ✅ | |
| Incidentes (tabla `incidents`) | | | | | ⬜ | | | | | | | | | |
| Portal de familias / datos de menores cifrados | | ⬜ | ⬜ | | | | | | 🟡 | | | | | ⬜ |
| Canales reales (email/WhatsApp) | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | | | ⬜ | | | | | ⬜ |
| Pagos por viajero / pasarela | | ⬜ | ⬜ | | | | | | ⬜ | | | | | ⬜ |

## Top 3 gaps que conviene construir después

1. **Canales reales con respuesta parseada (email + WhatsApp)** — desbloquea UC-01, 02, 04, 05, 06 y 09. Hoy todo sale al outbox; con un adaptador de salida y un parser de respuestas ("confirmado"/"no llegamos") los flows existentes pasan de demo a operación sin cambiar su lógica.
2. **Viajeros y pagos por persona alineados a los términos reales** — roster por gira, plan de pagos (US$95 + US$500/30 d + US$500/90 d + saldo a 110 d), recordatorios y mora como flows, y datos de menores en un almacén cifrado fuera del LLM. Es el corazón de UC-02, 09 y 03, y corrige la inconsistencia del seed (30 % de seña).
3. **Incidentes en campo + modo mobile** — API y pantalla sobre la tabla `incidents` que ya existe, sustitución de rival con el planificador y aviso al coach con aprobación. Es el momento en que el tour director más necesita el producto (UC-05) y alimenta Account 360 con lo que pasó en la gira.

## Preguntas para validar con IGS

1. ¿Cuántas consultas por semana entran y cuánto tarda hoy la primera propuesta real?
2. ¿Dónde viven hoy las confirmaciones de proveedores y los pagos por viajero (planilla, CRM, sistema propio)?
3. ¿Qué porcentaje de ventas viene de clientes recurrentes y referidos?
4. ¿Cómo se coordinan hoy los cambios en el Family Experience 2027 si la USWNT cambia de sede?
5. ¿Qué herramienta usan hoy para el reporte post-partido y el video?
