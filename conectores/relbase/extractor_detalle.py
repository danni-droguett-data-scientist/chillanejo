"""
extractor_detalle.py — Extrae líneas de detalle de cada DTE desde Relbase
y las carga en la tabla ventas_detalle de Supabase.

Flujo:
  1. Lee ventas pendientes de detalle desde Supabase (tabla ventas).
  2. Por cada venta, llama a GET /api/v1/dtes/{id} en Relbase.
  3. Transforma cada línea al schema de ventas_detalle.
  4. Hace upsert en Supabase.
  5. Registra progreso en sync_log.

Dependencias: requests, supabase, python-dotenv
Rate limit Relbase: 7 req/seg → sleep 0.15s entre llamadas.
"""

import os
import time
import logging
from datetime import datetime, timezone
from typing import Optional

import requests
from dotenv import load_dotenv
from supabase import create_client, Client

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("relbase.extractor_detalle")

RELBASE_BASE_URL = os.getenv("RELBASE_BASE_URL", "https://api.relbase.cl/api/v1")
RELBASE_TOKEN_USUARIO = os.getenv("RELBASE_TOKEN_USUARIO")
RELBASE_TOKEN_EMPRESA = os.getenv("RELBASE_TOKEN_EMPRESA")
RATE_LIMIT_SLEEP = float(os.getenv("RELBASE_RATE_LIMIT_SLEEP", "0.15"))

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

# Clave de sync_log para este proceso
SYNC_ENTIDAD = "ventas_detalle"

# Tamaño del lote de ventas que se procesa por ejecución (0 = todas)
BATCH_SIZE = int(os.getenv("DETALLE_BATCH_SIZE", "200"))


# ---------------------------------------------------------------------------
# Clientes
# ---------------------------------------------------------------------------

def _validar_credenciales() -> None:
    """Aborta si faltan variables de entorno críticas."""
    faltantes = [
        nombre
        for nombre, valor in {
            "RELBASE_TOKEN_USUARIO": RELBASE_TOKEN_USUARIO,
            "RELBASE_TOKEN_EMPRESA": RELBASE_TOKEN_EMPRESA,
            "SUPABASE_URL": SUPABASE_URL,
            "SUPABASE_SERVICE_ROLE_KEY": SUPABASE_SERVICE_ROLE_KEY,
        }.items()
        if not valor
    ]
    if faltantes:
        raise EnvironmentError(
            f"Variables de entorno faltantes: {', '.join(faltantes)}. "
            "Revisa tu archivo .env."
        )


def _headers_relbase() -> dict:
    return {
        "Authorization": RELBASE_TOKEN_USUARIO,
        "Company": RELBASE_TOKEN_EMPRESA,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _supabase_client() -> Client:
    # Usa service_role para saltar RLS en operaciones de ingesta
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)


# ---------------------------------------------------------------------------
# Capa Relbase — solo lectura
# ---------------------------------------------------------------------------

def obtener_detalle_dte(session: requests.Session, dte_id: int) -> Optional[dict]:
    """
    GET /api/v1/dtes/{dte_id}
    Retorna el dict completo del DTE (con sus líneas) o None si hay error.
    """
    url = f"{RELBASE_BASE_URL}/dtes/{dte_id}"
    try:
        response = session.get(url, headers=_headers_relbase(), timeout=30)
        response.raise_for_status()
        return response.json().get("data", {})
    except requests.exceptions.HTTPError as e:
        # 404 puede ocurrir si el DTE fue anulado/eliminado en Relbase
        if e.response.status_code == 404:
            logger.warning("DTE %s no encontrado en Relbase (404). Saltando.", dte_id)
        else:
            logger.error("Error HTTP al obtener DTE %s: %s", dte_id, e)
        return None
    except requests.exceptions.RequestException as e:
        logger.error("Error de red al obtener DTE %s: %s", dte_id, e)
        return None


# ---------------------------------------------------------------------------
# Capa Supabase — consultas
# ---------------------------------------------------------------------------

def obtener_ventas_sin_detalle(supabase: Client, limite: int) -> list[dict]:
    """
    Retorna ventas de Supabase que aún no tienen ninguna línea en ventas_detalle.
    Usa NOT IN sobre ventas_detalle para encontrar DTEs pendientes.
    """
    # IDs de ventas que ya tienen al menos una línea de detalle
    ids_con_detalle_resp = (
        supabase.table("ventas_detalle")
        .select("venta_id")
        .execute()
    )
    ids_con_detalle = {
        row["venta_id"]
        for row in (ids_con_detalle_resp.data or [])
    }

    query = (
        supabase.table("ventas")
        .select("id, dte_id_relbase, tipo_dte, folio")
        .order("fecha_emision", desc=False)
    )
    if limite > 0:
        query = query.limit(limite * 3)  # traemos más para filtrar en memoria

    resp = query.execute()
    ventas_todas = resp.data or []

    # Filtra las que no tienen detalle aún
    pendientes = [v for v in ventas_todas if v["id"] not in ids_con_detalle]

    if limite > 0:
        pendientes = pendientes[:limite]

    logger.info(
        "Ventas totales en Supabase: %d | Sin detalle: %d | A procesar: %d",
        len(ventas_todas),
        len(pendientes),
        len(pendientes),
    )
    return pendientes


