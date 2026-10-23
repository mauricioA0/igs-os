// The 2-minute guided tour (docs/design/demo-script.md). One story — Lakeshore University's
// March 2027 inquiry — followed across every surface. Ids are the seed's stable fixture UUIDs
// (`igs_common.seed.fixture_id("igs", kind, key)`), so links survive re-seeds and demo resets.

export const DEMO_IDS = {
  lakeshoreAccount: "17e97bd0-4cd1-52f0-b0bb-4bb8a22d91c8", // acc-lakeshore
  lakeshoreTrip: "c0b16481-9260-5765-8dd1-788c7b2a63ab", // t-2711
  proposalApproval: "d129a224-c013-5340-b0eb-95fe1c3fb000", // a-9003
  inquiryExecution: "57c5d89c-7923-572a-beec-09b92e5e1f29", // ex-lak-inbound
} as const;

export type TourStep = {
  /** `data-tour` value of the element to spotlight on that page. */
  anchor: string;
  /** Route (path + optional query) the step lives on. */
  href: string;
  title: string;
  body: string;
};

export const TOUR_STEPS: readonly TourStep[] = [
  {
    anchor: "today-queue",
    href: "/ops",
    title: "Today, for the ops team",
    body: "Everything that needs a person, ranked. Lakeshore University is at the top in red: the team's enrollment fees (24 × US$95, per IGS's terms) are a week overdue and the hotel releases the tour's blocks in 9 days.",
  },
  {
    anchor: "account-health",
    href: `/ops/accounts/${DEMO_IDS.lakeshoreAccount}`,
    title: "Account 360",
    body: "Why it's red, who decides and what was promised — every line cites the email, call or chat it came from. Health comes from rules, never from the model.",
  },
  {
    anchor: "copilot-ask",
    href: `/ops/accounts/${DEMO_IDS.lakeshoreAccount}`,
    title: "Ask the copilot",
    body: "“¿Cómo está Lakeshore y qué falta para que firmen?” The agent uses the same tools as the MCP server and answers with sources — or says it doesn't know.",
  },
  {
    anchor: "approval-card",
    href: `/ops/approvals?id=${DEMO_IDS.proposalApproval}`,
    title: "A human approves",
    body: "The sales agent drafted proposal IGS-2711 from Dana's chat but can't send it. Ops sees exactly what will go out, then approves, edits or rejects.",
  },
  {
    anchor: "execution-graph",
    href: `/ops/flows/inbound-inquiry/executions/${DEMO_IDS.inquiryExecution}`,
    title: "A durable flow",
    body: "The inbound-inquiry flow has been waiting on that approval without holding a server. Every node's input and output is here, and it resumes the moment ops decides.",
  },
  {
    anchor: "proposal-hero",
    href: `/proposal/${DEMO_IDS.lakeshoreTrip}`,
    title: "What the coach receives",
    body: "The proposal Dana takes to Robert Haines for next week's budget meeting: itinerary, opponents matched to her team's level, one price, IGS's payment terms and a clear way to reserve.",
  },
];

export const TOUR_PARAM = "tour";

/** Step number (1-based) from the `?tour=` query value, or null when the tour is off. */
export function parseStep(value: string | null | undefined): number | null {
  if (!value) return null;
  const n = Number(value);
  return Number.isInteger(n) && n >= 1 && n <= TOUR_STEPS.length ? n : null;
}

/** URL for a step, keeping the step's own query (e.g. `?id=` on approvals). */
export function stepUrl(step: number): string {
  const target = TOUR_STEPS[step - 1];
  const [path, query = ""] = target.href.split("?");
  const params = new URLSearchParams(query);
  params.set(TOUR_PARAM, String(step));
  return `${path}?${params.toString()}`;
}

export const TOUR_START_URL = stepUrl(1);
