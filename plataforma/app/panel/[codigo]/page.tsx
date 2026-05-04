// Detalle de pedido por código de retiro. Implementación completa en Fase 2.
export default function DetallePedidoPage({ params }: { params: { codigo: string } }) {
  return (
    <main className="min-h-screen bg-gray-50 p-6">
      <h1 className="text-lg font-semibold text-gray-900 mb-2">Pedido #{params.codigo}</h1>
      <p className="text-sm text-gray-500">Detalle disponible en Fase 2.</p>
    </main>
  );
}
