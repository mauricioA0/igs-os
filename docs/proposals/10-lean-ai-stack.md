# Propuesta 10 — Stack lean de IA para IGS (¿hace falta un "Voiceflow propio"?)

> Respuesta corta: **no, no para empezar.** IGS necesita un agente bien acotado, unas pocas automatizaciones determinísticas, una bandeja de aprobaciones y buen RAG sobre su operación. El editor visual de flows y Temporal autogestionado en GKE son la respuesta correcta para una plataforma multi-cliente con mucho volumen, no para un operador de giras con un equipo chico. Todo lo que dice este documento sobre el volumen de IGS es **hipótesis**, hay que validarlo con IGS.

## 1. Qué necesita IGS de verdad vs. qué tiene IGS OS

Volumen probable (hipótesis, a partir de su sitio: programas universitarios y clubes de EE.UU., giras de 10–14 días, Mundial 2027): decenas de giras por año, cientos de consultas por año, un pico estacional (primavera boreal), un equipo de operaciones de pocas personas en Buenos Aires.

| Necesidad real | Lo que tiene IGS OS hoy | ¿Hace falta para v1? |
|---|---|---|
| Responder consultas rápido y calificarlas | Chat público + flow `inbound-inquiry` + agente | **Sí** — el agente, no el flow visual |
| Armar propuestas con rivales del nivel | Planner determinístico + propuesta editorial | **Sí** |
| Que nada salga sin que ops lo apruebe | Bandeja de aprobaciones con hash del contenido | **Sí** — es el corazón del producto |
| Perseguir proveedores antes de la gira | Flow `pre-departure-check` (Temporal, timers durables) | **Sí, pero alcanza un cron diario** |
| Saber cómo está cada cliente | Account 360 (reglas + RAG con citas) | **Sí** |
| Que ops pregunte "¿qué falta para X?" | Copiloto + MCP | **Sí** (copiloto); MCP es un plus |
| Diseñar automatizaciones visualmente | Editor de flows estilo Voiceflow/n8n | **No** — con 3–5 automatizaciones fijas, se escriben en código |
| Ejecución durable de meses, millones de eventos | Temporal en GKE, KEDA, 512 shards | **No** al volumen de IGS |
| Búsqueda vectorial a escala de miles de millones | Vertex Vector Search (adaptador) | **No** — pgvector sobra |
| Modelos propios en GPU | BGE-M3 en Cloud Run (CPU/GPU) | **Opcional** — embeddings por API cuestan centavos a este volumen |

Es el primer riesgo que marca cualquier revisión de negocio: Temporal autogestionado en GKE, dos bases y un camino de GPU son una respuesta enterprise para un operador chico.

## 2. La propuesta: IGS OS "lean v1"

```
Vercel (web: ops + coach)  ──►  Cloud Run: core API (FastAPI)
                                   ├─ 1 agente (OpenAI tool calling) con las tools de dominio
                                   ├─ bandeja de aprobaciones (igual que hoy)
                                   ├─ RAG: Postgres + pgvector (embeddings por API o BGE-M3 en CPU)
                                   └─ outbox → envíos por email / WhatsApp Business
                                Cloud Run Jobs + Cloud Scheduler: automatizaciones determinísticas
                                Cloud SQL Postgres (una instancia chica)
```

1. **Un solo agente bien acotado** (OpenAI tool calling, el `igs_common.llm` que ya existe). Tools: buscar rivales/experiencias, armar borrador de gira, consultar cliente, pedir aprobación. Nada externo se ejecuta sin aprobación (ya está resuelto con `ToolClass` + aprobaciones).
2. **Automatizaciones determinísticas en código**, no en un canvas:
   - `inquiry-intake`: consulta nueva → agente califica → borrador → aprobación → envío.
   - `pre-departure`: cron diario → ítems sin confirmar a 30/14/7 días → recordatorio al proveedor → alerta en "Hoy".
   - `payments`: cron diario → vencimientos de inscripción/cuotas/saldo (términos reales: US$95, US$500, saldo a 110 días) → recordatorio + estado de salud.
   - `post-match`: ítem completado → borrador de reporte → aprobación → envío al coach.
3. **Estado y espera en Postgres**: tabla de jobs con `run_at`, `attempts`, `idempotency_key` + `SELECT … FOR UPDATE SKIP LOCKED` (el patrón que ya usa el outbox). Las esperas largas ("30 días antes") son filas con fecha, no workflows vivos. Las aprobaciones ya viven en Postgres.
4. **RAG en pgvector** (ya es el store por defecto). Embeddings: `text-embedding-3-small` por API (US$0.02/MTok → centavos por año a este volumen) o BGE-M3 en CPU si se quiere independencia; sin GPU.
5. **Canales**: email (dominio de IGS) y WhatsApp Business, con estado de entrega. Es lo que más valor agrega después del agente y hoy falta.

**Lo que no se pierde**: el modelo de datos, RLS por tenant, Account 360, la bandeja, el copiloto, la propuesta, los evals, los e2e y la seguridad. Lo que cambia es *cómo se orquesta*, no *qué hace* el producto.

## 3. Cuándo sí conviene el motor de flows / Temporal

Volver a encenderlo (el código ya existe y está testeado) cuando se cumpla **alguno** de estos disparadores:

