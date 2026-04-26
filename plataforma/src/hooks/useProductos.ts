import { useState, useEffect, useCallback } from "react";
import { supabase } from "@/lib/supabase";

export interface Producto {
  id: string;
  producto_id_relbase: number;
  codigo: string;
  nombre: string;
  descripcion: string | null;
  precio_neto: number;
  precio_bruto: number;
  categoria_nombre: string | null;
  unidad_medida: string | null;
  es_activo: boolean;
  imagen_url?: string;
}

interface FiltrosProductos {
  busqueda?: string;
  categoria?: string;
  soloConStock?: boolean;
  pagina?: number;
  porPagina?: number;
}

const POR_PAGINA = 24;

export function useProductos(filtros: FiltrosProductos = {}) {
  const [productos, setProductos] = useState<Producto[]>([]);
  const [total, setTotal] = useState(0);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const { busqueda, categoria, soloConStock, pagina = 1, porPagina = POR_PAGINA } = filtros;

  const cargar = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      let query = supabase
        .from("productos")
        .select("*", { count: "exact" })
        .eq("es_activo", true)
        .order("nombre");

      if (busqueda) {
        query = query.ilike("nombre", `%${busqueda}%`);
      }
      if (categoria) {
        query = query.eq("categoria_nombre", categoria);
      }
      if (soloConStock) {
        // Filtra productos que tienen stock > 0 en al menos una bodega
        const { data: conStock } = await supabase
          .from("stock")
          .select("producto_id_relbase")
          .gt("cantidad_disponible", 0);
        const ids = (conStock ?? []).map((s: any) => s.producto_id_relbase);
        if (ids.length) query = query.in("producto_id_relbase", ids);
      }

      const desde = (pagina - 1) * porPagina;
      query = query.range(desde, desde + porPagina - 1);

      const { data, count, error: err } = await query;
      if (err) throw err;

      setProductos(data as Producto[]);
      setTotal(count ?? 0);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Error cargando productos");
    } finally {
      setCargando(false);
    }
  }, [busqueda, categoria, soloConStock, pagina, porPagina]);

  useEffect(() => { cargar(); }, [cargar]);

  return { productos, total, cargando, error, totalPaginas: Math.ceil(total / porPagina) };
}

export function useCategorias() {
  const [categorias, setCategorias] = useState<string[]>([]);

  useEffect(() => {
    supabase
      .from("productos")
      .select("categoria_nombre")
      .eq("es_activo", true)
      .not("categoria_nombre", "is", null)
      .then(({ data }) => {
        const unicas = [...new Set((data ?? []).map((d: any) => d.categoria_nombre))].sort();
        setCategorias(unicas as string[]);
      });
  }, []);

  return categorias;
}
