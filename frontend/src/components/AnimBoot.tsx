"use client";

import { useEffect } from "react";

/** Injects /anim/anim.css + GSAP CDN + /anim/anim.js once. Mount on landing pages only. */
export default function AnimBoot() {
  useEffect(() => {
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = "/anim/anim.css";
    document.head.appendChild(link);
    const load = (src: string) =>
      new Promise<void>((resolve) => {
        const s = document.createElement("script");
        s.src = src;
        s.onload = () => resolve();
        s.onerror = () => resolve();
        document.head.appendChild(s);
      });
    (async () => {
      await load("https://unpkg.com/gsap@3.12/dist/gsap.min.js");
      await load("https://unpkg.com/gsap@3.12/dist/ScrollTrigger.min.js");
      await load("/anim/anim.js");
    })();
    return () => {
      if (link.parentNode) link.parentNode.removeChild(link);
    };
  }, []);
  return null;
}
