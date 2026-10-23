"use client";

import Link from "next/link";
import { ErrorScreen, linkClass, primaryClass } from "../_errors/error-screen";

// Coach-facing pages (chat, proposal): English and on-brand, never Next's generic 500.
export default function PublicError({ reset }: { error: Error; reset: () => void }) {
  return (
    <ErrorScreen
      lang="en"
      eyebrow="Infinity Global Sports"
      title="We'll be right back"
      body="This page couldn't load just now. Your tour details are safe — try again in a moment, or start a chat and our team will follow up."
      actions={
        <>
          <button type="button" onClick={reset} className={primaryClass}>
            Try again
          </button>
          <Link href="/chat" className={linkClass}>
            Plan your tour
          </Link>
        </>
      }
    />
  );
}
