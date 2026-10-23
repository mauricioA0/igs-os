import type { ComponentType } from "react";

export function displayNameOf(Component: ComponentType<never>): string {
  return Component.displayName ?? Component.name ?? "Component";
}
