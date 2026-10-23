import { useSyncExternalStore } from "react";

// React Flow marks its root "light" unless told otherwise, and the tokens scope the light theme to
// `.light`: follow the page's theme so the canvas never flips to light inside a dark page.
function subscribeTheme(onChange: () => void) {
  const observer = new MutationObserver(onChange);
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
  return () => observer.disconnect();
}

export function useColorMode(): "light" | "dark" {
  return useSyncExternalStore(
    subscribeTheme,
    () => (document.documentElement.classList.contains("light") ? "light" : "dark"),
    () => "dark",
  );
}
