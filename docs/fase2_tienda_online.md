# Fase 2 — Diseño Técnico: Tienda Online

> El Chillanejo — Plataforma Digital  
> Última actualización: 27/04/2026  
> Autor: Daniel Droguett R.

---

## 1. Stack tecnológico

| Capa | Tecnología |
|---|---|
| Framework | Next.js 14 (App Router) |
| UI | Tailwind CSS + shadcn/ui |
| Estado global | Zustand (carrito) |
| Backend / DB | Supabase (PostgreSQL + Edge Functions) |
| Pagos | Mercado Pago Checkout Pro |
| Split automático | Mercado Pago OAuth (aplicaciones de marketplace) |
| Email | Resend |
| Notificaciones internas | Twilio WhatsApp |
| Deploy | Vercel |

> **Migración desde Vite**: la carpeta `plataforma/` actual usa Vite + React sin App Router.  
> La tienda online en Next.js se construye en `plataforma/` como reemplazo completo.  
> Stripe se elimina — dependencias `@stripe/*` se remueven del `package.json`.

---

## 2. Estructura de carpetas (Next.js App Router)

```
plataforma/
├── app/
│   ├── layout.tsx                  ← layout raíz + providers
│   ├── page.tsx                    → redirige a /catalogo
│   ├── catalogo/
│   │   └── page.tsx                ← catálogo público
│   ├── producto/[id]/
│   │   └── page.tsx                ← detalle de producto
│   ├── carrito/
│   │   └── page.tsx                ← resumen del carrito
│   ├── checkout/
│   │   └── page.tsx                ← formulario + redirect MP
│   ├── pedido/
│   │   ├── confirmado/page.tsx     ← éxito post-pago
│   │   └── cancelado/page.tsx      ← cancelación MP
│   └── panel/
│       ├── layout.tsx              ← auth guard (solo Mirella)
│       ├── page.tsx                ← lista pedidos
│       ├── [codigo]/page.tsx       ← detalle pedido
│       └── devolucion/[id]/page.tsx
├── components/
│   ├── catalogo/
│   ├── carrito/
│   ├── checkout/
│   └── panel/
├── lib/
│   ├── supabase.ts
│   ├── mercadopago.ts
│   └── formato.ts
├── store/
│   └── carrito.ts                  ← Zustand
└── hooks/
    ├── useProductos.ts
    ├── useCarrito.ts
    └── usePedidos.ts
```

---

## 3. Catálogo de productos

### 3.1 Query Supabase

```typescript
// hooks/useProductos.ts
const { data } = await supabase
  .from("productos")
  .select("relbase_id, sku, nombre, descripcion, precio_neto, imagen_url, categoria_nombre")
  .eq("activo", true)
  .gt("stock_disponible", 0)
  .order("nombre");
```

### 3.2 Precio al público

`precio_bruto = precio_neto * 1.19` (IVA 19%). Calculado en cliente, no almacenado.

### 3.3 UX del catálogo

- Grid responsivo: 2 col móvil / 3 col tablet / 4 col desktop.
- Filtro por categoría (abarrotes / aseo / otros).
- Búsqueda en tiempo real por nombre (debounce 300ms, filtro client-side sobre el dataset cargado).
- Botón "Agregar al carrito" inline. Badge con cantidad en carrito flotante en header.
- Sin paginación — El Chillanejo tiene un catálogo manejable (~200–500 productos activos).

---

## 4. Carrito de compras

### 4.1 Store Zustand

```typescript
// store/carrito.ts
interface ItemCarrito {
  relbase_id: number;
  sku: string;
  nombre: string;
  precio_neto: number;
  precio_bruto: number;
  cantidad: number;
  imagen_url?: string;
}

interface CarritoStore {
  items: ItemCarrito[];
  agregar: (producto: Omit<ItemCarrito, "cantidad">, cantidad?: number) => void;
  cambiarCantidad: (relbase_id: number, cantidad: number) => void;
  quitar: (relbase_id: number) => void;
  vaciar: () => void;
  totales: () => { subtotal_neto: number; subtotal_bruto: number; iva: number; num_items: number };
}
```

