import type { Metadata } from "next";

// All legal routes remain drafts until counsel approves the exact documents.
export const metadata: Metadata = { robots: { index: false, follow: false } };

export default function LegalLayout({ children }: { children: React.ReactNode }) {
  return children;
}
