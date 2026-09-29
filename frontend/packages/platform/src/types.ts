/** The seam that makes the app portable across shells (ARCHITECTURE §4.2). */

export type PlatformKind = "pwa" | "telegram_mini_app";
export type DisplayMode = "browser" | "standalone";
export type DeviceOs = "android" | "ios" | "desktop" | "other";

export interface KeyValueStorage {
  get<T>(key: string): Promise<T | undefined>;
  set<T>(key: string, value: T): Promise<void>;
  del(key: string): Promise<void>;
}

export interface SharePayload {
  title?: string;
  text?: string;
  url?: string;
}

/** Add-to-home-screen (screen C, "добавьте на главный экран"). Added to §4.2 in this project. */
export interface InstallApi {
  os(): DeviceOs;
  isInstalled(): boolean;
  /** true when the browser offered a native install prompt (Chromium `beforeinstallprompt`). */
  canPrompt(): boolean;
  /** Shows the native prompt; resolves to the user's choice. */
  prompt(): Promise<"accepted" | "dismissed" | "unavailable">;
  /** iOS has no prompt API: the UI shows manual instructions instead. */
  needsManualInstructions(): boolean;
  onChange(listener: () => void): () => void;
}

export interface LaunchContext {
  startParam?: string;
  utm?: Record<string, string>;
}

export interface PlatformAdapter {
  kind: PlatformKind;
  displayMode(): DisplayMode;
  launchContext(): LaunchContext;
  storage: KeyValueStorage;
  share(payload: SharePayload): Promise<"shared" | "copied" | "cancelled">;
  openLink(url: string, opts?: { newTab?: boolean }): void;
  install?: InstallApi;
}
