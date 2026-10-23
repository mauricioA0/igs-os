import type { Metadata } from "next";
import { AccountsContainer } from "@/features/accounts/accounts.container";

export const metadata: Metadata = { title: "Clientes" };

export default function AccountsPage() {
  return <AccountsContainer />;
}
