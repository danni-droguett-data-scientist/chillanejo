import { useEffect, useState, useCallback } from "react";
import { supabase } from "@/lib/supabase";

// ---------------------------------------------------------------------------
// Tipos
// ---------------------------------------------------------------------------

export type Periodo =
  | "hoy"
  | "ultimos_7_dias"
  | "ultimos_30_dias"
  | "mes_actual"
  | "mes_anterior";

interface RangoFechas {
  desde: string;
  hasta: string;
}

interface VentaRaw {
  fecha_emision: string;
  neto: number | null;
  total: number | null;
  canal?: string | null;
}

export interface KpiPeriodo {
  ingresos_netos: number;
  ingresos_brutos: number;
  num_ventas: number;
  ticket_promedio: number;
}

export interface KpisVentas {
  hoy: KpiPeriodo;
  semana: KpiPeriodo;
  mes: KpiPeriodo;
  mes_anterior: { ingresos_netos: number; num_ventas: number };
}

export interface DesglosCanal {
  presencial: KpiPeriodo;
  online: KpiPeriodo;
}

export interface VentaDia {
  fecha: string;
  ingresos_netos: number;
  num_ventas: number;
}

export interface TopProducto {
  codigo_producto: string;
  nombre_producto: string;
  unidades_vendidas: number;
  ingresos_netos: number;
  ingresos_presencial: number;
  ingresos_online: number;
  margen_neto_total: number | null;
  margen_pct: number | null;
  num_transacciones: number;
  rank_ingresos: number;
}

export interface StockCritico {
  producto_id_relbase: number;
  codigo: string;
  nombre: string;
  categoria_nombre: string | null;
  stock_minimo: number;
  bodega_nombre: string;
  cantidad_disponible: number;
  nivel_alerta: "sin_stock" | "critico" | "bajo";
}

export interface ResumenStockCritico {
  sin_stock: number;
  critico: number;
  bajo: number;
  total: number;
}

export interface UltimaVenta {
  id: string;
  fecha_emision: string;
  folio: string | null;
  tipo_nombre: string;
  forma_pago: string | null;
  total_neto: number;
  total_bruto: number;
  estado: string;
}

export interface DashboardData {
  kpis: KpisVentas | null;
  desglosHoy: DesglosCanal | null;
  desglossemana: DesglosCanal | null;
  ventasPorDia: VentaDia[];
  topProductos: TopProducto[];
  stockCritico: StockCritico[];
  resumenStock: ResumenStockCritico | null;
  ultimasVentas: UltimaVenta[];
  ultimaSyncRelbase: string | null;
  cargando: boolean;
  error: string | null;
  ultimaActualizacion: Date | null;
  refetch: () => void;
}

// ---------------------------------------------------------------------------
// Constantes
// ---------------------------------------------------------------------------

const TIPO_NOMBRE: Record<number, string> = {
  39:   "Boleta",
  33:   "Factura",
  1001: "Nota de Venta",
};

const NIVEL_ALERTA = (cantidad: number): StockCritico["nivel_alerta"] =>
  cantidad <= 0 ? "sin_stock" : cantidad <= 5 ? "critico" : "bajo";

const INTERVALO_REFRESH_MS = 60 * 60 * 1000; // 60 minutos

// ---------------------------------------------------------------------------
// Helpers de fecha — usan hora local (Santiago), NO UTC
// ---------------------------------------------------------------------------

