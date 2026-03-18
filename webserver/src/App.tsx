import { HashRouter, Routes, Route } from "react-router-dom";
import PlayersPage from "./pages/PlayersPage";
import PlayerProfile from "./pages/PlayerProfile";

export default function App() {
  return (
    <HashRouter>
      <Routes>
        <Route path="/" element={<PlayersPage />} />
        <Route path="/player/:name" element={<PlayerProfile />} />
      </Routes>
    </HashRouter>
  );
}
