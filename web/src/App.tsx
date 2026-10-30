import { Chat } from "./components/Chat";
import { DemoBanner } from "./components/DemoBanner";
import { Sidebar } from "./components/Sidebar";
import { DEMO_MODE } from "./lib/api";

export default function App() {
  return (
    <div className="shell">
      {DEMO_MODE && <DemoBanner />}
      <div className="layout">
        <Sidebar />
        <main className="main">
          <Chat />
        </main>
      </div>
    </div>
  );
}
