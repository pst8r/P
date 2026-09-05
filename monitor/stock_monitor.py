#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Monitor de movimientos bursátiles
=================================

Descarga precios (diarios + intradía), calcula indicadores técnicos, clasifica
la tendencia de cada instrumento, detecta *setups* operables y genera:

  * output/monitor.json  — reporte estructurado (tendencias, señales, parámetros)
  * output/monitor.html  — dashboard autocontenido (sin CDN, abre offline)

Uso rápido
----------
  python3 stock_monitor.py --demo                 # datos sintéticos, sin red
  python3 stock_monitor.py                        # yfinance (pip install yfinance)
  python3 stock_monitor.py --source stooq         # sólo diario, sin dependencias
  python3 stock_monitor.py --tickers AAPL,NVDA    # sobrescribe la watchlist

El script sólo depende de la librería estándar. `yfinance` es opcional y se
usa únicamente para descargar datos reales (diario + intradía 5m).

Aviso: es una herramienta de análisis y estudio de parámetros. No constituye
asesoría de inversión.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import io
import json
import math
import os
import random
import sys
import urllib.request
from typing import Dict, List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONFIG = os.path.join(HERE, "config.json")
DEFAULT_OUT = os.path.join(HERE, "output")


# ---------------------------------------------------------------------------
# Utilidades numéricas (sin numpy/pandas)
# ---------------------------------------------------------------------------

def sma(values: List[float], n: int) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(values)
    acc = 0.0
    for i, v in enumerate(values):
        acc += v
        if i >= n:
            acc -= values[i - n]
        if i >= n - 1:
            out[i] = acc / n
    return out


