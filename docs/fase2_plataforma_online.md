# Fase 2 — Plataforma Online El Chillanejo

> El Chillanejo — Plataforma Digital  
> Última actualización: 27/04/2026  
> Autor: Daniel Droguett R.

---

## 1. Visión

Abrir el canal digital de El Chillanejo para ventas B2B y B2C. El negocio opera hoy solo de forma física en Chillán. La plataforma online suma:

- **Tienda web**: catálogo, carrito, checkout con pago online, retiro en local.
- **Bots de ventas**: WhatsApp, Instagram DM, Facebook Messenger — mismo catálogo y flujo de pedido.
- **Panel operativo Mirella**: gestión de pedidos online, confirmación de entrega, devoluciones.

---

## 2. Componentes principales

| Componente | Documento de diseño | Estado |
|---|---|---|
| Tienda online (Next.js) | `docs/fase2_tienda_online.md` | Diseño completo |
| Bots sociales (n8n + Claude) | `docs/fase2_bots.md` | Diseño completo |
| Dashboard Operativo (dashboards) | `dashboard/` | v1 en producción |

---

## 3. Flujo general de un pedido online

```
Cliente (web o bot)
  → Selecciona productos del catálogo (desde Supabase)
  → Arma carrito
  → Checkout: datos + pago
  → Mercado Pago Checkout Pro
  → Pago aprobado → código de retiro generado
  → Email + WhatsApp al cliente con código
  → Mirella recibe notificación en panel
  → Cliente va al local y presenta código
  → Mirella confirma entrega en panel
  → API Relbase crea nota de venta → stock descontado
  → Sync n8n actualiza Supabase con nuevo stock
```

---

## 4. Arquitectura de datos

Capa 2 de la arquitectura general (Supabase) agrega las tablas de la plataforma online:

```
ventas          ← DTEs Relbase (sync existente)
ventas_detalle  ← líneas DTEs
pedidos_online  ← pedidos web + bot (NUEVO fase 2)
bot_sesiones    ← estado conversacional bots (NUEVO fase 2)
mp_credentials  ← tokens OAuth Mercado Pago (NUEVO fase 2)
audit_log       ← log de acciones panel Mirella (NUEVO fase 2)
```

---

## 5. Roles y accesos

| Persona | Acceso |
|---|---|
| Clientes web | Solo tienda pública (sin auth) |
| Clientes bot | Sesión temporal en `bot_sesiones` |
| Mirella | Panel `/panel` (auth Supabase, rol `mirella`) |
| Marcelo / Ramón | Dashboard operativo + ejecutivo |
| Daniel (CEO) | Todo + aprobación devoluciones + Dashboard CEO personal |

---

## 6. Integraciones externas

| Servicio | Propósito |
|---|---|
| Mercado Pago | Pago online, split automático, boleta SII |
| Relbase API | Crear notas de venta al confirmar entrega |
| Twilio WhatsApp | Bot WhatsApp + notificaciones a Mirella |
| Meta Graph API | Bots Instagram DM + Facebook Messenger |
| Resend | Emails transaccionales (confirmación, recordatorio, cancelación) |
| Claude API | NLU e inteligencia conversacional de los bots |
| n8n | Orquestación de flujos: sync, crons, notificaciones, bots |

---

## 7. Consideraciones de productos

El Chillanejo opera en los rubros **abarrotes y aseo**. Esto impacta:

- **Devoluciones**: solo se aceptan productos cerrados, sin abrir, en buen estado. No aplica para productos con envase dañado o abierto.
- **Stock crítico**: productos de alta rotación — el descuento de stock al confirmar entrega es prioritario para mantener disponibilidad actualizada.
- **Catálogo en bots**: mostrar solo productos con `stock_disponible > 0` para no generar pedidos imposibles de cumplir.

---

## 8. Decisiones de arquitectura registradas

