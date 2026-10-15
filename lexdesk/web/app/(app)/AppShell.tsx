"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { Icon } from "@/components/Icon";
import { ThemeToggle } from "@/components/ThemeToggle";
import { Avatar, FirmMark, Modal, Spinner } from "@/components/ui";
import { api } from "@/lib/api";
import { isManager, useAuth, type User } from "@/lib/auth";
import { useFirm } from "@/lib/firm";
import { relative } from "@/lib/format";

type NavItem = { href: string; label: string; icon: string; show?: (u: User) => boolean };

const CLIENT_DESK = ["admin", "partner", "lawyer", "paralegal", "receptionist", "accountant"];
const BILLING = ["admin", "partner", "accountant", "lawyer", "paralegal"];

const STAFF_NAV: NavItem[] = [
  { href: "/dashboard", label: "Today", icon: "home" },
  { href: "/diary", label: "Court diary", icon: "calendar" },
  { href: "/appointments", label: "Appointments", icon: "clock" },
  { href: "/matters", label: "Matters", icon: "briefcase", show: (u) => u.role !== "receptionist" },
  { href: "/clients", label: "Clients", icon: "users", show: (u) => CLIENT_DESK.includes(u.role) },
  { href: "/messages", label: "Messages", icon: "message", show: (u) => u.role !== "receptionist" && u.role !== "accountant" },
  { href: "/billing", label: "Billing", icon: "receipt", show: (u) => BILLING.includes(u.role) },
  { href: "/library", label: "Library", icon: "scale", show: (u) => ["admin", "partner", "lawyer", "paralegal"].includes(u.role) },
  { href: "/templates", label: "Templates", icon: "file", show: (u) => ["admin", "partner", "lawyer", "paralegal"].includes(u.role) },
  { href: "/reports", label: "Reports", icon: "grid", show: (u) => isManager(u) },
];

const CLIENT_NAV: NavItem[] = [
  { href: "/portal", label: "My case", icon: "home" },
  { href: "/messages", label: "Messages", icon: "message" },
  { href: "/appointments", label: "Appointments", icon: "clock" },
  { href: "/billing", label: "Invoices", icon: "receipt" },
];

const PLATFORM_NAV: NavItem[] = [{ href: "/platform", label: "Law firms", icon: "building" }];

