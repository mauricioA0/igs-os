# 05 · Motor de contenido con IA y SEO

> Propuesta B5. Auditoría hecha el 2026-10-22 sobre https://infinityglobalsports.com (robots.txt, sitemap.xml, llms.txt y el HTML que entrega el servidor) más investigación pública de competidores. Las cifras de impacto son **rangos con supuestos explícitos**, no promesas.

## 1. Diagnóstico del sitio actual

| Aspecto | Qué hay hoy | Lectura |
|---|---|---|
| robots.txt | Permite Googlebot, Bingbot, Twitterbot, facebookexternalhit y `*`. Declara el sitemap. | Bien. |
| sitemap.xml | Tiene 27 URLs, todas en inglés. Incluye deporte × país (soccer/rugby/hockey/volleyball/basketball × Argentina/Brazil/Costa Rica/Spain), segmentos (college, youth club, private school), experiencias individuales y familiares, Superclásico, Infinity Cup y Brazil 2027 Women's. Un comentario anticipa una versión `/es/`. | La arquitectura de información ya es "programática" en espíritu: hay una página por deporte × destino y por segmento. |
| llms.txt | Existe y responde en `text/plain`. Resume la empresa y las páginas. | Es un adelanto poco común: ya piensan en los motores de respuesta. |
| Render | La home entrega unos 4,5 KB de HTML con TTFB de alrededor de 0,11 s. Es una SPA renderizada en el cliente: el contenido aparece recién con JavaScript. | **Es el problema número 1.** Google renderiza JS con demora. Los crawlers de los LLM (GPTBot, PerplexityBot, ClaudeBot) y las vistas previas sociales en general **no ejecutan JS**, así que ven una página vacía. |
| Títulos y meta | **Las 27 URLs comparten el mismo `<title>` y la misma `meta description`** ("Infinity Global Sports \| Elite International Sports Experiences"). | Google ve 27 páginas indistinguibles. No pueden posicionar por "college soccer tour Argentina" aunque esa página exista. |
| Canonical / JSON-LD | No aparecen en el HTML del servidor. | No hay `Organization`, `TouristTrip`, `FAQPage` ni `Event` (por ejemplo para el Superclásico o el Mundial 2027). |
| og:image | Alojada en `storage.googleapis.com/gpt-engineer-file-uploads`. | Indica un sitio hecho con Lovable. Funciona, pero es frágil y queda fuera de su dominio. |
| Blog / historias | No hay blog, ni historias de viajes, ni testimonios indexables en el sitemap (solo `/gallery`). | No tienen contenido "long-tail" ni prueba social que buscadores y LLMs puedan citar. |
| Formulario `/plan-a-tour` | Promete respuesta en "1 business day". No pide deporte, nivel, tamaño del grupo ni presupuesto. | Pierde la señal que serviría para segmentar el nurture (ver la propuesta B1). |
| Redes | No hay links sociales en el HTML del servidor; si existen, se renderizan por JS. | Para el knowledge graph de Google conviene que estén en `sameAs` del JSON-LD. |

**Voz de marca observada** (base de las guías de estilo): frases cortas e imperativas, tríadas ("Train. Compete. Experience.", "Real Sport. Real Environments.", "Built For Teams. Designed For Growth."), foco en el desarrollo del atleta y en la experiencia cultural auténtica, sin superlativos vacíos. Siempre en inglés para el público de EE. UU.

## 2. Competidores y cómo consiguen leads

| Competidor | Qué venden | Cómo capta leads (público y observable) |
|---|---|---|
| **Premier International Tours** | Giras de fútbol para college y clubes a más de 12 países, entre ellos Argentina y Brasil. Buenos Aires 9 días desde US$2.100 por persona (base 40 viajeros desde Miami). Elite Development Tour con Racing Club desde US$3.000. | Es **el que domina el SEO del nicho**. Tiene páginas por segmento (`/college-soccer-tours`), por país (`/argentina-soccer-tours`), **itinerarios de muestra** y **FAQs para college**, además de PDFs descargables con precio "desde". Recomienda reservar con 8 a 14 meses de anticipación, lo que marca el ciclo de nurture. Ofrece 1 viaje gratis cada 19 pagos. |
| **AIST** | Gira por Argentina personalizable (Buenos Aires + Rosario, 9 días y 6 noches) para college, high school y clubes de varios deportes. | Usa páginas de reserva en **WeTravel** (checkout y pago en cuotas incluidos) que funcionan como landing y como cierre. |
| **Pro Tours Soccer** | Inmersión de unos 10 días en Argentina con entrenamiento con técnicos profesionales y 5 a 7 partidos. Su fundador lo hace desde hace más de 15 años. | **Relación personal del fundador** y repetición con los mismos clubes. Aparece en directorios como SoccerWire. |
| **Inspire Sport Global** | Semana en Río: entrenamiento en las instalaciones de Fluminense, partido en el Maracaná y sesiones de playa. | También usa itinerarios en **WeTravel** como landing compartible. |
| **Clubes que van por su cuenta** (NCE, Beachside SC) | NCE: Río, 10 días, febrero 2027, solo por invitación, contra academias de Botafogo, Fluminense y Flamengo. Beachside: Argentina desde 2018, contra Boca, Estudiantes, Lanús y San Lorenzo. | Una **página propia del club con PDF de invitación**. Son a la vez competencia (desintermedian) y clientes potenciales. |
| **Clubes profesionales en EE. UU.** (Flamengo Soccer Camp, Botafogo Academy) | Camps en ciudades de EE. UU. con metodología brasileña, scouts y tryouts. | Compiten por la misma atención y el mismo presupuesto de las familias, apoyados en la marca del club. |

