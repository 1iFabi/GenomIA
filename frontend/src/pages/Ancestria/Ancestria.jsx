import React, { useCallback, useEffect, useState, useMemo, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ChevronDown as ChevronDownIcon,
  ChevronRight as ChevronRightIcon,
  ChevronUp as ChevronUpIcon,
  CircleUserRound as ProfileIcon,
  FlaskConical as PharmacogeneticsIcon,
  House as HomeIcon,
  KeyRound as KeyIcon,
  LayoutGrid as CategoriesIcon,
  LogOut as LogoutIcon,
  Map as AncestryIcon,
  Menu as MenuIcon,
  MessageCircle as ChatIcon,
  ChevronsLeft as ChevronsLeftIcon,
  Settings as SettingsIcon,
  Stethoscope as DiseasesIcon,
  Upload as UploadIcon,
  UserRound as TraitsIcon,
  UserRoundX as RemoveAccountIcon,
  X as CloseIcon,
} from '@animateicons/react/lucide';
import { Expand as FullscreenIcon, Shrink as ExitFullscreenIcon } from 'lucide-react';
import { API_ENDPOINTS, apiRequest, clearToken } from '../../config/api';
import Sidebar from '../../components/Sidebar/Sidebar';
import SectionHeader from '../../components/SectionHeader/SectionHeader';
import { useLatestGenomicsResults } from '../../hooks/useLatestGenomicsResults';
import SpinningCoin from '../../components/SpinningCoin/SpinningCoin';
import TacticalGlobe3D from '../../components/TacticalGlobe3D/TacticalGlobe3D';
import './Ancestria.css';

// URL del mapa mundial (TopoJSON)
const GEO_URL = "https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json";

// Geography remains a reference surface, never a projection of demo results.
const EMPTY_COUNTRY_RESULTS = new Map();

const createBriefHoverIcon = (Icon) => {
  const BriefHoverIcon = (props) => <Icon {...props} duration={0.6} />;
  BriefHoverIcon.displayName = `${Icon.displayName || 'AnimatedIcon'}BriefHover`;
  return BriefHoverIcon;
};

const ancestriaSidebarIconOverrides = {
  profile: createBriefHoverIcon(ProfileIcon),
  profileExpand: createBriefHoverIcon(ChevronDownIcon),
  profileCollapse: createBriefHoverIcon(ChevronUpIcon),
  key: createBriefHoverIcon(KeyIcon),
  removeAccount: createBriefHoverIcon(RemoveAccountIcon),
  categories: createBriefHoverIcon(CategoriesIcon),
  categoriesExpand: createBriefHoverIcon(ChevronDownIcon),
  categoriesCollapse: createBriefHoverIcon(ChevronUpIcon),
  categoryItems: [
    AncestryIcon,
    TraitsIcon,
    PharmacogeneticsIcon,
    DiseasesIcon,
  ].map(createBriefHoverIcon),
  aiExpand: createBriefHoverIcon(ChevronDownIcon),
  aiCollapse: createBriefHoverIcon(ChevronUpIcon),
  chat: createBriefHoverIcon(ChatIcon),
  admin: createBriefHoverIcon(SettingsIcon),
  adminExpand: createBriefHoverIcon(ChevronDownIcon),
  adminCollapse: createBriefHoverIcon(ChevronUpIcon),
  upload: createBriefHoverIcon(UploadIcon),
  home: createBriefHoverIcon(HomeIcon),
  logout: createBriefHoverIcon(LogoutIcon),
};

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

const isObject = (value) => value !== null && typeof value === 'object' && !Array.isArray(value);
const isText = (value) => typeof value === 'string' && value.trim().length > 0;
const isDemoGroup = (value) => typeof value === 'string' && /^Demo group [A-Z]+$/.test(value);
const isNumberInRange = (value, minimum, maximum) => (
  typeof value === 'number' && Number.isFinite(value) && value >= minimum && value <= maximum
);
const isClose = (left, right) => Math.abs(left - right) <= 1e-8;
const hasDemoDisclosure = (value) => isObject(value)
  && value.synthetic === true && value.non_clinical === true && isText(value.disclaimer);

const validateGlobalDisplay = (display) => {
  if (!isObject(display) || display.kind !== 'fictional_components'
    || !Array.isArray(display.components) || !display.components.length) return false;
  const labels = new Set();
  let total = 0;
  for (const component of display.components) {
    if (!isObject(component) || !isDemoGroup(component.label) || labels.has(component.label)
      || !isNumberInRange(component.display_percentage, 0, 100)) return false;
    labels.add(component.label);
    total += component.display_percentage;
  }
  return isClose(total, 100);
};

