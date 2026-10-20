import type {Metadata} from 'next';
import {ReferenceAuth} from '@/components/reference/auth';
import {emailEnabled} from '@/lib/email-auth';
import {legalDocument} from '@/lib/legal-document';
export const metadata:Metadata={title:'Новый пароль',robots:{index:false,follow:false}};
export const dynamic='force-dynamic';
export default async function Page(){
 const [email,offer,consent]=await Promise.all([emailEnabled(),legalDocument('offer'),legalDocument('pd_consent')]);
 return <ReferenceAuth mode='reset' emailEnabled={email} registrationReady={!!offer?.approved&&!!consent?.approved} localPreview={process.env.REKVERO_LOCAL_PREVIEW==='true'}/>;
}
