# Propuesta 07 — Compañero de gira (On-Tour Companion)

> Un asistente de IA que acompaña al equipo **durante** la gira, por WhatsApp y un portal web liviano, conectado a la operación de IGS OS. No reemplaza al tour leader: lo descarga de lo repetitivo y lo llama cuando importa.

**Estado:** propuesta. Todo lo que dice sobre la operación interna de IGS es hipótesis inferida de su sitio público, a validar con IGS.

## 1. Por qué

El sitio de IGS promete tres cosas que se juegan *en la gira*, no en la venta:

| Promesa pública (infinityglobalsports.com) | Dónde duele hoy (hipótesis) |
|---|---|
| Tour leader bilingüe 24/7 | Un solo humano absorbe todas las preguntas repetidas ("¿a qué hora sale el micro?", "¿qué traemos?") y las urgencias reales compiten con ellas |
| Micro privado, hoteles en zonas seguras | Un cambio (micro demorado, partido movido) se avisa por grupos de WhatsApp manuales; nadie sabe quién lo leyó |
| Experiencia premium "Train. Compete. Experience." | La satisfacción se mide al final (si se mide); un problema del día 3 se descubre en la encuesta del día 12 |

El compañero convierte la gira en algo **observable** para ops y **sin fricción** para el equipo.

## 2. Qué hace

| Capacidad | Para quién | Cómo |
|---|---|---|
| **Agenda del día** | Coach, staff, padres (adultos) | Cada mañana: plan del día desde los `trip_items` (hora local del destino, punto de encuentro, ropa, qué llevar). Consultable a demanda: "¿a qué hora es el partido?" |
| **Cambios en tiempo real** | Todos los adultos del grupo | Ops cambia un ítem en IGS OS (micro +30 min, partido movido) → evento `trip_item.status_changed` → flow → aviso al grupo con lo que cambió y qué hacer. Confirmación de lectura por persona |
| **Ayuda multilingüe** | Equipo (EN), con proveedores locales (ES/PT) | Traducción EN↔ES/PT de menús, carteles, frases para el árbitro o el mozo; foto → traducción. Frases útiles por destino desde la base de conocimiento |
| **Seguridad y emergencias** | Coach, staff, padres | Palabras y botones de emergencia ("lesión", "perdido", "médico", "policía") → **nunca responde la IA sola**: crea un incidente en IGS OS, llama/avisa al tour leader 24/7 y al líder de ops, y da los datos de contacto locales (hospital más cercano al hotel, número de emergencia del país) mientras tanto |
| **Recordatorios** | Coach y adultos | Antes de salir: pasaporte, formularios médicos, seguro, ropa por clima. Durante: "mañana salimos 7:30, uniforme visitante" |
| **Fotos del día (con consentimiento)** | Coach/staff | Al final del día invita a subir fotos a una carpeta privada de la gira; solo adultos suben; sin reconocimiento facial; los menores no se etiquetan; el material se usa para el recap solo con permiso explícito |
| **Pulso de satisfacción nocturno** | Coach y adultos | Una pregunta por noche (1–5 + comentario opcional). Un 1–2 abre un incidente "experiencia" en ops con el texto → se corrige al día siguiente, no en la encuesta final |
| **Cierre** | Coach / AD | Encuesta final (NPS + 3 preguntas), pedido de testimonio y de referido si NPS ≥ 9, recap del viaje (itinerario + resultados de partidos + fotos aprobadas) |

## 3. Canales

- **WhatsApp** (principal): es donde ya está el equipo. Un número de IGS por destino o uno global con contexto por gira.
- **Portal web liviano** `/trip/{token}` (complemento): itinerario vivo, documentos, contactos de emergencia, fotos, encuesta. Acceso por link mágico, sin cuenta. Ya está diseñado en `docs/design/coach-experience.md` §3 (portal del viaje).

### Restricciones de WhatsApp Business que condicionan el diseño (verificar contra la política vigente de Meta)

