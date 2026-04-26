/**
 * Checkout.tsx — Página de pago con Stripe (Webpay Plus vía Stripe Connect).
 * Split automático: 92% negocio / 8% CEO en cada transacción.
 *
 * Flujo:
 *  1. Muestra resumen del carrito y formulario de datos del comprador.
 *  2. Al confirmar, llama al Edge Function "crear-orden" en Supabase.
 *  3. El Edge Function crea una PaymentIntent en Stripe con transfer_data.
 *  4. Redirige al cliente a Stripe Checkout o renderiza el formulario de pago.
 */

import { useState } from "react";
import { ArrowLeft, Lock } from "lucide-react";
import { useCarrito } from "@/hooks/useCarrito";
import { supabase } from "@/lib/supabase";

const CLP = new Intl.NumberFormat("es-CL", { style: "currency", currency: "CLP", maximumFractionDigits: 0 });

interface DatosComprador {
  nombre: string;
  rut: string;
  email: string;
  telefono: string;
  direccion: string;
  ciudad: string;
}

const VACÍO: DatosComprador = {
  nombre: "", rut: "", email: "", telefono: "", direccion: "", ciudad: "",
};

export default function Checkout() {
  const { items, totales, vaciar } = useCarrito();
  const [datos, setDatos] = useState<DatosComprador>(VACÍO);
  const [procesando, setProcesando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const set = (campo: keyof DatosComprador) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setDatos((d) => ({ ...d, [campo]: e.target.value }));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setProcesando(true);
    setError(null);

    try {
      // Llama al Edge Function que crea la orden en Supabase y la PaymentIntent en Stripe
      const { data, error: fnError } = await supabase.functions.invoke("crear-orden", {
        body: {
          items: items.map((i) => ({
            producto_id_relbase: i.producto_id_relbase,
            codigo: i.codigo,
            nombre: i.nombre,
            cantidad: i.cantidad,
            precio_unitario_bruto: i.precio_bruto,
          })),
          comprador: datos,
          total_bruto: totales.subtotal_bruto,
          total_neto: totales.subtotal_neto,
        },
      });

      if (fnError) throw fnError;

      // Redirige a Stripe Checkout
      if (data?.checkout_url) {
        vaciar();
        window.location.href = data.checkout_url;
      } else {
        throw new Error("No se recibió URL de pago.");
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Error al procesar el pago");
    } finally {
      setProcesando(false);
    }
  };

  if (!items.length) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <p className="text-gray-500 mb-3">No hay productos en el carrito.</p>
          <a href="/" className="text-blue-600 hover:underline text-sm">Ir al catálogo</a>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="border-b bg-white px-4 py-4">
        <div className="max-w-4xl mx-auto flex items-center gap-3">
          <a href="/carrito" className="text-gray-400 hover:text-gray-600">
            <ArrowLeft className="h-5 w-5" />
          </a>
          <h1 className="text-lg font-semibold text-gray-900">Finalizar compra</h1>
          <Lock className="h-4 w-4 text-gray-300 ml-auto" />
        </div>
      </header>

      <div className="max-w-4xl mx-auto px-4 py-6 grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* Formulario comprador */}
        <form onSubmit={handleSubmit} className="lg:col-span-3 space-y-4">
          <div className="rounded-xl border bg-white p-5 shadow-sm space-y-4">
            <h2 className="font-semibold text-gray-800">Datos del comprador</h2>

            {[
              { campo: "nombre",    label: "Nombre o razón social", tipo: "text",  req: true  },
              { campo: "rut",       label: "RUT",                   tipo: "text",  req: true  },
              { campo: "email",     label: "Correo electrónico",    tipo: "email", req: true  },
              { campo: "telefono",  label: "Teléfono",              tipo: "tel",   req: false },
              { campo: "direccion", label: "Dirección de entrega",  tipo: "text",  req: false },
              { campo: "ciudad",    label: "Ciudad",                tipo: "text",  req: false },
            ].map(({ campo, label, tipo, req }) => (
              <div key={campo}>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  {label} {req && <span className="text-red-500">*</span>}
                </label>
                <input
                  type={tipo}
                  required={req}
                  value={datos[campo as keyof DatosComprador]}
                  onChange={set(campo as keyof DatosComprador)}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-400/20"
                />
              </div>
            ))}
          </div>

          {error && (
            <div className="rounded-lg border border-red-100 bg-red-50 px-4 py-3 text-sm text-red-700">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={procesando}
            className="w-full flex items-center justify-center gap-2 rounded-lg bg-blue-600 px-5 py-3.5 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-60 transition-colors"
          >
            <Lock className="h-4 w-4" />
            {procesando ? "Procesando…" : `Pagar ${CLP.format(totales.subtotal_bruto)}`}
          </button>
          <p className="text-center text-xs text-gray-400">
            Pago seguro vía Stripe · Webpay Plus disponible
          </p>
        </form>

        {/* Resumen */}
        <div className="lg:col-span-2 rounded-xl border bg-white p-5 shadow-sm h-fit space-y-3">
          <h2 className="font-semibold text-gray-800">Tu pedido</h2>
          <div className="space-y-2 max-h-64 overflow-y-auto">
            {items.map((item) => (
              <div key={item.producto_id_relbase} className="flex justify-between text-sm gap-2">
                <span className="text-gray-600 truncate">
                  {item.nombre} <span className="text-gray-400">×{item.cantidad}</span>
                </span>
                <span className="tabular-nums text-gray-800 shrink-0">
                  {CLP.format(item.precio_bruto * item.cantidad)}
                </span>
              </div>
            ))}
          </div>
          <div className="border-t pt-3 space-y-1.5 text-sm">
            <div className="flex justify-between text-gray-500">
              <span>Neto</span>
              <span className="tabular-nums">{CLP.format(totales.subtotal_neto)}</span>
            </div>
            <div className="flex justify-between text-gray-500">
              <span>IVA</span>
              <span className="tabular-nums">{CLP.format(totales.iva)}</span>
            </div>
            <div className="flex justify-between font-bold text-gray-900 pt-1 border-t">
              <span>Total</span>
              <span className="tabular-nums">{CLP.format(totales.subtotal_bruto)}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
