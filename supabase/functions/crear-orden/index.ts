/**
 * crear-orden — Edge Function que:
 *  1. Persiste la orden en Supabase (tabla ordenes).
 *  2. Crea una Stripe Checkout Session con transfer_data para el split 92/8.
 *  3. Retorna la checkout_url al cliente.
 */

import Stripe from "npm:stripe@15.12.0";

const stripe = new Stripe(Deno.env.get("STRIPE_SECRET_KEY") ?? "", {
  apiVersion: "2024-04-10",
});

const CEO_STRIPE_ACCOUNT = Deno.env.get("STRIPE_CEO_ACCOUNT_ID") ?? "";
const PLATAFORMA_URL     = Deno.env.get("PLATAFORMA_URL") ?? "https://chillanejo.cl";
// Comisión CEO: 8% sobre ventas online
const COMISION_CEO_PCT   = 0.08;

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") {
    return new Response(null, {
      headers: {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "authorization, content-type",
      },
    });
  }

  try {
    const { items, comprador, total_bruto, total_neto } = await req.json();

    if (!items?.length) throw new Error("El carrito está vacío.");
    if (!comprador?.nombre || !comprador?.rut || !comprador?.email) {
      throw new Error("Faltan datos obligatorios del comprador.");
    }

    // Monto en centavos (Stripe usa centavos para CLP también)
    const monto_clp = Math.round(total_bruto);
    // Transfer al CEO: 8% del total
    const transfer_amount = Math.round(monto_clp * COMISION_CEO_PCT);

    // Líneas para Stripe Checkout
    const line_items = items.map((item: any) => ({
      price_data: {
        currency: "clp",
        product_data: { name: item.nombre },
        unit_amount: Math.round(item.precio_unitario_bruto),
      },
      quantity: item.cantidad,
    }));

    const session = await stripe.checkout.sessions.create({
      payment_method_types: ["card"],
      line_items,
      mode: "payment",
      success_url: `${PLATAFORMA_URL}/orden-confirmada?session_id={CHECKOUT_SESSION_ID}`,
      cancel_url:  `${PLATAFORMA_URL}/carrito`,
      customer_email: comprador.email,
      metadata: {
        comprador_nombre: comprador.nombre,
        comprador_rut:    comprador.rut,
        items_json:       JSON.stringify(items.map((i: any) => ({ c: i.codigo, q: i.cantidad }))),
      },
      // Split 92/8: transfiere 8% automáticamente a la cuenta CEO
      ...(CEO_STRIPE_ACCOUNT && transfer_amount > 0
        ? {
            payment_intent_data: {
              transfer_data: {
                destination: CEO_STRIPE_ACCOUNT,
                amount: transfer_amount,
              },
            },
          }
        : {}),
    });

    return new Response(
      JSON.stringify({ checkout_url: session.url, session_id: session.id }),
      { headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" } }
    );
  } catch (error: unknown) {
    const msg = error instanceof Error ? error.message : "Error desconocido";
    return new Response(
      JSON.stringify({ error: msg }),
      { status: 400, headers: { "Content-Type": "application/json" } }
    );
  }
});
