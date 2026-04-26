-- =============================================================================
-- 005_ceo_views.sql — Vistas y funciones para Dashboard CEO Personal
-- =============================================================================
-- Usuario: solo Daniel (rol owner)
-- Métricas: ingresos por 3 líneas, costos stack, rentabilidad, pipeline
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Vista: resumen ingresos CEO por mes (las 3 líneas)
-- ---------------------------------------------------------------------------
create or replace view vw_ingresos_ceo_mensual as
select
    mes,
    monto_clp                                as honorarios_ds,
    0::numeric                               as comision_plataforma,  -- se popula cuando haya ventas online
    0::numeric                               as gestion_importacion,
    monto_clp                                as total_mes
from honorarios_ds
union all
select
    date_trunc('month', fecha_pago)::date    as mes,
    0                                        as honorarios_ds,
    0                                        as comision_plataforma,
    honorarios                               as gestion_importacion,
    honorarios                               as total_mes
from ingresos_importacion
where fecha_pago is not null
order by mes;

-- ---------------------------------------------------------------------------
-- Vista: costos stack por mes
-- ---------------------------------------------------------------------------
create or replace view vw_costos_stack_mensual as
select
    mes,
    sum(monto_clp)                           as total_clp,
    sum(monto_usd)                           as total_usd,
    json_object_agg(servicio, monto_clp)     as detalle
from costos_stack
group by mes
order by mes;

-- ---------------------------------------------------------------------------
-- Vista: rentabilidad CEO por mes (ingresos - costos)
-- ---------------------------------------------------------------------------
create or replace view vw_rentabilidad_ceo as
with ingresos as (
    select mes, sum(total_mes) as ingresos_total
    from vw_ingresos_ceo_mensual
    group by mes
),
costos as (
    select mes, total_clp as costos_total
    from vw_costos_stack_mensual
)
select
    i.mes,
    i.ingresos_total,
    coalesce(c.costos_total, 0)             as costos_total,
    i.ingresos_total - coalesce(c.costos_total, 0) as utilidad_neta,
    round(
        case when i.ingresos_total > 0
        then (i.ingresos_total - coalesce(c.costos_total, 0)) / i.ingresos_total * 100
        else null end,
    1)                                       as margen_pct
from ingresos i
left join costos c using (mes)
order by mes;

-- ---------------------------------------------------------------------------
-- Vista: pipeline de clientes DS
-- ---------------------------------------------------------------------------
create or replace view vw_pipeline_clientes as
select
    etapa,
    count(*)                                 as cantidad,
    sum(valor_estimado)                      as valor_pipeline,
    avg(valor_estimado)                      as ticket_promedio
from pipeline_clientes
group by etapa
order by
    case etapa
        when 'prospecto'    then 1
        when 'propuesta'    then 2
        when 'negociacion'  then 3
        when 'cerrado'      then 4
        else 5
    end;

-- ---------------------------------------------------------------------------
-- RPC: resumen_financiero_ceo — snapshot completo para las tarjetas CEO
-- ---------------------------------------------------------------------------
create or replace function resumen_financiero_ceo()
returns json
language sql stable security definer
as $$
    select json_build_object(
        'honorarios_acumulado_anio', (
            select coalesce(sum(monto_clp), 0)
            from honorarios_ds
            where mes >= date_trunc('year', current_date)
        ),
        'honorarios_mes_actual', (
            select coalesce(monto_clp, 0)
            from honorarios_ds
            where mes = date_trunc('month', current_date)::date
            limit 1
        ),
        'costos_mes_actual', (
            select coalesce(sum(monto_clp), 0)
            from costos_stack
            where mes = date_trunc('month', current_date)::date
        ),
        'pipeline_total', (
            select coalesce(sum(valor_estimado), 0)
            from pipeline_clientes
            where etapa != 'cerrado'
        ),
        'clientes_activos', (
            select count(*)
            from pipeline_clientes
            where etapa = 'cerrado'
        )
    );
$$;

-- Solo owner puede acceder
create policy "vw_ingresos_ceo_owner" on honorarios_ds
    for select using (auth.rol_app() = 'owner');

grant select on vw_ingresos_ceo_mensual,
               vw_costos_stack_mensual,
               vw_rentabilidad_ceo,
               vw_pipeline_clientes
to authenticated;

grant execute on function resumen_financiero_ceo() to authenticated;
