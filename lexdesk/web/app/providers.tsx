"use client";

import { useEffect } from "react";
import { ToastProvider } from "@/components/ui";
import { AuthProvider } from "@/lib/auth";
import { FirmProvider } from "@/lib/firm";

export function Providers({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    // Installable on phones as an app; works through patchy court-house signal.
    if ("serviceWorker" in navigator && process.env.NODE_ENV === "production") {
      navigator.serviceWorker.register("/sw.js").catch(() => undefined);
    }
  }, []);

  return (
    <AuthProvider>
      <FirmProvider>
        <ToastProvider>{children}</ToastProvider>
      </FirmProvider>
    </AuthProvider>
  );
}
