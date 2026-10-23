import { Skeleton } from "@/components/ui";

export default function Loading() {
  return (
    <div lang="es" className="space-y-6" aria-busy="true" aria-label="Cargando aprobaciones">
      <Skeleton className="h-12 w-64" />
      <div className="grid gap-6 lg:grid-cols-[24rem_minmax(0,1fr)]">
        <div className="space-y-2">
          {Array.from({ length: 5 }, (_, i) => (
            <Skeleton key={i} className="h-24 rounded-lg" />
          ))}
        </div>
        <Skeleton className="h-96 rounded-xl" />
      </div>
    </div>
  );
}
