"""
app.py — Bot WhatsApp El Chillanejo vía Twilio + FastAPI.

Webhook que recibe mensajes de WhatsApp y responde con
datos del negocio en tiempo real desde Supabase.

Comandos disponibles:
  ventas    → resumen ventas de hoy y semana
  stock     → alertas de stock crítico
  top       → top 5 productos de la semana
  ayuda     → lista de comandos

Despliegue: uvicorn bot.app:app --host 0.0.0.0 --port 8000
"""

import os
import logging
from fastapi import FastAPI, Form, Response
from fastapi.responses import PlainTextResponse
from dotenv import load_dotenv
from twilio.request_validator import RequestValidator
from twilio.twiml.messaging_response import MessagingResponse

from bot.handlers import manejar_mensaje

load_dotenv()

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("bot.app")

app = FastAPI(title="El Chillanejo Bot", docs_url=None, redoc_url=None)

TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/webhook/whatsapp")
async def webhook_whatsapp(
    From: str = Form(...),
    Body: str = Form(...),
    NumMedia: str = Form(default="0"),
):
    """
    Endpoint que Twilio llama al recibir un mensaje de WhatsApp.
    Retorna TwiML con la respuesta.
    """
    numero = From.replace("whatsapp:", "").strip()
    texto = Body.strip()

    logger.info("Mensaje recibido de %s: %s", numero, texto[:80])

    respuesta_texto = await manejar_mensaje(numero, texto)

    twiml = MessagingResponse()
    twiml.message(respuesta_texto)

    return Response(content=str(twiml), media_type="application/xml")
