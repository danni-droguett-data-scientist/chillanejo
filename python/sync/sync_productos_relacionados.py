"""
sync_productos_relacionados.py
Calcula ventas cruzadas entre productos y actualiza productos_relacionados en Supabase.

Algoritmo:
  1. Obtiene pares (venta_id, relbase_producto_id) del último año desde ventas_detalle
  2. Agrupa por venta_id para obtener los productos de cada transacción
  3. Cuenta frecuencia conjunta de cada par de productos
  4. Descarta pares con menos de MIN_FRECUENCIA ventas conjuntas
  5. Mantiene top TOP_RELACIONADOS por producto
  6. Upsert en productos_relacionados

ventas_detalle.relbase_producto_id es integer (FK a productos.relbase_id).
"""

import os
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from itertools import combinations

import requests
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL         = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

MIN_FRECUENCIA   = 5    # pares con menos ocurrencias se descartan
TOP_RELACIONADOS = 5    # máximo de relacionados por producto
PAGE_SIZE        = 1000 # filas por página al paginar Supabase

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers de red
# ---------------------------------------------------------------------------

def _headers_lectura() -> dict:
    return {
        "apikey":        SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Accept":        "application/json",
    }


def _headers_escritura() -> dict:
    return {
        **_headers_lectura(),
        "Content-Type": "application/json",
        "Prefer":       "resolution=merge-duplicates",
    }


def _fecha_hace_un_anio() -> str:
    return (datetime.utcnow() - timedelta(days=365)).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Paso 1: obtener filas de ventas_detalle
# ---------------------------------------------------------------------------

def fetch_detalle_ultimo_anio() -> list[dict]:
    """
    Retorna lista de {venta_id, relbase_producto_id} del último año.
    Pagina hasta agotar los resultados.
    """
    url    = f"{SUPABASE_URL}/rest/v1/ventas_detalle"
    filas  = []
    offset = 0

    while True:
        response = requests.get(
            url,
            headers=_headers_lectura(),
            params={
                "select":               "venta_id,relbase_producto_id",
                "relbase_producto_id":  "not.is.null",
                "created_at":           f"gte.{_fecha_hace_un_anio()}",
                "limit":                PAGE_SIZE,
                "offset":               offset,
            },
            timeout=60,
        )
        response.raise_for_status()

        pagina = response.json()
        filas.extend(pagina)
        log.info(
            "  Página offset=%d — %d filas (acumulado: %d)",
            offset, len(pagina), len(filas),
        )

        if len(pagina) < PAGE_SIZE:
            break
        offset += PAGE_SIZE

    return filas


# ---------------------------------------------------------------------------
# Paso 2: agrupar por venta
# ---------------------------------------------------------------------------

def agrupar_productos_por_venta(filas: list[dict]) -> dict[str, set[int]]:
    """
    Devuelve {venta_id: {relbase_producto_id, ...}}.
    Solo incluye ventas con al menos 2 productos distintos.
    """
    grupos: dict[str, set[int]] = defaultdict(set)
    for fila in filas:
        vid = fila.get("venta_id")
        pid = fila.get("relbase_producto_id")
        if vid and pid is not None:
            grupos[vid].add(int(pid))

    con_pares = {vid: prods for vid, prods in grupos.items() if len(prods) >= 2}
    log.info(
        "Ventas totales: %d | con ≥2 productos distintos: %d",
        len(grupos), len(con_pares),
    )
    return con_pares


# ---------------------------------------------------------------------------
# Paso 3: contar frecuencias de pares
# ---------------------------------------------------------------------------

def contar_frecuencias_pares(
    grupos: dict[str, set[int]],
) -> dict[tuple[int, int], int]:
    """
    Retorna {(producto_a, producto_b): frecuencia_conjunta}.
    Los pares siempre se almacenan en orden ascendente para evitar duplicados.
    """
    frecuencias: dict[tuple[int, int], int] = defaultdict(int)
    for productos in grupos.values():
        for a, b in combinations(sorted(productos), 2):
            frecuencias[(a, b)] += 1
    return frecuencias


# ---------------------------------------------------------------------------
# Paso 4 y 5: filtrar y rankear
# ---------------------------------------------------------------------------

def filtrar_y_rankear(
    frecuencias: dict[tuple[int, int], int],
) -> list[dict]:
    """
    Descarta pares bajo MIN_FRECUENCIA.
    Por cada producto retiene los TOP_RELACIONADOS más frecuentes.
    Retorna lista de dicts listos para upsert.
    """
    por_producto: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for (a, b), freq in frecuencias.items():
        if freq >= MIN_FRECUENCIA:
            por_producto[a].append((b, freq))
            por_producto[b].append((a, freq))

    registros = []
    for producto, candidatos in por_producto.items():
        top = sorted(candidatos, key=lambda x: x[1], reverse=True)[:TOP_RELACIONADOS]
        for relacionado, freq in top:
            registros.append({
                "producto_id":          producto,
                "producto_relacionado_id": relacionado,
                "frecuencia_conjunta":  freq,
            })
    return registros


# ---------------------------------------------------------------------------
# Paso 6: upsert en Supabase
# ---------------------------------------------------------------------------

def upsert_relacionados(registros: list[dict]) -> None:
    """Upsert en lotes de 500. Usa on_conflict por clave primaria compuesta."""
    if not registros:
        log.info("No hay pares para hacer upsert.")
        return

    url        = f"{SUPABASE_URL}/rest/v1/productos_relacionados"
    params     = {"on_conflict": "producto_id,producto_relacionado_id"}
    batch_size = 500

    for i in range(0, len(registros), batch_size):
        batch    = registros[i : i + batch_size]
        response = requests.post(
            url,
            headers=_headers_escritura(),
            params=params,
            json=batch,
            timeout=60,
        )
        if response.status_code in (200, 201):
            log.info(
                "  Batch %d/%d upserted — %d registros",
                i // batch_size + 1,
                -(-len(registros) // batch_size),
                len(batch),
            )
        else:
            log.error(
                "Error en batch %d: %s — %s",
                i // batch_size + 1, response.status_code, response.text,
            )
            response.raise_for_status()


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------

def main() -> None:
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        log.error("SUPABASE_URL o SUPABASE_SERVICE_ROLE_KEY no configurados en .env")
        raise SystemExit(1)

    log.info("=== Inicio sync productos relacionados ===")

    log.info("Paso 1: Leyendo ventas_detalle del último año...")
    filas = fetch_detalle_ultimo_anio()
    log.info("  Total filas: %d", len(filas))

    log.info("Paso 2: Agrupando por venta...")
    grupos = agrupar_productos_por_venta(filas)

    log.info("Paso 3: Calculando frecuencias de pares...")
    frecuencias = contar_frecuencias_pares(grupos)
    log.info("  Pares únicos encontrados: %d", len(frecuencias))

    log.info(
        "Paso 4-5: Filtrando (min=%d) y seleccionando top %d por producto...",
        MIN_FRECUENCIA, TOP_RELACIONADOS,
    )
    registros = filtrar_y_rankear(frecuencias)

    log.info("Paso 6: Upsert en productos_relacionados...")
    upsert_relacionados(registros)

    # Resumen final
    productos_con_relacionados = len({r["producto_id"] for r in registros})
    log.info("=== Sync completado ===")
    log.info("  Pares calculados (post-filtro):  %d", len(registros))
    log.info("  Productos con relacionados:      %d", productos_con_relacionados)


if __name__ == "__main__":
    main()
