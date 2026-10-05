# 🪡 Ofertas Aguja — Telegram Deal Forwarder Pro

Sistema profesional de monitoreo, filtrado inteligente y reenvío de ofertas en Telegram en tiempo real (< 50ms de latencia) con soporte **Multi-Canal** y **Multi-Proveedor** (Bunny, Nypau / Shark, etc.).

Diseñado con **arquitectura limpia orientada a objetos (POO)**, ingesta pasiva mediante **Telethon (Userbot MTProto)**, filtrado matemático estricto contra **mínimos históricos (Anti-Ruido)** y despacho mediante la **API oficial de Bots de Telegram** en formato Embed.

---

## 🌟 Características Principales

* ⚡ **Ingesta Multi-Canal en Tiempo Real (< 50ms)**: Monitorea múltiples canales simultáneamente basados en eventos (`events.NewMessage`) mediante Telethon MTProto. Cero latencia respecto al polling tradicional.
* 🧩 **Procesadores Especializados por Proveedor (POO)**:
  * `BunnyDealParser`: Especializado en canales de Bunny con hashtags de tienda, bloques de historial `$PRECIO - DD/MM/YYYY` y links directos.
  * `NypauDealParser`: Especializado en canales de Nypau / Shark (`🐘 70% - 99% Nypau 🐘`, `🔥🔥🐘🐘 ALERTA DE OFERTAS🐘🐘🔥🔥`), con soporte para enlaces de redirección Cloudflare (`link.ofertasshark.cl`), formato de historial invertido `DD/MM/YYYY $PRECIO` y discriminación automática de mensajes no estructurados (charlas, textos libres, enlaces sueltos).
* 🛡️ **Seguridad Total Anti-Ban**: Arquitectura desacoplada. Tu cuenta personal únicamente **lee** canales privados/VIP (cero riesgo de baneo por spam), mientras que el despacho se realiza a través de un **Bot Oficial** de Telegram con alta tolerancia de envío.
* 📉 **Filtro Anti-Ruido (Mínimo Histórico Real)**: Compara el precio de oferta actual contra el récord histórico más bajo registrado en el producto. Descarta descuentos falsos basados en precios de lista inflados y permite configurar un umbral agresivo de caída (ej: solo alertas que bajen $\ge 60\%$ respecto a su mínimo histórico).
* 🎨 **Diseño Visual "Ofertas Aguja"**: Formato embed limpio, ordenado y de alta conversión. Muestra el título en negrita, la marca, el salto de precio con flecha `➜`, el historial completo de precios y un botón interactivo `[🛍️ Obtener Oferta]`.
* 🗄️ **Persistencia y Deduplicación Local (SQLite)**: Registra cada oferta en `data/deals.db` para evitar reenviar productos duplicados en ventanas de tiempo configurables (ej: 12 horas).
* 🔍 **Herramientas de Auditoría y Backfill Incluidas**: Script `test_200.py` e `inspect_channel.py` para analizar mensajes de cualquier canal y rescatar únicamente las mejores ofertas bomba.

---

## 🏗️ Arquitectura del Sistema

```
ofertas-aguja/
│
├── core/
│   ├── client.py            # Cliente Telethon compartido y resolución de Peer
│   ├── database.py          # Repositorio SQLite (estado de lectura, deduplicación e historial)
│   └── models.py            # Modelos de dominio tipados (DealItem, HistoricalEntry, FilterResult)
│
├── engine/
│   ├── parser.py            # Parsers orientados a objetos (BunnyDealParser, NypauDealParser, get_parser)
│   ├── listener.py          # Motor de eventos multi-canal y backfill (DealForwarderEngine, ChannelSourceConfig)
│   │
│   ├── filters/             # Pipeline desacoplado (Chain of Responsibility)
│   │   ├── base.py          # Interfaz BaseFilter
│   │   ├── history.py       # StrictHistoricalLowFilter (filtro de caída vs mínimo histórico)
│   │   ├── discount.py      # MinDiscountFilter (% de descuento y límites de precio)
│   │   ├── dedup.py         # DeduplicationFilter (anti-spam temporal con SQLite)
│   │   ├── store.py         # StoreFilter (whitelist y blacklist de tiendas)
│   │   └── pipeline.py      # Orquestador del pipeline con short-circuit y logs
│   │
│   ├── formatters/
│   │   └── embed_formatter.py # Formateador HTML Embed con identidad 'Ofertas Aguja'
│   │
│   └── dispatchers/
│       └── bot_dispatcher.py  # Despachador asíncrono Telegram Bot API (httpx) con manejo 429
│
├── config.json              # Configuración de canales, umbrales y opciones visuales
├── inspect_channel.py       # Utilidad para inspeccionar mensajes crudos y parseados de cualquier proveedor
├── test_200.py              # Auditoría y testing masivo de los últimos 200 mensajes
├── main.py                  # Entry point de producción multi-canal
└── requirements.txt         # Dependencias del proyecto
```

---

## 🚀 Instalación y Puesta en Marcha

### 1. Clonar el repositorio
```bash
git clone https://github.com/Nico-Stade/reenvio-telegram-ofertas.git
cd reenvio-telegram-ofertas
```

