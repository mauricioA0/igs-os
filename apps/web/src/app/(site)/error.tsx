"use client";

import Link from "next/link";
import { ErrorScreen, linkClass, primaryClass } from "../_errors/error-screen";

export default function SiteError({ reset }: { error: Error; reset: () => void }) {
  return (
    <ErrorScreen
      lang="en"
      eyebrow="IGS OS"
      title="Something went wrong"
      body="This page couldn't load. Try again, or open the ops panel directly."
      actions={
        <>
          <button type="button" onClick={reset} className={primaryClass}>
            Try again
          </button>
          <Link href="/ops" className={linkClass}>
            Open the ops panel
          </Link>
        </>
      }
    />
  );
}
