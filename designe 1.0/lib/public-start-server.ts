import 'server-only';
import {cache} from 'react';
import {emailEnabled} from './email-auth';
import {legalDocument} from './legal-document';
import {publicStart} from './public-start';

export const loadPublicStart = cache(async () => {
  const [email, offer, consent] = await Promise.all([
    emailEnabled(1500), legalDocument('offer', undefined, 1500), legalDocument('pd_consent', undefined, 1500),
  ]);
  return publicStart(email && !!offer?.approved && !!consent?.approved,
    process.env.INROU_PUBLIC_CONTACT_EMAIL ?? 'woorldmub@gmail.com');
});
