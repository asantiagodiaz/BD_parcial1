import { Routes, Route, NavLink, Navigate } from "react-router-dom";
import { useConfig } from "./config.jsx";
import { makeT } from "./i18n/index.js";
import BuscarPage from "./pages/BuscarPage.jsx";
import SeleccionPage from "./pages/SeleccionPage.jsx";
import ConfirmacionPage from "./pages/ConfirmacionPage.jsx";
import MiReservaPage from "./pages/MiReservaPage.jsx";

export default function App() {
  const { locale } = useConfig();
  const t = makeT(locale);

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">✈</span>
          <div>
            <strong>{t("app.title")}</strong>
            <span className="brand-sub">{t("app.subtitle")}</span>
          </div>
        </div>
        <nav>
          <NavLink to="/buscar">{t("nav.buscar")}</NavLink>
          <NavLink to="/mi-reserva">{t("nav.miReserva")}</NavLink>
        </nav>
      </header>

      <main className="content">
        <Routes>
          <Route path="/" element={<Navigate to="/buscar" replace />} />
          <Route path="/buscar" element={<BuscarPage />} />
          <Route path="/seleccion" element={<SeleccionPage />} />
          <Route path="/confirmacion" element={<ConfirmacionPage />} />
          <Route path="/mi-reserva" element={<MiReservaPage />} />
          <Route path="/mi-reserva/:codigo" element={<MiReservaPage />} />
          <Route path="*" element={<Navigate to="/buscar" replace />} />
        </Routes>
      </main>

      <footer className="footer">
        Parcial 1 · Big Data · SPA React que consume la API REST (5.4/5.5)
      </footer>
    </div>
  );
}
