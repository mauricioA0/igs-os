# Propuesta 04 — "IGS Performance": análisis de rendimiento asistido por IA como producto premium

> Autor: B4 (estratega de producto, analítica deportiva). Fecha: 2026-10-22.
> Todo lo que se afirma sobre la operación interna de IGS es **hipótesis** a validar con IGS. Las cifras de impacto son rangos con supuestos explícitos, no promesas.

## 1. Resumen

IGS ya vende, dentro de la gira, *pre-match scouting reports*, *post-match performance analysis* y *video analysis & review* (home de infinityglobalsports.com, sección de qué incluye una gira, relevada el 2026-10-22). Hoy eso es un **componente del paquete**, probablemente artesanal (hipótesis: un analista o el staff local mira video y arma un PDF). La propuesta es convertirlo en un **producto con nombre propio — "IGS Performance"** — con tres capas:

1. **Scouting automático** de cada rival antes del partido.
2. **Video del partido → highlights y clips por jugador** en 24 h, con un portal para el coach.
3. **Reels para recruiting universitario y reels de marca compartibles**, que son el gancho emocional para jugadores y familias y, a la vez, el loop de marketing de IGS.

Por qué ahora: el mercado de EE.UU. (clubes juveniles y college) **ya paga por video y highlights** (Veo, Trace, Hudl son estándar en clubes), y para un jugador de 15–18 años un *highlight reel* jugando contra una academia argentina es material de recruiting diferencial. IGS tiene algo que ningún proveedor de cámaras tiene: **el rival, el contexto y la historia** (Bombonera, academia, nivel del rival).

## 2. Evidencia y puntos de partida

| Evidencia | Fuente | Qué implica |
|---|---|---|
| Las giras incluyen scouting pre-partido, análisis post-partido y review de video | Home de IGS (sección "what's included", relevada 2026-10-22) | Ya existe la promesa y la expectativa; falta escala y consistencia |
| Las páginas por segmento (college, club) no mencionan video ni recruiting | `/college-soccer-tours` (2026-10-22) | Oportunidad de **empaquetar y comunicar** lo que ya hacen |
| Rivales elegidos "a tu nivel, edad y objetivos" | Home de IGS | El scouting puede apoyarse en ese matching (sabemos el nivel de ambos equipos) |
| Clientes: college (D1–D3, NAIA) y clubes juveniles de EE.UU. | Home, testimonios, `/youth-club-soccer-tours` | Público que ya consume video (Veo/Trace/Hudl) y piensa en recruiting |
| Mundial Femenino 2027 en Brasil | Home (Family Experiences) | Ventana de contenido compartible de alto alcance |

## 3. Qué ya existe en IGS OS (no partimos de cero)

| Capacidad | Dónde | Cómo la reutilizamos |
|---|---|---|
| Catálogo de rivales con `level_score`, categoría, estilo de juego | `packages/py-common/fixtures/catalog.yaml`, tabla `opponents`; planner `igs_common.domain.planner` (±1 de nivel) | Base del **scouting brief**: nivel relativo, estilo, historial de partidos contra equipos de IGS |
| Flow durable **post-match-report** (se dispara cuando el ítem de partido pasa a `completed`) | `packages/flow-schema/examples/post-match-report.json`; worker `services/worker` | Lo extendemos: "video subido → procesar → highlights → borrador de reporte → **aprobación del coach/ops** → enviar" |
| Resultado del partido en el ítem (`trip_items.result`, estado `completed`) | migración 0001, `PATCH /v1/trips/{id}/items/{item}` | Disparador del pipeline y datos del reporte |
| RAG con citas (BGE-M3 + reranker, pgvector) | `igs_common.rag`, `services/models` | Scouting que cita sus fuentes (partidos previos, notas del staff local, reportes anteriores contra ese rival) |
| Aprobaciones atadas al contenido exacto (hash) | `/v1/approvals`, bandeja de aprobaciones | **Nada se publica sin aprobación**: obligatorio para imágenes de menores |
| Ficha 360 del cliente | `/ops/accounts/[id]` | El historial de reportes y reels del programa queda en la ficha → recompra y referidos |
| Cola de ingesta en Temporal | `INGESTION_WORKFLOWS` en `services/worker` | Mismo patrón para ingerir video (fan-out por segmento) |

