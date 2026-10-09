import type { DeviceOs, InstallApi } from "@kainem/platform";
import { useCallback, useEffect, useState } from "react";
import { useServices } from "./context";

/**
 * How screen C can help the user add the PWA to the home screen:
 * - prompt:   Chromium offered `beforeinstallprompt` → native dialog
 * - ios:      no API on iOS → step-by-step sheet (Safari → Share → «На экран „Домой“»)
 * - manual:   Android browser without the prompt → menu instructions
 * - hidden:   already installed, or a desktop without the prompt
 */
export type InstallMode = "prompt" | "ios" | "manual" | "hidden";

export function installModeOf(install: InstallApi | undefined): InstallMode {
  if (!install || install.isInstalled()) return "hidden";
  if (install.canPrompt()) return "prompt";
  if (install.needsManualInstructions()) return "ios";
  return install.os() === "android" ? "manual" : "hidden";
}

export function useInstall() {
  const { platform, analytics } = useServices();
  const install = platform.install;
  const [mode, setMode] = useState<InstallMode>(() => installModeOf(install));
  const [sheet, setSheet] = useState<"ios" | "manual" | null>(null);
  const os: DeviceOs = install?.os() ?? "other";

  useEffect(() => install?.onChange(() => setMode(installModeOf(install))), [install]);

  const offer = useCallback(async () => {
    if (!install) return;
    if (mode === "prompt") {
      analytics.track("a2hs_prompted", { os });
      if ((await install.prompt()) === "accepted") analytics.track("a2hs_accepted", { os });
      setMode(installModeOf(install));
    } else if (mode === "ios" || mode === "manual") {
      analytics.track("a2hs_instructions_shown", { os });
      setSheet(mode);
    }
  }, [analytics, install, mode, os]);

  return { mode, sheet, offer, closeSheet: () => setSheet(null) };
}
