-- =============================================================================
-- 007_add_canal_ventas.sql
-- Agrega columna canal a ventas e índice; reconstruye vw_ventas_periodo con canal.
-- =============================================================================

alter table ventas
  add column if not exists canal text not null default 'presencial'
  check (canal in (
    'presencial',
    'online_web',
    'online_whatsapp',
    'online_instagram',
    'online_facebook'
  ));

comment on column ventas.canal is
  'Canal de venta: presencial (tienda física) u online por plataforma/bot';

create index if not exists idx_ventas_canal on ventas(canal);

-- Reconstruir vw_ventas_periodo para exponer canal
-- (todas las vistas y RPCs de 002_dashboard_views dependen de esta vista base)
create or replace view vw_ventas_periodo as
select
    v.id,
    v.fecha_emision,
    v.tipo_documento,
    v.neto                                              as total_neto,
    v.total                                             as total_bruto,
    v.estado_sii,
    v.canal,
    coalesce(c.es_anonimo, false)                       as es_anonimo,
    coalesce(c.nombre, v.vendedor, 'Sin nombre')        as cliente_nombre,
    date_trunc('week',  v.fecha_emision::timestamptz)   as semana_inicio,
    date_trunc('month', v.fecha_emision::timestamptz)   as mes_inicio
from ventas v
left join clientes c on c.id = v.cliente_id;

comment on view vw_ventas_periodo is
    'Ventas con canal, agrupación temporal y datos de cliente. Base para KPIs.';

-- Re-grant (necesario al recrear la vista)
grant select on vw_ventas_periodo to authenticated;