def obtener_ultima_ejecucion(supabase: Client) -> Optional[datetime]:
    """Lee el timestamp de la última ejecución exitosa desde sync_log."""
    resp = (
        supabase.table("sync_log")
        .select("ultimo_sync")
        .eq("entidad", SYNC_ENTIDAD)
        .maybe_single()
        .execute()
    )
    if resp.data:
        return datetime.fromisoformat(resp.data["ultimo_sync"])
    return None


# ---------------------------------------------------------------------------
# Transformación Relbase → Supabase
# ---------------------------------------------------------------------------

def _safe_float(valor) -> Optional[float]:
    """Convierte a float de forma segura, retorna None si falla."""
    try:
        return float(valor) if valor is not None else None
    except (TypeError, ValueError):
        return None


def _safe_int(valor) -> Optional[int]:
    try:
        return int(valor) if valor is not None else None
    except (TypeError, ValueError):
        return None


def transformar_lineas(venta: dict, dte_data: dict) -> list[dict]:
    """
    Mapea las líneas (items) del DTE de Relbase al schema de ventas_detalle.

    Campos de Relbase (nombre tentativo — ajustar según respuesta real de la API):
      numero_linea, codigo, descripcion, cantidad,
      precio_unitario, descuento_porcentaje, descuento_monto,
      subtotal_neto, subtotal_bruto

    El campo margen_neto es calculado por trigger en Supabase, no se envía.
    """
    ahora = datetime.now(timezone.utc).isoformat()
    # Relbase puede usar "items" o "lineas" según versión del endpoint
    items = dte_data.get("items") or dte_data.get("lineas") or []

    if not items:
        logger.debug(
            "DTE %s (venta_id=%s) no tiene líneas en la respuesta.",
            venta["dte_id_relbase"],
            venta["id"],
        )
        return []

    lineas_transformadas = []
    for item in items:
        precio_unitario = _safe_float(item.get("precio_unitario"))
        cantidad = _safe_float(item.get("cantidad"))
        descuento_pct = _safe_float(item.get("descuento_porcentaje")) or 0.0

        # Subtotal neto: preferimos el valor de Relbase; calculamos como fallback
        subtotal_neto = _safe_float(item.get("subtotal_neto"))
        if subtotal_neto is None and precio_unitario and cantidad:
            subtotal_neto = round(
                precio_unitario * cantidad * (1 - descuento_pct / 100), 2
            )

        subtotal_bruto = _safe_float(item.get("subtotal_bruto"))

        # IVA implícito cuando existe subtotal neto y bruto
        iva_monto = None
        iva_porcentaje = None
        if subtotal_bruto is not None and subtotal_neto is not None:
            iva_monto = round(subtotal_bruto - subtotal_neto, 2)
            if subtotal_neto > 0:
                iva_porcentaje = round((iva_monto / subtotal_neto) * 100, 2)

        linea = {
            # Claves de relación
            "venta_id": venta["id"],
            "dte_id_relbase": venta["dte_id_relbase"],

            # Identificación de línea
            "numero_linea": _safe_int(item.get("numero_linea")) or _safe_int(item.get("nro_linea")),
            "codigo_producto": str(item.get("codigo") or item.get("codigo_producto") or ""),
            "nombre_producto": str(item.get("descripcion") or item.get("nombre") or ""),

            # Cantidades y precios
            "cantidad": cantidad,
            "precio_unitario_neto": precio_unitario,
            "precio_unitario_bruto": _safe_float(item.get("precio_unitario_bruto")),
            "descuento_porcentaje": descuento_pct,
            "descuento_monto": _safe_float(item.get("descuento_monto")),

            # Subtotales
            "subtotal_neto": subtotal_neto,
            "subtotal_bruto": subtotal_bruto,

            # IVA
            "iva_porcentaje": iva_porcentaje,
            "iva_monto": iva_monto,

            # costo_unitario y margen_neto se populan desde productos o por trigger
            "costo_unitario": None,

            # Trazabilidad
            "fuente": "relbase",
            "updated_at": ahora,
        }
        lineas_transformadas.append(linea)

    return lineas_transformadas


# ---------------------------------------------------------------------------
# Carga a Supabase
# ---------------------------------------------------------------------------

def upsert_lineas(supabase: Client, lineas: list[dict]) -> int:
    """
    Upsert de líneas en ventas_detalle.
    Clave única compuesta: (dte_id_relbase, numero_linea).
    Retorna la cantidad de filas procesadas.
    """
    if not lineas:
        return 0

    resp = (
        supabase.table("ventas_detalle")
        .upsert(lineas, on_conflict="dte_id_relbase,numero_linea")
        .execute()
    )
    return len(resp.data or [])


