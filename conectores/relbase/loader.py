"""
loader.py — Carga registros transformados a Supabase mediante upsert.

Schema real de Supabase (verificado):
  bodegas:       ON CONFLICT relbase_id
  productos:     ON CONFLICT relbase_id
  clientes:      ON CONFLICT relbase_id
  ventas:        ON CONFLICT relbase_id (FKs cliente_id/bodega_id resueltas con construir_lookup)
  ventas_detalle: insert directo (sin upsert — sin clave única compuesta definida)
  stock:         ON CONFLICT producto_id,bodega_id (IDs de BD)
  sync_log:      ON CONFLICT entidad (columnas: ultima_sync, registros_nuevos, registros_error)
"""

import os
import logging
from datetime import datetime, timezone
from typing import Optional

from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

logger = logging.getLogger("relbase.loader")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
CHUNK_SIZE = int(os.getenv("LOADER_CHUNK_SIZE", "100"))


# ---------------------------------------------------------------------------
# Cliente Supabase
# ---------------------------------------------------------------------------

def _supabase() -> Client:
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise EnvironmentError(
            "Faltan SUPABASE_URL o SUPABASE_SERVICE_ROLE_KEY en .env."
        )
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)


def _chunks(lista: list, tamaño: int):
    for i in range(0, len(lista), tamaño):
        yield lista[i : i + tamaño]


# ---------------------------------------------------------------------------
# Lookup de IDs de BD por relbase_id
# ---------------------------------------------------------------------------

def construir_lookup(supabase: Client, tabla: str, col_relbase: str = "relbase_id", col_db: str = "id") -> dict:
    """
    Retorna {relbase_id: db_id} para resolver FKs.
    Pagina para superar el límite de 1000 filas de PostgREST.
    """
    resultado = {}
    page_size = 1000
    offset = 0
    while True:
        resp = (
            supabase.table(tabla)
            .select(f"{col_relbase},{col_db}")
            .range(offset, offset + page_size - 1)
            .execute()
        )
        filas = resp.data or []
        for row in filas:
            if row.get(col_relbase) is not None:
                resultado[row[col_relbase]] = row[col_db]
        if len(filas) < page_size:
            break
        offset += page_size
    return resultado


def resolver_fks_ventas(registros: list[dict], clientes_map: dict, bodegas_map: dict) -> list[dict]:
    """Reemplaza _cliente_relbase_id/_bodega_relbase_id con IDs enteros de BD."""
    out = []
    for r in registros:
        cliente_relbase = r.pop("_cliente_relbase_id", None)
        bodega_relbase = r.pop("_bodega_relbase_id", None)
        r["cliente_id"] = clientes_map.get(cliente_relbase)
        r["bodega_id"] = bodegas_map.get(bodega_relbase)
        out.append(r)
    return out


def resolver_fks_detalle(registros: list[dict], ventas_map: dict, productos_map: dict) -> list[dict]:
    """Reemplaza _venta_relbase_id/_producto_relbase_id con IDs de BD."""
    out = []
    sin_venta = 0
    for r in registros:
        venta_relbase = r.pop("_venta_relbase_id", None)
        prod_relbase = r.pop("_producto_relbase_id", None)
        venta_id = ventas_map.get(venta_relbase)
        producto_id = productos_map.get(prod_relbase)
        if not venta_id:
            sin_venta += 1
            continue
        r["venta_id"] = venta_id
        r["producto_id"] = producto_id
        out.append(r)
    if sin_venta:
        logger.warning("%d líneas sin venta_id en BD — omitidas.", sin_venta)
    return out


def resolver_fks_stock(registros: list[dict], productos_map: dict, bodegas_map: dict) -> list[dict]:
    """Reemplaza _producto_relbase_id/_bodega_relbase_id con IDs de BD."""
    out = []
    sin_fk = 0
    for r in registros:
        prod_relbase = r.pop("_producto_relbase_id", None)
        bodega_relbase = r.pop("_bodega_relbase_id", None)
        producto_id = productos_map.get(prod_relbase)
        bodega_id = bodegas_map.get(bodega_relbase)
        if not producto_id or not bodega_id:
            sin_fk += 1
            continue
        r["producto_id"] = producto_id
        r["bodega_id"] = bodega_id
        out.append(r)
    if sin_fk:
        logger.warning("%d filas de stock sin FK válidas — omitidas.", sin_fk)
    return out


# ---------------------------------------------------------------------------
# Upsert en lotes
# ---------------------------------------------------------------------------

def _upsert_lotes(supabase: Client, tabla: str, registros: list[dict], on_conflict: str, chunk_size: int = CHUNK_SIZE) -> int:
    total = 0
    lotes = list(_chunks(registros, chunk_size))
    for idx, lote in enumerate(lotes, start=1):
        logger.debug("Upsert '%s': lote %d/%d (%d registros)", tabla, idx, len(lotes), len(lote))
        resp = supabase.table(tabla).upsert(lote, on_conflict=on_conflict).execute()
        total += len(resp.data or [])
    return total


def _insert_lotes(supabase: Client, tabla: str, registros: list[dict], chunk_size: int = CHUNK_SIZE) -> int:
    """Insert sin ON CONFLICT — para tablas sin unique constraint compuesto."""
    total = 0
    lotes = list(_chunks(registros, chunk_size))
    for idx, lote in enumerate(lotes, start=1):
        logger.debug("Insert '%s': lote %d/%d (%d registros)", tabla, idx, len(lotes), len(lote))
        resp = supabase.table(tabla).insert(lote).execute()
        total += len(resp.data or [])
    return total


