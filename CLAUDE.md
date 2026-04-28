# CLAUDE.md — El Chillanejo DS Platform

> Documento de contexto para Claude Code.
> Leer completo antes de escribir cualquier línea de código.
> Última actualización: abril 2026

---

## 1. QUIÉN SOY Y QUÉ ES ESTE PROYECTO

Soy Daniel Droguett R., CEO y Data Scientist del proyecto. No soy socio — soy el ejecutor técnico contratado por los socios Marcelo y Ramón para construir y operar tres proyectos aprobados:

1. **Plataforma digital con carrito** — canal online B2B/B2C para El Chillanejo.
2. **Servicio de Data Science** — dashboards, KPIs, alertas, análisis histórico.
3. **Programa de importación recurrente** — productos desde China (NINGBO Y&LNN).

El Chillanejo es una distribuidora de aseo y abarrotes en Chillán. Vende solo de forma física hoy. Este proyecto abre el canal digital y construye la inteligencia analítica del negocio.

---

## 2. EQUIPO Y ROLES

| Persona | Rol | Acceso |
|---|---|---|
| Daniel Droguett | CEO / Data Scientist (Owner) | Todo |
| Marcelo | Socio (Partner) | Dashboard Operativo + Ejecutivo |
| Ramón | Socio (Partner) | Dashboard Operativo + Ejecutivo |
| Mirella | Administradora operativa | Dashboard Operativo + panel admin operativo |

**Principio:** mínimo privilegio necesario por rol. RLS en Supabase lo hace cumplir.

---

## 3. STACK TÉCNICO

### Datos y backend
- **Relbase** — ERP operativo (fuente de datos). API REST v1. Rate limit: 7 req/seg. Paginación: 12 registros/página.
- **Supabase** — base analítica propia. PostgreSQL con RLS desde día uno.
- **n8n** — motor de automatización y flujos de ingesta.

### Análisis
- **Python** — pandas, numpy, requests, supabase-py
- **ML** — scikit-learn, statsmodels, prophet
- **Visualización exploratoria** — matplotlib, plotly, seaborn

### Frontend
- **React + Tailwind CSS + shadcn/ui + recharts/tremor**

### Pagos
- **Mercado Pago Checkout Pro** — pasarela oficial (reemplaza Stripe, decisión 27/04/2026)
- **Split automático 92/8** (negocio/CEO) vía Mercado Pago OAuth marketplace
- Webpay, débito y transferencia disponibles dentro del checkout de MP

### Comunicación
- **Twilio** — WhatsApp Business API
- **Resend** — correo transaccional

### Infraestructura
- **Vercel** — hosting
- **Cloudflare** — DNS y seguridad
- **GitHub** — repositorio (`danni-droguett-data-scientist/chillanejo`)

### Conversacional
- **Claude API** — exclusivo en Dashboard CEO Personal

### Librería nueva = consultar antes de incorporar. Sin excepciones.

---

## 4. ARQUITECTURA — DATA SOURCE ABSTRACTION LAYER

Sistema en 3 capas. No romper esta separación bajo ninguna circunstancia.

```
Capa 1 — Conectores específicos por fuente
  └── conectores/relbase/     ← primer conector, template reutilizable
  └── conectores/<futuro>/    ← Contabilium, Defontana, Excel, etc.

Capa 2 — Formato estándar Supabase (tablas universales)
  └── ventas, ventas_detalle, productos, clientes
  └── stock, stock_historico, compras, compras_detalle
  └── proveedores, bodegas, categorias, sync_log

Capa 3 — Análisis, dashboards, alertas, agentes
  └── Operan sobre Capa 2. Agnósticos de la fuente.
```

**Regla crítica:** la Capa 3 nunca llama directamente a Relbase. Solo lee Supabase.

---

## 5. ESTRUCTURA DEL REPOSITORIO

```
chillanejo/
├── CLAUDE.md                   ← este archivo
├── conectores/
│   └── relbase/                ← conector Relbase (template)
│       ├── client.py           ← autenticación y llamadas base
│       ├── extractor.py        ← extracción por entidad
│       ├── transformer.py      ← mapeo al formato estándar Supabase
│       └── loader.py           ← carga a Supabase con upsert
├── n8n_flows/                  ← exports JSON de flujos n8n
├── python/
│   ├── analysis/               ← notebooks y scripts de análisis
│   └── models/                 ← modelos ML (Prophet, sklearn)
├── supabase/
│   └── migrations/             ← SQL de schema y RLS
├── plataforma/                 ← frontend tienda online
├── dashboard/                  ← frontend dashboards
├── bot/                        ← bot WhatsApp y RRSS
└── docs/                       ← documentación técnica
```

---

## 6. SCHEMA SUPABASE — TABLAS PRINCIPALES

16 tablas en total. Las más críticas para el conector inicial:

- `ventas` — DTEs: boletas (39), facturas (33), notas de venta (1001)
- `ventas_detalle` — líneas de productos. Tiene `margen_neto` calculado automáticamente.
- `productos` — catálogo con `costo_unitario` y `precio_neto`
- `clientes` — B2B y B2C. Campo `es_anonimo` para boletas sin identificar.
- `stock` — snapshot actual por producto/bodega (upsert en cada sync)
- `stock_historico` — snapshots anteriores para análisis de tendencia
- `bodegas` — 2 bodegas: Principal y Punto de Venta
- `sync_log` — control de ingesta incremental por entidad
- `proveedores` — tabla propia Supabase (Relbase no la entrega bien)

Tablas CEO (solo Owner):
- `honorarios_ds` — ingresos mensuales DS
- `ingresos_importacion` — honorarios por ciclo
- `costos_stack` — costos mensuales del stack
- `pipeline_clientes` — futuros clientes DS

---

## 7. AUTENTICACIÓN RELBASE

Dos headers obligatorios en cada llamada:
```python
headers = {
    "Authorization": "<TOKEN_USUARIO>",   # token usuario integrador
    "Company": "<TOKEN_EMPRESA>"          # token empresa (entregado por Relbase)
}
```

**Credenciales NUNCA en código ni en GitHub.** Usar variables de entorno desde `.env` (excluido en `.gitignore`).

Rate limit: máximo 7 req/seg. El conector debe incluir `time.sleep(0.15)` entre llamadas en bulk.

---

## 8. ENDPOINTS RELBASE PRIORITARIOS

| Entidad | Endpoint | Notas |
|---|---|---|
| Ventas (DTEs) | `GET /api/v1/dtes` | Tipos: 33, 39, 1001 |
| Productos | `GET /api/v1/productos` | Incluye costo_unitario |
| Stock por bodega | `GET /api/v1/productos/{id}/stock_por_bodegas` | Por producto |
| Clientes | `GET /api/v1/clientes` | B2B y B2C |
| Compras | `GET /api/v1/compras` | Pendiente confirmar detalle líneas |
| Bodegas | `GET /api/v1/bodegas` | Seed inicial |

Paginación: parámetro `?page=N`. Verificar `meta.next_page` para continuar.

---

## 9. TRES DASHBOARDS

### Dashboard 1 — Operativo El Chillanejo
- Usuarios: Marcelo, Ramón, Mirella
- Frecuencia: consulta diaria
- Métricas: ventas hoy/semana/mes, stock crítico, alertas, top productos

### Dashboard 2 — Ejecutivo El Chillanejo
- Usuarios: Marcelo, Ramón, Daniel
- Frecuencia: quincenal (reuniones)
- Métricas: evolución, márgenes, impacto decisiones, comparativos

### Dashboard 3 — Ejecutivo Personal CEO
- Usuario: solo Daniel
- Métricas: ingresos por 3 líneas, costos stack, rentabilidad propia, pipeline clientes
- Incluye: integración Claude API conversacional exclusiva

**Orden de construcción:** Operativo → Ejecutivo Chillanejo → Ejecutivo CEO

---

## 10. MODELO COMERCIAL CEO

Tres líneas de ingreso:

1. **Honorarios DS:** $350.000 CLP/mes fijos
2. **Comisión plataforma:** 8% sobre ventas online pagadas online (Stripe Connect split 92/8)
3. **Gestión importación:** 10% sobre valor de importación por ciclo

Costos stack arranque: ~USD 9-40/mes. Operación estable: ~USD 70-150/mes.

---

## 11. SEGURIDAD — PRINCIPIOS NO NEGOCIABLES

1. **Credenciales nunca en código ni en GitHub.** Siempre variables de entorno.
2. **RLS habilitado** en todas las tablas Supabase desde día uno.
3. **Mínimo privilegio** por rol en cada operación.
4. **Cifrado** en reposo y en tránsito.
5. **Logs de auditoría** en operaciones críticas.
6. **Backups** automáticos diarios Supabase + backup manual semanal.
7. **YubiKey** en servicios críticos (llega ~5 junio 2026).
8. Cumplimiento **Ley 19.628** (protección datos Chile).

---

## 12. REGLAS DE TRABAJO

- **Escalabilidad multi-cliente:** el sistema es de lógica de negocio, no de rubro. El 80-90% debe ser reutilizable para futuros clientes.
- **Conector Relbase es el template:** cualquier conector futuro replica su estructura.
- **Sin dependencias nuevas sin consultar** a Daniel primero.
- **Comentarios en español** en todo el código.
- **Commits semánticos:** `feat:`, `fix:`, `refactor:`, `docs:`, `chore:`
- **Sin datos reales en tests.** Usar datos sintéticos o sandbox.
- **El conector nunca modifica datos en Relbase.** Solo lectura.

---

## 13. ORDEN DE CONSTRUCCIÓN (FASE 1)

1. `conectores/relbase/client.py` — autenticación y llamada base
2. `conectores/relbase/extractor.py` — extracción paginada por entidad
3. `conectores/relbase/transformer.py` — mapeo al schema Supabase
4. `conectores/relbase/loader.py` — upsert a Supabase
5. Carga histórica 18 meses (DTEs + productos + clientes + stock)
6. Análisis exploratorio → top 50-100 productos
7. Dashboard Operativo v1

---

*Este documento se actualiza al inicio de cada fase nueva del proyecto.*
