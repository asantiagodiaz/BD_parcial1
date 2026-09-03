import { createContext, useContext } from "react";

/**
 * 5.5.4 - estado global de locale y moneda. En el MVP hay una sola configuracion
 * activa (es-CO / COP), pero los componentes de precio y fecha la consumen de
 * contexto y no de constantes, para no rehacer la UI al internacionalizar.
 */
const DEFAULTS = {
  locale: "es-CO",
  // moneda de presentacion por defecto; la real de cada precio llega de la API
  currency: "COP",
};

const ConfigContext = createContext(DEFAULTS);

export function ConfigProvider({ children }) {
  // Aqui iria un selector de idioma/moneda; el MVP fija los valores.
  return (
    <ConfigContext.Provider value={DEFAULTS}>{children}</ConfigContext.Provider>
  );
}

export function useConfig() {
  return useContext(ConfigContext);
}

/** Formatea { monto, moneda } segun el locale activo. NO convierte importes. */
export function useFormatters() {
  const { locale } = useConfig();
  return {
    money: (monto, moneda) =>
      new Intl.NumberFormat(locale, {
        style: "currency",
        currency: moneda || DEFAULTS.currency,
        maximumFractionDigits: 0,
      }).format(monto),
    dateTime: (iso) =>
      new Intl.DateTimeFormat(locale, {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(new Date(iso)),
    time: (iso) =>
      new Intl.DateTimeFormat(locale, { timeStyle: "short" }).format(
        new Date(iso)
      ),
    date: (iso) =>
      new Intl.DateTimeFormat(locale, { dateStyle: "medium" }).format(
        new Date(iso)
      ),
  };
}
