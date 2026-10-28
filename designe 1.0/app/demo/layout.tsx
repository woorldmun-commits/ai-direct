import type {Metadata} from 'next';
import {notFound} from 'next/navigation';
import type {ReactNode} from 'react';
import {DemoProvider} from '@/components/ix/demo-store';

// Демонстрационный режим: синтетические данные из утверждённого прототипа, закрыт от индексации.
// Публичный демо-кабинет выведен из эксплуатации (аудит запуска): по умолчанию маршрут отдаёт 404.
// INROU_DEMO=1 — только локальная проверка или явно обозначенный staging; не включать на основном продукте.
export const metadata: Metadata = {title: 'Демонстрационный кабинет', robots: {index: false, follow: false}};

export default function DemoLayout({children}: {children: ReactNode}) {
  if (process.env.INROU_DEMO !== '1') notFound();
  return <DemoProvider>{children}</DemoProvider>;
}