Persiste en `localStorage` con `persist` middleware de Zustand.

### 4.2 UX del carrito

- Drawer lateral en desktop, página completa en móvil.
- Incremento/decremento por producto.
- Validación de stock al abrir carrito: si un producto ya no tiene stock, se marca con badge rojo "Sin stock" y se bloquea el checkout hasta que se elimine.

---

## 5. Checkout con Mercado Pago Checkout Pro

### 5.1 Flujo completo

```
1. Cliente llena datos (nombre, RUT, email, teléfono)
2. POST /api/crear-preferencia-mp
      → Valida stock en Supabase
      → Inserta pedido en estado 'pendiente_pago'
      → Llama a MP API /checkout/preferences con split OAuth
      → Retorna { preference_id, init_point }
3. Redirect a init_point (Mercado Pago Checkout Pro)
4. Cliente paga (tarjeta, débito, transferencia, Webpay)
5. MP redirige a:
      /pedido/confirmado?payment_id=...&status=approved
      /pedido/cancelado
6. Webhook MP (POST /api/webhook-mp) actualiza estado pedido en Supabase
7. Notificación a cliente vía Resend (email) + Twilio (WhatsApp opcional)
8. Notificación a Mirella vía Twilio WhatsApp
```

### 5.2 Split automático 92/8 via Mercado Pago OAuth

MP permite marketplaces donde el vendedor (El Chillanejo) autoriza al marketplace (plataforma del CEO) a cobrar en su nombre y retener una comisión.

**Setup una sola vez:**
1. Crear app en MP Developers como "marketplace".
2. El Chillanejo autoriza via OAuth: `GET https://auth.mercadopago.cl/authorization?client_id=...&response_type=code&platform_id=mp&redirect_uri=...`
3. Intercambiar `code` por `access_token` + `refresh_token` de la cuenta de El Chillanejo. Guardar en Supabase (tabla `mp_credentials`), cifrado.
4. En cada preferencia, usar `access_token` del Chillanejo con el parámetro `marketplace_fee` calculado como `total_bruto * 0.08`.

**Parámetro en la preferencia:**
```json
{
  "items": [...],
  "marketplace": "{{MP_APP_ID_CEO}}",
  "marketplace_fee": 368,
  "back_urls": { "success": "...", "failure": "...", "pending": "..." },
  "notification_url": "https://tienda.chillanejo.cl/api/webhook-mp"
}
```

MP deposita automáticamente:
- 92% a la cuenta de El Chillanejo.
- 8% a la cuenta del CEO (retenido como `marketplace_fee`).

Esto opera desde la venta 1, sin mínimos ni períodos de espera.

### 5.3 Edge Function: `crear-preferencia-mp`

