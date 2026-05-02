const CLP = new Intl.NumberFormat("es-CL", {
  style: "currency",
  currency: "CLP",
  maximumFractionDigits: 0,
});

const NUM = new Intl.NumberFormat("es-CL", { maximumFractionDigits: 0 });

export const clp = (valor: number | null | undefined): string =>
  valor == null ? "—" : CLP.format(valor);

export const num = (valor: number | null | undefined): string =>
  valor == null ? "—" : NUM.format(valor);

export const pct = (valor: number | null | undefined, decimales = 1): string =>
  valor == null ? "—" : `${valor.toFixed(decimales)}%`;

const MESES = ["ene","feb","mar","abr","may","jun","jul","ago","sep","oct","nov","dic"];

// Parsea "YYYY-MM-DD" directamente para evitar el bug UTC→local de new Date("YYYY-MM-DD")
export const fechaCorta = (iso: string): string => {
  const [, m, d] = iso.slice(0, 10).split("-");
  return `${d}-${MESES[parseInt(m) - 1]}`;
};

export const variacion = (actual: number, anterior: number): number | null => {
  if (!anterior) return null;
  return ((actual - anterior) / anterior) * 100;
};
