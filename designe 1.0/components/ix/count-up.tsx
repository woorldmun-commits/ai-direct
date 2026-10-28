'use client';
import {useEffect, useRef, type ReactNode} from 'react';

/** Only the decorative copy is interpolated; the canonical value remains unchanged for assistive technology. */
export function CountUp({amount, children, suffix = ''}: {amount: number; children: ReactNode; suffix?: string}) {
  const ref = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    const node = ref.current, media = matchMedia('(prefers-reduced-motion: reduce)');
    if (!node || media.matches || !Number.isFinite(amount) || Math.abs(amount) > Number.MAX_SAFE_INTEGER) return;
    let frame = 0;
    const original = node.textContent;
    let start = 0;
    const finish = () => { cancelAnimationFrame(frame); node.textContent = original; };
    const tick = (now: number) => {
      const progress = Math.min(1, (now - start) / 650);
      node.textContent = new Intl.NumberFormat('ru-RU', {maximumFractionDigits: 0}).format(Math.round(amount * (1 - (1 - progress) ** 3))) + suffix;
      if (progress < 1) frame = requestAnimationFrame(tick); else finish();
    };
    const observer = new IntersectionObserver(entries => { if (!media.matches && entries.some(e => e.isIntersecting)) { start = performance.now(); frame = requestAnimationFrame(tick); observer.disconnect(); } });
    const reduced = () => { observer.disconnect(); finish(); };
    observer.observe(node); media.addEventListener('change', reduced);
    return () => { observer.disconnect(); media.removeEventListener('change', reduced); cancelAnimationFrame(frame); };
  }, [amount, suffix]);
  return <><span className="sr-only-ix">{children}</span><span aria-hidden="true" ref={ref}>{children}</span></>;
}
