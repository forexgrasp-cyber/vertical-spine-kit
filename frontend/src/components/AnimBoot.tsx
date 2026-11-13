"use client";

import { useEffect } from "react";

/**
 * Loads the shared animation bundle once per page: anim.css, topic.css
 * (per-project motif, optional), the GSAP runtime, then anim.js -- in that
 * order, so anim.js never runs before its dependencies.
 *
 * Idempotent: a flag on <html> prevents double injection (StrictMode/HMR
 * remounts). Assets are page-lifetime, so there is no teardown.
 */
export default function AnimBoot() {
  useEffect(() => {
    const root = document.documentElement;
    if (root.dataset.animBoot === "1") return;
    root.dataset.animBoot = "1";
    const prefix = "";

    const addCss = (href: string) => {
      const l = document.createElement("link");
      l.rel = "stylesheet";
      l.href = href;
      document.head.appendChild(l);
      return l;
    };
    addCss(prefix + "/anim/anim.css");
    const topic = addCss(prefix + "/anim/topic.css");
    topic.onerror = () => topic.remove(); // motif CSS is optional

    const load = (src: string) =>
      new Promise<void>((resolve) => {
        const s = document.createElement("script");
        s.src = src;
        s.async = false; // preserve execution order
        s.onload = () => resolve();
        s.onerror = () => resolve(); // never block the bundle on a CDN miss
        document.head.appendChild(s);
      });

    (async () => {
      await load("https://unpkg.com/gsap@3.12/dist/gsap.min.js");
      await load("https://unpkg.com/gsap@3.12/dist/ScrollTrigger.min.js");
      await load(prefix + "/anim/anim.js");
    })();
  }, []);
  return null;
}
