import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { fetchProposal } from "@/features/coach/api";
import { ProposalView } from "@/features/coach/proposal/proposal-view";

type Props = { params: Promise<{ id: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { id } = await params;
  const p = await fetchProposal(id).catch(() => null);
  if (!p) return { title: "Proposal not found" };
  const title = `${p.team} · ${p.city} ${p.days}-day tour`;
  const description = `${p.days} days in ${p.city}: matches at your level, training and experiences — one all-inclusive price per person.`;
  return { title, description, openGraph: { title, description, type: "article" }, robots: { index: false } };
}

export default async function ProposalPage({ params }: Props) {
  const { id } = await params;
  const p = await fetchProposal(id);
  if (!p) notFound();
  return (
    <main className="flex flex-1 flex-col">
      <ProposalView p={p} />
    </main>
  );
}
