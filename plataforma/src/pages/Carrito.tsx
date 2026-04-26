import { Trash2, Plus, Minus, ArrowLeft, ShoppingBag } from "lucide-react";
import { useCarrito } from "@/hooks/useCarrito";

const CLP = new Intl.NumberFormat("es-CL", { style: "currency", currency: "CLP", maximumFractionDigits: 0 });

export default function Carrito() {
  const { items, totales, cambiarCantidad, quitar, vaciar } = useCarrito();

  if (!items.length) {
    return (
      <div className="min-h-screen bg-gray-50 flex flex-col items-center justify-center gap-4">
        <ShoppingBag className="h-16 w-16 text-gray-200" />
        <p className="text-lg font-semibold text-gray-600">Tu carrito está vacío</p>
        <a
          href="/"
          className="flex items-center gap-2 rounded-lg bg-blue-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-blue-700 transition-colors"
        >
          <ArrowLeft className="h-4 w-4" />
          Ver catálogo
        </a>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="border-b bg-white px-4 py-4">
        <div className="max-w-4xl mx-auto flex items-center gap-3">
          <a href="/" className="text-gray-400 hover:text-gray-600 transition-colors">
            <ArrowLeft className="h-5 w-5" />
          </a>
          <h1 className="text-lg font-semibold text-gray-900">
            Carrito · {totales.num_items} {totales.num_items === 1 ? "producto" : "productos"}
          </h1>
        </div>
      </header>

      <div className="max-w-4xl mx-auto px-4 py-6 grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Items */}
        <div className="lg:col-span-2 space-y-3">
          {items.map((item) => (
            <div
              key={item.producto_id_relbase}
              className="flex gap-4 rounded-xl border bg-white p-4 shadow-sm"
            >
              <div className="w-16 h-16 rounded-lg bg-gray-50 flex items-center justify-center text-2xl shrink-0">
                📦
              </div>

              <div className="flex-1 min-w-0">
                <p className="font-medium text-gray-800 truncate">{item.nombre}</p>
                <p className="text-xs text-gray-400 mt-0.5">{item.codigo}</p>
                <p className="text-sm font-semibold text-gray-900 mt-1">
                  {CLP.format(item.precio_bruto)}
                  <span className="text-xs text-gray-400 font-normal ml-1">c/u</span>
                </p>
              </div>

              <div className="flex flex-col items-end justify-between gap-2">
                <button
                  onClick={() => quitar(item.producto_id_relbase)}
                  className="text-gray-300 hover:text-red-400 transition-colors"
                >
                  <Trash2 className="h-4 w-4" />
                </button>

                <div className="flex items-center gap-2">
                  <button
                    onClick={() => cambiarCantidad(item.producto_id_relbase, item.cantidad - 1)}
                    className="rounded-md border p-1 hover:bg-gray-50 transition-colors"
                  >
                    <Minus className="h-3.5 w-3.5 text-gray-600" />
                  </button>
                  <span className="w-8 text-center text-sm font-medium tabular-nums">
                    {item.cantidad}
                  </span>
                  <button
                    onClick={() => cambiarCantidad(item.producto_id_relbase, item.cantidad + 1)}
                    className="rounded-md border p-1 hover:bg-gray-50 transition-colors"
                  >
                    <Plus className="h-3.5 w-3.5 text-gray-600" />
                  </button>
                </div>

                <p className="text-sm font-bold text-gray-900 tabular-nums">
                  {CLP.format(item.precio_bruto * item.cantidad)}
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

        {/* Resumen */}
        <div className="rounded-xl border bg-white p-5 shadow-sm h-fit space-y-4">
          <h2 className="font-semibold text-gray-800">Resumen del pedido</h2>

          <div className="space-y-2 text-sm">
            <div className="flex justify-between text-gray-600">
              <span>Subtotal neto</span>
              <span className="tabular-nums">{CLP.format(totales.subtotal_neto)}</span>
            </div>
            <div className="flex justify-between text-gray-600">
              <span>IVA (19%)</span>
              <span className="tabular-nums">{CLP.format(totales.iva)}</span>
            </div>
            <div className="border-t pt-2 flex justify-between font-bold text-gray-900">
              <span>Total</span>
              <span className="tabular-nums">{CLP.format(totales.subtotal_bruto)}</span>
            </div>
          </div>

          <a
            href="/checkout"
            className="block w-full text-center rounded-lg bg-blue-600 px-4 py-3 text-sm font-semibold text-white hover:bg-blue-700 transition-colors"
          >
            Ir al pago →
          </a>

          <a
            href="/"
            className="block text-center text-sm text-gray-400 hover:text-gray-600 transition-colors"
          >
            Continuar comprando
          </a>
        </div>
      </div>
    </div>
  );
}
