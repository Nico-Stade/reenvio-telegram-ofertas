"""
core/client.py — Cliente Telethon compartido y resolución de entidades.
Soporta:
  1. SESSION_STRING en .env  → sin interacción (ideal para Docker/VPS)
  2. Archivo .session local  → login interactivo la primera vez
"""
import os
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import PeerChannel, PeerChat, PeerUser
from dotenv import load_dotenv
from loguru import logger

load_dotenv()


def build_client() -> TelegramClient:
    api_id = os.getenv("API_ID")
    api_hash = os.getenv("API_HASH")
    session_name = os.getenv("SESSION_NAME", "telegram_forwarder")
    session_string = os.getenv("SESSION_STRING", "").strip()

    if not api_id or not api_hash:
        raise EnvironmentError(
            "Faltan API_ID o API_HASH en el archivo .env. "
            "Obtené tus credenciales en https://my.telegram.org/apps"
        )

    if session_string:
        logger.info("Usando SESSION_STRING del entorno (modo headless).")
        session = StringSession(session_string)
    else:
        logger.info(f"Usando sesión de archivo: {session_name}.session")
        session = session_name

    return TelegramClient(session, int(api_id), api_hash)


def parse_peer(identifier: str):
    """
    Convierte un identificador de canal a un objeto Peer que Telethon puede
    resolver sin necesidad de tenerlo en caché.
    """
    s = str(identifier).strip()
    if s.startswith("@") or not s.lstrip("-").isdigit():
        return s

    n = int(s)
    if s.startswith("-100"):
        return PeerChannel(int(s[4:]))
    elif n < 0:
        return PeerChat(-n)
    else:
        return PeerUser(n)
