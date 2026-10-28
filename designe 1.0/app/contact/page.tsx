import {publicMetadata} from '@/lib/public-metadata';
import {PublicPage} from '@/components/ix/public/pages';
export const metadata=publicMetadata('/contact', 'Контакты', 'Справка по доступу и подключению INROU, обзор продукта и условия тарифов. Контакты оператора публикуются после утверждения.');
export default function Page(){return <PublicPage page="contact"/>;}
