-- =============================================================================
-- 002_dashboard_views.sql — Vistas y funciones para Dashboard Operativo v1
-- =============================================================================
-- Todas las queries que alimentan el dashboard leen de estas vistas.
-- Nunca llaman directamente a tablas de detalle desde el frontend.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Vista: KPIs de ventas para un período arbitrario
-- Usada por las tarjetas Hoy / Semana / Mes
-- ---------------------------------------------------------------------------
create or replace view vw_ventas_periodo as
select
    v.id,
    v.fecha_emision,
    v.tipo_dte,
    v.total_neto,
    v.total_bruto,
    v.estado,
    v.es_anonimo,
    v.cliente_nombre,
    -- semana ISO y mes para agrupaciones rápidas
    date_trunc('week',  v.fecha_emision::timestamptz) as semana_inicio,
    date_trunc('month', v.fecha_emision::timestamptz) as mes_inicio
from ventas v
where v.estado != 'anulado';

comment on view vw_ventas_periodo is
    'Ventas vigentes con campos de agrupación temporal. Base para KPIs del dashboard.';

-- ---------------------------------------------------------------------------
-- Función RPC: kpis_ventas
-- Retorna totales para hoy, semana actual y mes actual en una sola llamada.
-- Frontend: supabase.rpc("kpis_ventas")
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
                'ingresos_netos',  coalesce(sum(total_neto), 0),
                'num_ventas',      count(*)
            )
            from vw_ventas_periodo
            where fecha_emision >= date_trunc('month', current_date - interval '1 month')
              and fecha_emision <  date_trunc('month', current_date)
        )
    );
$$;

-- ---------------------------------------------------------------------------
-- Función RPC: ventas_por_dia
-- Serie temporal diaria para el gráfico de barras del dashboard.
-- Parámetros: p_desde DATE, p_hasta DATE
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
-- Vista: Top productos de la semana actual
-- ---------------------------------------------------------------------------
create or replace view vw_top_productos_semana as
select
    vd.codigo_producto,
    vd.nombre_producto,
    sum(vd.cantidad)        as unidades_vendidas,
    sum(vd.subtotal_neto)   as ingresos_netos,
    sum(vd.margen_neto)     as margen_neto_total,
    count(distinct v.id)    as num_transacciones,
    rank() over (order by sum(vd.subtotal_neto) desc) as rank_ingresos
from ventas_detalle vd
join ventas v on v.id = vd.venta_id
where v.fecha_emision >= date_trunc('week', current_date)
  and v.estado != 'anulado'
  and vd.codigo_producto is not null
group by vd.codigo_producto, vd.nombre_producto
order by ingresos_netos desc;

comment on view vw_top_productos_semana is
    'Top productos por ingresos en la semana actual. Se recalcula en cada consulta.';

-- ---------------------------------------------------------------------------
-- Vista: Top productos del mes actual
-- ---------------------------------------------------------------------------
create or replace view vw_top_productos_mes as
select
    vd.codigo_producto,
    vd.nombre_producto,
    sum(vd.cantidad)        as unidades_vendidas,
    sum(vd.subtotal_neto)   as ingresos_netos,
    sum(vd.margen_neto)     as margen_neto_total,
    count(distinct v.id)    as num_transacciones,
    round(
        case when sum(vd.subtotal_neto) > 0
        then sum(vd.margen_neto) / sum(vd.subtotal_neto) * 100
        else null end,
    1) as margen_pct,
    rank() over (order by sum(vd.subtotal_neto) desc) as rank_ingresos
from ventas_detalle vd
join ventas v on v.id = vd.venta_id
where v.fecha_emision >= date_trunc('month', current_date)
  and v.estado != 'anulado'
  and vd.codigo_producto is not null
group by vd.codigo_producto, vd.nombre_producto
order by ingresos_netos desc;

-- ---------------------------------------------------------------------------
-- Vista: Stock crítico
-- Productos cuya cantidad disponible <= stock_minimo
-- ---------------------------------------------------------------------------
create or replace view vw_stock_critico as
select
    p.producto_id_relbase,
    p.codigo,
    p.nombre,
    p.categoria_nombre,
    p.stock_minimo,
    s.bodega_nombre,
    s.cantidad_disponible,
    s.cantidad_reservada,
    s.fecha_snapshot,
    -- nivel de alerta
    case
        when s.cantidad_disponible <= 0             then 'sin_stock'
        when s.cantidad_disponible <= p.stock_minimo * 0.5 then 'critico'
        else 'bajo'
    end as nivel_alerta