const validateLocalDisplay = (display) => {
  if (!isObject(display) || display.kind !== 'abstract_segments' || !isObject(display.axis)
    || typeof display.axis.label !== 'string' || !/^Demo axis [A-Z]+$/.test(display.axis.label)
    || !isNumberInRange(display.axis.extent, Number.MIN_VALUE, Number.MAX_SAFE_INTEGER)
    || display.axis.unit !== 'abstract_demo_units'
    || !Array.isArray(display.segments) || !display.segments.length) return false;
  let end = 0;
  for (const segment of display.segments) {
    if (!isObject(segment) || !isDemoGroup(segment.label)
      || !isNumberInRange(segment.offset, 0, display.axis.extent)
      || !isNumberInRange(segment.length, Number.MIN_VALUE, display.axis.extent)
      || !isClose(segment.offset, end)) return false;
    end = segment.offset + segment.length;
    if (!Number.isFinite(end) || end > display.axis.extent) return false;
  }
  return isClose(end, display.axis.extent);
};

// Validate all target modules before exposing either display. Never adopt another module,
// repair malformed values, or supply current fixture values for an older placeholder.
const readAncestryDisplays = (data) => {
  const displays = { global_ancestry: null, local_ancestry: null, invalid: false };
  if (!data) return displays;
  const invalid = () => ({ global_ancestry: null, local_ancestry: null, invalid: true });
  if (!hasDemoDisclosure(data) || !Array.isArray(data.results)) return invalid();
  const seen = new Set();
  for (const result of data.results) {
    if (!isObject(result) || typeof result.module !== 'string') return invalid();
    if (!['global_ancestry', 'local_ancestry'].includes(result.module)) continue;
    if (seen.has(result.module)) return invalid();
    seen.add(result.module);
    const payload = result.payload;
    if (result.result_type !== 'synthetic_placeholder' || result.value_code !== 'SYNTHETIC_NOT_EVALUATED'
      || !hasDemoDisclosure(payload) || payload.module !== result.module
      || payload.state !== 'not_evaluated' || payload.clinically_reviewed !== false) return invalid();
    if (!Object.hasOwn(payload, 'display')) {
      const label = `Synthetic ${result.module.replace('_', ' ')} placeholder`;
      if (payload.label !== label || !Array.isArray(payload.rows) || payload.rows.length !== 1
        || !isObject(payload.rows[0]) || payload.rows[0].label !== label
        || payload.rows[0].state !== 'not_evaluated' || payload.rows[0].value !== null) return invalid();
      continue;
    }
    if (!isDemoGroup(payload.label) || payload.display_only !== true
      || payload.numeric_semantics !== 'arbitrary_demo_only_not_evaluated') return invalid();
    const isValid = result.module === 'global_ancestry'
      ? validateGlobalDisplay(payload.display) : validateLocalDisplay(payload.display);
    if (!isValid) return invalid();
    displays[result.module] = payload.display;
  }
  return displays;
};

// Localize display text only; validation and React keys keep the raw labels.
const formatAncestryLabel = (label) => label
  .replace(/^Demo group ([A-Z]+)$/, 'Grupo $1')
  .replace(/^Demo axis ([A-Z]+)$/, 'Eje $1');

const ancestryStateMessages = {
  loading: 'Cargando datos…',
  empty: 'No hay datos de ancestría disponibles.',
  permission: 'No tienes permiso para consultar estos resultados.',
  error: 'No fue posible cargar los datos.',
};


