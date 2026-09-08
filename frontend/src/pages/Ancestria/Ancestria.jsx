import React, { useEffect, useState, useMemo, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Menu, X, Dna } from 'lucide-react';
import { ComposableMap, Geographies, Geography, ZoomableGroup } from 'react-simple-maps';
import { Tooltip } from 'react-tooltip';
import { scaleLinear } from 'd3-scale';
import { API_ENDPOINTS, apiRequest, clearToken } from '../../config/api';
import Sidebar from '../../components/Sidebar/Sidebar';
import SectionHeader from '../../components/SectionHeader/SectionHeader';
import IndigenousRadarChart from '../../components/IndigenousRadarChart/IndigenousRadarChart';
import compassRose from '../../assets/compass-rose.svg';
import './Ancestria.css';

// URL del mapa mundial (TopoJSON)
const GEO_URL = "https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json";

// Mapeo de códigos ISO-A3 numéricos (usados en TopoJSON) a continentes y nombres
const countryInfo = {
  // South America
  "032": { continent: "South America", code: "AR", name: "Argentina" },
  "068": { continent: "South America", code: "BO", name: "Bolivia" },
  "076": { continent: "South America", code: "BR", name: "Brazil" },
  "152": { continent: "South America", code: "CL", name: "Chile" },
  "170": { continent: "South America", code: "CO", name: "Colombia" },
  "218": { continent: "South America", code: "EC", name: "Ecuador" },
  "238": { continent: "South America", code: "FK", name: "Falkland Islands" },
  "254": { continent: "South America", code: "GF", name: "French Guiana" },
  "328": { continent: "South America", code: "GY", name: "Guyana" },
  "600": { continent: "South America", code: "PY", name: "Paraguay" },
  "604": { continent: "South America", code: "PE", name: "Peru" },
  "740": { continent: "South America", code: "SR", name: "Suriname" },
  "858": { continent: "South America", code: "UY", name: "Uruguay" },
  "862": { continent: "South America", code: "VE", name: "Venezuela" },

  // North America
  "028": { continent: "North America", code: "AG", name: "Antigua and Barbuda" },
  "044": { continent: "North America", code: "BS", name: "Bahamas" },
  "052": { continent: "North America", code: "BB", name: "Barbados" },
  "084": { continent: "North America", code: "BZ", name: "Belize" },
  "124": { continent: "North America", code: "CA", name: "Canada" },
  "188": { continent: "North America", code: "CR", name: "Costa Rica" },
  "192": { continent: "North America", code: "CU", name: "Cuba" },
  "212": { continent: "North America", code: "DM", name: "Dominica" },
  "214": { continent: "North America", code: "DO", name: "Dominican Republic" },
  "222": { continent: "North America", code: "SV", name: "El Salvador" },
  "308": { continent: "North America", code: "GD", name: "Grenada" },
  "320": { continent: "North America", code: "GT", name: "Guatemala" },
  "332": { continent: "North America", code: "HT", name: "Haiti" },
  "340": { continent: "North America", code: "HN", name: "Honduras" },
  "388": { continent: "North America", code: "JM", name: "Jamaica" },
  "484": { continent: "North America", code: "MX", name: "Mexico" },
  "558": { continent: "North America", code: "NI", name: "Nicaragua" },
  "591": { continent: "North America", code: "PA", name: "Panama" },
  "659": { continent: "North America", code: "KN", name: "Saint Kitts and Nevis" },
  "662": { continent: "North America", code: "LC", name: "Saint Lucia" },
  "670": { continent: "North America", code: "VC", name: "Saint Vincent and the Grenadines" },
  "780": { continent: "North America", code: "TT", name: "Trinidad and Tobago" },
  "840": { continent: "North America", code: "US", name: "United States" },
  "304": { continent: "North America", code: "GL", name: "Greenland" },

  // Europe
  "008": { continent: "Europe", code: "AL", name: "Albania" },
  "020": { continent: "Europe", code: "AD", name: "Andorra" },
  "040": { continent: "Europe", code: "AT", name: "Austria" },
  "112": { continent: "Europe", code: "BY", name: "Belarus" },
  "056": { continent: "Europe", code: "BE", name: "Belgium" },
  "070": { continent: "Europe", code: "BA", name: "Bosnia and Herzegovina" },
  "100": { continent: "Europe", code: "BG", name: "Bulgaria" },
  "191": { continent: "Europe", code: "HR", name: "Croatia" },
  "196": { continent: "Europe", code: "CY", name: "Cyprus" },
  "203": { continent: "Europe", code: "CZ", name: "Czech Republic" },
  "208": { continent: "Europe", code: "DK", name: "Denmark" },
  "233": { continent: "Europe", code: "EE", name: "Estonia" },
  "246": { continent: "Europe", code: "FI", name: "Finland" },
  "250": { continent: "Europe", code: "FR", name: "France" },
  "276": { continent: "Europe", code: "DE", name: "Germany" },
  "300": { continent: "Europe", code: "GR", name: "Greece" },
  "348": { continent: "Europe", code: "HU", name: "Hungary" },
  "352": { continent: "Europe", code: "IS", name: "Iceland" },
  "372": { continent: "Europe", code: "IE", name: "Ireland" },
  "380": { continent: "Europe", code: "IT", name: "Italy" },
  "428": { continent: "Europe", code: "LV", name: "Latvia" },
  "438": { continent: "Europe", code: "LI", name: "Liechtenstein" },
  "440": { continent: "Europe", code: "LT", name: "Lithuania" },
  "442": { continent: "Europe", code: "LU", name: "Luxembourg" },
  "470": { continent: "Europe", code: "MT", name: "Malta" },
  "498": { continent: "Europe", code: "MD", name: "Moldova" },
  "499": { continent: "Europe", code: "ME", name: "Montenegro" },
  "528": { continent: "Europe", code: "NL", name: "Netherlands" },
  "807": { continent: "Europe", code: "MK", name: "North Macedonia" },
  "578": { continent: "Europe", code: "NO", name: "Norway" },
  "616": { continent: "Europe", code: "PL", name: "Poland" },
  "620": { continent: "Europe", code: "PT", name: "Portugal" },
  "642": { continent: "Europe", code: "RO", name: "Romania" },
  "643": { continent: "Europe", code: "RU", name: "Russia" },
  "674": { continent: "Europe", code: "SM", name: "San Marino" },
  "688": { continent: "Europe", code: "RS", name: "Serbia" },
  "703": { continent: "Europe", code: "SK", name: "Slovakia" },
  "705": { continent: "Europe", code: "SI", name: "Slovenia" },
  "724": { continent: "Europe", code: "ES", name: "Spain" },
  "752": { continent: "Europe", code: "SE", name: "Sweden" },
  "756": { continent: "Europe", code: "CH", name: "Switzerland" },
  "804": { continent: "Europe", code: "UA", name: "Ukraine" },
  "826": { continent: "Europe", code: "GB", name: "United Kingdom" },

  // Asia
  "004": { continent: "Asia", code: "AF", name: "Afghanistan" },
  "051": { continent: "Asia", code: "AM", name: "Armenia" },
  "031": { continent: "Asia", code: "AZ", name: "Azerbaijan" },
  "048": { continent: "Asia", code: "BH", name: "Bahrain" },
  "050": { continent: "Asia", code: "BD", name: "Bangladesh" },
  "064": { continent: "Asia", code: "BT", name: "Bhutan" },
  "096": { continent: "Asia", code: "BN", name: "Brunei" },
  "116": { continent: "Asia", code: "KH", name: "Cambodia" },
  "156": { continent: "Asia", code: "CN", name: "China" },
  "268": { continent: "Asia", code: "GE", name: "Georgia" },
  "356": { continent: "Asia", code: "IN", name: "India" },
  "360": { continent: "Asia", code: "ID", name: "Indonesia" },
  "364": { continent: "Asia", code: "IR", name: "Iran" },
  "368": { continent: "Asia", code: "IQ", name: "Iraq" },
  "376": { continent: "Asia", code: "IL", name: "Israel" },
  "392": { continent: "Asia", code: "JP", name: "Japan" },
  "400": { continent: "Asia", code: "JO", name: "Jordan" },
  "398": { continent: "Asia", code: "KZ", name: "Kazakhstan" },
  "414": { continent: "Asia", code: "KW", name: "Kuwait" },
  "417": { continent: "Asia", code: "KG", name: "Kyrgyzstan" },
  "418": { continent: "Asia", code: "LA", name: "Laos" },
  "422": { continent: "Asia", code: "LB", name: "Lebanon" },
  "458": { continent: "Asia", code: "MY", name: "Malaysia" },
  "496": { continent: "Asia", code: "MN", name: "Mongolia" },
  "104": { continent: "Asia", code: "MM", name: "Myanmar" },
  "524": { continent: "Asia", code: "NP", name: "Nepal" },
  "408": { continent: "Asia", code: "KP", name: "North Korea" },
  "512": { continent: "Asia", code: "OM", name: "Oman" },
  "586": { continent: "Asia", code: "PK", name: "Pakistan" },
  "608": { continent: "Asia", code: "PH", name: "Philippines" },
  "634": { continent: "Asia", code: "QA", name: "Qatar" },
  "682": { continent: "Asia", code: "SA", name: "Saudi Arabia" },
  "702": { continent: "Asia", code: "SG", name: "Singapore" },
  "410": { continent: "Asia", code: "KR", name: "South Korea" },
  "144": { continent: "Asia", code: "LK", name: "Sri Lanka" },
  "760": { continent: "Asia", code: "SY", name: "Syria" },
  "158": { continent: "Asia", code: "TW", name: "Taiwan" },
  "762": { continent: "Asia", code: "TJ", name: "Tajikistan" },
  "764": { continent: "Asia", code: "TH", name: "Thailand" },
  "792": { continent: "Asia", code: "TR", name: "Turkey" },
  "795": { continent: "Asia", code: "TM", name: "Turkmenistan" },
  "784": { continent: "Asia", code: "AE", name: "United Arab Emirates" },
  "860": { continent: "Asia", code: "UZ", name: "Uzbekistan" },
  "704": { continent: "Asia", code: "VN", name: "Vietnam" },
  "887": { continent: "Asia", code: "YE", name: "Yemen" },

  // Africa
  "012": { continent: "Africa", code: "DZ", name: "Algeria" },
  "024": { continent: "Africa", code: "AO", name: "Angola" },
  "204": { continent: "Africa", code: "BJ", name: "Benin" },
  "072": { continent: "Africa", code: "BW", name: "Botswana" },
  "854": { continent: "Africa", code: "BF", name: "Burkina Faso" },
  "108": { continent: "Africa", code: "BI", name: "Burundi" },
  "132": { continent: "Africa", code: "CV", name: "Cabo Verde" },
  "120": { continent: "Africa", code: "CM", name: "Cameroon" },
  "140": { continent: "Africa", code: "CF", name: "Central African Republic" },
  "148": { continent: "Africa", code: "TD", name: "Chad" },
  "174": { continent: "Africa", code: "KM", name: "Comoros" },
  "180": { continent: "Africa", code: "CD", name: "Congo, DR" },
  "178": { continent: "Africa", code: "CG", name: "Congo" },
  "384": { continent: "Africa", code: "CI", name: "Cote d'Ivoire" },
  "262": { continent: "Africa", code: "DJ", name: "Djibouti" },
  "818": { continent: "Africa", code: "EG", name: "Egypt" },
  "226": { continent: "Africa", code: "GQ", name: "Equatorial Guinea" },
  "232": { continent: "Africa", code: "ER", name: "Eritrea" },
  "748": { continent: "Africa", code: "SZ", name: "Eswatini" },
  "231": { continent: "Africa", code: "ET", name: "Ethiopia" },
  "266": { continent: "Africa", code: "GA", name: "Gabon" },
  "270": { continent: "Africa", code: "GM", name: "Gambia" },
  "288": { continent: "Africa", code: "GH", name: "Ghana" },
  "324": { continent: "Africa", code: "GN", name: "Guinea" },
  "624": { continent: "Africa", code: "GW", name: "Guinea-Bissau" },
  "404": { continent: "Africa", code: "KE", name: "Kenya" },
  "426": { continent: "Africa", code: "LS", name: "Lesotho" },
  "430": { continent: "Africa", code: "LR", name: "Liberia" },
  "434": { continent: "Africa", code: "LY", name: "Libya" },
  "450": { continent: "Africa", code: "MG", name: "Madagascar" },
  "454": { continent: "Africa", code: "MW", name: "Malawi" },
  "466": { continent: "Africa", code: "ML", name: "Mali" },
  "478": { continent: "Africa", code: "MR", name: "Mauritania" },
  "480": { continent: "Africa", code: "MU", name: "Mauritius" },
  "504": { continent: "Africa", code: "MA", name: "Morocco" },
  "508": { continent: "Africa", code: "MZ", name: "Mozambique" },
  "516": { continent: "Africa", code: "NA", name: "Namibia" },
  "562": { continent: "Africa", code: "NE", name: "Niger" },
  "566": { continent: "Africa", code: "NG", name: "Nigeria" },
  "646": { continent: "Africa", code: "RW", name: "Rwanda" },
  "678": { continent: "Africa", code: "ST", name: "Sao Tome and Principe" },
  "686": { continent: "Africa", code: "SN", name: "Senegal" },
  "690": { continent: "Africa", code: "SC", name: "Seychelles" },
  "694": { continent: "Africa", code: "SL", name: "Sierra Leone" },
  "706": { continent: "Africa", code: "SO", name: "Somalia" },
  "710": { continent: "Africa", code: "ZA", name: "South Africa" },
  "728": { continent: "Africa", code: "SS", name: "South Sudan" },
  "729": { continent: "Africa", code: "SD", name: "Sudan" },
  "834": { continent: "Africa", code: "TZ", name: "Tanzania" },
  "768": { continent: "Africa", code: "TG", name: "Togo" },
  "788": { continent: "Africa", code: "TN", name: "Tunisia" },
  "800": { continent: "Africa", code: "UG", name: "Uganda" },
  "894": { continent: "Africa", code: "ZM", name: "Zambia" },
  "716": { continent: "Africa", code: "ZW", name: "Zimbabwe" },

  // Oceania
  "036": { continent: "Oceania", code: "AU", name: "Australia" },
  "242": { continent: "Oceania", code: "FJ", name: "Fiji" },
  "296": { continent: "Oceania", code: "KI", name: "Kiribati" },
  "584": { continent: "Oceania", code: "MH", name: "Marshall Islands" },
  "583": { continent: "Oceania", code: "FM", name: "Micronesia" },
  "520": { continent: "Oceania", code: "NR", name: "Nauru" },
  "554": { continent: "Oceania", code: "NZ", name: "New Zealand" },
  "585": { continent: "Oceania", code: "PW", name: "Palau" },
  "598": { continent: "Oceania", code: "PG", name: "Papua New Guinea" },
  "882": { continent: "Oceania", code: "WS", name: "Samoa" },
  "090": { continent: "Oceania", code: "SB", name: "Solomon Islands" },
  "776": { continent: "Oceania", code: "TO", name: "Tonga" },
  "798": { continent: "Oceania", code: "TV", name: "Tuvalu" },
  "548": { continent: "Oceania", code: "VU", name: "Vanuatu" }
};

