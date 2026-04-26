"""
transformer.py — Mapea registros crudos de Relbase al schema estándar de Supabase.

Funciones puras: no realizan llamadas HTTP ni operaciones de base de datos.
Entrada: lista de dicts tal como los entrega extractor.py.
Salida: lista de dicts lista para upsert en Supabase.

Entidades cubiertas:
  - dtes         → ventas
  - items de dte → ventas_detalle
  - productos    → productos
  - clientes     → clientes
  - bodegas      → bodegas
  - stock        → stock (snapshot actual)
"""

import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("relbase.transformer")

# RUT de cliente anónimo que Relbase usa para boletas sin identificar
RUTS_ANONIMOS = {"66666666-6", "55555555-5", "11111111-1"}


# ---------------------------------------------------------------------------
# Helpers de tipo
# ---------------------------------------------------------------------------

def _str(valor) -> Optional[str]:
    if valor is None:
        return None
    v = str(valor).strip()
    return v if v else None


def _float(valor) -> Optional[float]:
    try:
        return float(valor) if valor is not None else None
    except (TypeError, ValueError):
        return None


def _int(valor) -> Optional[int]:
    try:
        return int(valor) if valor is not None else None
    except (TypeError, ValueError):
        return None


def _bool(valor, default: bool = False) -> bool:
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, str):
        return valor.lower() in ("true", "1", "si", "sí", "yes", "activo")
    if isinstance(valor, int):
        return bool(valor)
    return default


def _fecha(valor) -> Optional[str]:
    """Normaliza fechas a ISO date string YYYY-MM-DD."""
    if not valor:
        return None
    if isinstance(valor, str):
        # Acepta YYYY-MM-DD o YYYY-MM-DDTHH:MM:SS...
        return valor[:10]
    return None


def _ahora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalizar_rut(rut: Optional[str]) -> Optional[str]:
    """Elimina puntos y deja el formato XX.XXX.XXX-D o XXXXXXXX-D en minúscula."""
    if not rut:
        return None
    return rut.replace(".", "").strip().upper()


# ---------------------------------------------------------------------------
# Ventas (DTEs)
# ---------------------------------------------------------------------------

def transformar_dte(dte: dict) -> dict:
    """
    Mapea un DTE crudo de Relbase a la tabla ventas de Supabase.

    Campos de Relbase esperados (ajustar si la API devuelve nombres distintos):
      id, folio, tipo_dte, fecha_emision, fecha_vencimiento,
      total_neto, total_iva, total_bruto, total_exento,
      estado, observaciones,
      cliente.id, cliente.rut, cliente.nombre, cliente.email,
      bodega.id / bodega_id,
      vendedor.nombre / vendedor_nombre
    """
    ahora = _ahora_iso()

    # Datos de cliente: pueden venir anidados o aplanados
    cliente = dte.get("cliente") or {}
    cliente_id_relbase = _int(dte.get("cliente_id") or cliente.get("id"))
    cliente_rut = _normalizar_rut(dte.get("cliente_rut") or cliente.get("rut"))
    cliente_nombre = _str(dte.get("cliente_nombre") or cliente.get("nombre") or cliente.get("razon_social"))

    es_anonimo = (
        not cliente_rut
        or cliente_rut in RUTS_ANONIMOS
        or not cliente_nombre
    )

    # Bodega
    bodega = dte.get("bodega") or {}
    bodega_id_relbase = _int(dte.get("bodega_id") or bodega.get("id"))

    # Vendedor
    vendedor = dte.get("vendedor") or {}
    vendedor_nombre = _str(
        dte.get("vendedor_nombre")
        or vendedor.get("nombre")
        or vendedor.get("name")
    )

    return {
        "dte_id_relbase": _int(dte.get("id")),
        "tipo_dte": _int(dte.get("tipo_dte") or dte.get("tipo")),
        "folio": _str(dte.get("folio")),
        "fecha_emision": _fecha(dte.get("fecha_emision") or dte.get("fecha")),
        "fecha_vencimiento": _fecha(dte.get("fecha_vencimiento")),
        "cliente_id_relbase": cliente_id_relbase,
        "cliente_rut": cliente_rut,
        "cliente_nombre": cliente_nombre,
        "cliente_email": _str(dte.get("cliente_email") or cliente.get("email")),
        "es_anonimo": es_anonimo,
        "total_neto": _float(dte.get("total_neto") or dte.get("monto_neto")),
        "total_iva": _float(dte.get("total_iva") or dte.get("monto_iva")),
        "total_bruto": _float(dte.get("total_bruto") or dte.get("monto_total")),
        "total_exento": _float(dte.get("total_exento") or dte.get("monto_exento")),
        "bodega_id_relbase": bodega_id_relbase,
        "vendedor_nombre": vendedor_nombre,
        "estado": _str(dte.get("estado") or dte.get("status")),
        "observaciones": _str(dte.get("observaciones") or dte.get("glosa")),
        "fuente": "relbase",
        "updated_at": ahora,
    }


