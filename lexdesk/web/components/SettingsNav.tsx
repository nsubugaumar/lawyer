"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { isManager, useAuth } from "@/lib/auth";
import { Icon } from "./Icon";

export function SettingsLayout({ title, intro, children }: { title: string; intro: string; children: React.ReactNode }) {
  const { user } = useAuth();
  const pathname = usePathname();
  const items = [
    { href: "/settings/profile", label: "My profile", icon: "user" },
    { href: "/settings/notifications", label: "Notifications", icon: "bell" },
    { href: "/settings/security", label: "Sign-in & security", icon: "lock" },
    ...(isManager(user) && user?.firm ? [{ href: "/settings/firm", label: "Firm settings", icon: "building" }, { href: "/settings/team", label: "Team", icon: "users" }] : []),
  ];
  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>{title}</h1>
          <p>{intro}</p>
        </div>
      </div>
      <div className="settings-grid">
        <nav className="settings-nav" aria-label="Settings">
          {items.map((i) => (
            <Link key={i.href} href={i.href} aria-current={pathname === i.href ? "true" : undefined}>
              <Icon name={i.icon} /> {i.label}
            </Link>
          ))}
        </nav>
        <div style={{ minWidth: 0 }}>{children}</div>
      </div>
    </div>
  );
}
