import type { Metadata } from "next";
import { LeadsContainer } from "@/features/leads/leads.container";

export const metadata: Metadata = { title: "Leads" };

export default function LeadsPage() {
  return <LeadsContainer />;
}
