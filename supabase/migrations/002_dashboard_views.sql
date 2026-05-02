-- =============================================================================
-- 002_dashboard_views.sql — Vistas y funciones para Dashboard Operativo v1
-- =============================================================================
-- Schema real (verificado contra transformer.py y PostgREST):
--   ventas:        relbase_id, tipo_documento, folio, estado_sii,
--                  fecha_emision, fecha_vencimiento,
--                  cliente_id (uuid FK), bodega_id (uuid FK),
--                  neto, iva, total, vendedor
--   ventas_detalle: venta_id (uuid FK), producto_id (uuid FK),
--                  relbase_producto_id, nombre_producto, sku,
--                  cantidad, precio_unitario, costo_unitario,
--                  descuento_pct, afecto_iva, total_neto
--   productos:     relbase_id, sku, nombre, descripcion,
--                  precio_neto, costo_unitario, activo
--   clientes:      relbase_id, rut, nombre, es_anonimo, activo
--   bodegas:       relbase_id, nombre, activa
--   stock:         producto_id (uuid FK), bodega_id (uuid FK), cantidad
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Vista base: ventas vigentes con campos de agrupación temporal
-- ---------------------------------------------------------------------------
create or replace view vw_ventas_periodo as
select
    v.id,
    v.fecha_emision,
    v.tipo_documento,
    v.neto                                              as total_neto,
    v.total                                             as total_bruto,
    v.estado_sii,
    coalesce(c.es_anonimo, false)                       as es_anonimo,
    coalesce(c.nombre, v.vendedor, 'Sin nombre')        as cliente_nombre,
    date_trunc('week',  v.fecha_emision::timestamptz)   as semana_inicio,
    date_trunc('month', v.fecha_emision::timestamptz)   as mes_inicio
from ventas v
left join clientes c on c.id = v.cliente_id;

comment on view vw_ventas_periodo is
    'Ventas con campos de agrupación temporal y datos de cliente. Base para KPIs.';

-- ---------------------------------------------------------------------------
-- RPC: kpis_ventas — totales hoy / semana / mes / mes anterior
-- ---------------------------------------------------------------------------
create or replace function kpis_ventas()
returns json
language sql stable security definer
as $$
    select json_build_object(
        'hoy', (
            select json_build_object(
                'ingresos_netos',  coalesce(sum(total_neto), 0),
                'ingresos_brutos', coalesce(sum(total_bruto), 0),
                'num_ventas',      count(*),
                'ticket_promedio', coalesce(avg(total_neto), 0)
            )
            from vw_ventas_periodo
            where fecha_emision = current_date
        ),
        'semana', (
            select json_build_object(
                'ingresos_netos',  coalesce(sum(total_neto), 0),
                'ingresos_brutos', coalesce(sum(total_bruto), 0),
                'num_ventas',      count(*),
                'ticket_promedio', coalesce(avg(total_neto), 0)
            )
            from vw_ventas_periodo
            where fecha_emision >= date_trunc('week', current_date)
        ),
        'mes', (
            select json_build_object(
                'ingresos_netos',  coalesce(sum(total_neto), 0),
                'ingresos_brutos', coalesce(sum(total_bruto), 0),
                'num_ventas',      count(*),
                'ticket_promedio', coalesce(avg(total_neto), 0)
            )
            from vw_ventas_periodo
            where fecha_emision >= date_trunc('month', current_date)
        ),
        'mes_anterior', (
            select json_build_object(
                'ingresos_netos', coalesce(sum(total_neto), 0),
                'num_ventas',     count(*)
            )
            from vw_ventas_periodo
            where fecha_emision >= date_trunc('month', current_date - interval '1 month')
              and fecha_emision <  date_trunc('month', current_date)
        )
    );
$$;

