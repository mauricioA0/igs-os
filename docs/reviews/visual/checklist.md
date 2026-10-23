# Visual comparison — checklist

Generated 2026-10-23T03:33:22.558Z by `scripts/visual/compare.mjs` against the contract in
`docs/design/igs-site-style.md`. Severity 5 = broken, 1 = polish. Sheets: site left, IGS OS right.

## `/` — desktop

Shot: `landing.desktop.png` · sheet: `sheet-landing.desktop.png` · owner: `apps/web/src/app/(site)/page.tsx`

h1: "The operating systemfor Infinity Global Sports." — "Barlow Condensed" 800 115.2px/92.16px, tracking -2.88px, uppercase

- [x] **render**
- [x] **font**
- [x] **size**
- [x] **tracking**
- [x] **color**
- [x] **spacing**
- [ ] **nav**: 10/14 nav items not Montserrat pills (e.g. "Ops panel→Today, trips, leads and Account 360." r=0px, Montserrat) (sev 3)
- [ ] **buttons**: 6 filled buttons not pills (e.g. "01Today, for the ops teamEverything that needs a person, ran" r=8px) (sev 3)

## `/design` — desktop

Shot: `design.desktop.png` · sheet: `sheet-design.desktop.png` · owner: `apps/web/src/app/(site)/design/page.tsx`

h1: "IGS OS,site-matched." — "Barlow Condensed" 900 115.2px/92.16px, tracking -2.88px, uppercase

- [x] **render**
- [ ] **font**: 4 text blocks not in Montserrat (e.g. "Design system" in "DM Sans") (sev 3)
- [x] **size**
- [x] **tracking**
- [ ] **color**: off-palette surfaces: lab(11.6638 24.1258 13.9309)×10, lab(12.1414 -1.97093 -19.8495)×9, lab(71.519 -39.936 23.7634)×6, lab(12.2902 -3.83221 -16.328)×4 (sev 2)
- [x] **spacing**
- [x] **nav**
- [x] **buttons**

## `/ops` — desktop

Shot: `ops-today.desktop.png` · sheet: `sheet-ops-today.desktop.png` · owner: `apps/web/src/features/today`

h1: "Hoy enOperación." — "Barlow Condensed" 900 115.2px/92.16px, tracking -2.88px, uppercase

- [x] **render**
- [ ] **font**: 7 text blocks not in Montserrat (e.g. "Viernes 23 de octubre" in "DM Sans") (sev 3)
- [x] **size**
- [x] **tracking**
- [ ] **color**: off-palette surfaces: lab(75.7437 35.0014 21.1298)×6, lab(76.435 22.5645 44.8159)×3, lab(67.4309 -8.57839 -26.6394)×2, lab(68.3392 48.9638 30.4235)×1 (sev 2)
- [x] **spacing**
- [x] **nav**
- [ ] **buttons**: 1 filled buttons not pills (e.g. "IGS-2715en 44 díasRiverside FC AcademyRio de Janeiro · 6 dic" r=8px) (sev 3)

## `/ops/trips` — desktop

Shot: `ops-trips.desktop.png` · sheet: `sheet-ops-trips.desktop.png` · owner: `apps/web/src/features/trips`

h1: "Giras" — "DM Sans" 400 48px/38.4px, tracking -2.88px, none

- [x] **render**
- [x] **font**
- [x] **size**
- [x] **tracking**
- [ ] **color**: off-palette surfaces: lab(67.4309 -8.57839 -26.6394)×10, lab(55.4741 -45.4549 30.1606)×2, lab(34.6355 11.3617 -52.825)×2, lab(68.3392 48.9638 30.4235)×1 (sev 2)
- [x] **spacing**
- [x] **nav**
- [x] **buttons**

## `/ops/trips/c0b16481-9260-5765-8dd1-788c7b2a63ab` — desktop

Shot: `ops-trip.desktop.png` · sheet: `sheet-ops-trip.desktop.png` · owner: `apps/web/src/features/trips`

h1: "Lakeshore University" — "Barlow Condensed" 800 60px/48px, tracking -1.5px, uppercase

