import type { Metadata } from "next";
import Link from "next/link";
import { RootDocument } from "./_document/root-document";
import { ErrorScreen, linkClass } from "./_errors/error-screen";

// Unmatched URLs have no route group (and so no root layout): this renders the whole document,
// with a language and the product's look (QA D-09).
export const metadata: Metadata = { title: "Not found · IGS OS" };

export default function GlobalNotFound() {
  return (
    <RootDocument lang="en">
      <ErrorScreen
        lang="en"
        eyebrow="404"
        title="Page not found"
        body="This address doesn't exist in IGS OS."
        actions={
          <>
            <Link href="/" className={linkClass}>
              Home
            </Link>
            <Link href="/ops" className={linkClass}>
              Ops panel
            </Link>
          </>
        }
      />
    </RootDocument>
  );
}
