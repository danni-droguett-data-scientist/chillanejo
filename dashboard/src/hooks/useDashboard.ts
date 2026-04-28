import { useEffect, useState, useCallback } from "react";
import { supabase } from "@/lib/supabase";

// ---------------------------------------------------------------------------
// Tipos
// ---------------------------------------------------------------------------

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

function inicioSemana(d: Date): string {
  const lunes = new Date(d);
  lunes.setDate(d.getDate() - ((d.getDay() + 6) % 7));
  return fechaLocal(lunes);
}

function calcKpi(rows: { neto: number; total: number }[]): KpiPeriodo {
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

// Trae todas las ventas de un rango paginando de a 1000 para superar el cap de PostgREST
async function fetchVentasPaginado(
  desde: string,
  hasta: string,
  campos: string
): Promise<any[]> {
  const PAGE = 1000;
  const all: any[] = [];
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

// Top productos: pagina ventas_detalle con join a ventas filtrado por mes.
// Incluye canal para desgloses y filtros en la UI.
async function fetchTopProductos(inicioMes: string, hoy: string): Promise<TopProducto[]> {
  const PAGE = 1000;
  const MAX_PAGES = 10;
  const rows: any[] = [];

  for (let page = 0; page < MAX_PAGES; page++) {
    const { data, error } = await supabase
      .from("ventas_detalle")
      .select(
        "relbase_producto_id, sku, nombre_producto, cantidad, total_neto, costo_unitario, venta_id, ventas!inner(fecha_emision, canal)"
      )
      .gte("ventas.fecha_emision", inicioMes)
      .lte("ventas.fecha_emision", hoy)
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
    const canal = (r.ventas as any)?.canal ?? "presencial";
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
      codigo_producto:    p.codigo_producto,
      nombre_producto:    p.nombre_producto,
      unidades_vendidas:  p.unidades,
      ingresos_netos:     p.ingresos,
      ingresos_presencial: p.ingresos_presencial,
      ingresos_online:    p.ingresos_online,
      margen_neto_total:  p.tieneMargen ? p.margen : null,
      margen_pct: p.tieneMargen && p.ingresos > 0
        ? Math.round((p.margen / p.ingresos) * 1000) / 10
        : null,
      num_transacciones: p.ventaIds.size,
      rank_ingresos: i + 1,
    }));
}

// ---------------------------------------------------------------------------
// Hook principal
// ---------------------------------------------------------------------------

export function useDashboard(): DashboardData {
  const [kpis,                setKpis]                = useState<KpisVentas | null>(null);
  const [desglosHoy,          setDesglosHoy]          = useState<DesglosCanal | null>(null);
  const [desglossemana,       setDesglossemana]       = useState<DesglosCanal | null>(null);
  const [ventasPorDia,        setVentasPorDia]        = useState<VentaDia[]>([]);
  const [topProductos,        setTopProductos]        = useState<TopProducto[]>([]);
  const [stockCritico,        setStockCritico]        = useState<StockCritico[]>([]);
  const [resumenStock,        setResumenStock]        = useState<ResumenStockCritico | null>(null);
  const [ultimasVentas,       setUltimasVentas]       = useState<UltimaVenta[]>([]);
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

      // Fase 1 — cuatro fetches en paralelo:
      //   · ventas del mes completo (paginado, incluye canal) → KPIs + gráfico + desglose
      //   · ventas mes anterior (paginado)                   → KPI mes_anterior
      //   · stock con embedding                              → alertas
      //   · últimas ventas con embedding                     → tabla
      const [ventasMes, ventasMesAnt, stockResp, ultimasResp] = await Promise.all([
        fetchVentasPaginado(inicioMes, hoy, "fecha_emision, neto, total, canal"),
        fetchVentasPaginado(inicioMesAnt, finMesAnt, "neto, total"),
        supabase.from("stock")
          .select("cantidad, productos!inner(relbase_id, sku, nombre, activo), bodegas(nombre)")
          .lte("cantidad", 20)
          .limit(200),
        supabase.from("ventas")
          .select("id, fecha_emision, folio, tipo_documento, neto, total, estado_sii, forma_pago")
          .order("fecha_emision", { ascending: false })
          .limit(20),
      ]);

      if (stockResp.error)   throw stockResp.error;
      if (ultimasResp.error) throw ultimasResp.error;

      // KPIs derivados del dataset del mes
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

      // Gráfico: agrupa por día y rellena días sin ventas con 0
      const porDiaMap = new Map<string, { ingresos_netos: number; num_ventas: number }>();
      for (const v of ventasMes) {
        const fecha = v.fecha_emision as string;
        const e = porDiaMap.get(fecha) ?? { ingresos_netos: 0, num_ventas: 0 };
        e.ingresos_netos += (v.neto as number) ?? 0;
        e.num_ventas     += 1;
        porDiaMap.set(fecha, e);
      }
      const ventasPorDiaData: VentaDia[] = [];
      const cursor = new Date(ahora.getFullYear(), ahora.getMonth(), 1);
      const fin    = new Date(ahora.getFullYear(), ahora.getMonth(), ahora.getDate());
      while (cursor <= fin) {
        const fecha = fechaLocal(cursor);
        ventasPorDiaData.push({ fecha, ...( porDiaMap.get(fecha) ?? { ingresos_netos: 0, num_ventas: 0 }) });
        cursor.setDate(cursor.getDate() + 1);
      }

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

      // Fase 2 — top productos (paginado secuencial, más lento)
      const topData = await fetchTopProductos(inicioMes, hoy);

      setKpis(kpisData);
      setDesglosHoy(desglosHoyData);
      setDesglossemana(desglossemanaData);
      setVentasPorDia(ventasPorDiaData);
      setTopProductos(topData);
      setStockCritico(stockData);
      setResumenStock(resumenData);
      setUltimasVentas(ultimasData);
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
  }, []);

  useEffect(() => {
    cargarDatos();
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
    cargando,
    error,
    ultimaActualizacion,
    refetch: cargarDatos,
  };
}
