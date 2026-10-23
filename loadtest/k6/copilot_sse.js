// Copilot turns over SSE against the mock LLM (loadtest/mock_llm): measures the API's own
// overhead (tool registry, policy, persistence, tracing) on top of a fixed model latency.
// Each iteration posts one turn and reads the stream to the `done` event.
import http from "k6/http";
import { check } from "k6";
import { Trend } from "k6/metrics";

const BASE = __ENV.API_URL || "http://localhost:8000";
const ttfb = new Trend("copilot_ttfb", true);

export const options = {
  scenarios: {
    turns: {
      executor: "constant-vus",
      vus: Number(__ENV.VUS || 10),
      duration: __ENV.DURATION || "30s",
    },
  },
  thresholds: {
    http_req_failed: ["rate<0.01"],
    checks: ["rate>0.99"],
  },
};

export default function () {
  const r = http.post(
    `${BASE}/v1/copilot/turns`,
    JSON.stringify({ message: "¿Cómo está Lakeshore y qué falta para que firmen?" }),
    {
      headers: {
        "content-type": "application/json",
        accept: "text/event-stream",
        ...(__ENV.API_KEY ? { authorization: `Bearer ${__ENV.API_KEY}` } : {}),
      },
      timeout: "60s",
    },
  );
  ttfb.add(r.timings.waiting);
  check(r, {
    "turn 200": (x) => x.status === 200,
    "stream ends with done": (x) => typeof x.body === "string" && x.body.includes("event: done"),
  });
}
