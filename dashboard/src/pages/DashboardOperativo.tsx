import { useState } from "react";
import { RefreshCw, ShoppingCart, TrendingUp, Users, Package } from "lucide-react";
import { useDashboard } from "@/hooks/useDashboard";
import type { TopProducto } from "@/hooks/useDashboard";
import { TarjetaKpi } from "@/components/dashboard/TarjetaKpi";
import { GraficoVentas } from "@/components/dashboard/GraficoVentas";
import { TablaTopProductos } from "@/components/dashboard/TablaTopProductos";
import { AlertasStock } from "@/components/dashboard/AlertasStock";
import { TablaUltimasVentas } from "@/components/dashboard/TablaUltimasVentas";
import { clp, variacion } from "@/lib/formato";

type CanalFiltro = "todos" | "presencial" | "online";

const TABS_CANAL: { key: CanalFiltro; label: string }[] = [
  { key: "todos",      label: "Todos"      },
  { key: "presencial", label: "Presencial" },
  { key: "online",     label: "Online"     },
];

// Dado el filtro activo, remapea ingresos_netos y re-rankea el top 10
function filtrarTop(datos: TopProducto[], canal: CanalFiltro): TopProducto[] {
  const mapeados = datos.map((p) => ({
    ...p,
    ingresos_netos:
      canal === "presencial" ? p.ingresos_presencial :
      canal === "online"     ? p.ingresos_online     :
      p.ingresos_netos,
  }));

  if (canal === "todos") return mapeados;

  return mapeados
    .filter((p) => p.ingresos_netos > 0)
    .sort((a, b) => b.ingresos_netos - a.ingresos_netos)
    .slice(0, 10)
    .map((p, i) => ({ ...p, rank_ingresos: i + 1 }));
}

