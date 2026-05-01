import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { clp, fechaCorta } from "@/lib/formato";
import type { VentaDia } from "@/hooks/useDashboard";

interface Props {
  datos: VentaDia[];
  cargando?: boolean;
}

// Para períodos cortos mostramos todos los ticks; para rangos largos cada 5 días.
function intervalEjeX(totalDias: number): number | "preserveStartEnd" {
  if (totalDias <= 7) return 0;
  if (totalDias <= 31) return 4;
  return "preserveStartEnd";
}

function TooltipPersonalizado({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border bg-white px-3 py-2 shadow-md text-sm">
      <p className="font-medium text-gray-700 mb-1">{fechaCorta(label)}</p>
      <p className="text-blue-600 font-semibold">{clp(payload[0]?.value)}</p>
      <p className="text-gray-400">{payload[1]?.value ?? 0} ventas</p>
    </div>
  );
}

export function GraficoVentas({ datos, cargando = false }: Props) {
  if (cargando) {
    return (
      <div className="h-64 w-full animate-pulse rounded-lg bg-gray-100" />
    );
  }

  if (!datos.length) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-gray-400">
        Sin datos disponibles
      </div>
    );
  }

  const xInterval = intervalEjeX(datos.length);

  return (
    <ResponsiveContainer width="100%" height={260}>
      <BarChart data={datos} margin={{ top: 4, right: 8, left: 8, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
        <XAxis
          dataKey="fecha"
          tickFormatter={fechaCorta}
          tick={{ fontSize: 11, fill: "#9ca3af" }}
          tickLine={false}
          axisLine={false}
          interval={xInterval}
        />
        <YAxis
          tickFormatter={(v) => `$${(v / 1_000_000).toFixed(1)}M`}
          tick={{ fontSize: 11, fill: "#9ca3af" }}
          tickLine={false}
          axisLine={false}
          width={52}
        />
        <Tooltip content={<TooltipPersonalizado />} cursor={{ fill: "#f5f5f5" }} />
        <Bar
          dataKey="ingresos_netos"
          fill="#2563eb"
          radius={[3, 3, 0, 0]}
          maxBarSize={32}
        />
      </BarChart>
    </ResponsiveContainer>
  );
}