const SETTINGS_NAV: NavItem[] = [
  { href: "/settings/notifications", label: "My notifications", icon: "bell" },
  { href: "/settings/security", label: "Sign-in & security", icon: "lock" },
  { href: "/settings/firm", label: "Firm settings", icon: "building", show: (u) => isManager(u) && !u.is_platform_operator },
  { href: "/settings/team", label: "Team", icon: "users", show: (u) => isManager(u) && !u.is_platform_operator },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const { user, ready, logout, mfaSetupRequired } = useAuth();
  const { firm } = useFirm();
  const router = useRouter();
  const pathname = usePathname();
  const [unread, setUnread] = useState(0);
  const [bellOpen, setBellOpen] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);

  useEffect(() => {
    if (ready && !user) router.replace(`/login?next=${encodeURIComponent(pathname)}`);
  }, [ready, user, router, pathname]);

  useEffect(() => {
    if (ready && user && mfaSetupRequired && !pathname.startsWith("/settings/security")) router.replace("/settings/security?setup=1");
  }, [ready, user, mfaSetupRequired, pathname, router]);

  // The bell: cheap poll, paused while the tab is hidden.
  useEffect(() => {
    if (!user) return;
    let alive = true;
    const tick = () => {
      if (document.visibilityState !== "visible") return;
      api<{ unread: number }>("/notifications/unread-count/").then((r) => alive && setUnread(r.unread)).catch(() => undefined);
    };
    tick();
    const id = setInterval(tick, 30000);
    document.addEventListener("visibilitychange", tick);
    return () => {
      alive = false;
      clearInterval(id);
      document.removeEventListener("visibilitychange", tick);
    };
  }, [user]);

  useEffect(() => {
    setMoreOpen(false);
    setBellOpen(false);
  }, [pathname]);

  if (!ready || !user) {
    return (
      <div className="app-root" style={{ display: "grid", placeItems: "center" }}>
        <Spinner />
      </div>
    );
  }

  const main = (user.is_platform_operator ? PLATFORM_NAV : user.role === "client" ? CLIENT_NAV : STAFF_NAV).filter((n) => !n.show || n.show(user));
  const settings = SETTINGS_NAV.filter((n) => !n.show || n.show(user));
  const isActive = (href: string) => pathname === href || pathname.startsWith(href + "/");
  const tabs = main.slice(0, 4);

  return (
    <div className="app-root">
      {/* ------------------------------------------------- desktop sidebar */}
      <aside className="sidebar">
        <Link href={main[0].href} className="brand">
          <FirmMark firm={firm} size={38} light />
          <span className="truncate">
            <span className="brand-name" style={{ display: "block" }}>{user.is_platform_operator ? "LexDesk" : firm.name}</span>
            <span className="brand-sub">{user.is_platform_operator ? "Platform" : "LexDesk"}</span>
          </span>
        </Link>
        <nav aria-label="Main">
          {main.map((n) => (
            <Link key={n.href} href={n.href} className="nav-link" aria-current={isActive(n.href) ? "page" : undefined}>
              <Icon name={n.icon} /> {n.label}
            </Link>
          ))}
          <Link href="/notifications" className="nav-link" aria-current={isActive("/notifications") ? "page" : undefined}>
            <Icon name="bell" /> Notifications {unread > 0 && <span className="count">{unread}</span>}
          </Link>
          <span className="nav-title">Settings</span>
          {settings.map((n) => (
            <Link key={n.href} href={n.href} className="nav-link" aria-current={isActive(n.href) ? "page" : undefined}>
              <Icon name={n.icon} /> {n.label}
            </Link>
          ))}
        </nav>
        <Link href="/settings/profile" className="me">
          <Avatar name={user.full_name} />
          <span className="truncate grow">
            <span style={{ display: "block", fontWeight: 600, fontSize: 14 }} className="truncate">{user.full_name}</span>
            <span style={{ fontSize: 12, color: "#9fb0cc" }}>{user.title || user.role_display}</span>
          </span>
        </Link>
      </aside>

      <div className="main">
        <header className="topbar">
          <Link href={main[0].href} className="mobile-only" aria-label="Home" style={{ textDecoration: "none" }}>
            <span className="row" style={{ ["--gap" as string]: "10px" }}>
              <FirmMark firm={firm} size={32} />
              <span className="serif strong truncate" style={{ fontSize: 16, color: "var(--ink)", maxWidth: "52vw" }}>{firm.name}</span>
            </span>
          </Link>
          {user.role !== "client" ? (
            <form
              className="search desktop-only"
              role="search"
              onSubmit={(e) => {
                e.preventDefault();
                const q = new FormData(e.currentTarget).get("q");
                if (q) router.push(`/matters?search=${encodeURIComponent(String(q))}`);
              }}
            >
              <Icon name="search" />
              <input name="q" placeholder="Search matters, case numbers, clients…" aria-label="Search" />
            </form>
          ) : (
            <span className="grow desktop-only" />
          )}
          <span className="grow mobile-only" />
          <ThemeToggle />
          <div style={{ position: "relative" }}>
            <button className="icon-btn" aria-label={`Notifications${unread ? `, ${unread} unread` : ""}`} onClick={() => setBellOpen((o) => !o)}>
              <Icon name="bell" />
              {unread > 0 && <span className="dot">{unread > 9 ? "9+" : unread}</span>}
            </button>
            {bellOpen && <BellPanel onClose={() => setBellOpen(false)} onRead={() => setUnread(0)} />}
          </div>
          <button
            className="icon-btn desktop-only"
            aria-label="Sign out"
            title="Sign out"
            onClick={async () => {
              await logout();
              router.replace("/login");
            }}
          >
            <Icon name="logout" />
          </button>
        </header>

        {children}
      </div>

      {/* ------------------------------------------------ phone tab bar */}
      <nav className="tabbar" aria-label="Main">
        {tabs.map((n) => (
          <Link key={n.href} href={n.href} aria-current={isActive(n.href) ? "page" : undefined}>
            <Icon name={n.icon} />
            {n.label.replace("Court diary", "Diary")}
          </Link>
        ))}
        {user.role === "client" && (
          <Link href="/notifications" aria-current={isActive("/notifications") ? "page" : undefined}>
            <Icon name="bell" />
            Alerts
          </Link>
        )}
        {user.role !== "client" && (
          <button onClick={() => setMoreOpen(true)} aria-haspopup="dialog">
            <Icon name="grid" />
            More
          </button>
        )}
      </nav>

      {moreOpen && (
        <Modal title={`Hello, ${user.first_name}`} subtitle={user.title || user.role_display} onClose={() => setMoreOpen(false)}>
          <div className="more-sheet">
            {[...main.slice(4), { href: "/notifications", label: "Notifications", icon: "bell" }, ...settings, { href: "/settings/profile", label: "My profile", icon: "user" }].map((n) => (
              <Link key={n.href} href={n.href}>
                <Icon name={n.icon} />
                {n.label}
              </Link>
            ))}
          </div>
          <button
            className="btn btn-block"
            style={{ marginTop: 16 }}
            onClick={async () => {
              await logout();
              router.replace("/login");
            }}
          >
            <Icon name="logout" /> Sign out
          </button>
        </Modal>
      )}
    </div>
  );
}