def transformar_dtes(dtes: list[dict]) -> list[dict]:
    transformados = []
    for dte in dtes:
        try:
            transformados.append(transformar_dte(dte))
        except Exception as e:
            logger.error("Error transformando DTE id=%s: %s", dte.get("id"), e)
    logger.info("DTEs transformados: %d/%d", len(transformados), len(dtes))
    return transformados


# ---------------------------------------------------------------------------
# Líneas de venta (ventas_detalle)
# ---------------------------------------------------------------------------

def transformar_linea_dte(linea: dict, venta_id: str, dte_id_relbase: int) -> dict:
    """
    Mapea una línea de ítem de un DTE a la tabla ventas_detalle.

    Args:
        linea: dict crudo de Relbase (un ítem dentro de data.items / data.lineas).
        venta_id: UUID de la venta en Supabase (FK).
        dte_id_relbase: ID del DTE en Relbase (parte de la clave única).

    Nota: costo_unitario y margen_neto se completan en etapas posteriores.
    """
    ahora = _ahora_iso()

    precio_unitario = _float(linea.get("precio_unitario"))
    cantidad = _float(linea.get("cantidad"))
    descuento_pct = _float(linea.get("descuento_porcentaje") or linea.get("descuento")) or 0.0

    subtotal_neto = _float(linea.get("subtotal_neto") or linea.get("monto_neto"))
    if subtotal_neto is None and precio_unitario and cantidad:
        subtotal_neto = round(precio_unitario * cantidad * (1 - descuento_pct / 100), 2)

    subtotal_bruto = _float(linea.get("subtotal_bruto") or linea.get("monto_total"))

    iva_monto = None
    iva_porcentaje = None
    if subtotal_bruto is not None and subtotal_neto is not None:
        iva_monto = round(subtotal_bruto - subtotal_neto, 2)
        if subtotal_neto > 0:
            iva_porcentaje = round((iva_monto / subtotal_neto) * 100, 2)

    return {
        "venta_id": venta_id,
        "dte_id_relbase": dte_id_relbase,
        "numero_linea": _int(
            linea.get("numero_linea") or linea.get("nro_linea") or linea.get("linea")
        ),
        "codigo_producto": _str(linea.get("codigo") or linea.get("codigo_producto")),
        "nombre_producto": _str(linea.get("descripcion") or linea.get("nombre")),
        "cantidad": cantidad,
        "precio_unitario_neto": precio_unitario,
        "precio_unitario_bruto": _float(linea.get("precio_unitario_bruto")),
        "descuento_porcentaje": descuento_pct,
        "descuento_monto": _float(linea.get("descuento_monto")),
        "subtotal_neto": subtotal_neto,
        "subtotal_bruto": subtotal_bruto,
        "iva_porcentaje": iva_porcentaje,
        "iva_monto": iva_monto,
        # Se completan en etapa de enriquecimiento cruzando con productos
        "costo_unitario": None,
        "fuente": "relbase",
        "updated_at": ahora,
    }


def transformar_lineas_dte(
    items: list[dict],
    venta_id: str,
    dte_id_relbase: int,
) -> list[dict]:
    transformadas = []
    for linea in items:
        try:
            transformadas.append(transformar_linea_dte(linea, venta_id, dte_id_relbase))
        except Exception as e:
            logger.error(
                "Error en línea %s del DTE %s: %s",
                linea.get("numero_linea"), dte_id_relbase, e,
            )
    return transformadas