```typescript
// Pseudocódigo Supabase Edge Function
export default async (req: Request) => {
  const { items, comprador, total_bruto, total_neto } = await req.json();

  // 1. Validar stock
  for (const item of items) {
    const { data: prod } = await supabase
      .from("productos")
      .select("stock_disponible")
      .eq("relbase_id", item.relbase_id)
      .single();
    if (prod.stock_disponible < item.cantidad) {
      return Response.json({ error: `Sin stock: ${item.nombre}` }, { status: 422 });
    }
  }

  // 2. Generar código de retiro (6 dígitos únicos del día)
  const codigo_retiro = await generarCodigoRetiro();

  // 3. Insertar pedido pendiente
  const { data: pedido } = await supabase.from("pedidos_online").insert({
    nombre_cliente: comprador.nombre,
    rut_cliente: comprador.rut,
    email_cliente: comprador.email,
    telefono_cliente: comprador.telefono,
    items_json: items,
    total_neto,
    total_bruto,
    codigo_retiro,
    estado: "pendiente_pago",
    origen: "tienda_web",
    fecha_limite_retiro: calcularFechaLimiteRetiro(), // +3 días hábiles
  }).select().single();

  // 4. Crear preferencia MP
  const mpItems = items.map(i => ({
    title: i.nombre,
    quantity: i.cantidad,
    unit_price: i.precio_bruto,
    currency_id: "CLP",
  }));

  const preference = await mp.preferences.create({
    items: mpItems,
    payer: { name: comprador.nombre, email: comprador.email },
    marketplace: MP_APP_ID,
    marketplace_fee: Math.round(total_bruto * 0.08),
    external_reference: pedido.id,
    back_urls: {
      success: `${BASE_URL}/pedido/confirmado`,
      failure: `${BASE_URL}/pedido/cancelado`,
      pending: `${BASE_URL}/pedido/confirmado`,
    },
    notification_url: `${BASE_URL}/api/webhook-mp`,
    expires: true,
    expiration_date_to: new Date(Date.now() + 30 * 60 * 1000).toISOString(), // 30 min
  }, { access_token: CHILLANEJO_MP_ACCESS_TOKEN });

  return Response.json({ preference_id: preference.id, init_point: preference.init_point });
};
```

### 5.4 Webhook MP

```typescript
// app/api/webhook-mp/route.ts
export async function POST(req: Request) {
  const { type, data } = await req.json();
  if (type !== "payment") return Response.json({ ok: true });

  const pago = await mp.payment.get(data.id, { access_token: CHILLANEJO_MP_ACCESS_TOKEN });
  const pedidoId = pago.external_reference;
  const aprobado = pago.status === "approved";

  await supabase.from("pedidos_online").update({
    estado: aprobado ? "pagado" : "pago_fallido",
    mp_payment_id: String(data.id),
    mp_status: pago.status,
  }).eq("id", pedidoId);

  if (aprobado) {
    await notificarClienteEmail(pedidoId);
    await notificarMirella(pedidoId);
  }

  return Response.json({ ok: true });
}
```

### 5.5 Comprobante Mercado Pago como boleta SII

El Chillanejo ya tiene configurado en su cuenta de MP la emisión automática de boleta electrónica al SII para cada pago aprobado. MP actúa como emisor en nombre del comercio. No se requiere integración adicional desde la tienda — el comprobante fiscal lo genera MP automáticamente y lo envía al email del comprador.

**Implicancia técnica**: la tienda no necesita llamar a la API de Relbase para emitir boleta en ventas online pagadas con MP. Solo se crea nota de venta en Relbase al confirmar el retiro (para descontar stock — ver sección 8).

---

## 6. Código de retiro

### 6.1 Generación

```sql
-- Función Supabase
create or replace function generar_codigo_retiro() returns text
language plpgsql as $$
declare
  codigo text;
  existe boolean;
  hoy date := current_date;
begin
  loop
    codigo := lpad(floor(random() * 1000000)::text, 6, '0');
    select exists(
      select 1 from pedidos_online
      where codigo_retiro = codigo
        and fecha_pedido::date = hoy
    ) into existe;
    exit when not existe;
  end loop;
  return codigo;
end;
$$;
```

### 6.2 Comunicación al cliente

Al aprobarse el pago, Resend envía un email con:
- Código de retiro destacado (6 dígitos, fuente grande)
- Detalle del pedido
- Fecha límite de retiro (3 días hábiles desde la compra)
- Dirección y horario del local
- Instrucciones: presentar código en caja, sin necesidad de imprimir

**QR a futuro**: el código numérico es la base. El QR será simplemente la URL `https://tienda.chillanejo.cl/retiro/{{codigo}}` que Mirella puede escanear desde el panel.

---

## 7. Plazo de retiro y cancelación automática

### 7.1 Reglas

