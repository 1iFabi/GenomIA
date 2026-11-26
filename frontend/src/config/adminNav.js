// The admin panel's three sections, shown on the same module bar as the client results.
// `tint`/`ink`/`rung` colour each page like a result module; all start from the guide's blue.
export const ADMIN_SECTIONS = [
  { key: 'admin_overview', name: 'Resumen', title: 'Resumen', href: '/dashboard', tint: '#E3ECFA', ink: '#0F2341', rung: '#4F8FD6' },
  { key: 'admin_users', name: 'Usuarios', title: 'Usuarios', href: '/dashboard/admin/usuarios', tint: '#DCEFED', ink: '#123A3A', rung: '#3E9A93' },
  { key: 'admin_activity', name: 'Actividad', title: 'Actividad', href: '/dashboard/admin/actividad', tint: '#E6E4F5', ink: '#2E2A52', rung: '#7A71C9' },
];

export const ADMIN_ROLE_LABEL = 'Administrador GenomIA';
