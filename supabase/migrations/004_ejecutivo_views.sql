-- =============================================================================
-- 004_ejecutivo_views.sql — Vistas y funciones para Dashboard Ejecutivo
-- =============================================================================
-- Usuarios: Marcelo, Ramón, Daniel (roles: owner, socio)
-- Frecuencia: quincenal (reuniones de resultados)
-- Métricas: evolución, márgenes, comparativos, impacto decisiones
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Vista: ventas agrupadas por mes (últimos 24 meses)
-- ---------------------------------------------------------------------------
create or replace view vw_ventas_mensual as
select
    date_trunc('month', fecha_emision)::date   as mes,
    count(*)                                    as num_ventas,
    sum(total_neto)                             as ingresos_netos,
    sum(total_bruto)                            as ingresos_brutos,
    avg(total_neto)                             as ticket_promedio,
    count(distinct cliente_id_relbase)
        filter (where not es_anonimo)           as clientes_unicos
from ventas
where estado != 'anulado'
  and fecha_emision >= (current_date - interval '24 months')
group by date_trunc('month', fecha_emision)
order by mes;

-- ---------------------------------------------------------------------------
-- Vista: margen bruto por categoría (mes actual y anterior)
-- ---------------------------------------------------------------------------
create or replace view vw_margen_por_categoria as
select
    coalesce(p.categoria_nombre, 'Sin categoría') as categoria,
    date_trunc('month', v.fecha_emision)::date     as mes,
    sum(vd.subtotal_neto)                           as ingresos_netos,
    sum(vd.margen_neto)                             as margen_neto_total,
    round(
        case when sum(vd.subtotal_neto) > 0
        then sum(vd.margen_neto) / sum(vd.subtotal_neto) * 100
        else null end,
    1)                                              as margen_pct,
    sum(vd.cantidad)                                as unidades_vendidas
from ventas_detalle vd
join ventas v        on v.id = vd.venta_id
left join productos p on p.codigo = vd.codigo_producto
where v.estado != 'anulado'
  and v.fecha_emision >= date_trunc('month', current_date - interval '12 months')
group by coalesce(p.categoria_nombre, 'Sin categoría'),
         date_trunc('month', v.fecha_emision)
order by mes desc, ingresos_netos desc;

-- ---------------------------------------------------------------------------
-- Vista: evolución de clientes únicos por mes
-- ---------------------------------------------------------------------------
create or replace view vw_evolucion_clientes as
select
    date_trunc('month', v.fecha_emision)::date          as mes,
    count(distinct v.cliente_id_relbase)
        filter (where not v.es_anonimo)                  as clientes_identificados,
    count(*) filter (where v.es_anonimo)                 as ventas_anonimas,
    count(distinct v.cliente_id_relbase)
        filter (
            where not v.es_anonimo
              and v.cliente_id_relbase not in (
                  select distinct cliente_id_relbase
                  from ventas v2
                  where v2.fecha_emision < date_trunc('month', v.fecha_emision)
                    and not v2.es_anonimo
                    and v2.estado != 'anulado'
              )
        )                                                as clientes_nuevos
from ventas v
where v.estado != 'anulado'
  and v.fecha_emision >= (current_date - interval '12 months')
group by date_trunc('month', v.fecha_emision)
order by mes;

-- ---------------------------------------------------------------------------
-- Vista: top productos acumulado (período configurable vía función)
-- ---------------------------------------------------------------------------
create or replace view vw_top_productos_historico as
select
    vd.codigo_producto,
    vd.nombre_producto,
    coalesce(p.categoria_nombre, 'Sin categoría') as categoria,
    sum(vd.cantidad)                               as unidades_totales,
    sum(vd.subtotal_neto)                          as ingresos_netos_total,
    sum(vd.margen_neto)                            as margen_neto_total,
    round(
        case when sum(vd.subtotal_neto) > 0
        then sum(vd.margen_neto) / sum(vd.subtotal_neto) * 100
        else null end,
    1)                                             as margen_pct,
    count(distinct v.id)                           as num_transacciones,
    min(v.fecha_emision)                           as primera_venta,
    max(v.fecha_emision)                           as ultima_venta
from ventas_detalle vd
join ventas v        on v.id = vd.venta_id
left join productos p on p.codigo = vd.codigo_producto
where v.estado != 'anulado'
  and vd.codigo_producto is not null
group by vd.codigo_producto, vd.nombre_producto, coalesce(p.categoria_nombre, 'Sin categoría')
order by ingresos_netos_total desc;

