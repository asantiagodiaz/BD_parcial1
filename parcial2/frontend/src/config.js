// Aeropuertos del dataset (los que usan las rutas de la semilla 963 mas MDE y CLO de demostracion).
export const AEROPUERTOS = ["ADZ", "BAQ", "BGA", "BOG", "CLO", "CTG", "CUC", "LET", "MDE", "PEI", "PSO", "SMR"];

// Las 9 rutas del historial del equipo (semilla 963). Ver parcial2/BITACORA.md.
export const RUTAS = [
  "CUC-BGA", "CTG-BOG", "CUC-SMR", "ADZ-CTG", "PSO-SMR",
  "SMR-BAQ", "ADZ-BAQ", "PSO-CUC", "BGA-BOG",
];

// price_cents llega en centavos
export const precio = (cents) =>
  new Intl.NumberFormat("es-CO", { style: "currency", currency: "COP", maximumFractionDigits: 0 }).format(cents / 100);

export const porcentaje = (fraccion) => `${(fraccion * 100).toFixed(2)}%`;

export const hoy = () => new Date().toISOString().slice(0, 10);