-- ---------------------------------------------------------------------------
-- RPC: ventas_por_dia — serie temporal para gráfico de barras
-- ---------------------------------------------------------------------------
create or replace function ventas_por_dia(p_desde date, p_hasta date)
returns table (
    fecha           date,
    ingresos_netos  numeric,
    num_ventas      bigint
)
language sql stable security definer
as $$
    select
        fecha_emision                  as fecha,
        coalesce(sum(total_neto), 0)   as ingresos_netos,
        count(*)                       as num_ventas
    from vw_ventas_periodo
    where fecha_emision between p_desde and p_hasta
    group by fecha_emision
    order by fecha_emision;
$$;

-- ---------------------------------------------------------------------------
-- Vista: top productos del mes actual
-- codigo_producto = sku (o relbase_id como fallback)
-- margen_neto     = total_neto - (costo_unitario × cantidad)
-- ---------------------------------------------------------------------------
create or replace view vw_top_productos_mes as
select
    coalesce(vd.sku, vd.relbase_producto_id::text)  as codigo_producto,
    vd.nombre_producto,
    sum(vd.cantidad)                                as unidades_vendidas,
    sum(vd.total_neto)                              as ingresos_netos,
    sum(
        case when vd.costo_unitario is not null and vd.cantidad is not null
        then vd.total_neto - (vd.costo_unitario * vd.cantidad)
        else null end
    )                                               as margen_neto_total,
    count(distinct v.id)                            as num_transacciones,
    round(
        case when sum(vd.total_neto) > 0
        then sum(
            case when vd.costo_unitario is not null and vd.cantidad is not null
            then vd.total_neto - (vd.costo_unitario * vd.cantidad)
            else null end
        ) / nullif(sum(vd.total_neto), 0) * 100
        else null end,
    1)                                              as margen_pct,
    rank() over (order by sum(vd.total_neto) desc)  as rank_ingresos
from ventas_detalle vd
join ventas v on v.id = vd.venta_id
where v.fecha_emision >= date_trunc('month', current_date)
  and vd.relbase_producto_id is not null
group by vd.relbase_producto_id, vd.sku, vd.nombre_producto
order by ingresos_netos desc;

comment on view vw_top_productos_mes is
    'Top productos por ingresos en el mes actual. Margen calculado en tiempo real.';

-- ---------------------------------------------------------------------------
-- Vista: top productos de la semana (para referencia futura)
-- ---------------------------------------------------------------------------
create or replace view vw_top_productos_semana as
select
    coalesce(vd.sku, vd.relbase_producto_id::text)  as codigo_producto,
    vd.nombre_producto,
    sum(vd.cantidad)                                as unidades_vendidas,
    sum(vd.total_neto)                              as ingresos_netos,
    count(distinct v.id)                            as num_transacciones,
    rank() over (order by sum(vd.total_neto) desc)  as rank_ingresos
from ventas_detalle vd
join ventas v on v.id = vd.venta_id
where v.fecha_emision >= date_trunc('week', current_date)
  and vd.relbase_producto_id is not null
group by vd.relbase_producto_id, vd.sku, vd.nombre_producto
order by ingresos_netos desc;

-- ---------------------------------------------------------------------------
-- Vista: stock crítico
-- Sin stock_minimo configurado por producto, usa umbrales fijos:
--   sin_stock : cantidad <= 0
--   critico   : cantidad entre 1 y 5
--   bajo      : cantidad entre 6 y 20
-- Ajustar umbrales según operación real del negocio.
-- ---------------------------------------------------------------------------
create or replace view vw_stock_critico as
select
    p.relbase_id                as producto_id_relbase,
    p.sku                       as codigo,
    p.nombre,
    null::text                  as categoria_nombre,
    1                           as stock_minimo,
    b.nombre                    as bodega_nombre,
    s.cantidad                  as cantidad_disponible,
    case
        when s.cantidad <= 0  then 'sin_stock'
        when s.cantidad <= 5  then 'critico'
        else                       'bajo'
    end                         as nivel_alerta
from stock s
join productos p on p.id = s.producto_id
join bodegas   b on b.id = s.bodega_id
where p.activo = true
  and s.cantidad <= 20
order by
    case when s.cantidad <= 0 then 0
         when s.cantidad <= 5 then 1
         else 2 end,
    p.nombre;

