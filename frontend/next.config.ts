import type { NextConfig } from "next";

const BACKEND_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8040";

const nextConfig: NextConfig = {
  output: "standalone",
  reactStrictMode: false,
  async rewrites() {
    return [
      {
        source: "/health",
        destination: `${BACKEND_URL}/health`,
      },
    ];
  },
};

export default nextConfig;
