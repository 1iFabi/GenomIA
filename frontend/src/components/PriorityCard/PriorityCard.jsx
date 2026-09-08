import { useState } from "react";
import { ChevronDown, AlertCircle, AlertTriangle, Info } from "lucide-react";
import { cn } from "../../lib/utils";
import GeneticTraitBar from "../GeneticTraitBar/GeneticTraitBar";
import "./PriorityCard.css";

const priorityConfig = {
  high: {
    icon: AlertCircle,
    bgColor: "bg-red-50",
    borderColor: "border-red-200",
    accentColor: "text-red-600",
    iconBgColor: "bg-red-100",
  },
  medium: {
    icon: AlertTriangle,
    bgColor: "bg-yellow-50",
    borderColor: "border-yellow-200",
    accentColor: "text-yellow-600",
    iconBgColor: "bg-yellow-100",
  },
  low: {
    icon: Info,
    bgColor: "bg-blue-50",
    borderColor: "border-blue-200",
    accentColor: "text-blue-600",
    iconBgColor: "bg-blue-100",
  },
};

const impactColors = {
  high: "#8b5cf6",
  medium: "#06b6d4",
  low: "#f59e0b",
};

const impactLabels = {
  high: "Alto",
  medium: "Medio",
  low: "Bajo",
};

const PriorityCard = ({ level, title, diseases }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const config = priorityConfig[level];
  const Icon = config.icon;

  return (
    <div
      className={cn(
        "rounded-2xl border-2 overflow-hidden transition-all duration-300 hover:shadow-lg",
        config.bgColor,
        config.borderColor
      )}
    >
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full p-6 flex items-center justify-between hover:opacity-80 transition-opacity"
      >
        <div className="flex items-center gap-3">
          <div className={cn("p-2 rounded-lg", config.iconBgColor)}>
            <Icon className={cn("w-5 h-5", config.accentColor)} />
          </div>
          <div className="text-left">
            <h2 className={cn("text-lg font-semibold", config.accentColor)}>{title}</h2>
            <p className={cn("text-sm", config.accentColor, "opacity-70")}>
              {diseases.length} {diseases.length === 1 ? "enfermedad" : "enfermedades"}
            </p>
          </div>
        </div>
        <ChevronDown
          className={cn(
            "w-5 h-5 transition-transform duration-300",
            config.accentColor,
            isExpanded && "rotate-180"
          )}
        />
      </button>

      {isExpanded && (
        <div className="px-6 pb-4 space-y-2 max-h-[calc(100vh-300px)] overflow-y-auto">
          {diseases.length > 0 ? (
            diseases.map((disease, index) => {
              const magnitude = Number(disease.magnitud_efecto);
              const hasMagnitude = Number.isFinite(magnitude) && magnitude > 0;
              const percentage = hasMagnitude
                ? Math.min(100, Math.round((magnitude / 5) * 100))
                : level === "high"
                  ? 80
                  : level === "medium"
                    ? 55
                    : 30;
              return (
                <GeneticTraitBar
                  key={disease.id}
                  title={disease.title}
                  rsid={disease.rsId || disease.rsid}
                  genotype={disease.genotype}
                  percentage={percentage}
                  impactLabel={impactLabels[level] || "Bajo"}
                  impactColor={impactColors[level] || "#64748b"}
                  details={{
                    cromosoma: disease.cromosoma || "N/A",
                    posicion: disease.posicion || "N/A",
                    categoria: "Enfermedades",
                    magnitud: hasMagnitude ? magnitude.toFixed(2) : "N/A",
                  }}
                  freqChile={disease.freq_chile_percent}
                  explanation={disease.description || "Sin descripcion disponible."}
                  delay={index * 50}
                />
              );
            })
          ) : (
            <p className="text-center text-gray-500 py-4">No hay enfermedades en esta categoría</p>
          )}
        </div>
      )}
    </div>
  );
};

export default PriorityCard;
