import { Suspense, type ReactNode } from "react";
import { TourRail } from "@/features/tour";
import { Barlow_Condensed, DM_Sans, Montserrat } from "next/font/google";
import "../globals.css";

// The site's three faces (docs/design/igs-site-style.md). Barlow Condensed stands in for the
// commercial Klein Condensed; DM Sans and Montserrat are the ones the site itself loads.
const barlowCondensed = Barlow_Condensed({
  variable: "--font-barlow-condensed",
  subsets: ["latin"],
  weight: ["800", "900"],
});
const dmSans = DM_Sans({ variable: "--font-dm-sans", subsets: ["latin"], weight: ["400", "600", "700"] });
const montserrat = Montserrat({ variable: "--font-montserrat", subsets: ["latin"], weight: ["400", "500", "600"] });

export const THEME_STORAGE_KEY = "igs-theme";

// Dark is the default; runs before paint so a stored "light" choice never flashes dark first.
const themeScript = `try{if(localStorage.getItem("${THEME_STORAGE_KEY}")==="light"){var c=document.documentElement.classList;c.remove("dark");c.add("light")}}catch(e){}`;

// The <html>/<body> shell shared by every root layout. Each route group renders it with its own
// language: ops and the app in Spanish, coach-facing pages in English (WCAG 3.1.1).
export function RootDocument({
  lang,
  theme,
  children,
}: {
  lang: "es" | "en";
  /** Force a theme for the whole surface; otherwise dark unless the user picked light. */
  theme?: "light" | "dark";
  children: ReactNode;
}) {
  return (
    <html
      lang={lang}
      suppressHydrationWarning
      className={[barlowCondensed.variable, dmSans.variable, montserrat.variable, "h-full antialiased", theme ?? "dark"]
        .filter(Boolean)
        .join(" ")}
    >
      <head>{!theme && <script dangerouslySetInnerHTML={{ __html: themeScript }} />}</head>
      <body className="flex min-h-full flex-col">
        {children}
        {/* The guided tour crosses every surface and reads ?tour= (useSearchParams). */}
        <Suspense fallback={null}>
          <TourRail />
        </Suspense>
      </body>
    </html>
  );
}

export const SITE_METADATA = {
  title: { default: "IGS OS", template: "%s · IGS OS" },
  description:
    "The operating system for Infinity Global Sports — agents, durable flows and RAG for sports tour operations.",
};