const normalizeCountryText = (value) => {
  if (!value) return "";
  return value
    .toString()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[().,]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
};


const containsTokenSequence = (haystack, needle) => {
  if (!haystack || !needle) return false;
  if (haystack === needle) return true;
  const hayTokens = haystack.split(" ");
  const needleTokens = needle.split(" ");
  if (needleTokens.length === 1) {
    return hayTokens.includes(needleTokens[0]);
  }
  for (let i = 0; i <= hayTokens.length - needleTokens.length; i += 1) {
    let match = true;
    for (let j = 0; j < needleTokens.length; j += 1) {
      if (hayTokens[i + j] !== needleTokens[j]) {
        match = false;
        break;
      }
    }
    if (match) return true;
  }
  return false;
};

const normalizeGeoId = (value) => {
  if (value === null || value === undefined) return "";
  const raw = value.toString().trim();
  if (!raw) return "";
  const numeric = Number(raw);
  if (Number.isFinite(numeric)) {
    const padded = numeric.toString().padStart(3, "0");
    return padded;
  }
  return raw;
};

const countryNameMapping = {
        "Chile": "Chile",
        "España": "Spain",
        "Mexico": "Mexico",
        "México": "Mexico",
        "Finlandia": "Finland",
        "Finland": "Finland",
        "Nigeria": "Nigeria",
        "China": "China",
        "Estados Unidos": "United States",
        "USA": "United States",
        "Rusia": "Russia",
        "Alemania": "Germany",
        "Francia": "France",
        "Italia": "Italy",
        "Reino Unido": "United Kingdom",
        "Brasil": "Brazil",
        "Peru": "Peru",
        "Perú": "Peru",
        "Colombia": "Colombia",
        "Argentina": "Argentina",
        "Bolivia": "Bolivia",
        "Venezuela": "Venezuela",
        "Ecuador": "Ecuador",
        "Paraguay": "Paraguay",
        "Uruguay": "Uruguay",
        "Guayana Francesa": "French Guiana",
        "Guyana Francesa": "French Guiana",
        "Guiana Francesa": "French Guiana",
        "Guyane": "French Guiana",
        "Kazajistán": "Kazakhstan",
        "Kazajistan": "Kazakhstan",
        "KAZ": "Kazakhstan",
        "Kazakhstan": "Kazakhstan",
        "Kazahistan": "Kazakhstan",
        "Kazakstan": "Kazakhstan",
        "Republic of Kazakhstan": "Kazakhstan",
        "Mongolia": "Mongolia",
        "MNG": "Mongolia",
        "Mongolie": "Mongolia"
    };

