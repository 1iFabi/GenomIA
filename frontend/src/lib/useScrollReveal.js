import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { useGSAP } from "@gsap/react";

gsap.registerPlugin(ScrollTrigger, useGSAP);

// The landing's sections load lazily and their images arrive late, so the page keeps growing after
// every trigger measured its start. Re-measure whenever the page height settles, or a section further
// down would reveal before the reader gets there.
if (typeof window !== "undefined" && typeof ResizeObserver !== "undefined") {
  let id;
  new ResizeObserver(() => {
    clearTimeout(id);
    id = setTimeout(() => ScrollTrigger.refresh(), 150);
  }).observe(document.body);
}

/**
 * Every [data-reveal] inside scope stays hidden until its own top reaches 85% of the viewport,
 * then settles in like Descubre's header; elements arriving together follow in reading order.
 * Motion settles without overshoot. Reduced motion keeps the scroll points but only cross-fades.
 * Elements rendered later (e.g. "Ver más preguntas") are simply visible.
 */
export default function useScrollReveal(scope) {
  useGSAP(() => {
    const els = gsap.utils.toArray("[data-reveal]", scope.current);
    if (!els.length) return;
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    gsap.set(els, reduce ? { opacity: 0 } : { opacity: 0, y: 18, filter: "blur(6px)" });
    ScrollTrigger.batch(els, {
      start: "top 85%",
      once: true,
      onEnter: (batch) =>
        gsap.to(batch, {
          opacity: 1,
          y: 0,
          filter: "blur(0px)",
          duration: reduce ? 0.35 : 0.8,
          ease: reduce ? "power1.out" : "expo.out",
          stagger: reduce ? 0 : 0.08,
          clearProps: "transform,filter", // a leftover transform would trap fixed children and hover lifts
        }),
    });
  }, { scope });
}
