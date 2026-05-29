/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // The verify/live API routes shell out to the Python core and read repo files,
  // so they MUST run on the Node.js server runtime (never the edge runtime) and
  // must not be statically prerendered.
  experimental: {},
};

export default nextConfig;
