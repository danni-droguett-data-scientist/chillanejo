"""
transformer.py — Mapea registros crudos de Relbase al schema real de Supabase.

Funciones puras: no realizan llamadas HTTP ni operaciones de base de datos.
Entrada: lista de dicts tal como los entrega extractor.py.
Salida: lista de dicts lista para upsert en Supabase.

Schema real (verificado contra PostgREST):
  bodegas:       relbase_id, nombre, activa
  productos:     relbase_id, sku, nombre, descripcion, precio_neto, costo_unitario, activo
  clientes:      relbase_id, rut, nombre, nombre_fantasia, giro, direccion, email, telefono, es_anonimo, activo
  ventas:        relbase_id, tipo_documento, folio, estado_sii, fecha_emision, fecha_vencimiento,
                 cliente_id (FK->clientes.id), bodega_id (FK->bodegas.id), neto, iva, total, vendedor
  ventas_detalle: venta_id (FK), producto_id (FK), relbase_producto_id, nombre_producto, sku,
                  cantidad, precio_unitario, costo_unitario, descuento_pct, afecto_iva, total_neto
  stock:         producto_id (FK->productos.id), bodega_id (FK->bodegas.id), cantidad
  sync_log:      entidad, fuente, ultima_sync, registros_nuevos, registros_error, estado

Los campos con prefijo _ son FKs que deben resolverse a IDs de BD antes del upsert.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("relbase.transformer")

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
        return valor[:10]
    return None


def _ahora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalizar_rut(rut: Optional[str]) -> Optional[str]:
    if not rut:
        return None
    return rut.replace(".", "").strip().upper()


# ---------------------------------------------------------------------------
# Bodegas
# ---------------------------------------------------------------------------

def transformar_bodega(bodega: dict) -> dict:
    enabled = bodega.get("enabled")
    return {
        "relbase_id": _int(bodega.get("id")),
        "nombre": _str(bodega.get("name") or bodega.get("nombre")),
        "activa": _bool(
            enabled if enabled is not None else (bodega.get("activa") or bodega.get("es_activa")),
            default=True,
        ),
    }


def transformar_bodegas(bodegas: list[dict]) -> list[dict]:
    out = []
    for b in bodegas:
        try:
            out.append(transformar_bodega(b))
        except Exception as e:
            logger.error("Error transformando bodega id=%s: %s", b.get("id"), e)
    logger.info("Bodegas transformadas: %d/%d", len(out), len(bodegas))
    return out


# ---------------------------------------------------------------------------
# Productos
# ---------------------------------------------------------------------------

def transformar_producto(prod: dict) -> dict:
    enabled = prod.get("enabled")
    return {
        "relbase_id": _int(prod.get("id")),
        "sku": _str(prod.get("code") or prod.get("codigo") or prod.get("sku")),
        "nombre": _str(prod.get("name") or prod.get("nombre")),
        "descripcion": _str(prod.get("description") or prod.get("descripcion")),
        "precio_neto": _float(prod.get("price") or prod.get("precio_neto")),
        "costo_unitario": _float(prod.get("unit_cost") or prod.get("costo_unitario")),
        "activo": _bool(
            enabled if enabled is not None else (prod.get("activo") or prod.get("es_activo")),
            default=True,
        ),
    }


def transformar_productos(productos: list[dict]) -> list[dict]:
    out = []
    for p in productos:
        try:
            out.append(transformar_producto(p))
        except Exception as e:
            logger.error("Error transformando producto id=%s: %s", p.get("id"), e)
    logger.info("Productos transformados: %d/%d", len(out), len(productos))
    return out


# ---------------------------------------------------------------------------
# Clientes
# ---------------------------------------------------------------------------

def transformar_cliente(cliente: dict) -> dict:
    rut = _normalizar_rut(cliente.get("rut"))
    nombre = _str(
        cliente.get("name") or cliente.get("nombre") or cliente.get("razon_social")
    )
    es_anonimo = not rut or rut in RUTS_ANONIMOS or not nombre
    enabled = cliente.get("enabled")
    return {
        "relbase_id": _int(cliente.get("id")),
        "rut": rut,
        "nombre": nombre,
        "nombre_fantasia": _str(cliente.get("fantasy_name") or cliente.get("nombre_fantasia")),
        "giro": _str(cliente.get("business_activity") or cliente.get("giro")),
        "direccion": _str(cliente.get("address") or cliente.get("direccion")),
        "email": _str(cliente.get("email")),
        "telefono": _str(cliente.get("phone") or cliente.get("telefono")),
        "es_anonimo": es_anonimo,
        "activo": _bool(
            enabled if enabled is not None else (cliente.get("activo") or cliente.get("es_activo")),
            default=True,
        ),
    }


def transformar_clientes(clientes: list[dict]) -> list[dict]:
    out = []
    for c in clientes:
        try:
            out.append(transformar_cliente(c))
        except Exception as e:
            logger.error("Error transformando cliente id=%s: %s", c.get("id"), e)
    logger.info("Clientes transformados: %d/%d", len(out), len(clientes))
    return out


# ---------------------------------------------------------------------------
# Ventas (DTEs)
# Los campos _cliente_relbase_id y _bodega_relbase_id son temporales:
# el loader los resuelve a cliente_id / bodega_id (IDs de BD) antes del upsert.
# ---------------------------------------------------------------------------

def transformar_dte(dte: dict) -> dict:
    return {
        "relbase_id": _int(dte.get("id")),
        "tipo_documento": _int(dte.get("type_document") or dte.get("tipo_dte")),
        "folio": _str(dte.get("folio")),
        "estado_sii": _str(dte.get("sii_status_name") or dte.get("estado_sii")),
        "fecha_emision": _fecha(dte.get("start_date") or dte.get("fecha_emision")),
        "fecha_vencimiento": _fecha(dte.get("end_date") or dte.get("fecha_vencimiento")),
        # FKs temporales — se resuelven en loader.resolver_fks_ventas()
        "_cliente_relbase_id": _int(dte.get("customer_id") or dte.get("cliente_id")),
        "_bodega_relbase_id": _int(dte.get("ware_house_id") or dte.get("bodega_id")),
        "neto": _float(dte.get("amount_neto") or dte.get("neto")),
        "iva": _float(dte.get("amount_iva") or dte.get("iva")),
        "total": _float(dte.get("amount_total") or dte.get("total")),
        "vendedor": _str(dte.get("vendedor_nombre") or dte.get("vendedor")),
        "forma_pago": _str(
            dte.get("payment_method_name")
            or dte.get("payment_method")
            or dte.get("forma_pago")
            or dte.get("tipo_pago")
        ),
    }


def transformar_dtes(dtes: list[dict]) -> list[dict]:
    out = []
    for d in dtes:
        try:
            out.append(transformar_dte(d))
        except Exception as e:
            logger.error("Error transformando DTE id=%s: %s", d.get("id"), e)
    logger.info("DTEs transformados: %d/%d", len(out), len(dtes))
    return out


# ---------------------------------------------------------------------------
# Ventas detalle
# venta_id y producto_id (FKs de BD) se resuelven en el loader.
# ---------------------------------------------------------------------------

def transformar_linea_detalle(item: dict, dte_id_relbase: int) -> dict:
    """
    Mapea una línea de ítem del DTE al schema de ventas_detalle.
    Los campos _venta_relbase_id y _producto_relbase_id se resuelven en el loader.
    """
    cantidad = _float(item.get("quantity") or item.get("cantidad"))
    precio_unitario = _float(item.get("price") or item.get("precio_unitario"))
    descuento_pct = _float(item.get("discount") or item.get("descuento_pct")) or 0.0
    total_neto = _float(item.get("total") or item.get("total_neto"))
    if total_neto is None and precio_unitario and cantidad:
        total_neto = round(precio_unitario * cantidad * (1 - descuento_pct / 100), 2)

    return {
        "_venta_relbase_id": dte_id_relbase,
        "_producto_relbase_id": _int(item.get("product_id") or item.get("relbase_producto_id")),
        "relbase_producto_id": _int(item.get("product_id") or item.get("relbase_producto_id")),
        "nombre_producto": _str(item.get("name") or item.get("nombre_producto") or item.get("descripcion")),
        "sku": _str(item.get("code") or item.get("sku") or item.get("codigo")),
        "cantidad": cantidad,
        "precio_unitario": precio_unitario,
        "costo_unitario": _float(item.get("unit_cost") or item.get("costo_unitario")),
        "descuento_pct": descuento_pct,
        "afecto_iva": _bool(item.get("is_tax_affected") or item.get("afecto_iva"), default=True),
        "total_neto": total_neto,
    }


def transformar_lineas_detalle(items: list[dict], dte_id_relbase: int) -> list[dict]:
    out = []
    for item in items:
        try:
            out.append(transformar_linea_detalle(item, dte_id_relbase))
        except Exception as e:
            logger.error("Error en línea de DTE %s: %s", dte_id_relbase, e)
    return out


# ---------------------------------------------------------------------------
# Stock
# producto_id y bodega_id (FKs de BD) se resuelven en el loader.
# ---------------------------------------------------------------------------

def transformar_stock(fila: dict) -> dict:
    return {
        "_producto_relbase_id": _int(fila.get("_producto_id_relbase")),
        "_bodega_relbase_id": _int(fila.get("ware_house_id") or fila.get("bodega_id")),
        "cantidad": _float(fila.get("current_stock") or fila.get("cantidad")) or 0.0,
    }


def transformar_stock_lista(filas: list[dict]) -> list[dict]:
    out = []
    for f in filas:
        try:
            out.append(transformar_stock(f))
        except Exception as e:
            logger.error("Error transformando stock: %s", e)
    logger.info("Stock transformado: %d/%d filas", len(out), len(filas))
    return out


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
    if entidad not in _TRANSFORMERS:
        raise ValueError(
            f"Entidad '{entidad}' no soportada. Opciones: {set(_TRANSFORMERS)}"
        )
    if not datos:
        logger.info("transformar('%s'): lista vacía.", entidad)
        return []
    logger.info("Transformando %d registros de '%s'...", len(datos), entidad)
    return _TRANSFORMERS[entidad](datos)
