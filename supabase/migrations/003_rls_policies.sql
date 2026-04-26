-- =============================================================================
-- 003_rls_policies.sql — Políticas RLS por rol
-- =============================================================================
-- Principio: mínimo privilegio. Cada rol ve solo lo que necesita.
--
-- Roles de app (JWT claim: app_role):
--   owner      → Daniel: todo
--   socio      → Marcelo, Ramón: operativo + ejecutivo (sin tablas CEO)
--   operativo  → Mirella: dashboard operativo + panel admin
--
-- Los usuarios se crean en Supabase Auth y se les asigna app_role
-- en la tabla auth.users o via JWT custom claims.
-- =============================================================================

-- Helper: extrae app_role del JWT
create or replace function auth.rol_app()
returns text
language sql stable
as $$
    select coalesce(
        current_setting('request.jwt.claims', true)::json->>'app_role',
        'anon'
    );
$$;

-- =============================================================================
-- VENTAS
-- =============================================================================
create policy "ventas_select_roles_negocio"
    on ventas for select
    using (auth.rol_app() in ('owner', 'socio', 'operativo'));

-- =============================================================================
-- VENTAS DETALLE
-- =============================================================================
create policy "ventas_detalle_select_roles_negocio"
    on ventas_detalle for select
    using (auth.rol_app() in ('owner', 'socio', 'operativo'));

-- =============================================================================
-- PRODUCTOS
-- =============================================================================
create policy "productos_select_roles_negocio"
    on productos for select
    using (auth.rol_app() in ('owner', 'socio', 'operativo'));

-- =============================================================================
-- CLIENTES
-- =============================================================================
create policy "clientes_select_roles_negocio"
    on clientes for select
    using (auth.rol_app() in ('owner', 'socio', 'operativo'));

-- =============================================================================
-- STOCK
-- =============================================================================
create policy "stock_select_roles_negocio"
    on stock for select
    using (auth.rol_app() in ('owner', 'socio', 'operativo'));

create policy "stock_historico_select_roles_negocio"
    on stock_historico for select
    using (auth.rol_app() in ('owner', 'socio', 'operativo'));

-- =============================================================================
-- BODEGAS / CATEGORÍAS
-- =============================================================================
create policy "bodegas_select_todos"
    on bodegas for select
    using (auth.rol_app() in ('owner', 'socio', 'operativo'));

create policy "categorias_select_todos"
    on categorias for select
    using (auth.rol_app() in ('owner', 'socio', 'operativo'));

-- =============================================================================
-- COMPRAS (solo owner y socio — Mirella no necesita ver compras)
-- =============================================================================
create policy "compras_select_owner_socio"
    on compras for select
    using (auth.rol_app() in ('owner', 'socio'));

create policy "compras_detalle_select_owner_socio"
    on compras_detalle for select
    using (auth.rol_app() in ('owner', 'socio'));

-- =============================================================================
-- PROVEEDORES
-- =============================================================================
create policy "proveedores_select_owner_socio"
    on proveedores for select
    using (auth.rol_app() in ('owner', 'socio'));

create policy "proveedores_write_owner"
    on proveedores for all
    using (auth.rol_app() = 'owner');

-- =============================================================================
-- SYNC LOG (solo owner puede ver — dato técnico interno)
-- =============================================================================
create policy "sync_log_select_owner"
    on sync_log for select
    using (auth.rol_app() = 'owner');

-- =============================================================================
-- TABLAS CEO — solo owner
-- =============================================================================
create policy "honorarios_ds_owner_only"
    on honorarios_ds for all
    using (auth.rol_app() = 'owner');

create policy "ingresos_importacion_owner_only"
    on ingresos_importacion for all
    using (auth.rol_app() = 'owner');

create policy "costos_stack_owner_only"
    on costos_stack for all
    using (auth.rol_app() = 'owner');

create policy "pipeline_clientes_owner_only"
    on pipeline_clientes for all
    using (auth.rol_app() = 'owner');
