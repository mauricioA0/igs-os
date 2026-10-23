"use client";

import { useEffect, useState } from "react";
import { Moon, Sun } from "lucide-react";
import { cn } from "./cn";

type Theme = "light" | "dark";
const KEY = "igs-theme"; // same key the RootDocument pre-paint script reads
const LABEL: Record<"es" | "en", Record<Theme, string>> = {
  es: { light: "Cambiar a tema oscuro", dark: "Cambiar a tema claro" },
  en: { light: "Switch to dark theme", dark: "Switch to light theme" },
};

function apply(theme: Theme) {
  const root = document.documentElement;
  root.classList.toggle("dark", theme === "dark");
  root.classList.toggle("light", theme === "light");
}

// Dark is the default for every surface; light is an opt-in remembered across surfaces.
export function ThemeToggle({ lang = "es", className }: { lang?: "es" | "en"; className?: string }) {
  const [theme, setTheme] = useState<Theme>("dark");

  useEffect(() => {
    try {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- sync with storage after hydration
      if (localStorage.getItem(KEY) === "light") setTheme("light");
    } catch {}
  }, []);

  const toggle = () => {
    const value: Theme = theme === "dark" ? "light" : "dark";
    setTheme(value);
    apply(value);
    try {
      if (value === "dark") localStorage.removeItem(KEY);
      else localStorage.setItem(KEY, value);
    } catch {}
  };

  const Icon = theme === "dark" ? Moon : Sun;
  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={LABEL[lang][theme]}
      title={LABEL[lang][theme]}
      className={cn(
        "inline-flex size-8 items-center justify-center rounded-full bg-secondary text-nav-idle transition-colors hover:text-foreground [&_svg]:size-4",
        className,
      )}
    >
      <Icon />
    </button>
  );
}
