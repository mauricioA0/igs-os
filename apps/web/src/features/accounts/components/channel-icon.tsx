import { type LucideIcon, Mail, MessageCircle, MessageSquare, Phone, StickyNote, Users } from "lucide-react";
import { cn } from "@/components/ui";

const ICON: Record<string, LucideIcon> = {
  email: Mail,
  call: Phone,
  meeting: Users,
  chat: MessageSquare,
  whatsapp: MessageCircle,
  note: StickyNote,
};

export function ChannelIcon({ channel, className }: { channel: string; className?: string }) {
  const Icon = ICON[channel] ?? MessageSquare;
  return <Icon className={cn("size-4", className)} aria-hidden />;
}
