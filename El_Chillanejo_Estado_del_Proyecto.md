# El Chillanejo — Estado del Proyecto

> Documento de estado y seguimiento del proyecto.
> Última actualización: 28/04/2026
> Autor: Daniel Droguett R.

---

## RESUMEN EJECUTIVO

Plataforma de data science y canal digital para El Chillanejo, distribuidora de aseo y abarrotes en Chillán.

**Socios:** Marcelo y Ramón  
**Ejecutor técnico:** Daniel Droguett R. (CEO / Data Scientist)  
**Administradora operativa:** Mirella

---

## FASE 1 — DATA SCIENCE Y DASHBOARD OPERATIVO

### Estado general: COMPLETO (base) / EN CURSO (automatización)

---

### 1. Supabase — Base de datos analítica

**Schema completo aplicado. 20 tablas totales.**

#### Tablas base (16)
- `ventas` — DTEs sincronizados desde Relbase (tipos 33, 39, 1001)
- `ventas_detalle` — líneas de productos con `margen_neto` calculado
- `productos` — catálogo con `costo_unitario` y `precio_neto`
- `clientes` — B2B y B2C, campo `es_anonimo`
- `stock` — snapshot actual por producto/bodega
- `stock_historico` — snapshots para análisis de tendencia
- `bodegas` — 2 bodegas: Principal y Punto de Venta
- `proveedores` — tabla propia (Relbase no entrega bien este dato)
- `categorias` — catálogo de categorías
- `compras` — órdenes de compra
- `compras_detalle` — líneas de compras
- `sync_log` — control de ingesta incremental por entidad
- `honorarios_ds` — ingresos DS del CEO (solo Owner)
- `ingresos_importacion` — honorarios por ciclo de importación (solo Owner)
- `costos_stack` — costos mensuales del stack (solo Owner)
- `pipeline_clientes` — futuros clientes DS (solo Owner)

#### Migraciones aplicadas
| Migración | Descripción | Estado |
|---|---|---|
| 001_schema_base.sql | Schema completo 16 tablas | ✅ Aplicada |
| 002_dashboard_views.sql | Vistas operativas | ✅ Aplicada |
| 003_rls_policies.sql | Políticas RLS (temporalmente deshabilitadas) | ✅ Aplicada |
| 004_ejecutivo_views.sql | Vistas dashboard ejecutivo | ✅ Aplicada |
| 005_ceo_views.sql | Vistas dashboard CEO personal | ✅ Aplicada |
| 006_add_forma_pago_ventas.sql | Campo `forma_pago` en tabla `ventas` | ✅ Aplicada |
| 007_add_canal_ventas.sql | Campo `canal` en tabla `ventas` (presencial/online_web/online_whatsapp/online_instagram/online_facebook) | ✅ Aplicada |

**⚠️ IMPORTANTE — RLS deshabilitado temporalmente:**
Las políticas RLS están definidas pero deshabilitadas. Se habilitarán cuando llegue la YubiKey (estimado ~5 junio 2026). Hasta entonces operar con service_role key únicamente desde backend y n8n.

---

### 2. Datos cargados — Carga histórica completa

| Tabla | Registros cargados |
|---|---|
| `ventas` | **126.916** ventas históricas |
| `ventas_detalle` | **307.895** líneas de detalle |
| `productos` | **1.095** productos |
| `stock` | Cargado (snapshot actual) |

Rango histórico: ~18 meses (hasta fecha de carga).  
Fuente: Relbase API — workflow histórico n8n ejecutado en Railway.

---

### 3. GitHub — Repositorio

**Repositorio:** `danni-droguett-data-scientist/chillanejo`

