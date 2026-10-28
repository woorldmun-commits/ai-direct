import {publicMetadata} from '@/lib/public-metadata';
import {PublicPage} from '@/components/ix/public/pages';
export const metadata=publicMetadata('/about', 'О компании', 'INROU — независимый сервис контроля рекламных расходов. Источник, период, формула и ограничения помогают принимать решения. Не аффилирован с Яндексом.');
export default function Page(){return <PublicPage page="about"/>;}
