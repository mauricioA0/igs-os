import type { Metadata } from "next";
import { GuideWidget } from "@/features/guide";
import { RootDocument, SITE_METADATA } from "../_document/root-document";

export const metadata: Metadata = SITE_METADATA;

// Landing and design system: English (the first-time visitor's entry point).
export default function SiteLayout({ children }: LayoutProps<"/">) {
  return (
    <RootDocument lang="en">
      {children}
      <GuideWidget locale="en" />
    </RootDocument>
  );
}
