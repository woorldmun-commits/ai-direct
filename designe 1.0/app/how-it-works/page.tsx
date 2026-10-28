import {publicMetadata} from '@/lib/public-metadata';
import {PublicPage} from '@/components/ix/public/pages';
export const metadata=publicMetadata('/how-it-works', 'Как работает', 'Пять шагов работы с INROU: подключение Директа и Метрики, проверка данных, изучение оснований, ручное решение и проверка результата.');
export default function Page(){return <PublicPage page="how-it-works"/>;}
