import 'server-only';
import { createHash } from 'node:crypto';
import { apiOrigin } from './api-origin';

export const LEGAL_KEYS = { offer: 'offer', 'pd-consent': 'pd_consent', 'marketing-consent': 'marketing', privacy: 'privacy', cookies: 'cookies', requisites: 'requisites' } as const;
export type LegalDocument = { document: string; version: string; locale: string; sha256: string; text: string; approved: boolean };
export type AcceptedDocuments = {offer: string; pd_consent: string};

function validVersion(version: unknown): version is string {
  return typeof version === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(version)
    && Number.isFinite(Date.parse(version)) && new Date(version).toISOString().slice(0, 10) === version;
}

export function registrationDocuments(offer: LegalDocument | null, consent: LegalDocument | null): AcceptedDocuments | null {
  return offer?.approved && consent?.approved ? {offer: offer.version, pd_consent: consent.version} : null;
}

export function validLegalDocument(value: unknown, key: string, version?: string): value is LegalDocument {
  if (!value || typeof value !== 'object') return false;
  const doc = value as Record<string, unknown>;
  return doc.document === key && validVersion(doc.version) && (version === undefined || doc.version === version) && doc.locale === 'ru-RU'
    && typeof doc.approved === 'boolean' && typeof doc.text === 'string' && doc.text.length > 0
    && doc.text.length <= 131072 && typeof doc.sha256 === 'string' && /^[a-f0-9]{64}$/.test(doc.sha256)
    && createHash('sha256').update(doc.text, 'utf8').digest('hex') === doc.sha256;
}

export async function legalDocument(key: string, version?: string, timeoutMs = 8000): Promise<LegalDocument | null> {
  if (!Object.values(LEGAL_KEYS).some(known => known === key)) return null;
  if (version !== undefined && !validVersion(version)) return null;
  const origin = apiOrigin();
  if (!origin) return null;
  try {
    const url = new URL(`/api/v1/legal/documents/${key}?locale=ru-RU`, origin);
    if (version !== undefined) url.searchParams.set('version', version);
    const response = await fetch(url, {
      cache: 'no-store', redirect: 'error', signal: AbortSignal.timeout(timeoutMs), headers: { Accept: 'application/json' },
    });
    if (!response.ok || !response.headers.get('content-type')?.includes('application/json') || !response.body) return null;
    const reader = response.body.getReader();
    const chunks: Uint8Array[] = [];
    let size = 0;
    try {
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        size += value.byteLength;
        if (size > 262144) return null;
        chunks.push(value);
      }
    } finally { await reader.cancel(); }
    const bytes = new Uint8Array(size);
    let offset = 0;
    for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
    const value: unknown = JSON.parse(new TextDecoder().decode(bytes));
    return validLegalDocument(value, key, version) ? value : null;
  } catch { return null; }
}
