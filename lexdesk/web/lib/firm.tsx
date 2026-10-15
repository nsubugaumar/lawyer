"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api } from "./api";
import { useAuth } from "./auth";

export type Social = { network: string; label: string; url: string };
export type PublicFirm = {
  name: string;
  tagline: string;
  about: string;
  founded_year: number | null;
  theme: string;
  logo_url: string;
  practice_areas: { key: string; label: string }[];
  testimonials: { quote: string; name: string; detail: string }[];
  phone: string;
  whatsapp_number: string;
  whatsapp_link: string;
  email: string;
  address: string;
  map_url: string;
  socials: Social[];
  office_hours: { opens: string; closes: string; days: number[] };
  booking_enabled: boolean;
  slot_minutes: number;
  booking_days_ahead: number;
};

const FALLBACK: PublicFirm = {
  name: "LexDesk Advocates",
  tagline: "",
  about: "",
  founded_year: null,
  theme: "navy_brass",
  logo_url: "",
  practice_areas: [],
  testimonials: [],
  phone: "",
  whatsapp_number: "",
  whatsapp_link: "",
  email: "",
  address: "",
  map_url: "",
  socials: [],
  office_hours: { opens: "08:30", closes: "17:30", days: [0, 1, 2, 3, 4] },
  booking_enabled: true,
  slot_minutes: 30,
  booking_days_ahead: 90,
};

type FirmState = { firm: PublicFirm; loaded: boolean; refresh: () => Promise<void> };
const FirmContext = createContext<FirmState>({ firm: FALLBACK, loaded: false, refresh: async () => undefined });

export function FirmProvider({ children }: { children: React.ReactNode }) {
  const [firm, setFirm] = useState<PublicFirm>(FALLBACK);
  const [loaded, setLoaded] = useState(false);
  const { user, ready } = useAuth();
  const signedInFirm = user?.firm?.id ?? null;

  const refresh = useCallback(async () => {
    try {
      const data = await api<PublicFirm>("/firm/public/");
      setFirm(data);
      try {
        localStorage.setItem("lexdesk.theme", data.theme);
      } catch {
        /* private mode */
      }
    } catch {
      /* keep the fallback; the site still works */
    } finally {
      setLoaded(true);
    }
  }, []);

  // Visitors see the firm at this address; signed in, you see your own firm.
  useEffect(() => {
    if (ready) refresh();
  }, [refresh, ready, signedInFirm]);

  useEffect(() => {
    document.documentElement.dataset.theme = firm.theme;
  }, [firm.theme]);

  return <FirmContext.Provider value={{ firm, loaded, refresh }}>{children}</FirmContext.Provider>;
}

export const useFirm = () => useContext(FirmContext);

export const DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

export function hoursLabel(firm: PublicFirm) {
  const days = firm.office_hours.days;
  const contiguous = days.length > 1 && days.every((d, i) => i === 0 || d === days[i - 1] + 1);
  const dayText = contiguous
    ? `${DAY_NAMES[days[0]].slice(0, 3)}–${DAY_NAMES[days[days.length - 1]].slice(0, 3)}`
    : days.map((d) => DAY_NAMES[d].slice(0, 3)).join(", ");
  return `${dayText}, ${firm.office_hours.opens}–${firm.office_hours.closes}`;
}
