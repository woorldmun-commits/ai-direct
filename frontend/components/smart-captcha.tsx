"use client";
import Script from 'next/script';
import { useCallback, useEffect, useRef, useState } from 'react';
import { useNonce } from '@/components/nonce';

type CaptchaApi = {
  render(container: HTMLElement, options: { sitekey: string; hl: string; callback: (token: string) => void }): number;
  destroy(id: number): void;
  subscribe(id: number, event: string, callback: () => void): () => void;
};
declare global { interface Window { smartCaptcha?: CaptchaApi } }

export function SmartCaptcha({ onToken }: { onToken: (token: string) => void }) {
  const nonce = useNonce();
  const container = useRef<HTMLDivElement>(null);
  const widget = useRef<number | undefined>(undefined);
  const unsubscribers = useRef<Array<() => void>>([]);
  const [failed, setFailed] = useState(false);
  const sitekey = process.env.NEXT_PUBLIC_SMARTCAPTCHA_SITE_KEY;
  const render = useCallback(() => {
    if (!sitekey || !container.current || !window.smartCaptcha || widget.current !== undefined) return;
    const sdk = window.smartCaptcha;
    widget.current = sdk.render(container.current, { sitekey, hl: 'ru', callback: onToken });
    unsubscribers.current = [
      sdk.subscribe(widget.current, 'token-expired', () => onToken('')),
      sdk.subscribe(widget.current, 'network-error', () => { onToken(''); setFailed(true); }),
      sdk.subscribe(widget.current, 'javascript-error', () => { onToken(''); setFailed(true); }),
    ];
  }, [sitekey, onToken]);
  useEffect(() => {
    render();
    return () => {
      unsubscribers.current.forEach((unsubscribe) => unsubscribe());
      if (widget.current !== undefined) window.smartCaptcha?.destroy(widget.current);
      widget.current = undefined;
    };
  }, [render]);
  if (!sitekey?.startsWith('ysc1_')) return <p role="alert" className="text-sm text-danger">Проверка от роботов пока недоступна. Обратитесь в поддержку.</p>;
  return <div><Script src="https://smartcaptcha.cloud.yandex.ru/captcha.js?render=onload" nonce={nonce} onReady={render} onError={() => { onToken(''); setFailed(true); }} /><div ref={container} className="min-h-[100px]" />{failed && <p role="alert" className="text-sm text-danger">Не удалось загрузить проверку. Обновите страницу и попробуйте снова.</p>}</div>;
}
