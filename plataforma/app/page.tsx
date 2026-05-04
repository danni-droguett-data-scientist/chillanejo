import Link from "next/link";
import { ShoppingCart, MapPin, Clock, Phone } from "lucide-react";

export default function Home() {
  return (
    <div className="min-h-screen bg-white flex flex-col">
      <header className="border-b px-6 py-4">
        <div className="max-w-5xl mx-auto flex items-center justify-between">
          <span className="text-lg font-bold text-gray-900">El Chillanejo</span>
          <Link
            href="/catalogo"
            className="flex items-center gap-2 text-sm text-gray-600 hover:text-gray-900 transition-colors"
          >
            <ShoppingCart className="h-4 w-4" />
            Tienda
          </Link>
        </div>
      </header>

      <main className="flex-1 flex flex-col items-center justify-center px-6 py-20 text-center">
        <div className="max-w-2xl mx-auto space-y-8">
          <div className="space-y-4">
            <h1 className="text-4xl sm:text-5xl font-bold text-gray-900 leading-tight">
              El Chillanejo
            </h1>
            <p className="text-xl text-gray-500 leading-relaxed">
              Distribuidora de aseo y abarrotes en Chillán.
              <br />
              Compra online — retira en local.
            </p>
          </div>

          <Link
            href="/catalogo"
            className="inline-flex items-center gap-2 rounded-xl bg-[#2563EB] px-8 py-4 text-base font-semibold text-white hover:bg-blue-700 transition-colors shadow-sm"
          >
            <ShoppingCart className="h-5 w-5" />
            Ver productos
          </Link>

          <div className="flex flex-col sm:flex-row items-center justify-center gap-6 text-sm text-gray-500 pt-4">
            <span className="flex items-center gap-2">
              <MapPin className="h-4 w-4 text-[#2563EB] shrink-0" />
              Chillán, Región de Ñuble
            </span>
            <span className="flex items-center gap-2">
              <Clock className="h-4 w-4 text-[#2563EB] shrink-0" />
              Lun–Vie 8:30–18:00 · Sáb 9:00–14:00
            </span>
            <span className="flex items-center gap-2">
              <Phone className="h-4 w-4 text-[#2563EB] shrink-0" />
              Retiro en local
            </span>
          </div>
        </div>
      </main>

      <footer className="border-t px-6 py-4 text-center text-xs text-gray-400">
        © {new Date().getFullYear()} El Chillanejo · Distribuidora Chillán
      </footer>
    </div>
  );
}
