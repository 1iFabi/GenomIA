import { useEffect, useRef } from "react";
import gsap from "gsap";
import { useGSAP } from "@gsap/react";
import "./GenominMascot.css";

gsap.registerPlugin(useGSAP);

const POSES = {
  entrance: "asomandose",
  idle: "saludando",
  hover: "guino_saludo",
  open: "apuntando",
  typing: "laptop",
  notFound: "pensando",
  found: "celebrando",
  sleep: "durmiendo",
};

const poseSrc = (name) => `${import.meta.env.BASE_URL}genomin/${name}.webp`;

// `pose` names a file in public/genomin directly, for callers that pick their own pose instead of a state
export default function GenominMascot({ state = "idle", pose, size = 96 }) {
  const root = useRef(null);
  const name = pose || POSES[state];
  const sleeping = state === "sleep";

  // Precarga las poses para que el cambio no parpadee mientras baja la imagen
  useEffect(() => {
    Object.values(POSES).forEach((n) => {
      new Image().src = poseSrc(n);
    });
  }, []);

  useGSAP(
    () => {
      const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
      if (reduce || sleeping) return;
      gsap.to(root.current, { y: -4, duration: 1.2, ease: "sine.inOut", yoyo: true, repeat: -1 });
    },
    { scope: root, dependencies: [sleeping], revertOnUpdate: true }
  );

  useGSAP(
    () => {
      const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
      gsap.fromTo(
        "img",
        { opacity: 0, scale: reduce ? 1 : 0.8, rotate: reduce ? 0 : -6 },
        { opacity: 1, scale: 1, rotate: 0, duration: reduce ? 0.2 : 0.5, ease: "back.out(2)" }
      );
    },
    { scope: root, dependencies: [name] }
  );

  return (
    <span ref={root} className="genomin-mascot" style={{ width: size, height: size }} aria-hidden>
      <img key={name} src={poseSrc(name)} alt="" width={size} height={size} draggable={false} />
    </span>
  );
}
