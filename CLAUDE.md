# Telegram Deal Forwarder Pro 🚀

Sistema profesional de monitoreo, filtrado y reenvío de ofertas en Telegram con arquitectura limpia orientada a objetos (POO), ingestión en tiempo real (< 50ms) y despacho mediante Telegram Bot API con formato Embed.

---

## 🏗️ Arquitectura del Sistema

```
telegram-arg/
│
├── core/
│   ├── models.py            # Modelos de dominio tipados (DealItem, HistoricalEntry, FilterResult)
│   └── database.py          # Repositorio SQLite (estado de lectura, deduplicación e historial local)
│
├── engine/
│   ├── parser.py            # Parser OOP de ofertas (BunnyDealParser)
│   ├── listener.py          # Listener en tiempo real (Telethon event-driven) y motor de reenvío
│   │
│   ├── filters/             # Pipeline de filtros desacoplados (Chain of Responsibility)
│   │   ├── base.py          # Interfaz BaseFilter
│   │   ├── history.py       # StrictHistoricalLowFilter (filtro anti-ruido con mínimo histórico)
│   │   ├── discount.py      # MinDiscountFilter (% de descuento y rangos de precio)
│   │   ├── dedup.py         # DeduplicationFilter (evita repetir la misma oferta en N horas)
│   │   ├── store.py         # StoreFilter (whitelist / blacklist de tiendas)
│   │   └── pipeline.py      # Orquestador del pipeline con short-circuit
│   │
│   ├── formatters/
│   │   └── embed_formatter.py # Formateador estilo embed (<a href="IMAGEN">&#8205;</a> + botones inline)
│   │
│   └── dispatchers/
│       └── bot_dispatcher.py  # Despachador asíncrono con Telegram Bot API, manejo 429 y backoff
│
├── config.json              # Configuración de canales y umbrales de filtrado
├── main.py                  # Entry point con soporte live, backfill y dry-run
└── requirements.txt
```

---

## ⚙️ Configuración (`config.json`)

```json
{
  "source_channel": "-1002230433964",
  "destination_channel": "-1003952548471",
  "filters": {
    "min_discount": 60,
    "strict_historical_low": true,
    "allow_no_history": false,
    "min_discount_if_no_history": 80,
    "dedup_window_hours": 12,
    "allowed_stores": [],
    "blocked_stores": []
  },
  "options": {
    "include_inline_button": true
  }
}
```

### Variables de entorno (`.env`)
```env
API_ID=tu_api_id
API_HASH=tu_api_hash
SESSION_NAME=telegram_forwarder
# Token del bot de Telegram obtenido de @BotFather:
BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
```

---

## 🚀 Comandos de Ejecución

### 1. Escucha en tiempo real (Producción)
Escucha eventos instantáneos en el canal origen y reenvía por Bot API:
```bash
python main.py
```

### 2. Modo Backfill (Recuperar o probar mensajes recientes)
Analiza y procesa los últimos `N` mensajes históricos del canal:
```bash
python main.py --backfill 20
```

### 3. Modo Simulación (Dry-Run)
Evalúa los mensajes con los filtros y muestra qué se aprobaría y qué se descartaría **sin enviar nada**:
```bash
python main.py --dry-run
```
