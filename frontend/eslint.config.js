import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores(['dist']),
  // El motor de hairline, copiado byte a byte de la skill hairline-create: se
  // consume tal cual, así que no se lintea (sus `catch {}` vacíos son suyos).
  globalIgnores(['src/pages/Descubre/visuals/hairline/kernel.js']),
  {
    files: ['**/*.{js,jsx}'],
    extends: [
      js.configs.recommended,
      reactHooks.configs['recommended-latest'],
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
      parserOptions: {
        ecmaVersion: 'latest',
        ecmaFeatures: { jsx: true },
        sourceType: 'module',
      },
    },
    rules: {
      'no-unused-vars': ['error', { varsIgnorePattern: '^[A-Z_]' }],
    },
  },
  {
    // Una figura de hairline vive en el banco de pruebas de la skill: toma sus
    // primitivas de `HL` y se registra llamando a `hairline`. Son globales por
    // contrato, así que aquí se declaran.
    files: ['src/pages/Descubre/visuals/hairline/query.js'],
    languageOptions: { globals: { HL: 'readonly', hairline: 'readonly' } },
  },
  {
    // Los componentes shadcn/ui (generados) exportan helpers (variants, cn)
    // junto a componentes; eso dispara react-refresh/only-export-components.
    files: ['src/components/ui/**/*.{js,jsx}'],
    rules: {
      'react-refresh/only-export-components': 'off',
    },
  },
  {
    // Keep the existing import paths working while the implementations live
    // in refresh-safe sibling modules.
    files: ['src/components/charts/chart-stat-flow.jsx'],
    rules: {
      'react-refresh/only-export-components': [
        'error',
        { allowExportNames: ['defaultChartStatFlowFormat'] },
      ],
    },
  },
  {
    // Keep the existing chart imports working while constants and hooks are
    // implemented in refresh-safe sibling modules.
    files: ['src/components/charts/pie-context.jsx'],
    rules: {
      'react-refresh/only-export-components': [
        'error',
        {
          allowExportNames: [
            'pieCssVars',
            'defaultPieColors',
            'usePieStable',
            'usePieHover',
            'usePie',
          ],
        },
      ],
    },
  },
  {
    // Keep existing consumers working while the hook implementation lives
    // in a refresh-safe sibling module.
    files: ['src/context/GenominContext.jsx'],
    rules: {
      'react-refresh/only-export-components': [
        'error',
        { allowExportNames: ['useGenomin'] },
      ],
    },
  },
])
