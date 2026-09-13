# Dashboard NFL — resultados y probabilidad de cubrir el spread

Tablero de la jornada de la NFL que se alimenta **en vivo** del marcador oficial: se actualiza
cada vez que se refresca la página y, si se deja abierto, cada N segundos por su cuenta. Para
cada partido muestra el marcador y estima la **probabilidad de que cada equipo cubra el
spread**, la de *push*, la de ganar y la de over/under del total.

Cruza tres fuentes en cada refresco: **ESPN** (marcador, situación de campo, líneas y momios),
**Polymarket** y **Kalshi** (mercados de predicción sobre el ganador). Usa escudos y colores
oficiales de los 32 equipos. Es una herramienta privada de análisis.

Genera dos artefactos en `output/`:

| Archivo | Contenido |
|---|---|
| `nfl.json` | Instantánea estructurada: partidos, líneas, situación y probabilidades. Útil para backtesting o para alimentar otras herramientas. |
| `nfl.html` | Dashboard autocontenido (sin CDN). Lleva el modelo dentro y consulta la API desde el navegador: **no necesita el script de Python para actualizarse**. |

> Herramienta de análisis estadístico y estudio de líneas. **No constituye asesoría de apuestas.**

## Uso

```bash
# Genera el dashboard con la jornada en curso
python3 nfl/nfl_dashboard.py

# Semana concreta / postemporada
python3 nfl/nfl_dashboard.py --season 2025 --week 3
python3 nfl/nfl_dashboard.py --season 2025 --week 2 --seasontype 3

# Sin red: datos sintéticos para probar el tablero
python3 nfl/nfl_dashboard.py --demo

# Sólo marcador y líneas, sin consultar mercados de predicción
python3 nfl/nfl_dashboard.py --no-markets
```

Después basta con abrir `nfl/output/nfl.html`. El HTML no queda congelado: al abrirlo consulta
el marcador otra vez, y el selector **Auto** (20 s / 30 s / 60 s / 3 min / manual) repite la
consulta mientras la pestaña esté visible. Si no hay conexión, el tablero conserva la última
instantánea y lo indica en la esquina superior derecha.

Sólo usa la librería estándar de Python 3.9+. No hay dependencias que instalar.

## Fuentes de datos

| Fuente | Qué aporta | Endpoint |
|---|---|---|
| ESPN | Marcador, cuarto, reloj, posesión, down & distance, línea, total y momios | `site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard` |
| Polymarket | Precio del mercado del ganador (dólares por acción = probabilidad) | `gamma-api.polymarket.com/events?tag_slug=nfl` |
| Kalshi | Precio del mercado del ganador (centavos = probabilidad), serie `KXNFLGAME` | `api.elections.kalshi.com/trade-api/v2/markets` |
| ESPN CDN | Escudos oficiales de los equipos | `a.espncdn.com/i/teamlogos/nfl/500/{abbr}.png` |

Las tres consultas salen **en paralelo** en cada refresco y son independientes: si una falla,
las otras siguen. Una fuente de mercado caída conserva su última lectura y la marca con
asterisco; el estado de cada una se ve en los chips bajo el título.

El emparejamiento entre mercados y partidos se hace por pareja de equipos, con tabla de alias
(`WAS`/`WSH`, `JAC`/`JAX`, `LA`/`LAR`, `OAK`/`LV`…), así que un mercado sin partido
correspondiente simplemente se ignora.

**Si el navegador bloquea una fuente por CORS** (los chips lo dirán), el script de Python la
consulta desde el servidor sin esa restricción: basta con volver a generar la instantánea para
refrescar las cotizaciones embebidas. Un `cron` cada pocos minutos cubre ese caso:

```bash
*/5 * * * * cd /ruta/al/repo && python3 nfl/nfl_dashboard.py --week 3 >/dev/null
```

Si la red donde se genera el archivo bloquea los dominios, el script avisa, marca el estado de
cada fuente y escribe la instantánea con datos demo: el dashboard seguirá intentando la
conexión en vivo al abrirse en un navegador con acceso.

## Identidad visual

Colores primarios y secundarios oficiales de los 32 clubes, más los escudos servidos desde el
CDN de ESPN. Si un logo no carga (sin red o red restringida) se sustituye por un escudo con la
abreviatura sobre el color del equipo, eligiendo texto claro u oscuro según el contraste.
Varios primarios oficiales son casi negros (Raiders, Bears, Patriots): sobre el fondo oscuro
del tablero el color se lleva a un rango visible sin perder la identidad.

Escudos y colores son marcas registradas de cada club. Este tablero es de **uso privado** y no
redistribuye ni comercializa esos activos.

## Controles del tablero

