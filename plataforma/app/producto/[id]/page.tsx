// Detalle de producto. Implementación completa en Fase 2.
export default function ProductoPage({ params }: { params: { id: string } }) {
  return (
    <main className="min-h-screen bg-gray-50 p-6">
      <h1 className="text-lg font-semibold text-gray-900">Producto {params.id}</h1>
      <p className="text-sm text-gray-500 mt-2">Detalle disponible en Fase 2.</p>
    </main>
  );
}
