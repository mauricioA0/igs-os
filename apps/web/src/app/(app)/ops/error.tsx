"use client";

import Link from "next/link";
import { ErrorScreen, linkClass, primaryClass } from "../../_errors/error-screen";

// Ops pages that can't render (API down, unexpected failure): Spanish, inside the ops shell.
export default function OpsError({ reset }: { error: Error; reset: () => void }) {
  return (
    <ErrorScreen
      lang="es"
      eyebrow="Operaciones"
      title="No pudimos cargar esta pantalla"
      body="La API no respondió o algo falló. No se envió nada ni se perdió ningún cambio: reintentá en unos segundos."
      actions={
        <>
          <button type="button" onClick={reset} className={primaryClass}>
            Reintentar
          </button>
          <Link href="/ops" className={linkClass}>
            Ir a Hoy
          </Link>
        </>
      }
    />
  );
}
