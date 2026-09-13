# Dashboard NFL — resultados y probabilidad de cubrir el spread

Tablero de la jornada de la NFL que se alimenta **en vivo** del marcador oficial: se actualiza
cada vez que se refresca la página y, si se deja abierto, cada N segundos por su cuenta. Para
cada partido muestra el marcador y estima la **probabilidad de que cada equipo cubra el
spread**, la de *push*, la de ganar y la de over/under del total.

Cruza tres fuentes en cada refresco: **ESPN** (marcador, situación de campo, líneas y momios),
**Polymarket** y **Kalshi** (mercados de predicción sobre el ganador). Usa escudos y colores
oficiales de los 32 equipos. Es una herramienta privada de análisis.

Incluye una sección de **quiniela propia** con la metodología de Yahoo Fantasy Pick'em: capturas
tus pronósticos, el tablero los contrasta contra los resultados en vivo y calcula cuántos puntos
llevas y cuántos proyectas terminar la semana. La quiniela siempre corresponde a la jornada que
estás revisando.

Y un **pronóstico de la jornada siguiente** que ordena la información disponible: reporte de
lesiones, desempeño de la semana anterior, noticias del plantel —incluidas las que no son
deportivas— y cotizaciones de los mercados de predicción.

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

# Con tu quiniela para puntuarla contra los resultados
python3 nfl/nfl_dashboard.py --picks nfl/picks.json
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
| ESPN · lesiones | Reporte de lesiones por equipo (jugador, posición, estatus) | `site.api.espn.com/.../nfl/injuries` |
| ESPN · noticias | Titulares de la liga con los equipos que menciona cada uno | `site.api.espn.com/.../nfl/news` |
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
| Pestañas | Marcadores (tarjetas), Spread ATS, Totales, **Mercados** (Polymarket · Kalshi · modelo), **Mi quiniela**, **Pronóstico**, Resumen y Metodología. |
| Chips de fuente | Estado de ESPN, Polymarket y Kalshi en la última lectura. |

Las preferencias de temporada, fase, semana e intervalo se guardan en el navegador.

## Mi quiniela (metodología Yahoo Pick'em)

La pestaña **Mi quiniela** replica las dos variantes de Yahoo Pro Football Pick'em:

| Ajuste | Opciones |
|---|---|
| Pronóstico | **Contra el spread** (gana después de aplicar la línea) o **directo** (gana el partido). |
| Puntuación | **Confianza**: repartes los valores 1 a N entre los N partidos de la semana, cada valor una sola vez; el acierto paga los puntos asignados y el fallo paga cero. **Estándar**: un punto por acierto. |
| Desempate | Total combinado de puntos del partido que elijas. |
| Push | Un empate contra la línea paga lo que indique `pickem.push_points`, cero por omisión. |

Con confianza, el máximo semanal es N × (N + 1) / 2: 136 puntos en una semana de 16 partidos.

### Qué calcula

| Indicador | Significado |
|---|---|
| Puntos asegurados | Suma de los partidos ya terminados. |
| En juego ahora | Valor esperado de los partidos en curso: confianza × probabilidad de que tu pronóstico acierte. |
| Proyección de la semana | Asegurados + en juego + pendientes. Es la respuesta a «cuántos puntos voy a sacar». |
| Máximo alcanzable | Lo que sumarías si aciertas todo lo que falta. |
| Efectividad | Aciertos sobre partidos ya resueltos. |

La probabilidad de acierto sale del **consenso** entre el modelo y los mercados de predicción
cuando hay cotización, y del modelo solo cuando no la hay. Cada refresco del marcador recalcula
puntos y proyección.

### Cómo se usa

1. Elige tipo de pronóstico y puntuación.
2. Marca un equipo por partido y asigna la confianza, o pulsa **Autollenar pendientes** para que
   el modelo ordene los partidos por probabilidad y reparta los valores disponibles.
3. Fija el desempate: partido y total combinado.
4. La quiniela se guarda sola en el navegador, por temporada, fase y semana.

### La quiniela sigue a la jornada

Cada quiniela queda sellada con temporada, fase y semana. Al cambiar de jornada en el selector se
carga la quiniela de esa jornada, y la semana que pides manda sobre la que devuelva el feed.

Si abres una quiniela capturada para otra semana, el tablero **no la puntúa** —mezclar
pronósticos de una semana con resultados de otra no significa nada— y ofrece dos salidas:
reasignarla a la jornada que estás viendo o empezar una nueva. El script hace lo mismo: si
`picks.json` trae una semana distinta a la de la instantánea, avisa y no la puntúa.

