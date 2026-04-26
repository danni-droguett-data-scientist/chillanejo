import { useEffect, useState, useCallback } from "react";
import { supabase } from "@/lib/supabase";

export interface ResumenCeo {
  honorarios_acumulado_anio: number;
  honorarios_mes_actual: number;
  costos_mes_actual: number;
  pipeline_total: number;
  clientes_activos: number;
}

export interface RentabilidadMes {
  mes: string;
  ingresos_total: number;
  costos_total: number;
  utilidad_neta: number;
  margen_pct: number | null;
}

export interface PipelineEtapa {
  etapa: string;
  cantidad: number;
  valor_pipeline: number;
  ticket_promedio: number;
}

export interface ClientePipeline {
  id: string;
  empresa: string;
  contacto: string | null;
  email: string | null;
  etapa: string;
  valor_estimado: number | null;
  notas: string | null;
  created_at: string;
}

export interface CeoData {
  resumen: ResumenCeo | null;
  rentabilidad: RentabilidadMes[];
  pipeline: PipelineEtapa[];
  clientes: ClientePipeline[];
  cargando: boolean;
  error: string | null;
  refetch: () => void;
}

export function useCeo(): CeoData {
  const [resumen, setResumen] = useState<ResumenCeo | null>(null);
  const [rentabilidad, setRentabilidad] = useState<RentabilidadMes[]>([]);
  const [pipeline, setPipeline] = useState<PipelineEtapa[]>([]);
  const [clientes, setClientes] = useState<ClientePipeline[]>([]);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const cargar = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      const [resResp, rentResp, pipeResp, clientResp] = await Promise.all([
        supabase.rpc("resumen_financiero_ceo"),
        supabase.from("vw_rentabilidad_ceo").select("*"),
        supabase.from("vw_pipeline_clientes").select("*"),
        supabase.from("pipeline_clientes").select("*").order("created_at", { ascending: false }),
      ]);

      if (resResp.error)    throw resResp.error;
      if (rentResp.error)   throw rentResp.error;
      if (pipeResp.error)   throw pipeResp.error;
      if (clientResp.error) throw clientResp.error;

      setResumen(resResp.data as ResumenCeo);
      setRentabilidad(rentResp.data as RentabilidadMes[]);
      setPipeline(pipeResp.data as PipelineEtapa[]);
      setClientes(clientResp.data as ClientePipeline[]);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Error cargando datos CEO");
    } finally {
      setCargando(false);
    }
  }, []);

  useEffect(() => { cargar(); }, [cargar]);

  return { resumen, rentabilidad, pipeline, clientes, cargando, error, refetch: cargar };
}
