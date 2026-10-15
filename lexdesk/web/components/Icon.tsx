/* A small, consistent line-icon set (24px grid, 1.75 stroke). */

const P: Record<string, React.ReactNode> = {
  home: <><path d="M3 10.5 12 3l9 7.5" /><path d="M5 9.5V20a1 1 0 0 0 1 1h4v-6h4v6h4a1 1 0 0 0 1-1V9.5" /></>,
  calendar: <><rect x="3" y="4.5" width="18" height="16.5" rx="2.5" /><path d="M3 9.5h18M8 2.5v4M16 2.5v4" /></>,
  briefcase: <><rect x="3" y="7" width="18" height="13" rx="2.5" /><path d="M8.5 7V5.5A1.5 1.5 0 0 1 10 4h4a1.5 1.5 0 0 1 1.5 1.5V7M3 12.5h18" /></>,
  users: <><circle cx="9" cy="8" r="3.5" /><path d="M2.5 20c.6-3.4 3.3-5.5 6.5-5.5s5.9 2.1 6.5 5.5" /><path d="M16 4.6a3.5 3.5 0 0 1 0 6.8M18 14.8c1.9.7 3.2 2.5 3.5 5.2" /></>,
  user: <><circle cx="12" cy="8" r="4" /><path d="M4 21c.8-4 4-6.5 8-6.5s7.2 2.5 8 6.5" /></>,
  clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3.5 2" /></>,
  file: <><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" /><path d="M14 3v5h5M9 13h6M9 17h4" /></>,
  receipt: <><path d="M6 3h12v18l-3-2-3 2-3-2-3 2z" /><path d="M9 8h6M9 12h6M9 16h3" /></>,
  bell: <><path d="M6 16V11a6 6 0 1 1 12 0v5l1.5 2h-15z" /><path d="M10 20.5a2.2 2.2 0 0 0 4 0" /></>,
  settings: <><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-1.8-.3 1.6 1.6 0 0 0-1 1.5V21a2 2 0 0 1-4 0v-.1a1.6 1.6 0 0 0-1-1.5 1.6 1.6 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.6 1.6 0 0 0 .3-1.8 1.6 1.6 0 0 0-1.5-1H3a2 2 0 0 1 0-4h.1a1.6 1.6 0 0 0 1.5-1 1.6 1.6 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.6 1.6 0 0 0 1.8.3H9a1.6 1.6 0 0 0 1-1.5V3a2 2 0 0 1 4 0v.1a1.6 1.6 0 0 0 1 1.5 1.6 1.6 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.6 1.6 0 0 0-.3 1.8V9a1.6 1.6 0 0 0 1.5 1H21a2 2 0 0 1 0 4h-.1a1.6 1.6 0 0 0-1.5 1z" /></>,
  search: <><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></>,
  plus: <path d="M12 5v14M5 12h14" />,
  minus: <path d="M5 12h14" />,
  "chevron-right": <path d="m9 6 6 6-6 6" />,
  "chevron-left": <path d="m15 6-6 6 6 6" />,
  "chevron-down": <path d="m6 9 6 6 6-6" />,
  "arrow-right": <path d="M5 12h14M13 6l6 6-6 6" />,
  x: <path d="M6 6l12 12M18 6 6 18" />,
  check: <path d="m5 12.5 4.5 4.5L19 7.5" />,
  "check-circle": <><circle cx="12" cy="12" r="9" /><path d="m8 12.5 3 3 5-6" /></>,
  menu: <path d="M4 7h16M4 12h16M4 17h16" />,
  logout: <><path d="M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3" /><path d="M10 16l-4-4 4-4M6 12h10" /></>,
  phone: <path d="M5 4h3.5l1.8 4.5-2.3 1.5a11 11 0 0 0 6 6l1.5-2.3L20 15.5V19a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2z" />,
  mail: <><rect x="3" y="5" width="18" height="14" rx="2.5" /><path d="m3.5 6.5 8.5 6.5 8.5-6.5" /></>,
  pin: <><path d="M12 21s-7-6.2-7-11.5a7 7 0 0 1 14 0C19 14.8 12 21 12 21z" /><circle cx="12" cy="9.5" r="2.5" /></>,
  scale: <><path d="M12 3v18M7 21h10M5 6.5h14M12 4.5l-7 2M12 4.5l7 2" /><path d="M5 6.5 2.5 13a3 3 0 0 0 5 0zM19 6.5 16.5 13a3 3 0 0 0 5 0z" /></>,
  gavel: <><path d="m14 4 6 6M11 7l6 6M12.5 5.5l-6 6M18.5 11.5l-6 6" /><path d="m8 15-5 5M3 21h9" /></>,
  shield: <><path d="M12 3 4.5 6v5.5c0 4.5 3.2 8.3 7.5 9.5 4.3-1.2 7.5-5 7.5-9.5V6z" /><path d="m9 12 2 2 4-4" /></>,
  lock: <><rect x="4.5" y="10.5" width="15" height="10.5" rx="2.5" /><path d="M8 10.5V7.5a4 4 0 0 1 8 0v3" /></>,
  building: <><path d="M4 21V5a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v16M16 9h2a2 2 0 0 1 2 2v10M2.5 21h19" /><path d="M8 7h4M8 11h4M8 15h4" /></>,
  info: <><circle cx="12" cy="12" r="9" /><path d="M12 11v5M12 7.5v.5" /></>,
  alert: <><path d="M12 3.5 2.5 20h19z" /><path d="M12 10v4.5M12 17.5v.5" /></>,
  upload: <><path d="M12 15V4M7.5 8.5 12 4l4.5 4.5" /><path d="M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3" /></>,
  download: <><path d="M12 4v11M7.5 10.5 12 15l4.5-4.5" /><path d="M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3" /></>,
  eye: <><path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z" /><circle cx="12" cy="12" r="3" /></>,
  video: <><rect x="3" y="6.5" width="13" height="11" rx="2.5" /><path d="m16 10.5 5-3v9l-5-3" /></>,
  grid: <><rect x="4" y="4" width="6.5" height="6.5" rx="1.5" /><rect x="13.5" y="4" width="6.5" height="6.5" rx="1.5" /><rect x="4" y="13.5" width="6.5" height="6.5" rx="1.5" /><rect x="13.5" y="13.5" width="6.5" height="6.5" rx="1.5" /></>,
  send: <><path d="M21 3 10 14" /><path d="M21 3 14.5 21l-4-7-7-4z" /></>,
  palette: <><path d="M12 3a9 9 0 0 0 0 18c1.1 0 1.8-.8 1.8-1.8 0-.5-.2-.9-.5-1.2-.3-.3-.5-.7-.5-1.2 0-1 .8-1.8 1.8-1.8H17a4 4 0 0 0 4-4c0-4.4-4-8-9-8z" /><circle cx="7.5" cy="11" r="1" /><circle cx="10" cy="7" r="1" /><circle cx="15" cy="7.5" r="1" /></>,
  globe: <><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3c2.5 2.5 3.8 5.5 3.8 9s-1.3 6.5-3.8 9c-2.5-2.5-3.8-5.5-3.8-9S9.5 5.5 12 3z" /></>,
  message: <path d="M4 5h16a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H9l-5 4V6a1 1 0 0 1 1-1z" />,
  star: <path d="m12 3.5 2.6 5.4 5.9.8-4.3 4.1 1 5.8L12 16.8l-5.2 2.8 1-5.8-4.3-4.1 5.9-.8z" />,
  smartphone: <><rect x="6.5" y="2.5" width="11" height="19" rx="2.5" /><path d="M11 18.5h2" /></>,
  link: <><path d="M10 14a4 4 0 0 0 5.7 0l3-3A4 4 0 0 0 13 5.3l-1 1" /><path d="M14 10a4 4 0 0 0-5.7 0l-3 3A4 4 0 0 0 11 18.7l1-1" /></>,
  copy: <><rect x="8" y="8" width="12" height="12" rx="2" /><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2" /></>,
  refresh: <><path d="M20 11a8 8 0 0 0-14.5-4.5L4 8" /><path d="M4 4v4h4M4 13a8 8 0 0 0 14.5 4.5L20 16" /><path d="M20 20v-4h-4" /></>,
  trash: <><path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3" /></>,
  edit: <><path d="M4 20h4L19 9a2.8 2.8 0 0 0-4-4L4 16z" /><path d="m13.5 6.5 4 4" /></>,
  heart: <path d="M12 20s-7.5-4.6-9-9.5C2 6.9 4.4 4.5 7.3 4.5c1.9 0 3.6 1 4.7 2.6 1.1-1.6 2.8-2.6 4.7-2.6 2.9 0 5.3 2.4 4.3 6C19.5 15.4 12 20 12 20z" />,
  home2: <><path d="M3 21h18M5 21V10l7-5 7 5v11" /><path d="M10 21v-5h4v5" /></>,
  family: <><circle cx="8" cy="6.5" r="2.5" /><circle cx="16" cy="6.5" r="2.5" /><circle cx="12" cy="13" r="2" /><path d="M3.5 20v-4a4.5 4.5 0 0 1 9 0M11.5 16a4.5 4.5 0 0 1 9 0v4M9 20v-1a3 3 0 0 1 6 0v1" /></>,
  handshake: <><path d="m11 17 2 2a1.4 1.4 0 0 0 2-2" /><path d="m14 14 2.5 2.5a1.4 1.4 0 0 0 2-2l-3.8-3.8a3 3 0 0 0-4.2 0l-.9.9a1.4 1.4 0 0 1-2-2l2.8-2.8a5 5 0 0 1 6 -.8l.6.4 2.5-.9" /><path d="m21 3.5 1 7.5-2 1M3 3.5 2 11l6.5 6.5a1.4 1.4 0 0 0 2-2" /><path d="M3 4.5h7" /></>,
  passport: <><rect x="5" y="2.5" width="14" height="19" rx="2" /><circle cx="12" cy="10" r="3.5" /><path d="M9 17h6" /></>,
  percent: <><path d="M19 5 5 19" /><circle cx="7" cy="7" r="2.5" /><circle cx="17" cy="17" r="2.5" /></>,
  bulb: <><path d="M9 18h6M10 21h4" /><path d="M12 3a6 6 0 0 0-3.5 10.9c.6.4 1 1.1 1 1.9V16h5v-.2c0-.8.4-1.5 1-1.9A6 6 0 0 0 12 3z" /></>,
  sparkle: <path d="M12 3c.6 4.4 2.6 6.4 7 7-4.4.6-6.4 2.6-7 7-.6-4.4-2.6-6.4-7-7 4.4-.6 6.4-2.6 7-7z" />,
  moon: <path d="M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5z" />,
  sun: <><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></>,
  inbox: <><path d="M3 13h5l1.5 3h5l1.5-3h5" /><path d="M5 5h14l2 8v6H3v-6z" /></>,
  wallet: <><path d="M4 7h15a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h12v3" /><circle cx="16" cy="13.5" r="1.2" /></>,
};