- [x] **render**
- [ ] **font**: h2 "Estado" in Montserrat (sev 2)
- [x] **size**
- [x] **tracking**
- [ ] **color**: off-palette surfaces: lab(76.435 22.5645 44.8159)×10, lab(68.3392 48.9638 30.4235)×1, lab(67.4309 -8.57839 -26.6394)×1 (sev 2)
- [x] **spacing**
- [ ] **nav**: 8/14 nav items not Montserrat pills (e.g. "D1Domingo 7 de marzo2 ítems, 2 sin confirmar" r=4px, Montserrat) (sev 3)
- [ ] **buttons**: 10 filled buttons not pills (e.g. "D1Domingo 7 de marzo2 ítems, 2 sin confirmar" r=4px) (sev 3)

## `/ops/accounts` — desktop

Shot: `ops-accounts.desktop.png` · sheet: `sheet-ops-accounts.desktop.png` · owner: `apps/web/src/features/accounts`

h1: "Cada cliente, con la fuente." — "Barlow Condensed" 800 60px/48px, tracking -1.5px, uppercase

- [x] **render**
- [x] **font**
- [x] **size**
- [x] **tracking**
- [ ] **color**: off-palette surfaces: lab(78.2483 -33.918 20.0899)×4, lab(76.435 22.5645 44.8159)×3, lab(75.7437 35.0014 21.1298)×2, lab(68.3392 48.9638 30.4235)×1 (sev 2)
- [x] **spacing**
- [x] **nav**
- [ ] **buttons**: 6 filled buttons not pills (e.g. "Universidad · USAEn riesgoLakeshore UniversityPort Huron, Mi" r=8px) (sev 3)

## `/ops/accounts/17e97bd0-4cd1-52f0-b0bb-4bb8a22d91c8` — desktop

Shot: `ops-account.desktop.png` · sheet: `sheet-ops-account.desktop.png` · owner: `apps/web/src/features/accounts`

h1: "Lakeshore University" — "Barlow Condensed" 800 60px/48px, tracking -1.5px, uppercase

- [x] **render**
- [ ] **font**: h2 "Resumen" in Montserrat (sev 2); 7 text blocks not in Montserrat (e.g. "Universidad · USA" in "DM Sans") (sev 3)
- [x] **size**
- [x] **tracking**
- [ ] **color**: off-palette surfaces: lab(68.3392 48.9638 30.4235)×1 (sev 2)
- [x] **spacing**
- [x] **nav**
- [ ] **buttons**: 5 buttons not in Montserrat (e.g. "1 Email · 17 oct · Marcus Feld") (sev 2)

## `/ops/approvals` — desktop

Shot: `ops-approvals.desktop.png` · sheet: `sheet-ops-approvals.desktop.png` · owner: `apps/web/src/features/approvals`

h1: "Bandeja de aprobaciones" — "Barlow Condensed" 800 60px/48px, tracking -1.5px, uppercase

- [x] **render**
- [ ] **font**: 6 text blocks not in Montserrat (e.g. "Operaciones" in "DM Sans") (sev 3)
- [x] **size**
- [x] **tracking**
- [x] **color**
- [x] **spacing**
- [x] **nav**
- [ ] **buttons**: 4 filled buttons not pills (e.g. "Cambio internovence en 32 h 27 minMover el partido de mañana" r=8px) (sev 3)

## `/ops/leads` — desktop

Shot: `ops-leads.desktop.png` · sheet: `sheet-ops-leads.desktop.png` · owner: `apps/web/src/features/leads`

h1: "Leads" — "Barlow Condensed" 800 48px/48px, tracking -0.72px, uppercase

- [x] **render**
- [ ] **font**: 8 text blocks not in Montserrat (e.g. "US$ 490.240" in "Barlow Condensed") (sev 3)
- [ ] **size**: h1 line-height 48px at 48px (site 0.8) (sev 2)
- [x] **tracking**
- [ ] **color**: off-palette surfaces: lab(67.4309 -8.57839 -26.6394)×9, lab(34.6355 11.3617 -52.825)×2, lab(68.3392 48.9638 30.4235)×1 (sev 2)
- [x] **spacing**
- [x] **nav**
- [x] **buttons**

## `/ops/flows` — desktop