Estructura completa:
```
chillanejo/
├── CLAUDE.md                        ← contexto para Claude Code (actualizado)
├── El_Chillanejo_Estado_del_Proyecto.md  ← este archivo
├── fase2_bots.md                    ← diseño técnico bots sociales
├── fase2_tienda_online.md           ← diseño técnico tienda online
├── fase2_plataforma_online.md       ← visión general fase 2
├── conectores/relbase/              ← conector Relbase (template)
│   ├── client.py
│   ├── sync_incremental.py
│   └── __init__.py
├── n8n_flows/
│   ├── sync_diario.json             ← workflow histórico (FUNCIONANDO)
│   └── sync_incremental_diario.json ← workflow incremental (EN CONSTRUCCIÓN)
├── python/analysis/
│   └── top_productos.py
├── supabase/migrations/             ← 7 migraciones (001 a 007)
├── dashboard/                       ← Dashboard Operativo v1
├── plataforma/                      ← futura tienda online (actualmente Vite, migrar a Next.js)
├── bot/                             ← código bots sociales
└── docs/                            ← documentación técnica
    ├── fase2_bots.md
    ├── fase2_tienda_online.md
    └── fase2_plataforma_online.md
```

---

### 4. n8n — Automatización y flujos de ingesta

#### Workflow 1: sync_diario (carga histórica)
- **Estado:** ✅ Funcionando en Railway
- **Función:** carga histórica completa de ventas, detalle, productos y stock desde Relbase
- **Resultado:** 126.916 ventas + 307.895 líneas + 1.095 productos cargados

#### Workflow 2: sync_incremental_diario (sync diario delta)
- **Estado:** 🔶 En construcción — pendiente completar
- **Función:** sincronización incremental horaria de ventas nuevas y cambios de stock
- **Nodos implementados (16 total):**

| # | Nodo | Tipo | Estado |
|---|---|---|---|
| 1 | Cron — cada hora | scheduleTrigger | ✅ |
| 2 | Set Fecha Chile | code | ✅ |
| 3 | Fetch Ventas Relbase | httpRequest | ✅ |
| 4 | Mapear Ventas | code | 🔶 Bloqueado por N8N_BLOCK_ENV_ACCESS_IN_NODE |
| 5 | Juntar Ventas | code | ⬜ |
| 6 | Upsert Ventas Supabase | httpRequest | ⬜ |
| 7 | Fetch IDs Ventas Supabase | httpRequest | ⬜ |
| 8 | Expandir Ventas | code | ⬜ |
| 9 | Loop Detalle por DTE | splitInBatches | ⬜ |
| 10 | Fetch Detalle Relbase | httpRequest | ⬜ |
| 11 | Mapear Detalle | code | ⬜ |
| 12 | Juntar Detalle | code | ⬜ |
| 13 | Upsert Detalle Supabase | httpRequest | ⬜ |
| 14 | Update sync_log | httpRequest | ⬜ |
| 15 | ¿Hubo error? | if | ⬜ |
| 16 | Notificar error | emailSend | ⬜ |

**Problema activo:** La variable de entorno `N8N_BLOCK_ENV_ACCESS_IN_NODE=true` en Railway bloquea el acceso a `process.env` dentro de nodos Code de n8n. Pendiente resolución: usar credenciales n8n nativas o desactivar `N8N_BLOCK_ENV_ACCESS_IN_NODE` en el entorno Railway.

**Próximo paso:** Resolver bloqueo de variables de entorno y completar nodos 5 en adelante.

---

### 5. Dashboard Operativo v1

- **Estado:** ✅ Funcionando en localhost:3002
- **Stack:** React + Vite + Tailwind CSS + shadcn/ui + recharts
- **Usuarios objetivo:** Marcelo, Ramón, Mirella
- **Componentes construidos:**
  - `TarjetaKpi.tsx` — tarjetas de métricas clave
  - `GraficoVentas.tsx` — evolución de ventas
  - `TablaTopProductos.tsx` — top productos por venta
  - `AlertasStock.tsx` — alertas de stock crítico
  - `GraficoMargen.tsx` — margen por categoría/período
  - `ChatClaude.tsx` — chat CEO con Claude API
  - `AuthContext.tsx` + `RutaProtegida.tsx` — autenticación
- **Hooks:** `useEjecutivo.ts`, `useCeo.ts`
- **Pendiente:** subir a Vercel + configurar usuarios socios en Supabase Auth

