"""
engine/listener.py — Listener multi-canal en tiempo real (event-driven) y catch-up vía Telethon MTProto.
"""
import asyncio
from dataclasses import dataclass, field
from typing import Optional, List, Dict
from loguru import logger
from telethon import TelegramClient, events

from core.database import SQLiteDealRepository
from core.models import DealItem
from core.client import parse_peer
from engine.parser import BaseDealParser, BunnyDealParser
from engine.filters.pipeline import FilterPipeline
from engine.dispatchers.bot_dispatcher import TelegramBotDispatcher
from engine.resolver import SharkLinkResolver


@dataclass
class ChannelSourceConfig:
    """Configuración de un canal fuente individual."""
    channel_id: str
    name: str = ""
    parser: BaseDealParser = field(default_factory=BunnyDealParser)
    pipeline: Optional[FilterPipeline] = None


class DealForwarderEngine:
    """
    Motor central multi-canal que orquesta:
    Userbot (Event Listener) -> Parser por Canal -> FilterPipeline -> BotDispatcher -> SQLite Repository.
    """

    def __init__(
        self,
        telethon_client: TelegramClient,
        dispatcher: TelegramBotDispatcher,
        repository: SQLiteDealRepository,
        default_pipeline: Optional[FilterPipeline] = None,
        sources: Optional[List[ChannelSourceConfig]] = None,
        # Parámetros retrocompatibles para canal único:
        source_channel: Optional[str] = None,
        parser: Optional[BaseDealParser] = None,
        pipeline: Optional[FilterPipeline] = None,
    ):
        self.client = telethon_client
        self.dispatcher = dispatcher
        self.repository = repository
        self.default_pipeline = default_pipeline or pipeline
        self.resolver = SharkLinkResolver()

        # Inicialización de fuentes
        self.sources: List[ChannelSourceConfig] = []
        if sources:
            self.sources = list(sources)
        elif source_channel:
            self.sources = [
                ChannelSourceConfig(
                    channel_id=str(source_channel),
                    name=str(source_channel),
                    parser=parser or BunnyDealParser(),
                    pipeline=pipeline or self.default_pipeline,
                )
            ]

        # Índices de búsqueda rápida por channel_id y variantes
        self._sources_by_id: Dict[str, ChannelSourceConfig] = {}
        for src in self.sources:
            cid = str(src.channel_id).strip()
            self._sources_by_id[cid] = src
            if cid.startswith("-100"):
                self._sources_by_id[cid[4:]] = src
            elif cid.lstrip("-").isdigit():
                self._sources_by_id[f"-100{cid.lstrip('-')}"] = src

        self._resolved_entities: Dict[str, any] = {}

    def get_source_config(self, channel_identifier: any) -> Optional[ChannelSourceConfig]:
        """Obtiene la configuración del canal fuente según su ID o chat_id de Telethon."""
        s_id = str(channel_identifier).strip()
        if s_id in self._sources_by_id:
            return self._sources_by_id[s_id]

        if s_id.startswith("-100"):
            stripped = s_id[4:]
            if stripped in self._sources_by_id:
                return self._sources_by_id[stripped]
        elif s_id.lstrip("-").isdigit():
            with_prefix = f"-100{s_id.lstrip('-')}"
            if with_prefix in self._sources_by_id:
                return self._sources_by_id[with_prefix]

        if len(self.sources) == 1:
            return self.sources[0]

        return None

    async def _resolve_entities(self):
        """Resuelve y almacena en caché las entidades de todos los canales configurados."""
        for src in self.sources:
            if src.channel_id not in self._resolved_entities:
                peer = parse_peer(src.channel_id)
                entity = await self.client.get_entity(peer)
                title = getattr(entity, "title", src.name or src.channel_id)
                if not src.name:
                    src.name = title
                self._resolved_entities[src.channel_id] = entity
                logger.info(f"[Engine] Canal fuente resuelto: '{title}' ({src.channel_id}) [Parser: {type(src.parser).__name__}]")

    async def process_message(self, message_id: int, text: str, source_channel: str) -> bool:
        """Procesa un mensaje individual usando el parser y pipeline correspondientes a su canal."""
        if not text:
            return False

        src = self.get_source_config(source_channel)
        parser = src.parser if src else (self.sources[0].parser if self.sources else BunnyDealParser())
        pipeline = (src.pipeline if src and src.pipeline else self.default_pipeline)
        channel_name = src.name if src else source_channel

        deal = parser.parse(message_id, text, str(source_channel))
        if not deal:
            logger.debug(f"[Engine] Mensaje {message_id} de {channel_name} no es una oferta estructurada.")
            return False

        # Si el deal tiene un enlace protegido (ofertasshark.cl), resolverlo a la tienda real
        if deal.product_url and "ofertasshark.cl" in deal.product_url:
            resolved_url, detected_store = await self.resolver.resolve(deal.product_url)
            if resolved_url:
                deal.product_url = resolved_url
            if detected_store and not deal.store:
                deal.store = detected_store

        # 1. Pipeline de filtros
        result = await pipeline.execute(deal)
        if not result.passed:
            self.repository.set_last_message_id(source_channel, message_id)
            return False

        # 2. Despacho por Bot API
        success = await self.dispatcher.dispatch(deal)
        if success:
            # 3. Registrar en base de datos para historial y deduplicación
            self.repository.record_sent_deal(deal)
            self.repository.set_last_message_id(source_channel, message_id)
            logger.success(f"[Engine] 🎉 Oferta '{deal.title[:40]}' de [{channel_name}] reenviada con éxito!")
            return True

        return False

    async def run_live(self) -> None:
        """Inicia el listener de eventos en tiempo real multi-canal (< 50ms latencia)."""
        await self._resolve_entities()

        peers = [parse_peer(src.channel_id) for src in self.sources]

        @self.client.on(events.NewMessage(chats=peers))
        async def on_new_deal(event):
            msg = event.message
            chat_id = str(event.chat_id)
            src = self.get_source_config(chat_id)
            ch_name = src.name if src else chat_id
            logger.info(f"\n[Engine] 📩 Nuevo mensaje entrante en [{ch_name}] (ID: {msg.id})")
            await self.process_message(msg.id, msg.text or "", chat_id)

        source_names = ", ".join(f"'{src.name or src.channel_id}'" for src in self.sources)
        logger.info(f"[Engine] ⚡ Escuchando mensajes en vivo en {len(self.sources)} canal(es): {source_names}...")
        await self.client.run_until_disconnected()

    async def run_backfill(self, limit: int = 15, target_channel: Optional[str] = None) -> int:
        """
        Lee los últimos N mensajes de los canales configurados y los procesa.
        Si se especifica target_channel, procesa solo ese canal; de lo contrario procesa todos.
        """
        await self._resolve_entities()

        total_approved = 0
        channels_to_process = (
            [src for src in self.sources if str(src.channel_id) == str(target_channel)]
            if target_channel
            else self.sources
        )

        for src in channels_to_process:
            entity = self._resolved_entities.get(src.channel_id)
            logger.info(f"[Engine] Obteniendo últimos {limit} mensajes de '{src.name}' ({src.channel_id})...")

            messages = await self.client.get_messages(entity, limit=limit)
            sorted_msgs = sorted(messages, key=lambda m: m.id)

            processed_count = 0
            approved_count = 0

            for msg in sorted_msgs:
                if msg.text:
                    passed = await self.process_message(msg.id, msg.text, src.channel_id)
                    if passed:
                        approved_count += 1
                    processed_count += 1

            logger.info(f"[Engine] [{src.name}] {processed_count} analizados, {approved_count} aprobados.")
            total_approved += approved_count

        return total_approved

    async def close(self):
        """Libera los recursos del motor y del navegador de resolución."""
        if hasattr(self, "resolver"):
            await self.resolver.close()
