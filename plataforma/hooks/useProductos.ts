import { useState, useEffect, useCallback } from "react";
import { supabase } from "@/lib/supabase";

export interface Producto {
  id: string;
  relbase_id: number;
  sku: string;
  nombre: string;
  descripcion: string | null;
  categoria_id: number | null;
  precio_neto: number;
  afecto_iva: boolean;
  activo: boolean;
  precio_bruto: number;
}

interface ProductoRaw {
  id: string;
  relbase_id: number;
  sku: string;
  nombre: string;
  descripcion: string | null;
  categoria_id: number | null;
  precio_neto: number;
  afecto_iva: boolean;
  activo: boolean;
}

interface FiltrosProductos {
  busqueda?:    string;
  soloConStock?: boolean;
  pagina?:      number;
  porPagina?:   number;
}

const POR_PAGINA = 24;

function conPrecioBruto(p: ProductoRaw): Producto {
  return {
    ...p,
    precio_bruto: Math.round(p.afecto_iva ? p.precio_neto * 1.19 : p.precio_neto),
  };
}

export function useProductos(filtros: FiltrosProductos = {}) {
  const [productos, setProductos] = useState<Producto[]>([]);
  const [total,     setTotal]     = useState(0);
  const [cargando,  setCargando]  = useState(true);
  const [error,     setError]     = useState<string | null>(null);

  const { busqueda, soloConStock, pagina = 1, porPagina = POR_PAGINA } = filtros;

  const cargar = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      let query = supabase
        .from("productos")
        .select(
          "id, relbase_id, sku, nombre, descripcion, categoria_id, precio_neto, activo, afecto_iva",
          { count: "exact" }
        )
        .eq("activo", true)
        .order("nombre");

      if (busqueda) query = query.ilike("nombre", `%${busqueda}%`);

      if (soloConStock) {
        const { data: conStock } = await supabase
          .from("stock")
          .select("producto_id")
          .gt("cantidad", 0);
        const ids = (conStock ?? []).map((s: { producto_id: number }) => s.producto_id);
        if (ids.length) query = query.in("relbase_id", ids);
      }

      const desde = (pagina - 1) * porPagina;
      query = query.range(desde, desde + porPagina - 1);

      const { data, count, error: err } = await query;
      console.log("Supabase response:", { data: data?.length, count, error: err });
      if (err) throw err;

      setProductos(((data ?? []) as ProductoRaw[]).map(conPrecioBruto));
      setTotal(count ?? 0);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Error cargando productos");
    } finally {
      setCargando(false);
    }
  }, [busqueda, soloConStock, pagina, porPagina]);

  useEffect(() => { cargar(); }, [cargar]);

  return { productos, total, cargando, error, totalPaginas: Math.ceil(total / porPagina) };
}

export function useCategorias() {
  return [] as string[];
}
