import type { NextConfig } from "next";

// The API runs on its own server. Proxying it through the web app keeps the
// browser on one origin, so the HttpOnly refresh cookie (SameSite=Strict)
// just works and no CORS is needed.
const API_ORIGIN = process.env.LEXDESK_API_ORIGIN ?? "http://127.0.0.1:8000";

const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "same-origin" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
];

const config: NextConfig = {
  reactStrictMode: true,
  output: "standalone",
  poweredByHeader: false,
  async rewrites() {
    // Django URLs end in a slash; keep it exactly as the app sent it.
    return [
      { source: "/api/:path*/", destination: `${API_ORIGIN}/api/:path*/` },
      { source: "/api/:path*", destination: `${API_ORIGIN}/api/:path*` },
    ];
  },
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
  skipTrailingSlashRedirect: true,
};

export default config;
