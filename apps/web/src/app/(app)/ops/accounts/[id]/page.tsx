import type { Metadata } from "next";
import { AccountDetailContainer } from "@/features/accounts/account-detail.container";
import { getAccount } from "@/features/accounts/api";

type Props = { params: Promise<{ id: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const account = await getAccount((await params).id).catch(() => null);
  return { title: account?.name ?? "Cliente" };
}

export default async function AccountPage({ params }: Props) {
  return <AccountDetailContainer id={(await params).id} />;
}
