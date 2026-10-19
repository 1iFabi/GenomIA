import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { useGSAP } from "@gsap/react";

gsap.registerPlugin(ScrollTrigger, useGSAP);

const BASES = "ACGT";

/**
 * Like Descubre, nothing shows before the reader scrolls to it: each block waits for its own
 * scroll point. 1) breadcrumb + 3D stage, 2) the package sheet (its rules draw left to right,
 * rows follow, the price decodes from DNA bases).
 * Motion settles without overshoot (expo.out, no bounce): nothing here was thrown by the user.
 * Reduced motion keeps the same scroll points but only cross-fades, and the price shows settled.
 * Remove the call in GenomaPricing.jsx and the section is complete and still.
 */
export default function usePricingIntro(scope) {
  useGSAP(() => {
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    const enter = (y, blur) =>
      reduce ? { opacity: 0, duration: 0.35, ease: "power1.out" } : { y, opacity: 0, filter: `blur(${blur}px)`, duration: 0.8, ease: "expo.out" };
    const at = (trigger, start = "top 80%") => gsap.timeline({ scrollTrigger: { trigger, start, once: true } });

    at(scope.current, "top 75%").from([".gp-container > .breadcrumb", ".gp-stage"], { ...enter(18, 6), stagger: 0.08 });

    const digits = [...scope.current.querySelectorAll(".gp-digit")];
    const settle = (el) => {
      el.textContent = el.dataset.d;
      el.classList.remove("is-decoding");
    };

    const sheet = at(".gp-pkg")
      .from(".gp-pkg__head", reduce ? enter() : { clipPath: "inset(0 100% 0 0)", duration: 0.9, ease: "expo.out" })
      .from([".gp-pkg__desc", ".gp-pkg__list li", ".gp-cta"], { ...enter(10, 4), stagger: reduce ? 0 : 0.05 }, reduce ? 0 : "-=0.55");

    if (!reduce) {
      digits.forEach((el, i) => {
        el.textContent = BASES[i % 4];
        el.classList.add("is-decoding");
      });
      sheet.addLabel("decode", 0.2);
      digits.forEach((el, i) => {
        let step = -1;
        sheet.to({}, {
          duration: 0.5 + i * 0.11,
          onUpdate() {
            const next = Math.floor(this.time() * 16); // ~16 base swaps a second
            if (next === step) return;
            step = next;
            el.textContent = BASES[(next + i) % 4];
          },
          onComplete: () => settle(el),
        }, "decode");
      });
    }
    // a timeline killed mid-decode (unmount, StrictMode) must not leave bases in the price
    return () => digits.forEach(settle);
  }, { scope });
}
