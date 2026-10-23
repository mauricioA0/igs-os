import { act, render, renderHook, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "./tabs";
import { useControllableState } from "./use-controllable-state";

describe("useControllableState", () => {
  it("owns the state when uncontrolled and reports changes", () => {
    const onChange = vi.fn();
    const { result } = renderHook(() => useControllableState({ defaultValue: "a", onChange }));
    act(() => result.current[1]("b"));
    expect(result.current[0]).toBe("b");
    expect(onChange).toHaveBeenCalledWith("b");
  });

  it("follows the prop when controlled and never stores its own copy", () => {
    const onChange = vi.fn();
    const { result, rerender } = renderHook(({ value }) => useControllableState({ value, defaultValue: "a", onChange }), {
      initialProps: { value: "x" },
    });
    act(() => result.current[1]("y"));
    expect(result.current[0]).toBe("x"); // parent hasn't accepted the change yet
    expect(onChange).toHaveBeenCalledWith("y");
    rerender({ value: "y" });
    expect(result.current[0]).toBe("y");
  });

  it("supports functional updates and skips no-op changes", () => {
    const onChange = vi.fn();
    const { result } = renderHook(() => useControllableState({ defaultValue: 1, onChange }));
    act(() => result.current[1]((n) => n + 1));
    act(() => result.current[1](2));
    expect(result.current[0]).toBe(2);
    expect(onChange).toHaveBeenCalledTimes(1);
  });
});

describe("Tabs", () => {
  const ui = (props: { value?: string; onValueChange?: (v: string) => void }) => (
    <Tabs defaultValue="one" {...props}>
      <TabsList label="Sections">
        <TabsTrigger value="one">One</TabsTrigger>
        <TabsTrigger value="two">Two</TabsTrigger>
      </TabsList>
      <TabsContent value="one">first</TabsContent>
      <TabsContent value="two">second</TabsContent>
    </Tabs>
  );

  it("works uncontrolled", () => {
    render(ui({}));
    fireEvent.click(screen.getByRole("tab", { name: "Two" }));
    expect(screen.getByRole("tabpanel").textContent).toBe("second");
  });

  it("works controlled", () => {
    const onValueChange = vi.fn();
    render(ui({ value: "one", onValueChange }));
    fireEvent.click(screen.getByRole("tab", { name: "Two" }));
    expect(onValueChange).toHaveBeenCalledWith("two");
    expect(screen.getByRole("tabpanel").textContent).toBe("first");
  });
});