| Regla | Consecuencia en el producto |
|---|---|
| **Ventana de 24 h**: solo se pueden enviar mensajes libres dentro de las 24 h del último mensaje del usuario; fuera de esa ventana, solo **plantillas aprobadas** | Agenda diaria, cambios y recordatorios se envían como **plantillas de categoría Utility** (pre-aprobadas por destino/idioma). Las respuestas conversacionales ocurren dentro de la ventana que abre el usuario al responder |
| **Categorías de plantilla** (Marketing / Utility / Authentication) y **cobro por plantilla entregada**; Meta puede **reclasificar** una plantilla según cómo responden los usuarios | Todo lo operativo, en Utility y sin contenido promocional. El pedido de testimonio/referido es **Marketing** (se cobra y se trata aparte, con opt-in explícito) |
| **Opt-in**: el usuario tiene que aceptar recibir mensajes del negocio por WhatsApp | Opt-in en el formulario de inscripción y en el portal, por persona, con registro de fecha/canal; baja en un toque ("STOP") |
| Precios y reglas cambiaron el 1/10/2026 (según proveedores) | Presupuestar por plantilla entregada × viajero × día; revisar la tabla oficial de Meta antes de cotizar |

El costo por gira es bajo (decenas de plantillas Utility por adulto por gira), pero hay que medirlo con la tabla oficial.

## 4. Menores: regla dura

Muchas giras son de equipos juveniles (U13–U19, high school, clubes). Por eso:

- **El compañero nunca le escribe a un menor.** Los destinatarios son adultos registrados: coach, staff, chaperones y **padres/tutores**.
- Los datos de jugadores (nombre, edad, pasaporte, ficha médica) **no pasan por el LLM ni por embeddings**, en línea con `docs/architecture/security.md` §3.7. El compañero trabaja con el itinerario y con datos de adultos.
- Las fotos con menores solo se suben a la carpeta privada de la gira, sin etiquetar, y cualquier uso público requiere consentimiento escrito del tutor.
- Si un menor escribe al número, responde un mensaje fijo (no generado) que lo deriva a su coach y avisa al coach.

## 5. Guardarraíles de IA

| Riesgo | Control |
|---|---|
| Inventa un horario o un lugar | Solo responde horarios, direcciones y precios **desde los datos de la gira** (tools de lectura); si no está, dice que no sabe y ofrece pasar con el tour leader |
| Responde una emergencia como si fuera una consulta | Clasificador de urgencia + palabras clave → flow de emergencia **sin LLM en el camino crítico** (mensaje fijo, incidente, llamada al leader) |
| Cambia algo de la gira | El compañero es de **solo lectura** sobre la operación. Pedidos de cambio ("¿podemos mover el entrenamiento?") se convierten en una **aprobación** para ops, como en el resto de IGS OS |
| Instrucciones inyectadas (un mensaje o una foto con texto "ignorá las reglas") | Mismas defensas que el copiloto: tool classes, contenido del usuario tratado como dato, red-team evals en CI (`docs/architecture/evals-and-testing.md`) |
| Tono/idioma | Plantillas fijas para avisos; texto generado solo en conversación, en el idioma del usuario, con un recordatorio visible de que es una IA y cómo llegar a una persona |

## 6. Qué ya existe en IGS OS (y qué falta)

| Pieza | Estado en el repo |
|---|---|
| Ítems de gira con estado, hora, alerta y proveedor; `PATCH /v1/trips/{id}/items/{item}` | ✅ `services/core/src/igs_core/api/v1/trips.py` |
| Evento `trip_item.status_changed` vía outbox → flows | ✅ `services/core/src/igs_core/events/` + dispatcher |
| Motor de flows durable con esperas, aprobaciones y nodos conversacionales (`say`/`capture`/`choice`) | ✅ `services/worker/` sobre Temporal |
| Incidentes | ✅ tabla `incidents` (`packages/py-common/src/igs_common/db/models`) — falta UI de incidentes en ops |
| Outbox de mensajes salientes (sin envío real) | ✅ outbox; ❌ **falta el conector de WhatsApp Business** (envío de plantillas, webhook de entrada, estados de entrega) |
| Base de conocimiento con citas (RAG) | ✅ `igs_common.rag` — falta contenido por destino (emergencias, frases, barrios) |
| Portal del viaje | 🟡 diseñado (`docs/design/coach-experience.md`), no construido |
| Copiloto/tool registry con clases de riesgo | ✅ `services/core/src/igs_core/agent/` — el compañero reusa las tools de lectura |
| Pulso nocturno, encuesta y NPS | ❌ falta (flow + tabla de respuestas + panel en ops) |

## 7. KPIs

