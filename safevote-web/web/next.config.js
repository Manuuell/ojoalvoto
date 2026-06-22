/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: false,
  output: 'standalone',
  async rewrites() {
    // Proxy /api/* al backend NestJS (evita CORS y centraliza el dominio)
    const api = process.env.API_URL || 'http://api:8000';
    return [{ source: '/api/:path*', destination: `${api}/api/:path*` }];
  },
};
module.exports = nextConfig;
