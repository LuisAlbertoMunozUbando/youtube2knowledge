import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  poweredByHeader: false,
  reactStrictMode: true,
  // `npm run build` runs `tsc --noEmit` first. Avoid running Next's integrated
  // validator a second time; that phase can terminate without diagnostics in
  // Vercel while the standalone typecheck succeeds.
  typescript: {
    ignoreBuildErrors: true,
  },
};

export default nextConfig;
