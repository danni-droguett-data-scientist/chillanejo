import { RefreshCw } from "lucide-react";
import { useEjecutivo } from "@/hooks/useEjecutivo";
import { TarjetaKpi } from "@/components/dashboard/TarjetaKpi";
import { GraficoTendencia } from "@/components/ejecutivo/GraficoTendencia";
import { GraficoMargen } from "@/components/ejecutivo/GraficoMargen";
import { TablaTopProductos } from "@/components/dashboard/TablaTopProductos";
import { clp, pct, variacion } from "@/lib/formato";

export default function DashboardEjecutivo() {
  const { tendencia, margenCategorias, topProductos, margenResumen, cargando, error, refetch } =
    useEjecutivo();

  const mesActual  = margenResumen?.mes_actual;
  const mesAnterior = margenResumen?.mes_anterior;
  const varIngresos = variacion(mesActual?.ingresos_netos ?? 0, mesAnterior?.ingresos_netos ?? 0);
  const varMargen   = variacion(mesActual?.margen_neto ?? 0, mesAnterior?.margen_neto ?? 0);

  const ultimoMes  = tendencia[tendencia.length - 1];
  const penultimo  = tendencia[tendencia.length - 2];
  const varTicket  = variacion(ultimoMes?.ticket_promedio ?? 0, penultimo?.ticket_promedio ?? 0);

  // Adapta topProductos al tipo esperado por TablaTopProductos
  const topAdaptado = topProductos.map((p, i) => ({
    codigo_producto: p.codigo_producto,
    nombre_producto: p.nombre_producto,
    unidades_vendidas: p.unidades_totales,
    ingresos_netos: p.ingresos_netos_total,
    margen_neto_total: p.margen_neto_total,
    margen_pct: p.margen_pct,
    num_transacciones: p.num_transacciones,
    rank_ingresos: i + 1,
  }));

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="border-b bg-white px-6 py-4 flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-gray-900">Dashboard Ejecutivo</h1>
          <p className="text-xs text-gray-400 mt-0.5">El Chillanejo · Resultados de gestión</p>
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

        {/* KPIs ejecutivos */}
        <section className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <TarjetaKpi
            titulo="Ingresos mes actual"
            valor={mesActual?.ingresos_netos ?? null}
            variacionPct={varIngresos}
            subtitulo="vs mes anterior"
            cargando={cargando}
          />
          <TarjetaKpi
            titulo="Margen bruto mes"
            valor={mesActual?.margen_neto ?? null}
            variacionPct={varMargen}
            subtitulo={mesActual?.margen_pct != null ? `${pct(mesActual.margen_pct)} del ingreso` : undefined}
            cargando={cargando}
          />
          <TarjetaKpi
            titulo="Ticket promedio"
            valor={ultimoMes?.ticket_promedio ?? null}
            variacionPct={varTicket}
            subtitulo="último mes cerrado"
            cargando={cargando}
          />
          <TarjetaKpi
            titulo="Ventas último mes"
            valor={ultimoMes?.ingresos_netos ?? null}
            formato="clp"
            subtitulo={`${ultimoMes?.num_ventas ?? "—"} transacciones`}
            cargando={cargando}
          />
        </section>

        {/* Tendencia 12 meses */}
        <section className="rounded-xl border bg-white p-5 shadow-sm">
          <h2 className="text-sm font-semibold text-gray-700 mb-4">
            Tendencia ingresos — últimos 12 meses
          </h2>
          <GraficoTendencia datos={tendencia} cargando={cargando} />
        </section>

        {/* Margen por categoría + Top productos */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <section className="rounded-xl border bg-white p-5 shadow-sm">
            <h2 className="text-sm font-semibold text-gray-700 mb-1">
              Ingresos por categoría
            </h2>
            <p className="text-xs text-gray-400 mb-4">
              Color indica margen: verde ≥30% · amarillo ≥15% · rojo &lt;15%
            </p>
            <GraficoMargen datos={margenCategorias} cargando={cargando} />
          </section>

          <section className="rounded-xl border bg-white p-5 shadow-sm">
            <h2 className="text-sm font-semibold text-gray-700 mb-4">
              Top 20 productos acumulado
            </h2>
            <TablaTopProductos datos={topAdaptado} cargando={cargando} />
          </section>
        </div>

      </main>
    </div>
  );
}
