# 🪡 Ofertas Aguja — Telegram Deal Forwarder Pro

Sistema profesional de monitoreo, filtrado inteligente y reenvío de ofertas en Telegram en tiempo real (< 50ms de latencia). 

Diseñado con **arquitectura limpia orientada a objetos (POO)**, ingesta pasiva mediante **Telethon (Userbot MTProto)**, filtrado matemático estricto contra **mínimos históricos (Anti-Ruido)** y despacho mediante la **API oficial de Bots de Telegram** en formato Embed.

---

## 🌟 Características Principales

* ⚡ **Ingesta en Tiempo Real (< 50ms)**: Basado en eventos (`events.NewMessage`) mediante Telethon MTProto. Cero latencia respecto al polling tradicional.
* 🛡️ **Seguridad Total Anti-Ban**: Arquitectura desacoplada. Tu cuenta personal únicamente **lee** canales privados/VIP (cero riesgo de baneo por spam), mientras que el despacho se realiza a través de un **Bot Oficial** de Telegram con alta tolerancia de envío.
* 📉 **Filtro Anti-Ruido (Mínimo Histórico Real)**: Compara el precio de oferta actual contra el récord histórico más bajo registrado en el producto. Descarta descuentos falsos basados en precios de lista inflados y permite configurar un umbral agresivo de caída (ej: solo alertas que bajen $\ge 60\%$ respecto a su mínimo histórico).
* 🎨 **Diseño Visual "Ofertas Aguja"**: Formato embed limpio, ordenado y de alta conversión. Muestra el título en negrita, la tienda, el salto de precio con flecha `➜`, el historial completo de precios y un botón interactivo `[🛍️ Obtener Oferta]`.
* 🗄️ **Persistencia y Deduplicación Local (SQLite)**: Registra cada oferta en `data/deals.db` para evitar reenviar productos duplicados en ventanas de tiempo configurables (ej: 12 horas).
* 🔍 **Herramientas de Auditoría y Backfill Incluidas**: Script `test_200.py` para analizar los últimos 200 mensajes de cualquier canal y rescatar únicamente las mejores ofertas bomba.

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
│   ├── parser.py            # Parser orientado a objetos (BunnyDealParser)
│   ├── listener.py          # Motor de eventos en vivo y backfill (DealForwarderEngine)
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
├── inspect_channel.py       # Utilidad para inspeccionar mensajes crudos y parseados de un canal
├── test_200.py              # Auditoría y testing masivo de los últimos 200 mensajes
├── main.py                  # Entry point de producción
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

> **Nota:** La primera vez que ejecutes el script, Telethon te pedirá tu número de teléfono y el código de verificación de Telegram por consola para generar el archivo de sesión seguro local.

---

## ⚙️ Configuración (`config.json`)

Edita `config.json` para definir tus canales de origen, destino y umbrales:

```json
{
  "source_channel": "-1002230433964",
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

### Explicación de parámetros:
| Parámetro | Tipo | Descripción |
|---|---|---|
| `source_channel` | `string` | ID numérico o `@username` del canal fuente a monitorear. |
| `destination_channel` | `string` | ID numérico o `@username` del canal donde el bot publicará. |
| `filters.min_discount` | `int` | Porcentaje de descuento mínimo que debe anunciar la oferta. |
| `filters.strict_historical_low` | `bool` | Exige que el precio sea menor o igual al récord histórico previo. |
| `filters.min_drop_percentage` | `float` | Caída porcentual mínima respecto al mínimo histórico (ej: `60.0` para casos bomba). |
| `filters.allow_no_history` | `bool` | Si `false`, descarta ofertas que no traigan bloque de historial verificable. |
| `filters.dedup_window_hours` | `int` | Ventana en horas para no reenviar el mismo producto repetido. |
| `options.include_inline_button` | `bool` | Si añade el botón interactivo `[🛍️ Obtener Oferta]`. |
| `options.show_above_text` | `bool` | Posición del embed: `false` pone el texto primero y la foto abajo; `true` foto arriba. |

---

## 💻 Modos de Uso

### Modo Producción (Escucha en vivo 24/7)
Inicia la escucha en tiempo real por eventos de Telegram:
```bash
python main.py
```

### Modo Backfill (Recuperar mensajes recientes)
Analiza y procesa los últimos `N` mensajes históricos:
```bash
python main.py --backfill 15
```

### Modo Simulación (Dry-Run)
Prueba los filtros sobre mensajes recientes sin enviar nada al bot:
```bash
python main.py --dry-run
```

### Herramienta de Auditoría Masiva (`test_200.py`)
Inspecciona los últimos 200 mensajes del canal con filtros agresivos de caída:
```bash
# Ver en consola las mayores caídas sin publicar:
python test_200.py --dry-run --min-drop 40

# Publicar al canal destino solo las ofertas que cayeron >= 60% vs histórico:
python test_200.py --min-drop 60
```

### Inspector de Canales (`inspect_channel.py`)
Permite ver los mensajes crudos o estructurados de cualquier canal:
```bash
python inspect_channel.py -c -1002230433964 -n 5 --parse
```

---

## 📱 Formato de los Mensajes ("Ofertas Aguja")

Cada alerta despachada luce de la siguiente forma:

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

---

## 📄 Licencia

Desarrollado para uso personal y proyectos de monitoreo de ofertas en Telegram.
