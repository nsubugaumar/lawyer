"use client";

import { useEffect, useState } from "react";
import { Icon } from "./Icon";

export type Mode = "light" | "dark" | "system";

function apply(mode: Mode) {
  const dark = mode === "dark" || (mode === "system" && matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.dataset.mode = dark ? "dark" : "light";
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", dark ? "#0e141e" : "#f7f4ee");
}

export function useMode() {
  const [mode, setModeState] = useState<Mode>("light");
  useEffect(() => {
    try {
      setModeState((localStorage.getItem("lexdesk.mode") as Mode) || "light");
    } catch {
      /* storage blocked: stay light */
    }
  }, []);
  useEffect(() => {
    if (mode !== "system") return;
    const query = matchMedia("(prefers-color-scheme: dark)");
    const follow = () => apply("system");
    query.addEventListener("change", follow);
    return () => query.removeEventListener("change", follow);
  }, [mode]);

  const setMode = (next: Mode) => {
    setModeState(next);
    apply(next);
    try {
      localStorage.setItem("lexdesk.mode", next);
    } catch {
      /* not remembered, but still applied */
    }
  };
  return { mode, setMode };
}

/** The sun/moon button in every header. */
export function ThemeToggle({ className = "icon-btn" }: { className?: string }) {
  const { mode, setMode } = useMode();
  const dark = mode === "dark" || (mode === "system" && typeof document !== "undefined" && document.documentElement.dataset.mode === "dark");
  return (
    <button
      type="button"
      className={className}
      onClick={() => setMode(dark ? "light" : "dark")}
      aria-label={dark ? "Switch to light theme" : "Switch to dark theme"}
      title={dark ? "Light theme" : "Dark theme"}
    >
      <Icon name={dark ? "sun" : "moon"} />
    </button>
  );
}

/** Light / Dark / Same as my device, for the profile page. */
export function ModePicker() {
  const { mode, setMode } = useMode();
  return (
    <div className="segmented" role="group" aria-label="Theme">
      {(
        [
          ["light", "Light"],
          ["dark", "Dark"],
          ["system", "Same as my device"],
        ] as [Mode, string][]
      ).map(([k, l]) => (
        <button key={k} type="button" aria-pressed={mode === k} onClick={() => setMode(k)}>
          {l}
        </button>
      ))}
    </div>
  );
}