Shot: `ops-flows.desktop.png` · sheet: `sheet-ops-flows.desktop.png` · owner: `apps/web/src/features/flows`

h1: "Flows queoperan solos." — "Barlow Condensed" 900 115.2px/92.16px, tracking -2.88px, uppercase

- [x] **render**
- [ ] **font**: 4 text blocks not in Montserrat (e.g. "Automatizaciones · conversaciones" in "DM Sans") (sev 3)
- [x] **size**
- [x] **tracking**
- [ ] **color**: off-palette surfaces: lab(76.435 22.5645 44.8159)×2, lab(68.3392 48.9638 30.4235)×1 (sev 2)
- [x] **spacing**
- [x] **nav**
- [x] **buttons**

## `/ops/flows/inbound-inquiry` — desktop

Shot: `ops-flow.desktop.png` · sheet: `sheet-ops-flow.desktop.png` · owner: `apps/web/src/features/flows`

h1: "Consulta entrante de un coach" — "DM Sans" 400 20px/25px, tracking -0.5px, none

- [x] **render**
- [ ] **font**: 4 text blocks not in Montserrat (e.g. "Saludo" in "DM Sans") (sev 3)
- [x] **size**
- [ ] **tracking**: h1 tracking -0.5px (site DM Sans −0.06em) (sev 2)
- [ ] **color**: off-palette surfaces: lab(68.3392 48.9638 30.4235)×1, lab(76.435 22.5645 44.8159)×1 (sev 2)
- [x] **spacing**
- [x] **nav**
- [ ] **buttons**: 9 filled buttons not pills (e.g. "Agente" r=8px) (sev 3)

## `/ops/flows/inbound-inquiry/executions/57c5d89c-7923-572a-beec-09b92e5e1f29` — desktop

Shot: `ops-execution.desktop.png` · sheet: `sheet-ops-execution.desktop.png` · owner: `apps/web/src/features/flows`

h1: "Ejecución 57c5d89c" — "Barlow Condensed" 800 60px/48px, tracking -1.5px, uppercase

- [x] **render**
- [x] **font**
- [x] **size**
- [x] **tracking**
- [ ] **color**: off-palette surfaces: lab(96.2986 0.51412 2.21729)×36, lab(100 0 0)×17, lab(91.3106 0.514567 2.21761)×17, lab(85.8585 0.515193 2.218)×9 (sev 2)
- [x] **spacing**
- [x] **nav**
- [ ] **buttons**: 3 filled buttons not pills (e.g. "" r=0px) (sev 3)

## `/chat` — desktop

Shot: `chat.desktop.png` · sheet: `sheet-chat.desktop.png` · owner: `apps/web/src/features/coach`

h1: "Your team.Our pitch." — "Barlow Condensed" 800 115.2px/92.16px, tracking -2.88px, uppercase

- [x] **render**
- [ ] **font**: 6 text blocks not in Montserrat (e.g. "Plan a tour" in "DM Sans") (sev 3)
- [x] **size**
- [x] **tracking**
- [ ] **color**: off-palette surfaces: lab(78.2483 -33.918 20.0899)×1 (sev 2)
- [x] **spacing**
- [x] **nav**
- [x] **buttons**

## `/proposal/c0b16481-9260-5765-8dd1-788c7b2a63ab` — desktop

Shot: `proposal.desktop.png` · sheet: `sheet-proposal.desktop.png` · owner: `apps/web/src/features/coach/proposal`

h1: "10 days inBuenos Aires." — "Barlow Condensed" 800 115.2px/92.16px, tracking -2.88px, uppercase

- [x] **render**
- [ ] **font**: 11 text blocks not in Montserrat (e.g. "Tour proposal · T-2711" in "DM Sans") (sev 3)
- [x] **size**
- [x] **tracking**
- [x] **color**
- [x] **spacing**
- [ ] **nav**: 9/13 nav items not Montserrat pills (e.g. "College soccer tours" r=0px, Montserrat) (sev 3)
- [x] **buttons**

## `/` — mobile

Shot: `landing.mobile.png` · sheet: `sheet-landing.mobile.png` · owner: `apps/web/src/app/(site)/page.tsx`

