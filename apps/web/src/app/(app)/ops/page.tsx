import type { Metadata } from "next";
import { TodayContainer } from "@/features/today/today.container";

export const metadata: Metadata = { title: "Hoy" };

export default function TodayPage() {
  return <TodayContainer />;
}