// Formatea una Date usando componentes locales (año/mes/día del navegador).
// Evita el bug de timezone: new Date().toISOString() devuelve UTC, lo que
// después de las ~21-22h local (Chile UTC-3) retorna la fecha del día siguiente.
function fechaLocal(d: Date): string {
  const y  = d.getFullYear();
  const m  = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${dd}`;
}

// Parsea "YYYY-MM-DD" en hora local. new Date("YYYY-MM-DD") usa UTC, lo que
// provoca que en Chile (UTC-3) el día 1 del mes se lea como el día anterior.
function parsearFechaLocal(fecha: string): Date {
  const [y, m, d] = fecha.split("-").map(Number);
  return new Date(y, m - 1, d);
}

function inicioSemana(d: Date): string {
  const lunes = new Date(d);
  lunes.setDate(d.getDate() - ((d.getDay() + 6) % 7));
  return fechaLocal(lunes);
}

// Calcula el rango {desde, hasta} para el período seleccionado.
// Los KPIs operativos (hoy/semana/mes) NO usan este rango — siempre
// se derivan del mes actual para reflejar el estado real del negocio.
// Este rango solo afecta el gráfico de tendencia y el top de productos.
function rangoDeFechas(periodo: Periodo): RangoFechas {
  const ahora = new Date();
  const hoy   = fechaLocal(ahora);

  switch (periodo) {
    case "hoy":
      return { desde: hoy, hasta: hoy };

    case "ultimos_7_dias": {
      const inicio = new Date(ahora);
      inicio.setDate(ahora.getDate() - 6);
      return { desde: fechaLocal(inicio), hasta: hoy };
    }

    case "ultimos_30_dias": {
      const inicio = new Date(ahora);
      inicio.setDate(ahora.getDate() - 29);
      return { desde: fechaLocal(inicio), hasta: hoy };
    }

    case "mes_actual":
      return {
        desde: fechaLocal(new Date(ahora.getFullYear(), ahora.getMonth(), 1)),
        hasta: hoy,
      };

    case "mes_anterior":
      return {
        desde: fechaLocal(new Date(ahora.getFullYear(), ahora.getMonth() - 1, 1)),
        hasta: fechaLocal(new Date(ahora.getFullYear(), ahora.getMonth(), 0)),
      };
  }
}

function calcKpi(rows: VentaRaw[]): KpiPeriodo {
  const ingresos_netos  = rows.reduce((s, r) => s + (r.neto  ?? 0), 0);
  const ingresos_brutos = rows.reduce((s, r) => s + (r.total ?? 0), 0);
  const num_ventas      = rows.length;
  return {
    ingresos_netos,
    ingresos_brutos,
    num_ventas,
    ticket_promedio: num_ventas > 0 ? ingresos_netos / num_ventas : 0,
  };
}

// Construye el arreglo diario del gráfico rellenando días sin ventas con 0.
function construirVentasPorDia(
  desde: string,
  hasta: string,
  porDiaMap: Map<string, { ingresos_netos: number; num_ventas: number }>
): VentaDia[] {
  const result: VentaDia[] = [];
  const cursor = parsearFechaLocal(desde);
  const fin    = parsearFechaLocal(hasta);
  while (cursor <= fin) {
    const fecha = fechaLocal(cursor);
    result.push({ fecha, ...(porDiaMap.get(fecha) ?? { ingresos_netos: 0, num_ventas: 0 }) });
    cursor.setDate(cursor.getDate() + 1);
  }
  return result;
}

// ---------------------------------------------------------------------------
// Fetchers
// ---------------------------------------------------------------------------

// Trae todas las ventas de un rango paginando de a 1000 para superar el cap de PostgREST
async function fetchVentasPaginado(
  desde: string,
  hasta: string,
  campos: string
): Promise<VentaRaw[]> {
  const PAGE = 1000;
  const all: VentaRaw[] = [];
  let offset = 0;
  while (true) {
    const { data, error } = await supabase
      .from("ventas")
      .select(campos)
      .gte("fecha_emision", desde)
      .lte("fecha_emision", hasta)
      .order("fecha_emision")
      .range(offset, offset + PAGE - 1);
    if (error) throw error;
    all.push(...(data ?? []));
    if ((data?.length ?? 0) < PAGE) break;
    offset += PAGE;
  }
  return all;
}

// Top productos: pagina ventas_detalle con join a ventas filtrado por rango de fechas.
// Incluye canal para desgloses y filtros en la UI.
async function fetchTopProductos(desde: string, hasta: string): Promise<TopProducto[]> {
  const PAGE = 1000;
  const MAX_PAGES = 10;
  const rows: any[] = [];

  for (let page = 0; page < MAX_PAGES; page++) {
    const { data, error } = await supabase
      .from("ventas_detalle")
      .select(
        "relbase_producto_id, sku, nombre_producto, cantidad, total_neto, costo_unitario, venta_id, ventas!inner(fecha_emision, canal)"
      )
      .gte("ventas.fecha_emision", desde)
      .lte("ventas.fecha_emision", hasta)
      .not("relbase_producto_id", "is", null)
      .range(page * PAGE, (page + 1) * PAGE - 1);

    if (error) throw error;
    rows.push(...(data ?? []));
    if ((data?.length ?? 0) < PAGE) break;
  }

  type Acum = {
    codigo_producto: string;
    nombre_producto: string;
    unidades: number;
    ingresos: number;
    ingresos_presencial: number;
    ingresos_online: number;
    margen: number;
    tieneMargen: boolean;
    ventaIds: Set<string>;
  };
  const map = new Map<number, Acum>();

  for (const r of rows) {
    const key: number = r.relbase_producto_id;
    if (!map.has(key)) {
      map.set(key, {
        codigo_producto: r.sku ?? String(key),
        nombre_producto: r.nombre_producto ?? "Sin nombre",
        unidades: 0, ingresos: 0, ingresos_presencial: 0, ingresos_online: 0,
        margen: 0, tieneMargen: false, ventaIds: new Set(),
      });
    }
    const p  = map.get(key)!;
    const tn = r.total_neto ?? 0;
    const canal    = (r.ventas as any)?.canal ?? "presencial";
    const esOnline = canal !== "presencial";

    p.unidades += r.cantidad ?? 0;
    p.ingresos += tn;
    if (esOnline) {
      p.ingresos_online    += tn;
    } else {
      p.ingresos_presencial += tn;
    }
    if (r.costo_unitario != null) {
      p.margen     += tn - r.costo_unitario * (r.cantidad ?? 0);
      p.tieneMargen = true;
    }
    if (r.venta_id) p.ventaIds.add(r.venta_id);
  }

  return Array.from(map.values())
    .sort((a, b) => b.ingresos - a.ingresos)
    .slice(0, 10)
    .map((p, i) => ({
      codigo_producto:     p.codigo_producto,
      nombre_producto:     p.nombre_producto,
      unidades_vendidas:   p.unidades,
      ingresos_netos:      p.ingresos,
      ingresos_presencial: p.ingresos_presencial,
      ingresos_online:     p.ingresos_online,
      margen_neto_total:   p.tieneMargen ? p.margen : null,
      margen_pct: p.tieneMargen && p.ingresos > 0
        ? Math.round((p.margen / p.ingresos) * 1000) / 10
        : null,
      num_transacciones: p.ventaIds.size,
      rank_ingresos: i + 1,
    }));
}

// Trae el timestamp de la última sincronización exitosa de DTEs desde Relbase.
// Retorna null si la tabla sync_log aún no tiene el registro o si falla la query.
async function fetchUltimaSync(): Promise<string | null> {
  const { data, error } = await supabase
    .from("sync_log")
    .select("ultima_sync")
    .eq("entidad", "dtes_diario")
    .single();
  if (error) return null;
  return (data as any)?.ultima_sync ?? null;
}

// ---------------------------------------------------------------------------
// Hook principal
// ---------------------------------------------------------------------------

export function useDashboard(periodo: Periodo = "mes_actual"): DashboardData {
  const [kpis,                setKpis]                = useState<KpisVentas | null>(null);
  const [desglosHoy,          setDesglosHoy]          = useState<DesglosCanal | null>(null);
  const [desglossemana,       setDesglossemana]       = useState<DesglosCanal | null>(null);
  const [ventasPorDia,        setVentasPorDia]        = useState<VentaDia[]>([]);
  const [topProductos,        setTopProductos]        = useState<TopProducto[]>([]);
  const [stockCritico,        setStockCritico]        = useState<StockCritico[]>([]);
  const [resumenStock,        setResumenStock]        = useState<ResumenStockCritico | null>(null);
  const [ultimasVentas,       setUltimasVentas]       = useState<UltimaVenta[]>([]);
  const [ultimaSyncRelbase,   setUltimaSyncRelbase]   = useState<string | null>(null);
  const [cargando,            setCargando]            = useState(true);
  const [error,               setError]               = useState<string | null>(null);
  const [ultimaActualizacion, setUltimaActualizacion] = useState<Date | null>(null);

  const cargarDatos = useCallback(async () => {
    setCargando(true);
    setError(null);

    try {
      const ahora = new Date();

      // Todas las fechas calculadas con hora LOCAL (Santiago), no UTC.
      // Bug previo: toISOString() devuelve UTC → después de ~21h local en Chile
      // la fecha avanzaba un día y los filtros client-side de "hoy" y "semana"
      // nunca coincidían con los datos de Relbase → KPIs mostraban $0.
      const hoy          = fechaLocal(ahora);
      const lunesSemana  = inicioSemana(ahora);
      const inicioMes    = fechaLocal(new Date(ahora.getFullYear(), ahora.getMonth(), 1));
      const inicioMesAnt = fechaLocal(new Date(ahora.getFullYear(), ahora.getMonth() - 1, 1));
      const finMesAnt    = fechaLocal(new Date(ahora.getFullYear(), ahora.getMonth(), 0));

      // Rango del período seleccionado (gráfico + top productos).
      // Si coincide con "mes_actual", reutilizamos ventasMes sin un fetch extra.
      const rango = rangoDeFechas(periodo);
      const rangoEsMesActual = rango.desde === inicioMes && rango.hasta === hoy;

      // Fase 1 — fetches en paralelo:
      //   · ventas del mes actual          → KPIs operativos + desglose canal
      //   · ventas mes anterior            → KPI comparativo
      //   · ventas del período seleccionado → gráfico (null si coincide con mes actual)
      //   · stock con embedding            → alertas
      //   · últimas ventas con embedding   → tabla
      //   · última sync Relbase            → indicador de frescura de datos
      const [ventasMes, ventasMesAnt, ventasPeriodoExtra, stockResp, ultimasResp, ultimaSync] =
        await Promise.all([
          fetchVentasPaginado(inicioMes, hoy, "fecha_emision, neto, total, canal"),
          fetchVentasPaginado(inicioMesAnt, finMesAnt, "neto, total"),
          rangoEsMesActual
            ? Promise.resolve(null)
            : fetchVentasPaginado(rango.desde, rango.hasta, "fecha_emision, neto, total, canal"),
          supabase.from("stock")
            .select("cantidad, productos!inner(relbase_id, sku, nombre, activo), bodegas(nombre)")
            .lte("cantidad", 20)
            .limit(200),
          supabase.from("ventas")
            .select("id, fecha_emision, folio, tipo_documento, neto, total, estado_sii, forma_pago")
            .order("fecha_emision", { ascending: false })
            .limit(20),
          fetchUltimaSync(),
        ]);

      if (stockResp.error)   throw stockResp.error;
      if (ultimasResp.error) throw ultimasResp.error;

      // KPIs siempre derivados del mes actual (estado operativo real del negocio)
      const ventasHoy    = ventasMes.filter((v) => v.fecha_emision === hoy);
      const ventasSemana = ventasMes.filter((v) => v.fecha_emision >= lunesSemana);

      const kpisData: KpisVentas = {
        hoy:    calcKpi(ventasHoy),
        semana: calcKpi(ventasSemana),
        mes:    calcKpi(ventasMes),
        mes_anterior: {
          ingresos_netos: ventasMesAnt.reduce((s, r) => s + (r.neto ?? 0), 0),
          num_ventas:     ventasMesAnt.length,
        },
      };

      // Desglose por canal (null canal en datos históricos → presencial)
      const esOnline = (v: any) => (v.canal ?? "presencial") !== "presencial";
      const desglosHoyData: DesglosCanal = {
        presencial: calcKpi(ventasHoy.filter((v) => !esOnline(v))),
        online:     calcKpi(ventasHoy.filter(esOnline)),
      };
      const desglossemanaData: DesglosCanal = {
        presencial: calcKpi(ventasSemana.filter((v) => !esOnline(v))),
        online:     calcKpi(ventasSemana.filter(esOnline)),
      };

      // Gráfico: usa el período seleccionado; agrupa por día y rellena días sin ventas con 0
      const datosPeriodo = ventasPeriodoExtra ?? ventasMes;
      const porDiaMap = new Map<string, { ingresos_netos: number; num_ventas: number }>();
      for (const v of datosPeriodo) {
        const fecha = v.fecha_emision as string;
        const e = porDiaMap.get(fecha) ?? { ingresos_netos: 0, num_ventas: 0 };
        e.ingresos_netos += (v.neto as number) ?? 0;
        e.num_ventas     += 1;
        porDiaMap.set(fecha, e);
      }
      const ventasPorDiaData = construirVentasPorDia(rango.desde, rango.hasta, porDiaMap);

      // Stock crítico
      const stockData: StockCritico[] = (stockResp.data ?? [])
        .filter((s: any) => s.productos?.activo === true)
        .map((s: any) => ({
          producto_id_relbase: s.productos.relbase_id,
          codigo:              s.productos.sku ?? String(s.productos.relbase_id),
          nombre:              s.productos.nombre ?? "Sin nombre",
          categoria_nombre:    null,
          stock_minimo:        1,
          bodega_nombre:       s.bodegas?.nombre ?? "Sin bodega",
          cantidad_disponible: s.cantidad,
          nivel_alerta:        NIVEL_ALERTA(s.cantidad),
        }))
        .sort((a: StockCritico, b: StockCritico) => {
          const ord = { sin_stock: 0, critico: 1, bajo: 2 };
          return ord[a.nivel_alerta] - ord[b.nivel_alerta];
        });

      const resumenData: ResumenStockCritico = {
        sin_stock: stockData.filter((s) => s.nivel_alerta === "sin_stock").length,
        critico:   stockData.filter((s) => s.nivel_alerta === "critico").length,
        bajo:      stockData.filter((s) => s.nivel_alerta === "bajo").length,
        total:     stockData.length,
      };

      // Últimas ventas
      const ultimasData: UltimaVenta[] = (ultimasResp.data ?? []).map((v: any) => ({
        id:            v.id,
        fecha_emision: v.fecha_emision,
        folio:         v.folio ?? null,
        tipo_nombre:   TIPO_NOMBRE[v.tipo_documento as number] ?? String(v.tipo_documento),
        forma_pago:    v.forma_pago ?? null,
        total_neto:    v.neto,
        total_bruto:   v.total,
        estado:        v.estado_sii ?? "",
      }));

      // Fase 2 — top productos del período seleccionado (paginado secuencial, más lento)
      const topData = await fetchTopProductos(rango.desde, rango.hasta);

      setKpis(kpisData);
      setDesglosHoy(desglosHoyData);
      setDesglossemana(desglossemanaData);
      setVentasPorDia(ventasPorDiaData);
      setTopProductos(topData);
      setStockCritico(stockData);
      setResumenStock(resumenData);
      setUltimasVentas(ultimasData);
      setUltimaSyncRelbase(ultimaSync);
      setUltimaActualizacion(new Date());
    } catch (err: unknown) {
      const mensaje =
        err instanceof Error
          ? err.message
          : (err as { message?: string })?.message ?? "Error cargando datos";
      setError(mensaje);
      console.error("[useDashboard]", err);
    } finally {
      setCargando(false);
    }
  }, [periodo]);

  useEffect(() => {
    cargarDatos();
    const intervalo = setInterval(cargarDatos, INTERVALO_REFRESH_MS);
    return () => clearInterval(intervalo);
  }, [cargarDatos]);

  return {
    kpis,
    desglosHoy,
    desglossemana,
    ventasPorDia,
    topProductos,
    stockCritico,
    resumenStock,
    ultimasVentas,
    ultimaSyncRelbase,
    cargando,
    error,
    ultimaActualizacion,
    refetch: cargarDatos,
  };
}
