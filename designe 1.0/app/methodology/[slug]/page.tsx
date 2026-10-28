import Link from 'next/link';
import {notFound} from 'next/navigation';
import {PublicFrame} from '@/components/ix/public/chrome';
import {Card} from '@/components/ix/ui';
import {methodBySlug} from '@/lib/methodology';
import {publicMetadata} from '@/lib/public-metadata';

type Props = {params: Promise<{slug: string}>};
export async function generateMetadata({params}: Props) {
  const {slug} = await params;
  const method = methodBySlug(slug);
  if (!method) notFound();
  return publicMetadata(`/methodology/${slug}`, method.title, method.description);
}
export default async function MethodPage({params}: Props) {
  const {slug} = await params;
  const method = methodBySlug(slug);
  if (!method) notFound();
  return <PublicFrame><article className="ix-legal"><Link href="/methodology">← Все методики</Link><h1>{method.title}</h1><p className="ix-pub-lead">{method.description}</p><p className="ix-muted ix-mini">Версия: {method.version} · Проверено 26 октября 2026</p>{[['Какие данные нужны', method.inputs], ['Расчёт и условия', method.calculation], ['Ограничения', method.limits], ['Следующий шаг', method.action]].map(([title, text]) => <Card key={title}><h2>{title}</h2><p>{text}</p></Card>)}<p>В самой рекомендации проверяйте источник, период, снимок и версию: они определяют применимость вывода к вашему кабинету.</p><p>Определения источников: <a href="https://yandex.ru/dev/direct/doc/ru/reports/fields-list">поля отчётов Директа</a> и <a href="https://yandex.ru/support/metrica/ru/general/goal">цели Метрики</a>.</p><Link className="ix-btn ix-btn--primary" href="/#product-preview">Посмотреть пример интерфейса</Link></article></PublicFrame>;
}
