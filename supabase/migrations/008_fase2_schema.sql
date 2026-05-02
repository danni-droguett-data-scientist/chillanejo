-- =============================================================================
-- Migración 008 — Fase 2: Tienda Online
-- Fecha: 2026-05-02
-- Descripción: Schema completo para la tienda online — pedidos, credenciales
--              Mercado Pago, log de auditoría, función de código de retiro y RLS.
-- =============================================================================


-- =============================================================================
-- 1. TABLA: pedidos_online
-- =============================================================================

create table pedidos_online (
  id                      uuid primary key default uuid_generate_v4(),

  -- Origen del pedido
  origen                  text not null default 'tienda_web',  -- 'tienda_web' | 'bot' | 'whatsapp' | 'instagram' | 'messenger'
  canal_sender_id         text,                                 -- solo para pedidos originados en bot

  -- Cliente
  nombre_cliente          text not null,
  rut_cliente             text,
  email_cliente           text,
  telefono_cliente        text,

  -- Productos y montos
  items_json              jsonb not null,
  total_neto              numeric(14,2) not null,
  total_bruto             numeric(14,2) not null,
  codigo_retiro           text not null unique,

  -- Pago Mercado Pago
  mp_preference_id        text,
  mp_payment_id           text,
  mp_status               text,
  forma_pago_real         text,     -- registrado por Mirella al confirmar entrega
  forma_pago_detalle      jsonb,    -- ej: { "debito": 3000, "efectivo": 2000 }

  -- Estado del pedido
  -- Valores válidos: pendiente_pago | pagado | entregado | cancelado_sin_retiro
  --                  cancelado_manual | pago_fallido | devolucion_solicitada | devuelto
  estado                  text not null default 'pendiente_pago',

  -- Timestamps de ciclo de vida
  fecha_pedido            timestamptz not null default now(),
  fecha_limite_retiro     date,
  pagado_at               timestamptz,
  entregado_at            timestamptz,
  cancelado_at            timestamptz,

  -- Integración Relbase
  relbase_nota_venta_id   integer,  -- ID del DTE creado en Relbase al confirmar entrega

  -- Devolución
  devolucion_estado       text,
  devolucion_items_json   jsonb,
  devolucion_motivo       text,
  devolucion_aprobada_at  timestamptz,
  devolucion_metodo       text,

  -- Auditoría
  created_at              timestamptz not null default now(),
  updated_at              timestamptz not null default now()
);

create index if not exists idx_pedidos_codigo     on pedidos_online(codigo_retiro);
create index if not exists idx_pedidos_estado     on pedidos_online(estado);
create index if not exists idx_pedidos_fecha      on pedidos_online(fecha_pedido);
create index if not exists idx_pedidos_mp_payment on pedidos_online(mp_payment_id);


-- =============================================================================
-- 2. TABLA: mp_credentials
-- Almacena tokens OAuth de Mercado Pago. Solo accesible por service_role.
-- access_token cifrado con pgsodium (extensión nativa de Supabase).
-- =============================================================================

create table mp_credentials (
  id            uuid primary key default uuid_generate_v4(),
  cuenta        text not null unique,   -- 'chillanejo' | 'ceo'
  access_token  text not null,          -- cifrado con pgsodium
  refresh_token text,
  expires_at    timestamptz,
  updated_at    timestamptz not null default now()
);

-- Sin RLS pública — solo service_role puede acceder.
alter table mp_credentials enable row level security;


-- =============================================================================
-- 3. TABLA: audit_log
-- Registro inmutable de acciones críticas sobre pedidos.
-- =============================================================================

create table audit_log (
  id          bigserial primary key,
  tabla       text not null,
  registro_id uuid not null,
  accion      text not null,   -- 'confirmar_entrega' | 'cancelar' | 'devolucion_aprobar' | ...
  actor       text not null,   -- 'mirella' | 'ceo' | 'sistema' | 'bot'
  detalle     jsonb,
  created_at  timestamptz not null default now()
);


-- =============================================================================
-- 4. FUNCIÓN: generar_codigo_retiro()
-- Genera un código numérico de 6 dígitos único dentro del día actual.
-- Se llama desde la Edge Function al crear una preferencia MP.
-- =============================================================================

create or replace function generar_codigo_retiro()
returns text
language plpgsql
as $$
declare
  codigo  text;
  existe  boolean;
  hoy     date := current_date;
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


-- =============================================================================
-- 5. RLS: pedidos_online
-- Mirella puede leer todos los pedidos y actualizar solo hacia estados
-- permitidos por su rol (entregado, devolucion_solicitada).
-- Los cambios de estado mayores (cancelar, aprobar devolución) son exclusivos
-- de service_role (Edge Functions / n8n).
-- =============================================================================

alter table pedidos_online enable row level security;

create policy "mirella_lee_pedidos"
  on pedidos_online
  for select
  using (auth.jwt() ->> 'role' = 'mirella');

create policy "mirella_actualiza_pedidos"
  on pedidos_online
  for update
  using (auth.jwt() ->> 'role' = 'mirella')
  with check (estado in ('entregado', 'devolucion_solicitada'));
