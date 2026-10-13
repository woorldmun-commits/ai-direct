"use client";

import { useEffect } from "react";
import { usePathname } from "next/navigation";

export function PageMotion() {
  const path = usePathname();
  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const main = document.getElementById("main-content");
    const animation = main?.animate([{ opacity: .65, transform: "translateY(8px)" }, { opacity: 1, transform: "translateY(0)" }], { duration: 320, easing: "cubic-bezier(.2,.8,.2,1)" });
    return () => animation?.cancel();
  }, [path]);
  return null;
}