El botón **Exportar JSON** descarga un `picks.json` con el mismo formato que lee el script; si lo
guardas en `nfl/picks.json`, la instantánea que genera Python ya viene con tu quiniela puntuada
(útil para versionarla o para abrir el tablero en otro equipo). **Importar JSON** hace el camino
inverso. Ver [`picks.example.json`](picks.example.json):

```bash
python3 nfl/nfl_dashboard.py --picks nfl/picks.json
```

Las claves de `picks` son `VISITANTE@LOCAL` con las abreviaturas del marcador, así que la quiniela
sobrevive a regenerar la instantánea.

Dos reglas para que el ejercicio sea honesto:

- **Autollenar pendientes** sólo toca partidos que no han empezado: usar la probabilidad de un
  partido en curso o terminado sería pronosticar con el resultado a la vista. Respeta los valores
  de confianza ya comprometidos y reparte los que quedan libres.
- **Bloquear iniciados** (activo por omisión) impide editar el pronóstico de un partido que ya
  arrancó. Se puede desactivar si estás capturando una quiniela a media jornada.

El tablero avisa si repites un valor de confianza, si dejas huecos en el rango 1..N o si faltan
partidos por pronosticar.

## Pronóstico de la jornada siguiente

La pestaña **Pronóstico** construye la semana que viene con la información que ya existe. Parte
del margen que implica la línea publicada y le aplica cuatro ajustes, cada uno con tope propio y
un tope conjunto:

| Ajuste | De dónde sale | Tope |
|---|---|---|
| Lesiones | Reporte oficial: cada jugador pesa por posición y estatus (fuera, duda, probable). El quarterback domina la escala. | `injury_cap`, 4.0 pts por equipo |
| Forma | Margen contra la línea de la semana anterior, escalado. Una semana es muestra chica, por eso pesa poco. | `form_cap`, 2.5 pts |
| Noticias | Titulares clasificados por reglas de palabras clave en cuatro categorías. | `news_cap`, 1.5 pts por equipo |
| Mercado | Diferencia entre el margen que implica el precio de Polymarket o Kalshi y la base, con el peso del consenso. | `market_cap`, 3.0 pts |
| **Conjunto** | Suma de los cuatro | `total_cap`, 6.0 pts |

Las categorías de noticias, configurables en `forecast.news_rules`:

| Categoría | Qué detecta | Peso |
|---|---|---|
| Fuera de cancha | Suspensiones, arrestos, demandas, investigaciones, despidos de entrenador | −0.8 |
| Plantel inestable | Solicitudes de traspaso, disputas de contrato, bajas, cambios de coordinador | −0.4 |
| Refuerzo | Altas, regresos, jugadores activados o autorizados a jugar | +0.3 |
| Logística | Juegos internacionales, semana corta, clima extremo, viajes | −0.3 |

El resultado por partido es el margen esperado, el lado sugerido, su probabilidad de cubrir y la
confianza ordenada de menor a mayor certeza, como pide Yahoo. Cada fila muestra las lesiones y
los titulares que movieron el número, para que puedas discutir el ajuste en lugar de aceptarlo.

**Aplicar a mi quiniela** guarda esos picks en la semana pronosticada y lleva el tablero a esa
jornada para que la ajustes a mano.

```bash
# Genera también el pronóstico de la jornada siguiente en la instantánea
python3 nfl/nfl_dashboard.py --forecast

# Pronostica una jornada concreta
python3 nfl/nfl_dashboard.py --forecast-week 7
```

### Límites del pronóstico

- La clasificación de noticias es por palabras clave, no por lectura: puede marcar de más o
  pasar por alto un matiz. Los titulares que la dispararon se muestran siempre.
- El peso de una lesión sale de la posición, no del jugador concreto ni de la calidad de su
  reemplazo.
- Con una sola semana de resultados la forma es ruido; gana peso conforme avanza la temporada
  sólo si amplías la muestra.
- Si la jornada siguiente aún no tiene líneas publicadas, la base es ventaja de local más forma,
  bastante más débil. La columna lo indica.

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
| `forecast` | `home_field`, pesos y topes de cada ajuste (`form_weight`, `form_cap`, `injury_cap`, `news_cap`, `market_cap`, `total_cap`), `position_weights`, `status_weights` y `news_rules`. |
| `pickem` | `mode` (`ats` o `su`), `scoring` (`confidence` o `standard`) y `push_points` por omisión de la quiniela. |
| `assets` | `logos` (usar escudos o sólo colores) y `logo_template`. |
| `model` | `sigma_full_game`, `sigma_total`, `sigma_overtime`, `sigma_floor`, `possession_points`, `default_total` y los pesos `key_numbers` por margen. |
| `defaults` | Fase por omisión al pedir una semana concreta. |

Subir `sigma_full_game` aplana las probabilidades (más incertidumbre); bajarla las polariza.
`possession_points` controla cuánto vale tener el balón al final del partido.
