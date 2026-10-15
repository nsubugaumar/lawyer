import type { NextConfig } from "next";

// The API runs on its own server. Proxying it through the web app keeps the
// browser on one origin, so the HttpOnly refresh cookie (SameSite=Strict)
// just works and no CORS is needed.
const API_ORIGIN = process.env.LEXDESK_API_ORIGIN ?? "http://127.0.0.1:8000";

// Content Security Policy for every page: scripts and connections only from
// LexDesk itself, fonts only from Google Fonts, no framing, no plugins.
// ('unsafe-inline' scripts are needed by Next.js hydration and the theme
// script; everything external is still blocked.)
const csp = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline'",
  "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
  "font-src 'self' https://fonts.gstatic.com",
  "img-src 'self' data: blob:",
  "connect-src 'self'",
  "frame-src 'self' blob:",
  "worker-src 'self'",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
].join("; ");

const securityHeaders = [
  { key: "Content-Security-Policy", value: csp },
  { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "same-origin" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
];

const config: NextConfig = {
  reactStrictMode: true,
  output: "standalone",
  // LexDesk uses no optimised images; turning the optimiser off removes it
  // (and its image-parsing libraries) from the server's attack surface.
  images: { unoptimized: true },
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
