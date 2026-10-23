import type { Metadata } from "next";
import { getTrip } from "@/features/trips/api";
import { TripDetailContainer } from "@/features/trips/trip-detail.container";

type Props = { params: Promise<{ id: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const trip = await getTrip((await params).id).catch(() => null);
  return { title: trip ? `${trip.code ?? "Gira"} · ${trip.team.organization ?? trip.title}` : "Gira" };
}

export default async function TripPage({ params }: Props) {
  return <TripDetailContainer id={(await params).id} />;
}
