import { BrowserRouter, Route, Routes } from "react-router";
import { AuthProvider } from "./auth/AuthProvider";
import { GuestOnly, RequireSession } from "./routes";
import { KitShowcase } from "./screens/KitShowcase";
import { MagicLink } from "./screens/MagicLink";
import { Help } from "./screens/Help";
import { Home } from "./screens/Home";
import { Onboarding } from "./screens/Onboarding";
import { Splash } from "./screens/Splash";
import { Welcome } from "./screens/Welcome";

export function AppRoutes({ showKit = false }: { showKit?: boolean }) {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/" element={<Splash />} />
        <Route path="/welcome" element={<GuestOnly><Welcome /></GuestOnly>} />
        <Route path="/auth/tg" element={<MagicLink />} />
        <Route path="/onboarding" element={<RequireSession><Onboarding /></RequireSession>} />
        <Route path="/home" element={<RequireSession><Home /></RequireSession>} />
        <Route path="/help" element={<RequireSession><Help /></RequireSession>} />
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