| KPI | Línea base (a medir) | Meta del piloto (hipótesis) |
|---|---|---|
| NPS de la gira | encuesta actual de IGS (si existe) | +10 puntos |
| Tiempo de resolución de incidentes (detectado → resuelto) | no se mide hoy | mediana < 2 h para incidentes no médicos |
| Problemas detectados durante la gira vs. en la encuesta final | 0 % durante (hipótesis) | > 70 % detectados por el pulso nocturno |
| Preguntas repetitivas que llegan al tour leader | todas | −50 % (las resuelve el compañero con datos de la gira) |
| Lectura de avisos de cambio | desconocida | > 90 % de adultos confirman en 30 min |
| Testimonios y referidos por gira | — | ≥ 1 testimonio y ≥ 1 referido por cada 3 giras |

## 8. Esfuerzo

| Pieza | Talla |
|---|---|
| Conector WhatsApp Business (plantillas, webhook, estados, opt-in) | **M** |
| Flows: agenda diaria, aviso de cambio, recordatorios, pulso nocturno, cierre | **S** (el motor ya existe) |
| Flow de emergencia + UI de incidentes en ops | **M** |
| Traducción y frases por destino (KB + tool de traducción) | **S** |
| Portal del viaje (link mágico, itinerario vivo, fotos, encuesta) | **M** |
| Fotos con consentimiento (storage privado, permisos, retención) | **M** |
| Evals (urgencia, no-invención de horarios, menores, inyección) | **S** |
| **Total piloto** | **L** |

## 9. Riesgos

| Riesgo | Mitigación |
|---|---|
| Meta reclasifica plantillas o cambia precios | Plantillas estrictamente operativas; presupuesto con margen; monitorear la categoría de cada plantilla |
| Un aviso automático equivocado (hora mal cargada) llega a 60 personas | Avisos solo desde cambios hechos por ops en IGS OS; vista previa + aprobación para cambios de último momento |
| El equipo no se suma (otro número, otro bot) | Opt-in en la inscripción, presentación por el coach el día 1, un solo número y mensajes cortos |
| Datos de menores | Regla dura del §4, revisión legal (COPPA, LGPD, Ley 25.326) antes de producción |
| Dependencia de conectividad | El portal funciona offline con el itinerario cacheado; los avisos críticos también por SMS de respaldo (opcional) |
| La IA "habla de más" en una emergencia | Camino crítico sin LLM, mensajes fijos, escalamiento humano inmediato |

## 10. Piloto propuesto

- **Alcance:** 1 gira de un equipo universitario (adultos, menos fricción con menores) a Buenos Aires, 10 días.
- **Incluye:** agenda diaria, avisos de cambio, emergencias con escalamiento, recordatorios, pulso nocturno, encuesta final. Fotos y portal: opcionales.
- **Antes de la gira:** opt-in de coach y staff; plantillas Utility aprobadas en EN; contenido de emergencias y frases para Buenos Aires en la KB; ensayo con el tour leader.
- **Durante:** el tour leader ve en IGS OS los incidentes y el pulso de cada noche; ops cambia ítems y el aviso sale solo.
- **Éxito:** NPS ≥ la línea base +10, cero incidentes críticos atendidos por la IA sin escalar, tour leader reporta menos preguntas repetidas, ≥ 90 % de lectura de avisos.
- **Después:** decidir si se extiende a padres de equipos juveniles (con el portal y las reglas de menores) y a las *family experiences* del Mundial Femenino 2027.

## Fuentes

- Promesas de IGS: [infinityglobalsports.com](https://infinityglobalsports.com/) (tour leader bilingüe 24/7, micro privado, hoteles seguros).
- WhatsApp Business (guías de terceros; confirmar contra Meta): [Meta — Pricing on the WhatsApp Business Platform](https://developers.facebook.com/docs/whatsapp/pricing), [Courier — WhatsApp pricing explained](https://www.courier.com/guides/whatsapp-pricing), [eGrow — template pricing 2026](https://www.egrow.com/en/blog/whatsapp-template-pricing-explained-2026), [SleekFlow — templates](https://sleekflow.io/en-us/blog/whatsapp-business-template), [Kommo — updated pricing rules](https://support.kommo.com/docs/updated-pricing-rules-for-whatsapp-business), [QuickReply — API pricing 2026](https://www.quickreply.ai/whatsapp-automation/whatsapp-business-api-pricing).
- Repo: `docs/architecture/security.md` (datos de menores), `docs/design/coach-experience.md` (portal del viaje), `docs/architecture/flow-engine.md`.
