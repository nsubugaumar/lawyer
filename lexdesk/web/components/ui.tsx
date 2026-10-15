"use client";

import { createContext, useCallback, useContext, useEffect, useId, useRef, useState } from "react";
import { avatarColor, initials } from "@/lib/format";
import type { PublicFirm, Social } from "@/lib/firm";
import { Icon } from "./Icon";

/* ------------------------------------------------------------- data hook */

export function useLoad<T>(load: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | undefined>(undefined);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);
  const loader = useRef(load);
  loader.current = load;

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      setData(await loader.current());
      setError(null);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return { data, setData, error, loading, reload };
}

/* ---------------------------------------------------------------- toasts */

type Toast = { id: number; text: string; kind: "ok" | "err" };
const ToastContext = createContext<(text: string, kind?: "ok" | "err") => void>(() => undefined);

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const push = useCallback((text: string, kind: "ok" | "err" = "ok") => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, text, kind }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4200);
  }, []);
  return (
    <ToastContext.Provider value={push}>
      {children}
      <div className="toast-host" role="status" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`toast ${t.kind === "err" ? "err" : ""}`}>
            <Icon name={t.kind === "err" ? "alert" : "check-circle"} />
            <span>{t.text}</span>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export const useToast = () => useContext(ToastContext);

/* ----------------------------------------------------------------- modal */

export function Modal({
  title,
  subtitle,
  onClose,
  children,
  footer,
  wide,
}: {
  title: string;
  subtitle?: string;
  onClose: () => void;
  children: React.ReactNode;
  footer?: React.ReactNode;
  wide?: boolean;
}) {
  const id = useId();
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = overflow;
    };
  }, [onClose]);

  return (
    <div className="overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby={id} style={wide ? { width: "min(760px, 100%)" } : undefined}>
        <div className="modal-head">
          <div>
            <h2 id={id} style={{ fontSize: "1.3rem" }}>{title}</h2>
            {subtitle && <p className="muted small" style={{ marginTop: 4 }}>{subtitle}</p>}
          </div>
          <button className="icon-btn" onClick={onClose} aria-label="Close">
            <Icon name="x" />
          </button>
        </div>
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-foot">{footer}</div>}
      </div>
    </div>
  );
}

/* ----------------------------------------------------------- small parts */

export function Avatar({ name, size }: { name: string; size?: "lg" }) {
  return (
    <span className={`avatar ${size === "lg" ? "avatar-lg" : ""}`} style={{ background: avatarColor(name) }} aria-hidden>
      {initials(name)}
    </span>
  );
}

export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <div className="row" style={{ justifyContent: "center", padding: 32 }}>
      <div className="spinner" role="status" aria-label={label} />
    </div>
  );
}

export function Empty({ icon = "inbox", title, children, action }: { icon?: string; title: string; children?: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div className="empty">
      <Icon name={icon} />
      <h3>{title}</h3>
      {children && <p style={{ maxWidth: 380 }}>{children}</p>}
      {action && <div style={{ marginTop: 8 }}>{action}</div>}
    </div>
  );
}

export function ErrorNote({ error }: { error: unknown }) {
  if (!error) return null;
  const message = (error as { message?: string })?.message ?? "Something went wrong.";
  return (
    <div className="notice err">
      <Icon name="alert" />
      <span>{message}</span>
    </div>
  );
}

export function Field({
  label,
  hint,
  error,
  children,
  htmlFor,
}: {
  label: string;
  hint?: React.ReactNode;
  error?: string;
  children: React.ReactNode;
  htmlFor?: string;
}) {
  return (
    <div className="field">
      <label htmlFor={htmlFor}>{label}</label>
      {children}
      {error ? <span className="error-text">{error}</span> : hint ? <span className="hint">{hint}</span> : null}
    </div>
  );
}

export function Switch({ checked, onChange, label, disabled }: { checked: boolean; onChange: (v: boolean) => void; label: string; disabled?: boolean }) {
  return (
    <label className="switch" title={label}>
      <input type="checkbox" checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} aria-label={label} />
      <span />
    </label>
  );
}

const STATUS: Record<string, [string, string]> = {
  // matters
  intake: ["Intake", "badge-gold"],
  open: ["Open", "badge-blue"],
  on_hold: ["On hold", "badge-amber"],
  closed: ["Closed", ""],
  // appointments
  requested: ["Awaiting confirmation", "badge-amber"],
  confirmed: ["Confirmed", "badge-green"],
  cancelled: ["Cancelled", "badge-red"],
  completed: ["Completed", ""],
  no_show: ["No-show", "badge-red"],
  // court
  pending: ["Upcoming", "badge-blue"],
  held: ["Held", "badge-green"],
  adjourned: ["Adjourned", "badge-amber"],
  met: ["Deadline met", "badge-green"],
  vacated: ["Vacated", ""],
  // invoices
  draft: ["Draft", ""],
  issued: ["Issued", "badge-blue"],
  part_paid: ["Part paid", "badge-amber"],
  paid: ["Paid", "badge-green"],
  void: ["Void", ""],
  // tasks
  todo: ["To do", ""],
  in_progress: ["In progress", "badge-blue"],
  done: ["Done", "badge-green"],
  // clients
  prospect: ["Prospect", "badge-gold"],
  active: ["Active", "badge-green"],
  former: ["Former", ""],
};

export function StatusBadge({ status }: { status: string }) {
  const [label, cls] = STATUS[status] ?? [status, ""];
  return <span className={`badge ${cls}`}>{label}</span>;
}

/* -------------------------------------------------------- firm identity */

export function FirmMark({ firm, size = 40, light }: { firm: Pick<PublicFirm, "name" | "logo_url">; size?: number; light?: boolean }) {
  if (firm.logo_url) {
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={firm.logo_url} alt="" width={size} height={size} style={{ width: size, height: size, objectFit: "contain", borderRadius: 10 }} />;
  }
  return (
    <span
      aria-hidden
      style={{
        width: size,
        height: size,
        borderRadius: size / 4,
        display: "grid",
        placeItems: "center",
        flex: "none",
        background: light ? "rgba(255,255,255,0.1)" : "var(--primary)",
        border: light ? "1px solid rgba(255,255,255,0.18)" : "none",
        color: light ? "var(--accent)" : "#fff",
      }}
    >
      <Icon name="scale" size={size * 0.55} />
    </span>
  );
}

export function SocialLinks({ socials, whatsapp, onLight }: { socials: Social[]; whatsapp?: string; onLight?: boolean }) {
  if (!socials.length && !whatsapp) return null;
  return (
    <div className={`socials ${onLight ? "on-light" : ""}`}>
      {whatsapp && (
        <a className="social" href={whatsapp} target="_blank" rel="noopener noreferrer" aria-label="Chat with us on WhatsApp">
          <Icon name="whatsapp" />
        </a>
      )}
      {socials.map((s) => (
        <a key={s.network} className="social" href={s.url} target="_blank" rel="noopener noreferrer" aria-label={`${s.label} (opens in a new tab)`} title={s.label}>
          <Icon name={s.network} />
        </a>
      ))}
    </div>
  );
}

export function copyText(text: string) {
  return navigator.clipboard?.writeText(text);
}