Lo que **no** existe: ingesta de video, detección de eventos, tracking de jugadores, editor de clips, portal del coach, consentimientos de imagen.

## 4. El producto

### 4.1 Scouting brief automático (antes de cada partido)
- **Entrada**: rival del catálogo + notas del staff local + partidos previos de IGS contra ese rival + datos públicos (tabla de liga, resultados recientes de la categoría cuando estén disponibles).
- **Salida**: 1 página por rival en inglés: nivel relativo ("un escalón arriba de tu equipo"), estilo (presión alta, juego directo…), jugadores a observar (solo si hay fuente pública y sin datos sensibles de menores), 3 claves tácticas sugeridas, **con citas**.
- **Flujo**: se genera 72 h antes del partido, lo revisa el staff de IGS (aprobación), llega al coach por el portal y por mail.
- **Valor**: hoy (hipótesis) requiere a una persona que conozca al rival; con IA el staff **edita** en vez de **escribir**.

### 4.2 Video → highlights y clips por jugador (después del partido)
- **Captura**: tres niveles, de menor a mayor costo:
  1. Teléfono/trípode o drone del staff (cero hardware nuevo).
  2. Cámara IA de un partner (Veo / Trace) en las sedes recurrentes de Buenos Aires.
  3. Video de la sede si la academia ya filma.
- **Procesamiento**: detección de momentos (goles, ocasiones, atajadas, pelota parada) por audio + movimiento + modelo de visión; el staff o el coach **etiqueta dorsales una sola vez** y el sistema arma clips por jugador.
- **Salida en 24 h**: highlights del partido (3–5 min), un *clip pack* por jugador, y un **borrador de reporte post-partido** (stats básicas, momentos clave, 3 aprendizajes) sobre el flow `post-match-report` existente.

### 4.3 Portal del coach (dentro del portal de la gira)
- Pestaña "Performance" en el portal de la gira (`docs/design/coach-experience.md` §3): scouting de cada rival, video de cada partido, clips por jugador, reporte, comparación entre partidos de la gira.
- El coach decide **qué se comparte** con jugadores y familias (control y consentimiento).
- Exportación a Hudl o al sistema del club si el programa lo usa (evitar lock-in que espante a los coaches).

### 4.4 Reels de recruiting (jugador)
- Reel de 60–90 s por jugador con sus mejores acciones, **con contexto de la gira** ("vs Academia Palermo FC, nivel pro-academy, Buenos Aires, marzo 2027"), listo para enviar a coaches universitarios.
- **Regla**: los reels de menores solo se generan con consentimiento firmado del padre o tutor y del club, y solo se entregan al jugador y su familia. **No se publican**.

### 4.5 Reels de marca (marketing de IGS)
- Montaje automático del día o de la gira: estadio, entrenamiento, partido, cultura. Con plantillas de marca IGS.
- **Solo con consentimiento explícito de uso de imagen para marketing** (separado del de recruiting). Por defecto, sin caras de menores o con desenfoque.
- Loop: el club y las familias lo comparten → alcance orgánico → consultas nuevas. Es la ventaja frente a la competencia en el canal que más pesa (referidos y redes de familias).

## 5. Build vs. partner

| Pieza | Recomendación | Por qué |
|---|---|---|
| Cámara y captura | **Partner** (Veo o Trace) para sedes recurrentes; teléfono/drone como base | No somos fabricantes de cámaras. Veo graba la cancha entera (sirve para táctica) y Trace genera highlights por jugador (sirve para recruiting). Hudl Focus es más caro y conviene solo si el club ya usa Hudl; Pixellot apunta a ligas e instalaciones, no a un operador de giras |
| Detección de momentos y clips | **Partner primero**: usar la salida de Veo/Trace cuando haya cámara; **build liviano** para el video de teléfono/drone (modelo de visión + heurísticas de audio) | El 80% del valor está en tener clips en 24 h; la precisión fina la resuelve el partner |
| Scouting brief | **Build** sobre IGS OS | Es contenido propio de IGS (catálogo, conocimiento del staff local); diferencial que nadie más tiene |
| Reporte post-partido, portal, aprobaciones, consentimientos | **Build** sobre IGS OS | Ya tenemos el flow, el RAG, las aprobaciones y la ficha 360 |
| Reels (montaje, plantillas, música con licencia) | **Build** con un pipeline de edición automática (ffmpeg + plantillas) | Requiere la marca y la historia de IGS; música solo de librerías con licencia |

