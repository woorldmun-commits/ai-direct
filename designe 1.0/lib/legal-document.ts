import 'server-only';
import { createHash } from 'node:crypto';
import { apiOrigin } from './api-origin';

export const LEGAL_VERSION = '2026-10-01';
export const LEGAL_KEYS = { offer: 'offer', 'pd-consent': 'pd_consent', 'marketing-consent': 'marketing', privacy: 'privacy', cookies: 'cookies', requisites: 'requisites' } as const;
export type LegalDocument = { document: string; version: string; locale: string; sha256: string; text: string; approved: boolean };

export function validLegalDocument(value: unknown, key: string): value is LegalDocument {
  if (!value || typeof value !== 'object') return false;
  const doc = value as Record<string, unknown>;
  return doc.document === key && doc.version === LEGAL_VERSION && doc.locale === 'ru-RU'
    && typeof doc.approved === 'boolean' && typeof doc.text === 'string' && doc.text.length > 0
    && doc.text.length <= 131072 && typeof doc.sha256 === 'string' && /^[a-f0-9]{64}$/.test(doc.sha256)
    && createHash('sha256').update(doc.text, 'utf8').digest('hex') === doc.sha256;
}

export async function legalDocument(key: string): Promise<LegalDocument | null> {
  if (!Object.values(LEGAL_KEYS).some(known => known === key)) return null;
  const origin = apiOrigin();
  if (!origin) return null;
  try {
    const response = await fetch(new URL(`/api/v1/legal/documents/${key}?version=${LEGAL_VERSION}&locale=ru-RU`, origin), {
      cache: 'no-store', redirect: 'error', signal: AbortSignal.timeout(8000), headers: { Accept: 'application/json' },
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
    return validLegalDocument(value, key) ? value : null;
  } catch { return null; }
}
