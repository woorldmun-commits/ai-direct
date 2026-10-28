import {publicMetadata} from '@/lib/public-metadata';
import {PublicPage} from '@/components/ix/public/pages';
export const metadata=publicMetadata('/business', 'Бизнесу', 'Фактические рекламные расходы, план и основания рекомендаций в INROU. Проверьте данные перед ручным решением по рекламе.');
export default function Page(){return <PublicPage page="business"/>;}
