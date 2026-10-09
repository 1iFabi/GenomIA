import React, { useCallback, useEffect, useState, useMemo, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ChevronDown as ChevronDownIcon,
  ChevronUp as ChevronUpIcon,
  Menu as MenuIcon,
  X as CloseIcon,
} from '@animateicons/react/lucide';
import { animatedSidebarIcons } from '../../components/Sidebar/animatedSidebarIcons';
import { Expand as FullscreenIcon, Shrink as ExitFullscreenIcon } from 'lucide-react';
import { API_ENDPOINTS, apiRequest, clearToken } from '../../config/api';
import { RESULT_NAV_ITEMS } from '../../config/resultNav';
import Sidebar from '../../components/Sidebar/Sidebar';
import SectionHeader from '../../components/SectionHeader/SectionHeader';
import { moduleRows, useLatestGenomicsResults } from '../../hooks/useLatestGenomicsResults';
import { useSession } from '../../hooks/useSession';
import SpinningCoin from '../../components/SpinningCoin/SpinningCoin';
import TacticalGlobe3D from '../../components/TacticalGlobe3D/TacticalGlobe3D';
import ContinentExplorer from '../../components/ContinentExplorer/ContinentExplorer';
import { CONTINENT_LABELS, buildContinentShapes, groupByContinent } from '../../components/ContinentExplorer/continents';
import './Ancestria.css';
import { SkeletonBlock } from '../../components/DashboardSkeleton/DashboardSkeleton';

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

const continentByCode = Object.fromEntries(Object.values(countryInfo).map((info) => [info.code, info.continent]));
const continentOfCode = (code) => continentByCode[code] ?? null;

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

// Paleta harmónica: púrpura → azules progresivos (coolors.co)
const ANCESTRY_COLORS = { NAT: '#203590', EUR: '#230462', EAS: '#6083c5', AFR: '#96b8db' };
const ancestryColor = (code) => ANCESTRY_COLORS[code] || '#748CAB';
// Mirrors the globe's continent-view fills so the legend always matches what is painted.
const MAP_COLORS = { withAncestry: '#6083C5', ancestry: '#203590', continent: '#96B8DB', none: '#E6E5E0' };
const ancestryStateMessages = {
  loading: 'Cargando datos…',
  empty: 'No hay datos de ancestría disponibles.',
  permission: 'No tienes permiso para consultar estos resultados.',
  error: 'No fue posible cargar los datos.',
};


