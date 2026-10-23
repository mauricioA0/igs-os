import { connection } from "next/server";
import { ApiUnavailable } from "@/features/ops-shell/bits";
import { type AccountSummary, getAccount, listAccounts } from "./api";
import { AccountsList } from "./components/accounts-list";

function Hero() {
  return (
    <header className="space-y-4 border-b border-line pb-8">
      <p className="eyebrow-wide text-muted-foreground">Account 360</p>
      <h1 className="type-hero">
        <span className="headline-muted">Cada cliente, </span>
        <span>con la fuente.</span>
      </h1>
      <p className="max-w-2xl text-muted-foreground">
        Su salud, quién decide y qué está pendiente, armado a partir de mails, llamadas y chats.
      </p>
    </header>
  );
}

/**
 * The list endpoint carries health but not its reasons; accounts that need attention are few, so
 * their first rule-based reason is read from the detail. A failed read just leaves the card without one.
 */
async function reasonsFor(accounts: AccountSummary[]): Promise<Map<string, string>> {
  const flagged = accounts.filter((a) => a.health !== "green").slice(0, 24);
  const details = await Promise.all(flagged.map((a) => getAccount(a.id).catch(() => null)));
  return new Map(
    details.flatMap((d) => (d?.health_reasons?.[0] ? [[d.id, d.health_reasons[0]] as const] : [])),
  );
}

export async function AccountsContainer() {
  await connection();
  let accounts: AccountSummary[];
  try {
    accounts = await listAccounts();
  } catch (error) {
    return (
      <div className="space-y-8">
        <Hero />
        <ApiUnavailable error={error} what="los clientes" />
      </div>
    );
  }
  const reasons = await reasonsFor(accounts);
  return (
    <div className="space-y-8">
      <Hero />
      <AccountsList
        accounts={accounts.map((a) => ({
          id: a.id,
          name: a.name,
          kind: a.kind,
          country: a.country,
          location: [a.city, a.state].filter(Boolean).join(", "),
          programs: a.sport_programs,
          health: a.health,
          status: a.status,
          tier: a.tier,
          reason: reasons.get(a.id),
        }))}
      />
    </div>
  );
}
