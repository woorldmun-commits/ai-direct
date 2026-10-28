import type {Metadata} from 'next';

export function publicMetadata(path: string, title: string, description: string): Metadata {
  const socialTitle = `${title} — INROU`;
  return {title, description, alternates: {canonical: path},
    openGraph: {type: 'website', locale: 'ru_RU', siteName: 'INROU', url: path,
      title: socialTitle, description, images: [{url: '/social-preview.png', alt: 'INROU — контроль рекламных расходов'}]},
    twitter: {card: 'summary_large_image', title: socialTitle, description, images: ['/social-preview.png']}};
}
