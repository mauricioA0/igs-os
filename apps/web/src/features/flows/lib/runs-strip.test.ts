import { describe, expect, it } from "vitest";
import { runsByDay } from "./runs-strip";

describe("runsByDay", () => {
  const now = Date.parse("2026-10-22T15:00:00Z"); // 12:00 in Buenos Aires

  it("returns seven Buenos Aires days, oldest first, with empty days kept", () => {
    const days = runsByDay([], now);
    expect(days).toHaveLength(7);
    expect(days[0].day).toBe("2026-10-16");
    expect(days[6].day).toBe("2026-10-22");
    expect(days.every((d) => d.total === 0)).toBe(true);
  });

  it("buckets by local day and status, and drops runs outside the window", () => {
    const days = runsByDay(
      [
        { started_at: "2026-10-22T02:00:00Z", status: "succeeded" }, // 21-oct 23:00 BA
        { started_at: "2026-10-22T14:00:00Z", status: "failed" },
        { started_at: "2026-10-22T14:30:00Z", status: "succeeded" },
        { started_at: "2026-10-01T12:00:00Z", status: "succeeded" },
      ],
      now,
    );
    expect(days[5]).toMatchObject({ day: "2026-10-21", total: 1, byStatus: { succeeded: 1 } });
    expect(days[6]).toMatchObject({ total: 2, byStatus: { failed: 1, succeeded: 1 } });
    expect(days.reduce((n, d) => n + d.total, 0)).toBe(3);
  });
});
