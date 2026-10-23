import { describe, expect, it } from "vitest";
import { sharedApiKey } from "./server";

// S-01 (docs/reviews/security-2026-10.md): without sign-in, a shared key acts for every visitor.
describe("sharedApiKey", () => {
  it("is used in local development", () => {
    expect(sharedApiKey({ NODE_ENV: "development", IGS_API_KEY: "igs_k" })).toBe("igs_k");
  });

  it("is ignored in production unless the deployment opts in", () => {
    expect(sharedApiKey({ NODE_ENV: "production", IGS_API_KEY: "igs_k" })).toBeUndefined();
    expect(
      sharedApiKey({ NODE_ENV: "production", IGS_API_KEY: "igs_k", IGS_WEB_ALLOW_SHARED_KEY: "1" }),
    ).toBe("igs_k");
  });

  it("is undefined when no key is configured", () => {
    expect(sharedApiKey({ NODE_ENV: "development" })).toBeUndefined();
  });
});
