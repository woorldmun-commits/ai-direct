import {publicMetadata} from '@/lib/public-metadata';
import {PublicPage} from '@/components/ix/public/pages';
export const metadata=publicMetadata('/integrations', 'Интеграции', 'Яндекс Директ и Метрика как источники INROU: подключение для чтения данных, цели, конверсии и ограничения текущей версии.');
export default function Page(){return <PublicPage page="integrations"/>;}
