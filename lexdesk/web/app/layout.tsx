import type { Metadata, Viewport } from "next";
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

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,400..700;1,9..144,400..600&family=Inter:wght@400;500;600;700&display=swap"
        />
      </head>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
