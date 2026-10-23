# Propuesta 01: Concierge de IA en el sitio, de la consulta a la propuesta en minutos

> **En una línea:** un agente en infinityglobalsports.com que conversa con el coach o el director, califica la consulta en el mismo chat y le muestra una muestra de itinerario al instante. La propuesta formal sale después, cuando la aprueba una persona de IGS. Es un agente con tools, no un builder tipo Voiceflow. Todo lo que dice este documento sobre la operación interna de IGS es **hipótesis** y hay que validarlo con IGS.

## 1. Evidencia (lo que publica el sitio)

| Hecho | Fuente | Qué implica |
|---|---|---|
| El formulario pide programa, rol, teléfono, ventana de viaje, "cómo nos conociste" y sitio web. **No pide deporte, nivel, categoría, cantidad de viajeros, duración ni presupuesto.** | `/plan-a-tour` | Alguien de IGS tiene que volver a contactar al coach para calificar antes de poder armar opciones. |
| Promesa: *"We will respond with sample itinerary options within 1 business day."* | `/plan-a-tour` (meta y bullets) | El SLA es público y se mide en días hábiles, cuando se puede medir en minutos. |
| "How did you hear about us?" incluye **AI Assistant (ChatGPT, Gemini, etc.)** | `/plan-a-tour` | IGS ya sabe que una parte de sus clientes llega desde asistentes de IA. Esos clientes esperan una respuesta conversacional. |
| Roles: Head Coach, Assistant Coach, Director of Coaching, Executive Director, Athletic Director, Head of School | `/plan-a-tour` | Quien escribe no siempre decide, así que hay que capturar al decisor y el proceso de aprobación (PO, board, calendario escolar). |
| Grupos de 20 a 35 viajeros, planificación de 12 a 18 meses antes, rivales "carefully matched to your level" | `/college-soccer-tours`, home | El itinerario de muestra se puede armar con reglas conocidas: días, entrenamientos, hasta 3 amistosos y rival por nivel. |
| Oficinas en Buenos Aires, Nueva York y Denver | `/about` | Una consulta que llega un viernes a la noche en Denver se atiende el lunes en Buenos Aires. El agente atiende en el momento. |

## 2. Qué hace

1. **Conversa en lugar de mostrar el formulario**, o al lado del formulario con un "¿preferís chatear?". Hace una pregunta por turno, en inglés por defecto y en español o portugués si el usuario escribe así.
2. **Califica:** deporte, género, categoría, nivel (D1/D2/D3/NAIA/JUCO, club ECNL/MLS NEXT/regional, high school), viajeros (jugadores y staff), ventana y duración, destino (Argentina, Brasil, España, Costa Rica), presupuesto por persona, decisor y fecha de decisión.
3. **Responde preguntas frecuentes con citas** a las páginas del sitio y a los términos: inscripción de US$95, cuotas, reembolsos escalonados, seguro y reglas para menores. Usa RAG sobre el contenido público, el mismo `search_knowledge` que ya existe.
4. **Muestra un itinerario de muestra al instante**, con días, entrenamientos, amistosos contra rivales de su nivel y experiencias. Va marcado como *"sample, final proposal reviewed by our team"*. Lo arma el planner determinístico (`igs_common.domain.planner.plan_itinerary`), no el LLM, así que no inventa estadios ni rivales.
5. **Da un rango de precio, no un precio cerrado.** Por ejemplo *"most programs like yours land between US$X and US$Y per traveler"*, con una tabla de rangos que define IGS. El precio exacto lo pone una persona.
6. **Hace el handoff:** crea el lead con todo calificado, le ofrece al coach agendar una llamada (Calendly o Google Calendar) y le deja a ops un borrador de propuesta en la bandeja de aprobaciones. Nada sale hacia el cliente sin aprobación.
7. **Sigue el hilo:** si el coach vuelve días después, el agente retoma la charla con el contexto (Account 360). Si pasa X días sin respuesta, propone un follow-up y el follow-up también pasa por aprobación.

### Ejemplo

> **Coach:** We're a D2 women's soccer program, thinking about Argentina next May.
> **Concierge:** Great fit, we run several of those every spring. How many travelers would you bring, players plus staff?
> **Coach:** 26 total, 9 or 10 days.
> **Concierge:** Here's a sample 9-day Buenos Aires itinerary for a D2 women's program: 2 sessions at pro academies, 3 friendlies against club sides at your level (no back-to-back match days), a Superclásico-week stadium visit and a tango night. Programs like yours usually land between US$X and US$Y per traveler, with a US$95 enrollment per traveler to hold the dates. Who signs off on the trip at your school, you or the athletic director?

