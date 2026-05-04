import Link from "next/link";

// Página de cancelación post-pago Mercado Pago.
export default function PedidoCanceladoPage() {
  return (
    <div className="min-h-screen bg-white flex flex-col items-center justify-center px-4 text-center gap-6">
      <div className="text-6xl">✕</div>
      <div className="space-y-2">
        <h1 className="text-2xl font-bold text-gray-900">Pago cancelado</h1>
        <p className="text-gray-500 text-sm max-w-sm">
          El pago no fue procesado. Tu carrito sigue guardado — puedes intentarlo de nuevo.
        </p>
      </div>
      <div className="flex gap-3">
        <Link
          href="/checkout"
          className="rounded-lg bg-[#2563EB] px-6 py-2.5 text-sm font-medium text-white hover:bg-blue-700 transition-colors"
        >
          Reintentar pago
        </Link>
        <Link
          href="/catalogo"
          className="rounded-lg border px-6 py-2.5 text-sm font-medium text-gray-600 hover:bg-gray-50 transition-colors"
        >
          Ver catálogo
        </Link>
      </div>
    </div>
  );
}
