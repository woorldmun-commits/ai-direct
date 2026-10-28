import type { Metadata } from "next";
import { ReferenceAuth } from "@/components/reference/auth";
import { emailEnabled } from "@/lib/email-auth";
import { legalDocument, registrationDocuments } from "@/lib/legal-document";
export const metadata: Metadata = { title: "Вход в inrou", robots: { index: false, follow: false }, alternates: { canonical: "/login" } };
export default async function LoginPage({ searchParams }: { searchParams: Promise<{ error?: string; legacy?: string }> }) {
  const query = await searchParams;
  const [offer, consent, email] = await Promise.all([legalDocument('offer'), legalDocument('pd_consent'),emailEnabled()]);
  return <ReferenceAuth emailEnabled={email} legacyLogin={query.legacy==='1'} localPreview={process.env.NODE_ENV!=='production'&&process.env.INROU_LOCAL_PREVIEW==='true'} callbackError={!!query.error} acceptedDocuments={registrationDocuments(offer,consent)} />;
}
