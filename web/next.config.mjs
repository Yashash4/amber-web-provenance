/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // The deployed demo is self-contained and client-renderable: it renders the
  // REAL packet values bundled at build time (app/data/packet.ts) with no
  // request-time filesystem reads and no Python/child-process spawns, so it
  // deploys cleanly to a serverless/static host (Vercel) without a server-side
  // exception. The full-stack build keeps the Python verify_packet path.
  experimental: {},
};

export default nextConfig;