const Ancestria = () => {
  const { user } = useSession();
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [isMobile, setIsMobile] = useState(false);
  const results = useLatestGenomicsResults();
  const globalAncestry = moduleRows(results, 'global_ancestry');
  const localAncestry = moduleRows(results, 'local_ancestry');
  const resultStatus = results.status === 'ready' && !globalAncestry.length && !localAncestry.length
    ? 'empty' : results.status;
  const [isInsightPanelOpen, setIsInsightPanelOpen] = useState(false);
  const [fullscreenMode, setFullscreenMode] = useState(null);
  const [isFullscreenMotionReady, setIsFullscreenMotionReady] = useState(false);
  const [fullscreenAnnouncement, setFullscreenAnnouncement] = useState('');
  const [hoveredCountryCode, setHoveredCountryCode] = useState(null);
  const [selectedCountryCode, setSelectedCountryCode] = useState(null);
  const [focusRequest, setFocusRequest] = useState(null);
  const [activeContinent, setActiveContinent] = useState(null);
  const [hoveredContinent, setHoveredContinent] = useState(null);
  const [geographies, setGeographies] = useState([]);
  const countryDataByIso = useMemo(() => new Map(globalAncestry.filter((row) => row.country_code).map((row) => [
    row.country_code, {
      name: row.country,
      population: row.label,
      group: row.group_label,
      color: ancestryColor(row.group),
      percentage: row.proportion * 100,
    },
  ])), [globalAncestry]);
  const ancestryGroups = useMemo(() => {
    const groups = new Map();
    for (const row of globalAncestry) {
      const code = row.group || row.population;
      const group = groups.get(code) || { code, label: row.group_label || row.label, color: ancestryColor(code), proportion: 0 };
      group.proportion += row.proportion;
      groups.set(code, group);
    }
    return [...groups.values()];
  }, [globalAncestry]);
  const continents = useMemo(() => groupByContinent(globalAncestry, continentOfCode), [globalAncestry]);
  const continentShapes = useMemo(
    () => buildContinentShapes(geographies, getGeoCountryInfo, continents),
    [geographies, continents],
  );
  const selectedRow = globalAncestry.find((row) => row.country_code === selectedCountryCode) || null;
  const selectedRank = selectedRow
    ? [...globalAncestry].sort((a, b) => b.proportion - a.proportion).indexOf(selectedRow) + 1 : null;
  const [cohort, setCohort] = useState(null);
  // Fetched only when the comparison tab is opened, so the default view makes one results request.
  const loadCohort = useCallback(() => {
    if (cohort && cohort.status !== 'error') return;
    setCohort({ status: 'loading' });
    apiRequest(API_ENDPOINTS.ANCESTRY_COHORT, { method: 'GET' }).then(({ ok, data }) => {
      setCohort(ok && data ? { status: 'ready', data } : { status: 'error' });
    });
  }, [cohort]);

  // World > continent > country: each step turns the globe toward what was chosen.
  const openContinent = useCallback((key) => {
    setActiveContinent(key);
    setSelectedCountryCode(null);
    setHoveredContinent(null);
    setIsInsightPanelOpen(true);
    setFocusRequest({ continent: key, requestId: Date.now() });
  }, []);
  const openCountry = useCallback((row) => {
    setActiveContinent(continentOfCode(row.country_code));
    setSelectedCountryCode(row.country_code);
    setIsInsightPanelOpen(true);
    setFocusRequest({ countryCode: row.country_code, requestId: Date.now() });
  }, []);
  const goToWorld = useCallback(() => {
    setActiveContinent(null);
    setSelectedCountryCode(null);
  }, []);
  const continentView = useMemo(() => ({
    active: activeContinent,
    withAncestry: new Set(continents.map((continent) => continent.key)),
    labels: CONTINENT_LABELS,
    hovered: hoveredContinent,
    onSelect: openContinent,
    onHover: setHoveredContinent,
  }), [activeContinent, continents, hoveredContinent, openContinent]);
  const mapContainerRef = useRef(null);
  const fullscreenToggleRef = useRef(null);
  const drawerToggleRef = useRef(null);

  useEffect(() => {
    const syncFullscreenState = () => {
      if (document.fullscreenElement === mapContainerRef.current) {
        setFullscreenMode('native');
        setFullscreenAnnouncement('');
        return;
      }

      setFullscreenMode((currentMode) => (currentMode === 'native' ? null : currentMode));
    };

    document.addEventListener('fullscreenchange', syncFullscreenState);
    return () => document.removeEventListener('fullscreenchange', syncFullscreenState);
  }, []);

  useEffect(() => {
    if (!fullscreenMode) {
      setIsFullscreenMotionReady(false);
      return undefined;
    }

    setIsFullscreenMotionReady(false);
    const frame = window.requestAnimationFrame(() => setIsFullscreenMotionReady(true));
    return () => window.cancelAnimationFrame(frame);
  }, [fullscreenMode]);

  useEffect(() => {
    if (fullscreenMode !== 'fallback') return undefined;

    const closeFallbackOnEscape = (event) => {
      if (event.key !== 'Escape') return;
      event.preventDefault();
      setFullscreenMode(null);
      setFullscreenAnnouncement('');
    };

    document.addEventListener('keydown', closeFallbackOnEscape);
    return () => document.removeEventListener('keydown', closeFallbackOnEscape);
  }, [fullscreenMode]);

  useEffect(() => {
    if (fullscreenMode !== 'fallback' || 'fullscreenElement' in document) return undefined;

    // Keep the inactive value consistent in DOM implementations that omit the Fullscreen API.
    Object.defineProperty(document, 'fullscreenElement', { configurable: true, value: null });
    return () => {
      if (document.fullscreenElement === null) delete document.fullscreenElement;
    };
  }, [fullscreenMode]);

  const navigate = useNavigate();

  useEffect(() => {
    const checkMobile = () => {
      const mobile = window.innerWidth <= 1024;
      setIsMobile(mobile);
      if (!mobile) setIsMobileMenuOpen(false);
    };
    
    checkMobile();
    window.addEventListener('resize', checkMobile);
    return () => window.removeEventListener('resize', checkMobile);
  }, []);

  const handleLogout = async () => {
    try {
      await clearToken();
    } catch (error) { console.error(error); }
    navigate('/');
  };

  // Desktop keeps the panel as a fixed column; mobile keeps it as a sheet behind the toggle.
  const isPanelShown = !isMobile || isInsightPanelOpen;
  const isFullscreenRail = Boolean(isPanelShown && fullscreenMode);

  // Opening the mobile sheet scrolls the globe to the top of the screen, so both stay in view together.
  useEffect(() => {
    if (!isMobile || !isInsightPanelOpen || fullscreenMode) return undefined;
    const frame = window.requestAnimationFrame(() => {
      const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
      mapContainerRef.current?.scrollIntoView?.({ block: 'start', behavior: reduce ? 'auto' : 'smooth' });
    });
    const closeOnEscape = (event) => {
      if (event.key !== 'Escape') return;
      setIsInsightPanelOpen(false);
      drawerToggleRef.current?.focus();
    };
    document.addEventListener('keydown', closeOnEscape);
    return () => {
      window.cancelAnimationFrame(frame);
      document.removeEventListener('keydown', closeOnEscape);
    };
  }, [isMobile, isInsightPanelOpen, fullscreenMode]);

  // A click outside the open continent (ocean, space, or a country elsewhere without ancestry) steps back to the
  // world view; with nothing open, it only dismisses the mobile sheet.
  const handleMapBackgroundClick = useCallback(() => {
    setHoveredCountryCode(null);
    if (activeContinent) goToWorld();
    else setIsInsightPanelOpen(false);
  }, [activeContinent, goToWorld]);
  const handleNoDataCountryClick = useCallback((info) => {
    if (activeContinent && info?.continent !== activeContinent) goToWorld();
  }, [activeContinent, goToWorld]);

  const handleFullscreenToggle = useCallback(async (event) => {
    event.stopPropagation();
    const mapCard = mapContainerRef.current;
    if (!mapCard) return;

    if (fullscreenMode === 'fallback') {
      setFullscreenMode(null);
      setFullscreenAnnouncement('');
      return;
    }

    if (fullscreenMode === 'native') {
      if (typeof document.exitFullscreen !== 'function') return;
      try {
        await document.exitFullscreen();
      } catch {
        // Keep the expanded control available if the browser refuses to exit.
      }
      if (document.fullscreenElement !== mapCard) setFullscreenMode(null);
      return;
    }

    if (typeof mapCard.requestFullscreen !== 'function' || document.fullscreenEnabled === false) {
      setFullscreenMode('fallback');
      setFullscreenAnnouncement('La pantalla completa del navegador no está disponible. Se activó la vista expandida del mapa.');
      return;
    }

    try {
      await mapCard.requestFullscreen();
      if (document.fullscreenElement === mapCard) {
        setFullscreenMode('native');
        setFullscreenAnnouncement('');
      } else {
        setFullscreenMode('fallback');
        setFullscreenAnnouncement('La pantalla completa del navegador no está disponible. Se activó la vista expandida del mapa.');
      }
    } catch {
      if (document.fullscreenElement === mapCard) {
        setFullscreenMode('native');
        return;
      }
      setFullscreenMode('fallback');
      setFullscreenAnnouncement('No se pudo abrir la pantalla completa del navegador. Se activó la vista expandida del mapa.');
    }
  }, [fullscreenMode]);

  useEffect(() => {
    const button = fullscreenToggleRef.current;
    if (!button) return undefined;

    const stopFullscreenClickPropagation = (event) => {
      event.stopPropagation();
      handleFullscreenToggle(event);
    };

    button.addEventListener('click', stopFullscreenClickPropagation);
    return () => button.removeEventListener('click', stopFullscreenClickPropagation);
  }, [handleFullscreenToggle]);


  return (
    <div className={`ancestria-dashboard${isMobile && isInsightPanelOpen ? ' ancestria-dashboard--sheet-open' : ''}`}>
      {isMobile && (
        <button
          className="ancestria-dashboard__burger"
          type="button"
          aria-label={isMobileMenuOpen ? 'Cerrar menú' : 'Abrir menú'}
          aria-expanded={isMobileMenuOpen}
          onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
        >
          {isMobileMenuOpen
            ? <CloseIcon size={24} duration={0.6} aria-hidden="true" />
            : <MenuIcon size={24} duration={0.6} aria-hidden="true" />}
        </button>
      )}

      <aside className="ancestria-dashboard__sidebar">
        <Sidebar
          items={RESULT_NAV_ITEMS}
          onLogout={handleLogout}
          user={user}
          isMobileMenuOpen={isMobileMenuOpen}
          setIsMobileMenuOpen={setIsMobileMenuOpen}
          iconOverrides={animatedSidebarIcons}
        />
      </aside>

      <main className="ancestria-dashboard__main">
        <div className="ancestria-page">
          <SectionHeader
                title={(
                <span className="ancestria-page__editorial-title">
                  <span className="ancestria-page__title-main">
                    <span className="ancestria-page__title-prefix">ANCE</span><span className="ancestria-page__title-accent">STRÍA</span>
                  </span>
                  <span className="ancestria-page__title-separator" aria-hidden="true">|</span>
                  <span className="ancestria-page__title-supporting">
                    Explora tus resultados y un mapa de referencia geográfica.
                  </span>
                </span>
               )} />

          <div className="ancestria-page__content">
            <div
              ref={mapContainerRef}
              className={`ancestria-page__chart-card${isInsightPanelOpen ? ' ancestria-page__chart-card--drawer-open' : ''}${fullscreenMode ? ` ancestria-page__chart-card--fullscreen-${fullscreenMode} ancestria-page__chart-card--fullscreen-motion-${isFullscreenMotionReady ? 'settled' : 'entering'}` : ''}`}
            >
              <div className="ancestria-map-stage">
              <div className="ancestria-map-mark" aria-hidden="true">
                <SpinningCoin src="/cNormal.png" alt="" size="100%" speed="12s" />
              </div>

              <TacticalGlobe3D
                geographyUrl={GEO_URL}
                accessibleLabel="Globo de ancestría por país"
                countryDataByIso={countryDataByIso}
                getGeoCountryInfo={getGeoCountryInfo}
                selectedCountryCode={selectedCountryCode}
                hoveredCountryCode={hoveredCountryCode}
                onHoverCountry={setHoveredCountryCode}
                onSelectCountry={(_data, info) => {
                  const row = globalAncestry.find((item) => item.country_code === info.code);
                  if (row) openCountry(row);
                }}
                focusRequest={focusRequest}
                onBackgroundClick={handleMapBackgroundClick}
                onNoDataCountryClick={handleNoDataCountryClick}
                continentView={continentView}
                onGeographiesLoaded={setGeographies}
              />
              {resultStatus === 'ready' && continents.length > 0 && (
                <ul className="ancestria-map-legend" aria-label="Leyenda del mapa">
                  {(activeContinent
                    ? [
                      [MAP_COLORS.ancestry, 'Países con tu ancestría'],
                      [MAP_COLORS.continent, `Resto de ${CONTINENT_LABELS[activeContinent] || activeContinent}`],
                      [MAP_COLORS.none, 'Otros continentes'],
                    ]
                    : [
                      [MAP_COLORS.withAncestry, 'Continente con tu ancestría'],
                      [MAP_COLORS.none, 'Sin ancestría registrada'],
                    ]
                  ).map(([color, label]) => (
                    <li key={label}>
                      <span className="ancestria-map-legend__swatch" style={{ background: color }} />
                      {label}
                    </li>
                  ))}
                </ul>
              )}
              {resultStatus !== 'ready' && (
                <div
                  className={`ancestria-results-status${resultStatus === 'loading' ? ' ancestria-results-status--loading' : ''}`}
                  role={['permission', 'error'].includes(resultStatus) ? 'alert' : 'status'}
                  aria-label="Estado de los resultados"
                  aria-live={['permission', 'error'].includes(resultStatus) ? 'assertive' : 'polite'}
                  aria-busy={results.loading}
                  onClick={(event) => event.stopPropagation()}
                  onPointerDown={(event) => event.stopPropagation()}
                >
                  {ancestryStateMessages[resultStatus] && (
                    <p className={resultStatus === 'loading' ? 'dashboard-skeleton__announcement' : undefined}>
                      {ancestryStateMessages[resultStatus]}
                    </p>
                  )}
                  {resultStatus === 'loading' && (
                    <div className="ancestria-loading-summary" aria-hidden="true">
                      <SkeletonBlock className="ancestria-loading-summary__heading" />
                      {[0, 1, 2].map((index) => (
                        <div className="ancestria-loading-summary__row" key={index}>
                          <SkeletonBlock className="ancestria-loading-summary__marker" />
                          <SkeletonBlock className="ancestria-loading-summary__label" />
                          <SkeletonBlock className="ancestria-loading-summary__share" />
                        </div>
                      ))}
                    </div>
                  )}
                  {!results.loading && <button type="button" aria-label="Reintentar carga de resultados" onClick={results.retry}>Reintentar</button>}
                </div>
              )}
              <button
                ref={fullscreenToggleRef}
                className="ancestria-fullscreen-toggle"
                type="button"
                aria-label={fullscreenMode ? 'Salir de pantalla completa' : 'Expandir mapa a pantalla completa'}
                aria-pressed={fullscreenMode !== null}
                onPointerDown={(event) => event.stopPropagation()}
              >
                {fullscreenMode
                  ? <ExitFullscreenIcon aria-hidden="true" />
                  : <FullscreenIcon aria-hidden="true" />}
              </button>
              <span
                className="ancestria-fullscreen-status"
                role={fullscreenAnnouncement ? 'status' : undefined}
                aria-live="polite"
              >
                {fullscreenAnnouncement}
              </span>
              </div>
              {isMobile && (
                <button
                  ref={drawerToggleRef}
                  className="ancestria-drawer-toggle"
                  type="button"
                  aria-controls="ancestria-insight-panel"
                  aria-expanded={isInsightPanelOpen}
                  onClick={(event) => {
                    event.stopPropagation();
                    setIsInsightPanelOpen((open) => !open);
                  }}
                >
                  {isInsightPanelOpen
                    ? <ChevronDownIcon duration={0.6} aria-hidden="true" />
                    : <ChevronUpIcon duration={0.6} aria-hidden="true" />}
                  <span>{isInsightPanelOpen ? 'Ocultar' : 'Ver tus orígenes'}</span>
                </button>
              )}

              <aside
                id="ancestria-insight-panel"
                className={`ancestria-insight-rail${isPanelShown ? ' ancestria-insight-rail--open' : ''}${isFullscreenRail ? ' ancestria-insight-rail--fullscreen' : ''}`}
                aria-label="Panel de ancestría"
                aria-hidden={!isPanelShown}
                aria-busy={results.loading}
                inert={isPanelShown ? undefined : ''}
                onClick={(event) => event.stopPropagation()}
              >
                <div className={`ancestria-insight-legend${isFullscreenRail ? ' ancestria-insight-legend--fullscreen' : ''}`}>
                <ContinentExplorer
                  status={resultStatus}
                  continents={continents}
                  shapes={continentShapes}
                  groups={ancestryGroups}
                  activeContinent={activeContinent}
                  selectedRow={selectedRow}
                  selectedRank={selectedRank}
                  onOpenContinent={openContinent}
                  onOpenCountry={openCountry}
                  onGoToWorld={goToWorld}
                  onHoverContinent={setHoveredContinent}
                  onHoverCountry={setHoveredCountryCode}
                  cohort={cohort}
                  onRequestCohort={loadCohort}
                />
                </div>
              </aside>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
};

export default Ancestria;
