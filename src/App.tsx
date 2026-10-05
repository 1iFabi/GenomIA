import './index.css';

function EnrollButton({ className = '' }: { className?: string }) {
  return (
    <button className={`enroll-button ${className}`} type="button">
      INSCRIBIRSE
    </button>
  );
}

export default function App() {
  return (
    <main className="genomia-page relative h-full w-full overflow-hidden" aria-label="GenomIA">
      <section className="genomia-hero" aria-labelledby="hero-title">
        <video className="hero-video" autoPlay muted loop playsInline preload="auto" aria-hidden="true" tabIndex={-1}>
          <source
            src="https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260613_180732_a54afbf6-b30d-470e-861f-669871f09f67.mp4"
            type="video/mp4"
          />
        </video>
        <div className="hero-shade" aria-hidden="true" />
        <div className="hero-atmosphere" aria-hidden="true" />

        <header className="topbar">
          <a className="brand-lockup" href="/" aria-label="GenomIA, inicio">
            <img className="brand-mark" src="/manus-storage/cSolido_6e7ee4e3.png" alt="Logo GenomIA" />
          </a>
          <span className="about-link">QUIENES SOMOS.</span>
        </header>

        <div className="hero-content">
          <h1 id="hero-title" className="hero-title">
            <span className="title-line title-line--brand text-glow">GenomIA:</span>
            <span className="title-line title-line--subtitle">Descubre la historia que tu</span>
            <span className="title-line title-line--subtitle">ADN tiene para contarte</span>
          </h1>
          <EnrollButton className="enroll-button--hero" />
        </div>

        <span className="hero-horizon" aria-hidden="true" />
      </section>
    </main>
  );
}
