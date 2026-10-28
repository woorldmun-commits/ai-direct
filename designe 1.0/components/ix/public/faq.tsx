'use client';
import {useId, useState} from 'react';

export function FaqSearch({items}: {items: [string, string][]}) {
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState('Все вопросы');
  const id = useId();
  const categories = ['Все вопросы', 'Подключение', 'Данные и безопасность', 'Тарифы и оплата'];
  const group = (index: number) => index === 2 || index === 3 ? 'Подключение' : index === 4 || index === 1 ? 'Данные и безопасность' : index >= 5 ? 'Тарифы и оплата' : 'Все вопросы';
  const shown = items.filter(([question, answer], index) => (category === 'Все вопросы' || group(index) === category) && `${question} ${answer}`.toLocaleLowerCase('ru').includes(query.trim().toLocaleLowerCase('ru')));
  return <div className="ix-faq-layout"><div className="ix-faq-search"><label htmlFor={id} className="sr-only-ix">Поиск по вопросам</label><input id={id} className="ix-field" type="search" placeholder="Поиск по вопросам…" value={query} onChange={event => setQuery(event.target.value)} /></div><nav aria-label="Категории вопросов">{categories.map(item => <button key={item} type="button" className="ix-pill" aria-pressed={category === item} onClick={() => setCategory(item)}>{item}</button>)}</nav><div className="ix-pub-faq"><p className="sr-only-ix" role="status">Найдено вопросов: {shown.length}</p>{shown.map(([question, answer]) => <details key={question}><summary>{question}</summary><p>{answer}</p></details>)}{!shown.length && <p className="ix-muted">Вопросы не найдены. Измените запрос или категорию.</p>}</div></div>;
}