# ---------------------------------------------------------------------------
# sync_log
# ---------------------------------------------------------------------------

def _actualizar_sync_log(supabase: Client, entidad: str, procesados: int, cargados: int, errores: int = 0) -> None:
    ahora = datetime.now(timezone.utc).isoformat()
    payload = {
        "entidad": entidad,
        "fuente": "relbase",
        "ultima_sync": ahora,
        "registros_nuevos": cargados,
        "registros_error": errores,
        "estado": "ok" if errores == 0 else "error_parcial",
    }
    try:
        supabase.table("sync_log").insert(payload).execute()
    except Exception as e:
        logger.warning("sync_log insert falló para '%s': %s", entidad, e)
    logger.info("sync_log '%s' → procesados=%d | cargados=%d | errores=%d", entidad, procesados, cargados, errores)


# ---------------------------------------------------------------------------
# Cargadores específicos
# ---------------------------------------------------------------------------

def cargar_bodegas(supabase: Client, registros: list[dict], chunk_size: int = CHUNK_SIZE) -> int:
    total = _upsert_lotes(supabase, "bodegas", registros, "relbase_id", chunk_size)
    logger.info("Bodegas cargadas: %d", total)
    return total


def cargar_productos(supabase: Client, registros: list[dict], chunk_size: int = CHUNK_SIZE) -> int:
    total = _upsert_lotes(supabase, "productos", registros, "relbase_id", chunk_size)
    logger.info("Productos cargados: %d", total)
    return total


def cargar_clientes(supabase: Client, registros: list[dict], chunk_size: int = CHUNK_SIZE) -> int:
    total = _upsert_lotes(supabase, "clientes", registros, "relbase_id", chunk_size)
    logger.info("Clientes cargados: %d", total)
    return total


def cargar_dtes(supabase: Client, registros: list[dict], clientes_map: dict, bodegas_map: dict, chunk_size: int = CHUNK_SIZE) -> int:
    resueltos = resolver_fks_ventas(registros, clientes_map, bodegas_map)
    total = _upsert_lotes(supabase, "ventas", resueltos, "relbase_id", chunk_size)
    logger.info("Ventas (DTEs) cargadas: %d", total)
    return total


def cargar_ventas_detalle(supabase: Client, registros: list[dict], ventas_map: dict, productos_map: dict, chunk_size: int = CHUNK_SIZE) -> int:
    resueltos = resolver_fks_detalle(registros, ventas_map, productos_map)
    if not resueltos:
        return 0
    total = _insert_lotes(supabase, "ventas_detalle", resueltos, chunk_size)
    logger.info("ventas_detalle cargadas: %d líneas", total)
    return total


def cargar_stock(supabase: Client, registros: list[dict], productos_map: dict, bodegas_map: dict, chunk_size: int = CHUNK_SIZE) -> int:
    resueltos = resolver_fks_stock(registros, productos_map, bodegas_map)
    if not resueltos:
        return 0
    total = _upsert_lotes(supabase, "stock", resueltos, "producto_id,bodega_id", chunk_size)
    logger.info("Stock cargado: %d filas", total)
    return total


# ---------------------------------------------------------------------------
# Dispatcher unificado (usado por sync_incremental y otros)
# Nota: ventas, ventas_detalle y stock requieren los maps de FK — usar
# los cargadores específicos directamente cuando se necesiten resoluciones.
# ---------------------------------------------------------------------------

def cargar_entidad(
    entidad: str,
    registros: list[dict],
    chunk_size: int = CHUNK_SIZE,
    actualizar_sync: bool = True,
    # Maps opcionales para FKs
    clientes_map: Optional[dict] = None,
    bodegas_map: Optional[dict] = None,
    ventas_map: Optional[dict] = None,
    productos_map: Optional[dict] = None,
) -> dict:
    if not registros:
        logger.info("cargar_entidad('%s'): lista vacía.", entidad)
        return {"entidad": entidad, "total_registros": 0, "total_cargados": 0, "errores": 0}

    supabase = _supabase()
    errores = 0
    total_cargados = 0

    logger.info("Cargando %d registros de '%s' en Supabase...", len(registros), entidad)
    inicio = datetime.now(timezone.utc)

    try:
        if entidad == "bodegas":
            total_cargados = cargar_bodegas(supabase, registros, chunk_size)
        elif entidad == "productos":
            total_cargados = cargar_productos(supabase, registros, chunk_size)
        elif entidad == "clientes":
            total_cargados = cargar_clientes(supabase, registros, chunk_size)
        elif entidad == "dtes":
            total_cargados = cargar_dtes(supabase, registros, clientes_map or {}, bodegas_map or {}, chunk_size)
        elif entidad == "ventas_detalle":
            total_cargados = cargar_ventas_detalle(supabase, registros, ventas_map or {}, productos_map or {}, chunk_size)
        elif entidad == "stock":
            total_cargados = cargar_stock(supabase, registros, productos_map or {}, bodegas_map or {}, chunk_size)
        else:
            raise ValueError(f"Entidad '{entidad}' no soportada.")
    except Exception as e:
        logger.error("Error al cargar entidad '%s': %s", entidad, e)
        errores = 1

    duracion = (datetime.now(timezone.utc) - inicio).total_seconds()

    if actualizar_sync:
        _actualizar_sync_log(supabase, entidad, len(registros), total_cargados, errores)

    metricas = {
        "entidad": entidad,
        "total_registros": len(registros),
        "total_cargados": total_cargados,
        "errores": errores,
        "duracion_seg": round(duracion, 2),
    }
    logger.info("Carga '%s': %d/%d en %.1fs", entidad, total_cargados, len(registros), duracion)
    return metricas
