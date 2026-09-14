import { useEffect, useRef, useState } from 'react';
import { motion as Motion, useMotionValue, useReducedMotion, useSpring } from 'motion/react';
import './TiltedCard.css';

const springValues = {
  damping: 30,
  stiffness: 100,
  mass: 2
};

const resetMotionValue = (motionValue, value) => {
  if (typeof motionValue.jump === 'function') {
    motionValue.jump(value);
  } else {
    motionValue.set(value);
  }
};

export default function TiltedCard({
  imageSrc,
  altText = 'Tilted card image',
  captionText = '',
  containerHeight = '300px',
  containerWidth = '100%',
  imageHeight = '300px',
  imageWidth = '300px',
  scaleOnHover = 1.1,
  rotateAmplitude = 14,
  showMobileWarning = true,
  showTooltip = true,
  overlayContent = null,
  displayOverlayContent = false
}) {
  const ref = useRef(null);
  const shouldReduceMotion = useReducedMotion() === true;

  const x = useMotionValue();
  const y = useMotionValue();
  const rotateX = useSpring(useMotionValue(0), springValues);
  const rotateY = useSpring(useMotionValue(0), springValues);
  const scale = useSpring(1, springValues);
  const opacity = useSpring(0);
  const rotateFigcaption = useSpring(0, {
    stiffness: 350,
    damping: 30,
    mass: 1
  });

  const [lastY, setLastY] = useState(0);

  useEffect(() => {
    if (!shouldReduceMotion) return;

    resetMotionValue(x, 0);
    resetMotionValue(y, 0);
    resetMotionValue(rotateX, 0);
    resetMotionValue(rotateY, 0);
    resetMotionValue(scale, 1);
    resetMotionValue(opacity, 0);
    resetMotionValue(rotateFigcaption, 0);
    setLastY(0);
  }, [opacity, rotateFigcaption, rotateX, rotateY, scale, shouldReduceMotion, x, y]);

  function handleMouse(e) {
    if (shouldReduceMotion || !ref.current) return;

    const rect = ref.current.getBoundingClientRect();
    const offsetX = e.clientX - rect.left - rect.width / 2;
    const offsetY = e.clientY - rect.top - rect.height / 2;

    const rotationX = (offsetY / (rect.height / 2)) * -rotateAmplitude;
    const rotationY = (offsetX / (rect.width / 2)) * rotateAmplitude;

    rotateX.set(rotationX);
    rotateY.set(rotationY);

    x.set(e.clientX - rect.left);
    y.set(e.clientY - rect.top);

    const velocityY = offsetY - lastY;
    rotateFigcaption.set(-velocityY * 0.6);
    setLastY(offsetY);
  }

  function handleMouseEnter() {
    if (shouldReduceMotion) return;

    scale.set(scaleOnHover);
    opacity.set(1);
  }

  function handleMouseLeave() {
    if (shouldReduceMotion) return;

    opacity.set(0);
    scale.set(1);
    rotateX.set(0);
    rotateY.set(0);
    rotateFigcaption.set(0);
  }

  return (
    <figure
      ref={ref}
      className="tilted-card-figure"
      style={{
        height: containerHeight,
        width: containerWidth
      }}
      onMouseMove={handleMouse}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      {showMobileWarning && (
        <div className="tilted-card-mobile-alert">This effect is not optimized for mobile. Check on desktop.</div>
      )}

      <Motion.div
        className="tilted-card-inner"
        style={{
          width: imageWidth,
          height: imageHeight,
          rotateX,
          rotateY,
          scale
        }}
      >
        <Motion.img
          src={imageSrc}
          alt={altText}
          className="tilted-card-img"
          style={{
            width: imageWidth,
            height: imageHeight
          }}
        />

        {displayOverlayContent && overlayContent && (
          <Motion.div className="tilted-card-overlay">{overlayContent}</Motion.div>
        )}
      </Motion.div>

      {showTooltip && (
        <Motion.figcaption
          className="tilted-card-caption"
          style={{
            x,
            y,
            opacity,
            rotate: rotateFigcaption
          }}
        >
          {captionText}
        </Motion.figcaption>
      )}
    </figure>
  );
}
