// First-writer-wins under contention: many approvers decide the same pending approval at once.
// Exactly one request may succeed; every other one must get 409 (already-decided/changed).
// Needs an API key with igs:approve bound to an ops user (see loadtest/README.md); run
// `services/core/scripts/demo_reset.py` before each run to put a-9003 back to pending.
import http from "k6/http";
import { check } from "k6";
import { Counter } from "k6/metrics";

const BASE = __ENV.API_URL || "http://localhost:8000";
const APPROVAL = __ENV.APPROVAL_ID || "d129a224-c013-5340-b0eb-95fe1c3fb000"; // a-9003
const KEY = __ENV.API_KEY;
const wins = new Counter("approval_wins");
const conflicts = new Counter("approval_conflicts");

export const options = {
  scenarios: {
    race: { executor: "per-vu-iterations", vus: Number(__ENV.VUS || 25), iterations: 1 },
  },
  thresholds: {
    approval_wins: ["count==1"],
    checks: ["rate==1"],
  },
};

export function setup() {
  if (!KEY) throw new Error("API_KEY is required");
  const r = http.get(`${BASE}/v1/approvals/${APPROVAL}`, { headers: { authorization: `Bearer ${KEY}` } });
  if (r.status !== 200) throw new Error(`approval lookup failed: ${r.status} ${r.body}`);
  return { hash: r.json("payload_hash") };
}

export default function (data) {
  const r = http.post(
    `${BASE}/v1/approvals/${APPROVAL}/decision`,
    JSON.stringify({ decision: "approved", payload_hash: data.hash, comment: `k6 vu ${__VU}` }),
    { headers: { authorization: `Bearer ${KEY}`, "content-type": "application/json" } },
  );
  if (r.status === 200) wins.add(1);
  if (r.status === 409) conflicts.add(1);
  check(r, { "200 or 409": (x) => x.status === 200 || x.status === 409 });
}
