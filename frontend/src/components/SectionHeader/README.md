# Componente SectionHeader

Componente reutilizable para los headers de las subsecciones genéticas (Enfermedades, Rasgos, Ancestría, Farmacogenética, Biomarcadores, Biométricas).

## Uso

```jsx
import SectionHeader from '../../components/SectionHeader/SectionHeader';
import { Activity } from 'lucide-react'; // O el icono que prefieras

<SectionHeader
  title="Nombre de la Sección"
  subtitle="Descripción de la sección"
  icon={Activity}
/>
```

## Props

- **title** (string, requerido): Título de la sección
- **subtitle** (string, opcional): Subtítulo o descripción de la sección
- **icon** (React Component, opcional): Componente de icono de lucide-react

## Iconos Sugeridos por Sección

| Sección | Icono | Importación |
|---------|-------|-------------|
| Enfermedades | Activity | `import { Activity } from 'lucide-react'` |
| Rasgos | Sparkles | `import { Sparkles } from 'lucide-react'` |
| Ancestría | Globe | `import { Globe } from 'lucide-react'` |
| Farmacogenética | Pill | `import { Pill } from 'lucide-react'` |
| Biomarcadores | Microscope | `import { Microscope } from 'lucide-react'` |
| Biométricas | Heart | `import { Heart } from 'lucide-react'` |

## Ejemplo Completo

```jsx
import React from 'react';
import SectionHeader from '../../components/SectionHeader/SectionHeader';
import { Activity } from 'lucide-react';
import './MiSeccion.css';

const MiSeccion = () => {
  return (
    <div className="mi-seccion-dashboard">
      <main className="mi-seccion-dashboard__main">
        <div className="mi-seccion-page">
          <SectionHeader
            title="Enfermedades"
            subtitle="Aquí podrás explorar tu predisposición genética..."
            icon={Activity}
          />
          
          {/* Resto del contenido */}
        </div>
      </main>
    </div>
  );
};

export default MiSeccion;
```

## Estilos

El componente incluye:
- Fondo azul gradiente (mismo de AdminReports)
- Bordes redondeados
- Icono con background semi-transparente
- Responsive (se adapta a móviles)
- Sombra sutil

No es necesario agregar estilos adicionales en la página que lo use.