### 2. Crear entorno virtual e instalar dependencias
```bash
python -m venv venv
# En Windows:
.\venv\Scripts\activate
# En Linux/Mac:
source venv/bin/activate

pip install -r requirements.txt
```

### 3. Configurar variables de entorno (`.env`)
Copia la plantilla `.env.example`:
```bash
cp .env.example .env
```

Edita `.env` con tus credenciales:
```env
# Obtenidos en https://my.telegram.org/apps
API_ID=12345678
API_HASH=abcdef1234567890abcdef1234567890

# Nombre de la sesión local (.session)
SESSION_NAME=telegram_forwarder

# (Opcional) Session string para servidores headless/Docker sin login interactivo
# SESSION_STRING=

# Token de tu bot obtenido en @BotFather
BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
```

---

## ⚙️ Configuración (`config.json`)

`config.json` soporta una lista de canales fuente (`sources`), cada uno asociado a su procesador correspondiente:

```json
{
  "sources": [
    {
      "channel_id": "-1002230433964",
      "name": "Bunny 60% OFF",
      "parser": "bunny"
    },
    {
      "channel_id": "-1001630413456",
      "name": "🐘 70% - 99% Nypau 🐘",
      "parser": "nypau"
    },
    {
      "channel_id": "-1001815551781",
      "name": "🔥🔥🐘🐘 ALERTA DE OFERTAS🐘🐘🔥🔥",
      "parser": "nypau"
    }
  ],
  "destination_channel": "-1003952548471",
  "filters": {
    "min_discount": 60,
    "strict_historical_low": true,
    "min_drop_percentage": 60.0,
    "allow_no_history": false,
    "dedup_window_hours": 12,
    "allowed_stores": [],
    "blocked_stores": []
  },
  "options": {
    "include_inline_button": true,
    "show_above_text": false
  }
}
```

> **Canales de destino habituales:**
> - Canal de Testing: `-1003952548471`
> - Canal Oficial (Ofertas Aguja): `-1003717939030`

### Explicación de parámetros:
| Parámetro | Tipo | Descripción |
|---|---|---|
| `sources` | `list` | Lista de canales a monitorear. Cada elemento define `channel_id`, `name` y `parser` (`bunny` o `nypau`). |
| `destination_channel` | `string` | ID numérico del canal donde el bot publicará (Testing o Producción). |
| `filters.min_discount` | `int` | Porcentaje de descuento mínimo anunciado respecto al precio de lista. |
| `filters.strict_historical_low` | `bool` | Exige que el precio sea menor o igual al récord histórico más bajo previo. |
| `filters.min_drop_percentage` | `float` | Caída porcentual mínima requerida respecto al mínimo histórico (ej: `60.0` para cazar anomalías/errores de precio). |
| `filters.allow_no_history` | `bool` | Si `false`, descarta ofertas que no traigan bloque de historial verificable. |
| `filters.dedup_window_hours` | `int` | Ventana en horas para evitar reenviar el mismo producto. |
| `options.include_inline_button` | `bool` | Si añade el botón interactivo `[🛍️ Obtener Oferta]`. |
| `options.show_above_text` | `bool` | Posición del embed: `false` pone el texto primero y la foto abajo; `true` foto arriba. |

---

## 💻 Modos de Uso

### Modo Producción (Escucha en vivo 24/7 de todos los canales)
Inicia la escucha en tiempo real de todos los canales configurados:
```bash
python main.py
```

### Modo Backfill (Recuperar mensajes recientes)
Analiza y procesa los últimos `N` mensajes de cada canal configurado:
```bash
python main.py --backfill 15
```

O para un canal específico:
```bash
python main.py --backfill 15 --channel -1001815551781
```

### Modo Simulación (Dry-Run)
Prueba los filtros sobre mensajes recientes sin enviar nada al bot:
```bash
python main.py --dry-run
```

### Inspector de Canales (`inspect_channel.py`)
Permite ver los mensajes crudos o estructurados con detección automática de parser:
```bash
# Inspeccionar canal de Nypau con auto-detección
python inspect_channel.py -c -1001630413456 -n 5 --parse

# Inspeccionar canal de Bunny
python inspect_channel.py -c -1002230433964 -n 5 --parse
```

---

## 📱 Formato de los Mensajes ("Ofertas Aguja")

Cada alerta despachada luce limpia y ordenada:

```text
🪡 Ofertas Aguja · #Ripley ✨
ADIDAS ZAPATILLAS HOMBRE ADIDAS URBANO AZUL VL COURT 3.0 CUERO

$54.990 ➜ $20.990 (-62%)
(Precio lista tienda: $69.990)

Historial 📈
$54.990 - 29/07/2026
$69.990 - 17/07/2026
$54.990 - 14/07/2026

[ Foto Embed de la Oferta ]

[ 🛍️ Obtener Oferta ]
```

*(Cuando un canal como Nypau no informa tienda, el encabezado se muestra limpiamente como `🪡 Ofertas Aguja ✨` sin etiquetas vacías).*

---

## 📄 Licencia

Desarrollado para uso personal y proyectos de monitoreo de ofertas en Telegram.