h1: "The operating systemfor Infinity Global Sports." — "Barlow Condensed" 800 48px/38.4px, tracking -1.2px, uppercase

- [x] **render**
- [x] **font**
- [x] **size**
- [x] **tracking**
- [x] **color**
- [x] **spacing**
- [ ] **nav**: 14/14 nav items not Montserrat pills (e.g. "Ops panel→Today, trips, leads and Account 360." r=0px, Montserrat) (sev 3)
- [ ] **buttons**: 6 filled buttons not pills (e.g. "01Today, for the ops teamEverything that needs a person, ran" r=8px) (sev 3)

## `/design` — mobile

Shot: `design.mobile.png` · sheet: `sheet-design.mobile.png` · owner: `apps/web/src/app/(site)/design/page.tsx`

h1: "IGS OS,site-matched." — "Barlow Condensed" 900 48px/38.4px, tracking -1.2px, uppercase

- [x] **render**
- [ ] **font**: 4 text blocks not in Montserrat (e.g. "Design system" in "DM Sans") (sev 3)
- [x] **size**
- [x] **tracking**
- [ ] **color**: off-palette surfaces: lab(11.6638 24.1258 13.9309)×10, lab(12.1414 -1.97093 -19.8495)×9, lab(71.519 -39.936 23.7634)×6, lab(12.2902 -3.83221 -16.328)×4 (sev 2)
- [x] **spacing**
- [ ] **nav**: 4/14 nav items not Montserrat pills (e.g. "Today" r=0px, Montserrat) (sev 3)
- [x] **buttons**

## `/ops` — mobile

Shot: `ops-today.mobile.png` · sheet: `sheet-ops-today.mobile.png` · owner: `apps/web/src/features/today`

h1: "Hoy enOperación." — "Barlow Condensed" 900 48px/38.4px, tracking -1.2px, uppercase

- [x] **render**
- [ ] **font**: 7 text blocks not in Montserrat (e.g. "Viernes 23 de octubre" in "DM Sans") (sev 3)
- [x] **size**
- [x] **tracking**
- [ ] **color**: off-palette surfaces: lab(75.7437 35.0014 21.1298)×6, lab(76.435 22.5645 44.8159)×3, lab(67.4309 -8.57839 -26.6394)×2, lab(78.2483 -33.918 20.0899)×1 (sev 2)
- [x] **spacing**
- [x] **nav**
- [ ] **buttons**: 1 filled buttons not pills (e.g. "IGS-2715en 44 díasRiverside FC AcademyRio de Janeiro · 6 dic" r=8px) (sev 3)

## `/ops/trips` — mobile

Shot: `ops-trips.mobile.png` · sheet: `sheet-ops-trips.mobile.png` · owner: `apps/web/src/features/trips`

h1: "Giras" — "DM Sans" 400 32px/25.6px, tracking -1.92px, none

- [x] **render**
- [x] **font**
- [x] **size**
- [x] **tracking**
- [ ] **color**: off-palette surfaces: lab(67.4309 -8.57839 -26.6394)×10, lab(55.4741 -45.4549 30.1606)×2, lab(34.6355 11.3617 -52.825)×2, lab(78.2483 -33.918 20.0899)×1 (sev 2)
- [x] **spacing**
- [x] **nav**
- [x] **buttons**

## `/ops/trips/c0b16481-9260-5765-8dd1-788c7b2a63ab` — mobile

Shot: `ops-trip.mobile.png` · sheet: `sheet-ops-trip.mobile.png` · owner: `apps/web/src/features/trips`

h1: "Lakeshore University" — "Barlow Condensed" 800 40px/32px, tracking -1px, uppercase

- [x] **render**
- [ ] **font**: h2 "Estado" in Montserrat (sev 2)
- [x] **size**
- [x] **tracking**
- [ ] **color**: off-palette surfaces: lab(76.435 22.5645 44.8159)×10, lab(67.4309 -8.57839 -26.6394)×1, lab(68.3392 48.9638 30.4235)×1 (sev 2)
- [ ] **spacing**: horizontal scroll at this width (section "La TiraD1Domingo 7 de marzo2 í" right=798 .space-y-6; aside "EstadoGiraPropuestaPrecio p/pU" right=798 .space-y-4) (sev 4)
- [ ] **nav**: 10/14 nav items not Montserrat pills (e.g. "D1Domingo 7 de marzo2 ítems, 2 sin confirmar" r=4px, Montserrat) (sev 3)
- [ ] **buttons**: 10 filled buttons not pills (e.g. "D1Domingo 7 de marzo2 ítems, 2 sin confirmar" r=4px) (sev 3)

