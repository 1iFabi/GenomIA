// The five result modules, in the same order everywhere: top to bottom on the dashboard helix,
// left to right on the module bar. `title` invites in, `cta` names what opening it shows,
// `short` names it where room is tight (the phone's module bar), `tint`/`ink` colour its page, `rung` is the colour of its stretch on the helix (blender/dna_dashboard.py).
export const RESULT_MODULES = [
  { key: 'global_ancestry', name: 'Ancestría', title: 'Tus raíces', cta: 'Explora tus orígenes', href: '/dashboard/ancestria', tint: '#E8D4F0', ink: '#4A1C5F', rung: '#9b72c9' },
  { key: 'pharmacogenetics', name: 'Farmacogenética', title: 'Tus remedios', short: 'Fármacos', cta: 'Mira tus medicamentos', href: '/dashboard/farmacogenetica', tint: '#EDE6DF', ink: '#3E3A37', rung: '#a88d74' },
  { key: 'traits', name: 'Rasgos', title: 'Lo que te hace tú', cta: 'Descubre tus rasgos', href: '/dashboard/rasgos', tint: '#D4E8F8', ink: '#1E3A5F', rung: '#4f8fd6' },
  { key: 'polygenic_risk', name: 'Riesgo poligénico', title: 'Frente al promedio', short: 'Poligénico', cta: 'Compara tus riesgos', href: '/dashboard/enfermedades#polygenic_risk', tint: '#FBE5D3', ink: '#7A3410', rung: '#e5874a' },
  { key: 'monogenic_risk', name: 'Riesgo monogénico', title: 'Gen por gen', short: 'Monogénico', cta: 'Revisa tus variantes', href: '/dashboard/enfermedades#monogenic_risk', tint: '#E0F0E4', ink: '#3A5F3E', rung: '#5aa874' },
];

// The module on show on the dashboard helix; a module page writes its own so "back" lands on it.
export const SLOT_KEY = 'genomia.dashboard.module';

export const GUIDE_HREF = '/dashboard/modulos';
