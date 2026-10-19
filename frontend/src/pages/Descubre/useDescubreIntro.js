import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { useGSAP } from "@gsap/react";

gsap.registerPlugin(ScrollTrigger, useGSAP);

/**
 * The section's one entrance: the header settles, then the cards follow in reading order.
 * Everything is visible without it: remove the call in Descubre.jsx and the section is complete and still.
 * It runs once, on scroll into view, and never blocks input.
 */
export default function useDescubreIntro(scope) {
  useGSAP(() => {
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;
    const tl = gsap.timeline({ scrollTrigger: { trigger: scope.current, start: "top 75%", once: true } });
    tl.from(".descubre-header > *", { y: 18, opacity: 0, filter: "blur(6px)", duration: 0.8, ease: "expo.out", stagger: 0.08 })
      .from(".dcard", { y: 28, opacity: 0, duration: 0.9, ease: "expo.out", stagger: 0.09 }, "-=0.45");
  }, { scope });
}
