import { useState, useEffect } from 'react';
import { HelpCircle } from 'lucide-react';
import Tooltip from '../Tooltip/Tooltip';
import { AnimatedCircularProgressBar } from "@/components/ui/animated-circular-progress-bar";
import '../../styles/cards.css';

export default function CircularProgress({ score }) {
  const [animatedScore, setAnimatedScore] = useState(0);

  useEffect(() => {
    const timer = setTimeout(() => {
      setAnimatedScore(score);
    }, 100);

    return () => clearTimeout(timer);
  }, [score]);

  const getScoreData = () => {
    if (score < 20) return { hexColor: '#10B981', textColor: 'text-emerald-500', level: 'Riesgo muy bajo' };
    if (score < 40) return { hexColor: '#0EA5E9', textColor: 'text-sky-500', level: 'Riesgo bajo' };
    if (score < 60) return { hexColor: '#F59E0B', textColor: 'text-amber-500', level: 'Riesgo moderado' };
    if (score < 80) return { hexColor: '#F97316', textColor: 'text-orange-500', level: 'Riesgo elevado' };
    return { hexColor: '#EF4444', textColor: 'text-red-500', level: 'Riesgo alto' };
  };

  const { hexColor, textColor, level } = getScoreData();

  const getDescription = (level) => {
    switch (level) {
      case 'Riesgo muy bajo':
        return 'Tu perfil genético muestra una predisposición muy favorable frente a las variantes analizadas.';
      case 'Riesgo bajo':
        return 'Tu perfil genético presenta una predisposición baja en la mayoría de las condiciones evaluadas.';
      case 'Riesgo moderado':
        return 'Tienes algunas variantes que aumentan ligeramente el riesgo. Un estilo de vida saludable ayuda a equilibrarlo.';
      case 'Riesgo elevado':
        return 'Se observan varias variantes asociadas a mayor riesgo. Es recomendable conversar estos resultados con un profesional de la salud.';
      case 'Riesgo alto':
        return 'Tu perfil concentra variantes de alto impacto. Lo ideal es que un médico revise estos resultados para definir seguimiento y prevención.';
      default:
        return '';
    }
  };

  const tooltipContent = `Este score resume tu predisposición genética a enfermedades, dándole más peso a las de alta prioridad que a las de baja.

No es un diagnóstico. Un valor más alto indica que, dentro de las variantes que analizamos, hay más cambios relevantes, pero siempre debe interpretarse junto con tus hábitos, antecedentes y la opinión de un especialista.`;

  return (
    <div className="card-pro card-large-pro">
      <div className="card-pro__header">
        <div>
          <div className="flex items-center gap-2">
            <h3>Score Genético</h3>
            <Tooltip content={tooltipContent}>
              <HelpCircle
                size={16}
                className="text-gray-400 hover:text-gray-600 transition-colors"
              />
            </Tooltip>
          </div>
          <p className="card-pro__subtitle">
            Evaluación ponderada de tu predisposición a enfermedades.
          </p>
        </div>
      </div>

      <div className="flex flex-1 flex-col items-center justify-center gap-2 p-1 sm:gap-4 sm:p-2">
        {/* Contenedor para superponer nuestro número */}
        <div className="relative flex items-center justify-center">
          <AnimatedCircularProgressBar
            value={animatedScore}
            gaugePrimaryColor={hexColor}
            gaugeSecondaryColor="#E5E7EB"
            // Hacemos transparente el texto interno del componente
            className={`w-28 h-28 sm:w-32 sm:h-32 text-transparent`}
          />

          {/* Nuestro número centrado y con el color correcto */}
          <span
            className={`absolute text-2xl sm:text-3xl font-bold ${textColor}`}
          >
            {animatedScore}
          </span>
        </div>

        <div className="w-full text-center px-2 sm:px-4">
          <p className={`text-base sm:text-lg font-bold ${textColor} mb-2 sm:mb-4`}>
            {level}
          </p>
          <div className="border-t border-gray-200 pt-2 sm:pt-4 mt-2 sm:mt-4 mx-1 sm:mx-4">
            <p className="text-xs sm:text-sm text-gray-600 max-w-xs mx-auto">
              {getDescription(level)}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
