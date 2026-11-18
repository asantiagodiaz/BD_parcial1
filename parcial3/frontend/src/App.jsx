import { Routes, Route, NavLink, Navigate } from "react-router-dom";
import BuscarPage from "./pages/BuscarPage.jsx";
import ManagerPage from "./pages/ManagerPage.jsx";

export default function App() {
  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">✈</span>
          <div>
            <strong>RegionalAir</strong>
            <span className="brand-sub">Reservas y panel gerencial</span>
          </div>
        </div>
        <nav>
          <NavLink to="/" end>Reservar</NavLink>
          <NavLink to="/manager">Panel gerencial</NavLink>
        </nav>
      </header>

      <main className="content">
        <Routes>
          <Route path="/" element={<BuscarPage />} />
          <Route path="/manager" element={<ManagerPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>

      <footer className="footer">
        Parcial 3 · Big Data e Ingeniería de Datos · eventos en Kinesis, vista en vivo y modelo estrella en Athena
      </footer>
    </div>
  );
}
