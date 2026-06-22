export const metadata = {
  title: 'Ojo al Voto — Auditoría ciudadana de las elecciones 2026',
  description: 'Verificación colaborativa de las actas E-14 de las elecciones presidenciales de Colombia 2026. Transparencia ciudadana, abierta y sin fines de lucro.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es">
      <body style={{ margin: 0, background: '#eef2f6', color: '#0f172a', fontFamily: 'system-ui, sans-serif' }}>
        {children}
      </body>
    </html>
  );
}