**Patrones que se repiten:**
1. Páginas por segmento y país con **itinerario de muestra y precio "desde"**. Es lo que Google premia para búsquedas como "argentina soccer tour".
2. **FAQs específicas de college**. Por ejemplo, la NCAA permite una gira al exterior cada 4 años por equipo, y eso define cuándo el coach busca.
3. **Prensa ganada en los sitios de athletics de las universidades.** Las notas tipo "Men's soccer heads to Argentina" en prestosports o clemsontigers.com son backlinks de dominios `.edu` y prueba social que hoy nadie captura de forma sistemática.
4. Checkout compartible (WeTravel) que los coaches reenvían a las familias.
5. Ninguno publica **historias de viaje sistemáticas ni datos verificables** (partidos jugados, rivales, resultados). **Ese hueco es la oportunidad de IGS.**

> No verifiqué el gasto en ads ni las redes de cada competidor. Lo de arriba sale solo de sus páginas públicas y de la cobertura en medios.

## 3. Propuesta: motor de contenido con IA

La idea central: **cada gira que IGS opera produce datos estructurados** en IGS OS (viaje, rivales, sedes, resultados, aprobaciones, mensajes del coach). El motor convierte esos datos en contenido con **revisión humana obligatoria**. Por eso no es contenido genérico de IA: es contenido que solo IGS puede escribir.

### 3.0 Fundación técnica (requisito de todo lo demás) · Esfuerzo **M**

- **SSR o prerender** de las rutas públicas (Next.js con SSG/ISR, o prerender en el edge si se quedan en Lovable). Sin esto, nada de lo siguiente lo leen los LLMs.
- `<title>`, `meta description`, `canonical` y `og:*` **únicos por URL**, generados desde una tabla de páginas.
- JSON-LD: `Organization` (con `sameAs` a las redes), `TouristTrip` con `itinerary` y `offers` "desde" por programa, `FAQPage` y `Event` (Superclásico, Mundial Femenino 2027).
- `hreflang` en/es cuando exista `/es/`, como ya anticipa el comentario del sitemap. Mantener llms.txt sincronizado y generado desde la misma tabla.
- og:image en su propio dominio o CDN.

### 3.1 Landings programáticas deporte × destino × nivel · Esfuerzo **M**

- Matriz: deporte (5) × destino (4) × segmento o nivel (NCAA D1, D2/D3/NAIA, club U14–U19, private school, femenino). Ejemplo: *"D1 Women's Soccer Tour to Buenos Aires"*.
- **Regla anti contenido pobre:** una página se publica solo si tiene al menos **3 datos propios**. Por ejemplo: itinerario real de muestra, rivales o academias con los que IGS realmente jugó, precio "desde" vigente, una historia o testimonio de ese segmento, y FAQs específicas (reglas NCAA de viaje al exterior, ventana de spring/summer). Si no se cumple, la combinación queda `noindex` o directamente no existe.
- Arranque prudente: **unas 20 a 30 páginas de alta intención**, no las 200 combinaciones posibles. Se agregan más solo cuando una página tiene datos.
- El LLM redacta con una **plantilla de marca** y los hechos vienen de la base, no del modelo. Cada afirmación lleva su fuente interna, igual que las citas de Account 360.

### 3.2 Historias de viaje generadas de cada gira (con consentimiento) · Esfuerzo **M**

- Al cerrar una gira, IGS OS arma un borrador de recap con: día a día, partidos, rivales, resultados, momentos y citas del coach, más fotos subidas por el equipo.
- **Consentimiento explícito** del programa (y de los padres cuando hay menores, ver Riesgos). Sin consentimiento no hay historia pública: queda como recap privado para el equipo, que igual tiene valor de retención.
- Salidas a partir de un mismo borrador: historia en el sitio, **un kit de prensa para el SID de la universidad** (para que publique su nota y nos enlace: el backlink `.edu` del patrón 3), un post para redes y un resumen para el email a familias.

