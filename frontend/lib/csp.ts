export function buildCsp(nonce: string, development = false, captcha = false): string {
  if (!/^[A-Za-z0-9+/=_-]+$/.test(nonce)) throw new Error('Invalid CSP nonce');
  const captchaOrigin = captcha ? ' https://smartcaptcha.cloud.yandex.ru https://smartcaptcha.yandexcloud.net' : '';
  return [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${development ? " 'unsafe-eval'" : ''}${captchaOrigin}`,
    `style-src 'self' 'nonce-${nonce}'${development ? " 'unsafe-inline'" : ''}`,
    "style-src-attr 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "font-src 'self'",
    `connect-src 'self'${development ? ' ws: wss:' : ''}${captchaOrigin}`,
    `frame-src ${captcha ? captchaOrigin.trim() : "'none'"}`,
    "object-src 'none'", "base-uri 'self'", "form-action 'self'", "frame-ancestors 'none'",
  ].join('; ');
}