const Ancestria = () => {
  const [user, setUser] = useState(null);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [isMobile, setIsMobile] = useState(false);
  const results = useLatestGenomicsResults();
  const displays = useMemo(() => readAncestryDisplays(results.data), [results.data]);
  const resultStatus = displays.invalid ? 'error'
    : results.status === 'ready' && !displays.global_ancestry && !displays.local_ancestry
      ? 'empty' : results.status;
  const [isInsightPanelOpen, setIsInsightPanelOpen] = useState(false);
  const [fullscreenMode, setFullscreenMode] = useState(null);
  const [isFullscreenMotionReady, setIsFullscreenMotionReady] = useState(false);
  const [fullscreenAnnouncement, setFullscreenAnnouncement] = useState('');
  const [hoveredCountryCode, setHoveredCountryCode] = useState(null);
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

  const fetchUser = async () => {
    try {
      const response = await apiRequest(API_ENDPOINTS.ME, { method: 'GET' });
      if (response.ok && response.data) {
        setUser(response.data.user || response.data);
      }
    } catch (error) {
      console.error('Error fetching user data:', error);
    }
  };

  const handleLogout = async () => {
    try {
      await apiRequest(API_ENDPOINTS.LOGOUT, { method: 'POST' });
    } catch (error) { console.error(error); }
    clearToken();
    navigate('/');
  };

  const isFullscreenRail = Boolean(isInsightPanelOpen && fullscreenMode);

  const handleMapBackgroundClick = useCallback(() => {
    setHoveredCountryCode(null);
    setIsInsightPanelOpen(false);
  }, []);

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

  const sidebarItems = useMemo(() => [
    { label: 'Ancestría', href: '/dashboard/ancestria' },
    { label: 'Rasgos', href: '/dashboard/rasgos' },
    { label: 'Farmacogenética', href: '/dashboard/farmacogenetica' },
    { label: 'Enfermedades', href: '/dashboard/enfermedades' },
  ], []);

  return (
    <div className="ancestria-dashboard">
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
          items={sidebarItems}
          onLogout={handleLogout}
          user={user}
          isMobileMenuOpen={isMobileMenuOpen}
          setIsMobileMenuOpen={setIsMobileMenuOpen}
          iconOverrides={ancestriaSidebarIconOverrides}
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
              style={fullscreenMode ? undefined : { height: isMobile ? '400px' : '600px' }}
            >
              {!isInsightPanelOpen && (
                <div className="ancestria-map-mark" aria-hidden="true">
                  <SpinningCoin src="/cNormal.png" alt="" size="100%" speed="12s" />
                </div>
              )}

              <TacticalGlobe3D
                geographyUrl={GEO_URL}
                accessibleLabel="Globo de referencia geográfica"
                countryDataByIso={EMPTY_COUNTRY_RESULTS}
                getGeoCountryInfo={getGeoCountryInfo}
                selectedCountryCode={null}
                hoveredCountryCode={hoveredCountryCode}
                onHoverCountry={setHoveredCountryCode}
                focusRequest={null}
                onBackgroundClick={handleMapBackgroundClick}
              />
              <div
                className="ancestria-results-status"
                role={['permission', 'error'].includes(resultStatus) ? 'alert' : 'status'}
                aria-label="Estado de los resultados"
                aria-live={['permission', 'error'].includes(resultStatus) ? 'assertive' : 'polite'}
                aria-busy={results.loading}
                onClick={(event) => event.stopPropagation()}
                onPointerDown={(event) => event.stopPropagation()}
              >
                <p>La geografía es solo exploración; no interpreta estos resultados.</p>
                {ancestryStateMessages[resultStatus] && <p>{ancestryStateMessages[resultStatus]}</p>}
                {!results.loading && <button type="button" aria-label="Reintentar carga de resultados" onClick={results.retry}>Reintentar</button>}
              </div>
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
              <button
                ref={drawerToggleRef}
                className="ancestria-drawer-toggle"
                type="button"
                aria-controls="ancestria-insight-panel"
                aria-expanded={isInsightPanelOpen}
                aria-label={`${isInsightPanelOpen ? 'Cerrar' : 'Abrir'} panel de ancestría`}
                onClick={(event) => {
                  event.stopPropagation();
                  setIsInsightPanelOpen((open) => !open);
                }}
              >
                {isMobile
                  ? (isInsightPanelOpen
                    ? <ChevronDownIcon duration={0.6} aria-hidden="true" />
                    : <ChevronsLeftIcon duration={0.6} aria-hidden="true" />)
                  : (isInsightPanelOpen
                    ? <ChevronRightIcon duration={0.6} aria-hidden="true" />
                    : <ChevronsLeftIcon duration={0.6} aria-hidden="true" />)}
              </button>

              <aside
                id="ancestria-insight-panel"
                className={`ancestria-insight-rail${isInsightPanelOpen ? ' ancestria-insight-rail--open' : ''}${isFullscreenRail ? ' ancestria-insight-rail--fullscreen' : ''}`}
                aria-label="Panel de ancestría"
                aria-hidden={!isInsightPanelOpen}
                aria-busy={results.loading}
                inert={isInsightPanelOpen ? undefined : ''}
                onClick={(event) => event.stopPropagation()}
              >
                <h2 className="ancestria-insight-rail__title">
                  {isInsightPanelOpen && <img src="/cNormal.png" alt="" aria-hidden="true" />}
                  <span>Resultados</span>
                </h2>
                <div className={`ancestria-insight-legend${isFullscreenRail ? ' ancestria-insight-legend--fullscreen' : ''}`}>
                  <section aria-labelledby="ancestria-global-title">
                    <h3 id="ancestria-global-title">Ancestría global</h3>
                    {displays.global_ancestry ? (
                      <ol>
                        {displays.global_ancestry.components.map((component) => (
                          <li key={component.label}>{formatAncestryLabel(component.label)}: {component.display_percentage}%</li>
                        ))}
                      </ol>
                    ) : (
                      <p className="ancestria-insight-rail__message">No hay resultados disponibles para este módulo.</p>
                    )}
                  </section>
                  <section aria-labelledby="ancestria-local-title">
                    <h3 id="ancestria-local-title">Ancestría local</h3>
                    {displays.local_ancestry ? (
                      <>
                        <p>{formatAncestryLabel(displays.local_ancestry.axis.label)}</p>
                        <p>Extensión: {displays.local_ancestry.axis.extent} unidades</p>
                        <ol>
                          {displays.local_ancestry.segments.map((segment, index) => (
                            <li key={index}>
                              {formatAncestryLabel(segment.label)}: inicio {segment.offset} · longitud {segment.length} unidades
                            </li>
                          ))}
                        </ol>
                      </>
                    ) : (
                      <p className="ancestria-insight-rail__message">No hay resultados disponibles para este módulo.</p>
                    )}
                  </section>
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
