import type { Metadata } from "next";
import { ReferenceAuth } from "@/components/reference/auth";
import { emailEnabled } from "@/lib/email-auth";
import { legalDocument } from "@/lib/legal-document";
export const metadata: Metadata = { title: "Вход в AdPilot", robots: { index: false, follow: false }, alternates: { canonical: "/login" } };
export default async function LoginPage({ searchParams }: { searchParams: Promise<{ error?: string }> }) {
  const query = await searchParams;
  const [offer, consent, email] = await Promise.all([legalDocument('offer'), legalDocument('pd_consent'),emailEnabled()]);
  return <ReferenceAuth emailEnabled={email} localPreview={process.env.REKVERO_LOCAL_PREVIEW==='true'} callbackError={!!query.error} registrationReady={!!offer?.approved && !!consent?.approved} />;
}
