'use client';
import {useEffect} from 'react';

export function SectionMotion() {
  useEffect(() => {
    const media = matchMedia('(prefers-reduced-motion: reduce)');
    if (media.matches) return;
    const animations: Animation[] = [];
    const observer = new IntersectionObserver(entries => {
      for (const entry of entries) if (entry.isIntersecting) {
        animations.push(entry.target.animate([{opacity: 0, transform: 'translateY(16px)'}, {opacity: 1, transform: 'translateY(0)'}], {duration: 560, easing: 'cubic-bezier(.22,1,.36,1)'}));
        observer.unobserve(entry.target);
      }
    }, {threshold: .08});
    document.querySelectorAll('.ix-pub main>section').forEach(node => { if (node.getBoundingClientRect().top >= innerHeight) observer.observe(node); });
    const cancel = () => { observer.disconnect(); animations.forEach(a => a.cancel()); };
    media.addEventListener('change', cancel);
    return () => { cancel(); media.removeEventListener('change', cancel); };
  }, []);
  return null;
}
