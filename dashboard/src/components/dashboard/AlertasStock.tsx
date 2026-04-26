import { AlertTriangle, PackageX, TrendingDown } from "lucide-react";
import { num } from "@/lib/formato";
import type { StockCritico, ResumenStockCritico } from "@/hooks/useDashboard";

interface Props {
  items: StockCritico[];
  resumen: ResumenStockCritico | null;
  cargando?: boolean;
}

const CONFIG_NIVEL = {
  sin_stock: {
    label: "Sin stock",
    icono: PackageX,
    clase: "text-red-600 bg-red-50 border-red-100",
    iconoClase: "text-red-500",
  },
  critico: {
    label: "Crítico",
    icono: AlertTriangle,
    clase: "text-amber-700 bg-amber-50 border-amber-100",
    iconoClase: "text-amber-500",
  },
  bajo: {
    label: "Stock bajo",
    icono: TrendingDown,
    clase: "text-blue-600 bg-blue-50 border-blue-100",
    iconoClase: "text-blue-400",
  },
} as const;

export function AlertasStock({ items, resumen, cargando = false }: Props) {
  if (cargando) {
    return <div className="h-40 animate-pulse rounded-lg bg-gray-100" />;
  }

  if (!resumen || resumen.total === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-8 text-center gap-2">
        <div className="rounded-full bg-emerald-50 p-3">
          <PackageX className="h-5 w-5 text-emerald-500" />
        </div>
        <p className="text-sm font-medium text-emerald-700">Stock saludable</p>
        <p className="text-xs text-gray-400">Ningún producto bajo el mínimo</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* Contadores resumen */}
      <div className="grid grid-cols-3 gap-2">
        {(["sin_stock", "critico", "bajo"] as const).map((nivel) => {
          const cfg = CONFIG_NIVEL[nivel];
          const Icono = cfg.icono;
          const count = resumen[nivel];
          if (!count) return null;
          return (
            <div
              key={nivel}
              className={`rounded-lg border px-3 py-2 flex items-center gap-2 ${cfg.clase}`}
            >
              <Icono className={`h-4 w-4 shrink-0 ${cfg.iconoClase}`} />
              <div>
                <p className="text-lg font-bold leading-none">{count}</p>
                <p className="text-xs mt-0.5 opacity-70">{cfg.label}</p>
              </div>
            </div>
          );
        })}
      </div>

      {/* Listado de productos */}
      <div className="divide-y divide-gray-50 max-h-72 overflow-y-auto">
        {items.map((item) => {
          const cfg = CONFIG_NIVEL[item.nivel_alerta];
          const Icono = cfg.icono;
          return (
            <div key={`${item.producto_id_relbase}-${item.bodega_nombre}`}
              className="flex items-center justify-between py-2.5 gap-3">
              <div className="flex items-center gap-2 min-w-0">
                <Icono className={`h-4 w-4 shrink-0 ${cfg.iconoClase}`} />
                <div className="min-w-0">
                  <p className="text-sm font-medium text-gray-800 truncate">
                    {item.nombre}
                  </p>
                  <p className="text-xs text-gray-400">
                    {item.bodega_nombre} · mín {num(item.stock_minimo)}
                  </p>
                </div>
              </div>
              <div className="text-right shrink-0">
                <p className={`text-sm font-bold tabular-nums ${
                  item.nivel_alerta === "sin_stock" ? "text-red-600" : "text-gray-700"
                }`}>
                  {num(item.cantidad_disponible)}
                </p>
                <p className="text-xs text-gray-400">disponible</p>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
