import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores(['dist']),
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
    files: ['src/context/NalaContext.jsx'],
    rules: {
      'react-refresh/only-export-components': [
        'error',
        { allowExportNames: ['useNala'] },
      ],
    },
  },
])
