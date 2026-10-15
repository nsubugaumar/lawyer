"use client";

import Link from "next/link";
import { Seal } from "@/components/Icon";
import { ThemeToggle } from "@/components/ThemeToggle";
import { FirmMark } from "@/components/ui";
import { useFirm } from "@/lib/firm";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  const { firm } = useFirm();
  return (
    <div className="auth-shell">
      <div className="auth-art">
        <Link href="/" className="row" style={{ color: "#fff", textDecoration: "none" }}>
          <FirmMark firm={firm} size={42} light />
          <span className="serif" style={{ fontSize: 18, fontWeight: 600 }}>{firm.name}</span>
        </Link>
        <div>
          <blockquote>Every file, every hearing, every client, in one quiet, secure place.</blockquote>
          <cite>Your diary reminds you. Your documents travel with you. Nothing is left on a desk.</cite>
        </div>
        <span style={{ fontSize: 13, color: "#9fb0cc" }}>Protected by two-factor sign-in and encrypted documents.</span>
        <Seal className="seal" />
      </div>
      <div className="auth-panel" style={{ position: "relative" }}>
        <span style={{ position: "absolute", top: 16, right: 16 }}><ThemeToggle /></span>
        {children}
      </div>
    </div>
  );
}