-- ---------------------------------------------------------------------------
-- RPC: comparativo_periodos — compara dos rangos de fechas
-- Ejemplo: mes actual vs mismo mes año anterior
-- ---------------------------------------------------------------------------
create or replace function comparativo_periodos(
    p_desde_a   date,
    p_hasta_a   date,
    p_desde_b   date,
    p_hasta_b   date
)
returns json
language sql stable security definer
as $$
    select json_build_object(
        'periodo_a', (
            select json_build_object(
                'desde',           p_desde_a,
                'hasta',           p_hasta_a,
                'ingresos_netos',  coalesce(sum(total_neto),  0),
                'ingresos_brutos', coalesce(sum(total_bruto), 0),
                'num_ventas',      count(*),
                'ticket_promedio', coalesce(avg(total_neto),  0),
                'clientes_unicos', count(distinct cliente_id_relbase)
                                   filter (where not es_anonimo)
            )
            from ventas
            where estado != 'anulado'
              and fecha_emision between p_desde_a and p_hasta_a
        ),
        'periodo_b', (
            select json_build_object(
                'desde',           p_desde_b,
                'hasta',           p_hasta_b,
                'ingresos_netos',  coalesce(sum(total_neto),  0),
                'ingresos_brutos', coalesce(sum(total_bruto), 0),
                'num_ventas',      count(*),
                'ticket_promedio', coalesce(avg(total_neto),  0),
                'clientes_unicos', count(distinct cliente_id_relbase)
                                   filter (where not es_anonimo)
            )
            from ventas
            where estado != 'anulado'
              and fecha_emision between p_desde_b and p_hasta_b
        )
    );
$$;

-- ---------------------------------------------------------------------------
-- RPC: tendencia_12_meses — serie mensual para el gráfico de línea
-- ---------------------------------------------------------------------------
create or replace function tendencia_12_meses()
returns table (
    mes             date,
    ingresos_netos  numeric,
    num_ventas      bigint,
    ticket_promedio numeric
)
language sql stable security definer
as $$
    select
        date_trunc('month', fecha_emision)::date   as mes,
        coalesce(sum(total_neto), 0)               as ingresos_netos,
        count(*)                                   as num_ventas,
        coalesce(avg(total_neto), 0)               as ticket_promedio
    from ventas
    where estado != 'anulado'
      and fecha_emision >= date_trunc('month', current_date - interval '11 months')
    group by date_trunc('month', fecha_emision)
    order by mes;
$$;

-- ---------------------------------------------------------------------------
-- RPC: margen_resumen_mes — margen total del mes para tarjeta ejecutiva
-- ---------------------------------------------------------------------------
create or replace function margen_resumen_mes()
returns json
language sql stable security definer
as $$
    select json_build_object(
        'mes_actual', (
            select json_build_object(
                'ingresos_netos', coalesce(sum(vd.subtotal_neto), 0),
                'margen_neto',    coalesce(sum(vd.margen_neto), 0),
                'margen_pct',     round(
                    case when sum(vd.subtotal_neto) > 0
                    then sum(vd.margen_neto) / sum(vd.subtotal_neto) * 100
                    else null end, 1)
            )
            from ventas_detalle vd
            join ventas v on v.id = vd.venta_id
            where v.estado != 'anulado'
              and v.fecha_emision >= date_trunc('month', current_date)
        ),
        'mes_anterior', (
            select json_build_object(
                'ingresos_netos', coalesce(sum(vd.subtotal_neto), 0),
                'margen_neto',    coalesce(sum(vd.margen_neto), 0),
                'margen_pct',     round(
                    case when sum(vd.subtotal_neto) > 0
                    then sum(vd.margen_neto) / sum(vd.subtotal_neto) * 100
                    else null end, 1)
            )
            from ventas_detalle vd
            join ventas v on v.id = vd.venta_id
            where v.estado != 'anulado'
              and v.fecha_emision >= date_trunc('month', current_date - interval '1 month')
              and v.fecha_emision <  date_trunc('month', current_date)
        )
    );
$$;

-- Grants
grant select on vw_ventas_mensual,
               vw_margen_por_categoria,
               vw_evolucion_clientes,
               vw_top_productos_historico
to authenticated;

grant execute on function comparativo_periodos(date,date,date,date) to authenticated;
grant execute on function tendencia_12_meses()                       to authenticated;
grant execute on function margen_resumen_mes()                       to authenticated;
