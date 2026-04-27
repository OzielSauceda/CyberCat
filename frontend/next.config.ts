import type { NextConfig } from "next"

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/v1/:path*",
        destination: "http://backend:8000/v1/:path*",
      },
    ]
  },
}

export default nextConfig
