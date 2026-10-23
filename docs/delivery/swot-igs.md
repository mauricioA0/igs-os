# SWOT — what IGS OS would solve for Infinity Global Sports

Short English version of [foda-igs.md](foda-igs.md). Facts come from infinityglobalsports.com (checked 2026-10-22); **anything about IGS's internal operation is an inferred hypothesis** to validate with the team.

## IGS today → IGS OS

| | Item (hypothesis) | IGS OS answer | Where in the repo |
|---|---|---|---|
| **Strength** | AFA and top-club access to level-matched opponents | Level-aware itinerary planner (±1 level, no back-to-back matches) | `igs_common/domain/planner.py` |
| **Strength** | Premium, emotional product | Editorial proposal with a clear path to reserve | `apps/web/src/app/(public)/proposal/` |
| **Strength** | Bilingual team in the US and Buenos Aires | Spanish ops panel, English coach surfaces, one data model | `(app)/` · `(public)/` |
| **Weakness** | Inquiries and proposals handled by hand | Agent qualifies the inquiry and drafts the proposal; ops approves before sending | `examples/inbound-inquiry.json`, `api/v1/public_chat.py` |
| **Weakness** | Provider confirmations chased over WhatsApp/email | Flow requests confirmations 30 days out, waits 48 h, escalates gaps | `examples/pre-departure-check.json` |
| **Weakness** | Client knowledge lives in a few heads | Account 360: status, stakeholders, risks, next step, every line cited | `/ops/accounts`, `igs_common/accounts/` |
| **Opportunity** | 2027 Women's World Cup family packages | Inquiry chat and proposals that scale without headcount growing at the same rate | `/chat`, versioned flows |
| **Opportunity** | Predictable US college calendar, strong referrals | Lead pipeline, date-based reactivation, referral signals in Account 360 | `/ops/leads`, `wait` node |
| **Opportunity** | New destinations and sports | Catalog and planning rules are data, not code | `catalog.yaml` |
| **Threat** | Faster or cheaper competitors | Same-day proposals; competitor quotes tracked as risks | Lakeshore story in `fixtures/accounts.yaml` |
| **Threat** | On-tour logistics failures | "Today" queue with alerts, per-item status, incidents | `/ops` |
| **Threat** | Minors' personal data | Player data never reaches the LLM or embeddings; per-tenant RLS | `docs/architecture/security.md` |

## IGS OS itself, honestly

- **Strengths:** built for this business; human in control with full audit; measured quality (856 Python tests, e2e with axe, BGE-M3 recall@5 0.82); horizontal scale.
- **Weaknesses:** demo data only; no integrations with IGS's current tools yet; self-hosted Temporal has an ops cost; the flow editor still speaks to technical users.
- **Opportunities:** become the team's OS for the 2027 World Cup; copilot through MCP from Claude; a product other tour operators could use.
- **Threats:** LLM cost and failure modes (mitigated with mandatory citations, risk-tiered tools, model per role); adoption and change management; minors' data compliance (COPPA, LGPD, Argentina's Ley 25.326) needs legal review before real data.

## Impact hypotheses (ranges, to validate against a measured baseline)

- First response to an inquiry: from 4–48 h to under 5 minutes; approved proposal in 4–24 h.
- Proposals per coordinator per week: from 5–10 to 15–30.
- Provider confirmation follow-ups: 60–80% automated.
- Inquiry-to-deposit conversion: +10–25% relative.

## First questions for IGS

1. What eats most of the ops team's time today?
2. How many inquiries and tours per season, and how long from inquiry to proposal?
3. Which tools do you use today, and which won't you change?
4. Expected family volume for the 2027 World Cup?
5. Which minors' data do you handle, where does it live, and who owns compliance?
