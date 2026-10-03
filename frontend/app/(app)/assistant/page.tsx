import type { Metadata } from "next";
import { Chat } from "@/components/assistant/chat";

export const metadata: Metadata = { title: "AI-аналитик" };

export default function AssistantPage() {
  return <Chat />;
}
