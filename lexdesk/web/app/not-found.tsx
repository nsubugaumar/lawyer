import Link from "next/link";

export default function NotFound() {
  return (
    <div style={{ minHeight: "100dvh", display: "grid", placeItems: "center", padding: 24, textAlign: "center" }}>
      <div style={{ display: "grid", gap: 14, justifyItems: "center" }}>
        <span className="eyebrow">Page not found</span>
        <h1>We could not find that page</h1>
        <p className="muted">It may have moved, or the link may be mistyped.</p>
        <Link href="/" className="btn btn-primary">Go to the home page</Link>
      </div>
    </div>
  );
}
