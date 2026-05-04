// Flujo de devolución. Implementación completa en Fase 2.
export default function DevolucionPage({ params }: { params: { id: string } }) {
  return (
    <main className="min-h-screen bg-gray-50 p-6">
      <h1 className="text-lg font-semibold text-gray-900 mb-2">Devolución #{params.id}</h1>
      <p className="text-sm text-gray-500">Disponible en Fase 2.</p>
    </main>
  );
}