- Más de ~20 automatizaciones distintas, o ops quiere crearlas/cambiarlas **sin un desarrollador**.
- Flujos con muchos pasos humanos encadenados y reintentos complejos (p. ej. confirmación multi-proveedor con negociación) donde una tabla de jobs se vuelve frágil.
- Volumen sostenido de miles de ejecuciones/día o múltiples operadores (IGS OS vendido a otros tour operators).
- Conversaciones largas multi-turno con estado (no solo chat de calificación).

Y aun entonces, primero **Temporal Cloud** o Temporal sobre Cloud Run con una DB chica antes que GKE autogestionado.

## 4. Comparación de opciones (volumen IGS hipotético)

Supuestos: ~500 consultas/año, ~40 giras/año, 3–5 personas en ops. LLM con los precios verificados (gpt-6-luna US$0.10/US$0.50 por MTok, gpt-6.1-sol US$2/US$10).

| | **A. Lean custom (recomendada)** | **B. IGS OS completo (demo actual)** | **C. Comprar SaaS** (HubSpot + Zapier/n8n cloud + widget de chat con IA) |
|---|---|---|---|
| Costo fijo de infraestructura | **El más bajo**: Cloud Run que escala a cero, un Cloud SQL chico y jobs programados | El más alto: suma GKE, Temporal y el servicio de modelos; en prod, GPU y Vector Search siempre encendidos | Licencias por usuario del CRM + automatizaciones + widget; crece con el equipo |
| LLM/mes | ≈ $1–10 (calificación + borradores + copiloto) | igual | incluido o ≈ $20–100 en créditos IA del proveedor |
| Time-to-value | **2–4 semanas** sobre lo existente (recortar, no construir) | ya existe como demo; producción real requiere login, envíos reales, operación de GKE | 2–6 semanas de configuración, pero sin la lógica de IGS (rivales por nivel, términos de pago, propuesta) |
| Mantenimiento | Bajo: 1 servicio, 1 DB, jobs con cron. Lo opera 1 persona | Alto: GKE, Temporal (upgrades, esquema, shards), KEDA, 2 servicios de modelos | Bajo en infra; alto en "pegamento" (Zaps que se rompen en silencio) |
| Lock-in | Bajo: Postgres + Python + OpenAI vía interfaz propia (se cambia de proveedor) | Bajo, pero con mucha superficie propia | **Alto**: datos y procesos en el CRM; migrar es caro |
| Calidad de IA | Alta: agente con tools de dominio, aprobaciones, RAG con citas, evals | Igual | Media: chatbots genéricos, sin rivales por nivel ni propuesta propia; poca trazabilidad |
| Riesgo con datos de menores | Controlable (RLS, store separado, nada al LLM) | Igual | Depende del proveedor; difícil de auditar |

## 5. Recomendación

**Opción A.** Es el mismo producto que se ve en la demo, con la mitad de las piezas: una API, un Postgres, cron jobs y un agente. Tiene el costo fijo de infraestructura más bajo de las tres opciones más unos pocos dólares de LLM, lo puede operar una sola persona, y deja el motor de flows y Temporal "en el estante" con disparadores claros para encenderlos. Responde a ese riesgo: lo pueden pagar y mantener desde el día uno, y escala cuando IGS escale.

En la presentación conviene mostrar las dos cosas: la demo completa (prueba de que se puede llegar lejos) y este v1 lean como el plan real.

## 6. Migración desde la demo actual

**Se mantiene tal cual**: `services/core` (API, aprobaciones, Account 360, copiloto, MCP), `igs_common` (dominio, llm, rag con pgvector, seed), `apps/web`, evals, e2e, Terraform de red/Cloud SQL/Cloud Run/Secrets.

**Se apaga ahora para cortar costo** (orden sugerido):
1. **GKE Autopilot + Temporal + KEDA** → `kubectl delete` del namespace/helm release y `terraform` con el módulo `gke` deshabilitado. Es la mayor parte del costo fijo, en demo y en prod.
2. **Base de Temporal** (`temporal`, `temporal_visibility`) en Cloud SQL → drop.
3. **`services/models` en Cloud Run** → embeddings por API (`text-embedding-3-small`) detrás del mismo `Embedder`, o BGE-M3 en CPU solo si se quiere evitar dependencia. Reindexar con `python -m igs_common.ingest index-all`.
4. **Vertex Vector Search** → ya está apagado en demo (pgvector); no habilitarlo.

**Se reemplaza**:
- `FlowExecutionWorkflow` → `igs_common.jobs`: tabla `jobs` + dispatcher con `SKIP LOCKED` (reusar el patrón del `OutboxDispatcher`) y Cloud Scheduler que dispara un Cloud Run Job cada 5–15 min.
- Nodos `approval`/`wait` → la aprobación ya es una fila; al decidirla, el endpoint encola el siguiente paso (`job` con `run_at = now`). Las esperas son `run_at` futuros.
- Las 3 automatizaciones de ejemplo (`inbound-inquiry`, `pre-departure-check`, `post-match-report`) → 3–4 funciones Python con tests (los escenarios de flow existentes sirven como casos de prueba).
- Editor de flows → se oculta del menú de ops (feature flag `flows`); el código queda para cuando se cumpla un disparador del §3.

**Riesgos de la migración**: perder la durabilidad "gratis" de Temporal (mitigar con idempotency keys y reintentos con backoff en la tabla de jobs, ya probado en el outbox); el demo pierde el momento "el flow se reanuda en vivo" (mitigar mostrando el job encolado y ejecutado en la traza, o manteniendo la demo actual solo para la presentación y pausándola después con `scripts/deploy/demo-pause.sh`).
