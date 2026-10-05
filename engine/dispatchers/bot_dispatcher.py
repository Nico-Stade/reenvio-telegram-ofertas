"""
engine/dispatchers/bot_dispatcher.py — Despachador asíncrono con Telegram Bot API estilo Embed.
Envía siempre como sendMessage con preview embebida (estilo Bunny / embed card), NO como foto gigante.
"""
import asyncio
import json
import random
from typing import List, Optional, Dict, Any
import httpx
from loguru import logger
from core.models import DealItem
from engine.formatters.embed_formatter import EmbedMessageFormatter


class TelegramBotDispatcher:
    def __init__(
        self,
        bot_tokens: List[str],
        destination_chat_id: str,
        formatter: Optional[EmbedMessageFormatter] = None,
        proxies: Optional[List[str]] = None,
        include_inline_button: bool = True,
        show_above_text: bool = False,
    ):
        self.bot_tokens = [t.strip() for t in bot_tokens if t and t.strip()]
        if not self.bot_tokens:
            raise ValueError("Se requiere al menos un BOT_TOKEN válido para el despachador.")
        
        self.destination_chat_id = str(destination_chat_id).strip()
        self.formatter = formatter or EmbedMessageFormatter()
        self.proxies = proxies or []
        self.include_inline_button = include_inline_button
        self.show_above_text = show_above_text
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=15.0)
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    def _pick_token(self) -> str:
        """Selecciona un token del pool o el principal."""
        return random.choice(self.bot_tokens)

    async def dispatch(self, deal: DealItem) -> bool:
        """
        Envía el mensaje como un Embed limpio usando sendMessage + preview anclado a la imagen.
        """
        client = await self._get_client()
        text = self.formatter.build_message(deal)
        reply_markup = self.formatter.build_reply_markup(deal) if self.include_inline_button else None
        max_retries = 5

        payload: Dict[str, Any] = {
            "chat_id": self.destination_chat_id,
            "text": text,
            "parse_mode": "HTML",
        }

        # Anclar la previsualización estrictamente a la URL de la imagen (evita previews de la tienda)
        if deal.image_url:
            payload["link_preview_options"] = {
                "is_disabled": False,
                "url": deal.image_url,
                "prefer_large_media": True,
                "show_above_text": self.show_above_text,
            }
        else:
            payload["link_preview_options"] = {"is_disabled": True}

        if reply_markup:
            payload["reply_markup"] = json.dumps(reply_markup)

        for attempt in range(1, max_retries + 1):
            token = self._pick_token()
            url = f"https://api.telegram.org/bot{token}/sendMessage"

            try:
                response = await client.post(url, json=payload)

                if response.status_code == 200:
                    logger.success(f"[BotDispatcher] ✓ Embed enviado a {self.destination_chat_id} ('{deal.title[:35]}...')")
                    return True

                if response.status_code == 429:
                    retry_after = int(response.json().get("parameters", {}).get("retry_after", 3))
                    logger.warning(f"[BotDispatcher] 429 rate limit. Esperando {retry_after}s... (Intento {attempt})")
                    await asyncio.sleep(retry_after)
                    continue

                if response.status_code == 400:
                    logger.error(f"[BotDispatcher] 400 Bad Request: {response.text[:250]}")
                    return False

                logger.warning(f"[BotDispatcher] HTTP {response.status_code}: {response.text[:150]}")
                await asyncio.sleep(min(2.5, 0.5 * attempt))

            except httpx.RequestError as exc:
                logger.warning(f"[BotDispatcher] Error de red ({type(exc).__name__}). Reintentando...")
                await asyncio.sleep(min(2.5, 0.5 * attempt))

        return False
