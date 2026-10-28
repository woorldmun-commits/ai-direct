import {publicMetadata} from '@/lib/public-metadata';
import {PublicPage} from '@/components/ix/public/pages';
export const metadata=publicMetadata('/pricing', 'Тарифы', 'Планируемые тарифы INROU, количество рекламных аккаунтов и состав подписки. Оплата пока не подключена; рекламный бюджет оплачивается отдельно.');
export default function Page(){return <PublicPage page="pricing"/>;}