## 3. Por qué no hace falta un "Voiceflow"

La conversación tiene un objetivo claro (calificar y mostrar valor) y un conjunto cerrado de acciones. Eso se resuelve con **un agente con tools y un esquema de lead**, no con un diagrama de nodos:

| Pieza | Implementación |
|---|---|
| Comportamiento | Un system prompt versionado en el repo, con tono de marca, reglas (nunca prometer precio cerrado, nunca hablar de menores con datos personales) y el esquema de calificación |
| Memoria del turno | El estado de la conversación es un objeto `LeadDraft` con los campos de la sección 2. El agente llena huecos y no repite preguntas. |
| Tools | `search_site_knowledge`, `sample_itinerary`, `price_range`, `create_or_update_lead`, `book_call`, `request_human` |
| Seguridad | Las tools que escriben hacia afuera devuelven `approval_required`, que es el mismo patrón de aprobaciones de IGS OS |
| Evals | 30 a 50 conversaciones guionadas (coach apurado, padre que entra por error, pregunta por precio, intento de prompt injection) que corren en CI con un juez |

IGS OS ya tiene el flow `inbound-inquiry` y el editor visual. Son útiles si IGS quiere que un no-programador cambie el guion, pero para v1 alcanza con el agente. Ver la [propuesta 10](10-lean-ai-stack.md).

## 4. Dónde vive

- **Widget** en el sitio actual (un `<script>` que abre un panel con el estilo del sitio) en `/plan-a-tour` y en las páginas de producto. En cada página de producto el agente ya sabe el contexto ("vengo de College Soccer Tours").
- **Página propia** `/plan-a-tour/chat` para campañas y links de email.
- **WhatsApp Business**, más adelante, con el mismo agente detrás. Muchos coaches latinoamericanos y padres lo prefieren. Ver la [propuesta 07](07-on-tour-companion.md).
- **Asistentes de IA externos**: el mismo set de tools se expone como un MCP público de solo lectura (`find_tour`, `sample_itinerary`), así ChatGPT o Gemini pueden responder con datos de IGS. Complementa el trabajo de AEO de la [propuesta 05](05-ai-content-seo.md).

## 5. Qué ya existe en IGS OS

| Existe | Falta |
|---|---|
| Chat público (`/chat`, `services/core/src/igs_core/api/v1/public_chat.py`) con streaming | Widget embebible para el sitio de IGS |
| Planner con rivales por nivel y precios (`plan_itinerary`, `pricing.quote`) | Tabla de rangos de precio que defina IGS |
| Leads (`/ops/leads`), aprobaciones con hash, Account 360 | Captura de decisor y fecha de decisión como campos de primera clase |
| RAG híbrido con citas (`search_knowledge`) | Ingesta del contenido público del sitio y de los términos |
| Propuesta pública (`/proposal/{ref}`) | Integración de agenda (Calendly o Google Calendar) y del CRM que use IGS hoy |
| Evals con juez (`evals/`) | Set de conversaciones del concierge |

## 6. Guardarraíles

- **Precio:** solo rangos predefinidos. Cualquier cifra exacta sale de una propuesta aprobada.
- **Menores:** si quien escribe es un padre o un jugador menor, el agente no pide datos personales del menor y deriva al club o a la experiencia de familias.
- **Promesas:** no confirma disponibilidad de rivales, estadios ni fechas. Usa siempre "sample" y "subject to availability".
- **Prompt injection:** las tools que escriben están detrás de aprobación y el contenido recuperado se trata como dato, nunca como instrucción.
- **Datos:** la conversación se guarda con consentimiento visible y se borra a pedido. El lead lleva el origen `concierge`.
- **Escalado humano:** el agente siempre ofrece "talk to a person". Si detecta enojo, una urgencia o un caso fuera de alcance, crea una tarea para ventas.

## 7. KPIs

