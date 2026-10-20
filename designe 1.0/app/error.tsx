"use client";
import Link from 'next/link';
export default function ErrorPage({reset}:{reset:()=>void}){return <main className="mc-error-page"><span>Ошибка загрузки</span><h1>Не удалось открыть страницу</h1><p>Попробуйте загрузить её повторно. Если ошибка сохраняется, обратитесь к администратору.</p><div><button onClick={reset} className="ref-button ref-primary">Повторить</button><Link href="/" className="ref-button">На главную</Link></div></main>;}
