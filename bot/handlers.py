"""
handlers.py — Lógica de respuesta del bot según el comando recibido.

Cada handler consulta Supabase (Capa 2) y formatea la respuesta
en texto plano para WhatsApp (sin HTML, máx ~1600 chars).
"""

import os
import logging
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

logger = logging.getLogger("bot.handlers")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

# Números autorizados (whatsapp:+56XXXXXXXXX sin el prefijo)
NUMEROS_AUTORIZADOS: set[str] = set(
    filter(None, os.getenv("BOT_NUMEROS_AUTORIZADOS", "").split(","))
)


def _supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)


def _clp(valor: float | None) -> str:
    if valor is None:
        return "—"
    return f"${valor:,.0f}".replace(",", ".")


# ---------------------------------------------------------------------------
# Handlers por comando
# ---------------------------------------------------------------------------

async def handler_ventas() -> str:
    supabase = _supabase()
    data = supabase.rpc("kpis_ventas").execute().data
    if not data:
        return "No se pudieron obtener los datos de ventas."

    hoy    = data.get("hoy", {})
    semana = data.get("semana", {})
    mes    = data.get("mes", {})

    return (
        "📊 *Resumen de ventas*\n\n"
        f"*Hoy*\n"
        f"  Ingresos: {_clp(hoy.get('ingresos_netos'))}\n"
        f"  Transacciones: {hoy.get('num_ventas', 0)}\n\n"
        f"*Esta semana*\n"
        f"  Ingresos: {_clp(semana.get('ingresos_netos'))}\n"
        f"  Transacciones: {semana.get('num_ventas', 0)}\n\n"
        f"*Este mes*\n"
        f"  Ingresos: {_clp(mes.get('ingresos_netos'))}\n"
        f"  Transacciones: {mes.get('num_ventas', 0)}\n"
        f"  Ticket prom: {_clp(mes.get('ticket_promedio'))}"
    )


async def handler_stock() -> str:
    supabase = _supabase()
    resumen = supabase.rpc("resumen_stock_critico").execute().data
    items = (
        supabase.from_("vw_stock_critico")
        .select("nombre, cantidad_disponible, nivel_alerta, bodega_nombre")
        .limit(10)
        .execute()
        .data or []
    )

    if not resumen or resumen.get("total", 0) == 0:
        return "✅ Stock saludable. Ningún producto bajo el mínimo."

    lineas = [
        f"⚠️ *Alertas de stock* ({resumen['total']} productos)\n",
        f"🔴 Sin stock: {resumen.get('sin_stock', 0)}",
        f"🟠 Crítico:   {resumen.get('critico', 0)}",
        f"🟡 Bajo:      {resumen.get('bajo', 0)}\n",
    ]

    for item in items[:8]:
        icono = "🔴" if item["nivel_alerta"] == "sin_stock" else "🟠" if item["nivel_alerta"] == "critico" else "🟡"
        lineas.append(
            f"{icono} {item['nombre'][:30]}\n"
            f"   Disp: {item['cantidad_disponible']:.0f} — {item['bodega_nombre']}"
        )

    return "\n".join(lineas)


async def handler_top() -> str:
    supabase = _supabase()
    productos = (
        supabase.from_("vw_top_productos_semana")
        .select("nombre_producto, ingresos_netos, unidades_vendidas, margen_pct")
        .limit(5)
        .execute()
        .data or []
    )

    if not productos:
        return "Sin ventas registradas esta semana."

    lineas = ["🏆 *Top 5 productos esta semana*\n"]
    for i, p in enumerate(productos, 1):
        margen = f" ({p['margen_pct']:.0f}%)" if p.get("margen_pct") else ""
        lineas.append(
            f"{i}. {p['nombre_producto'][:28]}\n"
            f"   {_clp(p['ingresos_netos'])} · {p['unidades_vendidas']:.0f} uds{margen}"
        )

    return "\n".join(lineas)


async def handler_ayuda() -> str:
    return (
        "🤖 *El Chillanejo Bot*\n\n"
        "Comandos disponibles:\n\n"
        "📊 *ventas* — Resumen hoy / semana / mes\n"
        "📦 *stock* — Alertas de stock crítico\n"
        "🏆 *top* — Top 5 productos de la semana\n"
        "❓ *ayuda* — Esta lista\n\n"
        "Envía cualquier comando para empezar."
    )


async def handler_no_autorizado() -> str:
    return "Lo siento, este número no tiene acceso al bot de El Chillanejo."


async def handler_desconocido(texto: str) -> str:
    return (
        f"No entendí el comando *{texto[:30]}*.\n\n"
        "Escribe *ayuda* para ver los comandos disponibles."
    )


# ---------------------------------------------------------------------------
# Router principal
# ---------------------------------------------------------------------------

_COMANDOS = {
    "ventas":  handler_ventas,
    "stock":   handler_stock,
    "top":     handler_top,
    "ayuda":   handler_ayuda,
    "help":    handler_ayuda,
    "hola":    handler_ayuda,
    "inicio":  handler_ayuda,
}


async def manejar_mensaje(numero: str, texto: str) -> str:
    """
    Punto de entrada: recibe número y texto, retorna respuesta como string.
    """
    # Validar número autorizado (si la lista está configurada)
    if NUMEROS_AUTORIZADOS and numero not in NUMEROS_AUTORIZADOS:
        logger.warning("Número no autorizado intentó acceder: %s", numero)
        return await handler_no_autorizado()

    comando = texto.lower().strip().split()[0] if texto.strip() else "ayuda"

    handler = _COMANDOS.get(comando)
    if handler:
        try:
            return await handler()
        except Exception as e:
            logger.error("Error en handler '%s': %s", comando, e)
            return "Ocurrió un error procesando tu solicitud. Intenta de nuevo."

    return await handler_desconocido(texto)