type Note = { id: string; title: string; body: string; link: string; read_at: string | null; created_at: string; category: string; urgent: boolean };

const CATEGORY_ICON: Record<string, string> = { diary: "gavel", appointment: "clock", agenda: "calendar", billing: "receipt", security: "lock", general: "bell" };

function BellPanel({ onClose, onRead }: { onClose: () => void; onRead: () => void }) {
  const [notes, setNotes] = useState<Note[] | null>(null);
  const ref = useRef<HTMLDivElement>(null);
  const router = useRouter();

  useEffect(() => {
    api<{ results: Note[] }>("/notifications/", { query: { page_size: 8 } }).then((r) => setNotes(r.results)).catch(() => setNotes([]));
    const onDoc = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && onClose();
    setTimeout(() => document.addEventListener("mousedown", onDoc), 0);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [onClose]);

  async function open(n: Note) {
    if (!n.read_at) api(`/notifications/${n.id}/read/`, { method: "POST" }).catch(() => undefined);
    onClose();
    if (n.link) router.push(n.link);
  }

  return (
    <div
      ref={ref}
      className="card"
      role="dialog"
      aria-label="Notifications"
      style={{ position: "absolute", right: 0, top: 48, width: "min(380px, calc(100vw - 24px))", boxShadow: "var(--shadow-lg)", zIndex: 60, overflow: "hidden" }}
    >
      <div className="card-head">
        <h3>Notifications</h3>
        <button
          className="btn btn-ghost btn-sm"
          onClick={async () => {
            await api("/notifications/read-all/", { method: "POST" });
            setNotes((ns) => ns?.map((n) => ({ ...n, read_at: n.read_at ?? new Date().toISOString() })) ?? null);
            onRead();
          }}
        >
          Mark all read
        </button>
      </div>
      <div style={{ maxHeight: 420, overflowY: "auto" }}>
        {notes === null ? (
          <Spinner />
        ) : notes.length === 0 ? (
          <div className="empty" style={{ padding: 28 }}>
            <Icon name="bell" />
            <p>You are all caught up.</p>
          </div>
        ) : (
          <ul className="list">
            {notes.map((n) => (
              <li key={n.id}>
                <button className="list-item" onClick={() => open(n)} style={{ alignItems: "flex-start", padding: "12px 16px" }}>
                  <span style={{ width: 34, height: 34, borderRadius: 10, display: "grid", placeItems: "center", flex: "none", background: n.urgent ? "var(--danger-soft)" : "var(--primary-soft)", color: n.urgent ? "var(--danger)" : "var(--primary)" }}>
                    <Icon name={CATEGORY_ICON[n.category] ?? "bell"} size={17} />
                  </span>
                  <span className="grow">
                    <span style={{ display: "block", fontWeight: n.read_at ? 500 : 700, fontSize: 14 }}>{n.title}</span>
                    <span className="muted tiny">{relative(n.created_at)}</span>
                  </span>
                  {!n.read_at && <span style={{ width: 8, height: 8, borderRadius: "50%", background: "var(--accent)", marginTop: 6, flex: "none" }} />}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
      <Link href="/notifications" className="list-item" style={{ justifyContent: "center", borderTop: "1px solid var(--line)", fontWeight: 600, fontSize: 14 }} onClick={onClose}>
        See all notifications
      </Link>
    </div>
  );
}
