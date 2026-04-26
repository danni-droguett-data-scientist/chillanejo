-- =============================================================================
-- 001_schema_base.sql — Schema principal El Chillanejo DS Platform
-- =============================================================================
-- Crea las 16 tablas con RLS habilitado desde el primer día.
-- Ejecutar una sola vez sobre el proyecto Supabase vacío.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Extensiones
-- ---------------------------------------------------------------------------
create extension if not exists "uuid-ossp";
create extension if not exists "pg_stat_statements";

-- ---------------------------------------------------------------------------
-- Bodegas
-- ---------------------------------------------------------------------------
create table if not exists bodegas (
    id                  uuid primary key default uuid_generate_v4(),
    bodega_id_relbase   integer unique not null,
    nombre              text not null,
    direccion           text,
    es_activa           boolean not null default true,
    fuente              text not null default 'relbase',
    created_at          timestamptz not null default now(),
    updated_at          timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- Categorías
-- ---------------------------------------------------------------------------
create table if not exists categorias (
    id                      uuid primary key default uuid_generate_v4(),
    categoria_id_relbase    integer unique,
    nombre                  text not null,
    fuente                  text not null default 'relbase',
    created_at              timestamptz not null default now(),
    updated_at              timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- Productos
-- ---------------------------------------------------------------------------
create table if not exists productos (
    id                      uuid primary key default uuid_generate_v4(),
    producto_id_relbase     integer unique not null,
    codigo                  text,
    nombre                  text not null,
    descripcion             text,
    precio_neto             numeric(14,2),
    precio_bruto            numeric(14,2),
    costo_unitario          numeric(14,2),
    categoria_id_relbase    integer references categorias(categoria_id_relbase),
    categoria_nombre        text,
    unidad_medida           text,
    es_activo               boolean not null default true,
    stock_minimo            numeric(14,4) default 0,
    fuente                  text not null default 'relbase',
    created_at              timestamptz not null default now(),
    updated_at              timestamptz not null default now()
);

create index if not exists idx_productos_codigo on productos(codigo);
create index if not exists idx_productos_activo on productos(es_activo);

-- ---------------------------------------------------------------------------
-- Clientes
-- ---------------------------------------------------------------------------
create table if not exists clientes (
    id                      uuid primary key default uuid_generate_v4(),
    cliente_id_relbase      integer unique not null,
    rut                     text,
    nombre                  text,
    email                   text,
    telefono                text,
    direccion               text,
    ciudad                  text,
    region                  text,
    tipo_cliente            text,
    giro                    text,
    es_anonimo              boolean not null default false,
    es_activo               boolean not null default true,
    fuente                  text not null default 'relbase',
    created_at              timestamptz not null default now(),
    updated_at              timestamptz not null default now()
);

create index if not exists idx_clientes_rut on clientes(rut);

-- ---------------------------------------------------------------------------
-- Ventas (DTEs)
-- ---------------------------------------------------------------------------
create table if not exists ventas (
    id                      uuid primary key default uuid_generate_v4(),
    dte_id_relbase          integer unique not null,
    tipo_dte                integer not null,          -- 33, 39, 1001
    folio                   text,
    fecha_emision           date not null,
    fecha_vencimiento       date,
    cliente_id_relbase      integer,
    cliente_rut             text,
    cliente_nombre          text,
    cliente_email           text,
    es_anonimo              boolean not null default false,
    total_neto              numeric(14,2),
    total_iva               numeric(14,2),
    total_bruto             numeric(14,2),
    total_exento            numeric(14,2),
    bodega_id_relbase       integer references bodegas(bodega_id_relbase),
    vendedor_nombre         text,
    estado                  text not null default 'emitido',
    observaciones           text,
    fuente                  text not null default 'relbase',
    created_at              timestamptz not null default now(),
    updated_at              timestamptz not null default now()
);

create index if not exists idx_ventas_fecha    on ventas(fecha_emision);
create index if not exists idx_ventas_tipo_dte on ventas(tipo_dte);
create index if not exists idx_ventas_estado   on ventas(estado);
create index if not exists idx_ventas_cliente  on ventas(cliente_id_relbase);

-- ---------------------------------------------------------------------------
-- Ventas detalle
-- ---------------------------------------------------------------------------
create table if not exists ventas_detalle (
    id                      uuid primary key default uuid_generate_v4(),
    venta_id                uuid references ventas(id) on delete cascade,
    dte_id_relbase          integer not null,
    numero_linea            integer,
    codigo_producto         text,
    nombre_producto         text,
    cantidad                numeric(14,4),
    precio_unitario_neto    numeric(14,2),
    precio_unitario_bruto   numeric(14,2),
    descuento_porcentaje    numeric(6,2) default 0,
    descuento_monto         numeric(14,2) default 0,
    subtotal_neto           numeric(14,2),
    subtotal_bruto          numeric(14,2),
    iva_porcentaje          numeric(6,2),
    iva_monto               numeric(14,2),
    costo_unitario          numeric(14,2),
    -- margen_neto calculado automáticamente
    margen_neto             numeric(14,2) generated always as (
                                case
                                    when costo_unitario is not null and cantidad is not null
                                    then subtotal_neto - (costo_unitario * cantidad)
                                    else null
                                end
                            ) stored,
    fuente                  text not null default 'relbase',
    created_at              timestamptz not null default now(),
    updated_at              timestamptz not null default now(),
    unique (dte_id_relbase, numero_linea)
);

create index if not exists idx_detalle_dte      on ventas_detalle(dte_id_relbase);
create index if not exists idx_detalle_venta_id on ventas_detalle(venta_id);
create index if not exists idx_detalle_codigo   on ventas_detalle(codigo_producto);

-- ---------------------------------------------------------------------------
-- Stock (snapshot actual)
-- ---------------------------------------------------------------------------
create table if not exists stock (
    id                      uuid primary key default uuid_generate_v4(),
    producto_id_relbase     integer not null references productos(producto_id_relbase),
    bodega_id_relbase       integer not null references bodegas(bodega_id_relbase),
    bodega_nombre           text,
    cantidad                numeric(14,4) not null default 0,
    cantidad_reservada      numeric(14,4) not null default 0,
    cantidad_disponible     numeric(14,4) not null default 0,
    fecha_snapshot          timestamptz not null default now(),
    fuente                  text not null default 'relbase',
    created_at              timestamptz not null default now(),
    updated_at              timestamptz not null default now(),
    unique (producto_id_relbase, bodega_id_relbase)
);

create index if not exists idx_stock_producto on stock(producto_id_relbase);

-- ---------------------------------------------------------------------------
-- Stock histórico
-- ---------------------------------------------------------------------------
create table if not exists stock_historico (
    id                      uuid primary key default uuid_generate_v4(),
    producto_id_relbase     integer not null,
    bodega_id_relbase       integer not null,
    bodega_nombre           text,
    cantidad                numeric(14,4),
    cantidad_reservada      numeric(14,4),
    cantidad_disponible     numeric(14,4),
    fecha_snapshot          timestamptz not null default now(),
    fuente                  text not null default 'relbase',
    created_at              timestamptz not null default now(),
    updated_at              timestamptz not null default now(),
    unique (producto_id_relbase, bodega_id_relbase, fecha_snapshot)
);

create index if not exists idx_stock_hist_fecha    on stock_historico(fecha_snapshot);
create index if not exists idx_stock_hist_producto on stock_historico(producto_id_relbase);

-- ---------------------------------------------------------------------------
-- Proveedores (tabla propia — Relbase no la entrega bien)
-- ---------------------------------------------------------------------------
create table if not exists proveedores (
    id          uuid primary key default uuid_generate_v4(),
    rut         text unique,
    nombre      text not null,
    email       text,
    telefono    text,
    pais        text default 'Chile',
    notas       text,
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- Compras
-- ---------------------------------------------------------------------------
create table if not exists compras (
    id                  uuid primary key default uuid_generate_v4(),
    compra_id_relbase   integer unique,
    proveedor_id        uuid references proveedores(id),
    fecha_emision       date,
    fecha_recepcion     date,
    total_neto          numeric(14,2),
    total_iva           numeric(14,2),
    total_bruto         numeric(14,2),
    estado              text,
    fuente              text default 'relbase',
    created_at          timestamptz not null default now(),
    updated_at          timestamptz not null default now()
);

create table if not exists compras_detalle (
    id                  uuid primary key default uuid_generate_v4(),
    compra_id           uuid references compras(id) on delete cascade,
    numero_linea        integer,
    codigo_producto     text,
    nombre_producto     text,
    cantidad            numeric(14,4),
    precio_unitario     numeric(14,2),
    subtotal_neto       numeric(14,2),
    fuente              text default 'relbase',
    created_at          timestamptz not null default now(),
    updated_at          timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- Sync log
-- ---------------------------------------------------------------------------
create table if not exists sync_log (
    id                      uuid primary key default uuid_generate_v4(),
    entidad                 text unique not null,
    ultimo_sync             timestamptz,
    registros_procesados    integer default 0,
    registros_cargados      integer default 0,
    errores                 integer default 0,
    ultimo_id_procesado     integer,
    created_at              timestamptz not null default now(),
    updated_at              timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- Tablas CEO (solo Owner — RLS restringe acceso)
-- ---------------------------------------------------------------------------
create table if not exists honorarios_ds (
    id              uuid primary key default uuid_generate_v4(),
    mes             date not null unique,    -- primer día del mes
    monto_clp       numeric(14,0) not null,
    pagado          boolean not null default false,
    fecha_pago      date,
    notas           text,
    created_at      timestamptz not null default now()
);

create table if not exists ingresos_importacion (
    id                  uuid primary key default uuid_generate_v4(),
    ciclo               text not null,       -- ej. "2026-Q1"
    valor_importacion   numeric(14,2),
    honorarios          numeric(14,2),       -- 10% del valor
    pagado              boolean not null default false,
    fecha_pago          date,
    notas               text,
    created_at          timestamptz not null default now()
);

create table if not exists costos_stack (
    id              uuid primary key default uuid_generate_v4(),
    mes             date not null,
    servicio        text not null,
    monto_usd       numeric(10,2),
    monto_clp       numeric(14,0),
    categoria        text,
    created_at      timestamptz not null default now(),
    unique (mes, servicio)
);

create table if not exists pipeline_clientes (
    id              uuid primary key default uuid_generate_v4(),
    empresa         text not null,
    contacto        text,
    email           text,
    etapa           text not null default 'prospecto',  -- prospecto, propuesta, negociacion, cerrado
    valor_estimado  numeric(14,0),
    notas           text,
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- RLS: habilitar en todas las tablas
-- ---------------------------------------------------------------------------
do $$
declare
    t text;
begin
    foreach t in array array[
        'bodegas','categorias','productos','clientes',
        'ventas','ventas_detalle','stock','stock_historico',
        'proveedores','compras','compras_detalle','sync_log',
        'honorarios_ds','ingresos_importacion','costos_stack','pipeline_clientes'
    ]
    loop
        execute format('alter table %I enable row level security', t);
    end loop;
end;
$$;

-- Política base: el service_role (conector) bypasea RLS por defecto en Supabase.
-- Las políticas por rol se agregan en 002_rls_policies.sql (siguiente migración).

comment on table ventas         is 'DTEs emitidos: boletas (39), facturas (33), notas de venta (1001)';
comment on table ventas_detalle is 'Líneas de producto por DTE. margen_neto es columna generada.';
comment on table stock          is 'Snapshot actual de stock por producto y bodega.';
comment on table sync_log       is 'Control de sincronización incremental por entidad Relbase.';