export default function DashboardOperativo() {
  const [canalFiltro, setCanalFiltro] = useState<CanalFiltro>("todos");

  const {
    kpis,
    desglosHoy,
    desglossemana,
    ventasPorDia,
    topProductos,
    stockCritico,
    resumenStock,
    ultimasVentas,
    cargando,
    error,
    ultimaActualizacion,
    refetch,
  } = useDashboard();

  const varMes = variacion(
    kpis?.mes.ingresos_netos ?? 0,
    kpis?.mes_anterior.ingresos_netos ?? 0,
  );

  const topFiltrado = filtrarTop(topProductos, canalFiltro);

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="border-b bg-white px-6 py-4 flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-gray-900">Dashboard Operativo</h1>
          <p className="text-xs text-gray-400 mt-0.5">El Chillanejo · Distribuidora</p>
        </div>
        <div className="flex items-center gap-3">
          {ultimaActualizacion && (
            <span className="text-xs text-gray-400 hidden sm:block">
              Actualizado {ultimaActualizacion.toLocaleTimeString("es-CL", { hour: "2-digit", minute: "2-digit" })}
            </span>
          )}
          <button
            onClick={refetch}
            disabled={cargando}
            className="flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-50 disabled:opacity-50 transition-colors"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${cargando ? "animate-spin" : ""}`} />
            Actualizar
          </button>
        </div>
      </header>

      {/* Error */}
      {error && (
        <div className="mx-6 mt-4 rounded-lg border border-red-100 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      <main className="p-6 space-y-6 max-w-[1400px] mx-auto">

        {/* Fila 1: KPIs principales */}
        <section className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <TarjetaKpi
            titulo="Ventas hoy"
            valor={kpis?.hoy.ingresos_netos ?? null}
            subtitulo={`${kpis?.hoy.num_ventas ?? "—"} transacciones`}
            icono={<ShoppingCart className="h-4 w-4" />}
            cargando={cargando}
          />
          <TarjetaKpi
            titulo="Ventas esta semana"
            valor={kpis?.semana.ingresos_netos ?? null}
            subtitulo={`${kpis?.semana.num_ventas ?? "—"} transacciones`}
            icono={<TrendingUp className="h-4 w-4" />}
            cargando={cargando}
          />
          <TarjetaKpi
            titulo="Ventas este mes"
            valor={kpis?.mes.ingresos_netos ?? null}
            variacionPct={varMes}
            subtitulo="vs mes anterior"
            icono={<Users className="h-4 w-4" />}
            cargando={cargando}
          />
          <TarjetaKpi
            titulo="Alertas de stock"
            valor={resumenStock?.total ?? null}
            formato="numero"
            subtitulo={
              resumenStock
                ? `${resumenStock.sin_stock} sin stock · ${resumenStock.critico} críticos`
                : undefined
            }
            icono={<Package className="h-4 w-4" />}
            cargando={cargando}
          />
        </section>

        {/* Fila 1b: Desglose por canal — hoy y semana */}
        {!cargando && desglosHoy && desglossemana && (
          <section className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {/* Hoy por canal */}
            <div className="rounded-xl border bg-white px-5 py-3.5 flex flex-wrap items-center gap-x-5 gap-y-1 text-sm shadow-sm">
              <span className="text-xs font-medium text-gray-400 uppercase tracking-wide mr-1">Hoy</span>
              <span className="flex items-center gap-1.5">
                <span className="inline-block h-2 w-2 rounded-full bg-gray-400" />
                <span className="text-gray-500">Presencial</span>
                <span className="font-semibold text-gray-800 tabular-nums">
                  {clp(desglosHoy.presencial.ingresos_netos)}
                </span>
                <span className="text-gray-300 text-xs">
                  ({desglosHoy.presencial.num_ventas} vtас)
                </span>
              </span>
              <span className="flex items-center gap-1.5">
                <span className="inline-block h-2 w-2 rounded-full bg-blue-500" />
                <span className="text-gray-500">Online</span>
                <span className="font-semibold text-blue-700 tabular-nums">
                  {clp(desglosHoy.online.ingresos_netos)}
                </span>
                <span className="text-gray-300 text-xs">
                  ({desglosHoy.online.num_ventas} vtас)
                </span>
              </span>
            </div>

            {/* Semana por canal */}
            <div className="rounded-xl border bg-white px-5 py-3.5 flex flex-wrap items-center gap-x-5 gap-y-1 text-sm shadow-sm">
              <span className="text-xs font-medium text-gray-400 uppercase tracking-wide mr-1">Semana</span>
              <span className="flex items-center gap-1.5">
                <span className="inline-block h-2 w-2 rounded-full bg-gray-400" />
                <span className="text-gray-500">Presencial</span>
                <span className="font-semibold text-gray-800 tabular-nums">
                  {clp(desglossemana.presencial.ingresos_netos)}
                </span>
                <span className="text-gray-300 text-xs">
                  ({desglossemana.presencial.num_ventas} vtас)
                </span>
              </span>
              <span className="flex items-center gap-1.5">
                <span className="inline-block h-2 w-2 rounded-full bg-blue-500" />
                <span className="text-gray-500">Online</span>
                <span className="font-semibold text-blue-700 tabular-nums">
                  {clp(desglossemana.online.ingresos_netos)}
                </span>
                <span className="text-gray-300 text-xs">
                  ({desglossemana.online.num_ventas} vtас)
                </span>
              </span>
            </div>
          </section>
        )}

        {/* Fila 2: Gráfico ventas 30 días */}
        <section className="rounded-xl border bg-white p-5 shadow-sm">
          <h2 className="text-sm font-semibold text-gray-700 mb-4">
            Ingresos netos — mes actual
          </h2>
          <GraficoVentas datos={ventasPorDia} cargando={cargando} />
        </section>

        {/* Fila 3: Top productos + Alertas stock */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <section className="rounded-xl border bg-white p-5 shadow-sm">
            {/* Header con filtro canal */}
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-semibold text-gray-700">
                Top 10 productos — mes actual
              </h2>
              <div className="flex gap-1">
                {TABS_CANAL.map(({ key, label }) => (
                  <button
                    key={key}
                    onClick={() => setCanalFiltro(key)}
                    className={`px-2.5 py-1 rounded-full text-xs font-medium transition-colors ${
                      canalFiltro === key
                        ? "bg-gray-900 text-white"
                        : "bg-gray-100 text-gray-500 hover:bg-gray-200"
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
            <TablaTopProductos datos={topFiltrado} cargando={cargando} />
          </section>

          <section className="rounded-xl border bg-white p-5 shadow-sm">
            <h2 className="text-sm font-semibold text-gray-700 mb-4">
              Alertas de stock
            </h2>
            <AlertasStock
              items={stockCritico}
              resumen={resumenStock}
              cargando={cargando}
            />
          </section>
        </div>

        {/* Fila 4: Últimas ventas */}
        <section className="rounded-xl border bg-white p-5 shadow-sm">
          <h2 className="text-sm font-semibold text-gray-700 mb-4">
            Últimas ventas
          </h2>
          <TablaUltimasVentas datos={ultimasVentas} cargando={cargando} />
        </section>

      </main>
    </div>
  );
}
