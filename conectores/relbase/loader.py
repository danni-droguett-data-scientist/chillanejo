"""
loader.py — Carga registros transformados a Supabase mediante upsert.

Responsabilidades:
  - Upsert por entidad con la clave correcta para cada tabla.
  - Carga en lotes (chunks) para evitar timeouts en cargas masivas.
  - Actualiza sync_log al terminar cada entidad.
  - Enriquece ventas_detalle con costo_unitario desde productos (opcional).

No transforma ni extrae datos — solo persiste lo que recibe.

Uso:
  from conectores.relbase.loader import cargar_entidad
  cargar_entidad("productos", registros_transformados)
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

# Tamaño de lote para cada upsert (evita timeouts en cargas masivas)
CHUNK_SIZE = int(os.getenv("LOADER_CHUNK_SIZE", "100"))


# ---------------------------------------------------------------------------
# Cliente Supabase
# ---------------------------------------------------------------------------

def _supabase() -> Client:
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise EnvironmentError(
            "Faltan SUPABASE_URL o SUPABASE_SERVICE_ROLE_KEY en .env."
        )
    # service_role omite RLS — correcto para ingesta desde el conector
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)


def _chunks(lista: list, tamaño: int):
    """Genera sub-listas de tamaño fijo."""
    for i in range(0, len(lista), tamaño):
        yield lista[i : i + tamaño]


# ---------------------------------------------------------------------------
# Configuración de upsert por entidad
# ---------------------------------------------------------------------------

# tabla Supabase → clave(s) únicas para el ON CONFLICT
_UPSERT_CONFIG = {
    "dtes":          ("ventas",          "dte_id_relbase"),
    "productos":     ("productos",        "producto_id_relbase"),
    "clientes":      ("clientes",         "cliente_id_relbase"),
    "bodegas":       ("bodegas",          "bodega_id_relbase"),
    "stock":         ("stock",            "producto_id_relbase,bodega_id_relbase"),
    "ventas_detalle":("ventas_detalle",   "dte_id_relbase,numero_linea"),
}


# ---------------------------------------------------------------------------
# Upsert en lotes
# ---------------------------------------------------------------------------

def _upsert_lotes(
    supabase: Client,
    tabla: str,
    registros: list[dict],
    on_conflict: str,
    chunk_size: int = CHUNK_SIZE,
) -> int:
    """
    Upsert de registros en Supabase en lotes.
    Retorna la cantidad total de filas procesadas.
    """
    total = 0
    lotes = list(_chunks(registros, chunk_size))

    for idx, lote in enumerate(lotes, start=1):
        logger.debug(
            "Upsert tabla '%s': lote %d/%d (%d registros)",
            tabla, idx, len(lotes), len(lote),
        )
        resp = (
            supabase.table(tabla)
            .upsert(lote, on_conflict=on_conflict)
            .execute()
        )
        total += len(resp.data or [])

    return total


# ---------------------------------------------------------------------------
# sync_log
# ---------------------------------------------------------------------------

def _actualizar_sync_log(
    supabase: Client,
    entidad: str,
    registros_procesados: int,
    registros_cargados: int,
    errores: int = 0,
) -> None:
    ahora = datetime.now(timezone.utc).isoformat()
    payload = {
        "entidad": entidad,
        "ultimo_sync": ahora,
        "registros_procesados": registros_procesados,
        "registros_cargados": registros_cargados,
        "errores": errores,
        "updated_at": ahora,
    }
    supabase.table("sync_log").upsert(payload, on_conflict="entidad").execute()
    logger.info(
        "sync_log '%s' → procesados=%d | cargados=%d | errores=%d",
        entidad, registros_procesados, registros_cargados, errores,
    )


# ---------------------------------------------------------------------------
# Enriquecimiento: costo_unitario en ventas_detalle
# ---------------------------------------------------------------------------

def enriquecer_costo_unitario(supabase: Client) -> int:
    """
    Actualiza costo_unitario en ventas_detalle cruzando con la tabla productos
    mediante codigo_producto.

    Ejecutar después de cargar productos y ventas_detalle.
    Retorna cantidad de filas actualizadas.
    """
    # Consulta SQL directa via RPC o update con join
    # Supabase SDK no soporta UPDATE con JOIN, se usa rpc o SQL raw.
    # Se implementa con una RPC definida en Supabase (ver migrations).
    try:
        resp = supabase.rpc("enriquecer_costo_unitario_detalle").execute()
        actualizadas = resp.data if isinstance(resp.data, int) else 0
        logger.info("costo_unitario enriquecido en %d filas de ventas_detalle.", actualizadas)
        return actualizadas
    except Exception as e:
        logger.warning(
            "No se pudo ejecutar enriquecer_costo_unitario_detalle (RPC): %s. "
            "Crear la función en Supabase migrations.",
            e,
        )
        return 0


# ---------------------------------------------------------------------------
# Cargadores por entidad
# ---------------------------------------------------------------------------

def cargar_dtes(
    supabase: Client,
    registros: list[dict],
    chunk_size: int = CHUNK_SIZE,
) -> int:
    tabla, on_conflict = _UPSERT_CONFIG["dtes"]
    total = _upsert_lotes(supabase, tabla, registros, on_conflict, chunk_size)
    logger.info("Ventas (DTEs) cargadas: %d", total)
    return total


def cargar_productos(
    supabase: Client,
    registros: list[dict],
    chunk_size: int = CHUNK_SIZE,
) -> int:
    tabla, on_conflict = _UPSERT_CONFIG["productos"]
    total = _upsert_lotes(supabase, tabla, registros, on_conflict, chunk_size)
    logger.info("Productos cargados: %d", total)
    return total


def cargar_clientes(
    supabase: Client,
    registros: list[dict],
    chunk_size: int = CHUNK_SIZE,
) -> int:
    tabla, on_conflict = _UPSERT_CONFIG["clientes"]
    total = _upsert_lotes(supabase, tabla, registros, on_conflict, chunk_size)
    logger.info("Clientes cargados: %d", total)
    return total


def cargar_bodegas(
    supabase: Client,
    registros: list[dict],
    chunk_size: int = CHUNK_SIZE,
) -> int:
    tabla, on_conflict = _UPSERT_CONFIG["bodegas"]
    total = _upsert_lotes(supabase, tabla, registros, on_conflict, chunk_size)
    logger.info("Bodegas cargadas: %d", total)
    return total


def cargar_stock(
    supabase: Client,
    registros: list[dict],
    chunk_size: int = CHUNK_SIZE,
    guardar_historico: bool = True,
) -> int:
    """
    Upsert en stock (snapshot actual) y copia opcional a stock_historico.
    La clave única es (producto_id_relbase, bodega_id_relbase).
    """
    tabla, on_conflict = _UPSERT_CONFIG["stock"]
    total = _upsert_lotes(supabase, tabla, registros, on_conflict, chunk_size)
    logger.info("Stock cargado: %d filas", total)

    if guardar_historico and registros:
        _upsert_lotes(
            supabase,
            "stock_historico",
            registros,
            # stock_historico guarda múltiples snapshots por fecha
            "producto_id_relbase,bodega_id_relbase,fecha_snapshot",
            chunk_size,
        )
        logger.info("Snapshot histórico de stock guardado: %d filas", total)

    return total


def cargar_ventas_detalle(
    supabase: Client,
    registros: list[dict],
    chunk_size: int = CHUNK_SIZE,
) -> int:
    tabla, on_conflict = _UPSERT_CONFIG["ventas_detalle"]
    total = _upsert_lotes(supabase, tabla, registros, on_conflict, chunk_size)
    logger.info("ventas_detalle cargadas: %d líneas", total)
    return total


# ---------------------------------------------------------------------------
# Dispatcher unificado
# ---------------------------------------------------------------------------

_CARGADORES = {
    "dtes":          cargar_dtes,
    "productos":     cargar_productos,
    "clientes":      cargar_clientes,
    "bodegas":       cargar_bodegas,
    "stock":         cargar_stock,
    "ventas_detalle": cargar_ventas_detalle,
}


def cargar_entidad(
    entidad: str,
    registros: list[dict],
    chunk_size: int = CHUNK_SIZE,
    actualizar_sync: bool = True,
) -> dict:
    """
    Punto de entrada único. Carga registros transformados en la tabla correspondiente.

    Args:
        entidad: "dtes" | "productos" | "clientes" | "bodegas" | "stock" | "ventas_detalle"
        registros: lista de dicts producida por transformer.py.
        chunk_size: tamaño del lote de upsert.
        actualizar_sync: si True, registra en sync_log al terminar.

    Returns:
        Dict con métricas: entidad, total_registros, total_cargados, errores.
    """
    if entidad not in _CARGADORES:
        raise ValueError(
            f"Entidad '{entidad}' no soportada. Opciones: {set(_CARGADORES)}"
        )

    if not registros:
        logger.info("cargar_entidad('%s'): lista vacía, nada que cargar.", entidad)
        return {"entidad": entidad, "total_registros": 0, "total_cargados": 0, "errores": 0}

    supabase = _supabase()
    errores = 0
    total_cargados = 0

    logger.info("Cargando %d registros de '%s' en Supabase...", len(registros), entidad)
    inicio = datetime.now(timezone.utc)

    try:
        total_cargados = _CARGADORES[entidad](supabase, registros, chunk_size)
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
    logger.info(
        "Carga '%s' completada: %d/%d en %.1fs",
        entidad, total_cargados, len(registros), duracion,
    )
    return metricas
