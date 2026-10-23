"use client";

import { AlertTriangle } from "lucide-react";
import { Button, EmptyState } from "@/components/ui";

export default function ApprovalsError({ reset }: { error: Error; reset: () => void }) {
  return (
    <div lang="es">
      <EmptyState
        icon={<AlertTriangle />}
        title="No pudimos cargar las aprobaciones"
        description="La API no respondió. Las decisiones pendientes siguen esperando: no se envió nada."
        action={<Button onClick={reset}>Reintentar</Button>}
      />
    </div>
  );
}
