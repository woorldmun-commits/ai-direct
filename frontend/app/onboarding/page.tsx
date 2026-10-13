import type { Metadata } from "next";
import { SessionGate, WorkspaceEntry } from "@/components/live/session";
export const metadata: Metadata = { title: "Настройка бизнеса", robots: { index: false, follow: false } };
export default function OnboardingPage() { return <SessionGate><WorkspaceEntry onboarding /></SessionGate>; }
