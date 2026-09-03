import esCO from "./es-CO.json";

// 5.5.4 - textos externalizados. Anadir un idioma = anadir un JSON aqui.
const CATALOGS = { "es-CO": esCO };

/** t("clave", { var: valor }) -> texto con {var} interpolado. */
export function makeT(locale) {
  const cat = CATALOGS[locale] || esCO;
  return (key, vars) => {
    let s = cat[key] ?? key;
    if (vars) {
      for (const [k, v] of Object.entries(vars)) {
        s = s.replaceAll(`{${k}}`, String(v));
      }
    }
    return s;
  };
}
