    import "./Loader.css";
    
    export default function Loader({ label = "Cargando…" }) {
      return (
        <div className="loader" role="status" aria-live="polite">
          <div className="loader-spinner" aria-hidden="true" />
          <span className="loader-label">{label}</span>
        </div>
      );
    }
