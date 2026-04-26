import { RefreshCw, ShoppingCart, TrendingUp, Users, Package } from "lucide-react";
import { useDashboard } from "@/hooks/useDashboard";
import { TarjetaKpi } from "@/components/dashboard/TarjetaKpi";
import { GraficoVentas } from "@/components/dashboard/GraficoVentas";
import { TablaTopProductos } from "@/components/dashboard/TablaTopProductos";
import { AlertasStock } from "@/components/dashboard/AlertasStock";
import { TablaUltimasVentas } from "@/components/dashboard/TablaUltimasVentas";
import { variacion } from "@/lib/formato";

export default function DashboardOperativo() {
  const {
    kpis,
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

        {/* Fila 2: Gráfico ventas 30 días */}
        <section className="rounded-xl border bg-white p-5 shadow-sm">
          <h2 className="text-sm font-semibold text-gray-700 mb-4">
            Ingresos netos — últimos 30 días
          </h2>
          <GraficoVentas datos={ventasPorDia} cargando={cargando} />
        </section>

        {/* Fila 3: Top productos + Alertas stock */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <section className="rounded-xl border bg-white p-5 shadow-sm">
            <h2 className="text-sm font-semibold text-gray-700 mb-4">
              Top 10 productos — mes actual
            </h2>
            <TablaTopProductos datos={topProductos} cargando={cargando} />
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