Hay que pedir cotizaciones escritas 2026 a Veo y Trace (cámara + fee de plataforma). No encontramos precios públicos confiables al 2026-10-22.

## 6. Precio (hipótesis para validar)

| Paquete | Qué incluye | Precio sugerido |
|---|---|---|
| **Incluido** (base actual) | Scouting brief por rival + highlights del partido + reporte post-partido | Sin costo extra: mejora lo que IGS ya promete |
| **Performance Pack** (add-on por equipo) | Clips por jugador de todos los partidos + portal + comparativa de la gira | US$ 25–45 por jugador (≈ US$ 500–1.000 por equipo de 22) |
| **Recruiting Reel** (por jugador, opcional) | Reel 60–90 s con contexto, revisado por staff, en 48 h | US$ 49–99 por jugador |
| **Familias / Mundial 2027** | Reel de la experiencia familiar | US$ 29–59 por familia |

Supuesto de costo variable: cámara de partner amortizada por partido + procesamiento + revisión humana ≈ US$ 150–300 por partido. A validar con las cotizaciones.

## 7. KPIs

- **Tiempo partido → highlights publicados** (meta: < 24 h) y **partido → reporte aprobado** (meta: < 48 h).
- **Adopción del add-on**: % de equipos que compran Performance Pack; % de jugadores que compran reel.
- **Ingreso por gira** incremental.
- **Satisfacción del coach** con el reporte (encuesta 1–5 al cierre de la gira).
- **Alcance de reels de marca** (vistas, compartidos) y **consultas atribuidas** (campo "¿cómo nos conociste?" + UTM).
- **Recompra y referidos** del programa (ficha 360).
- **Incidentes de privacidad**: 0 (gate obligatorio).

## 8. Impacto esperado (rangos, con supuestos)

Supuestos explícitos: 40–80 equipos por año, 3 partidos por gira, 22 jugadores por equipo. Ninguno de estos números está validado con IGS.

| Palanca | Supuesto | Rango anual |
|---|---|---|
| Performance Pack | 25–50% de los equipos lo compran a US$ 500–1.000 | US$ 5.000–40.000 |
| Recruiting Reel | 15–35% de los jugadores de equipos college y club competitivos a US$ 49–99 | US$ 6.500–61.000 |
| Horas de staff ahorradas en reportes | Hoy 3–6 h por partido (hipótesis); con IA 1–2 h de revisión | 250–1.000 h por año |
| Consultas por referidos y redes | 2–5% más de consultas atribuidas a reels compartidos | A medir en el piloto |

El valor menos medible y probablemente mayor es **diferenciación**: "tu equipo vuelve con video profesional, scouting de cada rival y reels de recruiting" es un argumento de venta frente a otros operadores de giras.

## 9. Esfuerzo (sobre IGS OS)

| Pieza | Esfuerzo | Notas |
|---|---|---|
| Scouting brief (RAG + flow + aprobación + PDF/portal) | **S** | Casi todo existe; es un flow nuevo y una plantilla |
| Extensión del flow post-match-report + ingesta de video (subida, almacenamiento GCS, transcodificación) | **M** | Temporal ya orquesta la ingesta; falta el pipeline de video |
| Integración con Veo/Trace (importar video y eventos) | **M** | Depende de las APIs del partner y del contrato |
| Detección de momentos propia para video de teléfono/drone | **L** | Modelo de visión + tuning; arrancar con heurísticas y revisión humana |
| Portal del coach (pestaña Performance) | **M** | Sobre el portal de la gira ya diseñado |
| Reels (montaje automático + plantillas de marca) | **M** | ffmpeg + plantillas; música con licencia |
| Consentimientos (padres/tutores, club, marketing) y gestión de derechos | **M** | Obligatorio **antes** de cualquier video de menores |

