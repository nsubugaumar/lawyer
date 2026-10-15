"use client";

import { Suspense } from "react";
import { Spinner } from "@/components/ui";
import { SetPassword } from "../SetPassword";

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={<Spinner />}>
      <SetPassword purpose="reset" />
    </Suspense>
  );
}
