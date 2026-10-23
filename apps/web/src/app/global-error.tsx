"use client";

// Last-resort boundary when a root layout itself fails: it replaces the whole document, so it
// can't rely on the design system's stylesheet being loaded.
export default function GlobalError({ reset }: { error: Error; reset: () => void }) {
  return (
    <html lang="en">
      <body style={{ fontFamily: "system-ui, sans-serif", margin: 0, background: "#f4f2ee", color: "#1a1a1a" }}>
        <main style={{ maxWidth: 560, margin: "15vh auto", padding: "0 24px" }}>
          <p style={{ letterSpacing: "0.12em", textTransform: "uppercase", fontSize: 12 }}>IGS OS</p>
          <h1 style={{ fontSize: 36, margin: "12px 0" }}>Something went wrong</h1>
          <p>Please try again in a moment.</p>
          <button type="button" onClick={reset} style={{ marginTop: 24, padding: "8px 16px", fontWeight: 600 }}>
            Try again
          </button>
        </main>
      </body>
    </html>
  );
}
