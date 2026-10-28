import Link from 'next/link';
import {PublicFrame} from '@/components/ix/public/chrome';
import {Card} from '@/components/ix/ui';
import {METHODS} from '@/lib/methodology';
import {publicMetadata} from '@/lib/public-metadata';

export const metadata = publicMetadata('/methodology', 'Методики рекомендаций', 'Три правила INROU: кампания без конверсий, высокий CPA и площадки без конверсий. Источники, расчёты, достаточность и ограничения.');

export default function Methodology() {
  return <PublicFrame><h1>Как проверяются рекомендации</h1><p className="ix-pub-lead">Источник, период, расчёт и ограничения — до принятия решения.</p><div className="ix-pub-cols">{Object.entries(METHODS).map(([slug, method]) => <Card key={slug}><h2>{method.title}</h2><p>{method.description}</p><Link href={`/methodology/${slug}`}>Открыть методику →</Link></Card>)}</div><p className="ix-muted">Параметры привязаны к версии правила. Ни одно правило не гарантирует экономию или отсутствие других проблем. Данные Директа и Метрики подключаются отдельно; изменения рекламы выполняет человек.</p></PublicFrame>;
}