comment on view vw_stock_critico is
    'Productos activos con stock bajo. Umbrales: 0=sin_stock, 1-5=critico, 6-20=bajo.';

-- ---------------------------------------------------------------------------
-- RPC: resumen_stock_critico — conteo por nivel para tarjeta KPI
-- ---------------------------------------------------------------------------
create or replace function resumen_stock_critico()
returns json
language sql stable security definer
as $$
    select json_build_object(
        'sin_stock', count(*) filter (where nivel_alerta = 'sin_stock'),
        'critico',   count(*) filter (where nivel_alerta = 'critico'),
        'bajo',      count(*) filter (where nivel_alerta = 'bajo'),
        'total',     count(*)
    )
    from vw_stock_critico;
$$;

-- ---------------------------------------------------------------------------
-- Vista: ventas por tipo (semana actual) — para donut futuro
-- ---------------------------------------------------------------------------
create or replace view vw_ventas_tipo_semana as
select
    tipo_documento,
    case tipo_documento
        when 39   then 'Boleta'
        when 33   then 'Factura'
        when 1001 then 'Nota de Venta'
        else tipo_documento::text
    end             as tipo_nombre,
    count(*)        as cantidad,
    sum(total_neto) as ingresos_netos
from vw_ventas_periodo
where fecha_emision >= date_trunc('week', current_date)
group by tipo_documento
order by ingresos_netos desc;

-- ---------------------------------------------------------------------------
-- Vista: últimas ventas (tabla en tiempo real)
-- ---------------------------------------------------------------------------
create or replace view vw_ultimas_ventas as
select
    v.id,
    v.fecha_emision,
    v.folio,
    case v.tipo_documento
        when 39   then 'Boleta'
        when 33   then 'Factura'
        when 1001 then 'Nota de Venta'
        else v.tipo_documento::text
    end                                         as tipo_nombre,
    coalesce(c.nombre, v.vendedor, 'Sin nombre') as cliente,
    coalesce(c.es_anonimo, false)               as es_anonimo,
    v.neto                                      as total_neto,
    v.total                                     as total_bruto,
    v.estado_sii                                as estado
from ventas v
left join clientes c on c.id = v.cliente_id
order by v.fecha_emision desc, v.id desc;

comment on view vw_ultimas_ventas is
    'Últimas ventas con datos del cliente para tabla en tiempo real del dashboard.';

-- ---------------------------------------------------------------------------
-- RPC: enriquecer_costo_unitario_detalle
-- Rellena costo_unitario nulo en ventas_detalle cruzando con productos.
-- ---------------------------------------------------------------------------
create or replace function enriquecer_costo_unitario_detalle()
returns integer
language plpgsql security definer
as $$
declare
    filas_actualizadas integer;
begin
    update ventas_detalle vd
    set costo_unitario = p.costo_unitario
    from productos p
    where vd.relbase_producto_id = p.relbase_id
      and p.costo_unitario is not null
      and vd.costo_unitario is null;

    get diagnostics filas_actualizadas = row_count;
    return filas_actualizadas;
end;
$$;

comment on function enriquecer_costo_unitario_detalle is
    'Rellena costo_unitario nulo en ventas_detalle con el valor de productos.';

-- ---------------------------------------------------------------------------
-- Grants: acceso mínimo — solo authenticated, ningún acceso anon
-- ---------------------------------------------------------------------------
revoke all on all tables    in schema public from anon;
revoke all on all functions in schema public from anon;
revoke all on all sequences in schema public from anon;

grant usage  on schema public to authenticated;

grant select on
    vw_ventas_periodo,
    vw_top_productos_mes,
    vw_top_productos_semana,
    vw_stock_critico,
    vw_ventas_tipo_semana,
    vw_ultimas_ventas
to authenticated;

grant execute on function kpis_ventas()                      to authenticated;
grant execute on function ventas_por_dia(date, date)         to authenticated;
grant execute on function resumen_stock_critico()            to authenticated;
grant execute on function enriquecer_costo_unitario_detalle  to service_role;