const countryNameMappingNormalized = Object.entries(countryNameMapping).reduce((acc, [key, value]) => {
    acc[normalizeCountryText(key)] = value;
    return acc;
}, {});

const countryInfoById = Object.entries(countryInfo).reduce((acc, [id, info]) => {
    const normalizedId = normalizeGeoId(id);
    acc[id] = info;
    acc[normalizedId] = info;
    return acc;
}, {});

const countryInfoByName = Object.values(countryInfo).reduce((acc, info) => {
    acc[normalizeCountryText(info.name)] = info;
    acc[normalizeCountryText(info.code)] = info;
    return acc;
}, {});

const getGeoCountryInfo = (geo) => {
    if (!geo) return null;

    const geoId = normalizeGeoId(geo.id);
    
    // Fallback explícito para IDs de Kazakhstan y Mongolia si el mapeo falla
    if (geoId === "398") return countryInfo["398"];
    if (geoId === "496") return countryInfo["496"];

    const direct = countryInfoById[geoId] || countryInfoById[String(geo.id)];
    if (direct) return direct;

    const geoName = geo?.properties?.name || "";
    const normalizedName = normalizeCountryText(geoName);
    const mappedName = countryNameMapping[geoName] || countryNameMappingNormalized[normalizedName];
    const lookup = mappedName ? normalizeCountryText(mappedName) : normalizedName;

    return countryInfoByName[lookup] || null;
};

