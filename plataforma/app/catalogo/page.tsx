"use client";

import { useState } from "react";
import Link from "next/link";
import { Search, Plus, ShoppingCart } from "lucide-react";
import { useProductos } from "@/hooks/useProductos";
import { useCarrito } from "@/hooks/useCarrito";
import { clp } from "@/lib/formato";
import type { Producto } from "@/hooks/useProductos";

function TarjetaProducto({ producto }: { producto: Producto }) {
  const { agregar, items } = useCarrito();
  const enCarrito = items.find((i) => i.relbase_id === producto.relbase_id);

  return (
    <div className="rounded-xl border bg-white p-4 shadow-sm hover:shadow-md transition-shadow flex flex-col gap-3">
      <div className="aspect-square rounded-lg bg-gray-100" />

      <div className="flex-1">
        <h3 className="text-sm font-semibold text-[#1F2937] leading-snug line-clamp-2">
          {producto.nombre}
        </h3>
        <p className="text-xs text-gray-400 mt-0.5">{producto.sku}</p>
      </div>

      <div className="flex items-end justify-between gap-2">
        <div>
          <p className="text-base font-bold text-[#1F2937]">{clp(producto.precio_bruto)}</p>
          <p className="text-xs text-gray-400">Neto {clp(producto.precio_neto)}</p>
        </div>
        <button
          onClick={() =>
            agregar({
              relbase_id:   producto.relbase_id,
              sku:          producto.sku,
              nombre:       producto.nombre,
              precio_neto:  producto.precio_neto,
              precio_bruto: producto.precio_bruto,
            })
          }
          className={`flex items-center gap-1 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
            enCarrito
              ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
              : "bg-[#2563EB] text-white hover:bg-blue-700"
          }`}
        >
          {enCarrito ? (
            <>{enCarrito.cantidad} en carrito</>
          ) : (
            <><Plus className="h-3.5 w-3.5" />Agregar</>
          )}
        </button>
      </div>
    </div>
  );
}

export default function CatalogoPage() {
  const [busqueda,       setBusqueda]       = useState("");
  const [busquedaActiva, setBusquedaActiva] = useState("");
  const [pagina,         setPagina]         = useState(1);
  const [soloConStock,   setSoloConStock]   = useState(false);

  const { productos, total, cargando, totalPaginas } = useProductos({
    busqueda: busquedaActiva,
    soloConStock,
    pagina,
  });
  const { totales } = useCarrito();

  const buscar = () => { setBusquedaActiva(busqueda); setPagina(1); };

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="sticky top-0 z-20 border-b bg-white px-4 py-3 shadow-sm">
        <div className="max-w-6xl mx-auto flex items-center justify-between gap-4">
          <Link href="/" className="text-lg font-bold text-[#1F2937] shrink-0">
            El Chillanejo
          </Link>

          <div className="flex-1 max-w-lg flex gap-2">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
              <input
                type="text"
                placeholder="Buscar productos..."
                value={busqueda}
                onChange={(e) => setBusqueda(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && buscar()}
                className="w-full rounded-lg border border-gray-200 pl-9 pr-3 py-2 text-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-400/20"
              />
            </div>
            <button
              onClick={buscar}
              className="rounded-lg bg-[#2563EB] px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 transition-colors"
            >
              Buscar
            </button>
          </div>

          <Link
            href="/carrito"
            className="relative flex items-center gap-1.5 rounded-lg border px-3 py-2 text-sm text-[#1F2937] hover:bg-gray-50 transition-colors"
          >
            <ShoppingCart className="h-4 w-4" />
            <span className="hidden sm:inline">Carrito</span>
            {totales.num_items > 0 && (
              <span className="absolute -top-1.5 -right-1.5 flex h-5 w-5 items-center justify-center rounded-full bg-[#2563EB] text-xs font-bold text-white">
                {totales.num_items}
              </span>
            )}
          </Link>
        </div>
      </header>

      <div className="max-w-6xl mx-auto px-4 py-6">
        <div className="flex items-center justify-between mb-4">
          <p className="text-sm text-gray-500">
            {cargando ? "Cargando…" : `${total} productos`}
          </p>
          <label className="flex items-center gap-2 text-sm text-gray-600 cursor-pointer">
            <input
              type="checkbox"
              checked={soloConStock}
              onChange={(e) => { setSoloConStock(e.target.checked); setPagina(1); }}
              className="rounded border-gray-300 text-[#2563EB] focus:ring-blue-500"
            />
            Solo con stock
          </label>
        </div>

        {cargando ? (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
            {Array.from({ length: 12 }).map((_, i) => (
              <div key={i} className="rounded-xl border bg-white p-4 space-y-3 animate-pulse">
                <div className="aspect-square rounded-lg bg-gray-100" />
                <div className="h-4 bg-gray-100 rounded w-3/4" />
                <div className="h-4 bg-gray-100 rounded w-1/2" />
              </div>
            ))}
          </div>
        ) : productos.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-center gap-3">
            <Search className="h-10 w-10 text-gray-200" />
            <p className="text-gray-500 font-medium">Sin productos para esta búsqueda</p>
            <button
              onClick={() => { setBusqueda(""); setBusquedaActiva(""); setSoloConStock(false); setPagina(1); }}
              className="text-sm text-[#2563EB] hover:underline"
            >
              Limpiar filtros
            </button>
          </div>
        ) : (
          <>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
              {productos.map((p) => <TarjetaProducto key={p.id} producto={p} />)}
            </div>

            {totalPaginas > 1 && (
              <div className="flex justify-center gap-2 mt-8">
                <button
                  onClick={() => setPagina((p) => Math.max(1, p - 1))}
                  disabled={pagina === 1}
                  className="rounded-lg border px-3 py-1.5 text-sm disabled:opacity-40 hover:bg-gray-50"
                >
                  ← Anterior
                </button>
                <span className="text-sm text-gray-500 flex items-center px-3">
                  {pagina} / {totalPaginas}
                </span>
                <button
                  onClick={() => setPagina((p) => Math.min(totalPaginas, p + 1))}
                  disabled={pagina === totalPaginas}
                  className="rounded-lg border px-3 py-1.5 text-sm disabled:opacity-40 hover:bg-gray-50"
                >
                  Siguiente →
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