## `/ops/accounts` — mobile

Shot: `ops-accounts.mobile.png` · sheet: `sheet-ops-accounts.mobile.png` · owner: `apps/web/src/features/accounts`

h1: "Cada cliente, con la fuente." — "Barlow Condensed" 800 40px/32px, tracking -1px, uppercase

- [x] **render**
- [x] **font**
- [x] **size**
- [x] **tracking**
- [ ] **color**: off-palette surfaces: lab(78.2483 -33.918 20.0899)×4, lab(76.435 22.5645 44.8159)×3, lab(75.7437 35.0014 21.1298)×2 (sev 2)
- [x] **spacing**
- [x] **nav**
- [ ] **buttons**: 6 filled buttons not pills (e.g. "Universidad · USAEn riesgoLakeshore UniversityPort Huron, Mi" r=8px) (sev 3)

## `/ops/accounts/17e97bd0-4cd1-52f0-b0bb-4bb8a22d91c8` — mobile

Shot: `ops-account.mobile.png` · sheet: `sheet-ops-account.mobile.png` · owner: `apps/web/src/features/accounts`

h1: "Lakeshore University" — "Barlow Condensed" 800 40px/32px, tracking -1px, uppercase

- [x] **render**
- [ ] **font**: h2 "Resumen" in Montserrat (sev 2); 7 text blocks not in Montserrat (e.g. "Universidad · USA" in "DM Sans") (sev 3)
- [x] **size**
- [x] **tracking**
- [ ] **color**: off-palette surfaces: lab(75.7437 35.0014 21.1298)×1 (sev 2)
- [x] **spacing**
- [x] **nav**
- [ ] **buttons**: 5 buttons not in Montserrat (e.g. "1 Email · 17 oct · Marcus Feld") (sev 2)

## `/ops/approvals` — mobile

Shot: `ops-approvals.mobile.png` · sheet: `sheet-ops-approvals.mobile.png` · owner: `apps/web/src/features/approvals`

h1: "Bandeja de aprobaciones" — "Barlow Condensed" 800 40px/32px, tracking -1px, uppercase

- [x] **render**
- [ ] **font**: 6 text blocks not in Montserrat (e.g. "Operaciones" in "DM Sans") (sev 3)
- [x] **size**
- [x] **tracking**
- [x] **color**
- [x] **spacing**
- [x] **nav**
- [ ] **buttons**: 4 filled buttons not pills (e.g. "Cambio internovence en 32 h 26 minMover el partido de mañana" r=8px) (sev 3)

## `/ops/leads` — mobile

Shot: `ops-leads.mobile.png` · sheet: `sheet-ops-leads.mobile.png` · owner: `apps/web/src/features/leads`

h1: "Leads" — "Barlow Condensed" 800 36px/40px, tracking -0.54px, uppercase

- [x] **render**
- [ ] **font**: 8 text blocks not in Montserrat (e.g. "US$ 490.240" in "Barlow Condensed") (sev 3)
- [ ] **size**: h1 line-height 40px at 36px (site 0.8) (sev 2)
- [x] **tracking**
- [ ] **color**: off-palette surfaces: lab(67.4309 -8.57839 -26.6394)×9, lab(34.6355 11.3617 -52.825)×2, lab(55.4741 -45.4549 30.1606)×1, lab(68.3392 48.9638 30.4235)×1 (sev 2)
- [ ] **spacing**: horizontal scroll at this width (div "Nuevo2US$ 164.600Maple Grove C" right=1176 .grid.min-w-6xl.grid-cols-5.gap-4) (sev 4)
- [x] **nav**
- [x] **buttons**

## `/ops/flows` — mobile

