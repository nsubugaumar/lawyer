"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { Icon } from "@/components/Icon";
import { Spinner, useLoad, useToast } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { money } from "@/lib/format";

type Status = { tx_ref: string; status: string; amount: string; currency: string; invoice_number: string; firm: string };

/**
 * Test mode only. Stands in for Flutterwave's checkout so a firm can try
 * online payment end to end before connecting real Mobile Money.
 */
export default function TestCheckoutPage() {
  return (
    <Suspense fallback={<Spinner />}>
      <TestCheckout />
    </Suspense>
  );
}

function TestCheckout() {
  const ref = useSearchParams().get("ref") ?? "";
  const router = useRouter();
  const toast = useToast();
  const payment = useLoad(() => api<Status>(`/billing/online-payments/${ref}/`), [ref]);
  const [busy, setBusy] = useState(false);

  async function answer(outcome: "success" | "failed") {
    setBusy(true);
    try {
      await api(`/billing/online-payments/${ref}/`, { method: "POST", body: { outcome } });
      router.replace(`/billing?payment=${ref}`);
    } catch (err) {
      toast(errorMessage(err), "err");
      setBusy(false);
    }
  }

  if (payment.loading) return <div className="page"><Spinner /></div>;
  const p = payment.data;
  return (
    <div className="page" style={{ maxWidth: 480 }}>
      <div className="card card-pad stack" style={{ ["--gap" as string]: "16px", textAlign: "center", justifyItems: "center" }}>
        <span className="badge badge-amber">Test mode: no money moves</span>
        <span style={{ width: 64, height: 64, borderRadius: 18, display: "grid", placeItems: "center", background: "#ffcb05", color: "#1a1a1a" }}><Icon name="smartphone" size={30} /></span>
        <h1 style={{ fontSize: "1.5rem" }}>Mobile Money</h1>
        {p ? (
          <>
            <p className="muted">{p.firm} · Invoice {p.invoice_number}</p>
            <strong className="serif" style={{ fontSize: 32 }}>{money(p.amount, p.currency)}</strong>
            <p className="small muted">On a live account, the client would now get a prompt on their phone to approve with their PIN.</p>
            <div className="row wrap" style={{ justifyContent: "center" }}>
              <button className="btn" disabled={busy} onClick={() => answer("failed")}>Decline</button>
              <button className="btn btn-primary btn-lg" disabled={busy} onClick={() => answer("success")}><Icon name="check" /> Approve payment</button>
            </div>
          </>
        ) : (
          <p>This payment could not be found.</p>
        )}
      </div>
    </div>
  );
}