const getGeoContinentName = (geo) => getGeoCountryInfo(geo)?.continent || "Otros";


const Ancestria = () => {
  const [user, setUser] = useState(null);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [isMobile, setIsMobile] = useState(false);
  const [ancestryData, setAncestryData] = useState(null);
  const [selectedCountry, setSelectedCountry] = useState(null);
  const mapContainerRef = useRef(null);
  
  // Estado del mapa (solo activo/inactivo, sin coordenadas)
  const [activeContinent, setActiveContinent] = useState(null); 
  const [hoveredContinent, setHoveredContinent] = useState(null);

  const navigate = useNavigate();

  // Escala de color para los porcentajes (azul muy claro a azul profundo)
  const colorScale = scaleLinear()
    .domain([0, 100]) // 0% a 100% para diferenciar claramente los tonos
    .range(["#E1F5FE", "#01579B"]); // Azul muy pálido a Azul intenso

  useEffect(() => {
    fetchUser();
    
    const checkMobile = () => {
      const mobile = window.innerWidth <= 1024;
      setIsMobile(mobile);
      if (!mobile) setIsMobileMenuOpen(false);
    };
    
    checkMobile();
    window.addEventListener('resize', checkMobile);
    return () => window.removeEventListener('resize', checkMobile);
  }, []);

  useEffect(() => {
    if (user) fetchAncestryData();
  }, [user]);

  // Bloquear el scroll de la página cuando el mouse está sobre el mapa
  useEffect(() => {
    const preventScroll = (e) => {
        e.preventDefault();
    };

    const container = mapContainerRef.current;
    if (container) {
        // { passive: false } es crucial para poder llamar a preventDefault
        container.addEventListener('wheel', preventScroll, { passive: false });
    }

    return () => {
        if (container) {
            container.removeEventListener('wheel', preventScroll);
        }
    };
  }, []);

  const fetchUser = async () => {
    const response = await apiRequest(API_ENDPOINTS.ME, { method: 'GET' });
    if (response.ok && response.data) setUser(response.data.user || response.data);
  };

  const fetchAncestryData = async () => {
    try {
      const response = await apiRequest(API_ENDPOINTS.ANCESTRY, { method: 'GET' });
      if (response.ok && response.data && response.data.data) {
        setAncestryData(response.data.data);
      }
    } catch (error) {
      console.error('Error fetching ancestry data:', error);
    }
  };

  const handleLogout = async () => {
    try {
      await apiRequest(API_ENDPOINTS.LOGOUT, { method: 'POST' });
    } catch (error) { console.error(error); }
    clearToken();
    navigate('/');
  };

  const getCountryData = (isoCode) => {
    if (!ancestryData?.countries) return null;
    
    // Mapeo de nombres de API (Español/Variados) a nombres del Mapa (Inglés TopoJSON)

    const info = Object.values(countryInfo).find(i => i.code === isoCode);
    if (!info) return null;

    const infoNameNormalized = normalizeCountryText(info.name);
    const infoCodeNormalized = normalizeCountryText(info.code);

    return ancestryData.countries.find(c => {
        // 1. Coincidencia directa con el nombre en inglés del mapa
        const normalizedName = normalizeCountryText(c.name);
        const mappedName = countryNameMapping[c.name] || countryNameMappingNormalized[normalizedName];
        const mappedNormalized = mappedName ? normalizeCountryText(mappedName) : "";
        if (normalizedName === infoNameNormalized) return true;
        if (normalizedName === infoCodeNormalized) return true;
        
        // 2. Coincidencia a través del mapeo (Nombre API -> Nombre Mapa)
        if (mappedNormalized === infoNameNormalized) return true;
        if (mappedNormalized === infoCodeNormalized) return true;
        if (containsTokenSequence(normalizedName, infoNameNormalized)) return true;
        if (mappedNormalized && containsTokenSequence(mappedNormalized, infoNameNormalized)) return true;

        return false;
    });
  };
  
  // Detectar en qué continentes hay datos y calcular sus totales
  const continentData = useMemo(() => {
    if (!ancestryData?.countries) return { active: new Set(), totals: {} };
    
    const active = new Set();
    const totals = {};
    
    // Mapeo inverso para normalizar nombres antes de buscar

    ancestryData.countries.forEach(c => {
        const normalizedName = normalizeCountryText(c.name);
        const mappedName = countryNameMapping[c.name] || countryNameMappingNormalized[normalizedName] || c.name;
        const mappedNormalized = normalizeCountryText(mappedName);

        // Buscar en countryInfo usando el nombre normalizado
        const found = Object.values(countryInfo).find(info => {
            const infoNameNormalized = normalizeCountryText(info.name);
            const infoCodeNormalized = normalizeCountryText(info.code);
            return (
                mappedNormalized === infoNameNormalized ||
                mappedNormalized === infoCodeNormalized ||
                normalizedName === infoNameNormalized ||
                normalizedName === infoCodeNormalized ||
                containsTokenSequence(normalizedName, infoNameNormalized) ||
                (mappedNormalized && containsTokenSequence(mappedNormalized, infoNameNormalized))
            );
        });
        
        if (found) {
            const cont = found.continent;
            active.add(cont);
            totals[cont] = (totals[cont] || 0) + c.percentage;
        }
    });
    return { active, totals };
  }, [ancestryData]);

  const handleGeographyClick = (geo, e) => {
    e.stopPropagation();
    const info = getGeoCountryInfo(geo);
    if (!info) return;

    // Si estamos en vista mundial y hacemos clic en un país, entramos a su continente
    if (!activeContinent || activeContinent !== info.continent) {
        if (continentData.active.has(info.continent)) {
             setActiveContinent(info.continent);
        }
        return;
    }

    // Si ya estamos en el continente, mostramos los detalles del país si tiene datos
    const data = getCountryData(info.code);
    
    // Validación extra: asegurarse de que data y percentage existan
    if (data && typeof data.percentage === 'number') {
        setSelectedCountry({ 
            ...data, 
            ...info,
            variants: Math.floor(data.percentage * 0.8) + 5,
            alleleFrequency: (30 + Math.random() * 10).toFixed(2)
        });
    }
  };

  const handleResetZoom = () => {
    setActiveContinent(null);
    setSelectedCountry(null);
  };


  const sidebarItems = useMemo(() => [
    { label: 'Ancestría', href: '/dashboard/ancestria' },
    { label: 'Rasgos', href: '/dashboard/rasgos' },
    { label: 'Farmacogenética', href: '/dashboard/farmacogenetica' },
    { label: 'Biomarcadores', href: '/dashboard/biomarcadores' },
    { label: 'Biométricas', href: '/dashboard/biometricas' },
    { label: 'Enfermedades', href: '/dashboard/enfermedades' },
  ], []);

  return (
    <div className="ancestria-dashboard">
        {/* Modal Detallado Estilo OLA.png */}
        {selectedCountry && (
            <div className="modal-overlay" onClick={() => setSelectedCountry(null)} style={{
                position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, 
                background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)',
                zIndex: 9999, display: 'flex', alignItems: 'center', justifyContent: 'center'
            }}>
                <div className="modal-content" onClick={e => e.stopPropagation()} style={{
                    background: 'white', padding: isMobile ? '1.5rem' : '2rem', borderRadius: '20px', 
                    maxWidth: '500px', width: '95%', fontFamily: '"Inter", sans-serif',
                    boxShadow: '0 10px 40px rgba(0,0,0,0.2)', position: 'relative',
                    maxHeight: '90vh', overflowY: 'auto'
                }}>
                    <button onClick={() => setSelectedCountry(null)} style={{
                        position: 'absolute', top: '15px', right: '15px', background: 'none', border: 'none', 
                        fontSize: '24px', color: '#888', cursor: 'pointer', zIndex: 10
                    }}>&times;</button>

                    <h2 style={{ color: '#1976D2', marginTop: 0, fontSize: isMobile ? '22px' : '28px', marginBottom: '1rem' }}>{selectedCountry.name}</h2>
                    
                    <p style={{ color: '#555', lineHeight: '1.6', fontSize: isMobile ? '14px' : '15px', marginBottom: '1.5rem' }}>
                        Tu ascendencia de {selectedCountry.name} es {(selectedCountry.percentage || 0) > 20 ? 'predominante' : 'parte'} en tu perfil genético, 
                        representando una parte significativa de tu herencia.
                    </p>

                    <div style={{ 
                        background: '#E3F2FD', borderLeft: '5px solid #1976D2', borderRadius: '8px', 
                        padding: isMobile ? '1rem' : '1.5rem', marginBottom: '1.5rem', color: '#1565C0', fontWeight: 'bold', fontSize: isMobile ? '14px' : '16px'
                    }}>
                        Porcentaje de ascendencia: <span style={{ fontSize: isMobile ? '16px' : '18px' }}>{(selectedCountry.percentage || 0).toFixed(1)}%</span>
                    </div>

                    <div style={{ 
                        border: '1px solid #E0E0E0', borderRadius: '12px', padding: '1rem', marginBottom: '1.5rem',
                        display: 'flex', justifyContent: 'space-between', fontSize: isMobile ? '13px' : '14px', color: '#666'
                    }}>
                        <div>
                            <span>Continente:</span>
                        </div>
                        <div style={{ fontWeight: '600', color: '#1976D2' }}>
                            {selectedCountry.continent || "Global"}
                        </div>
                    </div>

                    <h4 style={{ color: '#1976D2', marginBottom: '1rem', fontSize: isMobile ? '15px' : '16px' }}>Información Genética:</h4>
                    <ul style={{ listStyle: 'none', padding: 0, color: '#555', fontSize: isMobile ? '13px' : '14px', lineHeight: '1.8' }}>
                        <li>• Continente de origen: {selectedCountry.continent || "Desconocido"}</li>
                        <li>• Basado en {selectedCountry.variants || 20} variante(s) genética(s) analizada(s)</li>
                        <li>• Frecuencia alélica promedio: {selectedCountry.alleleFrequency || "33.10"}%</li>
                        <li>• Esta ascendencia contribuye a tu composición genética única</li>
                    </ul>

                    <button onClick={() => setSelectedCountry(null)} style={{
                        marginTop: '1.5rem', padding: isMobile ? '0.8rem' : '1rem', width: '100%', 
                        background: '#1976D2', color: 'white', border: 'none', borderRadius: '8px', 
                        cursor: 'pointer', fontSize: isMobile ? '14px' : '16px', fontWeight: 'bold', transition: 'background 0.2s'
                    }}
                    onMouseOver={(e) => e.target.style.background = '#1565C0'}
                    onMouseOut={(e) => e.target.style.background = '#1976D2'}
                    >
                        Cerrar
                    </button>
                </div>
            </div>
        )}

      {isMobile && (
        <button className="ancestria-dashboard__burger" onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}>
          {isMobileMenuOpen ? <X size={24} /> : <Menu size={24} />}
        </button>
      )}

      <aside className="ancestria-dashboard__sidebar">
        <Sidebar items={sidebarItems} onLogout={handleLogout} user={user} isMobileMenuOpen={isMobileMenuOpen} setIsMobileMenuOpen={setIsMobileMenuOpen} />
      </aside>

      <main className="ancestria-dashboard__main">
        <div className="ancestria-page">
          <SectionHeader title="Ancestría" subtitle="Conoce la composición de tus raíces genéticas, expresadas en porcentajes según su predominancia." icon={Dna} />

          <div className="ancestria-page__content">
            <div 
                ref={mapContainerRef}
                className="ancestria-page__chart-card" 
                onClick={handleResetZoom}
                style={{ 
                    gridColumn: '1 / -1', position: 'relative', 
                    height: isMobile ? '400px' : '600px', 
                    background: '#FFFFFF', 
                    borderRadius: '16px', overflow: 'hidden', border: '1px solid #E0E0E0',
                    userSelect: 'none', WebkitUserSelect: 'none', MozUserSelect: 'none', msUserSelect: 'none',
                    cursor: activeContinent ? 'zoom-out' : 'default'
            }}>
              
              <img src="/cNormal.png" alt="Logo" style={{ position: 'absolute', top: isMobile ? '20px' : '40px', right: isMobile ? '20px' : '40px', width: isMobile ? '30px' : '40px', filter: 'grayscale(100%)', zIndex: 10, opacity: 0.8, pointerEvents: 'none' }} />
              <img src={compassRose} alt="Brújula" style={{ position: 'absolute', top: isMobile ? '20px' : '40px', left: isMobile ? '20px' : '40px', width: isMobile ? '30px' : '40px', opacity: 0.8, zIndex: 10, pointerEvents: 'none' }} />

              {/* Indicador flotante del continente al hacer hover */}
              {!activeContinent && hoveredContinent && (
                <div style={{
                    position: 'absolute', top: isMobile ? '20px' : '40px', left: '50%', transform: 'translateX(-50%)',
                    zIndex: 20, background: 'rgba(255, 255, 255, 0.95)', backdropFilter: 'blur(8px)',
                    padding: isMobile ? '6px 20px' : '10px 32px', borderRadius: '30px',
                    boxShadow: '0 8px 24px rgba(25, 118, 210, 0.15)',
                    border: '1px solid rgba(25, 118, 210, 0.15)',
                    pointerEvents: 'none',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    transition: 'all 0.3s ease'
                }}>
                    <span style={{ 
                        color: '#0D47A1', fontWeight: '700', fontSize: isMobile ? '12px' : '15px', 
                        letterSpacing: '1px', textTransform: 'uppercase' 
                    }}>
                        {hoveredContinent === "South America" ? "América del Sur" :
                         hoveredContinent === "North America" ? "América del Norte" :
                         hoveredContinent === "Europe" ? "Europa" :
                         hoveredContinent === "Africa" ? "África" :
                         hoveredContinent === "Asia" ? "Asia" :
                         hoveredContinent === "Oceania" ? "Oceanía" : hoveredContinent}
                    </span>
                </div>
              )}

              {ancestryData?.countries && (
                <div style={{
                    position: 'absolute', 
                    bottom: isMobile ? '10px' : '20px', 
                    left: isMobile ? '10px' : '20px', 
                    zIndex: 10,
                    background: 'white', 
                    padding: isMobile ? '10px' : '15px', 
                    borderRadius: '12px',
                    boxShadow: '0 4px 20px rgba(0,0,0,0.08)', 
                    width: isMobile ? 'calc(100% - 20px)' : '280px',
                    maxWidth: isMobile ? '280px' : 'none',
                    fontFamily: '"Inter", sans-serif', border: '1px solid #F0F0F0'
                }} onClick={(e) => e.stopPropagation()}>
                    <h4 style={{ color: '#1976D2', margin: '0 0 8px 0', fontSize: isMobile ? '11px' : '13px', letterSpacing: '0.5px', fontWeight: '700' }}>ASCENDENCIA</h4>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: isMobile ? '4px 8px' : '8px 12px' }}>
                        {ancestryData.countries.map((country, idx) => (
                            <div key={idx} style={{ display: 'flex', alignItems: 'center', fontSize: isMobile ? '9px' : '11px', color: '#555' }}>
                                <div style={{ 
                                    width: isMobile ? '8px' : '10px', height: isMobile ? '8px' : '10px', borderRadius: '2px', 
                                    background: colorScale(country.percentage), marginRight: '6px' 
                                }}></div>
                                <span style={{ flex: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{country.name}</span>
                                <span style={{ fontWeight: '600', color: '#1976D2', marginLeft: '4px' }}>{country.percentage.toFixed(1)}%</span>
                            </div>
                        ))}
                    </div>
                </div>
              )}

              {/* Barra de leyenda minimalista abajo a la derecha */}
              {!isMobile && (
                <div style={{
                    position: 'absolute', bottom: '40px', right: '40px', zIndex: 10,
                    display: 'flex', flexDirection: 'column', alignItems: 'center'
                }}>
                    <div style={{ 
                        width: '200px', height: '8px', borderRadius: '4px', 
                        background: 'linear-gradient(to right, #E1F5FE, #01579B)',
                        marginBottom: '4px'
                    }}></div>
                    <div style={{ 
                        display: 'flex', justifyContent: 'space-between', width: '100%', 
                        fontSize: '11px', color: '#666', fontWeight: 'bold'
                    }}>
                        <span>0</span>
                        <span>100</span>
                    </div>
                </div>
              )}

              <ComposableMap 
                projection="geoMercator" 
                width={800} 
                height={500} 
                projectionConfig={{
                    scale: 115, 
                    center: [0, 40] 
                }}
                style={{ width: "100%", height: "100%", background: '#FFFFFF' }}
              >
                  <ZoomableGroup 
                    minZoom={1} 
                    maxZoom={4} 
                    filterZoomEvent={(evt) => evt.type !== 'dblclick'}
                    translateExtent={[
                        [0, 0], 
                        [800, 500]
                    ]}
                  >
                  <Geographies geography={GEO_URL}>
                    {({ geographies }) => {
                      // Agrupar geografías por continente para aplicar efectos de grupo (como escala)
                      const groups = geographies.reduce((acc, geo) => {
                        if (normalizeGeoId(geo.id) === "010") return acc; // Saltar Antártida
                        const cont = getGeoContinentName(geo);
                        if (!acc[cont]) acc[cont] = [];
                        acc[cont].push(geo);
                        return acc;
                      }, {});

                      return Object.entries(groups).map(([continentName, geos]) => {
                        const hasData = continentData.active.has(continentName);
                        const isHovered = !activeContinent && hasData && hoveredContinent === continentName;

                        return (
                          <g 
                            key={continentName}
                            style={{
                                transform: isHovered ? 'scale(1.03)' : 'scale(1)',
                                transition: 'transform 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
                                transformOrigin: 'center',
                                transformBox: 'fill-box',
                                cursor: (!activeContinent && hasData) ? 'pointer' : 'default'
                            }}
                            onMouseEnter={() => {
                                if (!activeContinent && hasData) setHoveredContinent(continentName);
                            }}
                            onMouseLeave={() => setHoveredContinent(null)}
                          >
                            {geos.map((geo) => {
                              const info = getGeoCountryInfo(geo);
                              const continent = continentName;
                              const countryData = info ? getCountryData(info.code) : null;

                              let fillColor = "#F9F9F9"; 
                              let strokeColor = "#E0E0E0"; 
                              let strokeWidth = 0.5;
                              let isClickable = false;
                              if (!activeContinent) {
                                  const totalContinent = continentData.totals[continent];
                                  if (totalContinent > 0) {
                                      fillColor = colorScale(totalContinent);
                                      strokeColor = "#D0D0D0"; 
                                      strokeWidth = 0.5; 
                                      isClickable = true;
                                  }
                              } else {
                                  if (continent === activeContinent) {
                                      strokeColor = "#333333";
                                      strokeWidth = 0.8;
                                      if (countryData) {
                                          fillColor = colorScale(countryData.percentage);
                                          isClickable = true;
                                      } else {
                                          fillColor = "#F9F9F9";
                                      }
                                  } else {
                                      fillColor = "#F5F5F5";
                                      strokeColor = "#E0E0E0"; 
                                      strokeWidth = 0.5;
                                  }
                              }

                              return (
                                <Geography
                                  key={geo.rsmKey}
                                  geography={geo}
                                  onClick={(e) => {
                                      if (isClickable || (activeContinent && info?.continent === activeContinent)) {
                                          handleGeographyClick(geo, e);
                                      }
                                  }}
                                  data-tooltip-id="my-tooltip"
                                  data-tooltip-content={
                                      activeContinent 
                                          ? (countryData ? `${countryData.name}: ${countryData.percentage.toFixed(1)}%` : null)
                                          : null
                                  }
                                                                    style={{
                                                                      default: { 
                                                                          fill: fillColor, 
                                                                          stroke: strokeColor, 
                                                                          strokeWidth: strokeWidth, 
                                                                          outline: "none", 
                                                                          transition: "fill 250ms ease, stroke 250ms ease",
                                                                          cursor: isClickable ? 'pointer' : 'default'
                                                                      },
                                                                      hover: { 
                                                                          fill: fillColor, 
                                                                          stroke: strokeColor, 
                                                                          strokeWidth: strokeWidth, 
                                                                          outline: "none", 
                                                                          cursor: isClickable ? 'pointer' : 'default'
                                                                      },
                                                                      pressed: { 
                                                                        outline: "none",
                                                                      },
                                                                    }}                                />
                              );
                            })}
                          </g>
                        );
                      });
                    }}
                  </Geographies>
                  </ZoomableGroup>
              </ComposableMap>
              <Tooltip id="my-tooltip" style={{ fontSize: '12px', padding: '4px 8px' }} />
            </div>
            
            <div style={{ marginTop: '2rem', gridColumn: '1 / -1' }}>
                <IndigenousRadarChart />
            </div>
          </div>
        </div>
      </main>
    </div>
  );
};

export default Ancestria;
