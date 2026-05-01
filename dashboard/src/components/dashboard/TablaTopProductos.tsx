import { clp, num, pct } from "@/lib/formato";
import type { TopProducto } from "@/hooks/useDashboard";

interface Props {
  datos: TopProducto[];
  cargando?: boolean;
}

const BADGE_MARGEN: Record<string, string> = {
  alto:  "bg-emerald-50 text-emerald-700",
  medio: "bg-amber-50 text-amber-700",
  bajo:  "bg-red-50 text-red-600",
};

function nivelMargen(m: number | null): "alto" | "medio" | "bajo" | null {
  if (m == null) return null;
  if (m >= 30) return "alto";
  if (m >= 15) return "medio";
  return "bajo";
}

export function TablaTopProductos({ datos, cargando = false }: Props) {
  if (cargando) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="h-10 animate-pulse rounded bg-gray-100" />
        ))}
      </div>
    );
  }

  if (!datos.length) {
    return (
      <p className="py-8 text-center text-sm text-gray-400">Sin ventas en el período</p>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b text-xs text-gray-400 uppercase tracking-wide">
            <th className="pb-2 text-left font-medium w-8">#</th>
            <th className="pb-2 text-left font-medium">Producto</th>
            <th className="pb-2 text-right font-medium">Unidades</th>
            <th className="pb-2 text-right font-medium">Ingresos</th>
            <th className="pb-2 text-right font-medium">Margen</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-50">
          {datos.map((p) => {
            const nivel = nivelMargen(p.margen_pct);
            return (
              <tr key={p.codigo_producto} className="hover:bg-gray-50 transition-colors">
                <td className="py-2.5 text-gray-400 font-mono text-xs">
                  {p.rank_ingresos}
                </td>
                <td className="py-2.5">
                  <p className="font-medium text-gray-800 truncate max-w-[200px]">
                    {p.nombre_producto}
                  </p>
                  <p className="text-xs text-gray-400">{p.codigo_producto}</p>
                </td>
                <td className="py-2.5 text-right tabular-nums text-gray-600">
                  {num(p.unidades_vendidas)}
                </td>
                <td className="py-2.5 text-right tabular-nums font-medium text-gray-800">
                  {clp(p.ingresos_netos)}
                </td>
                <td className="py-2.5 text-right">
                  {nivel ? (
                    <span
                      className={`inline-block rounded-full px-2 py-0.5 text-xs font-semibold ${BADGE_MARGEN[nivel]}`}
                    >
                      {pct(p.margen_pct)}
                    </span>
                  ) : (
                    <span className="text-gray-300 text-xs">—</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