| Evento | Cuándo | Acción |
|---|---|---|
| Recordatorio | Día 2 hábil | Email + WhatsApp al cliente |
| Cancelación automática | Día 3 hábil al cierre | Estado → `cancelado_sin_retiro` |
| Cargo por reserva | Al cancelar | Retener el 8% del total (ya retenido por MP como `marketplace_fee`) |

El 92% restante se devuelve al cliente como reembolso en MP.

### 7.2 Cron n8n para vencimiento

```
Cron: 0 20 * * 1-5  (20:00 hrs, lunes a viernes)
  → Query pedidos con estado='pagado' y fecha_limite_retiro = hoy
  → Para cada uno:
      → Update estado='cancelado_sin_retiro'
      → Llamar MP API: reembolso parcial por (total_bruto * 0.92)
      → Notificar cliente: email + WhatsApp
      → Registrar en audit_log
```

### 7.3 Cron recordatorio día 2

```
Cron: 0 9 * * 1-5  (09:00 hrs, lunes a viernes)
  → Query pedidos con estado='pagado' y fecha_limite_retiro = mañana (día hábil)
  → Para cada uno:
      → Enviar recordatorio cliente (email + WhatsApp)
```

---

## 8. Panel Mirella

Acceso en `/panel`. Auth vía Supabase Auth (email/password). RLS en Supabase restringe a rol `mirella`.

### 8.1 Lista de pedidos (`/panel`)

Columnas: Código | Fecha | Cliente | Total | Estado | Acciones

Filtros:
- Estado: todos / pendiente / pagado / entregado / cancelado
- Búsqueda por código de retiro (input numérico, match instantáneo)
- Fecha (hoy / esta semana / rango personalizado)

### 8.2 Detalle de pedido (`/panel/[codigo]`)

Muestra:
- Datos del cliente (nombre, RUT, teléfono, email)
- Código de retiro
- Fecha límite de retiro
- Listado de productos (nombre, cantidad, precio unitario, subtotal)
- Total neto + IVA + total bruto
- Estado actual
- Historial de estados con timestamps

Acciones disponibles según estado:

| Estado pedido | Acción disponible |
|---|---|
| `pagado` | Confirmar entrega |
| `entregado` | Solicitar devolución (escala a CEO para escenario 2) |
| `cancelado_*` | Solo lectura |

### 8.3 Confirmar entrega

Al hacer clic en "Confirmar entrega":

1. Modal con selección de **forma de pago real recibida** (puede ser combinada):
   - Débito
   - Efectivo
   - Transferencia
   - Combinación débito + efectivo (con montos parciales)

2. Al confirmar:
   - `UPDATE pedidos_online SET estado='entregado', forma_pago_real=..., entregado_at=now()`
   - Llamada a **API Relbase** para crear nota de venta y descontar stock (ver 8.4)
   - Registro en `audit_log`

> **Nota sobre forma de pago**: el pago online ya fue procesado por MP. La forma de pago real que registra Mirella corresponde a cómo se gestionó internamente (ej. si el cliente pagó online pero hubo algún ajuste en caja). En el caso estándar, simplemente se confirma sin cambio de forma de pago.

### 8.4 Crear nota de venta en Relbase al confirmar entrega

La API de Relbase permite crear documentos de tipo nota de venta (tipo 1001). **No emite boleta ni factura** (requiere certificado digital, que El Chillanejo tiene separado). La nota de venta sirve para descontar stock en Relbase.

```python
# Edge Function o llamada directa
POST /api/v1/dtes
{
  "type_document": 1001,
  "customer_id": null,          # cliente anónimo si no está en Relbase
  "ware_house_id": {{bodega_id}},
  "items": [
    {
      "product_id": {{relbase_id}},
      "quantity": {{cantidad}},
      "price": {{precio_neto}},
      "discount": 0
    }
  ],
  "observations": "Pedido online #{{codigo_retiro}} — confirmado por Mirella"
}
```

La nota de venta en Relbase activa el descuento de stock automáticamente. El sync incremental de n8n sincronizará el stock actualizado a Supabase en el siguiente ciclo.

