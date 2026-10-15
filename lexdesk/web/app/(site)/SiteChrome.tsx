"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { Icon } from "@/components/Icon";
import { ThemeToggle } from "@/components/ThemeToggle";
import { FirmMark, SocialLinks } from "@/components/ui";
import { useAuth, homeFor } from "@/lib/auth";
import { hoursLabel, useFirm } from "@/lib/firm";

export function SiteChrome({ children }: { children: React.ReactNode }) {
  const { firm } = useFirm();
  const { user } = useAuth();
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);
  useEffect(() => setOpen(false), [pathname]);

  const year = new Date().getFullYear();

  return (
    <div className="site">
      <header className={`site-header ${scrolled ? "scrolled" : ""}`}>
        <div className="container inner">
          <Link href="/" className="site-brand" aria-label={`${firm.name}, home`}>
            <FirmMark firm={firm} size={40} />
            <span className="name">{firm.name}</span>
          </Link>
          <nav className={`site-nav ${open ? "open" : ""}`} aria-label="Main">
            <a className="link" href="/#practice">What we do</a>
            <a className="link" href="/#team">Our lawyers</a>
            <a className="link" href="/#how">How it works</a>
            <a className="link" href="/#contact">Contact</a>
            {user ? (
              <Link className="link" href={homeFor(user)}>My account</Link>
            ) : (
              <Link className="link" href="/login">Sign in</Link>
            )}
            {firm.booking_enabled && (
              <Link className="btn btn-primary" href="/book" style={{ marginLeft: 6 }}>
                Book a consultation
              </Link>
            )}
          </nav>
          <span className="row" style={{ ["--gap" as string]: "2px" }}>
          <ThemeToggle />
          <button className="icon-btn site-menu-btn" onClick={() => setOpen((o) => !o)} aria-expanded={open} aria-label="Menu">
            <Icon name={open ? "x" : "menu"} />
          </button>
          </span>
        </div>
      </header>

      <main>{children}</main>

      <footer className="site-footer" id="contact">
        <div className="container">
          <div className="footer-grid">
            <div className="stack" style={{ ["--gap" as string]: "16px" }}>
              <div className="row">
                <FirmMark firm={firm} size={44} light />
                <span className="serif" style={{ color: "#fff", fontSize: 19, fontWeight: 600 }}>{firm.name}</span>
              </div>
              {firm.tagline && <p style={{ maxWidth: 360 }}>{firm.tagline}</p>}
              <SocialLinks socials={firm.socials} whatsapp={firm.whatsapp_link} />
            </div>
            <div>
              <h4>Visit</h4>
              <div className="stack" style={{ ["--gap" as string]: "8px" }}>
                {firm.address && <span style={{ whiteSpace: "pre-line" }}>{firm.address}</span>}
                {firm.map_url && (
                  <a href={firm.map_url} target="_blank" rel="noopener noreferrer">Get directions →</a>
                )}
              </div>
            </div>
            <div>
              <h4>Talk to us</h4>
              <div className="stack" style={{ ["--gap" as string]: "8px" }}>
                {firm.phone && <a href={`tel:${firm.phone}`}>{firm.phone}</a>}
                {firm.whatsapp_link && (
                  <a href={firm.whatsapp_link} target="_blank" rel="noopener noreferrer">WhatsApp {firm.whatsapp_number}</a>
                )}
                {firm.email && <a href={`mailto:${firm.email}`}>{firm.email}</a>}
              </div>
            </div>
            <div>
              <h4>Office hours</h4>
              <p>{hoursLabel(firm)}</p>
              <p style={{ marginTop: 8, fontSize: 13, color: "#9fb0cc" }}>For urgent criminal matters, call any time.</p>
            </div>
          </div>
          <div className="row-between wrap" style={{ marginTop: 44, paddingTop: 22, borderTop: "1px solid rgba(255,255,255,.1)", fontSize: 13, color: "#9fb0cc" }}>
            <span>© {year} {firm.name}. All rights reserved.</span>
            <span>Information on this site is general and is not legal advice for your situation. · <a href="/register" style={{ color: "#9fb0cc" }}>Law firms: join LexDesk</a></span>
          </div>
        </div>
      </footer>

      {firm.whatsapp_link && (
        <a className="wa-float" href={firm.whatsapp_link} target="_blank" rel="noopener noreferrer" aria-label="Chat with us on WhatsApp">
          <Icon name="whatsapp" />
          <span>Chat with us</span>
        </a>
      )}
    </div>
  );
}
