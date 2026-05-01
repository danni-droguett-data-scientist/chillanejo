import { useState } from "react";
import { RefreshCw, TrendingUp, DollarSign, Users, Server } from "lucide-react";
import { useCeo } from "@/hooks/useCeo";
import { TarjetaKpi } from "@/components/dashboard/TarjetaKpi";
import { ChatClaude } from "@/components/ceo/ChatClaude";
import { clp } from "@/lib/formato";
import {
  XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, BarChart, Bar,
} from "recharts";

const ETAPA_COLOR: Record<string, string> = {
  prospecto:   "bg-gray-100 text-gray-600",
  propuesta:   "bg-blue-50 text-blue-700",
  negociacion: "bg-amber-50 text-amber-700",
  cerrado:     "bg-emerald-50 text-emerald-700",
};

export default function DashboardCeo() {
  const { resumen, rentabilidad, pipeline, clientes, cargando, error, refetch } = useCeo();
  const [tabActiva, setTabActiva] = useState<"finanzas" | "pipeline">("finanzas");

  // Contexto de negocio resumido para Claude
  const contextoNegocio = resumen
    ? `Honorarios mes actual: ${clp(resumen.honorarios_mes_actual)}. ` +
      `Costos stack mes: ${clp(resumen.costos_mes_actual)}. ` +
      `Pipeline total: ${clp(resumen.pipeline_total)}. ` +
      `Clientes DS activos: ${resumen.clientes_activos}.`
    : undefined;

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="border-b bg-white px-6 py-4 flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-gray-900">Dashboard CEO</h1>
          <p className="text-xs text-gray-400 mt-0.5">Daniel Droguett · Vista personal</p>
        </div>
        <button
          onClick={refetch}
          disabled={cargando}
          className="flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-50 disabled:opacity-50 transition-colors"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${cargando ? "animate-spin" : ""}`} />
          Actualizar
        </button>
      </header>

      {error && (
        <div className="mx-6 mt-4 rounded-lg border border-red-100 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      <main className="p-6 space-y-6 max-w-[1400px] mx-auto">

        {/* KPIs CEO */}
        <section className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <TarjetaKpi
            titulo="Honorarios DS (mes)"
            valor={resumen?.honorarios_mes_actual ?? null}
            icono={<DollarSign className="h-4 w-4" />}
            cargando={cargando}
          />
          <TarjetaKpi
            titulo="Honorarios acumulado año"
            valor={resumen?.honorarios_acumulado_anio ?? null}
            icono={<TrendingUp className="h-4 w-4" />}
            cargando={cargando}
          />
          <TarjetaKpi
            titulo="Costos stack (mes)"
            valor={resumen?.costos_mes_actual ?? null}
            icono={<Server className="h-4 w-4" />}
            cargando={cargando}
          />
          <TarjetaKpi
            titulo="Pipeline DS"
            valor={resumen?.pipeline_total ?? null}
            subtitulo={`${resumen?.clientes_activos ?? "—"} clientes activos`}
            icono={<Users className="h-4 w-4" />}
            cargando={cargando}
          />
        </section>

        {/* Tabs */}
        <div className="flex gap-1 border-b">
          {(["finanzas", "pipeline"] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setTabActiva(tab)}
              className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors capitalize ${
                tabActiva === tab
                  ? "border-blue-600 text-blue-600"
                  : "border-transparent text-gray-500 hover:text-gray-700"
              }`}
            >
              {tab === "finanzas" ? "Finanzas personales" : "Pipeline DS"}
            </button>
          ))}
        </div>

        {tabActiva === "finanzas" && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Rentabilidad mensual */}
            <section className="rounded-xl border bg-white p-5 shadow-sm">
              <h2 className="text-sm font-semibold text-gray-700 mb-4">
                Ingresos vs costos — evolución mensual
              </h2>
              {cargando ? (
                <div className="h-56 animate-pulse rounded-lg bg-gray-100" />
              ) : (
                <ResponsiveContainer width="100%" height={224}>
                  <BarChart data={rentabilidad} margin={{ left: 4, right: 4 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                    <XAxis
                      dataKey="mes"
                      tickFormatter={(v) =>
                        new Date(v).toLocaleDateString("es-CL", { month: "short", year: "2-digit" })
                      }
                      tick={{ fontSize: 10, fill: "#9ca3af" }}
                      tickLine={false}
                      axisLine={false}
                    />
                    <YAxis
                      tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`}
                      tick={{ fontSize: 10, fill: "#9ca3af" }}
                      tickLine={false}
                      axisLine={false}
                      width={48}
                    />
                    <Tooltip
                      formatter={(v: number, name: string) => [
                        clp(v),
                        name === "ingresos_total" ? "Ingresos" :
                        name === "costos_total"   ? "Costos"   : "Utilidad",
                      ]}
                    />
                    <Bar dataKey="ingresos_total" fill="#bfdbfe" radius={[2, 2, 0, 0]} maxBarSize={24} name="Ingresos" />
                    <Bar dataKey="costos_total"   fill="#fca5a5" radius={[2, 2, 0, 0]} maxBarSize={24} name="Costos" />
                    <Bar dataKey="utilidad_neta"  fill="#34d399" radius={[2, 2, 0, 0]} maxBarSize={24} name="Utilidad" />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </section>

            {/* Chat Claude */}
            <ChatClaude contextoNegocio={contextoNegocio} />
          </div>
        )}

        {tabActiva === "pipeline" && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Embudo */}
            <section className="rounded-xl border bg-white p-5 shadow-sm">
              <h2 className="text-sm font-semibold text-gray-700 mb-4">Pipeline por etapa</h2>
              <div className="space-y-3">
                {pipeline.map((etapa) => (
                  <div key={etapa.etapa} className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${ETAPA_COLOR[etapa.etapa] ?? "bg-gray-100"}`}>
                        {etapa.etapa}
                      </span>
                      <span className="text-sm text-gray-500">{etapa.cantidad}</span>
                    </div>
                    <span className="text-sm font-semibold text-gray-800 tabular-nums">
                      {clp(etapa.valor_pipeline)}
                    </span>
                  </div>
                ))}
                {!pipeline.length && !cargando && (
                  <p className="text-sm text-gray-400 py-4 text-center">Sin clientes en pipeline</p>
                )}
              </div>
            </section>

            {/* Tabla clientes */}
            <section className="lg:col-span-2 rounded-xl border bg-white p-5 shadow-sm">
              <h2 className="text-sm font-semibold text-gray-700 mb-4">Clientes DS</h2>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-xs text-gray-400 uppercase tracking-wide">
                      <th className="pb-2 text-left font-medium">Empresa</th>
                      <th className="pb-2 text-left font-medium">Contacto</th>
                      <th className="pb-2 text-left font-medium">Etapa</th>
                      <th className="pb-2 text-right font-medium">Valor</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-50">
                    {clientes.map((c) => (
                      <tr key={c.id} className="hover:bg-gray-50">
                        <td className="py-2.5 font-medium text-gray-800">{c.empresa}</td>
                        <td className="py-2.5 text-gray-500">{c.contacto ?? "—"}</td>
                        <td className="py-2.5">
                          <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${ETAPA_COLOR[c.etapa] ?? "bg-gray-100"}`}>
                            {c.etapa}
                          </span>
                        </td>
                        <td className="py-2.5 text-right tabular-nums text-gray-700">
                          {c.valor_estimado ? clp(c.valor_estimado) : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          </div>
        )}

      </main>
    </div>
  );
}
