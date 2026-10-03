import type { Metadata } from "next";
import { Today } from "@/components/dashboard/today";

export const metadata: Metadata = { title: "Сегодня" };

export default function TodayPage() {
  return <Today />;
}
