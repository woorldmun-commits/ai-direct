import Link from 'next/link';
export default function NotFound(){return <main className="mc-error-page"><span>404</span><h1>Эта страница не найдена</h1><p>Проверьте адрес или перейдите к главной странице inrou.</p><Link href="/" className="ref-button ref-primary">На главную</Link></main>;}
