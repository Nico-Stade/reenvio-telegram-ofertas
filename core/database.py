"""
core/database.py — Repositorio SQLite para estado, persistencia y deduplicación.
"""
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List
import hashlib
from loguru import logger
from core.models import DealItem, HistoricalEntry


class SQLiteDealRepository:
    def __init__(self, db_path: str = "data/deals.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Crea las tablas necesarias si no existen."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Tabla de estado de lectura por canal/regla
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS channel_state (
                    channel_id TEXT PRIMARY KEY,
                    last_message_id INTEGER NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Tabla de ofertas procesadas / enviadas para deduplicación e historial local
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sent_deals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    deal_hash TEXT UNIQUE,
                    product_url TEXT,
                    title TEXT,
                    store TEXT,
                    original_price INTEGER,
                    offer_price INTEGER,
                    discount_percentage INTEGER,
                    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Historial local acumulado de precios por producto
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS price_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_key TEXT,
                    price INTEGER,
                    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sent_deals_hash ON sent_deals(deal_hash)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_price_history_key ON price_history(product_key)")
            conn.commit()

    @staticmethod
    def compute_deal_hash(deal: DealItem) -> str:
        """Genera un hash único basado en la URL limpia o en el título normalizado."""
        key = deal.clean_product_url or deal.title.strip().lower()
        return hashlib.sha256(key.encode("utf-8")).hexdigest()

    def get_last_message_id(self, channel_id: str) -> Optional[int]:
        """Obtiene el último ID de mensaje procesado para un canal."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT last_message_id FROM channel_state WHERE channel_id = ?", (str(channel_id),))
            row = cursor.fetchone()
            return row["last_message_id"] if row else None

    def set_last_message_id(self, channel_id: str, message_id: int) -> None:
        """Actualiza el último ID de mensaje procesado."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO channel_state (channel_id, last_message_id, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(channel_id) DO UPDATE SET
                    last_message_id = excluded.last_message_id,
                    updated_at = CURRENT_TIMESTAMP
            """, (str(channel_id), message_id))
            conn.commit()

    def is_deal_recently_sent(self, deal: DealItem, window_hours: int = 12) -> bool:
        """Verifica si el mismo producto fue enviado en las últimas N horas."""
        deal_hash = self.compute_deal_hash(deal)
        cutoff = datetime.utcnow() - timedelta(hours=window_hours)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT sent_at FROM sent_deals
                WHERE deal_hash = ? AND sent_at >= ?
            """, (deal_hash, cutoff.strftime("%Y-%m-%d %H:%M:%S")))
            return cursor.fetchone() is not None

    def record_sent_deal(self, deal: DealItem) -> None:
        """Registra una oferta que fue enviada exitosamente."""
        deal_hash = self.compute_deal_hash(deal)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO sent_deals 
                (deal_hash, product_url, title, store, original_price, offer_price, discount_percentage, sent_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (
                deal_hash,
                deal.clean_product_url,
                deal.title,
                deal.store,
                deal.original_price,
                deal.offer_price,
                deal.discount_percentage
            ))

            # Guardar también en el histórico de precios local
            product_key = deal.clean_product_url or deal.title.strip().lower()
            cursor.execute("""
                INSERT INTO price_history (product_key, price, recorded_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
            """, (product_key, deal.offer_price))

            conn.commit()

    def get_local_min_price(self, deal: DealItem) -> Optional[int]:
        """Consulta el precio mínimo registrado localmente en la base de datos."""
        product_key = deal.clean_product_url or deal.title.strip().lower()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT MIN(price) as min_p FROM price_history
                WHERE product_key = ?
            """, (product_key,))
            row = cursor.fetchone()
            return row["min_p"] if row and row["min_p"] is not None else None