| KPI | Línea base (hipótesis) | Objetivo |
|---|---|---|
| Tiempo a primera respuesta con itinerario de muestra | Hasta 1 día hábil | Menos de 2 minutos (muestra) y menos de 4 horas hábiles (propuesta aprobada) |
| % de leads que llegan calificados (8 campos o más) | Bajo, porque el formulario pide 5 campos y ninguno de calificación | Más del 70% |
| Conversión de visita a lead en `/plan-a-tour` | A medir | Más 20% a 50% relativo |
| Conversión de lead a reserva (fee de US$95 pagado) | A medir | Más 10% a 25% relativo |
| Horas de SDR por lead hasta la primera propuesta | A medir | Menos 40% a 60% |
| % de conversaciones derivadas a humano | n/a | Entre 10% y 25% (si es menos, el agente puede estar sobreprometiendo) |
| Calidad (juez y revisión semanal de 20 charlas) | n/a | 0 promesas de precio cerrado y 0 datos de menores capturados |

## 8. Impacto esperado (rangos, con supuestos)

Supuestos a validar: cientos de consultas por año, ticket promedio de unos US$3.000 a US$4.500 por viajero, grupos de 20 a 35 personas, o sea una gira de US$60.000 a US$150.000.

- **Conversión:** si de 300 consultas anuales hoy se cierra un 10% (30 giras) y el concierge sube la conversión de 10% a 25% relativo, son **3 a 8 giras más por año**. Eso equivale a unos **US$200.000 a US$1.000.000 de facturación adicional**, según el ticket.
- **Captura nocturna y de fin de semana:** las consultas que hoy esperan un día hábil se atienden en el momento. Es la principal palanca contra el operador rival que contesta primero; en el caso Lakeshore de la demo, el rival cotizó US$2.750.
- **Eficiencia:** si un SDR dedica hoy 30 a 60 minutos a calificar cada lead, recupera **150 a 300 horas por año** para cerrar ventas en lugar de preguntar datos.

## 9. Esfuerzo (sobre IGS OS)

| Pieza | Esfuerzo |
|---|---|
| Agente concierge (prompt, `LeadDraft`, tools existentes) y evals | **S** |
| Ingesta del sitio y de los términos al RAG público | **S** |
| Widget embebible con el estilo del sitio | **S** |
| Rangos de precio y reglas de negocio definidos con IGS | **S** (es trabajo de IGS más que de ingeniería) |
| Integración de agenda y del CRM de IGS | **M** |
| WhatsApp Business con el mismo agente | **M** |
| MCP público para asistentes de IA | **S** |

## 10. Piloto propuesto

1. **Semanas 1 y 2:** concierge en una página de producto (College Soccer Tours), sin reemplazar el formulario, con A/B 50/50 entre chat y formulario. Ventas revisa todas las charlas.
2. **Semanas 3 y 4:** se ajustan el prompt y los rangos con lo aprendido y se extiende a `/plan-a-tour` y a Youth Club.
3. **Decisión** con datos: conversión visita a lead, calidad del lead y tiempo a primera propuesta. Se decide si el chat pasa a ser la opción principal.

## 11. Riesgos

| Riesgo | Mitigación |
|---|---|
| El agente sobrepromete (precio, rival, fecha) | Rangos fijos, "sample" obligatorio, evals en CI y revisión semanal |
| Los coaches prefieren el formulario | El formulario sigue disponible y el A/B decide |
| Leads de baja calidad (curiosos) | Calificación antes de ofrecer la llamada y score de lead visible para ventas |
| Costo del LLM | Del orden de centavos por conversación con `gpt-6-luna` para charla y el modelo grande solo para el itinerario; irrelevante contra el ticket |
| Marca | Tono validado por IGS y respuestas revisadas en el piloto |

## 12. Preguntas para validar con IGS

1. ¿Cuántas consultas por mes entran por `/plan-a-tour` y qué porcentaje termina en reserva?
2. ¿Cuánto tarda hoy en promedio la primera propuesta, y quién la arma?
3. ¿Qué rangos de precio por persona están cómodos de mostrar en público?
4. ¿Qué CRM usan hoy (HubSpot, Salesforce, planilla) y cómo agendan las llamadas?
5. ¿Cuántos leads llegan con "AI Assistant" como origen? ¿Crece?
6. ¿Quién decide la compra en cada segmento (coach, AD, board, padres)?

## Fuentes

- https://infinityglobalsports.com/plan-a-tour (formulario y SLA, relevado el 2026-10-22)
- https://infinityglobalsports.com/college-soccer-tours
- https://infinityglobalsports.com/terms-and-conditions
- https://infinityglobalsports.com/about
- `docs/delivery/use-cases.md` (UC-01)