from stock s
join productos p on p.producto_id_relbase = s.producto_id_relbase
where p.es_activo = true
  and p.stock_minimo > 0
  and s.cantidad_disponible <= p.stock_minimo
order by
    case when s.cantidad_disponible <= 0 then 0
         when s.cantidad_disponible <= p.stock_minimo * 0.5 then 1
         else 2 end,
    p.nombre;

comment on view vw_stock_critico is
    'Productos activos cuyo stock disponible está en o por debajo del mínimo definido.';

-- ---------------------------------------------------------------------------
-- Función RPC: resumen_stock_critico
-- Conteo por nivel de alerta para la tarjeta de alertas del dashboard.
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
-- Vista: Ventas por tipo DTE (semana actual)
-- Para mini gráfico de donut en el dashboard
-- ---------------------------------------------------------------------------
create or replace view vw_ventas_tipo_semana as
select
    tipo_dte,
    case tipo_dte
        when 39   then 'Boleta'
        when 33   then 'Factura'
        when 1001 then 'Nota de Venta'
        else 'Otro'
    end                         as tipo_nombre,
    count(*)                    as cantidad,
    sum(total_neto)             as ingresos_netos
from vw_ventas_periodo
where fecha_emision >= date_trunc('week', current_date)
group by tipo_dte
order by ingresos_netos desc;

-- ---------------------------------------------------------------------------
-- Vista: Últimas ventas (tabla en tiempo real del dashboard)
-- ---------------------------------------------------------------------------
create or replace view vw_ultimas_ventas as
select
    v.id,
    v.fecha_emision,
    v.folio,
    case v.tipo_dte
        when 39   then 'Boleta'
        when 33   then 'Factura'
        when 1001 then 'Nota de Venta'
        else v.tipo_dte::text
    end                     as tipo_nombre,
    coalesce(v.cliente_nombre, 'Sin nombre') as cliente,
    v.es_anonimo,
    v.total_neto,
    v.total_bruto,
    v.estado
from ventas v
order by v.fecha_emision desc, v.id desc;

-- ---------------------------------------------------------------------------
-- RPC: enriquecer_costo_unitario_detalle
-- Actualiza costo_unitario en ventas_detalle cruzando con productos.
-- Llamada desde loader.py después de cada carga.
-- ---------------------------------------------------------------------------
create or replace function enriquecer_costo_unitario_detalle()
returns integer
language plpgsql security definer
as $$
declare
    filas_actualizadas integer;
begin
    update ventas_detalle vd
    set
        costo_unitario = p.costo_unitario,
        updated_at     = now()
    from productos p
    where vd.codigo_producto = p.codigo
      and p.costo_unitario is not null
      and vd.costo_unitario is null;

    get diagnostics filas_actualizadas = row_count;
    return filas_actualizadas;
end;
$$;

comment on function enriquecer_costo_unitario_detalle is
    'Rellena costo_unitario nulo en ventas_detalle con el valor de la tabla productos.';

-- ---------------------------------------------------------------------------
-- Grants: rol anon no tiene acceso, solo authenticated y service_role
-- (Las políticas RLS por usuario se definen en 003_rls_policies.sql)
-- ---------------------------------------------------------------------------
revoke all on all tables    in schema public from anon;
revoke all on all functions in schema public from anon;
revoke all on all sequences in schema public from anon;

grant usage  on schema public to authenticated;
grant select on vw_ventas_periodo,
               vw_top_productos_semana,
               vw_top_productos_mes,
               vw_stock_critico,
               vw_ventas_tipo_semana,
               vw_ultimas_ventas
to authenticated;

grant execute on function kpis_ventas()                      to authenticated;
grant execute on function ventas_por_dia(date, date)         to authenticated;
grant execute on function resumen_stock_critico()            to authenticated;
grant execute on function enriquecer_costo_unitario_detalle to service_role;
