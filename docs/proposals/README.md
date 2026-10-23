# Propuestas de negocio e IA para IGS

Diez propuestas para hacer crecer IGS y sumar IA a su sitio y su operación. Los rangos de impacto de cada documento son **hipótesis con supuestos explícitos**: hay que validarlos con IGS (volumen de leads, giras por año, ticket, margen). Ninguna necesita un builder tipo Voiceflow.

## Ranking

Criterio: impacto × urgencia ÷ esfuerzo, y cuánto reutiliza lo que IGS OS ya tiene.

| # | Propuesta | Por qué | Esfuerzo |
|---|---|---|---|
| 1 | [03 · Familias + Mundial Femenino 2027](03-families-world-cup-2027.md) | Ventana con fecha: sorteo el 11/12 y early bird solo antes. Concierge EN/ES/PT online antes del 15/11; upsell a eliminatorias | M |
| 2 | [05 · Contenido + SEO + AEO](05-ai-content-seo.md) | Las 27 URLs comparten título y la SPA se ve vacía para los bots de IA. Arreglar el render del lado del servidor es lo más barato y lo que más rinde | S → M |
| 3 | [01 · Concierge de IA en el sitio](01-ai-tour-concierge.md) | Reemplaza "te respondemos en 1 día hábil" por calificación + itinerario de muestra en minutos; la propuesta formal pasa por aprobación | M |
| 4 | [06 · Recompra + referidos + outbound](06-sales-automation-referrals.md) | El formulario ya pregunta Returning/Referral. Empezar por recompra y referidos (S); outbound en frío al final | S → M |
| 5 | [08 · Margen vivo + pricing](08-pricing-margin-forecasting.md) | Hoy no se guarda el costo real ni la moneda. Victoria rápida: 30 días con planilla + IA, sin construir nada | S → M |
| 6 | [09 · Portal de proveedores + red de rivales](09-partners-provider-network.md) | Confirmaciones por magic link + IA que lee respuestas (−40–70 % de tiempo persiguiendo). La red de rivales con rating es el foso competitivo | M → L |
| 7 | [02 · Armá tu gira (itinerario + precio)](02-instant-itinerary-builder.md) | Self-serve con precios de código, nunca del modelo. Necesita antes un catálogo de costos reales | M |
| 8 | [07 · Acompañante en gira (WhatsApp)](07-on-tour-companion.md) | Sube NPS y baja tiempos de incidentes; depende del conector WhatsApp Business y sus plantillas | L |
| 9 | [04 · IGS Performance (scouting + video)](04-ai-performance-analysis.md) | Ya lo prometen y no lo venden. Cámara de un partner (Veo/Trace), nosotros el resto. Riesgo fuerte: imágenes de menores | M → L |
| — | [10 · Stack liviano](10-lean-ai-stack.md) | No es un producto sino la forma de hacer todo lo anterior: un agente + automatizaciones + Postgres + aprobaciones; Temporal/GKE solo con disparadores claros | — |

## Secuencia sugerida

1. **Semanas 1–2:** SEO técnico (05) + planilla de margen (08) + reglas de recompra y referidos (06). Casi sin código.
2. **Semanas 2–4:** concierge del Mundial 2027 (03) sobre el mismo agente que después usa el sitio general (01).
3. **Mes 2:** portal de proveedores (09) y armá tu gira (02) con costos reales.
4. **Después:** acompañante por WhatsApp (07) e IGS Performance (04) como pilotos.

## Preguntas para validar con IGS

- ¿Cuántos leads por mes llegan hoy y qué parte termina en gira?
- ¿Qué porcentaje de giras viene de clientes que repiten o de referidos?
- ¿Dónde vive hoy el costo real por gira (planilla, contador, mails)?
- ¿Cuántas familias esperan para el Mundial 2027 y quién atiende "Text Jo"?
- ¿Qué permisos de imagen firman hoy las familias?
