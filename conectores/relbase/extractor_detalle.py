"""
extractor_detalle.py — Extrae líneas de detalle de cada DTE desde Relbase
y las carga en la tabla ventas_detalle de Supabase.

Flujo:
  1. Carga todas las ventas desde Supabase (paginando el límite 1000 de PostgREST).
  2. Filtra las que ya tienen detalle en ventas_detalle (para reanudar si se interrumpe).
  3. Por cada venta pendiente, llama GET /api/v1/dtes/{relbase_id} en paralelo.
  4. Transforma cada línea al schema real de ventas_detalle.
  5. Resuelve FK producto_id via productos_map.
  6. Inserta en ventas_detalle (insert directo, sin upsert — sin clave única compuesta).
  7. Registra resultado en sync_log.
"""

import os
import time
import threading
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Optional

import requests
from dotenv import load_dotenv
from supabase import Client

load_dotenv()

logger = logging.getLogger("relbase.extractor_detalle")

RELBASE_BASE_URL = os.getenv("RELBASE_BASE_URL", "https://api.relbase.cl/api/v1")
RELBASE_TOKEN_USUARIO = os.getenv("RELBASE_TOKEN_USUARIO")
RELBASE_TOKEN_EMPRESA = os.getenv("RELBASE_TOKEN_EMPRESA")
# 6 req/seg (conservador bajo el límite de 7) — más workers no ayuda porque el
# cuello de botella es el rate limit, no la latencia
MAX_WORKERS = int(os.getenv("RELBASE_MAX_WORKERS", "6"))
_MIN_INTERVAL = 1.0 / float(os.getenv("RELBASE_RATE_MAX", "6"))  # seg entre requests
CHUNK_SIZE = int(os.getenv("LOADER_CHUNK_SIZE", "100"))
BATCH_SIZE = int(os.getenv("DETALLE_BATCH_SIZE", "0"))  # 0 = todas

# Rate limiter global: serializa el inicio de cada request para no superar 7 req/seg
_rate_lock = threading.Lock()
_last_request_time: float = 0.0


def _rate_limit() -> None:
    """Bloquea el hilo actual hasta que sea seguro hacer el próximo request."""
    global _last_request_time
    with _rate_lock:
        now = time.time()
        wait = _MIN_INTERVAL - (now - _last_request_time)
        if wait > 0:
            time.sleep(wait)
        _last_request_time = time.time()


