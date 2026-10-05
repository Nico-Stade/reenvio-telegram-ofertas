"""
engine/listener.py — Listener en tiempo real (event-driven) y catch-up vía Telethon MTProto.
"""
import asyncio
from typing import Optional
from loguru import logger
from telethon import TelegramClient, events
from telethon.tl.types import PeerChannel, PeerChat, PeerUser

from core.database import SQLiteDealRepository
from core.models import DealItem
from engine.parser import BunnyDealParser
from engine.filters.pipeline import FilterPipeline
from engine.dispatchers.bot_dispatcher import TelegramBotDispatcher


def parse_peer(identifier: str):
    """Convierte un identificador en PeerChannel/PeerChat/PeerUser."""
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


class DealForwarderEngine:
    """
    Motor central que orquesta:
    Userbot (Event Listener) -> Parser -> FilterPipeline -> BotDispatcher -> SQLite Repository.
    """

    def __init__(
        self,
        telethon_client: TelegramClient,
        source_channel: str,
        parser: BunnyDealParser,
        pipeline: FilterPipeline,
        dispatcher: TelegramBotDispatcher,
        repository: SQLiteDealRepository,
    ):
        self.client = telethon_client
        self.source_channel = str(source_channel)
        self.source_peer = parse_peer(self.source_channel)
        self.parser = parser
        self.pipeline = pipeline
        self.dispatcher = dispatcher
        self.repository = repository
        self._source_entity = None

    async def _resolve_entity(self):
        if self._source_entity is None:
            self._source_entity = await self.client.get_entity(self.source_peer)
            title = getattr(self._source_entity, "title", self.source_channel)
            logger.info(f"[Engine] Canal fuente resuelto: '{title}' ({self.source_channel})")
        return self._source_entity

    async def process_message(self, message_id: int, text: str) -> bool:
        """Procesa un mensaje individual a través de todo el flujo."""
        if not text:
            return False

        deal = self.parser.parse(message_id, text, self.source_channel)
        if not deal:
            logger.debug(f"[Engine] Mensaje {message_id} no contiene formato de oferta válido.")
            return False

        # 1. Pipeline de filtros
        result = await self.pipeline.execute(deal)
        if not result.passed:
            # Guardamos de todas formas el último id procesado
            self.repository.set_last_message_id(self.source_channel, message_id)
            return False

        # 2. Despacho por Bot API
        success = await self.dispatcher.dispatch(deal)
        if success:
            # 3. Registrar en base de datos para historial y deduplicación
            self.repository.record_sent_deal(deal)
            self.repository.set_last_message_id(self.source_channel, message_id)
            logger.success(f"[Engine] 🎉 Oferta '{deal.title[:40]}' reenviada con éxito!")
            return True

        return False

    async def run_live(self) -> None:
        """Inicia el listener de eventos en tiempo real (< 50ms latencia)."""
        await self._resolve_entity()

        @self.client.on(events.NewMessage(chats=self.source_peer))
        async def on_new_deal(event):
            msg = event.message
            logger.info(f"\n[Engine] 📩 Nuevo mensaje entrante en {self.source_channel} (ID: {msg.id})")
            await self.process_message(msg.id, msg.text or "")

        logger.info(f"[Engine] ⚡ Escuchando mensajes en vivo en '{getattr(self._source_entity, 'title', self.source_channel)}'...")
        # Mantener corriendo indefinidamente
        await self.client.run_until_disconnected()

    async def run_backfill(self, limit: int = 15) -> int:
        """
        Lee los últimos N mensajes del canal y los procesa.
        Ideal para pruebas o para recuperar mensajes perdidos mientras el script estuvo apagado.
        """
        entity = await self._resolve_entity()
        logger.info(f"[Engine] Obteniendo últimos {limit} mensajes de '{getattr(entity, 'title', self.source_channel)}' para análisis...")
        
        messages = await self.client.get_messages(entity, limit=limit)
        # Procesar de más antiguo a más reciente
        sorted_msgs = sorted(messages, key=lambda m: m.id)
        
        processed_count = 0
        approved_count = 0

        for msg in sorted_msgs:
            if msg.text:
                passed = await self.process_message(msg.id, msg.text)
                if passed:
                    approved_count += 1
                processed_count += 1

        logger.info(f"[Engine] Backfill finalizado: {processed_count} analizados, {approved_count} aprobados y reenviados.")
        return approved_count
