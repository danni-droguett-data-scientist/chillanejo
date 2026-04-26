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
  cliente: string;
  es_anonimo: boolean;
  total_neto: number;
  total_bruto: number;
  estado: string;
}

export interface DashboardData {
  kpis: KpisVentas | null;
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
// Hook principal
// ---------------------------------------------------------------------------

export function useDashboard(): DashboardData {
  const [kpis, setKpis] = useState<KpisVentas | null>(null);
  const [ventasPorDia, setVentasPorDia] = useState<VentaDia[]>([]);
  const [topProductos, setTopProductos] = useState<TopProducto[]>([]);
  const [stockCritico, setStockCritico] = useState<StockCritico[]>([]);
  const [resumenStock, setResumenStock] = useState<ResumenStockCritico | null>(null);
  const [ultimasVentas, setUltimasVentas] = useState<UltimaVenta[]>([]);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [ultimaActualizacion, setUltimaActualizacion] = useState<Date | null>(null);

  const cargarDatos = useCallback(async () => {
    setCargando(true);
    setError(null);

    try {
      // Fecha para el gráfico: últimos 30 días
      const hace30dias = new Date();
      hace30dias.setDate(hace30dias.getDate() - 30);
      const desde = hace30dias.toISOString().slice(0, 10);
      const hasta = new Date().toISOString().slice(0, 10);

      const [
        kpisResp,
        diasResp,
        topResp,
        stockResp,
        resumenStockResp,
        ultimasResp,
      ] = await Promise.all([
        supabase.rpc("kpis_ventas"),
        supabase.rpc("ventas_por_dia", { p_desde: desde, p_hasta: hasta }),
        supabase.from("vw_top_productos_mes").select("*").limit(10),
        supabase.from("vw_stock_critico").select("*").limit(50),
        supabase.rpc("resumen_stock_critico"),
        supabase.from("vw_ultimas_ventas").select("*").limit(20),
      ]);

      if (kpisResp.error) throw kpisResp.error;
      if (diasResp.error) throw diasResp.error;
      if (topResp.error) throw topResp.error;
      if (stockResp.error) throw stockResp.error;
      if (resumenStockResp.error) throw resumenStockResp.error;
      if (ultimasResp.error) throw ultimasResp.error;

      setKpis(kpisResp.data as KpisVentas);
      setVentasPorDia(diasResp.data as VentaDia[]);
      setTopProductos(topResp.data as TopProducto[]);
      setStockCritico(stockResp.data as StockCritico[]);
      setResumenStock(resumenStockResp.data as ResumenStockCritico);
      setUltimasVentas(ultimasResp.data as UltimaVenta[]);
      setUltimaActualizacion(new Date());
    } catch (err: unknown) {
      const mensaje = err instanceof Error ? err.message : "Error cargando datos";
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
