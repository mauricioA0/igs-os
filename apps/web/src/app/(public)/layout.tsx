import type { Metadata } from "next";
import "@/features/coach/coach.css";
import { SiteHeader } from "@/features/coach/site-chrome";
import { GuideWidget } from "@/features/guide";
import { RootDocument, SITE_METADATA } from "../_document/root-document";

export const metadata: Metadata = SITE_METADATA;

// Coach-facing surfaces: English, and the dark photographic look of infinityglobalsports.com.
export default function PublicLayout({ children }: LayoutProps<"/">) {
  return (
    <RootDocument lang="en" theme="dark">
      <div className="igs-site flex min-h-dvh flex-col">
        <SiteHeader />
        {children}
      </div>
      <GuideWidget locale="en" />
    </RootDocument>
  );
}
