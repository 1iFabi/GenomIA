import React, { useMemo, useState, useEffect } from 'react';
import { Menu, X } from 'lucide-react';
import GridBento from '../../components/GridBento/GridBento';
import Sidebar from '../../components/Sidebar/Sidebar';
import Buttondownload from '../../components/Buttondownload';
import './Dashboard.css';

const Dashboard = ({ user, onLogout }) => {
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [isMobile, setIsMobile] = useState(false);
  const [isDownloading, setIsDownloading] = useState(false);

  useEffect(() => {
    const checkMobile = () => {
      const mobile = window.innerWidth <= 1024;
      setIsMobile(mobile);
      if (!mobile) {
        setIsMobileMenuOpen(false);
      }
    };
    
    checkMobile();
    window.addEventListener('resize', checkMobile);
    return () => window.removeEventListener('resize', checkMobile);
  }, []);

  const displayName = useMemo(() => {
    const candidates = [
      user?.first_name,
      user?.firstName,
      user?.name,
      user?.username,
      user?.email
    ];
    return candidates.find(Boolean) || 'Usuario';
  }, [user]);

  const cards = useMemo(
    () => [
      {
        id: 'postlogin-ancestria',
        navLabel: 'Ancestría',
        title: 'Ancestría',
        description:
          'Descubre tus orígenes genéticos y cómo las conexiones con distintas poblaciones han influido en tu historia ancestral.',
        cta: {
          label: 'Explorar ahora',
          href: '/dashboard/ancestria',
          ariaLabel: 'Explorar Ancestría'
        },
        className: 'card--ancestria',
        contentJustify: 'start',
        textColor: '#4A1C5F',
        descriptionColor: '#6B2E84',
        ctaColor: '#4A1C5F',
        style: {
          backgroundColor: '#E8D4F0',
          backgroundImage: 'url(\'/Dashboard/ojo.png\')',
          backgroundSize: '170% auto',
          backgroundPosition: 'center calc(100% + 210px)',
          backgroundRepeat: 'no-repeat',
        }
      },
      {
        id: 'postlogin-rasgos',
        navLabel: 'Rasgos',
        title: 'Rasgos',
        description:
          'Conoce los rasgos genéticos que influyen en tu apariencia, comportamiento y habilidades únicas.',
        cta: {
          label: 'Explorar ahora',
          href: '/dashboard/rasgos',
          ariaLabel: 'Explorar Rasgos'
        },
        className: 'card--rasgos',
        textColor: '#29455B',
        descriptionColor: '#2D5280',
        ctaColor: '#1E3A5F',
        style: {
          backgroundColor: '#D4E8F8',
          backgroundImage: 'url(\'/Dashboard/semicirculo.png\')',
          backgroundSize: '45% auto',
          backgroundPosition: 'calc(100% + 80px) calc(100% + 30px)',
          backgroundRepeat: 'no-repeat'
        }
      },
      {
        id: 'postlogin-farmacogenetica',
        navLabel: 'Farmacogenética',
        title: 'Farmacogenética',
        description:
          'Descubre cómo tu genética influye en los medicamentos para optimizar tus tratamientos.',
        cta: {
          label: 'Explorar ahora',
          href: '/dashboard/farmacogenetica',
          ariaLabel: 'Explorar Farmacogenética'
        },
        className: 'card--farmacogenetica',
        textColor: '#3E3A37',
        descriptionColor: '#5A5450',
        ctaColor: '#3E3A37',
        style: {
          backgroundColor: '#F0EAE4',
          backgroundImage: 'url(\'/Dashboard/grises.png\')',
          backgroundSize: '35% auto',
          backgroundPosition: 'right bottom -20px',
          backgroundRepeat: 'no-repeat'
        }
      },
      {
        id: 'postlogin-biomarcadores',
        navLabel: 'Biomarcadores',
        title: 'Biomarcadores',
        description:
          'Identifica biomarcadores genéticos que revelan factores clave de tu salud, bienestar y predisposición.',
        cta: {
          label: 'Explorar ahora',
          href: '/dashboard/biomarcadores',
          ariaLabel: 'Explorar Biomarcadores'
        },
        className: 'card--biomarcadores',
        textColor: '#5F3A1C',
        descriptionColor: '#845C2E',
        ctaColor: '#5F3A1C',
        style: {
          backgroundColor: '#F8E8D4',
          backgroundImage: 'url(\'/Dashboard/naranjo.png\')',
          backgroundSize: '45% auto',
          backgroundPosition: 'calc(100% + 60px) calc(100% + 15px)',
          backgroundRepeat: 'no-repeat'
        }
      },
      {
        id: 'postlogin-biometricas',
        navLabel: 'Biométricas',
        title: 'Biométricas',
        description:
          'Analiza tus datos biométricos para entender cómo tus características físicas influyen en tu salud general.',
        cta: {
          label: 'Explorar ahora',
          href: '/dashboard/biometricas',
          ariaLabel: 'Explorar Biométricas'
        },
        className: 'card--biometricas',
        textColor: '#5F1C3E',
        descriptionColor: '#842D5A',
        ctaColor: '#5F1C3E',
        style: {
          backgroundColor: '#f8e0edff',
          backgroundImage: 'url(\'/Dashboard/estrella.png\')',
          backgroundSize: '47% auto',
          backgroundPosition: 'calc(100% + 120px) calc(100% + 25px)',
          backgroundRepeat: 'no-repeat'
        }
      },
      {
        id: 'postlogin-enfermedades',
        navLabel: 'Enfermedades',
        title: 'Enfermedades',
        description:
          'Analiza tu genética para conocer predisposiciones y mutaciones que pueden influir en tu salud y bienestar.',
        cta: {
          label: 'Explorar ahora',
          href: '/dashboard/enfermedades',
          ariaLabel: 'Explorar Enfermedades'
        },
        className: 'card--enfermedades',
        textColor: '#3A5F3E',
        descriptionColor: '#4F7D54',
        ctaColor: '#3A5F3E',
        style: {
          backgroundColor: '#E0F0E4',
          backgroundImage: 'url(\'/Dashboard/cuadrado.png\')',
          backgroundSize: '25% auto',
          backgroundPosition: 'calc(100% + 50px) calc(100% + 50px)',
          backgroundRepeat: 'no-repeat'
        }
      }
    ],
    []
  );

  const sidebarItems = useMemo(
    () =>
      cards.map(card => ({
        label: card.navLabel ?? card.title ?? card.label,
        href: card.cta?.href ?? '#'
      })),
    [cards]
  );

  return (
    <div className="dashboard">
      {/* Burger button para móviles */}
      {isMobile && (
        <button 
          className="dashboard__burger"
          onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
          aria-label={isMobileMenuOpen ? "Cerrar menú" : "Abrir menú"}
          aria-expanded={isMobileMenuOpen}
        >
          {isMobileMenuOpen ? (
            <X size={24} strokeWidth={2.5} />
          ) : (
            <Menu size={24} strokeWidth={2.5} />
          )}
        </button>
      )}

      <aside className="dashboard__sidebar">
        <Sidebar 
          items={sidebarItems} 
          onLogout={onLogout} 
          user={user}
          isMobileMenuOpen={isMobileMenuOpen}
          setIsMobileMenuOpen={setIsMobileMenuOpen}
        />
      </aside>

      <main className="dashboard__main">
        <header className="dashboard__header">
          <div className="dashboard__headline">
            <h1 className="dashboard__welcome">Bienvenido/a {displayName}!</h1>
            <p className="dashboard__subtitle">
              Explora cómo tu información genética se relaciona con distintos aspectos de ti, y descubre análisis personalizados en cada categoría.
            </p>
          </div>
          <div className="dashboard__actions">
            <Buttondownload 
              userName={displayName} 
              isDownloading={isDownloading} 
              setIsDownloading={setIsDownloading} 
            />
          </div>
        </header>


        <section className="dashboard__grid" aria-label="Resumen postprueba">
          <GridBento
            cards={cards}
            textAutoHide={false}
            enableSpotlight={false}
            enableTilt={false}
            enableStars={false}
            enableBorderGlow={false}
            enableMagnetism={false}
            clickEffect={false}
            glowColor="8, 133, 216"
          />
        </section>
      </main>
    </div>
  );
};

export default Dashboard;
