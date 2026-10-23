import { execSync } from "node:child_process";
import path from "node:path";

// Resets the public demo tenant so every run starts from the same Lakeshore story.
// `--reset-demo` is the dedicated command (wave 3, X8); a plain idempotent seed is the fallback.
export default function globalSetup(): void {
  if (process.env.E2E_SKIP_RESET) return;
  const root = path.resolve(__dirname, "../../..");
  const env = {
    ...process.env,
    DATABASE_URL: process.env.DATABASE_URL ?? "postgres://igs:igs@localhost:5433/igs",
    OPENAI_API_KEY: "",
  };
  const run = (args: string) =>
    execSync(`uv run python -m igs_common.seed ${args}`, { cwd: root, env, stdio: "pipe" });
  try {
    run("--reset-demo");
  } catch {
    run("");
  }
}
