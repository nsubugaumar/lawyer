const TZ = "Africa/Kampala";

export function fmtDate(value: string | Date | null | undefined, opts: Intl.DateTimeFormatOptions = { day: "numeric", month: "short", year: "numeric" }) {
  if (!value) return "";
  return new Intl.DateTimeFormat("en-GB", { timeZone: TZ, ...opts }).format(new Date(value));
}

export const fmtTime = (v: string | Date) => fmtDate(v, { hour: "2-digit", minute: "2-digit", hour12: false });
export const fmtDay = (v: string | Date) => fmtDate(v, { weekday: "short", day: "numeric", month: "short" });
export const fmtLong = (v: string | Date) => fmtDate(v, { weekday: "long", day: "numeric", month: "long" });
export const fmtDateTime = (v: string | Date) => `${fmtDay(v)}, ${fmtTime(v)}`;
export const monthShort = (v: string | Date) => fmtDate(v, { month: "short" });
export const dayNum = (v: string | Date) => fmtDate(v, { day: "numeric" });

/** YYYY-MM-DD in the firm's timezone. */
export function isoDay(value: Date | string) {
  const parts = new Intl.DateTimeFormat("en-CA", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(value));
  return parts;
}

export function relative(value: string | Date) {
  const diff = (new Date(value).getTime() - Date.now()) / 1000;
  const abs = Math.abs(diff);
  const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
  if (abs < 60) return "just now";
  if (abs < 3600) return rtf.format(Math.round(diff / 60), "minute");
  if (abs < 86400) return rtf.format(Math.round(diff / 3600), "hour");
  if (abs < 86400 * 7) return rtf.format(Math.round(diff / 86400), "day");
  return fmtDate(value);
}

export function money(amount: string | number | null | undefined, currency = "UGX") {
  const n = Number(amount ?? 0);
  return `${currency} ${n.toLocaleString("en-GB", { maximumFractionDigits: currency === "UGX" ? 0 : 2 })}`;
}

export function greeting(date = new Date()) {
  const hour = Number(new Intl.DateTimeFormat("en-GB", { timeZone: TZ, hour: "numeric", hour12: false }).format(date));
  return hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";
}

export function initials(name = "") {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0]?.toUpperCase()).join("") || "?";
}

const AVATAR_COLORS = ["#1b3a6b", "#8a6a30", "#2f6b5b", "#7c2d3b", "#3f5f8f", "#5b4b8a", "#a0522d", "#2e6fb5"];
export function avatarColor(seed = "") {
  let h = 0;
  for (const c of seed) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return AVATAR_COLORS[h % AVATAR_COLORS.length];
}

export function minutesLabel(m: number) {
  if (m % 1440 === 0) return m === 1440 ? "1 day before" : `${m / 1440} days before`;
  if (m % 60 === 0) return m === 60 ? "1 hour before" : `${m / 60} hours before`;
  return `${m} minutes before`;
}

/** A local date + "HH:MM" in the firm's timezone → ISO string with offset. */
export function localToIso(day: string, time: string) {
  return `${day}T${time}:00+03:00`;
}
