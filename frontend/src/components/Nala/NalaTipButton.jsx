import { HelpCircle } from "lucide-react";
import { useNala } from "../../context/NalaContext";
import "./NalaTipButton.css";

export default function NalaTipButton({ query, ariaLabel = "Pregúntale a Nala" }) {
  const { askNala } = useNala();

  return (
    <button
      type="button"
      className="nala-tip-btn"
      aria-label={ariaLabel}
      onClick={(e) => {
        e.stopPropagation();
        askNala(query);
      }}
    >
      <HelpCircle size={16} />
      <span className="nala-tip-tooltip">PREGÚNTALE A NALA</span>
    </button>
  );
}
