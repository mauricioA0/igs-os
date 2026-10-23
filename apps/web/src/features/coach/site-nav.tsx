"use client";

// Centered pill nav of the site header; the current route gets the white pill.
import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV = [
  { href: "/", label: "Home" },
  { href: "/chat", label: "Plan a tour" },
  { href: "/ops", label: "Ops panel" },
  { href: "/ops/flows", label: "Flows" },
];

export function SiteNav() {
  const pathname = usePathname();
  return (
    <nav aria-label="Main" className="hidden md:block">
      <ul className="flex items-center gap-1 rounded-full border border-line bg-white/5 p-1">
        {NAV.map((item) => {
          const active = pathname === item.href;
          return (
            <li key={item.href}>
              <Link
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={`pill ${active ? "pill-active" : "pill-idle"}`}
              >
                {item.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