# ---------------------------------------------------------------------------
# Productos
# ---------------------------------------------------------------------------

def transformar_producto(prod: dict) -> dict:
    """
    Mapea un producto crudo de Relbase a la tabla productos de Supabase.

    Campos Relbase esperados:
      id, codigo, nombre, descripcion,
      precio_neto, precio_bruto, costo_unitario,
      categoria.id, categoria.nombre,
      unidad_medida, activo / es_activo, stock_minimo,
      updated_at
    """
    ahora = _ahora_iso()

    categoria = prod.get("categoria") or {}
    categoria_id_relbase = _int(
        prod.get("categoria_id") or categoria.get("id")
    )
    categoria_nombre = _str(
        prod.get("categoria_nombre") or categoria.get("nombre")
    )

    return {
        "producto_id_relbase": _int(prod.get("id")),
        "codigo": _str(prod.get("codigo") or prod.get("sku")),
        "nombre": _str(prod.get("nombre") or prod.get("descripcion")),
        "descripcion": _str(prod.get("descripcion_larga") or prod.get("descripcion_detalle")),
        "precio_neto": _float(prod.get("precio_neto") or prod.get("precio")),
        "precio_bruto": _float(prod.get("precio_bruto") or prod.get("precio_con_iva")),
        "costo_unitario": _float(prod.get("costo_unitario") or prod.get("costo")),
        "categoria_id_relbase": categoria_id_relbase,
        "categoria_nombre": categoria_nombre,
        "unidad_medida": _str(prod.get("unidad_medida") or prod.get("unidad")),
        "es_activo": _bool(prod.get("es_activo") or prod.get("activo"), default=True),
        "stock_minimo": _float(prod.get("stock_minimo") or prod.get("stock_critico")),
        "fuente": "relbase",
        "updated_at": _str(prod.get("updated_at")) or ahora,
    }


def transformar_productos(productos: list[dict]) -> list[dict]:
    transformados = []
    for prod in productos:
        try:
            transformados.append(transformar_producto(prod))
        except Exception as e:
            logger.error("Error transformando producto id=%s: %s", prod.get("id"), e)
    logger.info("Productos transformados: %d/%d", len(transformados), len(productos))
    return transformados


# ---------------------------------------------------------------------------
# Clientes
# ---------------------------------------------------------------------------

def transformar_cliente(cliente: dict) -> dict:
    """
    Mapea un cliente crudo de Relbase a la tabla clientes de Supabase.

    Campos Relbase esperados:
      id, rut, nombre / razon_social, email, telefono,
      direccion, ciudad, region,
      tipo_cliente / tipo (empresa/persona o B2B/B2C),
      giro, activo / es_activo, updated_at
    """
    ahora = _ahora_iso()

    rut = _normalizar_rut(cliente.get("rut"))
    nombre = _str(
        cliente.get("nombre")
        or cliente.get("razon_social")
        or cliente.get("nombre_fantasia")
    )
    es_anonimo = (
        not rut
        or rut in RUTS_ANONIMOS
        or not nombre
    )

    return {
        "cliente_id_relbase": _int(cliente.get("id")),
        "rut": rut,
        "nombre": nombre,
        "email": _str(cliente.get("email") or cliente.get("correo")),
        "telefono": _str(cliente.get("telefono") or cliente.get("fono")),
        "direccion": _str(cliente.get("direccion") or cliente.get("address")),
        "ciudad": _str(cliente.get("ciudad") or cliente.get("commune")),
        "region": _str(cliente.get("region")),
        "tipo_cliente": _str(
            cliente.get("tipo_cliente") or cliente.get("tipo") or cliente.get("categoria")
        ),
        "giro": _str(cliente.get("giro") or cliente.get("actividad_economica")),
        "es_anonimo": es_anonimo,
        "es_activo": _bool(
            cliente.get("es_activo") or cliente.get("activo"), default=True
        ),
        "fuente": "relbase",
        "updated_at": _str(cliente.get("updated_at")) or ahora,
    }


def transformar_clientes(clientes: list[dict]) -> list[dict]:
    transformados = []
    for c in clientes:
        try:
            transformados.append(transformar_cliente(c))
        except Exception as e:
            logger.error("Error transformando cliente id=%s: %s", c.get("id"), e)
    logger.info("Clientes transformados: %d/%d", len(transformados), len(clientes))
    return transformados