---

## FASE 2 — PLATAFORMA ONLINE Y BOTS SOCIALES

### Estado general: DISEÑO COMPLETO / IMPLEMENTACIÓN PENDIENTE

Los tres documentos de diseño técnico están completos y en el repositorio:

| Documento | Contenido | Estado |
|---|---|---|
| `fase2_tienda_online.md` | Stack, flujo checkout, split MP, panel Mirella, devoluciones | ✅ Diseño completo |
| `fase2_bots.md` | Bots WhatsApp/Instagram/Messenger, Claude NLU, sesiones | ✅ Diseño completo |
| `fase2_plataforma_online.md` | Visión general, arquitectura, decisiones | ✅ Diseño completo |

### Componentes a implementar

#### Tienda online (Next.js 14)
- Migrar `plataforma/` de Vite a Next.js 14 App Router
- Catálogo público, carrito (Zustand), checkout → MP Checkout Pro
- Split automático 92/8 vía MP OAuth marketplace
- Edge Function `crear-preferencia-mp` + webhook MP
- Páginas post-pago: `/pedido/confirmado`, `/pedido/cancelado`
- Código de retiro numérico 6 dígitos
- Emails con Resend (confirmación + recordatorio día 2)

#### Panel Mirella
- Ruta `/panel` con auth Supabase (rol `mirella`)
- Lista pedidos con filtros + búsqueda por código
- Detalle pedido: datos cliente, listado productos, estado
- Confirmar entrega: registra forma de pago real + crea nota de venta en Relbase
- Flujo devoluciones: solicitud Mirella → aprobación CEO

#### Bots sociales (n8n + Claude API)
- Bot WhatsApp vía Twilio
- Bot Instagram DM + Facebook Messenger (Meta Graph API)
- Estado de sesión en tabla `bot_sesiones`
- NLU con Claude API (intención + parámetros + respuesta en JSON)
- Notificación a Mirella vía WhatsApp al registrar pedido

#### Schema Supabase fase 2 (pendiente migración)
- `pedidos_online` — pedidos web + bot
- `bot_sesiones` — estado conversacional bots
- `mp_credentials` — tokens OAuth Mercado Pago (cifrado pgsodium)
- `audit_log` — log de acciones panel Mirella

---

## DECISIONES TOMADAS — SESIÓN 27-28/04/2026

| Decisión | Detalle |
|---|---|
| **Pasarela de pago** | Mercado Pago Checkout Pro. Stripe y Webpay Plus descartados. Confirmado con Marcelo el 27/04/2026. |
| **Split comisión** | 92/8 automático vía MP OAuth marketplace desde venta 1, sin mínimos ni períodos de espera. `marketplace_fee = total_bruto * 0.08`. |
| **Canales de venta** | `presencial` / `online_web` / `online_whatsapp` / `online_instagram` / `online_facebook` — campo `canal` en `ventas` (migración 007). |
| **Política de devoluciones** | 48 horas desde retiro. Solo productos cerrados, sin abrir y en buen estado. Rubros abarrotes y aseo únicamente. |
| **Plazo de retiro** | 3 días hábiles desde pago aprobado. Recordatorio día 2. Cancelación automática día 3. |
| **Relbase para stock** | API Relbase crea notas de venta (tipo 1001) al confirmar entrega, para descontar stock. No emite boletas vía API. |
| **Boleta SII** | MP emite boleta electrónica al SII automáticamente en cada pago aprobado. La tienda no necesita llamar a Relbase para esto. |
| **SPA MP** | Activar SPA (cuenta personal MP del CEO como marketplace) con contador antes de los primeros pagos reales en producción. |

---

## PENDIENTES INMEDIATOS (próxima sesión)

### P1 — CRÍTICO: Resolver n8n sync_incremental_diario

**Problema:** `N8N_BLOCK_ENV_ACCESS_IN_NODE=true` en Railway bloquea `process.env` en nodos Code.

