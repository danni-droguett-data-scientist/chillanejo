import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, Cell, ResponsiveContainer,
} from "recharts";
import { clp, pct } from "@/lib/formato";
import type { MargenCategoria } from "@/hooks/useEjecutivo";

interface Props {
  datos: MargenCategoria[];
  cargando?: boolean;
}

const COLOR_MARGEN = (m: number | null) => {
  if (m == null) return "#d1d5db";
  if (m >= 30) return "#10b981";
  if (m >= 15) return "#f59e0b";
  return "#ef4444";
};

export function GraficoMargen({ datos, cargando = false }: Props) {
  if (cargando) return <div className="h-64 animate-pulse rounded-lg bg-gray-100" />;

  // Agrupa por categoría (suma el mes más reciente)
  const porCategoria = Object.values(
    datos.reduce<Record<string, MargenCategoria>>((acc, d) => {
      if (!acc[d.categoria] || d.mes > acc[d.categoria].mes) acc[d.categoria] = d;
      return acc;
    }, {})
  ).sort((a, b) => (b.ingresos_netos ?? 0) - (a.ingresos_netos ?? 0)).slice(0, 10);

  return (
    <ResponsiveContainer width="100%" height={256}>
      <BarChart data={porCategoria} layout="vertical" margin={{ left: 8, right: 40 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" horizontal={false} />
        <XAxis
          type="number"
          tickFormatter={(v) => `$${(v / 1_000_000).toFixed(1)}M`}
          tick={{ fontSize: 11, fill: "#9ca3af" }}
          tickLine={false}
          axisLine={false}
        />
        <YAxis
          type="category"
          dataKey="categoria"
          width={110}
          tick={{ fontSize: 11, fill: "#6b7280" }}
          tickLine={false}
          axisLine={false}
        />
        <Tooltip
          formatter={(value: number, name: string) =>
            name === "ingresos_netos" ? [clp(value), "Ingresos"] : [pct(value as any), "Margen"]
          }
          cursor={{ fill: "#f9fafb" }}
        />
        <Bar dataKey="ingresos_netos" radius={[0, 3, 3, 0]} maxBarSize={20}>
          {porCategoria.map((entry, i) => (
            <Cell key={i} fill={COLOR_MARGEN(entry.margen_pct)} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
