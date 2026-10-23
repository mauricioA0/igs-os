import {
  Bot,
  CircleStop,
  Flag,
  GitBranch,
  GitFork,
  Globe,
  Hourglass,
  Layers,
  ListChecks,
  Mail,
  MessageSquare,
  Repeat,
  ScanText,
  Search,
  ShieldCheck,
  Split,
  TextCursorInput,
  Variable,
  Zap,
  type LucideIcon,
} from "lucide-react";
import type { FlowNodeType } from "../lib/types";

// One icon per step type. Category is told by the icon and its label; color stays for state.
export const stepIcons: Record<FlowNodeType, LucideIcon> = {
  agent: Bot,
  extract: ScanText,
  classify: Split,
  knowledge_search: Search,
  say: MessageSquare,
  capture: TextCursorInput,
  choice: ListChecks,
  condition: GitBranch,
  switch: GitFork,
  set: Variable,
  map: Repeat,
  subflow: Layers,
  wait: Hourglass,
  end: CircleStop,
  http: Globe,
  action: Zap,
  send_message: Mail,
  emit_event: Flag,
  approval: ShieldCheck,
};

export function StepIcon({ type, className = "" }: { type: FlowNodeType; className?: string }) {
  const Icon = stepIcons[type] ?? Zap;
  return (
    <span aria-hidden className={`grid size-7 shrink-0 place-items-center rounded-md border border-line bg-raised text-foreground ${className}`}>
      <Icon className="size-3.5" strokeWidth={2} />
    </span>
  );
}
