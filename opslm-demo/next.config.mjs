/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Keep local build concurrency bounded on the shared workstation.
  experimental: { cpus: 2 },
  turbopack: { root: import.meta.dirname },
};

export default nextConfig;
