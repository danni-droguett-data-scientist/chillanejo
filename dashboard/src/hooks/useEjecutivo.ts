import { useEffect, useState, useCallback } from "react";
import { supabase } from "@/lib/supabase";

export interface MesVenta {
  mes: string;
  num_ventas: number;
  ingresos_netos: number;
  ingresos_brutos: number;
  ticket_promedio: number;
  clientes_unicos: number;
}

export interface MargenCategoria {
  categoria: string;
  mes: string;
  ingresos_netos: number;
  margen_neto_total: number | null;
  margen_pct: number | null;
  unidades_vendidas: number;
}

export interface EvolucionClientes {
  mes: string;
  clientes_identificados: number;
  ventas_anonimas: number;
  clientes_nuevos: number;
}

export interface ProductoHistorico {
  codigo_producto: string;
  nombre_producto: string;
  categoria: string;
  unidades_totales: number;
  ingresos_netos_total: number;
  margen_neto_total: number | null;
  margen_pct: number | null;
  num_transacciones: number;
}

export interface MargenResumen {
  mes_actual: { ingresos_netos: number; margen_neto: number; margen_pct: number | null };
  mes_anterior: { ingresos_netos: number; margen_neto: number; margen_pct: number | null };
}

export interface EjecutivoData {
  tendencia: MesVenta[];
  margenCategorias: MargenCategoria[];
  evolucionClientes: EvolucionClientes[];
  topProductos: ProductoHistorico[];
  margenResumen: MargenResumen | null;
  cargando: boolean;
  error: string | null;
  refetch: () => void;
}

export function useEjecutivo(): EjecutivoData {
  const [tendencia, setTendencia] = useState<MesVenta[]>([]);
  const [margenCategorias, setMargenCategorias] = useState<MargenCategoria[]>([]);
  const [evolucionClientes, setEvolucionClientes] = useState<EvolucionClientes[]>([]);
  const [topProductos, setTopProductos] = useState<ProductoHistorico[]>([]);
  const [margenResumen, setMargenResumen] = useState<MargenResumen | null>(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const cargar = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      const [tendResp, catResp, clientResp, topResp, margenResp] = await Promise.all([
        supabase.rpc("tendencia_12_meses"),
        supabase.from("vw_margen_por_categoria").select("*"),
        supabase.from("vw_evolucion_clientes").select("*"),
        supabase.from("vw_top_productos_historico").select("*").limit(20),
        supabase.rpc("margen_resumen_mes"),
      ]);

      if (tendResp.error)   throw tendResp.error;
      if (catResp.error)    throw catResp.error;
      if (clientResp.error) throw clientResp.error;
      if (topResp.error)    throw topResp.error;
      if (margenResp.error) throw margenResp.error;

      setTendencia(tendResp.data as MesVenta[]);
      setMargenCategorias(catResp.data as MargenCategoria[]);
      setEvolucionClientes(clientResp.data as EvolucionClientes[]);
      setTopProductos(topResp.data as ProductoHistorico[]);
      setMargenResumen(margenResp.data as MargenResumen);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Error cargando datos ejecutivos");
    } finally {
      setCargando(false);
    }
  }, []);

  useEffect(() => { cargar(); }, [cargar]);

  return { tendencia, margenCategorias, evolucionClientes, topProductos, margenResumen, cargando, error, refetch: cargar };
}
