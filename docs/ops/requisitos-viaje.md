# Requisitos de viaje por destino (pasajeros con pasaporte de EE. UU.)

Verificado el **2026-10-23**. Es la base de las reglas que usa el chequeo de pre-salida
(`packages/py-common/src/igs_common/readiness/rules/2026-10.yaml`). No es asesoramiento legal:
las reglas cambian, y cada fila dice de dónde sale y qué tan firme es. Revisarlo **cada trimestre**
y antes de cada temporada alta (spring break, verano boreal, Mundial 2027).

Nivel de confianza de cada fuente:

- **Oficial**: página de un gobierno (cancillería, consulado, migraciones, UE).
- **Secundaria**: prensa o guías comerciales que citan la norma; sirve para orientarse, no para
  decidir sola.

`travel.state.gov` y el portal VFS de Brasil bloquean la descarga automática (403). Hay que
abrirlos a mano antes de cada temporada; abajo están los enlaces.

## Lo importante en tres líneas

1. **Brasil exige e-Visa a ciudadanos de EE. UU. desde el 10/04/2025** (US$ 80,90, solo por
   brazil.vfsevisa.com). Para **menores** la e-Visa pide partida de nacimiento y una autorización
   firmada por **ambos padres** con copia de sus pasaportes. Es lo que más tiempo lleva, así que el
   chequeo lo pide **60 días antes** de la salida.
2. **España (Schengen)**: el pasaporte tiene que vencer **al menos 3 meses después de salir** del
   espacio Schengen y haber sido **emitido hace menos de 10 años**. La regla de los 10 años es la que
   más se olvida y te deja afuera en el embarque. ETIAS **todavía no funciona** (sin fecha). EES
   (huellas y foto en frontera) **funciona desde el 10/04/2026**.
3. **Menores sin sus padres**:
   - En **Argentina**, un menor de **13 años** que no llega con quien ejerce la responsabilidad
     parental, o que no lo espera nadie autorizado, necesita **autorización de ingreso**.
   - En **Brasil**, la ley no exige claramente autorización a menores extranjeros, pero la Policía
     Federal **ha demorado** a menores sin el permiso de los dos padres.
   - Regla de IGS: **todo menor viaja con un consentimiento de ambos padres, certificado ante
     notario, que nombra al coach o al tour leader como adulto responsable**.

## Por destino

### Argentina

