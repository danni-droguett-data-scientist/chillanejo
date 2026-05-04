"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowLeft, Lock } from "lucide-react";
import { useCarrito } from "@/hooks/useCarrito";
import { clp } from "@/lib/formato";

interface DatosComprador {
  nombre:   string;
  rut:      string;
  email:    string;
  telefono: string;
}

const VACIO: DatosComprador = { nombre: "", rut: "", email: "", telefono: "" };

interface ErroresForm {
  nombre?:   string;
  rut?:      string;
  email?:    string;
  telefono?: string;
}

function validar(datos: DatosComprador): ErroresForm {
  const errores: ErroresForm = {};
  if (!datos.nombre.trim())   errores.nombre   = "El nombre es obligatorio";
  if (!datos.rut.trim())      errores.rut      = "El RUT es obligatorio";
  if (!datos.email.trim())    errores.email    = "El correo es obligatorio";
  else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(datos.email))
    errores.email = "Correo inválido";
  if (!datos.telefono.trim()) errores.telefono = "El teléfono es obligatorio";
  return errores;
}

export default function CheckoutPage() {
  const { items, totales } = useCarrito();
  const [datos,      setDatos]      = useState<DatosComprador>(VACIO);
  const [errores,    setErrores]    = useState<ErroresForm>({});
  const [procesando, setProcesando] = useState(false);
  const [enviado,    setEnviado]    = useState(false);

  const set = (campo: keyof DatosComprador) =>
    (e: React.ChangeEvent<HTMLInputElement>) => {
      setDatos((d) => ({ ...d, [campo]: e.target.value }));
      if (errores[campo]) setErrores((er) => ({ ...er, [campo]: undefined }));
    };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (totales.subtotal_neto < 5000) return;
    const nuevosErrores = validar(datos);
    if (Object.keys(nuevosErrores).length) {
      setErrores(nuevosErrores);
      return;
    }
    setProcesando(true);
    // Integración con Mercado Pago pendiente — Fase 2
    await new Promise((r) => setTimeout(r, 800));
    setProcesando(false);
    setEnviado(true);
  };

  if (!items.length) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <p className="text-gray-500 mb-3">No hay productos en el carrito.</p>
          <Link href="/catalogo" className="text-[#2563EB] hover:underline text-sm">
            Ir al catálogo
          </Link>
        </div>
      </div>
    );
  }

  if (enviado) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4">
        <div className="max-w-md w-full text-center space-y-4">
          <div className="text-5xl">✓</div>
          <h1 className="text-xl font-bold text-[#1F2937]">Pedido recibido</h1>
          <p className="text-gray-500 text-sm">
            La integración con Mercado Pago se activará próximamente.
            Te avisaremos a <strong>{datos.email}</strong> cuando esté disponible.
          </p>
          <Link
            href="/catalogo"
            className="inline-block rounded-lg bg-[#2563EB] px-6 py-2.5 text-sm font-medium text-white hover:bg-blue-700 transition-colors"
          >
            Volver al catálogo
          </Link>
        </div>
      </div>
    );
  }

  const campos: { campo: keyof DatosComprador; label: string; tipo: string }[] = [
    { campo: "nombre",   label: "Nombre o razón social", tipo: "text"  },
    { campo: "rut",      label: "RUT",                   tipo: "text"  },
    { campo: "email",    label: "Correo electrónico",    tipo: "email" },
    { campo: "telefono", label: "Teléfono",              tipo: "tel"   },
  ];

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="border-b bg-white px-4 py-4">
        <div className="max-w-4xl mx-auto flex items-center gap-3">
          <Link href="/carrito" className="text-gray-400 hover:text-gray-600 transition-colors">
            <ArrowLeft className="h-5 w-5" />
          </Link>
          <h1 className="text-lg font-semibold text-[#1F2937]">Finalizar compra</h1>
          <Lock className="h-4 w-4 text-gray-300 ml-auto" />
        </div>
      </header>

      <div className="max-w-4xl mx-auto px-4 py-6 grid grid-cols-1 lg:grid-cols-5 gap-6">
        <form onSubmit={handleSubmit} className="lg:col-span-3 space-y-4" noValidate>
          <div className="rounded-xl border bg-white p-5 shadow-sm space-y-4">
            <h2 className="font-semibold text-[#1F2937]">Datos del comprador</h2>

            {campos.map(({ campo, label, tipo }) => (
              <div key={campo}>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  {label} <span className="text-red-500">*</span>
                </label>
                <input
                  type={tipo}
                  value={datos[campo]}
                  onChange={set(campo)}
                  className={`w-full rounded-lg border px-3 py-2.5 text-sm focus:outline-none focus:ring-2 ${
                    errores[campo]
                      ? "border-red-300 focus:border-red-400 focus:ring-red-400/20"
                      : "border-gray-300 focus:border-blue-400 focus:ring-blue-400/20"
                  }`}
                />
                {errores[campo] && (
                  <p className="text-xs text-red-500 mt-1">{errores[campo]}</p>
                )}
              </div>
            ))}
          </div>

          {totales.subtotal_neto < 5000 && (
            <p className="text-sm text-amber-600 text-center">
              Monto mínimo de compra: {clp(5000)} neto
            </p>
          )}
          <button
            type="submit"
            disabled={procesando || totales.subtotal_neto < 5000}
            className="w-full flex items-center justify-center gap-2 rounded-lg bg-[#2563EB] px-5 py-3.5 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-60 transition-colors"
          >
            <Lock className="h-4 w-4" />
            {procesando ? "Procesando…" : `Confirmar pedido · ${clp(totales.subtotal_bruto)}`}
          </button>
          <p className="text-center text-xs text-gray-400">
            Pago con Mercado Pago · Disponible próximamente
          </p>
        </form>

        <div className="lg:col-span-2 rounded-xl border bg-white p-5 shadow-sm h-fit space-y-3">
          <h2 className="font-semibold text-[#1F2937]">Tu pedido</h2>
          <div className="space-y-2 max-h-64 overflow-y-auto">
            {items.map((item) => (
              <div key={item.relbase_id} className="flex justify-between text-sm gap-2">
                <span className="text-gray-600 truncate">
                  {item.nombre} <span className="text-gray-400">×{item.cantidad}</span>
                </span>
                <span className="tabular-nums text-[#1F2937] shrink-0">
                  {clp(item.precio_bruto * item.cantidad)}
                </span>
              </div>
            ))}
          </div>
          <div className="border-t pt-3 space-y-1.5 text-sm">
            <div className="flex justify-between text-gray-500">
              <span>Neto</span>
              <span className="tabular-nums">{clp(totales.subtotal_neto)}</span>
            </div>
            <div className="flex justify-between text-gray-500">
              <span>IVA (19%)</span>
              <span className="tabular-nums">{clp(totales.iva)}</span>
            </div>
            <div className="flex justify-between font-bold text-[#1F2937] pt-1 border-t">
              <span>Total</span>
              <span className="tabular-nums">{clp(totales.subtotal_bruto)}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
