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
from datetime import datetime, timezone, date
from typing import Optional, Generator

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("relbase.extractor")

RELBASE_BASE_URL = os.getenv("RELBASE_BASE_URL", "https://api.relbase.cl/api/v1")
RELBASE_TOKEN_USUARIO = os.getenv("RELBASE_TOKEN_USUARIO")
RELBASE_TOKEN_EMPRESA = os.getenv("RELBASE_TOKEN_EMPRESA")
RATE_LIMIT_SLEEP = float(os.getenv("RELBASE_RATE_LIMIT_SLEEP", "0.15"))

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


# ---------------------------------------------------------------------------
# Extracción paginada genérica
# ---------------------------------------------------------------------------

def _paginar(
    session: requests.Session,
    endpoint: str,
    params: dict = None,
) -> Generator[list, None, None]:
    """
    Itera páginas de un endpoint hasta que meta.next_page sea null.
    Yield: lista de registros de cada página.
    """
    pagina = 1
    params = params or {}

    while True:
        params["page"] = pagina
        logger.debug("GET %s página %d", endpoint, pagina)

        try:
            respuesta = _get(session, endpoint, params)
        except requests.exceptions.HTTPError as e:
            logger.error("Error HTTP en %s página %d: %s", endpoint, pagina, e)
            break
        except requests.exceptions.RequestException as e:
            logger.error("Error de red en %s página %d: %s", endpoint, pagina, e)
            break

        data = respuesta.get("data", [])
        if not data:
            break

        yield data

        # Verifica si hay siguiente página
        meta = respuesta.get("meta", {})
        siguiente = meta.get("next_page") or meta.get("nextPage")
        if not siguiente:
            break
        pagina += 1


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
        desde_fecha: ISO date YYYY-MM-DD, para extracción incremental.
        hasta_fecha: ISO date YYYY-MM-DD, límite superior.
    """
    tipos = tipos or TIPOS_DTE
    todos_los_dtes = []

    for tipo in tipos:
        params = {"tipo_dte": tipo}
        if desde_fecha:
            params["fecha_desde"] = desde_fecha
        if hasta_fecha:
            params["fecha_hasta"] = hasta_fecha

        registros_tipo = []
        for pagina in _paginar(session, "/dtes", params):
            registros_tipo.extend(pagina)

        logger.info("DTEs tipo %d extraídos: %d", tipo, len(registros_tipo))
        todos_los_dtes.extend(registros_tipo)

    logger.info("Total DTEs extraídos: %d", len(todos_los_dtes))
    return todos_los_dtes


def extraer_bodegas(session: requests.Session) -> list[dict]:
    """
    Extrae bodegas. Solo se usa en el seed inicial.
    Relbase generalmente devuelve pocas bodegas (no necesita paginación real).
    """
    registros = []
    for pagina in _paginar(session, "/bodegas"):
        registros.extend(pagina)

    logger.info("Bodegas extraídas: %d", len(registros))
    return registros


def extraer_stock_por_producto(
    session: requests.Session,
    producto_id: int,
) -> list[dict]:
    """
    GET /api/v1/productos/{id}/stock_por_bodegas
    Retorna el stock de un producto por cada bodega.
    Incluye el producto_id en cada registro para facilitar la carga.
    """
    try:
        respuesta = _get(session, f"/productos/{producto_id}/stock_por_bodegas")
        data = respuesta.get("data", [])
        # Agrega el id del producto a cada fila de stock
        for fila in data:
            fila["_producto_id_relbase"] = producto_id
        return data
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