def _headers_relbase() -> dict:
    return {
        "Authorization": RELBASE_TOKEN_USUARIO,
        "Company": RELBASE_TOKEN_EMPRESA,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


# ---------------------------------------------------------------------------
# Consultas Supabase
# ---------------------------------------------------------------------------

def _obtener_todas_ventas(supabase: Client) -> list[dict]:
    """Carga todas las ventas de Supabase paginando el límite 1000 de PostgREST."""
    resultado = []
    page_size = 1000
    offset = 0
    while True:
        resp = (
            supabase.table("ventas")
            .select("id,relbase_id,tipo_documento,folio")
            .order("fecha_emision", desc=False)
            .range(offset, offset + page_size - 1)
            .execute()
        )
        filas = resp.data or []
        resultado.extend(filas)
        if len(filas) < page_size:
            break
        offset += page_size
    return resultado


def _venta_ids_con_detalle(supabase: Client) -> set:
    """Retorna el conjunto de venta_ids que ya tienen al menos una línea en ventas_detalle."""
    ids: set = set()
    page_size = 1000
    offset = 0
    while True:
        resp = (
            supabase.table("ventas_detalle")
            .select("venta_id")
            .range(offset, offset + page_size - 1)
            .execute()
        )
        filas = resp.data or []
        for row in filas:
            ids.add(row["venta_id"])
        if len(filas) < page_size:
            break
        offset += page_size
    return ids


# ---------------------------------------------------------------------------
# Extracción Relbase
# ---------------------------------------------------------------------------

def _fetch_items_dte(
    session: requests.Session, dte_relbase_id: int, max_retries: int = 3
) -> tuple[int, Optional[list]]:
    """
    GET /api/v1/dtes/{dte_relbase_id}
    Retorna (dte_relbase_id, items) — items=[] si no tiene lineas, None si hay error.
    Respeta el rate limit global y reintenta en caso de 429.
    """
    url = f"{RELBASE_BASE_URL}/dtes/{dte_relbase_id}"
    for attempt in range(max_retries):
        _rate_limit()
        try:
            resp = session.get(url, headers=_headers_relbase(), timeout=30)
            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", 60))
                logger.warning("429 DTE %s — esperando %ds (intento %d)", dte_relbase_id, wait, attempt + 1)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            data = resp.json().get("data", {})
            if isinstance(data, dict):
                items = (
                    data.get("products")
                    or data.get("items")
                    or data.get("lineas")
                    or data.get("detail")
                    or []
                )
            else:
                items = []
            return dte_relbase_id, items
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                return dte_relbase_id, []  # DTE anulado/eliminado — no es error
            logger.error("Error HTTP DTE %s (intento %d): %s", dte_relbase_id, attempt + 1, e)
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
            return dte_relbase_id, None
        except Exception as e:
            logger.error("Error red DTE %s (intento %d): %s", dte_relbase_id, attempt + 1, e)
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
            return dte_relbase_id, None
    return dte_relbase_id, None


# ---------------------------------------------------------------------------
# Transformación y resolución de FKs
# ---------------------------------------------------------------------------

def _transformar_y_resolver(
    items: list,
    venta_db_id: int,
    dte_relbase_id: int,
    productos_map: dict,
) -> list[dict]:
    """
    Transforma ítems de un DTE y resuelve FKs.
    Usa transformer.transformar_lineas_detalle() para el mapeo de campos.
    """
    from conectores.relbase.transformer import transformar_lineas_detalle

    lineas_raw = transformar_lineas_detalle(items, dte_relbase_id)
    lineas = []
    for linea in lineas_raw:
        linea.pop("_venta_relbase_id", None)
        linea["venta_id"] = venta_db_id

        prod_relbase = linea.pop("_producto_relbase_id", None)
        linea["producto_id"] = productos_map.get(prod_relbase) if productos_map else None

        lineas.append(linea)
    return lineas


# ---------------------------------------------------------------------------
# Carga a Supabase
# ---------------------------------------------------------------------------

def _insertar_lineas(supabase: Client, lineas: list[dict]) -> int:
    """Insert en lotes. Retorna cantidad de filas insertadas."""
    if not lineas:
        return 0
    total = 0
    for i in range(0, len(lineas), CHUNK_SIZE):
        lote = lineas[i : i + CHUNK_SIZE]
        resp = supabase.table("ventas_detalle").insert(lote).execute()
        total += len(resp.data or [])
    return total


# ---------------------------------------------------------------------------
# Sync log
# ---------------------------------------------------------------------------

def _registrar_sync_log(supabase: Client, lineas: int, errores: int) -> None:
    ahora = datetime.now(timezone.utc).isoformat()
    payload = {
        "entidad": "ventas_detalle",
        "fuente": "relbase",
        "ultima_sync": ahora,
        "registros_nuevos": lineas,
        "registros_error": errores,
        "estado": "ok" if errores == 0 else "error_parcial",
    }
    try:
        supabase.table("sync_log").insert(payload).execute()
    except Exception as e:
        logger.warning("sync_log insert falló: %s", e)


# ---------------------------------------------------------------------------
# Orquestador principal
# ---------------------------------------------------------------------------

def extraer_y_cargar_detalles(
    batch_size: int = BATCH_SIZE,
    forzar_todos: bool = False,
    ventas_map: Optional[dict] = None,
    productos_map: Optional[dict] = None,
) -> dict:
    """
    Extrae detalle de DTEs desde Relbase y carga en ventas_detalle de Supabase.

    Args:
        batch_size: máximo de ventas a procesar (0 = todas).
        forzar_todos: si True, reprocesa ventas que ya tienen detalle.
        ventas_map: {relbase_id: db_id} — aceptado por compatibilidad; no se usa
                    directamente (se obtiene el db_id de la consulta a Supabase).
        productos_map: {relbase_id: db_id} de productos — resuelve producto_id FK.

    Returns:
        Diccionario con métricas: ventas_procesadas, lineas_cargadas, errores, duracion_seg.
    """
    from conectores.relbase.loader import _supabase
    supabase = _supabase()

    logger.info("=== Inicio extracción detalle de ventas ===")
    inicio = datetime.now(timezone.utc)

    logger.info("Cargando ventas desde Supabase...")
    todas_ventas = _obtener_todas_ventas(supabase)
    logger.info("Total ventas en Supabase: %d", len(todas_ventas))

    if not forzar_todos:
        ids_con_detalle = _venta_ids_con_detalle(supabase)
        logger.info("Ventas con detalle ya cargado: %d", len(ids_con_detalle))
        ventas_pendientes = [v for v in todas_ventas if v["id"] not in ids_con_detalle]
    else:
        ventas_pendientes = list(todas_ventas)

    if batch_size > 0:
        ventas_pendientes = ventas_pendientes[:batch_size]

    total_ventas = len(ventas_pendientes)
    logger.info("Ventas a procesar: %d", total_ventas)

    if not ventas_pendientes:
        logger.info("No hay ventas pendientes de detalle. Fin.")
        return {"ventas_procesadas": 0, "lineas_cargadas": 0, "errores": 0, "duracion_seg": 0}

    total_lineas = 0
    errores = 0
    procesadas = 0
    productos_map = productos_map or {}

    session = requests.Session()
    lote_size = 500
    total_lotes = (total_ventas + lote_size - 1) // lote_size

    for lote_num, batch_inicio in enumerate(range(0, total_ventas, lote_size), start=1):
        lote_ventas = ventas_pendientes[batch_inicio : batch_inicio + lote_size]

        # Fetch paralelo de todos los DTEs del lote
        resultados_fetch: dict[int, Optional[list]] = {}
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futuros = {
                pool.submit(_fetch_items_dte, session, v["relbase_id"]): v["relbase_id"]
                for v in lote_ventas
            }
            for futuro in as_completed(futuros):
                dte_relbase_id, items = futuro.result()
                resultados_fetch[dte_relbase_id] = items

        # Transforma y acumula líneas
        lineas_lote: list[dict] = []
        for venta in lote_ventas:
            items = resultados_fetch.get(venta["relbase_id"])
            if items is None:
                errores += 1
                continue
            if items:
                lineas = _transformar_y_resolver(
                    items, venta["id"], venta["relbase_id"], productos_map
                )
                lineas_lote.extend(lineas)
            procesadas += 1

        # Insert del lote completo
        if lineas_lote:
            cargadas = _insertar_lineas(supabase, lineas_lote)
            total_lineas += cargadas

        logger.info(
            "Lote %d/%d — ventas procesadas: %d | líneas totales: %d | errores: %d",
            lote_num, total_lotes, procesadas, total_lineas, errores,
        )

    session.close()

    _registrar_sync_log(supabase, total_lineas, errores)

    duracion = (datetime.now(timezone.utc) - inicio).total_seconds()
    metricas = {
        "ventas_procesadas": procesadas,
        "lineas_cargadas": total_lineas,
        "errores": errores,
        "duracion_seg": round(duracion, 2),
    }
    logger.info(
        "=== Fin detalle === ventas=%d | líneas=%d | errores=%d | %.1fs",
        procesadas, total_lineas, errores, duracion,
    )
    return metricas


# ---------------------------------------------------------------------------
# Punto de entrada CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    import sys

    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    parser = argparse.ArgumentParser(
        description="Extrae detalle de DTEs desde Relbase hacia Supabase."
    )
    parser.add_argument(
        "--batch", type=int, default=0,
        help="Máximo de ventas a procesar (0 = todas).",
    )
    parser.add_argument(
        "--forzar", action="store_true",
        help="Reprocesa ventas que ya tienen detalle en Supabase.",
    )
    args = parser.parse_args()

    resultado = extraer_y_cargar_detalles(
        batch_size=args.batch,
        forzar_todos=args.forzar,
    )
    print(resultado)
    sys.exit(0 if resultado.get("errores", 1) == 0 else 1)
