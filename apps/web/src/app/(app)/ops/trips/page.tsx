import type { Metadata } from "next";
import { TripsContainer } from "@/features/trips/trips.container";

export const metadata: Metadata = { title: "Giras" };

export default function TripsPage() {
  return <TripsContainer />;
}
