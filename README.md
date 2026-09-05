# P
Project Mgmt

## Contenido

- `2024 w4 Strategy.drawio` — diagrama de estrategia (draw.io).
- `monitor/` — **Monitor de movimientos bursátiles**: script en Python que calcula indicadores,
  clasifica tendencias, detecta setups y genera un dashboard HTML autocontenido con parámetros
  para definir estrategias de day trading. Ver [`monitor/README.md`](monitor/README.md).

```bash
python3 monitor/stock_monitor.py --demo   # prueba sin red
python3 monitor/stock_monitor.py          # datos reales (pip install yfinance)
```