# ---------------------------------------------------------------------------
# Bodegas
# ---------------------------------------------------------------------------

def transformar_bodega(bodega: dict) -> dict:
    ahora = _ahora_iso()
    return {
        "bodega_id_relbase": _int(bodega.get("id")),
        "nombre": _str(bodega.get("nombre") or bodega.get("name")),
        "direccion": _str(bodega.get("direccion") or bodega.get("address")),
        "es_activa": _bool(
            bodega.get("es_activa") or bodega.get("activo") or bodega.get("activa"),
            default=True,
        ),
        "fuente": "relbase",
        "updated_at": ahora,
    }


def transformar_bodegas(bodegas: list[dict]) -> list[dict]:
    transformados = []
    for b in bodegas:
        try:
            transformados.append(transformar_bodega(b))
        except Exception as e:
            logger.error("Error transformando bodega id=%s: %s", b.get("id"), e)
    logger.info("Bodegas transformadas: %d/%d", len(transformados), len(bodegas))
    return transformados


# ---------------------------------------------------------------------------
# Stock
# ---------------------------------------------------------------------------

def transformar_stock(fila: dict) -> dict:
    """
    Mapea una fila de stock_por_bodegas al schema de la tabla stock.

    El campo _producto_id_relbase es añadido por extraer_stock_por_producto()
    en extractor.py para identificar el producto.

    La clave única de upsert es (producto_id_relbase, bodega_id_relbase).
    """
    ahora = _ahora_iso()

    bodega = fila.get("bodega") or {}
    bodega_id_relbase = _int(
        fila.get("bodega_id") or fila.get("id") or bodega.get("id")
    )
    bodega_nombre = _str(
        fila.get("bodega_nombre") or fila.get("nombre") or bodega.get("nombre")
    )

    cantidad = _float(fila.get("cantidad") or fila.get("stock") or fila.get("existencia")) or 0.0
    cantidad_reservada = _float(
        fila.get("cantidad_reservada") or fila.get("reservado")
    ) or 0.0
    cantidad_disponible = round(cantidad - cantidad_reservada, 4)

    return {
        "producto_id_relbase": _int(fila.get("_producto_id_relbase")),
        "bodega_id_relbase": bodega_id_relbase,
        "bodega_nombre": bodega_nombre,
        "cantidad": cantidad,
        "cantidad_reservada": cantidad_reservada,
        "cantidad_disponible": cantidad_disponible,
        "fecha_snapshot": ahora,
        "fuente": "relbase",
        "updated_at": ahora,
    }


def transformar_stock_lista(filas: list[dict]) -> list[dict]:
    transformados = []
    for fila in filas:
        try:
            transformados.append(transformar_stock(fila))
        except Exception as e:
            logger.error(
                "Error transformando stock producto=%s: %s",
                fila.get("_producto_id_relbase"), e,
            )
    logger.info("Filas de stock transformadas: %d/%d", len(transformados), len(filas))
    return transformados


# ---------------------------------------------------------------------------
# Dispatcher unificado
# ---------------------------------------------------------------------------

_TRANSFORMERS = {
    "dtes": transformar_dtes,
    "productos": transformar_productos,
    "clientes": transformar_clientes,
    "bodegas": transformar_bodegas,
    "stock": transformar_stock_lista,
}


def transformar(entidad: str, datos: list[dict]) -> list[dict]:
    """
    Punto de entrada único: transforma una lista cruda de Relbase al schema Supabase.

    Args:
        entidad: "dtes" | "productos" | "clientes" | "bodegas" | "stock"
        datos: lista de dicts crudos entregados por extractor.py.

    Returns:
        Lista de dicts lista para upsert en loader.py.
    """
    if entidad not in _TRANSFORMERS:
        raise ValueError(
            f"Entidad '{entidad}' no soportada. Opciones: {set(_TRANSFORMERS)}"
        )
    if not datos:
        logger.info("transformar('%s'): lista vacía, nada que hacer.", entidad)
        return []

    logger.info("Transformando %d registros de '%s'...", len(datos), entidad)
    return _TRANSFORMERS[entidad](datos)