| Fecha | Decisión | Motivo |
|---|---|---|
| Apr 2026 | Supabase como capa analítica central | Agnóstica de ERP, permite múltiples fuentes |
| Apr 2026 | n8n como motor de automatización | Sin vendor lock-in, self-hosteable, visual |
| Apr 2026 | Retiro en local (sin despacho) | Simplifica logística en fase 2; despacho es fase 3 |
| Apr 2026 | Claude API solo en bots y CEO dashboard | Costo controlado; no para todos los usuarios |

---

---

## ACTUALIZACIÓN — 27/04/2026

### Mercado Pago reemplaza a Stripe

**Decisión confirmada con Marcelo el 27/04/2026.**

Stripe y Webpay Plus quedan descartados para la plataforma de El Chillanejo. Mercado Pago es la pasarela de pago oficial.

**Motivos:**
- MP tiene mayor penetración en Chile y mejor UX para usuarios finales.
- El Chillanejo ya opera con cuenta MP activa.
- MP emite comprobante válido como boleta al SII de forma nativa.
- El modelo OAuth de marketplace de MP permite split automático desde la venta 1, sin necesidad de Stripe Connect.

**Impacto en código existente:**
- `plataforma/package.json`: eliminar `@stripe/react-stripe-js` y `@stripe/stripe-js`.
- `plataforma/src/pages/Checkout.tsx`: reemplazar flujo Stripe por redirect a MP Checkout Pro.
- Supabase Edge Function `crear-orden`: reemplazar por `crear-preferencia-mp`.
- Variables de entorno: eliminar `STRIPE_*`, agregar `MP_*`.

---

### Split automático 92/8 desde venta 1 vía Mercado Pago OAuth

El split se implementa via **Mercado Pago Marketplace (OAuth)**:

- El Chillanejo (vendedor) autoriza a la plataforma del CEO (marketplace) vía OAuth de MP.
- En cada preferencia de pago se incluye `marketplace_fee = total_bruto * 0.08`.
- MP deposita automáticamente:
  - **92%** en la cuenta de El Chillanejo.
  - **8%** en la cuenta del CEO (retenido como `marketplace_fee`).
- Opera desde la primera venta, sin mínimos ni períodos de retención.

Detalles de implementación: ver `docs/fase2_tienda_online.md` sección 5.2.

---

### Cuenta personal MP del CEO

La cuenta de Mercado Pago del CEO actúa como el **marketplace** que recibe el 8% de comisión.

- Al activar la cuenta personal MP del CEO en producción: migrar el `MP_APP_ID` y credenciales de la app marketplace a esa cuenta definitiva.
- Hasta entonces, operar con cuenta de desarrollo/sandbox.
- La variable `CHILLANEJO_MP_ACCESS_TOKEN` (cuenta de El Chillanejo, obtenida vía OAuth) no cambia con este paso.

---

### Comprobante MP válido como boleta SII

Mercado Pago emite automáticamente la boleta electrónica al SII en cada pago aprobado, asociada al RUT fiscal de El Chillanejo. El comprobante se envía al email del comprador.

**Implicancia técnica:**
- La tienda online **no necesita** llamar a Relbase para emitir boleta en ventas online pagadas con MP.
- Relbase se usa solo para crear **nota de venta** (tipo 1001) al confirmar el retiro, con el único propósito de descontar stock.
- Las boletas de ventas online aparecerán en el SII directamente via MP, no en Relbase. Para efectos del dashboard, se deben reconciliar con los registros en `pedidos_online`.

---

### API Relbase — crear notas de venta (tipo 1001)

Confirmado: la API de Relbase permite crear documentos de tipo **nota de venta (1001)**. No permite emitir boletas (33) ni facturas (39) vía API — esos requieren certificado digital y se emiten desde la interfaz Relbase o vía MP en el caso de ventas online.

**Uso en la plataforma**: al confirmar el retiro en el Panel Mirella, se crea una nota de venta en Relbase para descontar el stock. El sync incremental de n8n llevará ese cambio a Supabase en el siguiente ciclo horario.

Endpoint: `POST /api/v1/dtes` con `type_document: 1001`.  
Detalles: ver `docs/fase2_tienda_online.md` sección 8.4.