## 10. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| **Imágenes de menores** (U13–U19): COPPA en EE.UU., Ley 25.326 en Argentina, LGPD en Brasil | Consentimiento firmado del padre o tutor y del club **antes** de filmar; consentimientos separados para recruiting y para marketing; por defecto sin publicación y con desenfoque de caras en material de marca; retención limitada; revisión legal antes del piloto |
| **Derechos de imagen de la sede y del rival** (academias de clubes profesionales) | Acuerdo con cada sede y rival para filmar y usar el material; cláusula estándar en el contrato con proveedores; sin logos de clubes profesionales en reels de marca sin permiso |
| **Precisión de la IA** (clips mal asignados, momentos perdidos) | Revisión humana obligatoria antes de entregar; etiquetado de dorsales por el staff; el coach puede corregir |
| **Scouting con datos de jugadores rivales menores** | Solo información de equipo y fuentes públicas; nada de perfiles individuales de menores rivales |
| **Reglas de recruiting NCAA** (contacto, beneficios) | El reel es del jugador y su familia; IGS no contacta coaches universitarios en nombre del jugador; validar con un asesor de compliance de college |
| **Dependencia de un partner de cámaras** | Exportación en formatos estándar; captura por teléfono/drone como alternativa |
| **Costo de hardware y operación en el viaje** | Arrancar en 1–2 sedes recurrentes de Buenos Aires; cámara del partner por alquiler o comodato antes de comprar |
| **Canibalizar lo que ya se promete** | La base mejora lo actual sin costo extra; lo que se cobra son clips por jugador y reels |

## 11. Piloto propuesto

- **Alcance**: 3–5 giras de Buenos Aires (fútbol, college y club competitivo), 1–2 sedes recurrentes.
- **Fase 0 (antes de viajar)**: consentimientos (padres/tutores, club, sedes), cotización y alquiler de cámara Veo o Trace, scouting brief de cada rival generado y aprobado por el staff.
- **Fase 1 (en la gira)**: filmación de cada partido; highlights y reporte post-partido en < 48 h por el flow; pestaña Performance en el portal del coach.
- **Fase 2 (cierre)**: oferta de Performance Pack y Recruiting Reel; encuesta al coach; un reel de marca por gira (solo con consentimiento de marketing).
- **Criterios de éxito**: ≥ 80% de partidos con highlights en < 24 h; satisfacción del coach ≥ 4/5; ≥ 25% de equipos compran el add-on o ≥ 15% de jugadores compran el reel; 0 incidentes de privacidad.
- **Decisión después del piloto**: escalar a todas las giras de fútbol, sumar Brasil y el Mundial 2027, y decidir build vs. partner para la detección de momentos con datos reales de costo y precisión.

## 12. Preguntas para validar con IGS

1. ¿Cómo producen hoy el scouting, el análisis post-partido y el review de video? ¿Quién lo hace y cuánto tiempo lleva?
2. ¿Ya filman los partidos? ¿Con qué equipo y qué hacen con el video después?
3. ¿Cuántos jugadores o coaches piden material para recruiting? ¿Alguna vez lo cobraron?
4. ¿Qué consentimientos de imagen firman hoy las familias y los clubes?
5. ¿Tienen acuerdos de filmación con las academias y sedes de Buenos Aires?

## Fuentes

- Infinity Global Sports, home y `/college-soccer-tours` (relevados 2026-10-22).
- [Veo — sports video camera systems compared](https://www.veo.com/article/sports-video-camera-systems-compared) (comparativa del propio Veo; tomar sus rankings como visión de vendedor).
- [Veo — soccer camera systems compared](https://www.veo.com/en-us/article/soccer-camera-systems-compared).
- [Folio3 — Veo alternatives](https://www.folio3.ai/blog/veo-alternatives).
- [TechBloat — XBotGo Falcon alternatives for youth sports](https://www.techbloat.com/best-xbotgo-falcon-alternatives-for-recording-youth-sports.html).
- [CB Insights — Pixellot alternatives](https://www.cbinsights.com/company/pixellot/alternatives-competitors).
