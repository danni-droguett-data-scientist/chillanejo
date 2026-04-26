"""
extractor.py — Extracción paginada de entidades desde la API de Relbase.

Entidades soportadas:
  - dtes       → ventas (tipos 33, 39, 1001)
  - productos  → catálogo con costo_unitario
  - clientes   → B2B y B2C
  - bodegas    → seed inicial
  - stock      → requiere lista de productos previa

Paginación: parámetro ?page=N, continúa mientras meta.next_page no sea null.
Rate limit: 7 req/seg → sleep 0.15s entre llamadas.

Uso:
  from conectores.relbase.extractor import extraer_entidad
  registros = extraer_entidad("productos")
"""

import os
import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, date
from typing import Optional, Generator

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("relbase.extractor")

RELBASE_BASE_URL = os.getenv("RELBASE_BASE_URL", "https://api.relbase.cl/api/v1")
RELBASE_TOKEN_USUARIO = os.getenv("RELBASE_TOKEN_USUARIO")
RELBASE_TOKEN_EMPRESA = os.getenv("RELBASE_TOKEN_EMPRESA")
RATE_LIMIT_SLEEP = float(os.getenv("RELBASE_RATE_LIMIT_SLEEP", "0.0"))
# Workers paralelos para paginación — seguro porque la latencia (~850ms) es el cuello
# de botella, no el rate limit de Relbase (probado: 0 errores 429 con sleep=0)
MAX_WORKERS = int(os.getenv("RELBASE_MAX_WORKERS", "5"))

# Tipos de DTE a extraer (boletas, facturas, notas de venta)
TIPOS_DTE = [33, 39, 1001]


# ---------------------------------------------------------------------------
# Cliente HTTP base
# ---------------------------------------------------------------------------

def _validar_credenciales() -> None:
    faltantes = [
        nombre
        for nombre, valor in {
            "RELBASE_TOKEN_USUARIO": RELBASE_TOKEN_USUARIO,
            "RELBASE_TOKEN_EMPRESA": RELBASE_TOKEN_EMPRESA,
        }.items()
        if not valor
    ]
    if faltantes:
        raise EnvironmentError(
            f"Variables de entorno faltantes: {', '.join(faltantes)}. "
            "Revisa tu archivo .env."
        )


