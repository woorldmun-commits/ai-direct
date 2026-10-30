import Link from 'next/link';
import {CookieSettingsButton} from '@/components/cookie-banner';
import {ThemeControl} from '@/components/theme-control';

export function FooterMeta() {
  return <div className="inrou-footer-meta"><span>© INROU</span><Link href="/legal/privacy">Конфиденциальность</Link><CookieSettingsButton/><ThemeControl/></div>;
}
