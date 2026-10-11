import { AppShell } from "../components/shell/AppShell";
import { isStandaloneTVRoute } from "../domain/tvRoute";

export default function Home() {
  return <AppShell standaloneTV={typeof window !== "undefined" && isStandaloneTVRoute(window.location.pathname, window.location.search)} />;
}
