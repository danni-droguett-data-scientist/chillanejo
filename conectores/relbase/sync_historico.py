"""
sync_historico.py — Carga histórica inicial desde Relbase hacia Supabase.

Ejecutar UNA VEZ para poblar la base analítica con los últimos 18 meses.
Las sincronizaciones incrementales posteriores usarán sync_incremental.py.

Orden de carga (dependencias):
  1. Bodegas          → seed, sin dependencias
  2. Productos        → necesario antes que stock y ventas_detalle
  3. Clientes         → necesario antes que ventas
  4. Ventas (DTEs)    → depende de clientes y bodegas
  5. Ventas detalle   → depende de ventas y productos
  6. Stock snapshot   → depende de productos y bodegas

Uso:
  python conectores/relbase/sync_historico.py
  python conectores/relbase/sync_historico.py --meses 12
  python conectores/relbase/sync_historico.py --desde 2024-10-01 --hasta 2026-04-30
  python conectores/relbase/sync_historico.py --solo productos clientes
  python conectores/relbase/sync_historico.py --continuar   # saltar etapas ya completadas
"""

import os
import sys
import logging
import argparse
import calendar
from datetime import datetime, timezone, date, timedelta
from typing import Optional

from dotenv import load_dotenv
from supabase import create_client

from conectores.relbase.client import RelbaseClient
from conectores.relbase.extractor import (
    extraer_productos,
    extraer_clientes,
    extraer_dtes,
    extraer_bodegas,
    extraer_stock_todos,
)
from conectores.relbase.transformer import transformar
from conectores.relbase.loader import cargar_entidad, enriquecer_costo_unitario

