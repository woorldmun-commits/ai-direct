import {publicMetadata} from '@/lib/public-metadata';
import {PublicPage} from '@/components/ix/public/pages';
export const metadata=publicMetadata('/features', 'Возможности', 'Контроль расходов, рекомендации с основаниями, качество источников и история решений: возможности INROU для работы с Яндекс Директом и Метрикой.');
export default function Page(){return <PublicPage page="features"/>;}