**Opciones a evaluar:**
1. Desactivar `N8N_BLOCK_ENV_ACCESS_IN_NODE` en variables de entorno de Railway.
2. Pasar credenciales como parámetros desde el nodo Schedule Trigger vía expression variables de n8n (sin tocar `process.env`).
3. Usar credenciales nativas n8n (Header Auth) en los nodos httpRequest en vez de variables de entorno.

**Próximo paso:** completar desde nodo 5 (Juntar Ventas) hasta nodo 16 (Notificar error).

---

### P2 — Habilitar RLS en Supabase

- **Bloqueante:** YubiKey en camino (estimado ~5 junio 2026)
- Políticas RLS ya definidas en migración 003
- **Acción pendiente:** cuando llegue YubiKey, configurar 2FA en Supabase y habilitar RLS tabla por tabla
- **Riesgo actual:** operar sin RLS — mitigado usando service_role key solo en backend/n8n

---

### P3 — Subir Dashboard a Vercel

- Dashboard Operativo v1 funcionando en localhost:3002
- **Acción pendiente:**
  1. Configurar `VITE_SUPABASE_URL` y `VITE_SUPABASE_ANON_KEY` en variables de entorno Vercel
  2. Deploy desde rama `main` del repositorio
  3. Configurar dominio (ej. `dashboard.chillanejo.cl` vía Cloudflare)

---

### P4 — Configurar usuarios socios en Supabase Auth

**Usuarios a crear:**
- Marcelo — acceso Dashboard Operativo + Ejecutivo
- Ramón — acceso Dashboard Operativo + Ejecutivo
- Mirella — acceso Dashboard Operativo + (futuro) Panel Mirella

**Acción pendiente:** crear usuarios en Supabase Auth > Users, asignar rol en JWT claims o tabla de perfiles.

---

### P5 — Iniciar implementación Fase 2

Una vez P1 resuelto, siguiente prioridad:
1. Migración schema Supabase fase 2 (008_fase2_schema.sql)
2. OAuth MP: setup app marketplace, flujo autorización El Chillanejo
3. Next.js: migrar plataforma/ de Vite a App Router

---

## STACK TÉCNICO COMPLETO

| Capa | Tecnología |
|---|---|
| ERP operativo | Relbase (fuente de datos, solo lectura) |
| Base analítica | Supabase (PostgreSQL + Edge Functions + Auth) |
| Automatización | n8n (self-hosted en Railway) |
| Análisis | Python (pandas, numpy, scikit-learn, prophet) |
| Frontend dashboards | React + Vite + Tailwind + shadcn/ui + recharts |
| Frontend tienda | Next.js 14 App Router + Tailwind + shadcn/ui + Zustand |
| Pagos | Mercado Pago Checkout Pro + OAuth marketplace (split 92/8) |
| Comunicación | Twilio (WhatsApp) + Resend (email transaccional) |
| IA conversacional | Claude API (bots + Dashboard CEO) |
| Deploy | Vercel (frontend) + Railway (n8n) |
| DNS / Seguridad | Cloudflare |
| Control de versiones | GitHub |
| 2FA hardware | YubiKey (en camino, ~5 jun 2026) |

---

## MODELO COMERCIAL CEO

| Línea | Detalle |
|---|---|
| Honorarios DS | $350.000 CLP/mes fijos |
| Comisión plataforma | 8% ventas online (`marketplace_fee` MP) |
| Gestión importación | 10% sobre valor de importación por ciclo |

**Importación:** NINGBO Y&LNN (China). Programa recurrente aprobado por socios.

---

## SEGURIDAD

| Item | Estado |
|---|---|
| Credenciales en `.env` (excluido de git) | ✅ |
| RLS definido en schema | ✅ (deshabilitado hasta YubiKey) |
| YubiKey para 2FA servicios críticos | 🔶 En camino (~5 jun 2026) |
| Cifrado en reposo (Supabase) | ✅ |
| Backups automáticos Supabase | ✅ |
| Cumplimiento Ley 19.628 (datos Chile) | ✅ por diseño |

---

*Este documento se actualiza al inicio de cada sesión de trabajo.*
