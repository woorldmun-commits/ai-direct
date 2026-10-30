export type PublicStart = {registrationReady: boolean; contactEmail: string | null; href: string; label: string};

export function publicStart(registrationReady: boolean, rawContact = ''): PublicStart {
  const email = rawContact.trim();
  const contactEmail = email.length <= 254 && /^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,63}$/.test(email)
    && email.split('@')[1].split('.').every(label=>/^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$/.test(label)) ? email : null;
  return {registrationReady, contactEmail,
    href: registrationReady ? '/signup' : contactEmail ? `mailto:${encodeURIComponent(contactEmail)}` : '/#product-preview',
    label: registrationReady ? 'Начать с 7 дней бесплатно' : contactEmail ? 'Обсудить подключение' : 'Посмотреть демо'};
}

export const DEFAULT_PUBLIC_START = publicStart(false);
