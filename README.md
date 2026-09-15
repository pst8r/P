# P
Project Mgmt

## Contenido

- `2024 w4 Strategy.drawio` — diagrama de estrategia (draw.io).
- `monitor/` — **Monitor de movimientos bursátiles**: script en Python que calcula indicadores,
  clasifica tendencias, detecta setups y genera un dashboard HTML autocontenido con parámetros
  para definir estrategias de day trading. Ver [`monitor/README.md`](monitor/README.md).

- `nfl/` — **Dashboard NFL**: script en Python que consulta el marcador oficial en vivo, estima
  la probabilidad de cubrir el spread de cada partido y genera un dashboard HTML autocontenido
  que se refresca solo. Ver [`nfl/README.md`](nfl/README.md).

- `t8/` — **T8 IT Service Desk**: espacio de diseño de una plataforma de mesa de servicio
  agéntica (ITIL 4 + KCS v6). Actualmente solo documentación de arquitectura, sin código.
  Ver [`t8/README.md`](t8/README.md).

```bash
python3 monitor/stock_monitor.py --demo   # prueba sin red
python3 monitor/stock_monitor.py          # datos reales (pip install yfinance)

python3 nfl/nfl_dashboard.py              # jornada NFL en curso
python3 nfl/nfl_dashboard.py --demo       # prueba sin red
```