---

## 9. Devoluciones

### 9.1 Reglas generales

- Solo productos de rubro **abarrotes y aseo**: aplica devolución si el producto está **cerrado, sin abrir y en buen estado**.
- Plazo: **48 horas desde el retiro** (campo `entregado_at`).
- No aplica para productos con envase abierto, dañado, o con fecha de vencimiento próxima.

### 9.2 Escenario 1 — Pedido no entregado (cancelación)

**Quién aprueba**: CEO (Daniel).

Casos:
- Cancelación automática por vencimiento de plazo (ver sección 7.2).
- Cancelación manual antes del retiro (cliente solicita por WhatsApp/bot).

Flujo:
```
Solicitud → CEO aprueba en Dashboard CEO → n8n trigger
  → MP API: reembolso total (si cancelación manual) o parcial 92% (si venció plazo)
  → Update pedido_online: estado='cancelado', motivo_cancelacion, cancelado_at
  → Notificación cliente: email + WhatsApp
  → No se crea nota de venta en Relbase (stock no fue descontado)
```

### 9.3 Escenario 2 — Pedido ya entregado

**Quién aprueba**: Mirella (con validación de condición del producto).

Flujo:
```
Mirella abre /panel/devolucion/[id]
  → Selecciona productos a devolver (parcial o total)
  → Confirma condición: "productos cerrados y en buen estado"
  → Ingresa motivo
  → Estado → 'devolucion_solicitada'
  → Notificación al CEO para revisión final

CEO aprueba en Dashboard CEO:
  → MP API: reembolso (total o parcial según productos devueltos)
  → Update pedido_online: estado='devuelto', devolucion_aprobada_at
  → Nota de venta correctiva en Relbase (opcional, para re-ingresar stock si aplica)
  → Notificación cliente
```

### 9.4 Tipos de reembolso por forma de pago

| Cómo pagó el cliente | Reembolso |
|---|---|
| Solo MP online | Reembolso automático vía MP API |
| Débito en local | Transferencia manual (se registra en `devolucion_metodo`) |
| Efectivo en local | Efectivo en caja en próxima visita |
| Transferencia bancaria | Transferencia manual |
| Combinación | Prorrateo según montos parciales registrados por Mirella |

---

## 10. Schema Supabase — tablas tienda online

### `pedidos_online`

```sql
create table pedidos_online (
  id                    uuid primary key default uuid_generate_v4(),
  -- Origen
  origen                text not null default 'tienda_web',  -- 'tienda_web' | 'bot' | 'whatsapp' | 'instagram' | 'messenger'
  canal_sender_id       text,                                 -- solo para pedidos bot
  -- Cliente
  nombre_cliente        text not null,
  rut_cliente           text,
  email_cliente         text,
  telefono_cliente      text,
  -- Pedido
  items_json            jsonb not null,
  total_neto            numeric(14,2) not null,
  total_bruto           numeric(14,2) not null,
  codigo_retiro         text not null unique,
  -- Pago
  mp_preference_id      text,
  mp_payment_id         text,
  mp_status             text,
  forma_pago_real       text,                                 -- registrado por Mirella al entregar
  forma_pago_detalle    jsonb,                                -- { debito: 3000, efectivo: 2000 }
  -- Estado
  estado                text not null default 'pendiente_pago',
  -- Timestamps
  fecha_pedido          timestamptz not null default now(),
  fecha_limite_retiro   date,
  pagado_at             timestamptz,
  entregado_at          timestamptz,
  cancelado_at          timestamptz,
  -- Relbase
  relbase_nota_venta_id integer,                             -- ID DTE creado al confirmar entrega
  -- Devolución
  devolucion_estado     text,
  devolucion_items_json jsonb,
  devolucion_motivo     text,
  devolucion_aprobada_at timestamptz,
  devolucion_metodo     text,
  -- Auditoría
  created_at            timestamptz not null default now(),
  updated_at            timestamptz not null default now()
);

-- Estados válidos
-- pendiente_pago | pagado | entregado | cancelado_sin_retiro | cancelado_manual
-- pago_fallido | devolucion_solicitada | devuelto

create index idx_pedidos_codigo    on pedidos_online(codigo_retiro);
create index idx_pedidos_estado    on pedidos_online(estado);
create index idx_pedidos_fecha     on pedidos_online(fecha_pedido);
create index idx_pedidos_mp_payment on pedidos_online(mp_payment_id);
```

