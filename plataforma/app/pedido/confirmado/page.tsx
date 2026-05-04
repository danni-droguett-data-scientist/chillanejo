import Link from "next/link";

// Página de éxito post-pago Mercado Pago. Se completa con la integración MP en Fase 2.
export default function PedidoConfirmadoPage() {
  return (
    <div className="min-h-screen bg-white flex flex-col items-center justify-center px-4 text-center gap-6">
      <div className="text-6xl">✓</div>
      <div className="space-y-2">
        <h1 className="text-2xl font-bold text-gray-900">¡Pago aprobado!</h1>
        <p className="text-gray-500 text-sm max-w-sm">
          Recibirás un correo con tu código de retiro. Recuerda retirar dentro de 3 días hábiles.
        </p>
      </div>
      <Link
        href="/"
        className="rounded-lg bg-[#2563EB] px-6 py-2.5 text-sm font-medium text-white hover:bg-blue-700 transition-colors"
      >
        Volver al inicio
      </Link>
    </div>
  );
}