### 3.3 Captura de testimonios en el portal del coach · Esfuerzo **S**

- Pedido automático de 7 a 14 días después de volver: 3 preguntas cortas, calificación, permiso de uso (nombre, cargo, programa, o anónimo) y un video opcional de 30 segundos.
- Con aprobación, el testimonio se convierte en `Review` en el JSON-LD y alimenta las landings del segmento.
- La IA solo **resume y extrae citas**. Nunca reescribe el sentido ni inventa testimonios. El texto final lo aprueba quien lo dijo.

### 3.4 Guiones de video corto · Esfuerzo **S**

- A partir de cada historia, 3 a 5 guiones de 15 a 45 segundos (gancho, momento, cierre con "Plan a tour") para Reels, TikTok y Shorts, con planos sugeridos de lo que el equipo efectivamente filmó.
- Formatos recurrentes: "Día 1 vs. Día 9", "Nuestro rival: academia de X", "Qué empacar para Buenos Aires en marzo".
- La edición la hace una persona. La IA ahorra la página en blanco, no reemplaza al editor.

### 3.5 Nurture por email según el calendario de college · Esfuerzo **M**

- Secuencias segmentadas por tipo de programa y ventana. Algunos hitos:
  - planificación de la gira de spring con 8 a 14 meses de anticipación;
  - aprobación de presupuesto en el otoño;
  - la regla NCAA de una gira cada 4 años: recordar al coach cuándo le vuelve a tocar;
  - el Mundial Femenino Brasil 2027 para programas femeninos y familias.
- Para que funcione, el formulario `/plan-a-tour` tiene que capturar deporte, nivel, tamaño y mes objetivo (se cruza con B1).
- Cada email usa contenido real (historias y testimonios del segmento). Se envía siempre desde una persona de IGS y el que se renueva cada ciclo es el contenido, no el remitente.
- Métrica norte: reuniones agendadas, no aperturas.

### 3.6 Optimización para motores de respuesta (ChatGPT, Perplexity, AI Overviews) · Esfuerzo **S** (sobre 3.0)

- Lo que más pesa: HTML legible sin JS (3.0), **datos citables** (precios "desde", duración, rivales y resultados con fecha), FAQs con respuestas cortas y directas, y menciones en terceros (notas de universidades, SoccerWire, medios locales).
- Mantener llms.txt con datos duros por programa. Permitir de forma explícita GPTBot, PerplexityBot, ClaudeBot y Google-Extended en robots.txt.
- **Monitoreo mensual:** un set fijo de alrededor de 30 preguntas ("best soccer tour operator for a college team to Argentina", "women's soccer trip Brazil 2027"…), consultado contra ChatGPT, Perplexity y Google. Se registra si IGS aparece y con qué fuente. Se automatiza como un flow de IGS OS.

## 4. Guardrails

1. **Ningún texto se publica sin aprobación humana.** Usa la misma bandeja de Aprobaciones de IGS OS, con diff y trazabilidad de fuente por párrafo.
2. **Los hechos salen de la base y no del modelo.** Si un dato no tiene fuente, el borrador lo marca y no se publica.
3. **Guía de voz de marca** extraída del sitio (tríadas, imperativo, frases cortas, sin hipérbole). Un evaluador automático puntúa cada borrador contra la guía y contra una lista de palabras prohibidas antes de que lo vea la persona que revisa.
4. **Consentimiento y privacidad:**
   - el consentimiento se registra por persona y por pieza;
   - los menores nunca aparecen con nombre completo;
   - las fotos de menores requieren el permiso de un padre;
   - se puede revocar y la pieza se despublica.
5. **Nada de reseñas o testimonios sintéticos.** Tampoco se usan nombres de rivales o academias sin confirmar que el partido existió.
6. **Volumen acotado:** cupo mensual de páginas nuevas. Cada página se revisa a los 90 días y la que no tiene tráfico se fusiona o pasa a `noindex`.

## 5. KPIs

| KPI | Línea base | Fuente |
|---|---|---|
| Páginas indexadas con título único | 0 de 27 hoy | Search Console |
| Clics orgánicos sin marca por mes | medir el primer mes | Search Console |
| Leads de `/plan-a-tour` atribuidos a orgánico o contenido | medir | Formulario + UTM |
| Tasa lead → reunión → reserva por canal | medir | IGS OS |
| Apariciones en el set de 30 preguntas a LLMs | medir el primer mes | Monitoreo 3.6 |
| Backlinks desde dominios `.edu` de athletics | medir | Kit de prensa 3.2 |
| % de giras cerradas con historia publicada y % con testimonio | 0 hoy | IGS OS |

