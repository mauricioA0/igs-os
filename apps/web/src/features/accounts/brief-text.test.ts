import { describe, expect, it } from "vitest";
import { splitLead } from "./brief-text";

describe("splitLead", () => {
  it("keeps the citations of the first sentence with it", () => {
    expect(splitLead("Lakeshore está en rojo por US$2.280 vencidos [1]. Haines decide el 31 [2].")).toEqual([
      "Lakeshore está en rojo por US$2.280 vencidos [1].",
      "Haines decide el 31 [2].",
    ]);
  });

  it("returns the whole text when there is a single sentence", () => {
    expect(splitLead("Todo en orden [1].")).toEqual(["Todo en orden [1].", ""]);
  });
});
