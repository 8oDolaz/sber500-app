import { BrowserRouter, Route, Routes } from "react-router";
import { AuthProvider } from "./auth/AuthProvider";
import { GuestOnly, RequireSession } from "./routes";
import { KitShowcase } from "./screens/KitShowcase";
import { MagicLink } from "./screens/MagicLink";
import { Splash } from "./screens/Splash";
import { HomeStub, OnboardingStub } from "./screens/Stubs";
import { Welcome } from "./screens/Welcome";

export function AppRoutes({ showKit = false }: { showKit?: boolean }) {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/" element={<Splash />} />
        <Route path="/welcome" element={<GuestOnly><Welcome /></GuestOnly>} />
        <Route path="/auth/tg" element={<MagicLink />} />
        <Route path="/onboarding" element={<RequireSession><OnboardingStub /></RequireSession>} />
        <Route path="/home" element={<RequireSession><HomeStub /></RequireSession>} />
        {showKit ? <Route path="/_kit" element={<KitShowcase />} /> : null}
        <Route path="*" element={<Splash />} />
      </Routes>
    </AuthProvider>
  );
}

export function App({ showKit = false }: { showKit?: boolean }) {
  return (
    <BrowserRouter>
      <AppRoutes showKit={showKit} />
    </BrowserRouter>
  );
}
