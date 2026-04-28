-- Agrega forma_pago a la tabla ventas.
-- Relbase entrega este campo como payment_method_name en el endpoint /api/v1/dtes.
alter table ventas add column if not exists forma_pago text;

comment on column ventas.forma_pago is 'Medio de pago según Relbase (efectivo, tarjeta, transferencia, etc.)';
