# Monitor de movimientos bursátiles

Herramienta para identificar **tendencias**, **volatilidad** y **setups operables** en una
lista de instrumentos, y para extraer los **parámetros** (entrada, stop, objetivo, tamaño de
posición) con los que definir estrategias que después puedan validarse y llevarse a *day
trading*.

Genera dos artefactos en `output/`:

| Archivo | Contenido |
|---|---|
| `monitor.json` | Reporte estructurado: indicadores, tendencia, señales y series por instrumento. Útil para backtesting o para alimentar otras herramientas. |
| `monitor.html` | Dashboard autocontenido (sin CDN, abre offline): ranking, tendencias, setups, detalle por instrumento y parámetros. |

> Es una herramienta de análisis y estudio. **No constituye asesoría de inversión.**

## Uso

```bash
# Sin red ni dependencias: datos sintéticos para probar el dashboard
python3 monitor/stock_monitor.py --demo

# Datos reales (diario + intradía 5 min) — requiere yfinance
pip install yfinance
python3 monitor/stock_monitor.py

# Datos reales sólo diarios, sin dependencias (CSV de stooq.com)
python3 monitor/stock_monitor.py --source stooq

# Sobrescribir la watchlist y la carpeta de salida
python3 monitor/stock_monitor.py --tickers AAPL,NVDA,WALMEX.MX --out-dir /tmp/monitor
```

El script sólo usa la librería estándar de Python 3.9+. `yfinance` es opcional y aporta las
barras intradía (VWAP, rango de apertura, sesgo de sesión). Con `--source stooq` las secciones
intradía quedan vacías.

Flujo recomendado para day trading: ejecutar el monitor **antes de la apertura** (con datos del
cierre anterior) para armar la lista de vigilancia, y **30–60 min después de la apertura** para
recalcular VWAP, rango de apertura y volumen relativo.

## Configuración (`config.json`)

| Bloque | Parámetros |
|---|---|
| `watchlist` | Símbolos en notación Yahoo (`AAPL`, `WALMEX.MX`). |
| `data` | Historial diario/intradía, intervalo intradía y minutos del rango de apertura. |
| `indicators` | Periodos de SMA 20/50/200, EMA 9/21, RSI, MACD, Bollinger, ATR, ADX y umbral de tendencia. |
| `signals` | Umbrales de los setups: sesiones de referencia para rupturas, RVOL mínimo, gap mínimo, distancia a EMA21, rango de ATR % operable y volumen mínimo en dólares. |
| `risk` | Tamaño de cuenta, riesgo por operación (%), stop en múltiplos de ATR, ratio beneficio/riesgo y posición máxima. |

## Qué calcula

**Indicadores por instrumento**: SMA 20/50/200, EMA 9/21, RSI 14, MACD (12/26/9), bandas de
Bollinger (20, 2σ) y su ancho, ATR 14 y ATR %, ADX/DI±, volumen relativo (RVOL) contra el
promedio de 20 sesiones, volumen en dólares, gap de apertura, rango del día, retornos a 5 y 20
sesiones, máximos/mínimos de 20 sesiones y 52 semanas. En intradía: VWAP de la sesión, rango de
apertura (ORB) y sesgo (EMA9/EMA21/VWAP).

**Tendencia diaria**: alineación del precio con SMA 20/50/200 (0–5 puntos) más fuerza por ADX →
`Alcista fuerte · Alcista · Lateral · Bajista · Bajista fuerte`.

**Score de operabilidad (0–100)**: suma de liquidez (volumen en dólares), volatilidad (ATR %
dentro del rango configurado), volumen relativo y fuerza de tendencia. Sirve para priorizar la
lista de vigilancia.

**Setups detectados** (cada uno trae entrada, stop = `stop_atr_multiple × ATR`, objetivo =
`reward_risk_ratio × riesgo`, acciones y nocional según el riesgo por operación):

| Setup | Condición |
|---|---|
| Ruptura de máximos / mínimos | Cierre fuera del rango de N sesiones con RVOL ≥ mínimo. |
| Gap and Go / Gap bajista | Gap ≥ umbral que mantiene la apertura, con RVOL alto. |
| Retroceso / Rebote a EMA21 | En tendencia definida, precio a ≤ 1 ATR de la EMA21 con RSI neutro. |
| Reversión a la media | RSI extremo y precio en la banda de Bollinger. |
| Compresión de volatilidad | Ancho de Bollinger en mínimo de N sesiones (alerta, no entrada). |
| ORB | Ruptura del rango de apertura, más fuerte si coincide con el lado del VWAP. |

## Cómo convertir los parámetros en una estrategia

1. Elegir un setup y fijar sus reglas con los umbrales de `config.json` (por ejemplo: ruptura de
   20 sesiones con RVOL ≥ 1.5, stop 1.5 ATR, objetivo 2 R).
2. Extraer de `monitor.json` los instrumentos y fechas en que se cumplió la condición y validar
   el resultado histórico (backtesting) antes de operar.
3. Operar sólo instrumentos con score de operabilidad alto y sin banderas de liquidez o
   volatilidad; limitar el tamaño con `risk_per_trade_pct` y `max_position_pct`.
4. Revisar y ajustar los umbrales cada semana según lo que muestre el monitor.

## Estructura

```
monitor/
├── README.md            # este documento
├── config.json          # watchlist, indicadores, señales y riesgo
├── stock_monitor.py     # script (sin dependencias; yfinance opcional)
└── output/
    ├── monitor.json     # ejemplo generado con --demo
    └── monitor.html     # ejemplo generado con --demo
```
