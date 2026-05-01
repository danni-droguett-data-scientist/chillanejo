import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer,
} from "recharts";
import { clp } from "@/lib/formato";
import type { MesVenta } from "@/hooks/useEjecutivo";

interface Props {
  datos: MesVenta[];
  cargando?: boolean;
}

function TooltipCustom({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border bg-white px-3 py-2 shadow-md text-sm space-y-1">
      <p className="font-semibold text-gray-700">{label}</p>
      {payload.map((p: any) => (
        <p key={p.dataKey} style={{ color: p.color }}>
          {p.name}: {p.dataKey === "ingresos_netos" ? clp(p.value) : p.value}
        </p>
      ))}
    </div>
  );
}

export function GraficoTendencia({ datos, cargando = false }: Props) {
  if (cargando) return <div className="h-72 animate-pulse rounded-lg bg-gray-100" />;

  const datosFormateados = datos.map((d) => ({
    ...d,
    mes_label: new Date(d.mes).toLocaleDateString("es-CL", { month: "short", year: "2-digit" }),
  }));

  return (
    <ResponsiveContainer width="100%" height={288}>
      <LineChart data={datosFormateados} margin={{ top: 4, right: 16, left: 8, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
        <XAxis
          dataKey="mes_label"
          tick={{ fontSize: 11, fill: "#9ca3af" }}
          tickLine={false}
          axisLine={false}
        />
        <YAxis
          yAxisId="ingresos"
          tickFormatter={(v) => `$${(v / 1_000_000).toFixed(0)}M`}
          tick={{ fontSize: 11, fill: "#9ca3af" }}
          tickLine={false}
          axisLine={false}
          width={52}
        />
        <YAxis
          yAxisId="ventas"
          orientation="right"
          tick={{ fontSize: 11, fill: "#9ca3af" }}
          tickLine={false}
          axisLine={false}
          width={36}
        />
        <Tooltip content={<TooltipCustom />} />
        <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 12 }} />
        <Line
          yAxisId="ingresos"
          type="monotone"
          dataKey="ingresos_netos"
          name="Ingresos netos"
          stroke="#2563eb"
          strokeWidth={2}
          dot={{ r: 3 }}
          activeDot={{ r: 5 }}
        />
        <Line
          yAxisId="ventas"
          type="monotone"
          dataKey="num_ventas"
          name="N° ventas"
          stroke="#10b981"
          strokeWidth={2}
          strokeDasharray="4 2"
          dot={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
