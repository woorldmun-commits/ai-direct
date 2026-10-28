import {publicMetadata} from '@/lib/public-metadata';
import {PublicPage} from '@/components/ix/public/pages';
export const metadata=publicMetadata('/faq', 'FAQ', 'Ответы о подключении INROU, источниках данных, ручных решениях, ограничениях рекомендаций и планируемой подписке.');
export default function Page(){return <PublicPage page="faq"/>;}
