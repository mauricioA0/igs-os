// Read path under load: the ops panel's main queries as the public demo tenant (no auth).
// Target from docs/architecture/cost-and-scale.md: p95 < 300 ms, < 1% errors.
import http from "k6/http";
import { check, group } from "k6";

const BASE = __ENV.API_URL || "http://localhost:8000";
const ACCOUNT = __ENV.ACCOUNT_ID || "17e97bd0-4cd1-52f0-b0bb-4bb8a22d91c8"; // Lakeshore
const EXECUTION = __ENV.EXECUTION_ID || "57c5d89c-7923-572a-beec-09b92e5e1f29";

export const options = {
  scenarios: {
    reads: {
      executor: "ramping-vus",
      stages: [
        { duration: __ENV.RAMP || "10s", target: Number(__ENV.VUS || 20) },
        { duration: __ENV.HOLD || "20s", target: Number(__ENV.VUS || 20) },
        { duration: "5s", target: 0 },
      ],
    },
  },
  thresholds: {
    http_req_failed: ["rate<0.01"],
    "http_req_duration{group:::trips}": ["p(95)<300"],
    "http_req_duration{group:::account}": ["p(95)<300"],
  },
};

export default function () {
  group("trips", () => {
    const r = http.get(`${BASE}/v1/trips?limit=25`);
    check(r, { "trips 200": (x) => x.status === 200 });
  });
  group("accounts", () => {
    check(http.get(`${BASE}/v1/accounts`), { "accounts 200": (x) => x.status === 200 });
  });
  group("account", () => {
    check(http.get(`${BASE}/v1/accounts/${ACCOUNT}`), { "account 200": (x) => x.status === 200 });
  });
  group("approvals", () => {
    check(http.get(`${BASE}/v1/approvals?status=pending`), { "approvals 200": (x) => x.status === 200 });
  });
  group("execution", () => {
    check(http.get(`${BASE}/v1/executions/${EXECUTION}`), { "execution 200": (x) => x.status === 200 });
  });
}
