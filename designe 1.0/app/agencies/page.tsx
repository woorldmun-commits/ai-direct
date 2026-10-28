import {publicMetadata} from '@/lib/public-metadata';
import {PublicPage} from '@/components/ix/public/pages';
export const metadata=publicMetadata('/agencies', 'Агентствам', 'Отдельные рабочие пространства клиентов, рекомендации с основаниями и история решений: работа агентства с портфелем проектов в INROU.');
export default function Page(){return <PublicPage page="agencies"/>;}