# ---------------------------------------------------------------------------
# Registro en sync_log
# ---------------------------------------------------------------------------

def actualizar_sync_log(
    supabase: Client,
    total_procesadas: int,
    total_lineas: int,
    errores: int,
    ultimo_dte_id: Optional[int] = None,
) -> None:
    ahora = datetime.now(timezone.utc).isoformat()
    payload = {
        "entidad": SYNC_ENTIDAD,
        "ultimo_sync": ahora,
        "registros_procesados": total_procesadas,
        "registros_cargados": total_lineas,
        "errores": errores,
        "ultimo_id_procesado": ultimo_dte_id,
        "updated_at": ahora,
    }
    supabase.table("sync_log").upsert(payload, on_conflict="entidad").execute()
    logger.info(
        "sync_log actualizado — ventas: %d | líneas: %d | errores: %d",
        total_procesadas,
        total_lineas,
        errores,
    )


# ---------------------------------------------------------------------------
# Orquestador principal
# ---------------------------------------------------------------------------

def extraer_y_cargar_detalles(
    batch_size: int = BATCH_SIZE,
    forzar_todos: bool = False,
) -> dict:
    """
    Proceso completo: extrae detalles de líneas desde Relbase y los carga en Supabase.

    Args:
        batch_size: máximo de ventas a procesar en esta ejecución (0 = todas).
        forzar_todos: si True, reprocesa ventas que ya tienen detalle.

    Returns:
        Diccionario con métricas de la ejecución.
    """
    _validar_credenciales()
    supabase = _supabase_client()

    logger.info("=== Inicio extracción detalle de ventas ===")
    inicio = datetime.now(timezone.utc)

    # Obtiene lista de ventas a procesar
    if forzar_todos:
        resp = (
            supabase.table("ventas")
            .select("id, dte_id_relbase, tipo_dte, folio")
            .order("fecha_emision", desc=False)
            .execute()
        )
        ventas = resp.data or []
        if batch_size > 0:
            ventas = ventas[:batch_size]
    else:
        ventas = obtener_ventas_sin_detalle(supabase, limite=batch_size)

    if not ventas:
        logger.info("No hay ventas pendientes de detalle. Fin.")
        return {"ventas_procesadas": 0, "lineas_cargadas": 0, "errores": 0}

    total_ventas = len(ventas)
    total_lineas = 0
    errores = 0
    ultimo_dte_id = None

    session = requests.Session()

    for idx, venta in enumerate(ventas, start=1):
        dte_id = venta.get("dte_id_relbase")
        if not dte_id:
            logger.warning("Venta %s no tiene dte_id_relbase. Saltando.", venta["id"])
            errores += 1
            continue

        logger.debug(
            "[%d/%d] Obteniendo detalle DTE %s (folio %s, tipo %s)",
            idx, total_ventas, dte_id, venta.get("folio"), venta.get("tipo_dte"),
        )

        # Respeta rate limit antes de cada llamada
        time.sleep(RATE_LIMIT_SLEEP)

        dte_data = obtener_detalle_dte(session, dte_id)
        if dte_data is None:
            errores += 1
            continue

        lineas = transformar_lineas(venta, dte_data)
        if lineas:
            cargadas = upsert_lineas(supabase, lineas)
            total_lineas += cargadas
            logger.debug("DTE %s → %d líneas cargadas.", dte_id, cargadas)
        else:
            # DTE sin líneas (puede ser válido para algunos tipos)
            logger.debug("DTE %s sin líneas de detalle.", dte_id)

        ultimo_dte_id = dte_id

        # Log de progreso cada 50 ventas
        if idx % 50 == 0:
            logger.info(
                "Progreso: %d/%d ventas | %d líneas acumuladas | %d errores",
                idx, total_ventas, total_lineas, errores,
            )

    session.close()

    # Actualiza sync_log con resultado de la ejecución
    actualizar_sync_log(supabase, total_ventas, total_lineas, errores, ultimo_dte_id)

    duracion = (datetime.now(timezone.utc) - inicio).total_seconds()
    metricas = {
        "ventas_procesadas": total_ventas,
        "lineas_cargadas": total_lineas,
        "errores": errores,
        "duracion_seg": round(duracion, 2),
    }
    logger.info(
        "=== Fin extracción detalle === ventas=%d | líneas=%d | errores=%d | %.1fs",
        total_ventas, total_lineas, errores, duracion,
    )
    return metricas


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Extrae detalle de líneas de DTEs desde Relbase hacia Supabase."
    )
    parser.add_argument(
        "--batch",
        type=int,
        default=BATCH_SIZE,
        help=f"Máximo de ventas a procesar (0 = todas). Default: {BATCH_SIZE}",
    )
    parser.add_argument(
        "--forzar",
        action="store_true",
        help="Reprocesa ventas que ya tienen detalle en Supabase.",
    )
    args = parser.parse_args()

    resultado = extraer_y_cargar_detalles(
        batch_size=args.batch,
        forzar_todos=args.forzar,
    )
    print(resultado)
