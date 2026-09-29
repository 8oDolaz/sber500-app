/**
 * Client events. Must match the backend catalog
 * (backend/src/planner/modules/analytics/catalog.py) — the server rejects anything else.
 */
export type Os = "android" | "ios" | "desktop" | "other";

export interface ClientEvents {
  screen_viewed: { screen: "splash" | "welcome" | "onboarding" | "home" | "help" };
  register_clicked: Record<string, never>;
  a2hs_prompted: { os: Os };
  a2hs_accepted: { os: Os };
  a2hs_instructions_shown: { os: Os };
  how_to_clicked: Record<string, never>;
}

export type ClientEventName = keyof ClientEvents;