/* Brand marks are filled, as their owners publish them. */
const BRANDS: Record<string, React.ReactNode> = {
  whatsapp: (
    <path d="M12 2.2A9.8 9.8 0 0 0 3.6 17l-1.4 5 5.2-1.4A9.8 9.8 0 1 0 12 2.2zm0 17.9a8.1 8.1 0 0 1-4.1-1.1l-.3-.2-3.1.8.8-3-.2-.3A8.1 8.1 0 1 1 12 20.1zm4.5-6.1c-.2-.1-1.5-.7-1.7-.8-.2-.1-.4-.1-.6.1l-.8 1c-.1.2-.3.2-.5.1-.2-.1-1-.4-2-1.2-.7-.7-1.2-1.5-1.4-1.7-.1-.2 0-.4.1-.5l.4-.4.3-.4v-.4l-.8-1.9c-.2-.5-.4-.4-.6-.4h-.5c-.2 0-.4.1-.7.3-.2.2-.9.9-.9 2.2s1 2.6 1.1 2.7c.1.2 1.9 2.9 4.6 4.1.6.3 1.1.4 1.5.5.6.2 1.2.2 1.6.1.5-.1 1.5-.6 1.7-1.2.2-.6.2-1.1.1-1.2l-.4-.2z" />
  ),
  facebook: <path d="M13.5 21v-7.5h2.6l.4-3h-3V8.6c0-.9.3-1.5 1.5-1.5h1.6V4.4c-.3 0-1.2-.1-2.3-.1-2.3 0-3.9 1.4-3.9 4v2.2H7.8v3h2.6V21z" />,
  instagram: (
    <path d="M12 3.6c2.7 0 3 0 4.1.1 2.7.1 4 1.4 4.1 4.1.1 1.1.1 1.4.1 4.1s0 3-.1 4.1c-.1 2.7-1.4 4-4.1 4.1-1.1.1-1.4.1-4.1.1s-3 0-4.1-.1c-2.7-.1-4-1.4-4.1-4.1C3.7 15 3.6 14.7 3.6 12s0-3 .1-4.1C3.8 5.2 5.1 3.9 7.9 3.8 9 3.7 9.3 3.6 12 3.6zM12 2c-2.7 0-3.1 0-4.1.1C4.3 2.2 2.3 4.2 2.1 7.9 2 8.9 2 9.3 2 12s0 3.1.1 4.1c.2 3.6 2.2 5.6 5.8 5.8 1 .1 1.4.1 4.1.1s3.1 0 4.1-.1c3.6-.2 5.6-2.2 5.8-5.8.1-1 .1-1.4.1-4.1s0-3.1-.1-4.1c-.2-3.6-2.2-5.6-5.8-5.8C15.1 2 14.7 2 12 2zm0 4.9a5.1 5.1 0 1 0 0 10.2 5.1 5.1 0 0 0 0-10.2zm0 8.5a3.4 3.4 0 1 1 0-6.8 3.4 3.4 0 0 1 0 6.8zm5.3-9.9a1.2 1.2 0 1 0 0 2.4 1.2 1.2 0 0 0 0-2.4z" />
  ),
  x: <path d="M17.8 3h3.1l-6.8 7.7 8 10.3h-6.2l-4.9-6.3L5.4 21H2.3l7.2-8.3L1.9 3h6.4l4.4 5.8zm-1.1 16.2h1.7L7.4 4.7H5.6z" />,
  linkedin: <path d="M20.4 2H3.6C2.7 2 2 2.7 2 3.6v16.8c0 .9.7 1.6 1.6 1.6h16.8c.9 0 1.6-.7 1.6-1.6V3.6c0-.9-.7-1.6-1.6-1.6zM8 19H5V9.5h3zM6.5 8.2a1.7 1.7 0 1 1 0-3.5 1.7 1.7 0 0 1 0 3.5zM19 19h-3v-4.6c0-1.1 0-2.5-1.5-2.5S12.8 13 12.8 14.3V19h-3V9.5h2.8v1.3h.1c.4-.8 1.4-1.6 2.8-1.6 3 0 3.5 2 3.5 4.5z" />,
  youtube: <path d="M21.6 7.2a2.5 2.5 0 0 0-1.8-1.8C18.2 5 12 5 12 5s-6.2 0-7.8.4A2.5 2.5 0 0 0 2.4 7.2C2 8.8 2 12 2 12s0 3.2.4 4.8a2.5 2.5 0 0 0 1.8 1.8C5.8 19 12 19 12 19s6.2 0 7.8-.4a2.5 2.5 0 0 0 1.8-1.8c.4-1.6.4-4.8.4-4.8s0-3.2-.4-4.8zM10 15V9l5.2 3z" />,
  tiktok: <path d="M16.6 2h-3.3v13.4a2.8 2.8 0 1 1-2.8-2.8c.3 0 .6 0 .8.1V9.3a6.2 6.2 0 1 0 5.3 6.1V8.6a8 8 0 0 0 4.4 1.3V6.6a4.5 4.5 0 0 1-4.4-4.6z" />,
};

