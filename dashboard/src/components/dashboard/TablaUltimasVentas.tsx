import { clp, fechaCorta } from "@/lib/formato";
import type { UltimaVenta } from "@/hooks/useDashboard";

interface Props {
  datos: UltimaVenta[];
  cargando?: boolean;
}

const BADGE_TIPO: Record<string, string> = {
  Boleta:        "bg-blue-50 text-blue-700",
  Factura:       "bg-purple-50 text-purple-700",
  "Nota de Venta": "bg-gray-100 text-gray-600",
};

export function TablaUltimasVentas({ datos, cargando = false }: Props) {
  if (cargando) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="h-10 animate-pulse rounded bg-gray-100" />
        ))}
      </div>
    );
  }

  if (!datos.length) {
    return (
      <p className="py-8 text-center text-sm text-gray-400">Sin ventas recientes</p>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b text-xs text-gray-400 uppercase tracking-wide">
            <th className="pb-2 text-left font-medium">Fecha</th>
            <th className="pb-2 text-left font-medium">Tipo</th>
            <th className="pb-2 text-left font-medium">Folio</th>
            <th className="pb-2 text-left font-medium">Forma de pago</th>
            <th className="pb-2 text-right font-medium">Total neto</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-50">
          {datos.map((v) => (
            <tr key={v.id} className="hover:bg-gray-50 transition-colors">
              <td className="py-2.5 text-gray-500 tabular-nums">
                {fechaCorta(v.fecha_emision)}
              </td>
              <td className="py-2.5">
                <span
                  className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${
                    BADGE_TIPO[v.tipo_nombre] ?? "bg-gray-100 text-gray-600"
                  }`}
                >
                  {v.tipo_nombre}
                </span>
              </td>
              <td className="py-2.5 tabular-nums text-gray-700">
                {v.folio ?? <span className="text-gray-400">—</span>}
              </td>
              <td className="py-2.5 text-gray-700">
                {v.forma_pago ?? <span className="text-gray-400 italic">—</span>}
              </td>
              <td className="py-2.5 text-right tabular-nums font-medium text-gray-800">
                {clp(v.total_neto)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
