import { describe, expect, it } from "vitest";
import { ApiError } from "@/lib/api/errors";
import { aiUnavailable } from "./ai-errors";

const problem = (status: number, slug: string) =>
  new ApiError({ type: `https://igs-os.dev/problems/${slug}`, title: slug, status } as never);

describe("aiUnavailable (QA D-14)", () => {
  it("tells 'not configured' apart from a failure", () => {
    expect(aiUnavailable(problem(503, "ai-unavailable"))).toBe("not-configured");
    expect(aiUnavailable(problem(502, "llm-error"))).toBe("failed");
    expect(aiUnavailable(new Error("boom"))).toBe("failed");
  });
});
