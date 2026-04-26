"""
sync_incremental.py — Sincronización diaria incremental Relbase → Supabase.

Ejecutar a diario (vía n8n o cron). Extrae solo los cambios del período
especificado usando sync_log para determinar desde dónde retomar.

Entidades sincronizadas:
  - Productos    → cambios de precio, costo, stock_minimo
  - Clientes     → nuevos y actualizados
  - Ventas       → DTEs del período (default: hoy)
  - Ventas det.  → líneas de ventas nuevas
  - Stock        → snapshot actual (siempre completo)

Uso:
  python conectores/relbase/sync_incremental.py
  python conectores/relbase/sync_incremental.py --desde 2026-04-20
  python conectores/relbase/sync_incremental.py --solo ventas stock
"""

import os
import sys
import logging
import argparse
from datetime import date, datetime, timezone, timedelta
from typing import Optional

from dotenv import load_dotenv
from supabase import create_client

from conectores.relbase.client import RelbaseClient
from conectores.relbase.extractor import (
    extraer_productos,
    extraer_clientes,
    extraer_dtes,
    extraer_stock_todos,
)
from conectores.relbase.transformer import transformar
from conectores.relbase.loader import cargar_entidad, enriquecer_costo_unitario
from conectores.relbase.extractor_detalle import extraer_y_cargar_detalles

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("sync_incremental.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("relbase.sync_incremental")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

# Ventana de seguridad: retrocede N días extra para capturar cambios tardíos
VENTANA_SEGURIDAD_DIAS = int(os.getenv("SYNC_VENTANA_SEGURIDAD_DIAS", "1"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _supabase():
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise EnvironmentError("Faltan SUPABASE_URL o SUPABASE_SERVICE_ROLE_KEY en .env.")
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)


def _ultimo_sync(supabase, entidad: str) -> Optional[str]:
    """
    Lee el último sync exitoso desde sync_log.
    Aplica ventana de seguridad hacia atrás para no perder cambios tardíos.
    """
    resp = (
        supabase.table("sync_log")
        .select("ultimo_sync")
        .eq("entidad", entidad)
        .maybe_single()
        .execute()
    )
    if not resp.data:
        return None
    ultimo = datetime.fromisoformat(resp.data["ultimo_sync"]).date()
    con_ventana = ultimo - timedelta(days=VENTANA_SEGURIDAD_DIAS)
    return con_ventana.strftime("%Y-%m-%d")


def _fecha_default() -> str:
    return date.today().strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Etapas incrementales
# ---------------------------------------------------------------------------

def sync_productos(client: RelbaseClient, supabase, desde: Optional[str]) -> dict:
    desde_efectivo = desde or _ultimo_sync(supabase, "productos") or _fecha_default()
    logger.info("Sync productos desde %s", desde_efectivo)
    crudos = extraer_productos(client._session, desde_fecha=desde_efectivo)
    if not crudos:
        logger.info("Sin cambios en productos.")
        return {"total_registros": 0, "total_cargados": 0, "errores": 0}
    transformados = transformar("productos", crudos)
    return cargar_entidad("productos", transformados)


def sync_clientes(client: RelbaseClient, supabase, desde: Optional[str]) -> dict:
    desde_efectivo = desde or _ultimo_sync(supabase, "clientes") or _fecha_default()
    logger.info("Sync clientes desde %s", desde_efectivo)
    crudos = extraer_clientes(client._session, desde_fecha=desde_efectivo)
    if not crudos:
        logger.info("Sin cambios en clientes.")
        return {"total_registros": 0, "total_cargados": 0, "errores": 0}
    transformados = transformar("clientes", crudos)
    return cargar_entidad("clientes", transformados)


def sync_ventas(
    client: RelbaseClient,
    supabase,
    desde: Optional[str],
    hasta: Optional[str],
) -> dict:
    desde_efectivo = desde or _ultimo_sync(supabase, "dtes") or _fecha_default()
    hasta_efectivo = hasta or _fecha_default()
    logger.info("Sync ventas %s → %s", desde_efectivo, hasta_efectivo)
    crudos = extraer_dtes(
        client._session,
        desde_fecha=desde_efectivo,
        hasta_fecha=hasta_efectivo,
    )
    if not crudos:
        logger.info("Sin ventas nuevas en el período.")
        return {"total_registros": 0, "total_cargados": 0, "errores": 0}
    transformados = transformar("dtes", crudos)
    return cargar_entidad("dtes", transformados)


def sync_ventas_detalle(supabase) -> dict:
    """
    Procesa ventas nuevas que aún no tienen detalle en ventas_detalle.
    batch_size=500 para no sobrecargar en días con muchas ventas.
    """
    logger.info("Sync ventas_detalle (batch 500)...")
    metricas = extraer_y_cargar_detalles(batch_size=500)
    enriquecer_costo_unitario(supabase)
    return metricas


def sync_stock(client: RelbaseClient, supabase) -> dict:
    """Stock siempre es snapshot completo (no incremental)."""
    logger.info("Sync stock (snapshot completo)...")
    resp = (
        supabase.table("productos")
        .select("producto_id_relbase")
        .execute()
    )
    ids_productos = [
        r["producto_id_relbase"]
        for r in (resp.data or [])
        if r.get("producto_id_relbase")
    ]
    if not ids_productos:
        logger.warning("Sin productos en Supabase. Ejecutar sync_historico primero.")
        return {"total_registros": 0, "total_cargados": 0, "errores": 1}
    crudos = extraer_stock_todos(client._session, ids_productos)
    transformados = transformar("stock", crudos)
    return cargar_entidad("stock", transformados)


# ---------------------------------------------------------------------------
# Pipeline incremental
# ---------------------------------------------------------------------------

ETAPAS_DISPONIBLES = ["productos", "clientes", "ventas", "ventas_detalle", "stock"]


def ejecutar_sync(
    desde: Optional[str] = None,
    hasta: Optional[str] = None,
    etapas: Optional[list[str]] = None,
) -> dict:
    supabase = _supabase()
    etapas_a_ejecutar = etapas or ETAPAS_DISPONIBLES

    invalidas = set(etapas_a_ejecutar) - set(ETAPAS_DISPONIBLES)
    if invalidas:
        raise ValueError(f"Etapas no reconocidas: {invalidas}")

    inicio = datetime.now(timezone.utc)
    logger.info("=== SYNC INCREMENTAL %s ===", inicio.strftime("%Y-%m-%d %H:%M UTC"))

    resumen = {}

    with RelbaseClient() as client:
        if "productos" in etapas_a_ejecutar:
            resumen["productos"] = sync_productos(client, supabase, desde)

        if "clientes" in etapas_a_ejecutar:
            resumen["clientes"] = sync_clientes(client, supabase, desde)

        if "ventas" in etapas_a_ejecutar:
            resumen["ventas"] = sync_ventas(client, supabase, desde, hasta)

        if "stock" in etapas_a_ejecutar:
            resumen["stock"] = sync_stock(client, supabase)

    if "ventas_detalle" in etapas_a_ejecutar:
        resumen["ventas_detalle"] = sync_ventas_detalle(supabase)

    duracion = (datetime.now(timezone.utc) - inicio).total_seconds()
    logger.info(
        "=== FIN SYNC %.1fs — %s ===",
        duracion,
        " | ".join(
            f"{e}: {m.get('total_cargados', m.get('lineas_cargadas', 0))} reg"
            for e, m in resumen.items()
            if m
        ),
    )
    resumen["_duracion_seg"] = round(duracion, 2)
    return resumen


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Sincronización incremental diaria Relbase → Supabase."
    )
    parser.add_argument("--desde", metavar="YYYY-MM-DD", help="Forzar fecha inicio")
    parser.add_argument("--hasta", metavar="YYYY-MM-DD", help="Forzar fecha fin")
    parser.add_argument(
        "--solo",
        nargs="+",
        metavar="ETAPA",
        choices=ETAPAS_DISPONIBLES,
        help="Ejecutar solo estas etapas",
    )
    args = parser.parse_args()

    resultado = ejecutar_sync(
        desde=args.desde,
        hasta=args.hasta,
        etapas=args.solo,
    )
    sys.exit(0 if not resultado.get("_duracion_seg") is None else 1)
