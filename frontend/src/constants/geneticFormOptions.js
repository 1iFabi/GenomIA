// Continentes y sus códigos de población
export const CONTINENTS = {
  'África': { code: 'AFR', countries: ['Nigeria', 'Ghana', 'Kenia', 'Etiopía', 'Sudáfrica'] },
  'Asia': { code: 'EAS', countries: ['China', 'Japón', 'India', 'Tailandia', 'Vietnam', 'Filipinas', 'Indonesia', 'Malasia'] },
  'Europa': { code: 'EUR', countries: ['España', 'Francia', 'Italia', 'Alemania', 'Reino Unido', 'Polonia', 'Suecia', 'Noruega', 'Finlandia', 'Dinamarca', 'Bélgica', 'Holanda', 'Suiza', 'Austria', 'Grecia', 'Portugal', 'Irlanda', 'Hungría'] },
  'América': { code: 'AMR', countries: ['México', 'Estados Unidos', 'Canadá', 'Brasil', 'Argentina', 'Colombia', 'Perú', 'Chile', 'Venezuela', 'Ecuador'] },
  'Oceanía': { code: 'OCE', countries: ['Australia', 'Nueva Zelanda', 'Fiji', 'Papúa Nueva Guinea', 'Samoa'] }
};

// Códigos de población por país (población en 1000 Genomes)
export const COUNTRY_CODES = {
  // Europa
  'España': 'IBS',
  'Francia': 'FRE',
  'Italia': 'TSI',
  'Alemania': 'GER',
  'Reino Unido': 'GBR',
  'Polonia': 'POL',
  'Suecia': 'SWE',
  'Noruega': 'NOR',
  'Finlandia': 'FIN',
  'Dinamarca': 'DEN',
  'Bélgica': 'BEL',
  'Holanda': 'HOL',
  'Suiza': 'SUI',
  'Austria': 'AUT',
  'Grecia': 'GRE',
  'Portugal': 'POR',
  'Irlanda': 'IRE',
  'Hungría': 'HUN',
  
  // Asia
  'China': 'CHI',
  'Japón': 'JPN',
  'India': 'IND',
  'Tailandia': 'THA',
  'Vietnam': 'VIE',
  'Filipinas': 'PHI',
  'Indonesia': 'IDN',
  'Malasia': 'MAL',
  
  // América
  'México': 'MEX',
  'Estados Unidos': 'USA',
  'Canadá': 'CAN',
  'Brasil': 'BRA',
  'Argentina': 'ARG',
  'Colombia': 'COL',
  'Perú': 'PER',
  'Chile': 'CHL',
  'Venezuela': 'VEN',
  'Ecuador': 'ECU',
  
  // África
  'Nigeria': 'NIG',
  'Ghana': 'GHA',
  'Kenia': 'KEN',
  'Etiopía': 'ETH',
  'Sudáfrica': 'RSA',
  
  // Oceanía
  'Australia': 'AUS',
  'Nueva Zelanda': 'NZL',
  'Fiji': 'FIJ',
  'Papúa Nueva Guinea': 'PNG',
  'Samoa': 'SAM'
};

// Fuentes de base de datos
export const DATABASE_SOURCES = [
  'dbSNP',
  'GWAS Catalog',
  'ClinVar',
  'SNPedia',
  'Otra'
];

// Fuentes para ancestría (continente/país)
export const ANCESTRY_SOURCES = [
  'gnomAD',
  '1000 Genomes',
  'SNPedia',
  'Otra'
];

// Tipos de evidencia
export const EVIDENCE_TYPES = [
  'Clínico',
  'GWAS',
  'Experimental',
  'Otra'
];