| Requisito | Detalle | Firmeza | Fuente |
|---|---|---|---|
| Visa | No necesita para turismo de hasta 90 días (prorrogable 90 más en Migraciones). | Secundaria (consenso) | [Consulado argentino en Miami](https://cmiam.cancilleria.gob.ar/en/visas), [World Travel Guide](https://www.worldtravelguide.net/guides/south-america/argentina/passport-visa) |
| Pasaporte | Vigente durante toda la estadía y en buen estado; con un pasaporte vencido o dañado pueden negar la entrada. No encontré una regla oficial de "6 meses" para turistas. | Secundaria | [Archivo travel.state.gov](https://webharvest.gov/peth04/20041108142734/http://travel.state.gov/travel/argentina.html) |
| Seguro de salud | El **DNU 366/2025** (B.O. 29/05/2025) obliga a todo extranjero a acreditar un seguro de salud y a presentar una declaración jurada del motivo del viaje. **No se sabe qué tan seguido lo controlan**: las fuentes dicen que la aplicación es gradual o que depende de la reglamentación. Lo tratamos como obligatorio. | Norma oficial, aplicación incierta | [Global Rescue](https://www.globalrescue.com/es/common/blog/detail/argentina-requires-travel-medical-insurance-guide/), [Chubb](https://www.chubb.com/cl-es/personas-y-familias/ideas/seguro-de-salud-para-viajar-a-argentina-obligatorio.html), [Radio Agricultura](https://www.radioagricultura.cl/tendencias/argentina-exigira-seguro-medico-obligatorio-a-turistas-como-afecta-a-los-chilenos_20250613/) |
| Menores < 13 | Cualquiera sea su nacionalidad: si no viajan acompañados ni los espera quien ejerce la responsabilidad parental o un **tercero autorizado**, necesitan autorización de ingreso. | Oficial (Migraciones, vía prensa) | [argentina.gob.ar](https://www.argentina.gob.ar/node/160885), [Canal 26 (2026)](https://www.canal26.com/general/2026/01/14/viajar-con-menores-al-exterior-que-documentacion-se-necesita-y-como-tramitarla/) |
| Menores 13–17 | La autorización de **salida** con escribano se exige a menores argentinos o residentes, no a turistas extranjeros. Igual, en el ingreso pueden pedir el permiso de los padres. | Secundaria | [BAL](https://www.bal.com/perspectives/bal-news/minors-required-to-have-travel-permit-birth-certificates), [Archivo travel.state.gov](https://webharvest.gov/peth04/20041108142734/http://travel.state.gov/travel/argentina.html) |
| Tasa de reciprocidad | No aplica: está suspendida desde 2016. | Secundaria | — |

### Brasil

| Requisito | Detalle | Firmeza | Fuente |
|---|---|---|---|
| **e-Visa** | Obligatoria para ciudadanos de EE. UU., Canadá y Australia **desde el 10/04/2025**. Arancel US$ 80,90. Se tramita solo en brazil.vfsevisa.com. Permite hasta 90 días de estadía por visita. La aprueban "en pocos días", pero si hay que sumar documentos puede tardar más: pedirla **con ~2 meses de anticipación**. Según la prensa, la aerolínea la controla al embarcar. | **Oficial** | [Consulado de Brasil en San Francisco (gov.br)](https://www.gov.br/mre/pt-br/consulado-sao-francisco/electronic-visitor-visa-e-visa), [Envoy Global](https://www.envoyglobal.com/news-alert/brazil-evisa-requirements-for-canada-u-s-and-australia/) |
| Papeles de la e-Visa | Pasaporte firmado y vigente durante todo el viaje, con **2 páginas libres** para la visa. Además: foto 2"×2", reserva de vuelo de ida y vuelta, y **extracto bancario de los últimos 30 días con al menos US$ 2.000**. | **Oficial** | [gov.br](https://www.gov.br/mre/pt-br/consulado-sao-francisco/electronic-visitor-visa-e-visa) |
| e-Visa de un **menor** | Partida de nacimiento original y una copia, autorización de viaje firmada por **ambos padres**, y copia del pasaporte o documento de cada padre. Si un padre es brasileño, también una *Declaração de Não-Cidadania*. | **Oficial** | [gov.br](https://www.gov.br/mre/pt-br/consulado-sao-francisco/electronic-visitor-visa-e-visa) |
| Menores sin sus padres (ingreso) | La ley brasileña **no exige claramente** autorización a menores que no son brasileños. Aun así, la Policía Federal **ha demorado** a menores sin permiso de ambos padres. Si el menor tiene **doble nacionalidad** (brasileña), sí la exige: **2 originales**, y si el padre que no viaja está en Brasil, en portugués y ante escribano brasileño (Res. CNJ 131/2011). | Oficial (Embajada de EE. UU. / CNJ) | [Embajada de EE. UU. en Brasil](https://br.usembassy.gov/minors-traveling/), [Advertencia del Depto. de Estado](https://travel.state.gov/en/international-travel/travel-advisories/brazil.html), [CNJ](https://www.cnj.jus.br/programas-e-acoes/viagem-ao-exterior/), [TJSC](https://www.tjsc.jus.br/web/infancia-e-juventude/autorizacao/viagem-internacional) |
| Riesgo legislativo | El Senado votó suspender la e-Visa; para que sea ley falta la Cámara de Diputados y la sanción presidencial. Al 2026-10-23 **no** fue aprobado. | Secundaria | [Manifold](https://manifold.markets/event/will-brazil-revoke-the-new-evisa-re) |

### Costa Rica

| Requisito | Detalle | Firmeza | Fuente |
|---|---|---|---|
| Visa | No necesita. La estadía la fija el oficial de migración al entrar: hasta 90 días según la mayoría de las fuentes, 180 según otra. | Secundaria | [Costa Rica Vibes (2026)](https://www.costaricavibes.com/costa-rica-entry-requirements/), [Costa Rica Experts](https://costaricaexperts.com/costa-rica-faqs/what-are-the-entry-requirements-for-costa-rica) |
| Pasaporte | Las fuentes no coinciden: vigente durante la estadía, o 6 meses recomendados. Usamos **vigente durante toda la estadía** como bloqueante y **6 meses** como recomendación. | Secundaria (conflicto) | [Friendly Planet](https://www.friendlyplanet.com/faqs/entry-requirements?tourId=650), [traveldocs](https://traveldocs.com/expedited-visa-services/costa-rica-visa-processing-country54) |
| Pasaje de salida | Hay que mostrar el pasaje para salir del país dentro de la estadía permitida. Como IGS emite el vuelo de vuelta, se controla a nivel gira. | Secundaria (consenso) | [FIU](https://www.ciara.fiu.edu/eco/travel_visa.htm) |
| Menores | El permiso de salida de Migración es para menores **costarricenses o residentes**. Para un menor turista extranjero que viaja con uno solo de sus padres o sin ellos, se **sugiere** una carta notarial del padre que no viaja. | Oficial (embajada, residentes) / secundaria (turistas) | [Embajada de Costa Rica](https://www.embajadadecostarica.org/wp-content/uploads/2025/02/Permiso-de-salida-de-menores-1-E2025.pdf), [Friendly Planet](https://www.friendlyplanet.com/faqs/entry-requirements?tourId=650) |

### España (Schengen)

| Requisito | Detalle | Firmeza | Fuente |
|---|---|---|---|
| Estadía | Hasta 90 días en cualquier período de 180, sin visa. Los días en otros países Schengen cuentan para el mismo límite. | **Oficial** | [Consulado de España en Washington](https://www.exteriores.gob.es/Consulados/washington/en/ServiciosConsulares/Paginas/Consular/Condiciones-de-entrada-en-Espana.aspx) |
| Pasaporte | Válido **hasta 3 meses después** de la salida de Schengen **y emitido hace menos de 10 años**. | **Oficial** | ídem |
| Medios económicos | En 2026: **€122 por persona y por día**, y **€1.099** como mínimo si la estadía es de 9 días o más. Sirven efectivo, tarjeta de crédito con extracto o libreta bancaria al día; **no** se aceptan cartas ni extractos online del banco. En una gira paga, la reserva del viaje organizado acredita el alojamiento. | **Oficial** | ídem |
| Pasaje de vuelta y alojamiento | Pasaje de vuelta "en todos los casos". El alojamiento se acredita con la reserva del viaje organizado. | **Oficial** | ídem |
| EES | Registro biométrico (foto y huellas) en la frontera exterior. Empezó el 12/10/2025 y funciona por completo desde el **10/04/2026**. Los datos quedan 3 años. Las primeras semanas hubo demoras grandes en los aeropuertos: el día de llegada hay que **sumar tiempo**. | **Oficial** (EEAS / Grecia / Dinamarca) | [EEAS](https://eeas.europa.eu/delegations/thailand/travelling-europe-new-entryexit-system_en), [MFA Grecia](https://www.mfa.gr/ireland/en/new-eu-digital-entryexit-system-takes-full-effect-on-the-10th-of-april-2026/), [EY](https://taxnews.ey.com/news/2026-0949-eus-entry-exit-system-fully-operational-as-of-10-april-2026) |
| ETIAS | **Todavía no funciona.** En julio de 2026 el portal sacó la meta "último trimestre de 2026"; la UE avisará la fecha con meses de anticipación, y la prensa habla de 2027. Cuando arranque: €20, válido 3 años, con 6 meses de transición. En las reglas queda **inactiva** (`effective_from: null`) y se activa poniendo la fecha. | Oficial (meta vieja) + secundaria (atraso) | [Gobierno de Países Bajos](https://government.nl/topics/holidays-and-travels/etias), [Navan (oct 2026)](https://navan.com/blog/when-does-etias-go-into-effect), [U. Michigan](https://procurement.umich.edu/etias-launch-delayed-until-late-2026/) |
| Menores | El consulado no pone reglas especiales a menores de EE. UU. La autorización de un padre la pide solo a menores ciudadanos de la UE o del EEE. | **Oficial** | [Consulado de España en Washington](https://www.exteriores.gob.es/Consulados/washington/en/ServiciosConsulares/Paginas/Consular/Condiciones-de-entrada-en-Espana.aspx) |

## Reglas propias de IGS (política del operador, no de los países)

Son más exigentes que la ley a propósito: lo que pesa es que nadie quede sin embarcar ni demorado
en la frontera.

| Regla | Por qué |
|---|---|
| **Seguro médico con cobertura de emergencia** para todos los pasajeros y todos los destinos | IGS ya lo promete en su sitio; en Argentina es obligatorio por el DNU 366/2025. |
| **Consentimiento de ambos padres certificado ante notario**, nombrando al adulto responsable de IGS o del club, para todo menor | Es la forma de cubrir Brasil, Argentina (< 13) y Costa Rica con un solo papel, y las aerolíneas lo piden seguido. |
| Para Brasil, copia de la **partida de nacimiento** de cada menor | Lo exige la e-Visa, y si hay dudas en frontera sirve para probar el vínculo. |
| Pasaporte válido **6 meses después del regreso** (recomendado; bloquea solo si el país exige más) | Muchas aerolíneas aplican la regla de los 6 meses aunque el país no la pida. |
| Contacto de emergencia y datos médicos (alergias, medicación) de cada pasajero | Los usa el tour leader 24/7. |

## Plazos con los que trabaja el chequeo

Se cuentan en días antes de la salida. Están en el YAML y se pueden ajustar.

| Ítem | Fecha límite | Supuesto |
|---|---|---|
| Renovar pasaporte | T−75 | Trámite rutinario en EE. UU.: 4–6 semanas, más margen para la e-Visa, que pide el pasaporte nuevo. |
| e-Visa de Brasil | T−60 | Pocos días si está todo bien; 2 meses si piden más papeles, sobre todo para menores. |
| Consentimiento de los padres ante notario | T−30 | Se firma recién con el roster cerrado. |
| Partida de nacimiento (Brasil) | T−60 | Hace falta para la e-Visa. |
| Seguro médico | T−14 | |
| Contacto de emergencia y datos médicos | T−21 | |

## Qué guarda IGS OS (y qué no)

- Por cada pasajero y requisito, solo el **estado**: `missing`, `requested`, `received`, `verified`
  o `not_applicable`. Se agregan fecha, nota y vencimiento cuando corresponde, por ejemplo la fecha
  de vencimiento de la e-Visa.
- **Nunca** se guardan imágenes ni escaneos de pasaportes, partidas o autorizaciones. Tampoco el
  número de pasaporte: alcanza con las fechas de emisión y de vencimiento para calcular las reglas.
  Si algún día hay que guardar documentos, va en un bucket aparte con CMEK, retención corta y acceso
  auditado, fuera de esta tabla.
- Los datos de menores se tratan como sensibles: solo se usan para las reglas (edad al salir, si
  viajan con sus padres) y no aparecen en mensajes al coach ni en texto que genere un modelo.