export type IconName = keyof typeof P | keyof typeof BRANDS;

export function Icon({ name, size, className, title }: { name: IconName | string; size?: number; className?: string; title?: string }) {
  const brand = BRANDS[name];
  const style = size ? { width: size, height: size } : undefined;
  if (brand) {
    return (
      <svg viewBox="0 0 24 24" fill="currentColor" style={style} className={className} aria-hidden={title ? undefined : true} role={title ? "img" : undefined}>
        {title && <title>{title}</title>}
        {brand}
      </svg>
    );
  }
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      style={style}
      className={className}
      aria-hidden={title ? undefined : true}
      role={title ? "img" : undefined}
    >
      {title && <title>{title}</title>}
      {P[name] ?? P.info}
    </svg>
  );
}

/* The firm's seal: a quiet scales-of-justice motif used as background art. */
export function Seal({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 200 200" fill="none" stroke="currentColor" strokeWidth="2" className={className} aria-hidden>
      <circle cx="100" cy="100" r="96" />
      <circle cx="100" cy="100" r="84" strokeDasharray="2 6" />
      <path d="M100 40v118M70 158h60M58 62h84M100 50 58 62M100 50l42 12" />
      <path d="M58 62 42 104a16 16 0 0 0 32 0zM142 62l-16 42a16 16 0 0 0 32 0z" />
      <circle cx="100" cy="44" r="5" />
    </svg>
  );
}

export const PRACTICE_ICONS: Record<string, string> = {
  litigation: "gavel",
  criminal: "shield",
  corporate: "briefcase",
  land: "home2",
  family: "family",
  employment: "handshake",
  immigration: "passport",
  tax: "percent",
  ip: "bulb",
  other: "scale",
};

export const PRACTICE_BLURBS: Record<string, string> = {
  litigation: "Disputes resolved in and out of court, with a clear plan and honest odds from day one.",
  criminal: "Calm, determined defence from arrest to appeal. We answer the phone at night.",
  corporate: "Company formation, contracts, investment and governance for businesses that are going places.",
  land: "Titles, transfers, leases and land disputes, checked properly before you pay a shilling.",
  family: "Marriage, divorce, custody, wills and succession, handled with discretion and care.",
  employment: "Contracts, disputes and workplace policy for employers and employees alike.",
  immigration: "Work permits, residence and citizenship, with every form and deadline handled.",
  tax: "Planning, compliance and disputes with the revenue authority.",
  ip: "Trademarks, copyright and brand protection for creators and companies.",
  other: "If it involves the law, start with a conversation. We will point you the right way.",
};
