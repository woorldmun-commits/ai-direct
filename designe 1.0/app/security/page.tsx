import {publicMetadata} from '@/lib/public-metadata';
import {PublicPage} from '@/components/ix/public/pages';
export const metadata=publicMetadata('/security', 'Безопасность', 'Как INROU разделяет доступ к рабочим пространствам и сохраняет основания решений. Изменения в рекламе выполняются вручную.');
export default function Page(){return <PublicPage page="security"/>;}
