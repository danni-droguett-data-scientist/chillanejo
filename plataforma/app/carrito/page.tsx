"use client";

import Link from "next/link";
import { Trash2, Plus, Minus, ArrowLeft, ShoppingBag } from "lucide-react";
import { useCarrito } from "@/hooks/useCarrito";
import { clp } from "@/lib/formato";

export default function CarritoPage() {
  const { items, totales, cambiarCantidad, quitar, vaciar } = useCarrito();

  if (!items.length) {
    return (
      <div className="min-h-screen bg-gray-50 flex flex-col items-center justify-center gap-4">
        <ShoppingBag className="h-16 w-16 text-gray-200" />
        <p className="text-lg font-semibold text-gray-600">Tu carrito está vacío</p>
        <Link
          href="/catalogo"
          className="flex items-center gap-2 rounded-lg bg-[#2563EB] px-5 py-2.5 text-sm font-medium text-white hover:bg-blue-700 transition-colors"
        >
          <ArrowLeft className="h-4 w-4" />
          Ver catálogo
        </Link>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="border-b bg-white px-4 py-4">
        <div className="max-w-4xl mx-auto flex items-center gap-3">
          <Link href="/catalogo" className="text-gray-400 hover:text-gray-600 transition-colors">
            <ArrowLeft className="h-5 w-5" />
          </Link>
          <h1 className="text-lg font-semibold text-[#1F2937]">
            Carrito · {totales.num_items} {totales.num_items === 1 ? "producto" : "productos"}
          </h1>
        </div>
      </header>

      <div className="max-w-4xl mx-auto px-4 py-6 grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-3">
          {items.map((item) => (
            <div
              key={item.relbase_id}
              className="flex gap-4 rounded-xl border bg-white p-4 shadow-sm"
            >
              <div className="w-16 h-16 rounded-lg bg-gray-100 shrink-0" />

              <div className="flex-1 min-w-0">
                <p className="font-medium text-[#1F2937] truncate">{item.nombre}</p>
                <p className="text-xs text-gray-400 mt-0.5">{item.sku}</p>
                <p className="text-sm font-semibold text-[#1F2937] mt-1">
                  {clp(item.precio_bruto)}
                  <span className="text-xs text-gray-400 font-normal ml-1">c/u</span>
                </p>
              </div>

              <div className="flex flex-col items-end justify-between gap-2">
                <button
                  onClick={() => quitar(item.relbase_id)}
                  className="text-gray-300 hover:text-red-400 transition-colors"
                >
                  <Trash2 className="h-4 w-4" />
                </button>

                <div className="flex items-center gap-2">
                  <button
                    onClick={() => cambiarCantidad(item.relbase_id, item.cantidad - 1)}
                    className="rounded-md border p-1 hover:bg-gray-50 transition-colors"
                  >
                    <Minus className="h-3.5 w-3.5 text-gray-600" />
                  </button>
                  <span className="w-8 text-center text-sm font-medium tabular-nums">
                    {item.cantidad}
                  </span>
                  <button
                    onClick={() => cambiarCantidad(item.relbase_id, item.cantidad + 1)}
                    className="rounded-md border p-1 hover:bg-gray-50 transition-colors"
                  >
                    <Plus className="h-3.5 w-3.5 text-gray-600" />
                  </button>
                </div>

                <p className="text-sm font-bold text-[#1F2937] tabular-nums">
                  {clp(item.precio_bruto * item.cantidad)}
                </p>
              </div>
            </div>
          ))}

          <button
            onClick={vaciar}
            className="text-xs text-gray-400 hover:text-red-500 transition-colors"
          >
            Vaciar carrito
          </button>
        </div>

        <div className="rounded-xl border bg-white p-5 shadow-sm h-fit space-y-4">
          <h2 className="font-semibold text-[#1F2937]">Resumen del pedido</h2>

          <div className="space-y-2 text-sm">
            <div className="flex justify-between text-gray-600">
              <span>Subtotal neto</span>
              <span className="tabular-nums">{clp(totales.subtotal_neto)}</span>
            </div>
            <div className="flex justify-between text-gray-600">
              <span>IVA (19%)</span>
              <span className="tabular-nums">{clp(totales.iva)}</span>
            </div>
            <div className="border-t pt-2 flex justify-between font-bold text-[#1F2937]">
              <span>Total</span>
              <span className="tabular-nums">{clp(totales.subtotal_bruto)}</span>
            </div>
          </div>

          <Link
            href="/checkout"
            className="block w-full text-center rounded-lg bg-[#2563EB] px-4 py-3 text-sm font-semibold text-white hover:bg-blue-700 transition-colors"
          >
            Ir al pago →
          </Link>

          <Link
            href="/catalogo"
            className="block text-center text-sm text-gray-400 hover:text-gray-600 transition-colors"
          >
            Continuar comprando
          </Link>
        </div>
      </div>
    </div>
  );
}
