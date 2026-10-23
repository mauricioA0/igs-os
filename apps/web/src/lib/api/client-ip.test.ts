import { describe, expect, it } from "vitest";

import { proxyIdentity, visitorIp } from "./client-ip";

describe("visitorIp", () => {
  it("prefers x-real-ip, then the first forwarded hop", () => {
    expect(visitorIp(new Headers({ "x-real-ip": "203.0.113.7" }))).toBe("203.0.113.7");
    expect(visitorIp(new Headers({ "x-forwarded-for": "198.51.100.2, 10.0.0.1" }))).toBe(
      "198.51.100.2",
    );
    expect(visitorIp(new Headers())).toBeUndefined();
  });
});

describe("proxyIdentity", () => {
  const incoming = new Headers({ "x-real-ip": "203.0.113.7" });

  it("adds the address and the secret when the secret is set", () => {
    expect(proxyIdentity(incoming, { IGS_PROXY_SHARED_SECRET: "s3cret" })).toEqual({
      "x-igs-client-ip": "203.0.113.7",
      "x-igs-proxy-secret": "s3cret",
    });
  });

  it("adds nothing without the secret", () => {
    expect(proxyIdentity(incoming, {})).toEqual({});
  });
});
