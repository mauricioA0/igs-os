import Link from "next/link";
import { ErrorScreen, linkClass } from "../../_errors/error-screen";

export default function OpsNotFound() {
  return (
    <ErrorScreen
      lang="es"
      eyebrow="404"
      title="No encontramos esto"
      body="Puede que el link sea viejo o que el registro ya no exista."
      actions={
        <Link href="/ops" className={linkClass}>
          Ir a Hoy
        </Link>
      }
    />
  );
}
