"use client";

import { motion, useInView, useReducedMotion } from "motion/react";
import { ArrowRight } from "lucide-react";
import Link from "next/link";
import { useRef, type CSSProperties } from "react";
import styles from "./prisma-hero.module.css";

interface WordsPullUpProps {
  text: string;
  className?: string;
  showAsterisk?: boolean;
  style?: CSSProperties;
}

export function WordsPullUp({ text, className = "", showAsterisk = false, style }: WordsPullUpProps) {
  const ref = useRef<HTMLSpanElement>(null);
  const isInView = useInView(ref, { once: true });
  const reducedMotion = useReducedMotion();
  const words = text.split(" ");

  return (
    <span ref={ref} className={`${styles.words} ${className}`} style={style}>
      {words.map((word, i) => (
        <motion.span
          key={`${word}-${i}`}
          initial={reducedMotion !== false ? false : { y: 20, opacity: 0 }}
          animate={isInView ? { y: 0, opacity: 1 } : {}}
          transition={{ duration: reducedMotion ? 0 : 0.6, delay: reducedMotion ? 0 : i * 0.08, ease: [0.16, 1, 0.3, 1] }}
          className={styles.word}
          style={{ marginRight: i === words.length - 1 ? 0 : "0.25em" }}
        >
          {word}
          {showAsterisk && i === words.length - 1 && <span aria-hidden="true" className={styles.asterisk}>*</span>}
        </motion.span>
      ))}
    </span>
  );
}

const navItems = [
  { label: "Возможности", href: "/#features" },
  { label: "Как работает", href: "/#how" },
  { label: "Демо", href: "/demo" },
  { label: "Войти", href: "/login" },
];

export function PrismaHero() {
  const reducedMotion = useReducedMotion();

  function toggleVideo(video: HTMLVideoElement) {
    if (video.paused) {
      void video.play().catch(() => {});
    } else {
      video.pause();
    }
  }

  return (
    <section className={styles.hero} aria-labelledby="prisma-hero-title">
      <div className={styles.frame}>
        <video
          autoPlay
          loop
          muted
          playsInline
          preload="metadata"
          role="button"
          tabIndex={0}
          title="Нажмите на фон, чтобы остановить или продолжить видео"
          aria-label="Фоновое видео. Нажмите на фон или клавишу пробел либо Enter, чтобы остановить или продолжить."
          onClick={(event) => toggleVideo(event.currentTarget)}
          onKeyDown={(event) => {
            if (event.code !== "Space" && event.key !== "Enter") return;
            event.preventDefault();
            if (event.repeat) return;
            toggleVideo(event.currentTarget);
          }}
          className={styles.video}
          src="https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260405_170732_8a9ccda6-5cff-4628-b164-059c500a2b41.mp4"
        />
        <div aria-hidden="true" className={styles.noise} />
        <div aria-hidden="true" className={styles.shade} />

        <nav className={styles.nav} aria-label="Навигация Rekvero">
          {navItems.map(({ label, href }) => <Link key={href} href={href}>{label}</Link>)}
        </nav>

        <div className={styles.content}>
          <h1 id="prisma-hero-title" className={styles.title}><WordsPullUp text="Rekvero" showAsterisk /></h1>
          <div className={styles.details}>
            <h2>Узнайте, куда уходит рекламный бюджет.</h2>
            <motion.p
              initial={reducedMotion !== false ? false : { y: 20, opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              transition={{ duration: reducedMotion ? 0 : 0.8, delay: reducedMotion ? 0 : 0.5, ease: [0.16, 1, 0.3, 1] }}
            >
              Rekvero проверяет Яндекс Директ и Метрику: расход без конверсий, CPA выше цели и площадки РСЯ. Вы видите сумму, причину и данные для решения.
            </motion.p>
            <motion.div
              initial={reducedMotion !== false ? false : { y: 20, opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              transition={{ duration: reducedMotion ? 0 : 0.8, delay: reducedMotion ? 0 : 0.7, ease: [0.16, 1, 0.3, 1] }}
            >
              <Link href="/signup" className={styles.cta}>
                Проверить аккаунт бесплатно
                <span><ArrowRight size={18} aria-hidden="true" /></span>
              </Link>
              <Link href="/demo" className={styles.demo}>Посмотреть демо <ArrowRight size={16} aria-hidden="true" /></Link>
            </motion.div>
            <small>Первый аудит бесплатно. Без карты.</small>
          </div>
        </div>
      </div>
    </section>
  );
}
