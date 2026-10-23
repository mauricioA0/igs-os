import type { Metadata } from "next";
import { CoachChat } from "@/features/coach/chat/coach-chat.container";
import { SiteFooter } from "@/features/coach/site-chrome";

export const metadata: Metadata = {
  title: "Plan your team's tour",
  description: "Talk to the Infinity Global Sports tour concierge: opponents at your level and a full tour proposal in minutes.",
};

const PROMISES = [
  ["Matched opponents", "Clubs and academies within one level of your team."],
  ["A full itinerary", "Matches, training and experiences, day by day."],
  ["One price", "All-inclusive on the ground, per person. No cost lines."],
];

export default function ChatPage() {
  return (
    <>
      <main className="relative isolate flex flex-1 flex-col">
        <div aria-hidden className="stadium-art absolute inset-0 -z-10 hidden lg:block" />
        <div className="site-container grid flex-1 lg:grid-cols-[1fr_28rem] lg:gap-12 lg:px-8">
          {/* Desktop only: the site's hero beside the concierge. On a phone the chat is the page. */}
          <section aria-labelledby="chat-hero" className="hidden flex-col justify-center py-16 lg:flex">
            <p className="eyebrow-wide">Plan a tour</p>
            <h1 id="chat-hero" className="type-mega mt-6">
              <span className="headline-muted">Your team.</span>
              <br />
              Our pitch.
            </h1>
            <p className="copy-long mt-8 max-w-lg">
              Tell the concierge about your team. It matches opponents at your level and drafts a
              complete tour proposal in minutes — a person from our team reviews it before it&apos;s
              sent.
            </p>
            <ul className="mt-10 grid max-w-2xl grid-cols-3 gap-4">
              {PROMISES.map(([t, d]) => (
                <li key={t} className="border-t border-line-strong pt-4">
                  <p className="type-small-title">{t}</p>
                  <p className="mt-2 text-sm leading-5 text-muted-foreground">{d}</p>
                </li>
              ))}
            </ul>
          </section>
          <h1 className="sr-only lg:hidden">Plan your team&apos;s tour</h1>
          <CoachChat />
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