Shot: `ops-flows.mobile.png` · sheet: `sheet-ops-flows.mobile.png` · owner: `apps/web/src/features/flows`

h1: "Flows queoperan solos." — "Barlow Condensed" 900 48px/38.4px, tracking -1.2px, uppercase

- [x] **render**
- [ ] **font**: 4 text blocks not in Montserrat (e.g. "Automatizaciones · conversaciones" in "DM Sans") (sev 3)
- [x] **size**
- [x] **tracking**
- [ ] **color**: off-palette surfaces: lab(76.435 22.5645 44.8159)×2, lab(68.3392 48.9638 30.4235)×1 (sev 2)
- [x] **spacing**
- [x] **nav**
- [x] **buttons**

## `/ops/flows/inbound-inquiry` — mobile

Shot: `ops-flow.mobile.png` · sheet: `sheet-ops-flow.mobile.png` · owner: `apps/web/src/features/flows`

h1: "Consulta entrante de un coach" — "DM Sans" 400 20px/25px, tracking -0.5px, none

- [x] **render**
- [ ] **font**: 8 text blocks not in Montserrat (e.g. "Saludo" in "DM Sans") (sev 3)
- [x] **size**
- [ ] **tracking**: h1 tracking -0.5px (site DM Sans −0.06em) (sev 2)
- [ ] **color**: off-palette surfaces: lab(68.3392 48.9638 30.4235)×1 (sev 2)
- [x] **spacing**
- [x] **nav**
- [ ] **buttons**: 3 filled buttons not pills (e.g. "" r=0px) (sev 3)

## `/ops/flows/inbound-inquiry/executions/57c5d89c-7923-572a-beec-09b92e5e1f29` — mobile

Shot: `ops-execution.mobile.png` · sheet: `sheet-ops-execution.mobile.png` · owner: `apps/web/src/features/flows`

h1: "Ejecución 57c5d89c" — "Barlow Condensed" 800 40px/32px, tracking -1px, uppercase

- [x] **render**
- [x] **font**
- [x] **size**
- [x] **tracking**
- [ ] **color**: off-palette surfaces: lab(96.2986 0.51412 2.21729)×36, lab(100 0 0)×17, lab(91.3106 0.514567 2.21761)×17, lab(85.8585 0.515193 2.218)×9 (sev 2)
- [x] **spacing**
- [x] **nav**
- [ ] **buttons**: 3 filled buttons not pills (e.g. "" r=0px) (sev 3)

## `/chat` — mobile

Shot: `chat.mobile.png` · sheet: `sheet-chat.mobile.png` · owner: `apps/web/src/features/coach`

h1: "Plan your team's tour" — Montserrat 400 16px/24px, tracking normal, none

- [x] **render**
- [ ] **font**: h1 "Plan your team's tour" in Montserrat (site Barlow/Klein Condensed or DM Sans) (sev 4)
- [x] **size**
- [x] **tracking**
- [ ] **color**: off-palette surfaces: lab(78.2483 -33.918 20.0899)×1 (sev 2)
- [x] **spacing**
- [x] **nav**
- [x] **buttons**

## `/proposal/c0b16481-9260-5765-8dd1-788c7b2a63ab` — mobile

Shot: `proposal.mobile.png` · sheet: `sheet-proposal.mobile.png` · owner: `apps/web/src/features/coach/proposal`

h1: "10 days inBuenos Aires." — "Barlow Condensed" 800 48px/38.4px, tracking -1.2px, uppercase

- [x] **render**
- [ ] **font**: 11 text blocks not in Montserrat (e.g. "Tour proposal · T-2711" in "DM Sans") (sev 3)
- [x] **size**
- [x] **tracking**
- [x] **color**
- [ ] **spacing**: horizontal scroll at this width (div "Per person$2,890All-inclusive " right=413 .proposal-card.stadium-art.relative.overflow-hidden.rounded-lg.border; div "01ReserveTell us you're in. No" right=413 .no-print.space-y-4; div "Train. Compete. Experience.Arg" right=4233 .marquee-track) (sev 4)
- [ ] **nav**: 9/9 nav items not Montserrat pills (e.g. "College soccer tours" r=0px, Montserrat) (sev 3)
- [x] **buttons**
