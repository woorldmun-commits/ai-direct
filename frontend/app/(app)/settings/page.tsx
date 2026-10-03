import type { Metadata } from "next";
import { Settings } from "@/components/dashboard/settings";

export const metadata: Metadata = { title: "Настройки" };

export default function SettingsPage() {
  return <Settings />;
}
