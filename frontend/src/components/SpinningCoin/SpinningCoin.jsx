import React from "react";
import "./SpinningCoin.css";

export default function SpinningCoin({
  src = "/cNormal.png",
  size = 60, // px por defecto; también acepta valores CSS como "clamp(56px, 12vw, 72px)"
  thickness = 8,
  speed = "6s",
  alt = "Genomia logo",
  variant = "flat", // "flat" (sin canto, flip espejado) o "3d" (rotación 3D)
}) {
  const sizeValue = typeof size === "number" ? `${size}px` : size;
  const edgeWidth = typeof thickness === "number" ? `${thickness}px` : thickness;
  const isFlat = variant === "flat";

  return (
    <div className="coin-scene" style={{ width: sizeValue, height: sizeValue }}>
      <div className={`coin ${isFlat ? "coin--flat" : "coin--3d"}`} style={{ animationDuration: speed }}>
        {/* Cara frontal */}
        <img className="coin-face coin-front" src={src} alt={alt} />
        {/* Cara trasera y canto solo para 3D */}
        {!isFlat && (
          <>
            <img className="coin-face coin-back" src={src} alt={alt} />
            <div className="coin-edge" style={{ width: edgeWidth }} />
          </>
        )}
      </div>
    </div>
  );
}
