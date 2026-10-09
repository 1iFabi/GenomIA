import { useLayoutEffect, useRef } from "react";
import { prefersStill } from "../../lib/utils";
import "./AuthPlate.css";

// One <video> for the whole app, created on first use and never recreated. Login and
// Register both render this plate; the live element moves into whichever page is
// mounting, so the loop keeps playing across the exchange with no reload, no poster
// swap and no seek back to a saved time.
let sharedVideo = null;

const getSharedVideo = () => {
  if (sharedVideo) return sharedVideo;
  const video = document.createElement("video");
  video.className = "auth-plate__media";
  video.loop = true;
  video.muted = true;
  video.playsInline = true;
  video.preload = "auto";
  video.poster = "/GenomIA_login_loop_poster.jpg";
  video.setAttribute("aria-hidden", "true");
  // WebM (VP9, 2160×2880) first; MP4 fallback for Safari without VP9.
  for (const [src, type] of [
    ["/GenomIA_login_loop.webm", "video/webm"],
    ["/GenomIA_login_loop.mp4", "video/mp4"],
  ]) {
    const source = document.createElement("source");
    source.src = src;
    source.type = type;
    video.appendChild(source);
  }
  sharedVideo = video;
  return video;
};

// Placa de arte compartida por Login y Register: es lo que cruza la pantalla en el
// swap, así que su contenido es idéntico en ambas páginas.
export default function AuthPlate() {
  const slotRef = useRef(null);

  useLayoutEffect(() => {
    const video = getSharedVideo();
    slotRef.current.appendChild(video);
    if (!prefersStill() && video.paused) video.play().catch(() => {});
  }, []);

  return (
    <div className="auth-plate">
      <div className="auth-plate__slot" ref={slotRef} />
      <div className="auth-plate__caption">
        <p className="auth-plate__title">
          Tu historia, escrita en tu <span className="auth-plate__accent">ADN</span>.
        </p>
        <p className="auth-plate__lede">Descubre lo que tus genes cuentan sobre ti.</p>
      </div>
    </div>
  );
}