def ema(values: List[float], n: int) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(values)
    if len(values) < n:
        return out
    k = 2.0 / (n + 1)
    seed = sum(values[:n]) / n
    out[n - 1] = seed
    prev = seed
    for i in range(n, len(values)):
        prev = values[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def stdev(values: List[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = sum(values) / len(values)
    return math.sqrt(sum((v - m) ** 2 for v in values) / len(values))


def rsi(closes: List[float], n: int = 14) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(closes)
    if len(closes) <= n:
        return out
    gains, losses = 0.0, 0.0
    for i in range(1, n + 1):
        d = closes[i] - closes[i - 1]
        if d >= 0:
            gains += d
        else:
            losses -= d
    ag, al = gains / n, losses / n
    out[n] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    for i in range(n + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        g = max(d, 0.0)
        l = max(-d, 0.0)
        ag = (ag * (n - 1) + g) / n
        al = (al * (n - 1) + l) / n
        out[i] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    return out


def macd(closes: List[float], fast: int, slow: int, signal: int):
    ef, es = ema(closes, fast), ema(closes, slow)
    line: List[Optional[float]] = [
        (a - b) if (a is not None and b is not None) else None for a, b in zip(ef, es)
    ]
    valid = [v for v in line if v is not None]
    sig_valid = ema(valid, signal)
    sig: List[Optional[float]] = [None] * len(closes)
    j = 0
    for i, v in enumerate(line):
        if v is not None:
            sig[i] = sig_valid[j]
            j += 1
    hist = [
        (a - b) if (a is not None and b is not None) else None for a, b in zip(line, sig)
    ]
    return line, sig, hist


def bollinger(closes: List[float], n: int, k: float):
    mid = sma(closes, n)
    up: List[Optional[float]] = [None] * len(closes)
    lo: List[Optional[float]] = [None] * len(closes)
    width: List[Optional[float]] = [None] * len(closes)
    for i in range(n - 1, len(closes)):
        sd = stdev(closes[i - n + 1 : i + 1])
        m = mid[i]
        if m is None:
            continue
        up[i] = m + k * sd
        lo[i] = m - k * sd
        width[i] = (up[i] - lo[i]) / m * 100 if m else None
    return mid, up, lo, width


def true_range(h: List[float], l: List[float], c: List[float]) -> List[float]:
    tr = [h[0] - l[0]]
    for i in range(1, len(c)):
        tr.append(max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])))
    return tr


def wilder(values: List[float], n: int) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(values)
    if len(values) < n:
        return out
    prev = sum(values[:n]) / n
    out[n - 1] = prev
    for i in range(n, len(values)):
        prev = (prev * (n - 1) + values[i]) / n
        out[i] = prev
    return out


def atr(h, l, c, n: int) -> List[Optional[float]]:
    return wilder(true_range(h, l, c), n)


def adx(h, l, c, n: int):
    """Devuelve (adx, di_plus, di_minus) con suavizado de Wilder."""
    size = len(c)
    tr = true_range(h, l, c)
    dmp = [0.0] * size
    dmm = [0.0] * size
    for i in range(1, size):
        up = h[i] - h[i - 1]
        dn = l[i - 1] - l[i]
        dmp[i] = up if (up > dn and up > 0) else 0.0
        dmm[i] = dn if (dn > up and dn > 0) else 0.0
    s_tr, s_p, s_m = wilder(tr, n), wilder(dmp, n), wilder(dmm, n)
    dip: List[Optional[float]] = [None] * size
    dim: List[Optional[float]] = [None] * size
    dx: List[float] = []
    dx_idx: List[int] = []
    for i in range(size):
        if s_tr[i] and s_p[i] is not None and s_m[i] is not None:
            dip[i] = 100 * s_p[i] / s_tr[i]
            dim[i] = 100 * s_m[i] / s_tr[i]
            den = dip[i] + dim[i]
            dx.append(100 * abs(dip[i] - dim[i]) / den if den else 0.0)
            dx_idx.append(i)
    adx_valid = wilder(dx, n)
    out: List[Optional[float]] = [None] * size
    for j, i in enumerate(dx_idx):
        out[i] = adx_valid[j]
    return out, dip, dim


def pct(a: float, b: float) -> float:
    return (a / b - 1) * 100 if b else 0.0


def r2(x: Optional[float], nd: int = 2) -> Optional[float]:
    return None if x is None else round(x, nd)


# ---------------------------------------------------------------------------
# Fuentes de datos
# ---------------------------------------------------------------------------

Bar = Dict[str, float]  # {"t": iso, "o","h","l","c","v"}


def fetch_yfinance(symbol: str, data_cfg: dict):
    import yfinance as yf  # opcional

    tk = yf.Ticker(symbol)
    daily_df = tk.history(period=data_cfg.get("daily_period", "1y"), interval="1d", auto_adjust=False)
    intra_df = tk.history(
        period=data_cfg.get("intraday_period", "5d"),
        interval=data_cfg.get("intraday_interval", "5m"),
        auto_adjust=False,
    )

    def to_bars(df, fmt):
        bars = []
        for ts, row in df.iterrows():
            if any(math.isnan(float(row[k])) for k in ("Open", "High", "Low", "Close")):
                continue
            bars.append(
                {
                    "t": ts.strftime(fmt),
                    "o": float(row["Open"]),
                    "h": float(row["High"]),
                    "l": float(row["Low"]),
                    "c": float(row["Close"]),
                    "v": float(row["Volume"]) if not math.isnan(float(row["Volume"])) else 0.0,
                }
            )
        return bars

    return to_bars(daily_df, "%Y-%m-%d"), to_bars(intra_df, "%Y-%m-%d %H:%M")


def fetch_stooq(symbol: str):
    """Diario únicamente. AAPL -> aapl.us ; WALMEX.MX -> walmex.mx"""
    s = symbol.lower()
    s = s if "." in s else f"{s}.us"
    url = f"https://stooq.com/q/d/l/?s={s}&i=d"
    with urllib.request.urlopen(url, timeout=30) as resp:
        text = resp.read().decode("utf-8", "replace")
    bars = []
    for row in csv.DictReader(io.StringIO(text)):
        try:
            bars.append(
                {
                    "t": row["Date"],
                    "o": float(row["Open"]),
                    "h": float(row["High"]),
                    "l": float(row["Low"]),
                    "c": float(row["Close"]),
                    "v": float(row.get("Volume") or 0),
                }
            )
        except (KeyError, ValueError):
            continue
    return bars[-260:], []


def demo_series(symbol: str, days: int = 260, sessions: int = 5, bars_per_session: int = 78):
    """Serie sintética determinista por símbolo (GBM con regímenes de tendencia)."""
    seed = int(hashlib.md5(symbol.encode()).hexdigest()[:8], 16)
    rng = random.Random(seed)
    known = {  # precios de referencia aproximados para que la demo sea verosímil
        "AAPL": 230, "MSFT": 430, "NVDA": 175, "AMD": 160, "TSLA": 340, "AMZN": 220,
        "META": 720, "GOOGL": 200, "SPY": 640, "QQQ": 570, "WALMEX.MX": 62,
        "GFNORTEO.MX": 180, "AMXB.MX": 17, "FEMSAUBD.MX": 190,
    }
    base = known.get(symbol, rng.choice([18, 45, 90, 150, 240, 420]))
    vol = rng.uniform(0.012, 0.035)
    base_vol = rng.uniform(2e6, 6e7)
    end = dt.date.today()
    dates = []
    d = end
    while len(dates) < days:
        if d.weekday() < 5:
            dates.append(d)
        d -= dt.timedelta(days=1)
    dates.reverse()

    # regímenes: cada 40-70 días cambia el drift
    price = base
    daily: List[Bar] = []
    drift = 0.0
    regime_left = 0
    for i, day in enumerate(dates):
        if regime_left <= 0:
            drift = rng.choice([-0.0025, -0.001, 0.0, 0.0008, 0.0015, 0.003])
            regime_left = rng.randint(40, 70)
        regime_left -= 1
        ret = rng.gauss(drift, vol)
        o = price * (1 + rng.gauss(0, vol * 0.35))
        c = price * math.exp(ret)
        hi = max(o, c) * (1 + abs(rng.gauss(0, vol * 0.5)))
        lo = min(o, c) * (1 - abs(rng.gauss(0, vol * 0.5)))
        v = base_vol * math.exp(rng.gauss(0, 0.45)) * (1 + 3 * abs(ret) / vol * 0.15)
        daily.append({"t": day.isoformat(), "o": o, "h": hi, "l": lo, "c": c, "v": v})
        price = c

    # Evento reciente para que haya setups: ruptura o gap en algunos símbolos
    kind = seed % 4
    last = daily[-1]
    if kind == 0:  # ruptura con volumen
        hi20 = max(b["h"] for b in daily[-21:-1])
        last["c"] = hi20 * 1.015
        last["h"] = last["c"] * 1.004
        last["o"] = hi20 * 0.99
        last["l"] = last["o"] * 0.995
        last["v"] *= 2.4
    elif kind == 1:  # gap alcista
        prev_c = daily[-2]["c"]
        last["o"] = prev_c * 1.03
        last["c"] = last["o"] * 1.012
        last["h"] = last["c"] * 1.003
        last["l"] = last["o"] * 0.997
        last["v"] *= 2.1
    elif kind == 2:  # sobreventa
        for b in daily[-6:]:
            b["c"] *= 0.985
            b["l"] = min(b["l"], b["c"] * 0.995)
            b["o"] = max(b["o"], b["c"])
        last["v"] *= 1.6

    # intradía (5 minutos) para las últimas `sessions` sesiones, coherente con el diario
    intraday: List[Bar] = []
    for b in daily[-sessions:]:
        day = dt.date.fromisoformat(b["t"])
        o, c = b["o"], b["c"]
        n = bars_per_session
        path = [o]
        for k in range(1, n):
            # puente browniano hacia el cierre
            remaining = n - k
            step = (c - path[-1]) / remaining + rng.gauss(0, o * vol / math.sqrt(n) * 0.9)
            path.append(path[-1] + step)
        path[-1] = c
        day_hi = max(path)
        day_lo = min(path)
        b["h"] = max(b["h"], day_hi)
        b["l"] = min(b["l"], day_lo)
        t = dt.datetime.combine(day, dt.time(9, 30))
        for k in range(n):
            po = path[k]
            pc = path[k + 1] if k + 1 < n else c
            noise = abs(rng.gauss(0, o * vol / math.sqrt(n) * 0.5))
            # perfil de volumen en U (apertura/cierre más activos)
            u = 1 + 2.2 * ((k / (n - 1) - 0.5) ** 2) * 4
            intraday.append(
                {
                    "t": (t + dt.timedelta(minutes=5 * k)).strftime("%Y-%m-%d %H:%M"),
                    "o": po,
                    "h": max(po, pc) + noise,
                    "l": min(po, pc) - noise,
                    "c": pc,
                    "v": b["v"] / n * u * math.exp(rng.gauss(0, 0.3)),
                }
            )
    return daily, intraday


# ---------------------------------------------------------------------------
# Análisis
# ---------------------------------------------------------------------------

def classify_trend(close, s20, s50, s200, e21, adx_v, di_p, di_m, adx_trend):
    """Clasificación de tendencia diaria."""
    score = 0
    if s20 and close > s20:
        score += 1
    if s50 and close > s50:
        score += 1
    if s200 and close > s200:
        score += 1
    if s20 and s50 and s20 > s50:
        score += 1
    if s50 and s200 and s50 > s200:
        score += 1
    strong = (adx_v or 0) >= adx_trend
    if score >= 4:
        label = "Alcista fuerte" if strong else "Alcista"
        code = "up_strong" if strong else "up"
    elif score <= 1:
        label = "Bajista fuerte" if strong else "Bajista"
        code = "down_strong" if strong else "down"
    else:
        label, code = "Lateral", "range"
    direction = "up" if code.startswith("up") else ("down" if code.startswith("down") else "flat")
    return {
        "label": label,
        "code": code,
        "direction": direction,
        "alignment_score": score,
        "adx": r2(adx_v, 1),
        "di_plus": r2(di_p, 1),
        "di_minus": r2(di_m, 1),
    }


def intraday_metrics(intra: List[Bar], cfg: dict):
    """VWAP de la última sesión, rango de apertura (ORB) y sesgo intradía."""
    if not intra:
        return None
    last_day = intra[-1]["t"][:10]
    session = [b for b in intra if b["t"][:10] == last_day]
    if len(session) < 3:
        return None
    cum_pv, cum_v = 0.0, 0.0
    vwap_series = []
    for b in session:
        typical = (b["h"] + b["l"] + b["c"]) / 3
        cum_pv += typical * b["v"]
        cum_v += b["v"]
        vwap_series.append(cum_pv / cum_v if cum_v else b["c"])
    closes = [b["c"] for b in session]
    e9 = ema(closes, cfg["ema_fast"])
    e21 = ema(closes, cfg["ema_slow"])
    interval_min = 5
    try:
        t0 = dt.datetime.strptime(session[0]["t"], "%Y-%m-%d %H:%M")
        t1 = dt.datetime.strptime(session[1]["t"], "%Y-%m-%d %H:%M")
        interval_min = max(1, int((t1 - t0).total_seconds() // 60))
    except ValueError:
        pass
    orb_bars = max(1, cfg["opening_range_minutes"] // interval_min)
    orb_hi = max(b["h"] for b in session[:orb_bars])
    orb_lo = min(b["l"] for b in session[:orb_bars])
    last = session[-1]
    vwap_now = vwap_series[-1]
    above_vwap = last["c"] > vwap_now
    bias = "flat"
    if above_vwap and e9[-1] and e21[-1] and e9[-1] > e21[-1]:
        bias = "up"
    elif (not above_vwap) and e9[-1] and e21[-1] and e9[-1] < e21[-1]:
        bias = "down"
    orb_break = "none"
    if last["c"] > orb_hi:
        orb_break = "up"
    elif last["c"] < orb_lo:
        orb_break = "down"
    session_hi = max(b["h"] for b in session)
    session_lo = min(b["l"] for b in session)
    return {
        "date": last_day,
        "bars": len(session),
        "vwap": r2(vwap_now),
        "above_vwap": above_vwap,
        "bias": bias,
        "orb_high": r2(orb_hi),
        "orb_low": r2(orb_lo),
        "orb_break": orb_break,
        "session_high": r2(session_hi),
        "session_low": r2(session_lo),
        "session_range_pct": r2(pct(session_hi, session_lo)),
        "series": [
            {"t": b["t"][11:], "c": r2(b["c"]), "v": round(b["v"]), "vwap": r2(vwap_series[i])}
            for i, b in enumerate(session)
        ],
    }


def position_size(entry: float, stop: float, risk_cfg: dict):
    risk_amt = risk_cfg["account_size"] * risk_cfg["risk_per_trade_pct"] / 100
    per_share = abs(entry - stop)
    if per_share <= 0:
        return 0, 0.0
    shares = int(risk_amt / per_share)
    max_notional = risk_cfg["account_size"] * risk_cfg["max_position_pct"] / 100
    if shares * entry > max_notional:
        shares = int(max_notional / entry)
    return shares, round(risk_amt, 2)


def make_signal(kind, side, title, why, entry, atr_v, strength, risk_cfg):
    mult = risk_cfg["stop_atr_multiple"]
    rr = risk_cfg["reward_risk_ratio"]
    if side == "long":
        stop = entry - mult * atr_v
        target = entry + rr * mult * atr_v
    else:
        stop = entry + mult * atr_v
        target = entry - rr * mult * atr_v
    shares, risk_amt = position_size(entry, stop, risk_cfg)
    return {
        "kind": kind,
        "side": side,
        "title": title,
        "why": why,
        "strength": int(max(0, min(100, strength))),
        "entry": r2(entry),
        "stop": r2(stop),
        "target": r2(target),
        "risk_per_share": r2(abs(entry - stop)),
        "reward_risk": rr,
        "shares": shares,
        "risk_amount": risk_amt,
        "notional": r2(shares * entry),
    }


def analyze(symbol: str, daily: List[Bar], intra: List[Bar], cfg: dict):
    ind, sig_cfg, risk_cfg = cfg["indicators"], cfg["signals"], cfg["risk"]
    if len(daily) < max(ind["sma_slow"] // 2, 60):
        return {"symbol": symbol, "error": f"Datos insuficientes ({len(daily)} barras)"}

    o = [b["o"] for b in daily]
    h = [b["h"] for b in daily]
    l = [b["l"] for b in daily]
    c = [b["c"] for b in daily]
    v = [b["v"] for b in daily]
    n = len(c)
    i = n - 1

    s20, s50, s200 = sma(c, ind["sma_fast"]), sma(c, ind["sma_mid"]), sma(c, ind["sma_slow"])
    e9, e21 = ema(c, ind["ema_fast"]), ema(c, ind["ema_slow"])
    rsi_v = rsi(c, ind["rsi_period"])
    m_line, m_sig, m_hist = macd(c, ind["macd_fast"], ind["macd_slow"], ind["macd_signal"])
    bb_mid, bb_up, bb_lo, bb_w = bollinger(c, ind["bb_period"], ind["bb_std"])
    atr_v = atr(h, l, c, ind["atr_period"])
    adx_v, di_p, di_m = adx(h, l, c, ind["adx_period"])
    vol_avg = sma(v, ind["volume_lookback"])

    last_close, prev_close = c[i], c[i - 1]
    atr_now = atr_v[i] or (h[i] - l[i]) or last_close * 0.01
    atr_pct = atr_now / last_close * 100
    rvol = v[i] / vol_avg[i] if vol_avg[i] else 1.0
    gap_pct = pct(o[i], prev_close)
    change_pct = pct(last_close, prev_close)
    range_pct = pct(h[i], l[i])
    dollar_vol = (vol_avg[i] or 0) * last_close
    hi52 = max(h[-252:])
    lo52 = min(l[-252:])
    lb = sig_cfg["breakout_lookback"]
    hi_lb = max(h[i - lb : i])
    lo_lb = min(l[i - lb : i])
    ret5 = pct(last_close, c[i - 5])
    ret20 = pct(last_close, c[i - 20])
    slope21 = pct(e21[i], e21[i - 5]) if (e21[i] and e21[i - 5]) else 0.0

    trend = classify_trend(
        last_close, s20[i], s50[i], s200[i], e21[i], adx_v[i], di_p[i], di_m[i], ind["adx_trend"]
    )
    trend["ema21_slope_5d_pct"] = r2(slope21)

    intra_m = intraday_metrics(intra, {**ind, **cfg["data"]})

    # --- setups ---------------------------------------------------------
    signals = []
    rvol_min = sig_cfg["rvol_min"]
    rsi_now = rsi_v[i] or 50

    if last_close > hi_lb and rvol >= rvol_min:
        signals.append(
            make_signal(
                "breakout", "long", "Ruptura de máximos con volumen",
                f"Cierre {last_close:.2f} > máximo de {lb} sesiones ({hi_lb:.2f}); RVOL {rvol:.1f}x",
                last_close, atr_now, 55 + min(rvol, 4) * 8 + (10 if trend["direction"] == "up" else 0), risk_cfg,
            )
        )
    if last_close < lo_lb and rvol >= rvol_min:
        signals.append(
            make_signal(
                "breakdown", "short", "Ruptura de mínimos con volumen",
                f"Cierre {last_close:.2f} < mínimo de {lb} sesiones ({lo_lb:.2f}); RVOL {rvol:.1f}x",
                last_close, atr_now, 55 + min(rvol, 4) * 8 + (10 if trend["direction"] == "down" else 0), risk_cfg,
            )
        )
    if gap_pct >= sig_cfg["gap_min_pct"] and rvol >= rvol_min and last_close >= o[i]:
        signals.append(
            make_signal(
                "gap_go", "long", "Gap and Go alcista",
                f"Gap +{gap_pct:.1f}% sostenido sobre la apertura; RVOL {rvol:.1f}x",
                last_close, atr_now, 50 + min(gap_pct, 8) * 4 + min(rvol, 4) * 5, risk_cfg,
            )
        )
    if gap_pct <= -sig_cfg["gap_min_pct"] and rvol >= rvol_min and last_close <= o[i]:
        signals.append(
            make_signal(
                "gap_down", "short", "Gap bajista con continuación",
                f"Gap {gap_pct:.1f}% sin recuperar la apertura; RVOL {rvol:.1f}x",
                last_close, atr_now, 50 + min(-gap_pct, 8) * 4 + min(rvol, 4) * 5, risk_cfg,
            )
        )
    if (
        trend["direction"] == "up"
        and e21[i]
        and abs(last_close - e21[i]) <= sig_cfg["pullback_atr_distance"] * atr_now
        and 38 <= rsi_now <= 58
    ):
        signals.append(
            make_signal(
                "pullback", "long", "Retroceso a EMA21 en tendencia alcista",
                f"Precio a {abs(last_close - e21[i]) / atr_now:.2f} ATR de la EMA21 ({e21[i]:.2f}); RSI {rsi_now:.0f}",
                last_close, atr_now, 50 + (adx_v[i] or 0) * 0.6, risk_cfg,
            )
        )
    if (
        trend["direction"] == "down"
        and e21[i]
        and abs(last_close - e21[i]) <= sig_cfg["pullback_atr_distance"] * atr_now
        and 42 <= rsi_now <= 62
    ):
        signals.append(
            make_signal(
                "pullback_short", "short", "Rebote a EMA21 en tendencia bajista",
                f"Precio a {abs(last_close - e21[i]) / atr_now:.2f} ATR de la EMA21 ({e21[i]:.2f}); RSI {rsi_now:.0f}",
                last_close, atr_now, 50 + (adx_v[i] or 0) * 0.6, risk_cfg,
            )
        )
    if rsi_now <= ind["rsi_oversold"] and bb_lo[i] and last_close <= bb_lo[i] * 1.01:
        signals.append(
            make_signal(
                "mean_rev_long", "long", "Reversión a la media (sobreventa)",
                f"RSI {rsi_now:.0f} y precio en banda inferior de Bollinger ({bb_lo[i]:.2f})",
                last_close, atr_now, 45 + (ind["rsi_oversold"] - rsi_now) * 1.5, risk_cfg,
            )
        )
    if rsi_now >= ind["rsi_overbought"] and bb_up[i] and last_close >= bb_up[i] * 0.99:
        signals.append(
            make_signal(
                "mean_rev_short", "short", "Reversión a la media (sobrecompra)",
                f"RSI {rsi_now:.0f} y precio en banda superior de Bollinger ({bb_up[i]:.2f})",
                last_close, atr_now, 45 + (rsi_now - ind["rsi_overbought"]) * 1.5, risk_cfg,
            )
        )
    sq_lb = sig_cfg["squeeze_lookback"]
    widths = [w for w in bb_w[max(0, i - sq_lb) : i + 1] if w is not None]
    squeeze = bool(widths) and bb_w[i] is not None and bb_w[i] <= min(widths) * 1.05
    if squeeze:
        signals.append(
            make_signal(
                "squeeze", "long" if trend["direction"] != "down" else "short",
                "Compresión de volatilidad (pre-ruptura)",
                f"Ancho de Bollinger {bb_w[i]:.1f}% en mínimo de {sq_lb} sesiones; vigilar ruptura del rango",
                last_close, atr_now, 40 + (10 if trend["direction"] != "flat" else 0), risk_cfg,
            )
        )
    if intra_m and intra_m["orb_break"] != "none" and rvol >= 1.0:
        side = "long" if intra_m["orb_break"] == "up" else "short"
        lvl = intra_m["orb_high"] if side == "long" else intra_m["orb_low"]
        signals.append(
            make_signal(
                "orb", side, f"Ruptura del rango de apertura ({cfg['data']['opening_range_minutes']} min)",
                f"Precio {'sobre' if side == 'long' else 'bajo'} el rango de apertura ({lvl}); "
                f"{'sobre' if intra_m['above_vwap'] else 'bajo'} VWAP {intra_m['vwap']}",
                last_close, atr_now,
                45 + (15 if (side == "long") == intra_m["above_vwap"] else 0) + min(rvol, 3) * 5,
                risk_cfg,
            )
        )
    signals.sort(key=lambda s: -s["strength"])

    # --- score de operabilidad para day trading (0-100) -------------------
    liq = min(1.0, dollar_vol / max(sig_cfg["min_dollar_volume"] * 5, 1))
    lo_a, hi_a = sig_cfg["atr_pct_min"], sig_cfg["atr_pct_max"]
    if atr_pct < lo_a:
        vol_score = atr_pct / lo_a
    elif atr_pct > hi_a:
        vol_score = max(0.0, 1 - (atr_pct - hi_a) / hi_a)
    else:
        vol_score = 1.0
    rvol_score = min(1.0, rvol / 2.0)
    trend_score = min(1.0, (adx_v[i] or 0) / 40) if trend["direction"] != "flat" else 0.3
    tradability = round(25 * (liq + vol_score + rvol_score + trend_score))
    flags = []
    if dollar_vol < sig_cfg["min_dollar_volume"]:
        flags.append("Liquidez baja")
    if atr_pct < lo_a:
        flags.append("Volatilidad insuficiente")
    if atr_pct > hi_a:
        flags.append("Volatilidad excesiva")

    keep = 90  # barras para las gráficas del dashboard
    series = {
        "t": [b["t"] for b in daily[-keep:]],
        "o": [r2(x) for x in o[-keep:]],
        "h": [r2(x) for x in h[-keep:]],
        "l": [r2(x) for x in l[-keep:]],
        "c": [r2(x) for x in c[-keep:]],
        "v": [round(x) for x in v[-keep:]],
        "ema9": [r2(x) for x in e9[-keep:]],
        "ema21": [r2(x) for x in e21[-keep:]],
        "sma50": [r2(x) for x in s50[-keep:]],
        "bb_up": [r2(x) for x in bb_up[-keep:]],
        "bb_lo": [r2(x) for x in bb_lo[-keep:]],
        "rsi": [r2(x, 1) for x in rsi_v[-keep:]],
        "macd_hist": [r2(x, 3) for x in m_hist[-keep:]],
        "vol_avg": [r2(x, 0) for x in vol_avg[-keep:]],
    }

    return {
        "symbol": symbol,
        "last_date": daily[i]["t"],
        "last": r2(last_close),
        "change_pct": r2(change_pct),
        "gap_pct": r2(gap_pct),
        "range_pct": r2(range_pct),
        "ret_5d_pct": r2(ret5),
        "ret_20d_pct": r2(ret20),
        "volume": round(v[i]),
        "rvol": r2(rvol),
        "dollar_volume_avg": round(dollar_vol),
        "atr": r2(atr_now),
        "atr_pct": r2(atr_pct),
        "rsi": r2(rsi_now, 1),
        "macd": r2(m_line[i], 3),
        "macd_signal": r2(m_sig[i], 3),
        "macd_hist": r2(m_hist[i], 3),
        "sma20": r2(s20[i]), "sma50": r2(s50[i]), "sma200": r2(s200[i]),
        "ema9": r2(e9[i]), "ema21": r2(e21[i]),
        "bb_upper": r2(bb_up[i]), "bb_lower": r2(bb_lo[i]), "bb_width_pct": r2(bb_w[i], 1),
        "high_20d": r2(hi_lb), "low_20d": r2(lo_lb),
        "high_52w": r2(hi52), "low_52w": r2(lo52),
        "dist_52w_high_pct": r2(pct(last_close, hi52)),
        "squeeze": squeeze,
        "trend": trend,
        "intraday": intra_m,
        "signals": signals,
        "tradability": tradability,
        "flags": flags,
        "series": series,
    }


# ---------------------------------------------------------------------------
# Dashboard HTML (autocontenido)
# ---------------------------------------------------------------------------

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Monitor Bursátil</title>
<style>
:root{
  --bg:#0A1438; --navy:#1E2761; --surface:#151E45; --surface2:#1E2952;
  --ice:#CADCFC; --white:#FFFFFF; --cyan:#00D9FF; --amber:#FFB800;
  --rose:#FF5C7A; --green:#3DD68C; --mute:#8895B3; --divider:#2A3666;
  --serif:Georgia,'Times New Roman',serif;
  --sans:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;
  --mono:'SF Mono',Menlo,Consolas,monospace;
}
*{box-sizing:border-box}
html,body{margin:0;padding:0}
body{background:var(--bg);
  background-image:radial-gradient(900px 500px at 88% -8%, rgba(0,217,255,.10), transparent 60%),
    radial-gradient(700px 480px at -6% 110%, rgba(30,39,97,.55), transparent 60%);
  color:var(--white);font-family:var(--sans);-webkit-font-smoothing:antialiased;font-size:14px;line-height:1.45;min-height:100vh}
body::before{content:"";position:fixed;inset:0;pointer-events:none;
  background-image:linear-gradient(rgba(0,217,255,.18) 1px,transparent 1px),linear-gradient(90deg,rgba(0,217,255,.18) 1px,transparent 1px);
  background-size:48px 48px;opacity:.12;mask-image:radial-gradient(circle at 50% 20%,black,transparent 80%);-webkit-mask-image:radial-gradient(circle at 50% 20%,black,transparent 80%)}
.wrap{max-width:1280px;margin:0 auto;padding:22px 26px 60px;position:relative}
header{display:flex;align-items:flex-end;justify-content:space-between;gap:20px;flex-wrap:wrap;border-bottom:1px solid var(--divider);padding-bottom:18px}
.kick{display:flex;align-items:center;gap:10px;font-weight:800;letter-spacing:.32em;font-size:12px;color:var(--cyan);text-transform:uppercase}
.kick .dot{width:9px;height:9px;border-radius:50%;background:var(--cyan);box-shadow:0 0 10px var(--cyan)}
h1{font-family:var(--serif);font-weight:700;font-size:30px;line-height:1.05;margin:8px 0 4px}
h1 .light{color:var(--ice);font-style:italic;font-weight:400}
.sub{color:var(--mute);font-size:13px}
.chip{display:inline-flex;align-items:center;gap:8px;padding:6px 12px;border:1px solid var(--divider);border-radius:999px;background:var(--surface);font-size:12px;color:var(--ice)}
.chip .dot{width:8px;height:8px;border-radius:50%;background:var(--green);box-shadow:0 0 9px var(--green)}
.chip.demo .dot{background:var(--amber);box-shadow:0 0 9px var(--amber)}

.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:20px 0}
.kpi{background:var(--surface);border:1px solid var(--divider);border-radius:12px;padding:16px 18px}
.kpi .lbl{font-size:11px;letter-spacing:.18em;text-transform:uppercase;color:var(--mute)}
.kpi .val{font-family:var(--serif);font-size:38px;line-height:1.05;margin-top:6px;color:var(--cyan)}
.kpi .val.amber{color:var(--amber)}
.kpi .foot{font-size:12px;color:var(--mute);margin-top:6px}

.tabs{display:flex;gap:6px;border-bottom:1px solid var(--divider);margin:6px 0 18px;flex-wrap:wrap}
.tabs button{background:transparent;border:0;color:var(--mute);font:inherit;font-size:13px;padding:10px 14px;cursor:pointer;border-bottom:2px solid transparent;letter-spacing:.02em}
.tabs button:hover{color:var(--ice)}
.tabs button.active{color:var(--cyan);border-bottom-color:var(--cyan)}
[data-panel]{display:none}[data-panel].active{display:block}

.card{background:var(--surface);border:1px solid var(--divider);border-radius:12px;padding:16px 18px;margin-bottom:14px}
.card h2{font-family:var(--serif);font-weight:700;font-size:18px;margin:0 0 4px}
.card h3{font-size:12px;letter-spacing:.18em;text-transform:uppercase;color:var(--cyan);margin:0 0 10px;font-weight:700}
.card .hint{color:var(--mute);font-size:12px;margin-bottom:10px}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}
.grid4{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}

table{width:100%;border-collapse:collapse;font-size:13px}
th,td{padding:8px 10px;text-align:right;border-bottom:1px solid var(--divider);white-space:nowrap}
th{color:var(--mute);font-weight:600;font-size:11px;letter-spacing:.12em;text-transform:uppercase;cursor:pointer;user-select:none}
th:hover{color:var(--ice)}
th.sorted{color:var(--cyan)}
th:first-child,td:first-child{text-align:left}
td.sym{font-weight:700;color:var(--white);cursor:pointer}
td.sym:hover{color:var(--cyan)}
tr.row:hover td{background:rgba(0,217,255,.04)}
.num{font-family:var(--mono);font-size:12.5px}
.pos{color:var(--green)}.neg{color:var(--rose)}.flat{color:var(--ice)}
.tscroll{overflow-x:auto}
.why{color:var(--mute);font-size:11.5px;line-height:1.35;margin-top:2px;max-width:420px}

.rag{display:inline-flex;align-items:center;gap:7px;font-size:12px;color:var(--ice)}
.rag i{width:8px;height:8px;border-radius:50%;display:inline-block}
.rag.green i{background:var(--green);box-shadow:0 0 8px var(--green)}
.rag.rose i{background:var(--rose);box-shadow:0 0 8px var(--rose)}
.rag.amber i{background:var(--amber);box-shadow:0 0 8px var(--amber)}
.rag.mute i{background:var(--mute)}
.badge{display:inline-block;padding:2px 8px;border-radius:6px;font-size:11px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;border:1px solid}
.badge.long{color:var(--green);border-color:rgba(61,214,140,.4);background:rgba(61,214,140,.08)}
.badge.short{color:var(--rose);border-color:rgba(255,92,122,.4);background:rgba(255,92,122,.08)}
.bar{height:6px;background:var(--divider);border-radius:3px;overflow:hidden;width:90px;display:inline-block;vertical-align:middle}
.bar i{display:block;height:100%;background:var(--cyan)}
.filters{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px;align-items:center}
.filters .f{padding:5px 11px;border-radius:999px;border:1px solid var(--divider);background:transparent;color:var(--mute);font:inherit;font-size:12px;cursor:pointer}
.filters .f.active{color:var(--cyan);border-color:var(--cyan)}
select{background:var(--surface2);color:var(--white);border:1px solid var(--divider);border-radius:8px;padding:7px 10px;font:inherit;font-size:13px}

.tcards{display:grid;grid-template-columns:repeat(auto-fill,minmax(290px,1fr));gap:14px}
.tcard{background:var(--surface);border:1px solid var(--divider);border-radius:12px;padding:14px 16px;cursor:pointer;transition:border-color .15s}
.tcard:hover{border-color:var(--cyan)}
.tcard .top{display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:4px 10px}
.tcard .sym{font-family:var(--serif);font-size:22px;font-weight:700}
.tcard .px{font-family:var(--mono);font-size:14px}
.tcard .meta{display:flex;gap:12px;flex-wrap:wrap;font-size:11.5px;color:var(--mute);margin-top:8px}
.tcard .meta b{color:var(--ice);font-weight:600}

.chart{position:relative;width:100%}
.chart svg{width:100%;height:auto;display:block}
.tip{position:absolute;pointer-events:none;background:#0E1A45;border:1px solid var(--divider);border-radius:8px;padding:8px 10px;font-size:12px;color:var(--ice);display:none;z-index:5;min-width:150px;box-shadow:0 6px 20px rgba(0,0,0,.35)}
.tip b{color:var(--white)}
.legend{display:flex;gap:14px;flex-wrap:wrap;font-size:11.5px;color:var(--mute);margin:6px 0 2px}
.legend i{display:inline-block;width:14px;height:2px;vertical-align:middle;margin-right:5px}
.detail-head{display:flex;justify-content:space-between;align-items:flex-end;gap:14px;flex-wrap:wrap;margin-bottom:12px}
.detail-head .big{font-family:var(--serif);font-size:34px;font-weight:700;line-height:1}
.detail-head .px{font-family:var(--mono);font-size:18px;margin-left:12px}
.kv{display:grid;grid-template-columns:1fr auto;gap:5px 14px;font-size:12.5px}
.kv span:nth-child(odd){color:var(--mute)}
.kv span:nth-child(even){font-family:var(--mono);color:var(--ice);text-align:right}
.kv span.hl{color:var(--amber)}
.rules td{white-space:normal;text-align:left;vertical-align:top}
.rules th{text-align:left;cursor:default}
.note{border-left:3px solid var(--amber);padding:10px 14px;background:rgba(255,184,0,.06);border-radius:0 8px 8px 0;font-size:12.5px;color:var(--ice);margin-top:14px}
.empty{color:var(--mute);padding:18px;text-align:center}
footer{margin-top:28px;color:var(--mute);font-size:11.5px;border-top:1px solid var(--divider);padding-top:14px}
@media (max-width:980px){.kpis,.grid4{grid-template-columns:repeat(2,1fr)}.grid2,.grid3{grid-template-columns:1fr}}
@media (max-width:560px){.kpis{grid-template-columns:1fr}.wrap{padding:16px}}
</style>
</head>
<body>
<div class="wrap">
<header>
  <div class="brand">
    <div class="kick"><span class="dot"></span>Monitor bursátil · Day trading</div>
    <h1>Movimientos, <span class="light">tendencias</span> y parámetros</h1>
    <div class="sub" id="subtitle"></div>
  </div>
  <div><span class="chip" id="status-chip"><span class="dot"></span><span id="status-text"></span></span></div>
</header>

<div class="kpis" id="kpis"></div>

<div class="tabs" id="tabs">
  <button data-tab="resumen" class="active">Resumen</button>
  <button data-tab="tendencias">Tendencias</button>
  <button data-tab="setups">Setups</button>
  <button data-tab="detalle">Detalle</button>
  <button data-tab="parametros">Parámetros</button>
</div>

<section data-panel="resumen" class="active">
  <div class="card">
    <h3>Ranking de instrumentos</h3>
    <div class="filters" id="trend-filters">
      <button class="f active" data-f="all">Todos</button>
      <button class="f" data-f="up">Alcistas</button>
      <button class="f" data-f="flat">Laterales</button>
      <button class="f" data-f="down">Bajistas</button>
      <span style="color:var(--mute);font-size:12px;margin-left:auto">Clic en encabezado para ordenar · clic en símbolo para ver detalle</span>
    </div>
    <div class="tscroll"><table id="rank"></table></div>
  </div>
  <div class="grid2">
    <div class="card"><h3>Distribución de tendencias</h3><div id="trend-dist"></div></div>
    <div class="card"><h3>Volatilidad (ATR %) vs. volumen relativo</h3><div class="hint">Zona operable: ATR% entre los umbrales configurados y RVOL ≥ mínimo.</div><div id="scatter" class="chart"></div></div>
  </div>
</section>

<section data-panel="tendencias">
  <div class="tcards" id="tcards"></div>
</section>

<section data-panel="setups">
  <div class="card">
    <h3>Setups detectados</h3>
    <div class="hint">Entrada, stop (múltiplo de ATR) y objetivo (ratio beneficio/riesgo) calculados con los parámetros de riesgo configurados. Ordenados por fuerza.</div>
    <div class="filters" id="side-filters">
      <button class="f active" data-f="all">Todos</button>
      <button class="f" data-f="long">Long</button>
      <button class="f" data-f="short">Short</button>
    </div>
    <div class="tscroll"><table id="setups-table"></table></div>
  </div>
</section>

<section data-panel="detalle">
  <div class="card">
    <div class="detail-head">
      <div><span class="big" id="d-sym"></span><span class="px" id="d-px"></span></div>
      <div><label style="color:var(--mute);font-size:12px;margin-right:8px">Instrumento</label><select id="d-select"></select></div>
    </div>
    <div class="grid4" id="d-stats"></div>
  </div>
  <div class="card">
    <h3>Precio diario · 90 sesiones</h3>
    <div class="legend"><span><i style="background:var(--cyan)"></i>Cierre</span><span><i style="background:var(--amber)"></i>EMA 21</span><span><i style="background:var(--mute)"></i>SMA 50</span><span><i style="background:rgba(0,217,255,.25);height:8px"></i>Bandas de Bollinger</span></div>
    <div id="d-price" class="chart"></div>
    <div id="d-vol" class="chart"></div>
  </div>
  <div class="grid2">
    <div class="card">
      <h3>Sesión intradía · VWAP y rango de apertura</h3>
      <div class="legend"><span><i style="background:var(--cyan)"></i>Precio</span><span><i style="background:var(--amber)"></i>VWAP</span><span><i style="background:rgba(202,220,252,.25);height:8px"></i>Rango de apertura</span></div>
      <div id="d-intra" class="chart"></div>
    </div>
    <div class="card">
      <h3>Parámetros de operación</h3>
      <div id="d-params"></div>
    </div>
  </div>
  <div class="grid2">
    <div class="card"><h3>RSI (14)</h3><div id="d-rsi" class="chart"></div></div>
    <div class="card"><h3>Histograma MACD</h3><div id="d-macd" class="chart"></div></div>
  </div>
</section>

<section data-panel="parametros">
  <div class="grid2">
    <div class="card"><h3>Indicadores</h3><div class="kv" id="p-ind"></div></div>
    <div class="card"><h3>Riesgo y señales</h3><div class="kv" id="p-risk"></div></div>
  </div>
  <div class="card">
    <h3>Reglas de los setups</h3>
    <div class="tscroll"><table class="rules" id="rules"></table></div>
    <div class="note"><b>Cómo usar los parámetros.</b> Cada setup es una hipótesis de estrategia: úsala para definir reglas de entrada, stop y objetivo, valida su rendimiento histórico (backtesting) y sólo después llévala a day trading con tamaño de posición limitado por el riesgo por operación. Este monitor no constituye asesoría de inversión.</div>
  </div>
</section>

<footer id="footer"></footer>
</div>

<script id="report-data" type="application/json">__DATA__</script>
<script>
(function(){
'use strict';
const R = JSON.parse(document.getElementById('report-data').textContent);
const T = R.tickers.filter(t => !t.error);
const ERR = R.tickers.filter(t => t.error);
const C = {cyan:'#00D9FF',amber:'#FFB800',rose:'#FF5C7A',green:'#3DD68C',mute:'#8895B3',ice:'#CADCFC',div:'#2A3666',white:'#FFFFFF'};
const fmt = (n,d=2) => (n===null||n===undefined||isNaN(n)) ? '—' : Number(n).toLocaleString('es-MX',{minimumFractionDigits:d,maximumFractionDigits:d});
const fmtBig = n => n>=1e9 ? fmt(n/1e9,1)+' B' : n>=1e6 ? fmt(n/1e6,1)+' M' : n>=1e3 ? fmt(n/1e3,0)+' K' : fmt(n,0);
const sgn = n => n>0?'pos':n<0?'neg':'flat';
const pctTxt = n => (n===null||n===undefined) ? '—' : (n>0?'+':'')+fmt(n,2)+'%';
const esc = s => String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const trendRag = t => t.direction==='up' ? 'green' : t.direction==='down' ? 'rose' : 'amber';
const kindLabel = {breakout:'Ruptura',breakdown:'Ruptura bajista',gap_go:'Gap and Go',gap_down:'Gap bajista',pullback:'Retroceso',pullback_short:'Rebote',mean_rev_long:'Reversión',mean_rev_short:'Reversión',squeeze:'Compresión',orb:'ORB'};

// ---------- header / KPIs ----------
document.getElementById('subtitle').textContent = `${R.generated_at} · ${T.length} instrumentos · fuente: ${R.source}`;
const chip = document.getElementById('status-chip');
document.getElementById('status-text').textContent = R.source==='demo' ? 'Datos sintéticos (demo)' : 'Datos de mercado';
if (R.source==='demo') chip.classList.add('demo');

const nUp = T.filter(t=>t.trend.direction==='up').length;
const nSig = T.reduce((s,t)=>s+t.signals.length,0);
const avgAtr = T.length ? T.reduce((s,t)=>s+t.atr_pct,0)/T.length : 0;
const avgScore = T.length ? T.reduce((s,t)=>s+t.tradability,0)/T.length : 0;
document.getElementById('kpis').innerHTML = `
  <div class="kpi"><div class="lbl">Instrumentos</div><div class="val">${T.length}</div><div class="foot">${nUp} en tendencia alcista · ${T.filter(t=>t.trend.direction==='down').length} bajista</div></div>
  <div class="kpi"><div class="lbl">Setups activos</div><div class="val amber">${nSig}</div><div class="foot">${T.filter(t=>t.signals.length).length} instrumentos con al menos una señal</div></div>
  <div class="kpi"><div class="lbl">ATR % promedio</div><div class="val">${fmt(avgAtr,2)}%</div><div class="foot">rango diario esperado por instrumento</div></div>
  <div class="kpi"><div class="lbl">Operabilidad media</div><div class="val">${fmt(avgScore,0)}</div><div class="foot">liquidez · volatilidad · volumen · tendencia (0–100)</div></div>`;

// ---------- tabs ----------
const tabs = document.querySelectorAll('[data-tab]');
const panels = document.querySelectorAll('[data-panel]');
function showTab(name){
  tabs.forEach(x=>x.classList.toggle('active', x.dataset.tab===name));
  panels.forEach(p=>p.classList.toggle('active', p.dataset.panel===name));
  if (name==='detalle') renderDetail();
  if (name==='resumen') renderScatter();
}
tabs.forEach(t=>t.addEventListener('click',()=>showTab(t.dataset.tab)));

// ---------- ranking ----------
let sortKey='tradability', sortDir=-1, trendFilter='all';
const cols = [
  {k:'symbol',l:'Símbolo',get:t=>t.symbol,render:t=>`<td class="sym" data-sym="${esc(t.symbol)}">${esc(t.symbol)}</td>`},
  {k:'last',l:'Último',get:t=>t.last,render:t=>`<td class="num">${fmt(t.last)}</td>`},
  {k:'change_pct',l:'Cambio',get:t=>t.change_pct,render:t=>`<td class="num ${sgn(t.change_pct)}">${pctTxt(t.change_pct)}</td>`},
  {k:'trend',l:'Tendencia',get:t=>t.trend.alignment_score,render:t=>`<td><span class="rag ${trendRag(t.trend)}"><i></i>${t.trend.label}</span></td>`},
  {k:'adx',l:'ADX',get:t=>t.trend.adx,render:t=>`<td class="num">${fmt(t.trend.adx,1)}</td>`},
  {k:'rsi',l:'RSI',get:t=>t.rsi,render:t=>`<td class="num ${t.rsi>=70?'neg':t.rsi<=30?'pos':''}">${fmt(t.rsi,1)}</td>`},
  {k:'rvol',l:'RVOL',get:t=>t.rvol,render:t=>`<td class="num ${t.rvol>=R.config.signals.rvol_min?'pos':''}">${fmt(t.rvol,2)}x</td>`},
  {k:'atr_pct',l:'ATR %',get:t=>t.atr_pct,render:t=>`<td class="num">${fmt(t.atr_pct,2)}%</td>`},
  {k:'gap_pct',l:'Gap',get:t=>t.gap_pct,render:t=>`<td class="num ${sgn(t.gap_pct)}">${pctTxt(t.gap_pct)}</td>`},
  {k:'dollar_volume_avg',l:'Vol. $ (20d)',get:t=>t.dollar_volume_avg,render:t=>`<td class="num">${fmtBig(t.dollar_volume_avg)}</td>`},
  {k:'tradability',l:'Operabilidad',get:t=>t.tradability,render:t=>`<td class="num"><span class="bar"><i style="width:${t.tradability}%"></i></span> ${t.tradability}</td>`},
  {k:'signals',l:'Setups',get:t=>t.signals.length,render:t=>`<td class="num ${t.signals.length?'pos':''}">${t.signals.length}</td>`},
];
function renderRank(){
  const rows = T.filter(t=>trendFilter==='all'||t.trend.direction===trendFilter)
    .slice().sort((a,b)=>{const col=cols.find(c=>c.k===sortKey);const x=col.get(a),y=col.get(b);return (x>y?1:x<y?-1:0)*sortDir;});
  let h='<thead><tr>'+cols.map(c=>`<th data-k="${c.k}" class="${c.k===sortKey?'sorted':''}">${c.l}${c.k===sortKey?(sortDir>0?' ▲':' ▼'):''}</th>`).join('')+'</tr></thead><tbody>';
  h += rows.map(t=>'<tr class="row">'+cols.map(c=>c.render(t)).join('')+'</tr>').join('');
  h += '</tbody>';
  const tbl=document.getElementById('rank'); tbl.innerHTML=h;
  tbl.querySelectorAll('th').forEach(th=>th.addEventListener('click',()=>{const k=th.dataset.k; if(sortKey===k) sortDir*=-1; else {sortKey=k; sortDir=(k==='symbol')?1:-1;} renderRank();}));
  tbl.querySelectorAll('td.sym').forEach(td=>td.addEventListener('click',()=>openDetail(td.dataset.sym)));
}
document.querySelectorAll('#trend-filters .f').forEach(b=>b.addEventListener('click',()=>{document.querySelectorAll('#trend-filters .f').forEach(x=>x.classList.remove('active'));b.classList.add('active');trendFilter=b.dataset.f;renderRank();}));
renderRank();

// ---------- trend distribution (stacked bar) ----------
(function(){
  const groups=[['up_strong','Alcista fuerte',C.green],['up','Alcista','rgba(61,214,140,.55)'],['range','Lateral',C.amber],['down','Bajista','rgba(255,92,122,.55)'],['down_strong','Bajista fuerte',C.rose]];
  const total=T.length||1; let x=0, rects='', labels='';
  const W=520,H=26;
  groups.forEach(([code,label,color])=>{const n=T.filter(t=>t.trend.code===code).length; if(!n) return; const w=n/total*W; rects+=`<rect x="${x}" y="0" width="${Math.max(w-2,0)}" height="${H}" rx="3" fill="${color}"/>`; x+=w;});
  labels = groups.map(([code,label,color])=>{const n=T.filter(t=>t.trend.code===code).length; return `<span class="rag"><i style="background:${color}"></i>${label} <b style="color:var(--white);margin-left:4px">${n}</b></span>`;}).join('&nbsp;&nbsp;&nbsp;');
  document.getElementById('trend-dist').innerHTML=`<svg viewBox="0 0 ${W} ${H}" width="100%" height="${H}">${rects}</svg><div class="legend" style="margin-top:10px">${labels}</div>
    <div class="hint" style="margin-top:12px">Alineación de precio con SMA 20/50/200 y fuerza por ADX ≥ ${R.config.indicators.adx_trend}.</div>`;
})();

// ---------- scatter ATR% vs RVOL ----------
function renderScatter(){
  const el=document.getElementById('scatter'); const W=520,H=230,p={l:40,r:16,t:12,b:32};
  const xs=T.map(t=>t.atr_pct), ys=T.map(t=>t.rvol);
  const xmax=Math.max(R.config.signals.atr_pct_max*1.1, ...xs)*1.05, ymax=Math.max(2.5,...ys)*1.1;
  const X=v=>p.l+(v/xmax)*(W-p.l-p.r), Y=v=>H-p.b-(v/ymax)*(H-p.t-p.b);
  const s=R.config.signals;
  let g=`<rect x="${X(s.atr_pct_min)}" y="${p.t}" width="${X(Math.min(s.atr_pct_max,xmax))-X(s.atr_pct_min)}" height="${Y(s.rvol_min)-p.t}" fill="rgba(0,217,255,.06)" stroke="rgba(0,217,255,.25)" stroke-dasharray="3 3"/>`;
  for(let i=0;i<=4;i++){const yv=ymax*i/4; g+=`<line x1="${p.l}" x2="${W-p.r}" y1="${Y(yv)}" y2="${Y(yv)}" stroke="${C.div}"/><text x="${p.l-6}" y="${Y(yv)+4}" text-anchor="end" font-size="10" fill="${C.mute}">${yv.toFixed(1)}x</text>`;}
  for(let i=0;i<=4;i++){const xv=xmax*i/4; g+=`<text x="${X(xv)}" y="${H-p.b+16}" text-anchor="middle" font-size="10" fill="${C.mute}">${xv.toFixed(1)}%</text>`;}
  g+=`<text x="${W/2}" y="${H-2}" text-anchor="middle" font-size="10" fill="${C.mute}">ATR % (volatilidad diaria)</text>`;
  T.forEach(t=>{const col=t.trend.direction==='up'?C.green:t.trend.direction==='down'?C.rose:C.amber;
    g+=`<circle class="pt" data-sym="${esc(t.symbol)}" cx="${X(t.atr_pct)}" cy="${Y(t.rvol)}" r="${5+t.signals.length*1.5}" fill="${col}" fill-opacity=".85" stroke="${C.bg||'#0A1438'}" stroke-width="2" style="cursor:pointer"/>`;
    g+=`<text x="${X(t.atr_pct)+8}" y="${Y(t.rvol)-7}" font-size="10" fill="${C.ice}">${esc(t.symbol.replace('.MX',''))}</text>`;});
  el.innerHTML=`<svg viewBox="0 0 ${W} ${H}">${g}</svg><div class="tip"></div>`;
  const tip=el.querySelector('.tip');
  el.querySelectorAll('.pt').forEach(c=>{
    c.addEventListener('mousemove',e=>{const t=T.find(x=>x.symbol===c.dataset.sym); const r=el.getBoundingClientRect(); tip.style.display='block'; tip.style.left=Math.min(e.clientX-r.left+12,r.width-170)+'px'; tip.style.top=(e.clientY-r.top-10)+'px'; tip.innerHTML=`<b>${esc(t.symbol)}</b> · ${t.trend.label}<br>ATR ${fmt(t.atr_pct)}% · RVOL ${fmt(t.rvol)}x<br>Setups: ${t.signals.length} · Operabilidad ${t.tradability}`;});
    c.addEventListener('mouseleave',()=>tip.style.display='none');
    c.addEventListener('click',()=>openDetail(c.dataset.sym));
  });
}
renderScatter();

// ---------- trend cards ----------
function sparkline(t){
  const W=280,H=70,p=4; const c=t.series.c, e=t.series.ema21; const n=c.length;
  const all=c.concat(e.filter(x=>x!==null)); const mn=Math.min(...all), mx=Math.max(...all);
  const X=i=>p+i/(n-1)*(W-2*p), Y=v=>H-p-((v-mn)/((mx-mn)||1))*(H-2*p);
  const path=arr=>{let d='',started=false; arr.forEach((v,i)=>{if(v===null)return; d+=(started?'L':'M')+X(i).toFixed(1)+','+Y(v).toFixed(1); started=true;}); return d;};
  const col=t.trend.direction==='up'?C.green:t.trend.direction==='down'?C.rose:C.amber;
  return `<svg viewBox="0 0 ${W} ${H}" width="100%" height="${H}"><path d="${path(e)}" fill="none" stroke="${C.amber}" stroke-width="1.2" stroke-opacity=".8"/><path d="${path(c)}" fill="none" stroke="${C.cyan}" stroke-width="2"/><circle cx="${X(n-1)}" cy="${Y(c[n-1])}" r="3.5" fill="${col}"/></svg>`;
}
document.getElementById('tcards').innerHTML = T.slice().sort((a,b)=>b.tradability-a.tradability).map(t=>{
  const ib=t.intraday ? (t.intraday.bias==='up'?'<span class="rag green"><i></i>Sesgo intradía alcista</span>':t.intraday.bias==='down'?'<span class="rag rose"><i></i>Sesgo intradía bajista</span>':'<span class="rag mute"><i></i>Intradía neutral</span>') : '<span class="rag mute"><i></i>Sin intradía</span>';
  return `<div class="tcard" data-sym="${esc(t.symbol)}">
    <div class="top"><span class="sym">${esc(t.symbol)}</span><span class="px ${sgn(t.change_pct)}">${fmt(t.last)} <small>${pctTxt(t.change_pct)}</small></span></div>
    <div style="display:flex;justify-content:space-between;margin:6px 0 4px"><span class="rag ${trendRag(t.trend)}"><i></i>${t.trend.label}</span>${ib}</div>
    ${sparkline(t)}
    <div class="meta"><span>ADX <b>${fmt(t.trend.adx,0)}</b></span><span>RSI <b>${fmt(t.rsi,0)}</b></span><span>ATR <b>${fmt(t.atr_pct,1)}%</b></span><span>RVOL <b>${fmt(t.rvol,1)}x</b></span><span>20d <b class="${sgn(t.ret_20d_pct)}">${pctTxt(t.ret_20d_pct)}</b></span><span>Setups <b>${t.signals.length}</b></span></div>
  </div>`;}).join('') + ERR.map(t=>`<div class="tcard"><div class="sym">${esc(t.symbol)}</div><div class="hint">${esc(t.error)}</div></div>`).join('');
document.querySelectorAll('.tcard[data-sym]').forEach(c=>c.addEventListener('click',()=>openDetail(c.dataset.sym)));

// ---------- setups table ----------
let sideFilter='all';
function renderSetups(){
  const rows=[]; T.forEach(t=>t.signals.forEach(s=>rows.push({t,s})));
  rows.sort((a,b)=>b.s.strength-a.s.strength);
  const f=rows.filter(r=>sideFilter==='all'||r.s.side===sideFilter);
  const tbl=document.getElementById('setups-table');
  if(!f.length){tbl.innerHTML='<tbody><tr><td class="empty">Sin setups con los filtros actuales.</td></tr></tbody>';return;}
  tbl.innerHTML=`<thead><tr><th style="cursor:default">Símbolo</th><th style="cursor:default;text-align:left;min-width:320px">Setup</th><th style="cursor:default">Lado</th><th style="cursor:default">Fuerza</th><th style="cursor:default">Entrada</th><th style="cursor:default">Stop</th><th style="cursor:default">Objetivo</th><th style="cursor:default">Riesgo/acc.</th><th style="cursor:default">Acciones</th><th style="cursor:default">Nocional</th></tr></thead><tbody>`+
    f.map(({t,s})=>`<tr class="row"><td class="sym" data-sym="${esc(t.symbol)}">${esc(t.symbol)}</td><td style="text-align:left;white-space:normal"><b>${esc(s.title)}</b><div class="why">${esc(s.why)}</div></td><td><span class="badge ${s.side}">${s.side}</span></td><td class="num"><span class="bar"><i style="width:${s.strength}%;background:${s.strength>=70?C.green:s.strength>=50?C.cyan:C.mute}"></i></span> ${s.strength}</td><td class="num">${fmt(s.entry)}</td><td class="num neg">${fmt(s.stop)}</td><td class="num pos">${fmt(s.target)}</td><td class="num">${fmt(s.risk_per_share)}</td><td class="num">${s.shares}</td><td class="num">${fmtBig(s.notional)}</td></tr>`).join('')+'</tbody>';
  tbl.querySelectorAll('td.sym').forEach(td=>td.addEventListener('click',()=>openDetail(td.dataset.sym)));
}
document.querySelectorAll('#side-filters .f').forEach(b=>b.addEventListener('click',()=>{document.querySelectorAll('#side-filters .f').forEach(x=>x.classList.remove('active'));b.classList.add('active');sideFilter=b.dataset.f;renderSetups();}));
renderSetups();

// ---------- detail ----------
const sel=document.getElementById('d-select');
sel.innerHTML=T.map(t=>`<option value="${esc(t.symbol)}">${esc(t.symbol)}</option>`).join('');
let current=T.length?T.slice().sort((a,b)=>b.tradability-a.tradability)[0].symbol:null;
sel.addEventListener('change',()=>{current=sel.value;renderDetail();});
function openDetail(sym){current=sym; sel.value=sym; showTab('detalle'); window.scrollTo({top:0,behavior:'smooth'});}

function lineChart(el, opts){
  // opts: {t:[], series:[{v:[],color,width,dash}], band:{up:[],lo:[]}, W,H, yfmt, hover:(i)=>html, hlines:[{y,color,label}], area}
  const W=opts.W||760,H=opts.H||260,p={l:52,r:14,t:10,b:opts.xlabels===false?8:26};
  const n=opts.t.length; const vals=[];
  opts.series.forEach(s=>s.v.forEach(v=>{if(v!==null&&v!==undefined)vals.push(v);}));
  if(opts.band){opts.band.up.concat(opts.band.lo).forEach(v=>{if(v!==null)vals.push(v);});}
  if(opts.hlines) opts.hlines.forEach(h=>vals.push(h.y));
  if(opts.bars) opts.bars.v.forEach(v=>{if(v!==null&&v!==undefined)vals.push(v);});
  if(opts.bars&&opts.ymin===undefined) vals.push(0);
  let mn=opts.ymin!==undefined?opts.ymin:Math.min(...vals), mx=opts.ymax!==undefined?opts.ymax:Math.max(...vals);
  if(mn===mx){mn-=1;mx+=1;} const pad=(mx-mn)*0.06; if(opts.ymin===undefined)mn-=pad; if(opts.ymax===undefined)mx+=pad;
  const X=i=>p.l+i/((n-1)||1)*(W-p.l-p.r), Y=v=>H-p.b-((v-mn)/(mx-mn))*(H-p.t-p.b);
  const path=arr=>{let d='',started=false; arr.forEach((v,i)=>{if(v===null||v===undefined){started=false;return;} d+=(started?'L':'M')+X(i).toFixed(1)+','+Y(v).toFixed(1); started=true;}); return d;};
  let g='';
  for(let i=0;i<=4;i++){const yv=mn+(mx-mn)*i/4; g+=`<line x1="${p.l}" x2="${W-p.r}" y1="${Y(yv).toFixed(1)}" y2="${Y(yv).toFixed(1)}" stroke="${C.div}" stroke-width="1"/><text x="${p.l-8}" y="${(Y(yv)+4).toFixed(1)}" text-anchor="end" font-size="10.5" fill="${C.mute}">${(opts.yfmt||(v=>fmt(v)))(yv)}</text>`;}
  if(opts.xlabels!==false){const step=Math.max(1,Math.round(n/6)); for(let i=0;i<n;i+=step){g+=`<text x="${X(i).toFixed(1)}" y="${H-8}" text-anchor="middle" font-size="10.5" fill="${C.mute}">${esc(opts.xfmt?opts.xfmt(opts.t[i]):opts.t[i])}</text>`;}}
  if(opts.band){let up='',lo=''; const idx=[]; opts.band.up.forEach((v,i)=>{if(v!==null&&opts.band.lo[i]!==null)idx.push(i);}); if(idx.length){up=idx.map((i,k)=>(k?'L':'M')+X(i).toFixed(1)+','+Y(opts.band.up[i]).toFixed(1)).join(''); lo=idx.slice().reverse().map(i=>'L'+X(i).toFixed(1)+','+Y(opts.band.lo[i]).toFixed(1)).join(''); g+=`<path d="${up}${lo}Z" fill="rgba(0,217,255,.07)" stroke="rgba(0,217,255,.28)" stroke-width="1"/>`;}}
  if(opts.hlines) opts.hlines.forEach(h=>{g+=`<line x1="${p.l}" x2="${W-p.r}" y1="${Y(h.y).toFixed(1)}" y2="${Y(h.y).toFixed(1)}" stroke="${h.color}" stroke-dasharray="4 4" stroke-width="1"/>`; if(h.label) g+=`<text x="${W-p.r-4}" y="${(Y(h.y)-4).toFixed(1)}" text-anchor="end" font-size="10" fill="${h.color}">${esc(h.label)}</text>`;});
  if(opts.rect){const r=opts.rect; g+=`<rect x="${X(r.i0).toFixed(1)}" y="${Y(r.hi).toFixed(1)}" width="${(X(r.i1)-X(r.i0)).toFixed(1)}" height="${(Y(r.lo)-Y(r.hi)).toFixed(1)}" fill="rgba(202,220,252,.10)" stroke="rgba(202,220,252,.35)" stroke-width="1"/>`;}
  if(opts.bars){const bw=Math.max(1,(W-p.l-p.r)/n*0.7); opts.bars.v.forEach((v,i)=>{if(v===null)return; const col=opts.bars.color?opts.bars.color(v,i):C.cyan; const y0=Y(Math.max(0,Math.min(v,0))); const y1=Y(Math.max(v,0)); const zero=Y(0); const top=Math.min(y1,zero), hgt=Math.abs(Y(v)-zero); g+=`<rect x="${(X(i)-bw/2).toFixed(1)}" y="${top.toFixed(1)}" width="${bw.toFixed(1)}" height="${Math.max(hgt,0.5).toFixed(1)}" rx="1" fill="${col}"/>`;});}
  opts.series.forEach(s=>{g+=`<path d="${path(s.v)}" fill="none" stroke="${s.color}" stroke-width="${s.width||2}" ${s.dash?`stroke-dasharray="${s.dash}"`:''} stroke-linejoin="round"/>`;});
  g+=`<line class="xh" x1="0" x2="0" y1="${p.t}" y2="${H-p.b}" stroke="${C.ice}" stroke-opacity=".5" style="display:none"/>`;
  el.innerHTML=`<svg viewBox="0 0 ${W} ${H}">${g}</svg><div class="tip"></div>`;
  const svg=el.querySelector('svg'), tip=el.querySelector('.tip'), xh=el.querySelector('.xh');
  el.onmousemove=e=>{const r=svg.getBoundingClientRect(); const sx=(e.clientX-r.left)/r.width*W; let i=Math.round((sx-p.l)/((W-p.l-p.r)/((n-1)||1))); i=Math.max(0,Math.min(n-1,i)); xh.setAttribute('x1',X(i)); xh.setAttribute('x2',X(i)); xh.style.display='block'; tip.style.display='block'; const lx=e.clientX-r.left; tip.style.left=(lx>r.width*0.65?lx-175:lx+14)+'px'; tip.style.top=Math.max(0,e.clientY-r.top-20)+'px'; tip.innerHTML=opts.hover(i);};
  el.onmouseleave=()=>{tip.style.display='none'; xh.style.display='none';};
}

function renderDetail(){
  if(!current) return; const t=T.find(x=>x.symbol===current); if(!t) return;
  document.getElementById('d-sym').textContent=t.symbol;
  const px=document.getElementById('d-px'); px.className='px '+sgn(t.change_pct); px.textContent=`${fmt(t.last)}  ${pctTxt(t.change_pct)}`;
  const s=t.series;
  document.getElementById('d-stats').innerHTML=[
    ['Tendencia',`<span class="rag ${trendRag(t.trend)}"><i></i>${t.trend.label}</span>`,`ADX ${fmt(t.trend.adx,1)} · DI+ ${fmt(t.trend.di_plus,0)} / DI− ${fmt(t.trend.di_minus,0)}`],
    ['Momento',`RSI ${fmt(t.rsi,1)}`,`MACD hist ${fmt(t.macd_hist,3)} · 5d ${pctTxt(t.ret_5d_pct)} · 20d ${pctTxt(t.ret_20d_pct)}`],
    ['Volatilidad',`ATR ${fmt(t.atr)} (${fmt(t.atr_pct,2)}%)`,`Bollinger ${fmt(t.bb_width_pct,1)}% ${t.squeeze?'· <span class="pos">compresión</span>':''} · rango hoy ${fmt(t.range_pct,2)}%`],
    ['Volumen',`RVOL ${fmt(t.rvol,2)}x`,`${fmtBig(t.volume)} hoy · ${fmtBig(t.dollar_volume_avg)} $/día (20d) · gap ${pctTxt(t.gap_pct)}`],
  ].map(([l,v,f])=>`<div class="kpi" style="padding:12px 14px"><div class="lbl">${l}</div><div style="font-family:var(--serif);font-size:20px;margin-top:4px">${v}</div><div class="foot">${f}</div></div>`).join('');

  const hov=i=>`<b>${esc(s.t[i])}</b><br>O ${fmt(s.o[i])} · H ${fmt(s.h[i])}<br>L ${fmt(s.l[i])} · C <b>${fmt(s.c[i])}</b><br>EMA21 ${fmt(s.ema21[i])} · SMA50 ${fmt(s.sma50[i])}<br>Vol ${fmtBig(s.v[i])} · RSI ${fmt(s.rsi[i],1)}`;
  lineChart(document.getElementById('d-price'),{t:s.t,W:1100,H:340,xfmt:d=>d.slice(5),band:{up:s.bb_up,lo:s.bb_lo},
    series:[{v:s.sma50,color:C.mute,width:1.3},{v:s.ema21,color:C.amber,width:1.6},{v:s.c,color:C.cyan,width:2}],
    hlines:[{y:t.high_20d,color:'rgba(61,214,140,.7)',label:'Máx 20d'},{y:t.low_20d,color:'rgba(255,92,122,.7)',label:'Mín 20d'}],hover:hov});
  lineChart(document.getElementById('d-vol'),{t:s.t,W:1100,H:110,xlabels:false,ymin:0,series:[{v:s.vol_avg,color:C.amber,width:1.2,dash:'3 3'}],
    bars:{v:s.v,color:(v,i)=>(s.vol_avg[i]&&v>=s.vol_avg[i]*R.config.signals.rvol_min)?C.cyan:'rgba(0,217,255,.35)'},yfmt:v=>fmtBig(v),hover:i=>`<b>${esc(s.t[i])}</b><br>Volumen ${fmtBig(s.v[i])}<br>Promedio 20d ${fmtBig(s.vol_avg[i])}`});

  const intraEl=document.getElementById('d-intra');
  if(t.intraday&&t.intraday.series.length>2){const it=t.intraday; const tt=it.series.map(b=>b.t); const cc=it.series.map(b=>b.c); const vv=it.series.map(b=>b.vwap);
    const orbBars=Math.max(1,Math.round(R.config.data.opening_range_minutes/Math.max(1,(parseInt(tt[1].slice(3))-parseInt(tt[0].slice(3))+60)%60||5)));
    lineChart(intraEl,{t:tt,W:520,H:230,rect:{i0:0,i1:Math.min(orbBars,tt.length-1),hi:it.orb_high,lo:it.orb_low},series:[{v:vv,color:C.amber,width:1.6},{v:cc,color:C.cyan,width:2}],hover:i=>`<b>${esc(it.date)} ${esc(tt[i])}</b><br>Precio <b>${fmt(cc[i])}</b><br>VWAP ${fmt(vv[i])}<br>Vol ${fmtBig(it.series[i].v)}`});
  } else intraEl.innerHTML='<div class="empty">Sin datos intradía para este instrumento (fuente sólo diaria).</div>';

  lineChart(document.getElementById('d-rsi'),{t:s.t,W:520,H:150,ymin:0,ymax:100,xfmt:d=>d.slice(5),series:[{v:s.rsi,color:C.cyan,width:1.8}],hlines:[{y:R.config.indicators.rsi_overbought,color:'rgba(255,92,122,.6)',label:'Sobrecompra'},{y:R.config.indicators.rsi_oversold,color:'rgba(61,214,140,.6)',label:'Sobreventa'}],yfmt:v=>fmt(v,0),hover:i=>`<b>${esc(s.t[i])}</b><br>RSI ${fmt(s.rsi[i],1)}`});
  lineChart(document.getElementById('d-macd'),{t:s.t,W:520,H:150,xfmt:d=>d.slice(5),series:[],bars:{v:s.macd_hist,color:v=>v>=0?C.green:C.rose},yfmt:v=>fmt(v,2),hover:i=>`<b>${esc(s.t[i])}</b><br>Histograma ${fmt(s.macd_hist[i],3)}`});

  const risk=R.config.risk; const it=t.intraday;
  let ph=`<div class="kv">
    <span>Cuenta / riesgo por operación</span><span>${fmtBig(risk.account_size)} · ${risk.risk_per_trade_pct}% (${fmt(risk.account_size*risk.risk_per_trade_pct/100,0)})</span>
    <span>Stop sugerido</span><span>${risk.stop_atr_multiple} × ATR = ${fmt(risk.stop_atr_multiple*t.atr)}</span>
    <span>Objetivo</span><span>${risk.reward_risk_ratio} R = ${fmt(risk.reward_risk_ratio*risk.stop_atr_multiple*t.atr)}</span>
    <span>Niveles clave</span><span>máx 20d ${fmt(t.high_20d)} · mín 20d ${fmt(t.low_20d)}</span>
    <span>Medias</span><span>EMA9 ${fmt(t.ema9)} · EMA21 ${fmt(t.ema21)} · SMA50 ${fmt(t.sma50)} · SMA200 ${fmt(t.sma200)}</span>
    <span>Bollinger</span><span>${fmt(t.bb_lower)} – ${fmt(t.bb_upper)}</span>
    <span>52 semanas</span><span>${fmt(t.low_52w)} – ${fmt(t.high_52w)} (${pctTxt(t.dist_52w_high_pct)} vs máx)</span>`;
  if(it) ph+=`<span>VWAP sesión</span><span class="${it.above_vwap?'pos':'neg'}">${fmt(it.vwap)} · precio ${it.above_vwap?'por encima':'por debajo'}</span>
    <span>Rango de apertura</span><span>${fmt(it.orb_low)} – ${fmt(it.orb_high)} · ${it.orb_break==='up'?'<span class="pos">ruptura alcista</span>':it.orb_break==='down'?'<span class="neg">ruptura bajista</span>':'sin ruptura'}</span>
    <span>Rango de la sesión</span><span>${fmt(it.session_low)} – ${fmt(it.session_high)} (${fmt(it.session_range_pct)}%)</span>`;
  ph+=`</div>`;
  if(t.flags.length) ph+=`<div class="note" style="border-color:var(--rose);background:rgba(255,92,122,.06)">${t.flags.map(esc).join(' · ')}</div>`;
  if(t.signals.length){ph+=`<h3 style="margin-top:16px">Setups del instrumento</h3>`+t.signals.map(sg=>`<div style="border:1px solid var(--divider);border-radius:10px;padding:10px 12px;margin-bottom:8px"><div style="display:flex;justify-content:space-between;align-items:center;gap:8px"><b>${esc(sg.title)}</b><span class="badge ${sg.side}">${sg.side}</span></div><div class="hint" style="margin:4px 0 6px">${esc(sg.why)}</div><div class="kv"><span>Entrada / Stop / Objetivo</span><span>${fmt(sg.entry)} / <span class="neg">${fmt(sg.stop)}</span> / <span class="pos">${fmt(sg.target)}</span></span><span>Tamaño</span><span>${sg.shares} acc. · ${fmtBig(sg.notional)} · riesgo ${fmt(sg.risk_amount,0)}</span><span>Fuerza</span><span>${sg.strength}/100</span></div></div>`).join('');}
  else ph+=`<div class="hint" style="margin-top:14px">Sin setups activos. Los niveles anteriores sirven para definir órdenes condicionales.</div>`;
  document.getElementById('d-params').innerHTML=ph;
}

// ---------- parámetros ----------
(function(){
  const I=R.config.indicators, S=R.config.signals, K=R.config.risk, D=R.config.data;
  const kv=(o,labels)=>Object.entries(labels).map(([k,l])=>`<span>${l}</span><span>${esc(o[k])}</span>`).join('');
  document.getElementById('p-ind').innerHTML=kv(I,{sma_fast:'SMA rápida',sma_mid:'SMA media',sma_slow:'SMA lenta',ema_fast:'EMA rápida',ema_slow:'EMA lenta',rsi_period:'RSI periodo',rsi_oversold:'RSI sobreventa',rsi_overbought:'RSI sobrecompra',macd_fast:'MACD rápida',macd_slow:'MACD lenta',macd_signal:'MACD señal',bb_period:'Bollinger periodo',bb_std:'Bollinger desv.',atr_period:'ATR periodo',adx_period:'ADX periodo',adx_trend:'ADX umbral tendencia',volume_lookback:'Volumen promedio (sesiones)'})
    +kv(D,{daily_period:'Historial diario',intraday_interval:'Intervalo intradía',intraday_period:'Historial intradía',opening_range_minutes:'Rango de apertura (min)'});
  document.getElementById('p-risk').innerHTML=kv(K,{account_size:'Tamaño de cuenta',risk_per_trade_pct:'Riesgo por operación (%)',stop_atr_multiple:'Stop (× ATR)',reward_risk_ratio:'Objetivo (R)',max_position_pct:'Posición máxima (% cuenta)'})
    +kv(S,{breakout_lookback:'Ruptura: sesiones de referencia',rvol_min:'RVOL mínimo',gap_min_pct:'Gap mínimo (%)',squeeze_lookback:'Compresión: sesiones',pullback_atr_distance:'Retroceso: distancia a EMA21 (ATR)',atr_pct_min:'ATR % mínimo operable',atr_pct_max:'ATR % máximo operable',min_dollar_volume:'Volumen $ mínimo/día'});
  const rules=[
    ['Ruptura de máximos / mínimos','Momentum','Cierre por encima del máximo (o debajo del mínimo) de N sesiones con RVOL ≥ mínimo.','Entrar en la ruptura o en el primer retest; stop 1.5×ATR; salir si el volumen no confirma.'],
    ['Gap and Go / Gap bajista','Momentum intradía','Gap ≥ umbral que mantiene la apertura (no se cierra) con volumen relativo alto.','Operar la continuación tras el rango de apertura; stop bajo el mínimo del rango o VWAP.'],
    ['Retroceso a EMA21 / Rebote a EMA21','Continuación de tendencia','En tendencia definida, precio a ≤ 1 ATR de la EMA21 con RSI neutro (sin sobrecompra/venta).','Entrar a favor de la tendencia cuando el precio recupera la EMA9; stop 1.5×ATR.'],
    ['Reversión a la media','Contra-tendencia','RSI extremo y precio tocando la banda de Bollinger.','Objetivo la media móvil de Bollinger; tamaño reducido: es la señal con menor fuerza base.'],
    ['Compresión de volatilidad','Preparación','Ancho de Bollinger en mínimo de N sesiones (rango estrecho, antes de un movimiento).','No es entrada: colocar alertas en los extremos del rango y operar la ruptura con volumen.'],
    ['ORB (rango de apertura)','Intradía','Precio rompe el máximo/mínimo de los primeros minutos de la sesión; más fuerte si coincide con el lado del VWAP.','Entrada en la ruptura; stop en el lado opuesto del rango; objetivo 2R o cierre por tiempo.'],
  ];
  document.getElementById('rules').innerHTML='<thead><tr><th>Setup</th><th>Tipo</th><th>Condición</th><th>Uso como estrategia</th></tr></thead><tbody>'+rules.map(r=>'<tr>'+r.map(c=>`<td>${c}</td>`).join('')+'</tr>').join('')+'</tbody>';
})();

document.getElementById('footer').innerHTML=`Generado ${esc(R.generated_at)} con <code>monitor/stock_monitor.py</code> · fuente <b>${esc(R.source)}</b>${ERR.length?` · ${ERR.length} instrumento(s) sin datos: ${ERR.map(e=>esc(e.symbol)).join(', ')}`:''}. Herramienta de análisis; no constituye asesoría de inversión.`;
})();
</script>
</body>
</html>
"""


def build_html(report: dict) -> str:
    data = json.dumps(report, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return HTML_TEMPLATE.replace("__DATA__", data)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Monitor de movimientos bursátiles para day trading")
    ap.add_argument("--config", default=DEFAULT_CONFIG, help="ruta a config.json")
    ap.add_argument("--tickers", help="lista separada por comas; sobrescribe la watchlist")
    ap.add_argument("--source", choices=["auto", "yfinance", "stooq", "demo"], default="auto")
    ap.add_argument("--demo", action="store_true", help="atajo para --source demo")
    ap.add_argument("--out-dir", default=DEFAULT_OUT)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    tickers = [t.strip().upper() for t in args.tickers.split(",")] if args.tickers else cfg["watchlist"]
    source = "demo" if args.demo else args.source
    if source == "auto":
        try:
            import yfinance  # noqa: F401
            source = "yfinance"
        except ImportError:
            print("yfinance no está instalado; usando stooq (sólo diario). "
                  "Instala con: pip install yfinance", file=sys.stderr)
            source = "stooq"

    log = (lambda *a: None) if args.quiet else (lambda *a: print(*a, file=sys.stderr))
    results = []
    for sym in tickers:
        try:
            if source == "demo":
                daily, intra = demo_series(sym)
            elif source == "yfinance":
                daily, intra = fetch_yfinance(sym, cfg["data"])
            else:
                daily, intra = fetch_stooq(sym)
            res = analyze(sym, daily, intra, cfg)
        except Exception as exc:  # noqa: BLE001 — un símbolo no debe tumbar el reporte
            res = {"symbol": sym, "error": f"{type(exc).__name__}: {exc}"}
        if "error" in res:
            log(f"  {sym:<12} ERROR {res['error']}")
        else:
            log(f"  {sym:<12} {res['last']:>10.2f} {res['change_pct']:>+7.2f}%  {res['trend']['label']:<15} "
                f"ADX {res['trend']['adx'] or 0:>5.1f}  RVOL {res['rvol']:.1f}x  setups {len(res['signals'])}")
        results.append(res)

    report = {
        "generated_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "source": source,
        "config": {k: cfg[k] for k in ("data", "indicators", "signals", "risk")},
        "tickers": results,
    }
    os.makedirs(args.out_dir, exist_ok=True)
    json_path = os.path.join(args.out_dir, "monitor.json")
    html_path = os.path.join(args.out_dir, "monitor.html")
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)
    with open(html_path, "w", encoding="utf-8") as fh:
        fh.write(build_html(report))
    ok = [r for r in results if "error" not in r]
    n_sig = sum(len(r["signals"]) for r in ok)
    log(f"\n{len(ok)}/{len(results)} instrumentos analizados · {n_sig} setups · fuente {source}")
    log(f"JSON: {json_path}\nHTML: {html_path}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
