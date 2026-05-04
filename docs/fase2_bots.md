# Fase 2 — Diseño Técnico: Bots de Ventas

> El Chillanejo — Plataforma Digital  
> Última actualización: 27/04/2026  
> Autor: Daniel Droguett R.

---

## 1. Visión general

Tres bots de atención y ventas sobre canales sociales existentes del negocio. Motor único de procesamiento: n8n orquesta el flujo, Claude API interpreta lenguaje natural, Supabase provee el catálogo y registra los pedidos.

Los tres bots comparten la misma lógica de negocio (catálogo, carrito, pedidos). Solo difiere el canal de entrada/salida.

```
Canal (WhatsApp / Instagram / Messenger)
  └─→ Webhook n8n
        └─→ Nodo Claude API (NLU + respuesta)
              └─→ Supabase (catálogo, pedidos_online)
                    └─→ Respuesta al canal
```

---

## 2. Stack por canal

| Canal | Entrada webhook | SDK salida | Auth |
|---|---|---|---|
| WhatsApp Business | Twilio Messaging Webhook | Twilio REST API (`POST /Messages`) | Account SID + Auth Token |
| Instagram DM | Meta Webhooks (Graph API) | Graph API `/me/messages` | Meta App Token (page-scoped) |
| Facebook Messenger | Meta Webhooks (Graph API) | Graph API `/me/messages` | Meta App Token (page-scoped) |

Instagram y Facebook comparten la misma app de Meta y el mismo token de página. Se diferencia por el campo `messaging_product` o el `sender.id` del webhook.

---

## 3. Flujo de conversación

### 3.1 Estados del bot

```
INICIO → MENU → CATALOGO → PRODUCTO → CARRITO → DATOS → CONFIRMACION → PEDIDO_REGISTRADO
                    ↕                    ↕                    ↕
                BUSQUEDA             ELIMINAR             CANCELAR
```

Estado persistido en tabla `bot_sesiones` (Supabase). Clave: `{canal}:{sender_id}`.

### 3.2 Intenciones que resuelve Claude API

| Intención | Ejemplos de mensaje |
|---|---|
| `ver_catalogo` | "qué tienen", "catálogo", "qué hay disponible" |
| `buscar_producto` | "tienen cloro?", "busco jabón", "precio del detergente" |
| `agregar_carrito` | "quiero 3 de ese", "agrega 2 limpiavidrios" |
| `ver_carrito` | "qué llevo", "resumen de mi pedido" |
| `confirmar_pedido` | "confirmo", "sí quiero", "procede" |
| `cancelar` | "cancelo", "no quiero nada", "bye" |
| `ayuda` | "no entiendo", "?" |

Claude API recibe: mensaje del usuario + estado actual de la sesión + últimos 5 turnos. Responde en JSON: `{ intencion, parametros, respuesta_texto }`.

### 3.3 Prompt del sistema (Claude API)

```
Eres el asistente de ventas de El Chillanejo, distribuidora de aseo y abarrotes en Chillán.
Tu tono es amable, directo y en español chileno informal.
Responde SIEMPRE con JSON válido: { "intencion": string, "parametros": object, "respuesta": string }
El campo "respuesta" es el texto que se enviará al cliente — máximo 300 caracteres por mensaje.
No inventes productos. Si no encuentras el producto en el catálogo, di que no está disponible.
Estado actual de la sesión: {{estado_sesion}}
Carrito actual: {{carrito}}
```

---

## 4. Catálogo desde Supabase

Query al iniciar `ver_catalogo` o `buscar_producto`:

```sql
select relbase_id, sku, nombre, precio_neto,
       round(precio_neto * 1.19) as precio_bruto
from productos
where activo = true
  and stock_disponible > 0   -- vista o columna calculada
order by nombre
limit 50;
```

El bot presenta los productos en grupos de 5, con navegación `"siguiente"` / `"anterior"`.

Para búsqueda por texto: `nombre ilike '%{{término}}%'`.

---

## 5. Carrito en sesión

El carrito no se persiste en Supabase hasta el momento de la confirmación. Se mantiene en el campo `carrito_json` de `bot_sesiones`:

```json
{
  "items": [
    { "relbase_id": 1042, "nombre": "Cloro 1L", "cantidad": 3, "precio_bruto": 1547 }
  ],
  "total_bruto": 4641
}
```

---

## 6. Registro de pedido

Al confirmar, el bot solicita:
1. Nombre completo
2. RUT (opcional para clientes habituales)
3. Teléfono de contacto

Luego inserta en `pedidos_online`:

