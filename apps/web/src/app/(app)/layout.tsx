import type { Metadata } from "next";
import { RootDocument, SITE_METADATA } from "../_document/root-document";

export const metadata: Metadata = SITE_METADATA;

// The ops app: Spanish (WCAG 3.1.1 — the team in Buenos Aires works in Spanish).
export default function AppLayout({ children }: LayoutProps<"/">) {
  return <RootDocument lang="es">{children}</RootDocument>;
}
