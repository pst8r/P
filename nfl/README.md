# Dashboard NFL — resultados y probabilidad de cubrir el spread

Tablero de la jornada de la NFL que se alimenta **en vivo** del marcador oficial: se actualiza
cada vez que se refresca la página y, si se deja abierto, cada N segundos por su cuenta. Para
cada partido muestra el marcador y estima la **probabilidad de que cada equipo cubra el
spread**, la de *push*, la de ganar y la de over/under del total.

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
```

Después basta con abrir `nfl/output/nfl.html`. El HTML no queda congelado: al abrirlo consulta
el marcador otra vez, y el selector **Auto** (20 s / 30 s / 60 s / 3 min / manual) repite la
consulta mientras la pestaña esté visible. Si no hay conexión, el tablero conserva la última
instantánea y lo indica en la esquina superior derecha.

Sólo usa la librería estándar de Python 3.9+. No hay dependencias que instalar.

## Fuente de datos

API pública de resultados de ESPN (`site.api.espn.com/.../football/nfl/scoreboard`), que
entrega marcador, cuarto, reloj, posesión, down & distance y las líneas publicadas (spread,
total y momios). El navegador la consulta directamente; el script de Python usa el mismo
endpoint para la instantánea inicial.

Si la red donde se genera el archivo bloquea ese dominio, el script avisa y escribe la
instantánea con datos demo: el dashboard seguirá intentando la conexión en vivo al abrirse en
un navegador con acceso.

## Controles del tablero

| Control | Para qué sirve |
|---|---|
| Temporada / Fase / Semana | Cambia la jornada consultada. *Actual* deja que la API devuelva la jornada en curso. |
| Auto | Intervalo de auto-refresco; se pausa cuando la pestaña no está visible. |
| Actualizar ahora | Fuerza una consulta inmediata. |
| Filtros | Todos · En vivo · Por jugar · Finalizados · **Cobertura apretada** (partidos en vivo cuyo spread sigue indefinido, < 65 %). |
| Pestañas | Marcadores (tarjetas), Spread ATS (tabla ordenable), Totales, Resumen (récord de la jornada y diferencias contra el mercado) y Metodología. |

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

**Ventaja contra el mercado**: cuando el feed trae momios, se convierten a probabilidad
implícita, se les retira la comisión repartiéndola entre ambos lados y se compara contra el
modelo. Ojo: las líneas del feed suelen ser de cierre, así que en partidos ya iniciados la
comparación enfrenta un modelo en vivo contra un precio previo al arranque. En partidos
terminados no se calcula.

### Límites

- No modela posición en el campo, downs restantes, tiempos fuera, clima ni lesiones.
- Los pesos de números clave son una calibración heurística, no un ajuste a una muestra propia.
- El reloj sólo avanza con cada consulta: entre refrescos las probabilidades quedan congeladas.

## Configuración (`config.json`)

| Bloque | Parámetros |
|---|---|
| `live` | `endpoint` de la API, `refresh_seconds` inicial y `fetch_on_load`. |
| `model` | `sigma_full_game`, `sigma_total`, `sigma_overtime`, `sigma_floor`, `possession_points`, `default_total` y los pesos `key_numbers` por margen. |
| `defaults` | Fase por omisión al pedir una semana concreta. |

Subir `sigma_full_game` aplana las probabilidades (más incertidumbre); bajarla las polariza.
`possession_points` controla cuánto vale tener el balón al final del partido.