```sql
insert into pedidos_online (
  canal, canal_sender_id,
  nombre_cliente, rut_cliente, telefono_cliente,
  items_json, total_bruto,
  codigo_retiro, estado, origen
) values (
  'whatsapp', '56912345678',
  'Juan Pérez', '12.345.678-9', '+56912345678',
  '[...]', 4641,
  generate_codigo_retiro(),  -- función en Supabase: 6 dígitos únicos del día
  'pendiente', 'bot'
);
```

Respuesta al cliente:
```
¡Pedido registrado! 🧾
Código de retiro: 481392
Tienes 3 días hábiles para retirar en local.
Dirección: [dirección El Chillanejo]
Horario: [horario]
```

---

## 7. Notificaciones a Mirella

Al registrar un pedido, n8n dispara una notificación vía Twilio WhatsApp al número de Mirella:

```
Nuevo pedido bot ({{canal}})
Cliente: Juan Pérez / +56912345678
Total: $4.641
Código: 481392
Ver panel: https://dashboard.elchillanejo.cl/pedidos
```

---

## 8. Schema Supabase — tablas del bot

### `bot_sesiones`

```sql
create table bot_sesiones (
  id            uuid primary key default uuid_generate_v4(),
  canal         text not null,          -- 'whatsapp' | 'instagram' | 'messenger'
  sender_id     text not null,
  estado        text not null default 'INICIO',
  carrito_json  jsonb not null default '{"items":[],"total_bruto":0}',
  historial     jsonb not null default '[]',  -- últimos 5 turnos
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  unique(canal, sender_id)
);
```

### `pedidos_online` (compartida con tienda online)

Ver sección 6 arriba y `fase2_tienda_online.md` para el schema completo.

---

## 9. Flujo n8n por canal

### 9.1 WhatsApp (Twilio)

```
Webhook Twilio (POST /webhook/twilio)
  → Nodo "Normalizar mensaje Twilio"     { canal, sender_id, texto }
  → Nodo "Leer sesión Supabase"
  → Nodo "Claude API — NLU"
  → Switch por intencion
      ver_catalogo   → HTTP Supabase productos → Formatear → Twilio sendMessage
      buscar_producto → HTTP Supabase ilike  → Formatear → Twilio sendMessage
      agregar_carrito → Actualizar carrito en sesión → Twilio sendMessage
      confirmar_pedido → Insert pedidos_online → Notificar Mirella → Twilio sendMessage
      cancelar        → Limpiar sesión → Twilio sendMessage
  → Nodo "Guardar sesión Supabase"
```

### 9.2 Instagram DM y Facebook Messenger

Idéntico al flujo Twilio, cambiando:
- Nodo entrada: Meta Webhook (verificación GET con `hub.challenge`)
- Nodo normalizar: extrae `sender.id` y `message.text` del payload de Graph API
- Nodo respuesta: `POST https://graph.facebook.com/v19.0/me/messages` con el `page_access_token`

Un solo flujo n8n puede manejar ambos canales Meta usando un Switch por `messaging_product` o `object` del payload.

---

## 10. Configuración de credenciales en n8n

| Variable n8n | Valor |
|---|---|
| `TWILIO_ACCOUNT_SID` | SID de la cuenta Twilio |
| `TWILIO_AUTH_TOKEN` | Auth token Twilio |
| `TWILIO_WHATSAPP_FROM` | `whatsapp:+56XXXXXXXXX` |
| `META_PAGE_ACCESS_TOKEN` | Token de página Meta |
| `META_VERIFY_TOKEN` | Token de verificación webhook Meta |
| `ANTHROPIC_API_KEY` | Clave Claude API |
| `SUPABASE_URL` | URL del proyecto Supabase |
| `SUPABASE_SERVICE_ROLE_KEY` | Service role key Supabase |

---

## 11. Límites y consideraciones operacionales

- **Rate limit Twilio WhatsApp**: 1 mensaje/seg por número en sandbox; en producción según tier aprobado.
- **Rate limit Meta**: 200 mensajes/hora por conversación por defecto.
- **Sesión TTL**: limpiar sesiones sin actividad > 24 horas vía cron n8n diario.
- **Productos de abarrotes y aseo**: no hay restricciones de venta por medio, pero registrar `categoria` en el item del pedido para análisis futuro.
- **Devoluciones por bot**: el bot no gestiona devoluciones. Escala siempre a Mirella o al panel web.

---

## 12. Orden de implementación

1. Flujo WhatsApp (Twilio) — ya existe cuenta, menor fricción de aprobación.
2. Facebook Messenger — aprobación Meta relativamente rápida.
3. Instagram DM — requiere cuenta verificada y revisión adicional de Meta.