def _headers() -> dict:
    return {
        "Authorization": RELBASE_TOKEN_USUARIO,
        "Company": RELBASE_TOKEN_EMPRESA,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _get(session: requests.Session, endpoint: str, params: dict = None) -> dict:
    """
    Llamada GET a Relbase. Lanza excepción en error HTTP.
    Aplica rate limit antes de cada llamada.
    """
    time.sleep(RATE_LIMIT_SLEEP)
    url = f"{RELBASE_BASE_URL}/{endpoint.lstrip('/')}"
    response = session.get(url, headers=_headers(), params=params or {}, timeout=30)
    response.raise_for_status()
    return response.json()


def _extraer_lista_de_data(data) -> list:
    """
    Relbase devuelve data como dict con la lista anidada (ej. data.products).
    Extrae el primer valor que sea una lista no vacía, o la lista directa.
    """
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for val in data.values():
            if isinstance(val, list):
                return val
    return []


# ---------------------------------------------------------------------------
# Extracción paginada genérica
# ---------------------------------------------------------------------------

def _fetch_pagina(session: requests.Session, endpoint: str, params: dict, pagina: int) -> tuple[int, list]:
    """Descarga una página específica. Retorna (pagina, registros)."""
    p = dict(params)
    p["page"] = pagina
    try:
        respuesta = _get(session, endpoint, p)
        return pagina, _extraer_lista_de_data(respuesta.get("data", []))
    except Exception as e:
        logger.error("Error en %s página %d: %s", endpoint, pagina, e)
        return pagina, []


def _paginar(
    session: requests.Session,
    endpoint: str,
    params: dict = None,
) -> Generator[list, None, None]:
    """
    Descarga página 1 para conocer total_pages, luego las páginas restantes
    en paralelo con MAX_WORKERS workers. Yield: lista de registros por página
    en orden numérico.
    Relbase devuelve data como dict anidado (ej. {"products": [...]}).
    """
    params = dict(params or {})

    # Página 1 siempre secuencial para obtener metadata de paginación
    try:
        primera = _get(session, endpoint, {**params, "page": 1})
    except Exception as e:
        logger.error("Error en %s página 1: %s", endpoint, e)
        return

    data_p1 = _extraer_lista_de_data(primera.get("data", []))
    if not data_p1:
        return
    yield data_p1

    meta = primera.get("meta", {})
    total_pages = int(meta.get("total_pages") or 1)
    if total_pages <= 1:
        return

    # Páginas 2..N en paralelo
    paginas_restantes = list(range(2, total_pages + 1))
    logger.debug("GET %s — descargando %d páginas con %d workers", endpoint, len(paginas_restantes), MAX_WORKERS)

    resultados: dict[int, list] = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futuros = {
            pool.submit(_fetch_pagina, session, endpoint, params, p): p
            for p in paginas_restantes
        }
        for futuro in as_completed(futuros):
            pagina, datos = futuro.result()
            if datos:
                resultados[pagina] = datos

    # Yield en orden para mantener consistencia
    for p in paginas_restantes:
        if p in resultados:
            yield resultados[p]


# ---------------------------------------------------------------------------
# Extractor por entidad
# ---------------------------------------------------------------------------

def extraer_productos(
    session: requests.Session,
    desde_fecha: Optional[str] = None,
) -> list[dict]:
    """
    Extrae el catálogo completo de productos desde Relbase.
    Args:
        desde_fecha: ISO date string YYYY-MM-DD para extracción incremental.
    """
    params = {}
    if desde_fecha:
        params["updated_at_from"] = desde_fecha

    registros = []
    for pagina in _paginar(session, "/productos", params):
        registros.extend(pagina)

    logger.info("Productos extraídos: %d", len(registros))
    return registros


def extraer_clientes(
    session: requests.Session,
    desde_fecha: Optional[str] = None,
) -> list[dict]:
    """Extrae clientes B2B y B2C desde Relbase."""
    params = {}
    if desde_fecha:
        params["updated_at_from"] = desde_fecha

    registros = []
    for pagina in _paginar(session, "/clientes", params):
        registros.extend(pagina)

    logger.info("Clientes extraídos: %d", len(registros))
    return registros


def extraer_dtes(
    session: requests.Session,
    tipos: list[int] = None,
    desde_fecha: Optional[str] = None,
    hasta_fecha: Optional[str] = None,
) -> list[dict]:
    """
    Extrae DTEs (ventas) de los tipos especificados.
    Por defecto extrae boletas (39), facturas (33) y notas de venta (1001).

    Args:
        tipos: lista de tipos DTE a extraer. Default: TIPOS_DTE.
        desde_fecha: ISO date YYYY-MM-DD — filtro start_date en Relbase.
        hasta_fecha: ISO date YYYY-MM-DD — filtro end_date en Relbase.
    """
    tipos = tipos or TIPOS_DTE
    todos_los_dtes = []

    for tipo in tipos:
        # Relbase requiere type_document (no tipo_dte); fechas: start_date/end_date
        params = {"type_document": tipo}
        if desde_fecha:
            params["start_date"] = desde_fecha
        if hasta_fecha:
            params["end_date"] = hasta_fecha

        registros_tipo = []
        for pagina in _paginar(session, "/dtes", params):
            registros_tipo.extend(pagina)

        logger.info("DTEs tipo %d extraídos: %d", tipo, len(registros_tipo))
        todos_los_dtes.extend(registros_tipo)

    logger.info("Total DTEs extraídos: %d", len(todos_los_dtes))
    return todos_los_dtes


def extraer_bodegas(session: requests.Session) -> list[dict]:
    """
    Extrae bodegas. Relbase las devuelve en data.warehouses sin paginación.
    """
    try:
        respuesta = _get(session, "/bodegas")
        data = respuesta.get("data", {})
        # Relbase devuelve {"warehouses": [...]} dentro de data
        if isinstance(data, dict):
            registros = data.get("warehouses", [])
        else:
            registros = _extraer_lista_de_data(data)
    except requests.exceptions.RequestException as e:
        logger.error("Error al obtener bodegas: %s", e)
        registros = []

    logger.info("Bodegas extraídas: %d", len(registros))
    return registros


def extraer_stock_por_producto(
    session: requests.Session,
    producto_id: int,
) -> list[dict]:
    """
    GET /api/v1/productos/{id}/stock_por_bodegas
    Relbase devuelve data.stocks[]. Agrega _producto_id_relbase a cada fila.
    """
    try:
        respuesta = _get(session, f"/productos/{producto_id}/stock_por_bodegas")
        data = respuesta.get("data", {})
        # Relbase devuelve {"stocks": [...]} dentro de data
        if isinstance(data, dict):
            filas = data.get("stocks", [])
        else:
            filas = _extraer_lista_de_data(data)
        for fila in filas:
            fila["_producto_id_relbase"] = producto_id
        return filas
    except requests.exceptions.HTTPError as e:
        logger.error("Error al obtener stock del producto %d: %s", producto_id, e)
        return []
    except requests.exceptions.RequestException as e:
        logger.error("Error de red para stock del producto %d: %s", producto_id, e)
        return []


def extraer_stock_todos(
    session: requests.Session,
    ids_productos: list[int],
) -> list[dict]:
    """
    Extrae stock por bodega para todos los productos dados.
    Llama a extraer_stock_por_producto por cada ID, respetando rate limit.

    Args:
        ids_productos: lista de IDs de productos en Relbase.
    """
    todo_el_stock = []
    total = len(ids_productos)

    for idx, prod_id in enumerate(ids_productos, start=1):
        stock = extraer_stock_por_producto(session, prod_id)
        todo_el_stock.extend(stock)

        if idx % 100 == 0:
            logger.info("Stock: %d/%d productos procesados", idx, total)

    logger.info(
        "Stock extraído: %d registros de %d productos", len(todo_el_stock), total
    )
    return todo_el_stock


# ---------------------------------------------------------------------------
# Función principal orquestadora
# ---------------------------------------------------------------------------

def extraer_entidad(
    entidad: str,
    desde_fecha: Optional[str] = None,
    hasta_fecha: Optional[str] = None,
    ids_productos: Optional[list[int]] = None,
    tipos_dte: Optional[list[int]] = None,
) -> list[dict]:
    """
    Punto de entrada único para extraer cualquier entidad de Relbase.

    Args:
        entidad: "productos" | "clientes" | "dtes" | "bodegas" | "stock"
        desde_fecha: YYYY-MM-DD para extracción incremental.
        hasta_fecha: YYYY-MM-DD, solo aplica a "dtes".
        ids_productos: requerido solo para entidad "stock".
        tipos_dte: subconjunto de tipos para entidad "dtes".

    Returns:
        Lista de dicts con los datos crudos de Relbase.
    """
    _validar_credenciales()

    entidades_validas = {"productos", "clientes", "dtes", "bodegas", "stock"}
    if entidad not in entidades_validas:
        raise ValueError(
            f"Entidad '{entidad}' no soportada. Opciones: {entidades_validas}"
        )

    logger.info("Iniciando extracción de '%s' desde Relbase...", entidad)
    inicio = datetime.now(timezone.utc)

    with requests.Session() as session:
        if entidad == "productos":
            datos = extraer_productos(session, desde_fecha)
        elif entidad == "clientes":
            datos = extraer_clientes(session, desde_fecha)
        elif entidad == "dtes":
            datos = extraer_dtes(session, tipos_dte, desde_fecha, hasta_fecha)
        elif entidad == "bodegas":
            datos = extraer_bodegas(session)
        elif entidad == "stock":
            if not ids_productos:
                raise ValueError(
                    "Para extraer 'stock' debes proporcionar 'ids_productos'."
                )
            datos = extraer_stock_todos(session, ids_productos)

    duracion = (datetime.now(timezone.utc) - inicio).total_seconds()
    logger.info(
        "Extracción '%s' completada: %d registros en %.1fs",
        entidad, len(datos), duracion,
    )
    return datos


# ---------------------------------------------------------------------------
# Punto de entrada CLI (modo debug / ejecución manual)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    import json

    logging.basicConfig(
        level="INFO",
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="Extrae una entidad de Relbase y muestra los primeros registros."
    )
    parser.add_argument(
        "entidad",
        choices=["productos", "clientes", "dtes", "bodegas", "stock"],
        help="Entidad a extraer",
    )
    parser.add_argument(
        "--desde", metavar="YYYY-MM-DD", help="Fecha inicio para extracción incremental"
    )
    parser.add_argument(
        "--hasta", metavar="YYYY-MM-DD", help="Fecha fin (solo DTEs)"
    )
    parser.add_argument(
        "--preview", type=int, default=3, help="Cantidad de registros a mostrar (default 3)"
    )
    args = parser.parse_args()

    resultado = extraer_entidad(
        entidad=args.entidad,
        desde_fecha=args.desde,
        hasta_fecha=args.hasta,
    )
    print(f"\nTotal extraídos: {len(resultado)}")
    print(f"Primeros {args.preview} registros:")
    print(json.dumps(resultado[: args.preview], indent=2, ensure_ascii=False, default=str))
