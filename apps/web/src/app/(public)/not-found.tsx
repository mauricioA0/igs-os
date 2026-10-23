import Link from "next/link";
import { ErrorScreen, linkClass } from "../_errors/error-screen";

export default function PublicNotFound() {
  return (
    <ErrorScreen
      lang="en"
      eyebrow="404"
      title="This proposal isn't here"
      body="The link may have expired or been mistyped. Ask your tour coordinator for a new one, or start a new inquiry."
      actions={
        <Link href="/chat" className={linkClass}>
          Plan your tour
        </Link>
      }
    />
  );
}
