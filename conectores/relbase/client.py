"""
client.py — Cliente base para la API de Relbase.

Centraliza autenticación, headers, rate limit y manejo de errores HTTP.
Los demás módulos del conector (extractor, loader) pueden importar
RelbaseClient en lugar de replicar la lógica de sesión.

Uso:
  from conectores.relbase.client import RelbaseClient

  with RelbaseClient() as client:
      data = client.get("/productos", params={"page": 1})
"""

import os
import time
import logging
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("relbase.client")

RELBASE_BASE_URL = os.getenv("RELBASE_BASE_URL", "https://api.relbase.cl/api/v1")
RELBASE_TOKEN_USUARIO = os.getenv("RELBASE_TOKEN_USUARIO")
RELBASE_TOKEN_EMPRESA = os.getenv("RELBASE_TOKEN_EMPRESA")
RATE_LIMIT_SLEEP = float(os.getenv("RELBASE_RATE_LIMIT_SLEEP", "0.15"))

# Reintentos ante errores de red o 5xx
MAX_REINTENTOS = int(os.getenv("RELBASE_MAX_REINTENTOS", "3"))
ESPERA_REINTENTO = float(os.getenv("RELBASE_ESPERA_REINTENTO", "2.0"))


class RelbaseClient:
    """
    Cliente HTTP para la API de Relbase.

    - Inyecta headers de autenticación en cada llamada.
    - Aplica rate limit (RATE_LIMIT_SLEEP segundos entre requests).
    - Reintenta en errores de red y respuestas 5xx.
    - Solo lectura: no expone métodos POST/PUT/DELETE.
    - Usable como context manager (with RelbaseClient() as client).
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        token_usuario: Optional[str] = None,
        token_empresa: Optional[str] = None,
        rate_limit_sleep: float = RATE_LIMIT_SLEEP,
        max_reintentos: int = MAX_REINTENTOS,
    ):
        self.base_url = (base_url or RELBASE_BASE_URL).rstrip("/")
        self._token_usuario = token_usuario or RELBASE_TOKEN_USUARIO
        self._token_empresa = token_empresa or RELBASE_TOKEN_EMPRESA
        self.rate_limit_sleep = rate_limit_sleep
        self.max_reintentos = max_reintentos
        self._session: Optional[requests.Session] = None
        self._validar_credenciales()

    def _validar_credenciales(self) -> None:
        faltantes = [
            nombre
            for nombre, valor in {
                "RELBASE_TOKEN_USUARIO": self._token_usuario,
                "RELBASE_TOKEN_EMPRESA": self._token_empresa,
            }.items()
            if not valor
        ]
        if faltantes:
            raise EnvironmentError(
                f"Variables de entorno faltantes: {', '.join(faltantes)}. "
                "Revisa tu archivo .env."
            )

    @property
    def _headers(self) -> dict:
        return {
            "Authorization": self._token_usuario,
            "Company": self._token_empresa,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> "RelbaseClient":
        self._session = requests.Session()
        return self

    def __exit__(self, *_) -> None:
        if self._session:
            self._session.close()
            self._session = None

    # ------------------------------------------------------------------
    # Llamadas HTTP
    # ------------------------------------------------------------------

    def get(self, endpoint: str, params: dict = None) -> dict:
        """
        GET a un endpoint de Relbase. Aplica rate limit y reintentos.

        Args:
            endpoint: ruta relativa, ej. "/productos" o "/dtes/123".
            params: query params opcionales.

        Returns:
            Cuerpo JSON de la respuesta como dict.

        Raises:
            requests.HTTPError: en errores 4xx no recuperables.
            requests.ConnectionError: si se agotan los reintentos.
        """
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        session = self._session or requests.Session()
        cierre_local = self._session is None

        intento = 0
        ultimo_error = None

        while intento < self.max_reintentos:
            # Rate limit antes de cada llamada
            time.sleep(self.rate_limit_sleep)

            try:
                response = session.get(
                    url,
                    headers=self._headers,
                    params=params or {},
                    timeout=30,
                )

                # Errores 4xx no se reintentan (salvo 429 — rate limit externo)
                if response.status_code == 429:
                    retry_after = float(response.headers.get("Retry-After", 5))
                    logger.warning(
                        "Rate limit externo (429). Esperando %.1fs...", retry_after
                    )
                    time.sleep(retry_after)
                    intento += 1
                    continue

                response.raise_for_status()

                if cierre_local:
                    session.close()

                return response.json()

            except requests.exceptions.HTTPError as e:
                # 4xx no recuperables → propagar inmediatamente
                if e.response is not None and e.response.status_code < 500:
                    if cierre_local:
                        session.close()
                    raise
                ultimo_error = e

            except requests.exceptions.RequestException as e:
                ultimo_error = e

            intento += 1
            if intento < self.max_reintentos:
                espera = ESPERA_REINTENTO * intento
                logger.warning(
                    "Error en GET %s (intento %d/%d): %s. Reintentando en %.1fs...",
                    endpoint, intento, self.max_reintentos, ultimo_error, espera,
                )
                time.sleep(espera)

        if cierre_local:
            session.close()

        raise requests.ConnectionError(
            f"GET {endpoint} falló tras {self.max_reintentos} intentos. "
            f"Último error: {ultimo_error}"
        )

    def paginar(self, endpoint: str, params: dict = None):
        """
        Generador que itera todas las páginas de un endpoint paginado.

        Yield: lista de registros de cada página (campo 'data').
        Detiene cuando meta.next_page es null o data está vacío.
        """
        params = dict(params or {})
        pagina = 1

        while True:
            params["page"] = pagina
            logger.debug("GET %s — página %d", endpoint, pagina)

            try:
                respuesta = self.get(endpoint, params)
            except Exception as e:
                logger.error(
                    "Error paginando %s en página %d: %s", endpoint, pagina, e
                )
                return

            data = respuesta.get("data", [])
            if not data:
                break

            yield data

            meta = respuesta.get("meta", {})
            siguiente = meta.get("next_page") or meta.get("nextPage")
            if not siguiente:
                break
            pagina += 1