### `mp_credentials`

```sql
create table mp_credentials (
  id            uuid primary key default uuid_generate_v4(),
  cuenta        text not null unique,            -- 'chillanejo' | 'ceo'
  access_token  text not null,                   -- cifrado con pgsodium
  refresh_token text,
  expires_at    timestamptz,
  updated_at    timestamptz not null default now()
);
-- Solo accesible por service_role. Sin RLS pública.
```

### `audit_log`

```sql
create table audit_log (
  id         bigserial primary key,
  tabla      text not null,
  registro_id uuid not null,
  accion     text not null,         -- 'confirmar_entrega' | 'cancelar' | 'devolucion_aprobar' ...
  actor      text not null,         -- 'mirella' | 'ceo' | 'sistema' | 'bot'
  detalle    jsonb,
  created_at timestamptz not null default now()
);
```

---

## 11. Configuración de variables de entorno

```env
# Mercado Pago
MP_APP_ID=...
MP_CLIENT_SECRET=...
CHILLANEJO_MP_ACCESS_TOKEN=...    # se obtiene y refresca vía OAuth
MP_WEBHOOK_SECRET=...

# Supabase
NEXT_PUBLIC_SUPABASE_URL=...
NEXT_PUBLIC_SUPABASE_ANON_KEY=...
SUPABASE_SERVICE_ROLE_KEY=...

# Relbase
RELBASE_TOKEN_USUARIO=...
RELBASE_TOKEN_EMPRESA=...

# Resend
RESEND_API_KEY=...
EMAIL_FROM=pedidos@chillanejo.cl

# Twilio (notificaciones Mirella)
TWILIO_ACCOUNT_SID=...
TWILIO_AUTH_TOKEN=...
TWILIO_WHATSAPP_MIRELLA=whatsapp:+56XXXXXXXXX
```

---

## 12. RLS Supabase — tienda online

```sql
-- pedidos_online: solo service_role escribe; mirella lee los suyos
alter table pedidos_online enable row level security;

create policy "mirella_lee_pedidos" on pedidos_online
  for select using (auth.jwt() ->> 'role' = 'mirella');

create policy "mirella_actualiza_pedidos" on pedidos_online
  for update using (auth.jwt() ->> 'role' = 'mirella')
  with check (estado in ('entregado', 'devolucion_solicitada'));

-- Solo service_role (Edge Functions) puede insertar y hacer cambios de estado mayores
```

---

## 13. Orden de implementación

1. Schema Supabase (`pedidos_online`, `mp_credentials`, `audit_log`) + migraciones RLS.
2. Generar función `generar_codigo_retiro()` en Supabase.
3. OAuth MP: setup app marketplace, flujo autorización El Chillanejo, persistir tokens.
4. Edge Function `crear-preferencia-mp` + webhook MP.
5. Next.js: catálogo → carrito → checkout (migrar desde Vite).
6. Páginas post-pago: `/pedido/confirmado`, `/pedido/cancelado`.
7. Emails Resend: confirmación de pedido + recordatorio día 2.
8. Panel Mirella: lista, detalle, confirmación de entrega, registro forma de pago.
9. Integración API Relbase: crear nota de venta al confirmar entrega.
10. Crons n8n: recordatorio día 2 + cancelación automática día 3.
11. Flujo devoluciones: Mirella + aprobación CEO.
