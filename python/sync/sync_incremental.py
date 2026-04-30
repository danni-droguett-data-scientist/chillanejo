"""
sync_incremental.py
Sincronización incremental diaria de ventas desde Relbase hacia Supabase.
Trae todas las páginas del día actual y hace upsert en la tabla ventas.

Reglas de código aplicadas:
- Claridad antes que inteligencia
- Funciones con una responsabilidad
- Manejo de errores explícito
- Sin credenciales en código — usar .env
- Logging útil en cada paso
"""

import os
import time
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv

# --- Configuración ---
load_dotenv()

RELBASE_BASE_URL = os.environ.get("RELBASE_BASE_URL", "")
RELBASE_TOKEN_USUARIO = os.environ.get("RELBASE_TOKEN_USUARIO", "")
RELBASE_TOKEN_EMPRESA = os.environ.get("RELBASE_TOKEN_EMPRESA", "")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

# Debug de variables de entorno al arranque
_ENV_VARS = {
    "RELBASE_BASE_URL":      RELBASE_BASE_URL,
    "RELBASE_TOKEN_USUARIO": RELBASE_TOKEN_USUARIO,
    "RELBASE_TOKEN_EMPRESA": RELBASE_TOKEN_EMPRESA,
    "SUPABASE_URL":          SUPABASE_URL,
    "SUPABASE_SERVICE_ROLE_KEY": SUPABASE_SERVICE_ROLE,
}
_presentes = [k for k, v in _ENV_VARS.items() if v]
_faltantes  = [k for k, v in _ENV_VARS.items() if not v]
log.debug("Variables de entorno presentes: %s", _presentes)
if _faltantes:
    log.warning("Variables de entorno FALTANTES: %s", _faltantes)


def fecha_hoy_chile() -> str:
    """Retorna la fecha actual en zona horaria de Santiago en formato YYYY-MM-DD."""
    return datetime.now(ZoneInfo("America/Santiago")).strftime("%Y-%m-%d")


def headers_relbase() -> dict:
    """Headers de autenticación para la API de Relbase."""
    return {
        "Authorization": RELBASE_TOKEN_USUARIO,
        "Company":       RELBASE_TOKEN_EMPRESA,
    }


def headers_supabase() -> dict:
    """Headers de autenticación para la API REST de Supabase."""
    return {
        "apikey":        SUPABASE_SERVICE_ROLE,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE}",
        "Content-Type":  "application/json",
        "Prefer":        "resolution=merge-duplicates",
    }


def fetch_pagina_relbase(fecha: str, pagina: int) -> dict:
    """
    Fetcha una página de DTEs desde Relbase para la fecha dada.
    Retorna el JSON completo de la respuesta.
    """
    url = f"{RELBASE_BASE_URL}/api/v1/dtes"
    params = {
        "start_date":    fecha,
        "end_date":      fecha,
        "type_document": 1001,
        "page":          pagina,
    }
    response = requests.get(
        url, headers=headers_relbase(), params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def fetch_todas_las_ventas(fecha: str) -> list:
    """
    Itera todas las páginas de Relbase para la fecha dada.
    Retorna lista con todos los DTEs del día.
    """
    dtes = []
    pagina = 1

    while True:
        log.info(f"Fetching página {pagina} de Relbase para {fecha}...")
        data = fetch_pagina_relbase(fecha, pagina)

        items = data.get("data", {}).get("dtes", [])
        dtes.extend(items)

        meta = data.get("meta", {})
        total_paginas = meta.get("total_pages", 1)
        next_page = meta.get("next_page", -1)

        log.info(
            f"  Página {pagina}/{total_paginas} — {len(items)} DTEs obtenidos")

        # Relbase indica no hay más páginas con next_page < 0
        if not next_page or next_page < 0 or pagina >= total_paginas:
            break

        pagina += 1
        time.sleep(0.2)  # Pausa entre requests para no saturar la API

    log.info(f"Total DTEs fetched: {len(dtes)}")
    return dtes


def mapear_venta(d: dict) -> dict:
    """
    Transforma un DTE de Relbase al esquema de la tabla ventas en Supabase.
    Solo extrae los campos analíticos necesarios.
    """
    return {
        "relbase_id":     d.get("id"),
        "tipo_documento": d.get("type_document"),
        "folio":          d.get("folio"),
        "estado_sii":     d.get("sii_status_name"),
        "fecha_emision":  (d.get("start_date") or "")[:10] or None,
        "neto":           d.get("amount_neto", 0),
        "iva":            d.get("amount_iva", 0),
        "total":          d.get("amount_total", 0),
        "vendedor":       d.get("vendedor_nombre"),
        "forma_pago":     d.get("payment_method_name"),
        "canal":          "presencial",
    }


def upsert_ventas_supabase(ventas: list) -> None:
    """
    Hace upsert del batch de ventas en Supabase.
    Usa on_conflict=relbase_id para evitar duplicados.
    """
    if not ventas:
        log.info("No hay ventas para hacer upsert.")
        return

    url = f"{SUPABASE_URL}/rest/v1/ventas"
    params = {"on_conflict": "relbase_id"}

    response = requests.post(
        url,
        headers=headers_supabase(),
        params=params,
        json=ventas,
        timeout=60,
    )

    if response.status_code in (200, 201):
        log.info(f"Upsert exitoso: {len(ventas)} ventas.")
    else:
        log.error(f"Error en upsert: {response.status_code} — {response.text}")
        response.raise_for_status()


def actualizar_sync_log(fecha: str, total: int) -> None:
    """Registra el resultado del sync en la tabla sync_log de Supabase."""
    url = f"{SUPABASE_URL}/rest/v1/sync_log"
    params = {"on_conflict": "entidad"}
    payload = [{
        "entidad":     "dtes_diario",
        "fuente":      "relbase",
        "ultima_sync": datetime.now(ZoneInfo("America/Santiago")).isoformat(),
        "estado":      "ok",
        "registros_nuevos": total,
    }]

    response = requests.post(
        url,
        headers=headers_supabase(),
        params=params,
        json=payload,
        timeout=30,
    )

    if response.status_code in (200, 201):
        log.info(f"sync_log actualizado — {total} registros.")
    else:
        log.warning(
            f"Error actualizando sync_log: {response.status_code} — {response.text}")


def main():
    """Punto de entrada principal del sync incremental."""
    fecha = fecha_hoy_chile()
    log.info(f"=== Sync incremental iniciado — {fecha} ===")

    try:
        # 1. Fetch todas las ventas del día desde Relbase
        dtes = fetch_todas_las_ventas(fecha)

        if not dtes:
            log.info("Sin ventas para sincronizar hoy.")
            actualizar_sync_log(fecha, 0)
            return

        # 2. Mapear al esquema de Supabase
        ventas = [mapear_venta(d) for d in dtes]
        log.info(f"Ventas mapeadas: {len(ventas)}")

        # 3. Upsert en Supabase en batches de 100
        batch_size = 100
        for i in range(0, len(ventas), batch_size):
            batch = ventas[i:i + batch_size]
            log.info(
                f"Upsert batch {i // batch_size + 1} — {len(batch)} ventas...")
            upsert_ventas_supabase(batch)
            time.sleep(0.1)

        # 4. Actualizar sync_log
        actualizar_sync_log(fecha, len(ventas))

        log.info(
            f"=== Sync completado — {len(ventas)} ventas sincronizadas ===")

    except Exception as e:
        log.error(f"Error crítico en sync: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
