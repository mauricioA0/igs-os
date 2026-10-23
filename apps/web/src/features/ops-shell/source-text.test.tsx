import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { looksEnglish, ReasonText, SourceText } from "./source-text";

describe("SourceText (QA D-07)", () => {
  it("detects English client text and Spanish system text", () => {
    expect(looksEnglish("The registration fees were due by October 15 for the March trip")).toBe(true);
    expect(looksEnglish("Saldo vencido: la seña de la gira está pendiente")).toBe(false);
  });

  it("marks English quotes with lang and a visible label", () => {
    render(<SourceText text="The hotel will release the block and the fee is due" />);
    const quote = screen.getByText("The hotel will release the block and the fee is due");
    expect(quote.closest("q")?.getAttribute("lang")).toBe("en");
    expect(screen.getByText("(original en inglés)")).toBeTruthy();
  });

  it("keeps the Spanish reason label and quotes only the statement", () => {
    render(<ReasonText reason="Riesgo abierto: The deposit was due on October 15 and is still open" />);
    expect(screen.getByText(/Riesgo abierto:/)).toBeTruthy();
    expect(screen.getByText("The deposit was due on October 15 and is still open").closest("q")).toBeTruthy();
  });
});
