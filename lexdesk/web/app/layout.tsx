import type { Metadata, Viewport } from "next";
import { headers } from "next/headers";
import "./globals.css";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: { default: "LexDesk", template: "%s · LexDesk" },
  description: "Trusted counsel. Book a consultation, follow your case and talk to your lawyer, all in one place.",
  manifest: "/manifest.webmanifest",
  icons: { icon: "/icon.svg", apple: "/icon.svg" },
  appleWebApp: { capable: true, title: "LexDesk", statusBarStyle: "default" },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: "#f7f4ee",
};

// Applies the firm's colours and the person's light/dark choice before first
// paint, so nothing flashes from one look to another.
const themeScript = `try{var d=document.documentElement,t=localStorage.getItem("lexdesk.theme"),m=localStorage.getItem("lexdesk.mode")||"light";if(t)d.dataset.theme=t;d.dataset.mode=m==="system"?(matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light"):m}catch(e){document.documentElement.dataset.mode="light"}`;

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  // The per-request code (nonce) from middleware.ts: only scripts carrying it run.
  const nonce = (await headers()).get("x-nonce") ?? undefined;
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script nonce={nonce} dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