load_dotenv()

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("sync_historico.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("relbase.sync_historico")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

MESES_DEFAULT = 18

# Tipos de DTE a cargar
TIPOS_DTE = [33, 39, 1001]


# ---------------------------------------------------------------------------
# Helpers de fecha
# ---------------------------------------------------------------------------

def _restar_meses(d: date, meses: int) -> date:
    """Resta N meses a una fecha sin dependencias externas."""
    anio = d.year - (meses // 12)
    mes = d.month - (meses % 12)
    if mes <= 0:
        mes += 12
        anio -= 1
    dia = min(d.day, calendar.monthrange(anio, mes)[1])
    return date(anio, mes, dia)


def _sumar_mes(d: date) -> date:
    """Avanza un mes manteniendo el día (o el último día del mes destino)."""
    mes = d.month + 1 if d.month < 12 else 1
    anio = d.year if d.month < 12 else d.year + 1
    dia = min(d.day, calendar.monthrange(anio, mes)[1])
    return date(anio, mes, dia)


def rango_historico(meses: int = MESES_DEFAULT) -> tuple[str, str]:
    """Retorna (fecha_inicio, fecha_fin) como strings YYYY-MM-DD."""
    hoy = date.today()
    inicio = _restar_meses(hoy, meses)
    return inicio.strftime("%Y-%m-%d"), hoy.strftime("%Y-%m-%d")


def _ahora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Estado de progreso (persiste en sync_log)
# ---------------------------------------------------------------------------

def _etapa_completa(supabase, etapa: str) -> bool:
    """Consulta sync_log para saber si una etapa del histórico ya fue cargada."""
    resp = (
        supabase.table("sync_log")
        .select("ultimo_sync")
        .eq("entidad", f"historico_{etapa}")
        .maybe_single()
        .execute()
    )
    return bool(resp.data)


def _marcar_etapa(supabase, etapa: str, metricas: dict) -> None:
    ahora = _ahora_iso()
    supabase.table("sync_log").upsert(
        {
            "entidad": f"historico_{etapa}",
            "ultimo_sync": ahora,
            "registros_procesados": metricas.get("total_registros", 0),
            "registros_cargados": metricas.get("total_cargados", 0),
            "errores": metricas.get("errores", 0),
            "updated_at": ahora,
        },
        on_conflict="entidad",
    ).execute()


# ---------------------------------------------------------------------------
# Etapas del pipeline
# ---------------------------------------------------------------------------

def etapa_bodegas(client: RelbaseClient, supabase, continuar: bool) -> dict:
    logger.info("── Etapa 1/6: Bodegas ──")
    if continuar and _etapa_completa(supabase, "bodegas"):
        logger.info("Etapa ya completada. Saltando.")
        return {}

    crudos = extraer_bodegas(client._session)
    transformados = transformar("bodegas", crudos)
    metricas = cargar_entidad("bodegas", transformados)
    _marcar_etapa(supabase, "bodegas", metricas)
    return metricas


def etapa_productos(client: RelbaseClient, supabase, continuar: bool) -> dict:
    logger.info("── Etapa 2/6: Productos ──")
    if continuar and _etapa_completa(supabase, "productos"):
        logger.info("Etapa ya completada. Saltando.")
        return {}

    crudos = extraer_productos(client._session)
    transformados = transformar("productos", crudos)
    metricas = cargar_entidad("productos", transformados)
    _marcar_etapa(supabase, "productos", metricas)
    return metricas


def etapa_clientes(client: RelbaseClient, supabase, continuar: bool) -> dict:
    logger.info("── Etapa 3/6: Clientes ──")
    if continuar and _etapa_completa(supabase, "clientes"):
        logger.info("Etapa ya completada. Saltando.")
        return {}

    crudos = extraer_clientes(client._session)
    transformados = transformar("clientes", crudos)
    metricas = cargar_entidad("clientes", transformados)
    _marcar_etapa(supabase, "clientes", metricas)
    return metricas


def etapa_ventas(
    client: RelbaseClient,
    supabase,
    continuar: bool,
    desde: str,
    hasta: str,
) -> dict:
    """
    Carga DTEs por tramos mensuales para evitar requests enormes y facilitar
    la reanudación si el proceso se interrumpe.
    """
    logger.info("── Etapa 4/6: Ventas (DTEs %s → %s) ──", desde, hasta)

    fecha_ini = date.fromisoformat(desde)
    fecha_fin = date.fromisoformat(hasta)
    cursor = fecha_ini
    metricas_total = {"total_registros": 0, "total_cargados": 0, "errores": 0}

    while cursor <= fecha_fin:
        fin_mes = _sumar_mes(cursor) - timedelta(days=1)
        fin_mes = min(fin_mes, fecha_fin)

        tramo = f"{cursor.strftime('%Y-%m')}"
        entidad_log = f"ventas_{tramo}"

        if continuar and _etapa_completa(supabase, entidad_log):
            logger.info("Tramo %s ya cargado. Saltando.", tramo)
        else:
            logger.info("Cargando ventas del tramo %s...", tramo)
            crudos = extraer_dtes(
                client._session,
                tipos=TIPOS_DTE,
                desde_fecha=cursor.strftime("%Y-%m-%d"),
                hasta_fecha=fin_mes.strftime("%Y-%m-%d"),
            )
            transformados = transformar("dtes", crudos)
            metricas = cargar_entidad("dtes", transformados, actualizar_sync=False)
            _marcar_etapa(supabase, entidad_log, metricas)

            metricas_total["total_registros"] += metricas.get("total_registros", 0)
            metricas_total["total_cargados"] += metricas.get("total_cargados", 0)
            metricas_total["errores"] += metricas.get("errores", 0)

        cursor = _sumar_mes(cursor)

    # Registra totales en sync_log con clave canónica
    _marcar_etapa(supabase, "ventas", metricas_total)
    return metricas_total


def etapa_ventas_detalle(supabase, continuar: bool) -> dict:
    """
    Delega en extractor_detalle.py, que lee ventas desde Supabase
    y consulta el detalle de cada DTE en Relbase.
    """
    logger.info("── Etapa 5/6: Ventas detalle ──")
    if continuar and _etapa_completa(supabase, "ventas_detalle"):
        logger.info("Etapa ya completada. Saltando.")
        return {}

    # Importación local para no crear dependencia circular en tests
    from conectores.relbase.extractor_detalle import extraer_y_cargar_detalles

    # batch_size=0 → procesa todos los DTEs sin límite
    metricas = extraer_y_cargar_detalles(batch_size=0)
    _marcar_etapa(supabase, "ventas_detalle", metricas)

    # Enriquece costo_unitario cruzando con productos
    logger.info("Enriqueciendo costo_unitario en ventas_detalle...")
    enriquecer_costo_unitario(supabase)

    return metricas


def etapa_stock(client: RelbaseClient, supabase, continuar: bool) -> dict:
    """Toma un snapshot de stock actual para todos los productos cargados."""
    logger.info("── Etapa 6/6: Stock (snapshot actual) ──")
    if continuar and _etapa_completa(supabase, "stock"):
        logger.info("Etapa ya completada. Saltando.")
        return {}

    # Obtiene IDs de productos desde Supabase (ya cargados en etapa 2)
    resp = (
        supabase.table("productos")
        .select("producto_id_relbase")
        .execute()
    )
    ids_productos = [
        row["producto_id_relbase"]
        for row in (resp.data or [])
        if row.get("producto_id_relbase")
    ]

    if not ids_productos:
        logger.warning("No hay productos en Supabase. Ejecuta etapa_productos primero.")
        return {"total_registros": 0, "total_cargados": 0, "errores": 1}

    logger.info("Obteniendo stock de %d productos...", len(ids_productos))
    crudos = extraer_stock_todos(client._session, ids_productos)
    transformados = transformar("stock", crudos)
    metricas = cargar_entidad("stock", transformados)
    _marcar_etapa(supabase, "stock", metricas)
    return metricas


# ---------------------------------------------------------------------------
# Pipeline principal
# ---------------------------------------------------------------------------

def ejecutar_pipeline(
    desde: str,
    hasta: str,
    etapas: Optional[list[str]] = None,
    continuar: bool = False,
) -> dict:
    """
    Ejecuta el pipeline de carga histórica completo o las etapas indicadas.

    Args:
        desde: fecha inicio YYYY-MM-DD.
        hasta: fecha fin YYYY-MM-DD.
        etapas: lista de etapas a ejecutar. None = todas.
        continuar: si True, salta etapas marcadas como completadas en sync_log.

    Returns:
        Dict con métricas por etapa.
    """
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise EnvironmentError(
            "Faltan SUPABASE_URL o SUPABASE_SERVICE_ROLE_KEY en .env."
        )

    supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
    todas_las_etapas = ["bodegas", "productos", "clientes", "ventas", "ventas_detalle", "stock"]
    etapas_a_ejecutar = etapas or todas_las_etapas

    etapas_invalidas = set(etapas_a_ejecutar) - set(todas_las_etapas)
    if etapas_invalidas:
        raise ValueError(f"Etapas no reconocidas: {etapas_invalidas}. Válidas: {todas_las_etapas}")

    inicio_total = datetime.now(timezone.utc)
    logger.info("=" * 60)
    logger.info("INICIO CARGA HISTÓRICA — %s → %s", desde, hasta)
    logger.info("Etapas: %s", etapas_a_ejecutar)
    logger.info("Modo continuar: %s", continuar)
    logger.info("=" * 60)

    resumen = {}

    with RelbaseClient() as client:

        if "bodegas" in etapas_a_ejecutar:
            resumen["bodegas"] = etapa_bodegas(client, supabase, continuar)

        if "productos" in etapas_a_ejecutar:
            resumen["productos"] = etapa_productos(client, supabase, continuar)

        if "clientes" in etapas_a_ejecutar:
            resumen["clientes"] = etapa_clientes(client, supabase, continuar)

        if "ventas" in etapas_a_ejecutar:
            resumen["ventas"] = etapa_ventas(client, supabase, continuar, desde, hasta)

    # ventas_detalle y stock no necesitan RelbaseClient abierto continuamente
    # (abren su propia sesión internamente)
    if "ventas_detalle" in etapas_a_ejecutar:
        resumen["ventas_detalle"] = etapa_ventas_detalle(supabase, continuar)

    if "stock" in etapas_a_ejecutar:
        with RelbaseClient() as client:
            resumen["stock"] = etapa_stock(client, supabase, continuar)

    duracion_total = (datetime.now(timezone.utc) - inicio_total).total_seconds()

    logger.info("=" * 60)
    logger.info("FIN CARGA HISTÓRICA — %.1f minutos", duracion_total / 60)
    for etapa, m in resumen.items():
        if m:
            logger.info(
                "  %-18s registros=%d | cargados=%d | errores=%d",
                etapa,
                m.get("total_registros", m.get("ventas_procesadas", 0)),
                m.get("total_cargados", m.get("lineas_cargadas", 0)),
                m.get("errores", 0),
            )
    logger.info("=" * 60)

    resumen["_duracion_seg"] = round(duracion_total, 2)
    return resumen


# ---------------------------------------------------------------------------
# Punto de entrada CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Carga histórica inicial desde Relbase hacia Supabase."
    )
    parser.add_argument(
        "--meses",
        type=int,
        default=MESES_DEFAULT,
        help=f"Meses hacia atrás a cargar (default {MESES_DEFAULT}). Ignorado si se usa --desde/--hasta.",
    )
    parser.add_argument(
        "--desde",
        metavar="YYYY-MM-DD",
        help="Fecha inicio del período histórico.",
    )
    parser.add_argument(
        "--hasta",
        metavar="YYYY-MM-DD",
        help="Fecha fin del período histórico (default: hoy).",
    )
    parser.add_argument(
        "--solo",
        nargs="+",
        metavar="ETAPA",
        choices=["bodegas", "productos", "clientes", "ventas", "ventas_detalle", "stock"],
        help="Ejecutar solo las etapas indicadas.",
    )
    parser.add_argument(
        "--continuar",
        action="store_true",
        help="Reanudar carga saltando etapas ya completadas según sync_log.",
    )
    args = parser.parse_args()

    # Resuelve rango de fechas
    if args.desde:
        fecha_inicio = args.desde
        fecha_fin = args.hasta or date.today().strftime("%Y-%m-%d")
    else:
        fecha_inicio, fecha_fin = rango_historico(args.meses)

    logger.info("Período: %s → %s", fecha_inicio, fecha_fin)

    resultado = ejecutar_pipeline(
        desde=fecha_inicio,
        hasta=fecha_fin,
        etapas=args.solo,
        continuar=args.continuar,
    )
    sys.exit(0 if resultado.get("_duracion_seg") else 1)