| Control | Para qué sirve |
|---|---|
| Temporada / Fase / Semana | Cambia la jornada consultada. *Actual* deja que la API devuelva la jornada en curso. |
| Auto | Intervalo de auto-refresco; se pausa cuando la pestaña no está visible. |
| Actualizar ahora | Fuerza una consulta inmediata. |
| Filtros | Todos · En vivo · Por jugar · Finalizados · **Cobertura apretada** (partidos en vivo cuyo spread sigue indefinido, < 65 %). |
| Pestañas | Marcadores (tarjetas), Spread ATS, Totales, **Mercados** (Polymarket · Kalshi · modelo), Resumen y Metodología. |
| Chips de fuente | Estado de ESPN, Polymarket y Kalshi en la última lectura. |

Las preferencias de temporada, fase, semana e intervalo se guardan en el navegador.

## Modelo

El margen final (local − visitante) se modela como una normal que se recalcula en cada
refresco:

```
mu    = margen actual + expectativa restante + ajuste por posesión
sigma = sigma_completo × raíz(fracción de partido restante)     (con piso)
```

- **Expectativa restante**: sale de la línea. Un local de −3.5 tiene expectativa de +3.5 puntos
  para el partido completo, prorrateada al tiempo que falta.
- **Posesión**: tener el balón casi no importa en el primer cuarto y pesa al final, así que el
  ajuste escala con el tiempo ya jugado.
- **Tiempo extra**: expectativa neutral y sigma reducida.
- **Números clave**: la normal subestima los márgenes de 3, 7, 10 y 14. En líneas enteras la
  probabilidad de *push* se pondera con esos pesos y el resto se reescala para sumar 100 %.
  Con una línea de −3 antes del kickoff el modelo da ~10 % de push, en línea con el histórico.
- **Total**: mismo esquema sobre la suma de puntos, con su propia sigma.
- **Ganar el partido**: el mismo cálculo con la línea en cero.

### Mercados de predicción

Polymarket y Kalshi cotizan al **ganador**, no al spread. El puente entre ambos es el propio
modelo:

1. El precio se normaliza entre los dos lados para que sumen 100 % (en Kalshi se toma el punto
   medio entre compra y venta).
2. Esa probabilidad de victoria se invierte sobre la normal del modelo para obtener el
   **margen implícito** que la justifica.
3. Con ese margen y la misma sigma se calcula la **probabilidad de cubrir implícita en el
   mercado**, ya comparable con la del modelo sobre la misma línea.
4. El **consenso** mezcla modelo y mercados según `consensus.model_weight` (0.5 por omisión),
   y la **divergencia** mide cuánto se separa el mercado del modelo: es la señal de qué partido
   vale la pena revisar.

La probabilidad de cubrir atribuida a Polymarket o Kalshi es, por tanto, una derivación del
modelo a partir de un precio real de ganador, no un precio de spread observado. Con poco
volumen el diferencial se ensancha, por eso la pestaña Mercados muestra el volumen.

**Ventaja contra el mercado**: cuando el feed trae momios, se convierten a probabilidad
implícita, se les retira la comisión repartiéndola entre ambos lados y se compara contra el
modelo. Ojo: las líneas del feed suelen ser de cierre, así que en partidos ya iniciados la
comparación enfrenta un modelo en vivo contra un precio previo al arranque. En partidos
terminados no se calcula.

### Límites

- No modela posición en el campo, downs restantes, tiempos fuera, clima ni lesiones.
- Los pesos de números clave son una calibración heurística, no un ajuste a una muestra propia.
- El reloj sólo avanza con cada consulta: entre refrescos las probabilidades quedan congeladas.
- Polymarket y Kalshi no cubren todos los partidos ni toda la semana; los que no tienen mercado
  se muestran sólo con el modelo.

## Configuración (`config.json`)

| Bloque | Parámetros |
|---|---|
| `live` | `endpoint` del marcador, `refresh_seconds` inicial y `fetch_on_load`. |
| `sources` | `polymarket` (`enabled`, `endpoint`, `query`) y `kalshi` (`enabled`, `endpoint`, `series_ticker`). Poner `enabled: false` apaga esa fuente en el script y en el navegador. |
| `consensus` | `model_weight`: peso del modelo frente a los mercados (0 = sólo mercados, 1 = sólo modelo). |
| `assets` | `logos` (usar escudos o sólo colores) y `logo_template`. |
| `model` | `sigma_full_game`, `sigma_total`, `sigma_overtime`, `sigma_floor`, `possession_points`, `default_total` y los pesos `key_numbers` por margen. |
| `defaults` | Fase por omisión al pedir una semana concreta. |

Subir `sigma_full_game` aplana las probabilidades (más incertidumbre); bajarla las polariza.
`possession_points` controla cuánto vale tener el balón al final del partido.