## 6. Impacto esperado (rangos)

**Supuestos:**
- **Ciclo largo:** como se reserva con 8 a 14 meses de anticipación, el contenido de hoy rinde en reservas de la temporada siguiente.
- **Volumen operativo:** de 10 a 30 giras por año, con al menos la mitad aceptando publicar su historia.
- **Fundación primero:** 3.0 se hace antes que todo lo demás.
- **Sin pauta:** no hay gasto en ads.

| Horizonte | Rango | Por qué |
|---|---|---|
| 0–3 meses | La mayor parte del efecto sale de **3.0**: las 27 páginas existentes empiezan a posicionar por su tema; las vistas previas sociales y los LLMs ven contenido real. | Hoy compiten con un solo título repetido 27 veces. |
| 3–9 meses | **+30% a +100% de clics orgánicos sin marca** sobre la línea base, y aparición en una parte del set de preguntas a LLMs. | Las landings con datos, las historias y las FAQs cubren búsquedas long-tail que Premier hoy captura casi solo. |
| 9–18 meses | **+10% a +30% de leads calificados** atribuibles a contenido, y mejor conversión del nurture (más reuniones por lead). | Depende de cuántas historias y testimonios se publiquen y de que el formulario capture el segmento. |

Si la base actual es muy chica, los porcentajes engañan: la meta real es pasar de "invisible fuera de la marca" a "aparecer en las 3 a 5 búsquedas clave del nicho".

## 7. Esfuerzo resumido

| Iniciativa | Esfuerzo |
|---|---|
| 3.0 Fundación (SSR, meta, JSON-LD, hreflang) | M |
| 3.1 Landings programáticas | M |
| 3.2 Historias de viaje | M |
| 3.3 Testimonios en el portal del coach | S |
| 3.4 Guiones de video | S |
| 3.5 Nurture por calendario | M |
| 3.6 Motores de respuesta y monitoreo | S |

Orden sugerido: 3.0 → 3.3 → 3.2 → 3.1 → 3.6 → 3.5 → 3.4.

## 8. Riesgos

| Riesgo | Mitigación |
|---|---|
| **Penalidad por contenido pobre o "scaled content abuse"** (políticas de spam de Google) | Mínimo de 3 datos propios por página, cupo mensual, `noindex` por defecto, revisión humana y poda a los 90 días. |
| Hechos inventados por el modelo (rivales, resultados, precios) | Generación anclada a la base con fuente por párrafo. Lo que no tiene fuente no se publica. |
| Menores en fotos, nombres o videos | Consentimiento de padres registrado, sin nombres completos de menores y despublicación ante revocación. |
| Precios "desde" desactualizados | Se leen de la tabla de precios vigente (ver B8) con fecha visible. |
| Migrar fuera de la SPA rompe URLs | Se mantienen las 27 rutas idénticas, con redirecciones 301 si algo cambia y validación del sitemap. |
| Dependencia de un solo canal (Google) | Las mismas piezas alimentan email, redes y kits de prensa. Los LLMs son un canal más, no el único. |
| La voz de marca se diluye | Guía de estilo con evaluador automático y una persona de IGS dueña de la aprobación final. |

## Fuentes de la investigación de competidores

- [Premier International Tours — college soccer tours](https://premierinternationaltours.com/college-soccer-tours), [Argentina soccer tours](https://www.premierinternationaltours.com/argentina-soccer-tours), [FAQs para college](https://www.premierinternationaltours.com/college-tours-faqs)
- [AIST — gira por Argentina (WeTravel)](https://aist.wetravel.com/i/6a95b617333735a22f6d20e3)
- [Inspire Sport Global — Río (WeTravel)](https://inspiresportglobal.wetravel.com/i/69dfd67b683cb3a89526dd3f)
- [SoccerWire — international soccer tours](https://soccerwire.com/tryout-camp/international-soccer-tours-tournaments)
- [NCE — Brazil Soccer Tour](https://ncesoccer.com/international/brazil/) · [Beachside Abroad](https://beachsidesoccer.org/our-club/beachside-abroad/)
- [Flamengo Soccer Camp en EE. UU.](https://en.flamengo.com.br/noticias/institucional/flamengo-soccer-camp-amplia-fronteiras-e-chega-a-mais-cidades-nos-estados-unidos-em-2025) · [Botafogo Academy International](https://academy.botafogo.com.br/international)
- Notas de athletics como ejemplo del patrón de backlinks: [Clemson](https://clemsontigers.com/?p=210892), [College of Charleston](https://today.cofc.edu/2014/05/16/mens-soccer-heads-brazil-ahead-world-cup/), [Wabash (regla NCAA de 4 años)](https://www.wabash.edu/news/story/7196)
