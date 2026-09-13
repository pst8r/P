#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dashboard de resultados NFL con probabilidad de cubrir el spread
================================================================

Genera un tablero autocontenido que se alimenta **en vivo** del marcador
oficial de la NFL (API pública de ESPN) cada vez que se refresca la página o
cada N segundos, y estima para cada partido:

  * marcador, cuarto y reloj (con posesión y down & distance cuando aplica),
  * probabilidad de que cada equipo **cubra el spread** (ATS),
  * probabilidad de empate contra la línea (*push*) en líneas enteras,
  * probabilidad de ganar el partido (moneyline) y de **over/under** del total,
  * ventaja del modelo contra la probabilidad implícita del mercado.

Artefactos en output/:
  * nfl.json  — instantánea estructurada (partidos, líneas, probabilidades)
  * nfl.html  — dashboard autocontenido (sin CDN); refresca en vivo por sí solo

Uso rápido
----------
  python3 nfl_dashboard.py --demo                 # datos sintéticos, sin red
  python3 nfl_dashboard.py                        # semana en curso (ESPN)
  python3 nfl_dashboard.py --season 2025 --week 3 # semana concreta
  python3 nfl_dashboard.py --seasontype 3         # postemporada

Sólo usa la librería estándar de Python 3.9+. El HTML no depende de este
script para actualizarse: lleva el mismo modelo en JavaScript y consulta la
API directamente desde el navegador.

Aviso: herramienta de análisis estadístico y estudio de líneas.
**No constituye asesoría de apuestas ni de inversión.**
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import random
import sys
import urllib.error
import urllib.request
from typing import Dict, List, Optional, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONFIG = os.path.join(HERE, "config.json")
DEFAULT_OUT = os.path.join(HERE, "output")

ESPN_SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"

SEASON_TYPES = {1: "Pretemporada", 2: "Temporada regular", 3: "Postemporada", 4: "Pro Bowl"}

# Identidad oficial por equipo: color primario, secundario y clave del logo.
# Fuente: guías de marca de los clubes. Uso privado del tablero.
TEAM_META = {
    "ARI": {"primary": "#97233F", "secondary": "#FFB612"},
    "ATL": {"primary": "#A71930", "secondary": "#A5ACAF"},
    "BAL": {"primary": "#241773", "secondary": "#9E7C0C"},
    "BUF": {"primary": "#00338D", "secondary": "#C60C30"},
    "CAR": {"primary": "#0085CA", "secondary": "#BFC0BF"},
    "CHI": {"primary": "#0B162A", "secondary": "#C83803"},
    "CIN": {"primary": "#FB4F14", "secondary": "#000000"},
    "CLE": {"primary": "#311D00", "secondary": "#FF3C00"},
    "DAL": {"primary": "#003594", "secondary": "#869397"},
    "DEN": {"primary": "#FB4F14", "secondary": "#002244"},
    "DET": {"primary": "#0076B6", "secondary": "#B0B7BC"},
    "GB":  {"primary": "#203731", "secondary": "#FFB612"},
    "HOU": {"primary": "#03202F", "secondary": "#A71930"},
    "IND": {"primary": "#002C5F", "secondary": "#A2AAAD"},
    "JAX": {"primary": "#006778", "secondary": "#D7A22A"},
    "KC":  {"primary": "#E31837", "secondary": "#FFB81C"},
    "LAC": {"primary": "#0080C6", "secondary": "#FFC20E"},
    "LAR": {"primary": "#003594", "secondary": "#FFA300"},
    "LV":  {"primary": "#000000", "secondary": "#A5ACAF"},
    "MIA": {"primary": "#008E97", "secondary": "#FC4C02"},
    "MIN": {"primary": "#4F2683", "secondary": "#FFC62F"},
    "NE":  {"primary": "#002244", "secondary": "#C60C30"},
    "NO":  {"primary": "#D3BC8D", "secondary": "#101820"},
    "NYG": {"primary": "#0B2265", "secondary": "#A71930"},
    "NYJ": {"primary": "#125740", "secondary": "#FFFFFF"},
    "PHI": {"primary": "#004C54", "secondary": "#A5ACAF"},
    "PIT": {"primary": "#FFB612", "secondary": "#101820"},
    "SEA": {"primary": "#002244", "secondary": "#69BE28"},
    "SF":  {"primary": "#AA0000", "secondary": "#B3995D"},
    "TB":  {"primary": "#D50A0A", "secondary": "#FF7900"},
    "TEN": {"primary": "#0C2340", "secondary": "#4B92DB"},
    "WSH": {"primary": "#5A1414", "secondary": "#FFB612"},
}
TEAMS = {
    "ARI": ("Arizona", "Cardinals"), "ATL": ("Atlanta", "Falcons"),
    "BAL": ("Baltimore", "Ravens"), "BUF": ("Buffalo", "Bills"),
    "CAR": ("Carolina", "Panthers"), "CHI": ("Chicago", "Bears"),
    "CIN": ("Cincinnati", "Bengals"), "CLE": ("Cleveland", "Browns"),
    "DAL": ("Dallas", "Cowboys"), "DEN": ("Denver", "Broncos"),
    "DET": ("Detroit", "Lions"), "GB": ("Green Bay", "Packers"),
    "HOU": ("Houston", "Texans"), "IND": ("Indianapolis", "Colts"),
    "JAX": ("Jacksonville", "Jaguars"), "KC": ("Kansas City", "Chiefs"),
    "LAC": ("Los Angeles", "Chargers"), "LAR": ("Los Angeles", "Rams"),
    "LV": ("Las Vegas", "Raiders"), "MIA": ("Miami", "Dolphins"),
    "MIN": ("Minnesota", "Vikings"), "NE": ("New England", "Patriots"),
    "NO": ("New Orleans", "Saints"), "NYG": ("New York", "Giants"),
    "NYJ": ("New York", "Jets"), "PHI": ("Philadelphia", "Eagles"),
    "PIT": ("Pittsburgh", "Steelers"), "SEA": ("Seattle", "Seahawks"),
    "SF": ("San Francisco", "49ers"), "TB": ("Tampa Bay", "Buccaneers"),
    "TEN": ("Tennessee", "Titans"), "WSH": ("Washington", "Commanders"),
}

# Alias de abreviatura usados por otras fuentes (Kalshi, Polymarket, feeds antiguos)
TEAM_ALIASES = {
    "WAS": "WSH", "WFT": "WSH", "JAC": "JAX", "LA": "LAR", "STL": "LAR",
    "SD": "LAC", "OAK": "LV", "LVR": "LV", "ARZ": "ARI", "BLT": "BAL",
    "CLV": "CLE", "HST": "HOU", "KAN": "KC", "NOR": "NO", "NWE": "NE",
    "SFO": "SF", "TAM": "TB", "GNB": "GB", "NYA": "NYJ",
}
TEAM_COLORS = {k: v["primary"] for k, v in TEAM_META.items()}
LOGO_TEMPLATE = "https://a.espncdn.com/i/teamlogos/nfl/500/{abbr}.png"


def canonical_abbr(abbr: str) -> str:
    a = (abbr or "").upper().strip()
    return TEAM_ALIASES.get(a, a)


def logo_url(abbr: str) -> str:
    return LOGO_TEMPLATE.format(abbr=canonical_abbr(abbr).lower())


# ---------------------------------------------------------------------------
# Utilidades estadísticas (sin numpy/scipy)
# ---------------------------------------------------------------------------

def norm_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def norm_pdf(x: float, mu: float, sigma: float) -> float:
    if sigma <= 0:
        return 0.0
    z = (x - mu) / sigma
    return math.exp(-0.5 * z * z) / (sigma * math.sqrt(2.0 * math.pi))


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def key_multiplier(margin: float, weights: Dict[str, float]) -> float:
    """Peso de número clave: la normal subestima los márgenes de 3, 7, 10, 14…"""
    k = abs(int(round(margin)))
    return float(weights.get(str(k), weights.get("default", 0.9)))


def american_to_prob(odds: Optional[float]) -> Optional[float]:
    if odds is None:
        return None
    try:
        o = float(odds)
    except (TypeError, ValueError):
        return None
    if o == 0:
        return None
    return (-o) / ((-o) + 100.0) if o < 0 else 100.0 / (o + 100.0)


def devig(p_a: Optional[float], p_b: Optional[float]) -> Tuple[Optional[float], Optional[float]]:
    """Reparte la comisión (vig) proporcionalmente entre los dos lados."""
    if p_a is None or p_b is None or (p_a + p_b) <= 0:
        return (p_a, p_b)
    s = p_a + p_b
    return (p_a / s, p_b / s)


# ---------------------------------------------------------------------------
# Modelo: probabilidad de cubrir el spread
# ---------------------------------------------------------------------------
#
# El margen final (local - visitante) se modela como una normal:
#
#   mu    = margen_actual + margen_esperado_restante + ajuste_por_posesion
#   sigma = sigma_completo * sqrt(fraccion_de_partido_restante)   (con piso)
#
# El margen esperado restante se obtiene de la línea de cierre: un local de
# -3.5 tiene una expectativa de +3.5 puntos para el partido completo, que se
# reparte proporcionalmente al tiempo que queda. Sobre esa normal se aplican
# los pesos de "números clave" (3, 7, 10, 14…) para la probabilidad de push.

def outcome_probabilities(k: float, mu: float, sigma: float,
                          weights: Dict[str, float],
                          max_push: float = 0.35) -> Tuple[float, float, float]:
    """P(X > k), P(X == k) y P(X < k) para una línea `k` sobre una normal discreta.

    Si `k` no es entero no hay push. Si lo es, la masa del empate se calcula con
    la densidad normal en `k` ponderada por el número clave y el resto se
    reescala para que las tres probabilidades sumen 1.
    """
    if sigma <= 1e-9:
        if k > mu + 1e-9:
            return (0.0, 0.0, 1.0)
        if k < mu - 1e-9:
            return (1.0, 0.0, 0.0)
        return (0.0, 1.0, 0.0)

    is_push_line = abs(k - round(k)) < 1e-9
    if not is_push_line:
        p_over = 1.0 - norm_cdf((k - mu) / sigma)
        return (clamp(p_over, 0.0, 1.0), 0.0, clamp(1.0 - p_over, 0.0, 1.0))

    p_push = clamp(norm_pdf(k, mu, sigma) * key_multiplier(k, weights), 0.0, max_push)
    p_over_raw = 1.0 - norm_cdf((k + 0.5 - mu) / sigma)
    p_under_raw = norm_cdf((k - 0.5 - mu) / sigma)
    rest = p_over_raw + p_under_raw
    if rest <= 1e-12:
        return (0.0, 1.0, 0.0)
    scale = (1.0 - p_push) / rest
    return (clamp(p_over_raw * scale, 0.0, 1.0), p_push, clamp(p_under_raw * scale, 0.0, 1.0))


def time_remaining(state: str, period: int, clock_seconds: int, halftime: bool) -> Tuple[int, float]:
    """Segundos de reglamentación restantes y fracción de partido pendiente."""
    if state == "pre":
        return (3600, 1.0)
    if state == "post":
        return (0, 0.0)
    if halftime:
        return (1800, 0.5)
    if period >= 5:                       # tiempo extra
        return (max(clock_seconds, 0), 0.0)
    p = max(1, min(4, int(period or 1)))
    rem = (4 - p) * 900 + max(0, min(900, clock_seconds))
    return (rem, clamp(rem / 3600.0, 0.0, 1.0))


def margin_distribution(margin_now: float, line_home: Optional[float], state: str,
                        period: int, clock_seconds: int, halftime: bool,
                        possession_home: Optional[bool], cfg: dict) -> Dict[str, float]:
    """Media y desviación del margen final (local - visitante)."""
    m = cfg.get("model", {})
    sigma_full = float(m.get("sigma_full_game", 13.2))
    sigma_floor = float(m.get("sigma_floor", 1.4))
    sigma_ot = float(m.get("sigma_overtime", 5.5))
    poss_edge = float(m.get("possession_points", 1.1))

    rem, frac = time_remaining(state, period, clock_seconds, halftime)
    expected_full = -(line_home if line_home is not None else 0.0)

    if state == "post":
        return {"mu": margin_now, "sigma": 0.0, "remaining": 0, "fraction": 0.0}

    if state == "in" and period >= 5:      # tiempo extra: casi moneda al aire
        sigma = max(sigma_floor, sigma_ot * math.sqrt(clamp(max(rem, 60) / 600.0, 0.05, 1.0)))
        mu = margin_now
    else:
        sigma = max(sigma_floor, sigma_full * math.sqrt(frac))
        mu = margin_now + expected_full * frac

    if possession_home is not None and state == "in":
        # Ventaja de tener el balón: irrelevante al inicio, decisiva al final.
        mu += (poss_edge * (1.0 - frac)) * (1.0 if possession_home else -1.0)

    return {"mu": mu, "sigma": sigma, "remaining": rem, "fraction": frac}


def total_distribution(total_now: float, line_total: Optional[float], state: str,
                       period: int, clock_seconds: int, halftime: bool,
                       cfg: dict) -> Dict[str, float]:
    m = cfg.get("model", {})
    sigma_total = float(m.get("sigma_total", 10.6))
    sigma_floor = float(m.get("sigma_floor", 1.4))
    rem, frac = time_remaining(state, period, clock_seconds, halftime)
    if state == "post":
        return {"mu": total_now, "sigma": 0.0, "fraction": 0.0}
    base = float(line_total) if line_total else float(m.get("default_total", 44.0))
    return {"mu": total_now + base * frac,
            "sigma": max(sigma_floor, sigma_total * math.sqrt(max(frac, 0.0))),
            "fraction": frac}


# ---------------------------------------------------------------------------
# Mercados de predicción (Polymarket · Kalshi)
# ---------------------------------------------------------------------------
#
# Ambas plataformas cotizan el ganador de cada partido en probabilidad directa
# (Polymarket en dólares por acción, Kalshi en centavos). Esa probabilidad se
# traduce a un margen esperado invirtiendo la normal del modelo, y de ahí a una
# probabilidad implícita de cubrir el spread, comparable con la del modelo.

POLYMARKET_EVENTS = "https://gamma-api.polymarket.com/events"
KALSHI_MARKETS = "https://api.elections.kalshi.com/trade-api/v2/markets"
KALSHI_NFL_SERIES = "KXNFLGAME"


def inv_norm_cdf(p: float) -> float:
    """Inversa de la normal estándar (Acklam); error < 1e-9 en (0,1)."""
    if p <= 0.0:
        return -8.0
    if p >= 1.0:
        return 8.0
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if p > phigh:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    q = p - 0.5
    r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / \
           (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)


def implied_margin(p_home_win: float, sigma: float) -> float:
    """Margen esperado que justifica una probabilidad de victoria del local."""
    return sigma * inv_norm_cdf(clamp(p_home_win, 0.001, 0.999))


def name_lookup() -> Dict[str, str]:
    """Nombre de equipo (apodo, ciudad, completo) -> abreviatura canónica."""
    out: Dict[str, str] = {}
    for abbr, (loc, nick) in TEAMS.items():
        out[nick.upper()] = abbr
        out[("%s %s" % (loc, nick)).upper()] = abbr
        out[loc.upper()] = abbr
        out[abbr] = abbr
    for alias, abbr in TEAM_ALIASES.items():
        out[alias] = abbr
    # Ciudades compartidas: se resuelven por apodo, no por ubicación
    for shared in ("LOS ANGELES", "NEW YORK"):
        out.pop(shared, None)
    return out


NAME_TO_ABBR = name_lookup()


def abbr_from_text(text: str) -> Optional[str]:
    if not text:
        return None
    up = str(text).upper().strip()
    if up in NAME_TO_ABBR:
        return NAME_TO_ABBR[up]
    for name, abbr in NAME_TO_ABBR.items():
        if len(name) > 3 and name in up:
            return abbr
    tokens = [t.strip(".,-_") for t in up.replace("-", " ").split()]
    for t in tokens:
        if t in NAME_TO_ABBR:
            return NAME_TO_ABBR[t]
    return None


def _as_list(value):
    """Gamma devuelve `outcomes`/`outcomePrices` como lista o como JSON en texto."""
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.strip().startswith("["):
        try:
            return json.loads(value)
        except ValueError:
            return []
    return []


def parse_polymarket(payload) -> List[dict]:
    """Normaliza eventos de la API Gamma a cotizaciones por partido."""
    events = payload if isinstance(payload, list) else (payload or {}).get("events") or []
    quotes: List[dict] = []
    for ev in events:
        markets = ev.get("markets") or ([ev] if ev.get("outcomes") else [])
        for mk in markets:
            kind = (mk.get("sportsMarketType") or "").lower()
            if kind and kind not in ("winner", "moneyline"):
                continue
            outcomes = _as_list(mk.get("outcomes"))
            prices = _as_list(mk.get("outcomePrices"))
            if len(outcomes) != 2:
                continue
            teams: Dict[str, float] = {}
            for i, label in enumerate(outcomes):
                abbr = abbr_from_text(label)
                price = None
                if i < len(prices):
                    try:
                        price = float(prices[i])
                    except (TypeError, ValueError):
                        price = None
                if abbr and price is not None:
                    teams[abbr] = clamp(price, 0.0, 1.0)
            if len(teams) != 2:
                slug_abbrs = [a for a in (abbr_from_text(tok) for tok in
                                          str(mk.get("slug") or ev.get("slug") or "").split("-")) if a]
                if len(set(slug_abbrs)) == 2 and len(prices) == 2:
                    try:
                        teams = {slug_abbrs[0]: clamp(float(prices[0]), 0, 1),
                                 slug_abbrs[1]: clamp(float(prices[1]), 0, 1)}
                    except (TypeError, ValueError):
                        continue
            if len(teams) != 2:
                continue
            try:
                volume = float(mk.get("volume") or ev.get("volume") or 0)
            except (TypeError, ValueError):
                volume = 0.0
            quotes.append({
                "source": "polymarket",
                "id": mk.get("slug") or ev.get("slug") or str(mk.get("id") or ""),
                "title": mk.get("question") or ev.get("title") or "",
                "teams": teams,
                "volume": volume,
                "start": mk.get("gameStartTime") or ev.get("startDate") or "",
                "closed": bool(mk.get("closed") or ev.get("closed")),
            })
    return quotes


def _kalshi_price(mk: dict) -> Optional[float]:
    bid, ask = mk.get("yes_bid"), mk.get("yes_ask")
    try:
        if bid is not None and ask is not None and float(ask) > 0:
            return clamp((float(bid) + float(ask)) / 200.0, 0.0, 1.0)
    except (TypeError, ValueError):
        pass
    for key in ("last_price", "previous_price"):
        try:
            if mk.get(key) is not None:
                return clamp(float(mk[key]) / 100.0, 0.0, 1.0)
        except (TypeError, ValueError):
            continue
    return None


def parse_kalshi(payload) -> List[dict]:
    """Agrupa los mercados por evento: cada equipo es un contrato «Yes»."""
    markets = (payload or {}).get("markets") or []
    by_event: Dict[str, dict] = {}
    for mk in markets:
        ticker = str(mk.get("ticker") or "")
        event_ticker = str(mk.get("event_ticker") or ticker.rsplit("-", 1)[0])
        price = _kalshi_price(mk)
        if price is None:
            continue
        abbr = None
        parts = ticker.split("-")
        if len(parts) >= 3:
            abbr = canonical_abbr(parts[-1])
            if abbr not in TEAM_META:
                abbr = None
        if abbr is None:
            abbr = abbr_from_text(mk.get("yes_sub_title") or mk.get("title") or "")
        if abbr is None:
            continue
        node = by_event.setdefault(event_ticker, {
            "source": "kalshi", "id": event_ticker,
            "title": mk.get("title") or "", "teams": {}, "volume": 0.0,
            "start": mk.get("open_time") or "", "closed": (mk.get("status") or "") not in ("open", "active"),
        })
        node["teams"][abbr] = price
        try:
            node["volume"] += float(mk.get("volume") or 0)
        except (TypeError, ValueError):
            pass
    return [q for q in by_event.values() if len(q["teams"]) == 2]


def normalize_quote(teams: Dict[str, float]) -> Dict[str, float]:
    """Reparte el diferencial (ambos lados rara vez suman exactamente 1)."""
    total = sum(teams.values())
    if total <= 0:
        return teams
    return {k: v / total for k, v in teams.items()}


def attach_markets(games: List[dict], quotes: List[dict]) -> None:
    """Empareja cada cotización con su partido por pareja de equipos."""
    for g in games:
        pair = {g["home"]["abbr"], g["away"]["abbr"]}
        found = g.setdefault("markets", {})
        for q in quotes:
            if set(q["teams"].keys()) != pair or q.get("closed"):
                continue
            prev = found.get(q["source"])
            if prev and prev.get("volume", 0) >= q.get("volume", 0):
                continue
            norm = normalize_quote(q["teams"])
            found[q["source"]] = {
                "id": q.get("id", ""), "title": q.get("title", ""),
                "p_home_win": round(norm.get(g["home"]["abbr"], 0.5), 4),
                "p_away_win": round(norm.get(g["away"]["abbr"], 0.5), 4),
                "raw_home": round(q["teams"].get(g["home"]["abbr"], 0.0), 4),
                "volume": round(q.get("volume", 0.0), 2),
            }


def fetch_markets(cfg: dict) -> Tuple[List[dict], Dict[str, str]]:
    """Consulta las fuentes habilitadas; devuelve cotizaciones y estado por fuente."""
    sources = cfg.get("sources", {})
    quotes: List[dict] = []
    status: Dict[str, str] = {}

    pm = sources.get("polymarket", {})
    if pm.get("enabled", True):
        url = pm.get("endpoint", POLYMARKET_EVENTS) + "?" + (pm.get("query") or "tag_slug=nfl&closed=false&limit=200")
        try:
            found = parse_polymarket(http_json(url))
            quotes.extend(found)
            status["polymarket"] = "ok (%d mercados)" % len(found)
        except Exception as exc:                      # red, formato o bloqueo
            status["polymarket"] = "error: %s" % exc

    kal = sources.get("kalshi", {})
    if kal.get("enabled", True):
        url = kal.get("endpoint", KALSHI_MARKETS) + "?series_ticker=%s&status=open&limit=500" % \
            kal.get("series_ticker", KALSHI_NFL_SERIES)
        try:
            found = parse_kalshi(http_json(url))
            quotes.extend(found)
            status["kalshi"] = "ok (%d eventos)" % len(found)
        except Exception as exc:
            status["kalshi"] = "error: %s" % exc

    return quotes, status


def evaluate_game(g: dict, cfg: dict) -> dict:
    """Añade a un partido normalizado sus probabilidades de spread, total y victoria."""
    weights = cfg.get("model", {}).get("key_numbers", {})
    state = g.get("state", "pre")
    margin_now = float(g.get("home_score", 0) or 0) - float(g.get("away_score", 0) or 0)
    total_now = float(g.get("home_score", 0) or 0) + float(g.get("away_score", 0) or 0)
    line_home = g.get("line_home")
    line_total = g.get("line_total")

    dist = margin_distribution(margin_now, line_home, state, g.get("period", 0),
                               g.get("clock_seconds", 0), bool(g.get("halftime")),
                               g.get("possession_home"), cfg)
    mu, sigma = dist["mu"], dist["sigma"]

    out: Dict[str, object] = {
        "margin_now": margin_now,
        "total_now": total_now,
        "projected_margin": round(mu, 1),
        "sigma": round(sigma, 2),
        "remaining_seconds": dist["remaining"],
        "fraction_remaining": round(dist["fraction"], 4),
    }

    # ---- Spread -----------------------------------------------------------
    if line_home is not None:
        k = -float(line_home)                      # margen que el local debe superar
        p_home, p_push, p_away = outcome_probabilities(k, mu, sigma, weights)
        out.update({
            "p_home_cover": round(p_home, 4),
            "p_away_cover": round(p_away, 4),
            "p_push": round(p_push, 4),
            "cover_margin_now": round(margin_now + float(line_home), 1),
        })
        if state == "post":
            edge = margin_now + float(line_home)
            out["ats_result"] = "home" if edge > 0 else ("away" if edge < 0 else "push")
    # ---- Moneyline --------------------------------------------------------
    p_hw, p_tie, p_aw = outcome_probabilities(0.0, mu, sigma, weights, max_push=0.02)
    out.update({"p_home_win": round(p_hw, 4), "p_away_win": round(p_aw, 4), "p_tie": round(p_tie, 4)})

    # ---- Total ------------------------------------------------------------
    tdist = total_distribution(total_now, line_total, state, g.get("period", 0),
                               g.get("clock_seconds", 0), bool(g.get("halftime")), cfg)
    out["projected_total"] = round(tdist["mu"], 1)
    if line_total is not None:
        p_over, p_push_t, p_under = outcome_probabilities(float(line_total), tdist["mu"], tdist["sigma"], weights)
        out.update({"p_over": round(p_over, 4), "p_under": round(p_under, 4),
                    "p_total_push": round(p_push_t, 4)})
        if state == "post":
            out["total_result"] = ("over" if total_now > float(line_total)
                                   else "under" if total_now < float(line_total) else "push")

    # ---- Mercados de predicción (Polymarket · Kalshi) --------------------
    markets = g.get("markets") or {}
    market_wins: List[float] = []
    for src in ("polymarket", "kalshi"):
        node = markets.get(src)
        if not node or node.get("p_home_win") is None:
            continue
        p_win = clamp(float(node["p_home_win"]), 0.0, 1.0)
        market_wins.append(p_win)
        if sigma > 0:
            mu_m = implied_margin(p_win, sigma)
            node["implied_margin"] = round(mu_m, 1)
            if line_home is not None:
                ph, pp, pa = outcome_probabilities(-float(line_home), mu_m, sigma, weights)
                node["p_home_cover"] = round(ph, 4)
                node["p_away_cover"] = round(pa, 4)
                node["p_push"] = round(pp, 4)
    if market_wins:
        cons_cfg = cfg.get("consensus", {})
        w_model = clamp(float(cons_cfg.get("model_weight", 0.5)), 0.0, 1.0)
        market_win = sum(market_wins) / len(market_wins)
        out["market_win_consensus"] = round(market_win, 4)
        out["market_divergence"] = round(market_win - float(out["p_home_win"]), 4)
        out["consensus_home_win"] = round(w_model * float(out["p_home_win"]) + (1 - w_model) * market_win, 4)
        covers = [m["p_home_cover"] for m in markets.values() if m.get("p_home_cover") is not None]
        if covers and out.get("p_home_cover") is not None:
            market_cover = sum(covers) / len(covers)
            out["market_cover_consensus"] = round(market_cover, 4)
            out["consensus_home_cover"] = round(
                w_model * float(out["p_home_cover"]) + (1 - w_model) * market_cover, 4)

    # ---- Ventaja contra el mercado ---------------------------------------
    mkt_home = american_to_prob(g.get("home_spread_odds"))
    mkt_away = american_to_prob(g.get("away_spread_odds"))
    mh, ma = devig(mkt_home, mkt_away)
    if mh is not None and out.get("p_home_cover") is not None and state != "post":
        out["market_home_cover"] = round(mh, 4)
        out["market_away_cover"] = round(ma, 4)
        live = float(out["p_home_cover"]) / max(1e-9, 1.0 - float(out.get("p_push", 0.0)))
        out["edge_home_cover"] = round(live - mh, 4)
    ml_h, ml_a = devig(american_to_prob(g.get("home_moneyline")), american_to_prob(g.get("away_moneyline")))
    if ml_h is not None:
        out["market_home_win"] = round(ml_h, 4)
        out["market_away_win"] = round(ml_a, 4)

    g["probs"] = out
    return g


# ---------------------------------------------------------------------------
# Lectura del marcador oficial (API pública de ESPN)
# ---------------------------------------------------------------------------

def scoreboard_url(season: Optional[int], week: Optional[int], seasontype: Optional[int],
                   dates: Optional[str] = None) -> str:
    params = ["limit=100"]
    if dates:
        params.append("dates=%s" % dates)
    elif season:
        params.append("dates=%d" % season)
    if seasontype:
        params.append("seasontype=%d" % seasontype)
    if week:
        params.append("week=%d" % week)
    return ESPN_SCOREBOARD + "?" + "&".join(params)


def http_json(url: str, timeout: int = 20) -> dict:
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; nfl-dashboard/1.0)",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def clock_to_seconds(display_clock: Optional[str]) -> int:
    if not display_clock:
        return 0
    txt = str(display_clock).strip()
    if ":" not in txt:
        try:
            return int(float(txt))
        except ValueError:
            return 0
    mm, _, ss = txt.partition(":")
    try:
        return int(float(mm)) * 60 + int(float(ss))
    except ValueError:
        return 0


def _first_number(text: str) -> Optional[float]:
    for token in text.replace("(", " ").replace(")", " ").split():
        try:
            return float(token)
        except ValueError:
            continue
    return None


def parse_spread(odds: dict, home_abbr: str, away_abbr: str) -> Tuple[Optional[float], Optional[str]]:
    """Devuelve la línea **desde la óptica del local** (negativo = local favorito)."""
    if not isinstance(odds, dict):
        return (None, None)
    details = (odds.get("details") or "").strip()
    display = details or None

    if details:
        up = details.upper().replace("'", "")
        if up in ("EVEN", "PK", "PICK", "PICKEM", "PICK EM"):
            return (0.0, display)
        value = _first_number(up)
        if value is not None:
            tokens = [t.strip(":,") for t in up.split()]
            if home_abbr and home_abbr.upper() in tokens:
                return (value, display)
            if away_abbr and away_abbr.upper() in tokens:
                return (-value, display)

    home_odds = odds.get("homeTeamOdds") or {}
    away_odds = odds.get("awayTeamOdds") or {}
    for node, sign in ((home_odds, 1.0), (away_odds, -1.0)):
        close = (node.get("close") or {}).get("pointSpread") or {}
        raw = close.get("line") or close.get("alternateDisplayValue") or close.get("american")
        if raw not in (None, ""):
            try:
                return (float(str(raw).replace("+", "")) * sign, display or str(raw))
            except ValueError:
                pass

    spread = odds.get("spread")
    if spread is not None:
        try:
            value = float(spread)
        except (TypeError, ValueError):
            return (None, display)
        if home_odds.get("favorite") is True:
            return (-abs(value), display)
        if away_odds.get("favorite") is True:
            return (abs(value), display)
        return (value, display)
    return (None, display)


def _moneyline(node: dict) -> Optional[float]:
    if not isinstance(node, dict):
        return None
    for raw in (node.get("moneyLine"), ((node.get("close") or {}).get("moneyLine") or {}).get("american")):
        if raw not in (None, "", "OFF"):
            try:
                return float(str(raw).replace("+", ""))
            except ValueError:
                continue
    return None


def _spread_odds(node: dict) -> Optional[float]:
    if not isinstance(node, dict):
        return None
    for raw in (node.get("spreadOdds"), ((node.get("close") or {}).get("pointSpread") or {}).get("american")):
        if raw not in (None, "", "OFF"):
            try:
                return float(str(raw).replace("+", ""))
            except ValueError:
                continue
    return None


def _team(comp: dict, side: str) -> dict:
    for c in comp.get("competitors", []):
        if c.get("homeAway") == side:
            return c
    return {}


def parse_event(ev: dict) -> Optional[dict]:
    comps = ev.get("competitions") or []
    if not comps:
        return None
    comp = comps[0]
    home_c, away_c = _team(comp, "home"), _team(comp, "away")
    home_t, away_t = (home_c.get("team") or {}), (away_c.get("team") or {})
    status = ev.get("status") or comp.get("status") or {}
    stype = status.get("type") or {}
    state = stype.get("state") or "pre"
    name = (stype.get("name") or "").upper()

    def team_dict(c: dict, t: dict) -> dict:
        abbr = (t.get("abbreviation") or "").upper()
        record = ""
        for r in (c.get("records") or []):
            if r.get("type") in ("total", None) or r.get("name") == "overall":
                record = r.get("summary") or ""
                break
        key = canonical_abbr(abbr)
        meta = TEAM_META.get(key, {})
        feed_color = t.get("color") or ""
        feed_alt = t.get("alternateColor") or ""
        return {
            "id": str(t.get("id") or ""),
            "abbr": key or abbr,
            "name": t.get("displayName") or t.get("name") or abbr,
            "short": t.get("shortDisplayName") or t.get("name") or abbr,
            "location": t.get("location") or "",
            "color": meta.get("primary") or (("#" + feed_color) if feed_color else "#1E2761"),
            "alt_color": meta.get("secondary") or (("#" + feed_alt) if feed_alt else "#8895B3"),
            "logo": t.get("logo") or logo_url(key or abbr),
            "record": record,
        }

    def score(c: dict) -> int:
        try:
            return int(float(c.get("score") or 0))
        except (TypeError, ValueError):
            return 0

    odds_list = comp.get("odds") or []
    odds = odds_list[0] if odds_list else {}
    home, away = team_dict(home_c, home_t), team_dict(away_c, away_t)
    line_home, line_display = parse_spread(odds, home["abbr"], away["abbr"])
    try:
        line_total = float(odds.get("overUnder")) if odds.get("overUnder") is not None else None
    except (TypeError, ValueError):
        line_total = None

    situation = comp.get("situation") or {}
    possession_id = str(situation.get("possession") or "")
    possession_home = None
    if state == "in" and possession_id:
        if possession_id == home["id"]:
            possession_home = True
        elif possession_id == away["id"]:
            possession_home = False

    broadcast = ""
    for b in (comp.get("broadcasts") or []):
        names = b.get("names") or []
        if names:
            broadcast = names[0]
            break

    venue = (comp.get("venue") or {}).get("fullName") or ""

    return {
        "id": str(ev.get("id") or comp.get("id") or ""),
        "date": ev.get("date") or comp.get("date") or "",
        "name": ev.get("shortName") or ev.get("name") or "",
        "state": state,
        "status_detail": stype.get("detail") or "",
        "status_short": stype.get("shortDetail") or "",
        "completed": bool(stype.get("completed")),
        "halftime": name == "STATUS_HALFTIME" or (stype.get("description") or "").lower() == "halftime",
        "period": int(status.get("period") or 0),
        "clock": status.get("displayClock") or "",
        "clock_seconds": clock_to_seconds(status.get("displayClock")),
        "home": home,
        "away": away,
        "home_score": score(home_c),
        "away_score": score(away_c),
        "line_home": line_home,
        "line_display": line_display,
        "line_total": line_total,
        "odds_provider": (odds.get("provider") or {}).get("name") or "",
        "home_moneyline": _moneyline(odds.get("homeTeamOdds") or {}),
        "away_moneyline": _moneyline(odds.get("awayTeamOdds") or {}),
        "home_spread_odds": _spread_odds(odds.get("homeTeamOdds") or {}),
        "away_spread_odds": _spread_odds(odds.get("awayTeamOdds") or {}),
        "possession_home": possession_home,
        "down_distance": situation.get("downDistanceText") or "",
        "possession_text": situation.get("possessionText") or "",
        "red_zone": bool(situation.get("isRedZone")),
        "last_play": ((situation.get("lastPlay") or {}).get("text") or "") if isinstance(situation.get("lastPlay"), dict) else "",
        "venue": venue,
        "broadcast": broadcast,
        "neutral_site": bool(comp.get("neutralSite")),
    }


def fetch_scoreboard(season: Optional[int], week: Optional[int], seasontype: Optional[int],
                     dates: Optional[str] = None) -> Tuple[List[dict], dict]:
    url = scoreboard_url(season, week, seasontype, dates)
    raw = http_json(url)
    games = [g for g in (parse_event(ev) for ev in (raw.get("events") or [])) if g]
    meta = {
        "season": ((raw.get("season") or {}).get("year")
                   or (raw.get("leagues") or [{}])[0].get("season", {}).get("year")),
        "seasontype": (raw.get("season") or {}).get("type") or seasontype,
        "week": (raw.get("week") or {}).get("number") or week,
        "url": url,
    }
    return games, meta


# ---------------------------------------------------------------------------
# Datos sintéticos (--demo): permiten probar el tablero sin red
# ---------------------------------------------------------------------------

DEMO_MATCHUPS = [
    ("KC", "BUF"), ("SF", "DAL"), ("PHI", "NYG"), ("BAL", "CIN"),
    ("DET", "GB"), ("MIA", "NYJ"), ("HOU", "IND"), ("LAR", "SEA"),
    ("TB", "NO"), ("MIN", "CHI"), ("DEN", "LV"), ("PIT", "CLE"),
    ("JAX", "TEN"), ("LAC", "ARI"), ("ATL", "CAR"), ("WSH", "NE"),
]


def demo_games(cfg: dict, seed: int = 20250913) -> List[dict]:
    rnd = random.Random(seed)
    now = dt.datetime.now(dt.timezone.utc)
    games: List[dict] = []

    def team_block(abbr: str) -> dict:
        loc, nick = TEAMS[abbr]
        meta = TEAM_META.get(abbr, {})
        return {"id": abbr, "abbr": abbr, "name": "%s %s" % (loc, nick), "short": nick,
                "location": loc, "color": meta.get("primary", "#1E2761"),
                "alt_color": meta.get("secondary", "#8895B3"), "logo": logo_url(abbr),
                "record": "%d-%d" % (rnd.randint(1, 11), rnd.randint(1, 8))}

    # 5 finalizados, 5 en curso (incluye medio tiempo y tiempo extra), el resto por jugar
    plan = (["post"] * 5) + ["in", "in", "in", "half", "ot"] + ["pre"] * 6

    for i, (home_abbr, away_abbr) in enumerate(DEMO_MATCHUPS):
        kind = plan[i % len(plan)]
        line_home = round(rnd.choice([-9.5, -7.0, -6.5, -4.5, -3.5, -3.0, -2.5, -1.5, 0.0,
                                      1.5, 2.5, 3.0, 3.5, 6.5]), 1)
        line_total = round(rnd.choice([38.5, 41.0, 42.5, 44.5, 45.0, 47.5, 49.5, 51.5]), 1)
        state, period, clock, halftime = "pre", 0, "", False
        hs = as_ = 0
        possession_home = None
        down_distance, last_play = "", ""

        if kind in ("post", "in", "half", "ot"):
            pace = {"post": 1.0, "in": rnd.choice([0.35, 0.6, 0.85]), "half": 0.5, "ot": 1.0}[kind]
            exp_total = line_total * pace
            exp_margin = -line_home * pace
            hs = max(0, int(round((exp_total + exp_margin) / 2 + rnd.gauss(0, 3.5))))
            as_ = max(0, int(round((exp_total - exp_margin) / 2 + rnd.gauss(0, 3.5))))
            hs = int(round(hs / 3.0)) * 3 + rnd.choice([0, 0, 1, 4])
            as_ = int(round(as_ / 3.0)) * 3 + rnd.choice([0, 0, 1, 4])

        if kind == "post":
            state, period, clock = "post", 4, "0:00"
            if hs == as_:
                hs += 3
        elif kind == "in":
            state = "in"
            period = {0.35: 2, 0.6: 3, 0.85: 4}.get(round(pace, 2), rnd.randint(2, 4))
            period = max(1, min(4, period))
            secs = rnd.randint(20, 890)
            clock = "%d:%02d" % (secs // 60, secs % 60)
            possession_home = rnd.choice([True, False])
            down_distance = rnd.choice(["1ro y 10 en la 32", "2do y 7 en la 50",
                                        "3ro y 4 en la 38 rival", "4to y 1 en la 12 rival"])
            last_play = rnd.choice([
                "Pase completo de 12 yardas para primer down.",
                "Carrera de 3 yardas por el centro.",
                "Gol de campo bueno de 41 yardas.",
                "Pase incompleto por la banda derecha.",
                "Despeje de 46 yardas, sin retorno.",
            ])
        elif kind == "half":
            state, period, clock, halftime = "in", 2, "0:00", True
        elif kind == "ot":
            state, period = "in", 5
            secs = rnd.randint(60, 560)
            clock = "%d:%02d" % (secs // 60, secs % 60)
            as_ = hs  # empatados al final de reglamentación
            possession_home = rnd.choice([True, False])
            down_distance = "1ro y 10 en la 44 rival"

        kickoff = now + dt.timedelta(hours=(-3 if kind != "pre" else rnd.randint(2, 72)))
        games.append({
            "id": "demo-%02d" % (i + 1),
            "date": kickoff.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "name": "%s @ %s" % (away_abbr, home_abbr),
            "state": state,
            "status_detail": {"post": "Final", "pre": kickoff.strftime("%d/%m %H:%M UTC")}.get(
                kind, "Medio tiempo" if kind == "half" else ("TE %s" % clock if kind == "ot" else "Q%d %s" % (period, clock))),
            "status_short": "Final" if kind == "post" else clock,
            "completed": kind == "post",
            "halftime": halftime,
            "period": period,
            "clock": clock,
            "clock_seconds": clock_to_seconds(clock),
            "home": team_block(home_abbr),
            "away": team_block(away_abbr),
            "home_score": hs,
            "away_score": as_,
            "line_home": line_home,
            "line_display": ("%s %+.1f" % (home_abbr, line_home)) if line_home else "PK",
            "line_total": line_total,
            "odds_provider": "Demo",
            "home_moneyline": -170 if line_home < 0 else 145,
            "away_moneyline": 145 if line_home < 0 else -170,
            "home_spread_odds": -110,
            "away_spread_odds": -110,
            "possession_home": possession_home,
            "down_distance": down_distance,
            "possession_text": "",
            "red_zone": bool(possession_home is not None and rnd.random() < 0.2),
            "last_play": last_play,
            "venue": "Estadio demo",
            "broadcast": rnd.choice(["FOX", "CBS", "NBC", "ESPN", "Prime"]),
            "neutral_site": False,
        })
    return games


def demo_quotes(games: List[dict], cfg: dict, seed: int = 7311) -> List[dict]:
    """Cotizaciones sintéticas de Polymarket y Kalshi alrededor de la línea."""
    rnd = random.Random(seed)
    sigma = float(cfg.get("model", {}).get("sigma_full_game", 13.2))
    quotes: List[dict] = []
    for g in games:
        if g.get("line_home") is None or g.get("state") == "post":
            continue
        base = norm_cdf(-float(g["line_home"]) / sigma)
        home, away = g["home"]["abbr"], g["away"]["abbr"]
        for source, spread_cents in (("polymarket", 0.02), ("kalshi", 0.03)):
            if rnd.random() < 0.15:       # no todos los partidos tienen mercado
                continue
            p = clamp(base + rnd.gauss(0, 0.035), 0.03, 0.97)
            quotes.append({
                "source": source,
                "id": "%s-%s-%s" % (source[:2], away.lower(), home.lower()),
                "title": "%s vs %s" % (away, home),
                "teams": {home: round(p, 3), away: round(1 - p + spread_cents, 3)},
                "volume": round(rnd.uniform(15000, 900000), 2),
                "start": g.get("date", ""),
                "closed": False,
            })
    return quotes


# ---------------------------------------------------------------------------
# Reporte
# ---------------------------------------------------------------------------

def summarize(games: List[dict]) -> dict:
    finals = [g for g in games if g.get("state") == "post"]
    live = [g for g in games if g.get("state") == "in"]
    pre = [g for g in games if g.get("state") == "pre"]
    ats = {"home": 0, "away": 0, "push": 0}
    fav, dog = 0, 0
    for g in finals:
        res = (g.get("probs") or {}).get("ats_result")
        if res in ats:
            ats[res] += 1
        line = g.get("line_home")
        if res in ("home", "away") and line is not None and line != 0:
            favorite_is_home = line < 0
            if (res == "home") == favorite_is_home:
                fav += 1
            else:
                dog += 1
    decided = ats["home"] + ats["away"]
    totals_over = sum(1 for g in finals if (g.get("probs") or {}).get("total_result") == "over")
    totals_under = sum(1 for g in finals if (g.get("probs") or {}).get("total_result") == "under")
    return {
        "games": len(games),
        "live": len(live),
        "final": len(finals),
        "scheduled": len(pre),
        "ats_home": ats["home"], "ats_away": ats["away"], "ats_push": ats["push"],
        "ats_home_pct": round(100.0 * ats["home"] / decided, 1) if decided else None,
        "favorites_covered": fav, "underdogs_covered": dog,
        "favorites_pct": round(100.0 * fav / (fav + dog), 1) if (fav + dog) else None,
        "totals_over": totals_over, "totals_under": totals_under,
        "points": sum((g.get("home_score") or 0) + (g.get("away_score") or 0) for g in games),
        "with_line": sum(1 for g in games if g.get("line_home") is not None),
    }


def build_report(games: List[dict], cfg: dict, meta: dict, source: str,
                 quotes: Optional[List[dict]] = None,
                 source_status: Optional[Dict[str, str]] = None) -> dict:
    if quotes:
        attach_markets(games, quotes)
    for g in games:
        evaluate_game(g, cfg)
    games.sort(key=lambda g: ({"in": 0, "pre": 1, "post": 2}.get(g.get("state"), 3), g.get("date") or ""))
    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "source": source,
        "source_status": source_status or {},
        "meta": meta,
        "config": cfg,
        "quotes": quotes or [],
        "teams": {k: list(v) for k, v in TEAMS.items()},
        "team_meta": TEAM_META,
        "team_aliases": TEAM_ALIASES,
        "summary": summarize(games),
        "games": games,
    }


# ---------------------------------------------------------------------------
# Dashboard HTML (autocontenido; se refresca solo contra la API de ESPN)
# ---------------------------------------------------------------------------

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>NFL · Resultados y probabilidad de spread</title>
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
.wrap{max-width:1320px;margin:0 auto;padding:22px 26px 60px;position:relative}
header{display:flex;align-items:flex-end;justify-content:space-between;gap:20px;flex-wrap:wrap;border-bottom:1px solid var(--divider);padding-bottom:18px}
.kick{display:flex;align-items:center;gap:10px;font-weight:800;letter-spacing:.32em;font-size:12px;color:var(--cyan);text-transform:uppercase}
.kick .dot{width:9px;height:9px;border-radius:50%;background:var(--cyan);box-shadow:0 0 10px var(--cyan)}
h1{font-family:var(--serif);font-weight:700;font-size:30px;line-height:1.05;margin:8px 0 4px}
h1 .light{color:var(--ice);font-style:italic;font-weight:400}
.sub{color:var(--mute);font-size:13px}
.headright{display:flex;flex-direction:column;align-items:flex-end;gap:8px}
.chip{display:inline-flex;align-items:center;gap:8px;padding:6px 12px;border:1px solid var(--divider);border-radius:999px;background:var(--surface);font-size:12px;color:var(--ice)}
.chip .dot{width:8px;height:8px;border-radius:50%;background:var(--green);box-shadow:0 0 9px var(--green)}
.chip.warn .dot{background:var(--amber);box-shadow:0 0 9px var(--amber)}
.chip.bad .dot{background:var(--rose);box-shadow:0 0 9px var(--rose)}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.35}}
.chip.loading .dot{animation:pulse 1s infinite}
.sources{display:flex;gap:8px;flex-wrap:wrap;margin:14px 0 0}
.chip.src{font-size:11.5px;padding:5px 11px;gap:7px}
.chip.src em{font-style:normal;color:var(--mute)}
.chip.src.ok .dot{background:var(--green);box-shadow:0 0 8px var(--green)}
.chip.src.warn .dot{background:var(--amber);box-shadow:0 0 8px var(--amber)}

.controls{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin:18px 0 4px}
.controls label{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--mute);margin-right:4px}
select,input[type=number]{background:var(--surface2);color:var(--white);border:1px solid var(--divider);border-radius:8px;padding:7px 10px;font:inherit;font-size:13px}
input[type=number]{width:92px}
button.act{background:var(--surface2);border:1px solid var(--divider);color:var(--ice);border-radius:8px;padding:7px 14px;font:inherit;font-size:13px;cursor:pointer}
button.act:hover{border-color:var(--cyan);color:var(--cyan)}
button.act.on{border-color:var(--cyan);color:var(--cyan)}
.ctlgroup{display:flex;align-items:center;gap:6px;padding:4px 8px;border:1px solid var(--divider);border-radius:999px;background:rgba(21,30,69,.55)}

.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:20px 0}
.kpi{background:var(--surface);border:1px solid var(--divider);border-radius:12px;padding:16px 18px}
.kpi .lbl{font-size:11px;letter-spacing:.18em;text-transform:uppercase;color:var(--mute)}
.kpi .val{font-family:var(--serif);font-size:38px;line-height:1.05;margin-top:6px;color:var(--cyan)}
.kpi .val.amber{color:var(--amber)}
.kpi .val.green{color:var(--green)}
.kpi .foot{font-size:12px;color:var(--mute);margin-top:6px}

.tabs{display:flex;gap:6px;border-bottom:1px solid var(--divider);margin:6px 0 18px;flex-wrap:wrap}
.tabs button{background:transparent;border:0;color:var(--mute);font:inherit;font-size:13px;padding:10px 14px;cursor:pointer;border-bottom:2px solid transparent}
.tabs button:hover{color:var(--ice)}
.tabs button.active{color:var(--cyan);border-bottom-color:var(--cyan)}
[data-panel]{display:none}[data-panel].active{display:block}

.filters{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px;align-items:center}
.filters .f{padding:5px 11px;border-radius:999px;border:1px solid var(--divider);background:transparent;color:var(--mute);font:inherit;font-size:12px;cursor:pointer}
.filters .f.active{color:var(--cyan);border-color:var(--cyan)}

.games{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:14px}
.game{background:var(--surface);border:1px solid var(--divider);border-radius:12px;padding:14px 16px;display:flex;flex-direction:column;gap:10px}
.game.islive{border-color:rgba(0,217,255,.45);box-shadow:0 0 0 1px rgba(0,217,255,.08)}
.ghead{display:flex;justify-content:space-between;align-items:center;gap:10px;font-size:11.5px;color:var(--mute)}
.tag{display:inline-flex;align-items:center;gap:6px;padding:2px 9px;border-radius:999px;font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;border:1px solid}
.tag.live{color:var(--cyan);border-color:rgba(0,217,255,.45);background:rgba(0,217,255,.08)}
.tag.live i{width:7px;height:7px;border-radius:50%;background:var(--cyan);animation:pulse 1.2s infinite}
.tag.pre{color:var(--ice);border-color:var(--divider);background:rgba(202,220,252,.05)}
.tag.post{color:var(--mute);border-color:var(--divider)}
.tag.rz{color:var(--rose);border-color:rgba(255,92,122,.45);background:rgba(255,92,122,.10)}

.teams{display:flex;flex-direction:column;gap:7px}
.trow{display:grid;grid-template-columns:26px 1fr auto auto;align-items:center;gap:9px}
.crest{width:26px;height:26px;object-fit:contain;display:inline-block;vertical-align:middle;filter:drop-shadow(0 1px 2px rgba(0,0,0,.45))}
.crest.sm{width:18px;height:18px;margin-right:2px}
.crest.fallback{border-radius:5px;font-size:9px;font-weight:800;letter-spacing:.02em;color:#fff;
  display:inline-flex;align-items:center;justify-content:center;text-align:center;line-height:1;
  box-shadow:0 0 0 1px rgba(255,255,255,.18) inset}
.crest.sm.fallback{font-size:7px;border-radius:4px}
.teamstrip{display:flex;height:4px;border-radius:3px;overflow:hidden;margin:-4px -4px 2px}
.teamstrip i{flex:1}
.mkts{display:flex;gap:7px;flex-wrap:wrap;border-top:1px dashed var(--divider);padding-top:9px}
.mk{display:inline-flex;align-items:center;gap:5px;padding:3px 9px;border-radius:999px;font-size:11px;
  border:1px solid var(--divider);color:var(--mute);background:rgba(30,41,82,.5)}
.mk b{color:var(--ice);font-family:var(--mono);font-weight:600}
.mk.polymarket{border-color:rgba(0,217,255,.35)}
.mk.kalshi{border-color:rgba(61,214,140,.35)}
.mk.cons{border-color:rgba(255,184,0,.4);color:var(--amber)}
.mk.cons b{color:var(--amber)}
.stale{color:var(--amber);font-weight:700}
.trow .nm{font-weight:600;font-size:14px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.trow .nm small{display:block;color:var(--mute);font-size:11px;font-weight:400}
.trow .ball{color:var(--amber);font-size:12px;width:14px;text-align:center}
.trow .sc{font-family:var(--mono);font-size:22px;min-width:34px;text-align:right}
.trow.loser .nm,.trow.loser .sc{color:var(--mute)}
.trow.win .sc{color:var(--white)}

.lines{display:flex;gap:14px;flex-wrap:wrap;font-size:11.5px;color:var(--mute);border-top:1px solid var(--divider);padding-top:9px}
.lines b{color:var(--ice);font-family:var(--mono);font-weight:600}

.probs{display:flex;flex-direction:column;gap:7px}
.prow{display:grid;grid-template-columns:52px 1fr 54px;align-items:center;gap:9px;font-size:12px}
.prow .who{color:var(--mute);font-family:var(--mono);font-size:11.5px}
.prow .pct{text-align:right;font-family:var(--mono);font-size:13px;color:var(--ice)}
.bar{height:8px;background:var(--divider);border-radius:4px;overflow:hidden}
.bar i{display:block;height:100%;background:var(--cyan);transition:width .4s ease}
.bar i.green{background:var(--green)}.bar i.rose{background:var(--rose)}.bar i.amber{background:var(--amber)}
.proj{display:flex;gap:12px;flex-wrap:wrap;font-size:11.5px;color:var(--mute)}
.proj b{color:var(--ice);font-family:var(--mono);font-weight:600}
.situ{font-size:11.5px;color:var(--mute);border-top:1px dashed var(--divider);padding-top:8px;min-height:0}
.situ b{color:var(--ice);font-weight:600}
.res{display:flex;gap:8px;flex-wrap:wrap;align-items:center;font-size:12px}
.pill{display:inline-block;padding:3px 10px;border-radius:6px;font-size:11px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;border:1px solid}
.pill.ok{color:var(--green);border-color:rgba(61,214,140,.4);background:rgba(61,214,140,.08)}
.pill.no{color:var(--rose);border-color:rgba(255,92,122,.4);background:rgba(255,92,122,.08)}
.pill.push{color:var(--amber);border-color:rgba(255,184,0,.4);background:rgba(255,184,0,.08)}

.card{background:var(--surface);border:1px solid var(--divider);border-radius:12px;padding:16px 18px;margin-bottom:14px}
.card h2{font-family:var(--serif);font-weight:700;font-size:18px;margin:0 0 4px}
.card h3{font-size:12px;letter-spacing:.18em;text-transform:uppercase;color:var(--cyan);margin:0 0 10px;font-weight:700}
.card p{color:var(--ice);font-size:13px;margin:0 0 10px}
.card ul{margin:0 0 10px;padding-left:18px;color:var(--ice);font-size:13px}
.card li{margin-bottom:5px}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:14px}

table{width:100%;border-collapse:collapse;font-size:13px}
th,td{padding:8px 10px;text-align:right;border-bottom:1px solid var(--divider);white-space:nowrap}
th{color:var(--mute);font-weight:600;font-size:11px;letter-spacing:.12em;text-transform:uppercase;cursor:pointer;user-select:none}
th:hover{color:var(--ice)}
th.sorted{color:var(--cyan)}
th:first-child,td:first-child{text-align:left}
tr.row:hover td{background:rgba(0,217,255,.04)}
.num{font-family:var(--mono);font-size:12.5px}
.pos{color:var(--green)}.neg{color:var(--rose)}.flat{color:var(--ice)}
.tscroll{overflow-x:auto}
.mini{height:6px;width:74px;background:var(--divider);border-radius:3px;overflow:hidden;display:inline-block;vertical-align:middle;margin-right:7px}
.mini i{display:block;height:100%;background:var(--cyan)}

.chart svg{width:100%;height:auto;display:block}
.note{border-left:3px solid var(--amber);padding:10px 14px;background:rgba(255,184,0,.06);border-radius:0 8px 8px 0;font-size:12.5px;color:var(--ice);margin-top:14px}
.empty{color:var(--mute);padding:26px;text-align:center}
footer{margin-top:28px;color:var(--mute);font-size:11.5px;border-top:1px solid var(--divider);padding-top:14px}
@media (max-width:980px){.kpis{grid-template-columns:repeat(2,1fr)}.grid2{grid-template-columns:1fr}}
@media (max-width:560px){.kpis{grid-template-columns:1fr}.wrap{padding:16px}.headright{align-items:flex-start}}
</style>
</head>
<body>
<div class="wrap">
<header>
  <div class="brand">
    <div class="kick"><span class="dot"></span>NFL · Marcador en vivo &amp; líneas</div>
    <h1>Resultados y <span class="light">probabilidad de cubrir</span> el spread</h1>
    <div class="sub" id="subtitle">Cargando…</div>
  </div>
  <div class="headright">
    <span class="chip" id="status-chip"><span class="dot"></span><span id="status-text">Iniciando</span></span>
    <span class="sub" id="updated"></span>
  </div>
</header>

<div class="sources" id="sources"></div>

<div class="controls">
  <div class="ctlgroup">
    <label for="season">Temporada</label>
    <input type="number" id="season" min="2002" max="2100" step="1">
  </div>
  <div class="ctlgroup">
    <label for="stype">Fase</label>
    <select id="stype">
      <option value="1">Pretemporada</option>
      <option value="2" selected>Temporada regular</option>
      <option value="3">Postemporada</option>
    </select>
  </div>
  <div class="ctlgroup">
    <label for="week">Semana</label>
    <select id="week"></select>
  </div>
  <div class="ctlgroup">
    <label for="every">Auto</label>
    <select id="every">
      <option value="0">Manual</option>
      <option value="20">20 s</option>
      <option value="30" selected>30 s</option>
      <option value="60">60 s</option>
      <option value="180">3 min</option>
    </select>
  </div>
  <button class="act" id="reload">Actualizar ahora</button>
  <span class="sub" id="countdown"></span>
</div>

<div class="kpis" id="kpis"></div>

<div class="tabs">
  <button data-tab="scores" class="active">Marcadores</button>
  <button data-tab="ats">Spread (ATS)</button>
  <button data-tab="totals">Totales</button>
  <button data-tab="markets">Mercados</button>
  <button data-tab="summary">Resumen</button>
  <button data-tab="method">Metodología</button>
</div>

<section data-panel="scores" class="active">
  <div class="filters" id="filters">
    <button class="f active" data-f="all">Todos</button>
    <button class="f" data-f="in">En vivo</button>
    <button class="f" data-f="pre">Por jugar</button>
    <button class="f" data-f="post">Finalizados</button>
    <button class="f" data-f="close">Cobertura apretada</button>
  </div>
  <div class="games" id="games"></div>
</section>

<section data-panel="ats">
  <div class="card">
    <h3>Probabilidad de cubrir el spread</h3>
    <div class="hint sub">La línea se muestra desde la óptica del equipo local. Haz clic en los encabezados para ordenar.</div>
    <div class="tscroll"><table id="ats-table"></table></div>
  </div>
</section>

<section data-panel="totals">
  <div class="card">
    <h3>Over / Under</h3>
    <div class="tscroll"><table id="totals-table"></table></div>
  </div>
</section>

<section data-panel="markets">
  <div class="card">
    <h3>Polymarket · Kalshi · modelo</h3>
    <div class="hint sub">Probabilidad de que gane el local según cada fuente, el margen que esa
      probabilidad implica y la probabilidad de cubrir que se deriva de él.</div>
    <div class="tscroll"><table id="markets-table"></table></div>
    <div class="sub" id="markets-note" style="margin-top:10px"></div>
  </div>
</section>

<section data-panel="summary">
  <div class="grid2">
    <div class="card"><h3>Cobertura de la jornada</h3><div id="ats-record"></div></div>
    <div class="card"><h3>Mayor diferencia contra el mercado</h3><div class="tscroll"><table id="edge-table"></table></div><div class="sub" id="edge-note" style="margin-top:10px"></div></div>
  </div>
  <div class="card">
    <h3>Probabilidad de cubrir por partido</h3>
    <div class="sub" style="margin-bottom:8px">Lado favorecido por el modelo en cada partido pendiente.
      <span style="color:#00D9FF">■</span> en vivo · <span style="color:#3DD68C">■</span> por jugar</div>
    <div class="chart" id="chart"></div>
  </div>
</section>

<section data-panel="method">
  <div class="card">
    <h2>Cómo se calcula la probabilidad de cubrir</h2>
    <p>El margen final del partido (local menos visitante) se modela como una distribución
    normal cuya media y dispersión se actualizan con cada refresco del marcador:</p>
    <ul>
      <li><b>Media</b> = margen actual + expectativa restante + ajuste por posesión. La
      expectativa restante sale de la línea de cierre: un local de −3.5 tiene una expectativa
      de +3.5 puntos para el partido completo, prorrateada al tiempo que falta.</li>
      <li><b>Dispersión</b> = sigma de partido completo × raíz de la fracción de tiempo
      restante, con un piso para que el final de partido no quede determinista. En tiempo
      extra se usa una sigma reducida y expectativa neutral.</li>
      <li><b>Posesión</b>: tener el balón vale poco al inicio y mucho al final, por lo que el
      ajuste escala con el tiempo ya jugado.</li>
      <li><b>Números clave</b>: la normal subestima los márgenes de 3, 7, 10 y 14 puntos. En
      líneas enteras la probabilidad de <i>push</i> se pondera con esos pesos y el resto se
      reescala para sumar 100 %.</li>
    </ul>
    <p>El total (over/under) usa el mismo esquema sobre la suma de puntos, con su propia sigma.
    La probabilidad de ganar es el mismo cálculo con línea en cero.</p>
    <h3>Contra el mercado</h3>
    <p>Cuando el feed trae momios, se convierten a probabilidad implícita y se les retira la
    comisión repartiéndola entre ambos lados. La columna <i>edge</i> es la diferencia entre la
    probabilidad del modelo y esa probabilidad sin comisión: positiva favorece al local.</p>
    <h3>Mercados de predicción</h3>
    <p>Además de las casas de apuestas, el tablero consulta <b>Polymarket</b> (API Gamma) y
    <b>Kalshi</b> (API pública de mercados). Ambas cotizan al ganador del partido en
    probabilidad directa: Polymarket en dólares por acción y Kalshi en centavos, donde el
    precio medio entre compra y venta es la probabilidad. Los dos lados se normalizan para que
    sumen 100 %.</p>
    <ul>
      <li>Esa probabilidad de victoria se convierte en <b>margen implícito</b> invirtiendo la
      normal del modelo, y de ahí sale la <b>probabilidad de cubrir implícita en el mercado</b>,
      comparable con la del modelo sobre la misma línea.</li>
      <li>El <b>consenso</b> mezcla modelo y mercados con el peso definido en
      <code>consensus.model_weight</code> (0.5 por omisión).</li>
      <li>La <b>divergencia</b> es cuánto se separa el mercado del modelo en la probabilidad de
      que gane el local: es la señal de dónde revisar el partido.</li>
      <li>El emparejamiento entre fuentes se hace por pareja de equipos, con alias de
      abreviatura, así que un mercado sin contraparte en el marcador simplemente se ignora.</li>
    </ul>
    <h3>Datos</h3>
    <p id="method-source">Marcador, situación de campo y líneas provienen de la API pública de
    resultados de ESPN; los logos oficiales, de su CDN de escudos. Todo se consulta
    directamente desde el navegador en cada refresco. Si una fuente falla, las demás siguen
    funcionando y el tablero conserva la última lectura disponible marcándola con asterisco.</p>
    <h3>Límites</h3>
    <ul>
      <li>No modela posición en el campo, downs restantes, tiempos fuera ni lesiones.</li>
      <li>Las líneas del feed suelen ser de cierre, no en vivo: el <i>edge</i> mostrado
      compara un modelo en vivo contra un precio previo al partido.</li>
      <li>Kalshi y Polymarket cotizan al ganador, no al spread: la probabilidad de cubrir que
      se les atribuye es una derivación del modelo, no un precio observado.</li>
      <li>Un mercado con poco volumen puede tener un diferencial amplio; el volumen se muestra
      en la pestaña Mercados para juzgarlo.</li>
      <li>Los pesos de números clave son una calibración heurística, no un ajuste a una
      muestra específica.</li>
    </ul>
    <div class="note"><b>Aviso.</b> Herramienta de análisis estadístico y estudio de líneas.
    No constituye asesoría de apuestas ni recomendación para arriesgar dinero.</div>
  </div>
</section>

<footer id="foot"></footer>
</div>
<script>
"use strict";
var BOOT = __DATA__;
var CFG = BOOT.config || {};
var M = CFG.model || {};
var LIVE = CFG.live || {};
var KEYW = M.key_numbers || {};
var TEAM_META = BOOT.team_meta || {};
var TEAM_ALIASES = BOOT.team_aliases || {};
var TEAMS_ES = BOOT.teams || {};
var ASSETS = CFG.assets || {};
var SOURCES = CFG.sources || {};
var CONSENSUS = CFG.consensus || {};
var ENDPOINT = LIVE.endpoint || "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard";
var LOGO_TEMPLATE = ASSETS.logo_template || "https://a.espncdn.com/i/teamlogos/nfl/500/{abbr}.png";

function canonicalAbbr(abbr) {
  var a = String(abbr || "").toUpperCase().trim();
  return TEAM_ALIASES[a] || a;
}
function logoUrl(abbr) {
  return LOGO_TEMPLATE.replace("{abbr}", canonicalAbbr(abbr).toLowerCase());
}
function luminance(hex) {
  var h = String(hex || "").replace("#", "");
  if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
  if (h.length !== 6) return 0.5;
  var v = [0, 2, 4].map(function (i) {
    var c = parseInt(h.substr(i, 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2];
}
function hexToRgb(hex) {
  var h = String(hex || "").replace("#", "");
  if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
  if (h.length !== 6) return [30, 39, 97];
  return [0, 2, 4].map(function (i) { return parseInt(h.substr(i, 2), 16); });
}
function rgbToHex(rgb) {
  return "#" + rgb.map(function (v) {
    var s = Math.max(0, Math.min(255, Math.round(v))).toString(16);
    return s.length < 2 ? "0" + s : s;
  }).join("");
}
function mix(hex, target, amount) {
  var a = hexToRgb(hex), b = hexToRgb(target);
  return rgbToHex([0, 1, 2].map(function (i) { return a[i] + (b[i] - a[i]) * amount; }));
}
/* Varios primarios oficiales son casi negros (Raiders, Bears, Patriots) y algún
   secundario es blanco puro: sobre el fondo oscuro del tablero hay que llevar el
   color a un rango visible sin perder la identidad del equipo. */
function displayColor(team) {
  var primary = team.color || "#1E2761", alt = team.alt_color || "";
  var candidates = [primary, alt].filter(function (c) { return c; });
  for (var i = 0; i < candidates.length; i++) {
    var l = luminance(candidates[i]);
    if (l >= 0.06 && l <= 0.75) return candidates[i];
  }
  var base = primary;
  if (luminance(base) > 0.75) return mix(base, "#000000", 0.25);
  var out = base;
  for (var step = 0; step < 4 && luminance(out) < 0.06; step++) out = mix(out, "#FFFFFF", 0.22);
  return out;
}
function textOn(hex) { return luminance(hex) > 0.28 ? "#0A1438" : "#FFFFFF"; }

var S = {
  games: BOOT.games || [],
  meta: BOOT.meta || {},
  summary: BOOT.summary || {},
  source: BOOT.source || "demo",
  quotes: BOOT.quotes || [],
  quotesAt: BOOT.generated_at || "",
  sourceStatus: { espn: { ok: false, detail: "sin consultar" },
                  polymarket: { ok: false, detail: "sin consultar" },
                  kalshi: { ok: false, detail: "sin consultar" } },
  updated: BOOT.generated_at || "",
  online: false,
  error: "",
  loading: false,
  filter: "all",
  sort: { key: "state", dir: 1 },
  nextIn: 0
};

/* ---------------------------------------------------------------- modelo */
function erf(x) {
  var s = x < 0 ? -1 : 1; x = Math.abs(x);
  var t = 1 / (1 + 0.3275911 * x);
  var y = 1 - ((((1.061405429 * t - 1.453152027) * t + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * Math.exp(-x * x);
  return s * y;
}
function normCdf(z) { return 0.5 * (1 + erf(z / Math.SQRT2)); }
function normPdf(x, mu, s) { if (s <= 0) return 0; var z = (x - mu) / s; return Math.exp(-0.5 * z * z) / (s * Math.sqrt(2 * Math.PI)); }
function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }
function invNormCdf(p) {
  if (p <= 0) return -8; if (p >= 1) return 8;
  var a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
    1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00];
  var b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
    6.680131188771972e+01, -1.328068155288572e+01];
  var c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
    -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00];
  var d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
    3.754408661907416e+00];
  var plow = 0.02425, phigh = 1 - plow, q, r;
  if (p < plow) {
    q = Math.sqrt(-2 * Math.log(p));
    return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) /
      ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1);
  }
  if (p > phigh) {
    q = Math.sqrt(-2 * Math.log(1 - p));
    return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) /
      ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1);
  }
  q = p - 0.5; r = q * q;
  return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q /
    (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1);
}
function impliedMargin(pHomeWin, sigma) { return sigma * invNormCdf(clamp(pHomeWin, 0.001, 0.999)); }
function keyMultiplier(k) {
  var key = String(Math.abs(Math.round(k)));
  var w = KEYW[key];
  if (w === undefined) w = KEYW["default"];
  return w === undefined ? 0.9 : w;
}
function outcomeProbabilities(k, mu, sigma, maxPush) {
  if (maxPush === undefined) maxPush = 0.35;
  if (sigma <= 1e-9) {
    if (k > mu + 1e-9) return [0, 0, 1];
    if (k < mu - 1e-9) return [1, 0, 0];
    return [0, 1, 0];
  }
  var isPushLine = Math.abs(k - Math.round(k)) < 1e-9;
  if (!isPushLine) {
    var p = 1 - normCdf((k - mu) / sigma);
    return [clamp(p, 0, 1), 0, clamp(1 - p, 0, 1)];
  }
  var push = clamp(normPdf(k, mu, sigma) * keyMultiplier(k), 0, maxPush);
  var over = 1 - normCdf((k + 0.5 - mu) / sigma);
  var under = normCdf((k - 0.5 - mu) / sigma);
  var rest = over + under;
  if (rest <= 1e-12) return [0, 1, 0];
  var sc = (1 - push) / rest;
  return [clamp(over * sc, 0, 1), push, clamp(under * sc, 0, 1)];
}
function timeRemaining(state, period, clockSeconds, halftime) {
  if (state === "pre") return [3600, 1];
  if (state === "post") return [0, 0];
  if (halftime) return [1800, 0.5];
  if (period >= 5) return [Math.max(clockSeconds, 0), 0];
  var p = Math.max(1, Math.min(4, period || 1));
  var rem = (4 - p) * 900 + Math.max(0, Math.min(900, clockSeconds || 0));
  return [rem, clamp(rem / 3600, 0, 1)];
}
function americanToProb(o) {
  if (o === null || o === undefined || o === "") return null;
  var v = parseFloat(o);
  if (!isFinite(v) || v === 0) return null;
  return v < 0 ? (-v) / ((-v) + 100) : 100 / (v + 100);
}
function devig(a, b) {
  if (a === null || b === null || (a + b) <= 0) return [a, b];
  return [a / (a + b), b / (a + b)];
}
function evaluateGame(g) {
  var sigmaFull = M.sigma_full_game || 13.2, sigmaFloor = M.sigma_floor || 1.4;
  var sigmaOt = M.sigma_overtime || 5.5, possEdge = M.possession_points || 1.1;
  var sigmaTotal = M.sigma_total || 10.6, defTotal = M.default_total || 44;
  var state = g.state || "pre";
  var marginNow = (g.home_score || 0) - (g.away_score || 0);
  var totalNow = (g.home_score || 0) + (g.away_score || 0);
  var tr = timeRemaining(state, g.period || 0, g.clock_seconds || 0, !!g.halftime);
  var rem = tr[0], frac = tr[1];
  var line = (g.line_home === null || g.line_home === undefined) ? null : parseFloat(g.line_home);
  var mu, sigma;
  if (state === "post") { mu = marginNow; sigma = 0; }
  else if (state === "in" && (g.period || 0) >= 5) {
    sigma = Math.max(sigmaFloor, sigmaOt * Math.sqrt(clamp(Math.max(rem, 60) / 600, 0.05, 1)));
    mu = marginNow;
  } else {
    sigma = Math.max(sigmaFloor, sigmaFull * Math.sqrt(frac));
    mu = marginNow + (line === null ? 0 : -line) * frac;
  }
  if (state === "in" && (g.possession_home === true || g.possession_home === false)) {
    mu += (possEdge * (1 - frac)) * (g.possession_home ? 1 : -1);
  }
  var out = {
    margin_now: marginNow, total_now: totalNow,
    projected_margin: Math.round(mu * 10) / 10, sigma: Math.round(sigma * 100) / 100,
    remaining_seconds: rem, fraction_remaining: frac
  };
  if (line !== null && isFinite(line)) {
    var r = outcomeProbabilities(-line, mu, sigma);
    out.p_home_cover = r[0]; out.p_push = r[1]; out.p_away_cover = r[2];
    out.cover_margin_now = Math.round((marginNow + line) * 10) / 10;
    if (state === "post") {
      var e = marginNow + line;
      out.ats_result = e > 0 ? "home" : (e < 0 ? "away" : "push");
    }
  }
  var w = outcomeProbabilities(0, mu, sigma, 0.02);
  out.p_home_win = w[0]; out.p_tie = w[1]; out.p_away_win = w[2];

  var lineTotal = (g.line_total === null || g.line_total === undefined) ? null : parseFloat(g.line_total);
  var muT = state === "post" ? totalNow : totalNow + (lineTotal === null ? defTotal : lineTotal) * frac;
  var sigT = state === "post" ? 0 : Math.max(sigmaFloor, sigmaTotal * Math.sqrt(frac));
  out.projected_total = Math.round(muT * 10) / 10;
  if (lineTotal !== null && isFinite(lineTotal)) {
    var t = outcomeProbabilities(lineTotal, muT, sigT);
    out.p_over = t[0]; out.p_total_push = t[1]; out.p_under = t[2];
    if (state === "post") out.total_result = totalNow > lineTotal ? "over" : (totalNow < lineTotal ? "under" : "push");
  }
  var markets = g.markets || {};
  var marketWins = [];
  ["polymarket", "kalshi"].forEach(function (src) {
    var node = markets[src];
    if (!node || node.p_home_win === null || node.p_home_win === undefined) return;
    var pWin = clamp(Number(node.p_home_win), 0, 1);
    marketWins.push(pWin);
    if (sigma > 0) {
      var muM = impliedMargin(pWin, sigma);
      node.implied_margin = Math.round(muM * 10) / 10;
      if (line !== null && isFinite(line)) {
        var rm = outcomeProbabilities(-line, muM, sigma);
        node.p_home_cover = rm[0]; node.p_push = rm[1]; node.p_away_cover = rm[2];
      }
    }
  });
  if (marketWins.length) {
    var wModel = clamp(CONSENSUS.model_weight === undefined ? 0.5 : Number(CONSENSUS.model_weight), 0, 1);
    var marketWin = marketWins.reduce(function (a, b) { return a + b; }, 0) / marketWins.length;
    out.market_win_consensus = marketWin;
    out.market_divergence = marketWin - out.p_home_win;
    out.consensus_home_win = wModel * out.p_home_win + (1 - wModel) * marketWin;
    var covers = Object.keys(markets).map(function (k) { return markets[k].p_home_cover; })
      .filter(function (v) { return v !== undefined && v !== null; });
    if (covers.length && out.p_home_cover !== undefined) {
      var marketCover = covers.reduce(function (a, b) { return a + b; }, 0) / covers.length;
      out.market_cover_consensus = marketCover;
      out.consensus_home_cover = wModel * out.p_home_cover + (1 - wModel) * marketCover;
    }
  }

  var mk = devig(americanToProb(g.home_spread_odds), americanToProb(g.away_spread_odds));
  if (mk[0] !== null && out.p_home_cover !== undefined && state !== "post") {
    out.market_home_cover = mk[0];
    out.edge_home_cover = (out.p_home_cover / Math.max(1e-9, 1 - (out.p_push || 0))) - mk[0];
  }
  var ml = devig(americanToProb(g.home_moneyline), americanToProb(g.away_moneyline));
  if (ml[0] !== null) { out.market_home_win = ml[0]; out.market_away_win = ml[1]; }
  g.probs = out;
  return g;
}

/* --------------------------------------------------- lectura del feed */
function clockToSeconds(txt) {
  if (!txt) return 0;
  txt = String(txt).trim();
  if (txt.indexOf(":") < 0) { var n = parseFloat(txt); return isFinite(n) ? Math.round(n) : 0; }
  var parts = txt.split(":");
  var mm = parseFloat(parts[0]), ss = parseFloat(parts[1]);
  if (!isFinite(mm) || !isFinite(ss)) return 0;
  return Math.round(mm * 60 + ss);
}
function firstNumber(text) {
  var toks = String(text).replace(/[()]/g, " ").split(/\s+/);
  for (var i = 0; i < toks.length; i++) { var v = parseFloat(toks[i]); if (isFinite(v)) return v; }
  return null;
}
function parseSpread(odds, homeAbbr, awayAbbr) {
  if (!odds) return [null, null];
  var details = (odds.details || "").trim();
  var display = details || null;
  if (details) {
    var up = details.toUpperCase().replace(/'/g, "");
    if (["EVEN", "PK", "PICK", "PICKEM", "PICK EM"].indexOf(up) >= 0) return [0, display];
    var value = firstNumber(up);
    if (value !== null) {
      var toks = up.split(/\s+/).map(function (t) { return t.replace(/[:,]/g, ""); });
      if (homeAbbr && toks.indexOf(homeAbbr.toUpperCase()) >= 0) return [value, display];
      if (awayAbbr && toks.indexOf(awayAbbr.toUpperCase()) >= 0) return [-value, display];
    }
  }
  var sides = [[odds.homeTeamOdds || {}, 1], [odds.awayTeamOdds || {}, -1]];
  for (var s = 0; s < sides.length; s++) {
    var close = ((sides[s][0].close || {}).pointSpread) || {};
    var raw = close.line || close.alternateDisplayValue || close.american;
    if (raw !== undefined && raw !== null && raw !== "") {
      var num = parseFloat(String(raw).replace("+", ""));
      if (isFinite(num)) return [num * sides[s][1], display || String(raw)];
    }
  }
  if (odds.spread !== undefined && odds.spread !== null) {
    var sp = parseFloat(odds.spread);
    if (!isFinite(sp)) return [null, display];
    if ((odds.homeTeamOdds || {}).favorite === true) return [-Math.abs(sp), display];
    if ((odds.awayTeamOdds || {}).favorite === true) return [Math.abs(sp), display];
    return [sp, display];
  }
  return [null, display];
}
function pickOdds(node, keys) {
  if (!node) return null;
  var cands = [node[keys[0]], ((node.close || {})[keys[1]] || {}).american];
  if (keys[1] === "pointSpread") cands[1] = ((node.close || {}).pointSpread || {}).american;
  for (var i = 0; i < cands.length; i++) {
    var raw = cands[i];
    if (raw === undefined || raw === null || raw === "" || raw === "OFF") continue;
    var v = parseFloat(String(raw).replace("+", ""));
    if (isFinite(v)) return v;
  }
  return null;
}
function competitor(comp, side) {
  var cs = comp.competitors || [];
  for (var i = 0; i < cs.length; i++) if (cs[i].homeAway === side) return cs[i];
  return {};
}
function teamBlock(c) {
  var t = c.team || {};
  var abbr = (t.abbreviation || "").toUpperCase();
  var rec = "";
  var recs = c.records || [];
  for (var i = 0; i < recs.length; i++) {
    if (recs[i].type === "total" || recs[i].name === "overall" || !recs[i].type) { rec = recs[i].summary || ""; break; }
  }
  var key = canonicalAbbr(abbr);
  var meta = TEAM_META[key] || {};
  var feed = t.color ? (t.color.charAt(0) === "#" ? t.color : "#" + t.color) : "";
  var feedAlt = t.alternateColor ? (t.alternateColor.charAt(0) === "#" ? t.alternateColor : "#" + t.alternateColor) : "";
  return {
    id: String(t.id || ""), abbr: key || abbr,
    name: t.displayName || t.name || abbr,
    short: t.shortDisplayName || t.name || abbr,
    location: t.location || "",
    color: meta.primary || feed || "#1E2761",
    alt_color: meta.secondary || feedAlt || "#8895B3",
    logo: t.logo || logoUrl(key || abbr),
    record: rec
  };
}
function parseEvent(ev) {
  var comps = ev.competitions || [];
  if (!comps.length) return null;
  var comp = comps[0];
  var homeC = competitor(comp, "home"), awayC = competitor(comp, "away");
  var status = ev.status || comp.status || {};
  var stype = status.type || {};
  var state = stype.state || "pre";
  var name = (stype.name || "").toUpperCase();
  var home = teamBlock(homeC), away = teamBlock(awayC);
  var oddsList = comp.odds || [];
  var odds = oddsList.length ? oddsList[0] : {};
  var sp = parseSpread(odds, home.abbr, away.abbr);
  var ou = odds.overUnder !== undefined && odds.overUnder !== null ? parseFloat(odds.overUnder) : null;
  var situation = comp.situation || {};
  var possId = String(situation.possession || "");
  var possHome = null;
  if (state === "in" && possId) {
    if (possId === home.id) possHome = true; else if (possId === away.id) possHome = false;
  }
  var broadcast = "";
  var bs = comp.broadcasts || [];
  for (var i = 0; i < bs.length; i++) { if ((bs[i].names || []).length) { broadcast = bs[i].names[0]; break; } }
  var lastPlay = situation.lastPlay && situation.lastPlay.text ? situation.lastPlay.text : "";
  return {
    id: String(ev.id || comp.id || ""),
    date: ev.date || comp.date || "",
    name: ev.shortName || ev.name || "",
    state: state,
    status_detail: stype.detail || "",
    status_short: stype.shortDetail || "",
    completed: !!stype.completed,
    halftime: name === "STATUS_HALFTIME" || String(stype.description || "").toLowerCase() === "halftime",
    period: parseInt(status.period || 0, 10) || 0,
    clock: status.displayClock || "",
    clock_seconds: clockToSeconds(status.displayClock),
    home: home, away: away,
    home_score: parseInt(homeC.score || 0, 10) || 0,
    away_score: parseInt(awayC.score || 0, 10) || 0,
    line_home: sp[0], line_display: sp[1],
    line_total: isFinite(ou) ? ou : null,
    odds_provider: (odds.provider || {}).name || "",
    home_moneyline: pickOdds(odds.homeTeamOdds, ["moneyLine", "moneyLine"]),
    away_moneyline: pickOdds(odds.awayTeamOdds, ["moneyLine", "moneyLine"]),
    home_spread_odds: pickOdds(odds.homeTeamOdds, ["spreadOdds", "pointSpread"]),
    away_spread_odds: pickOdds(odds.awayTeamOdds, ["spreadOdds", "pointSpread"]),
    possession_home: possHome,
    down_distance: situation.downDistanceText || "",
    possession_text: situation.possessionText || "",
    red_zone: !!situation.isRedZone,
    last_play: lastPlay,
    venue: (comp.venue || {}).fullName || "",
    broadcast: broadcast,
    neutral_site: !!comp.neutralSite
  };
}
function summarize(games) {
  var finals = games.filter(function (g) { return g.state === "post"; });
  var ats = { home: 0, away: 0, push: 0 }, fav = 0, dog = 0, over = 0, under = 0, pts = 0;
  games.forEach(function (g) { pts += (g.home_score || 0) + (g.away_score || 0); });
  finals.forEach(function (g) {
    var p = g.probs || {};
    if (ats[p.ats_result] !== undefined) ats[p.ats_result]++;
    if (p.total_result === "over") over++; else if (p.total_result === "under") under++;
    var line = g.line_home;
    if ((p.ats_result === "home" || p.ats_result === "away") && line !== null && line !== undefined && line !== 0) {
      if ((p.ats_result === "home") === (line < 0)) fav++; else dog++;
    }
  });
  var decided = ats.home + ats.away;
  return {
    games: games.length,
    live: games.filter(function (g) { return g.state === "in"; }).length,
    final: finals.length,
    scheduled: games.filter(function (g) { return g.state === "pre"; }).length,
    ats_home: ats.home, ats_away: ats.away, ats_push: ats.push,
    ats_home_pct: decided ? Math.round(1000 * ats.home / decided) / 10 : null,
    favorites_covered: fav, underdogs_covered: dog,
    favorites_pct: (fav + dog) ? Math.round(1000 * fav / (fav + dog)) / 10 : null,
    totals_over: over, totals_under: under,
    points: pts,
    with_line: games.filter(function (g) { return g.line_home !== null && g.line_home !== undefined; }).length
  };
}

/* ------------------------------- mercados de predicción (PM · Kalshi) */
var NAME_TO_ABBR = (function () {
  var out = {};
  Object.keys(TEAMS_ES).forEach(function (abbr) {
    var loc = TEAMS_ES[abbr][0], nick = TEAMS_ES[abbr][1];
    out[nick.toUpperCase()] = abbr;
    out[(loc + " " + nick).toUpperCase()] = abbr;
    out[loc.toUpperCase()] = abbr;
    out[abbr] = abbr;
  });
  Object.keys(TEAM_ALIASES).forEach(function (a) { out[a] = TEAM_ALIASES[a]; });
  delete out["LOS ANGELES"]; delete out["NEW YORK"];   /* ciudades compartidas */
  return out;
})();
function abbrFromText(text) {
  if (!text) return null;
  var up = String(text).toUpperCase().trim();
  if (NAME_TO_ABBR[up]) return NAME_TO_ABBR[up];
  var names = Object.keys(NAME_TO_ABBR);
  for (var i = 0; i < names.length; i++) {
    if (names[i].length > 3 && up.indexOf(names[i]) >= 0) return NAME_TO_ABBR[names[i]];
  }
  var toks = up.replace(/-/g, " ").split(/\s+/).map(function (t) { return t.replace(/^[.,_-]+|[.,_-]+$/g, ""); });
  for (var j = 0; j < toks.length; j++) if (NAME_TO_ABBR[toks[j]]) return NAME_TO_ABBR[toks[j]];
  return null;
}
function asList(value) {
  if (Array.isArray(value)) return value;
  if (typeof value === "string" && value.trim().charAt(0) === "[") {
    try { return JSON.parse(value); } catch (e) { return []; }
  }
  return [];
}
function parsePolymarket(payload) {
  var events = Array.isArray(payload) ? payload : ((payload || {}).events || []);
  var quotes = [];
  events.forEach(function (ev) {
    var markets = ev.markets || (ev.outcomes ? [ev] : []);
    markets.forEach(function (mk) {
      var kind = String(mk.sportsMarketType || "").toLowerCase();
      if (kind && kind !== "winner" && kind !== "moneyline") return;
      var outcomes = asList(mk.outcomes), prices = asList(mk.outcomePrices);
      if (outcomes.length !== 2) return;
      var teams = {};
      outcomes.forEach(function (label, i) {
        var abbr = abbrFromText(label), price = parseFloat(prices[i]);
        if (abbr && isFinite(price)) teams[abbr] = clamp(price, 0, 1);
      });
      if (Object.keys(teams).length !== 2) {
        var slugAbbrs = String(mk.slug || ev.slug || "").split("-").map(abbrFromText)
          .filter(function (a) { return a; });
        var uniq = slugAbbrs.filter(function (a, i) { return slugAbbrs.indexOf(a) === i; });
        if (uniq.length === 2 && prices.length === 2 && isFinite(parseFloat(prices[0]))) {
          teams = {}; teams[uniq[0]] = clamp(parseFloat(prices[0]), 0, 1);
          teams[uniq[1]] = clamp(parseFloat(prices[1]), 0, 1);
        }
      }
      if (Object.keys(teams).length !== 2) return;
      quotes.push({
        source: "polymarket",
        id: mk.slug || ev.slug || String(mk.id || ""),
        title: mk.question || ev.title || "",
        teams: teams,
        volume: parseFloat(mk.volume || ev.volume || 0) || 0,
        start: mk.gameStartTime || ev.startDate || "",
        closed: !!(mk.closed || ev.closed)
      });
    });
  });
  return quotes;
}
function kalshiPrice(mk) {
  var bid = parseFloat(mk.yes_bid), ask = parseFloat(mk.yes_ask);
  if (isFinite(bid) && isFinite(ask) && ask > 0) return clamp((bid + ask) / 200, 0, 1);
  var last = parseFloat(mk.last_price);
  if (isFinite(last)) return clamp(last / 100, 0, 1);
  var prev = parseFloat(mk.previous_price);
  return isFinite(prev) ? clamp(prev / 100, 0, 1) : null;
}
function parseKalshi(payload) {
  var markets = (payload || {}).markets || [];
  var byEvent = {};
  markets.forEach(function (mk) {
    var ticker = String(mk.ticker || "");
    var eventTicker = String(mk.event_ticker || ticker.split("-").slice(0, -1).join("-"));
    var price = kalshiPrice(mk);
    if (price === null) return;
    var abbr = null, parts = ticker.split("-");
    if (parts.length >= 3) {
      var cand = canonicalAbbr(parts[parts.length - 1]);
      if (TEAM_META[cand]) abbr = cand;
    }
    if (!abbr) abbr = abbrFromText(mk.yes_sub_title || mk.title || "");
    if (!abbr) return;
    if (!byEvent[eventTicker]) {
      byEvent[eventTicker] = {
        source: "kalshi", id: eventTicker, title: mk.title || "", teams: {}, volume: 0,
        start: mk.open_time || "",
        closed: ["open", "active"].indexOf(String(mk.status || "")) < 0
      };
    }
    byEvent[eventTicker].teams[abbr] = price;
    byEvent[eventTicker].volume += parseFloat(mk.volume || 0) || 0;
  });
  return Object.keys(byEvent).map(function (k) { return byEvent[k]; })
    .filter(function (q) { return Object.keys(q.teams).length === 2; });
}
function normalizeQuote(teams) {
  var total = Object.keys(teams).reduce(function (a, k) { return a + teams[k]; }, 0);
  if (total <= 0) return teams;
  var out = {};
  Object.keys(teams).forEach(function (k) { out[k] = teams[k] / total; });
  return out;
}
function attachMarkets(games, quotes) {
  games.forEach(function (g) {
    var pair = [g.home.abbr, g.away.abbr].sort().join("|");
    g.markets = {};
    (quotes || []).forEach(function (q) {
      if (q.closed) return;
      if (Object.keys(q.teams).sort().join("|") !== pair) return;
      var prev = g.markets[q.source];
      if (prev && (prev.volume || 0) >= (q.volume || 0)) return;
      var norm = normalizeQuote(q.teams);
      g.markets[q.source] = {
        id: q.id || "", title: q.title || "",
        p_home_win: norm[g.home.abbr], p_away_win: norm[g.away.abbr],
        raw_home: q.teams[g.home.abbr], volume: q.volume || 0, stale: !!q.stale
      };
    });
  });
}

/* ------------------------------------------------------------- formato */
function $(id) { return document.getElementById(id); }
function esc(s) {
  return String(s === null || s === undefined ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
function pct(p, nd) {
  if (p === null || p === undefined || !isFinite(p)) return "—";
  return (100 * p).toFixed(nd === undefined ? 1 : nd) + " %";
}
function signed(v, nd) {
  if (v === null || v === undefined || !isFinite(v)) return "—";
  var d = nd === undefined ? 1 : nd;
  var x = Number(v);
  if (Math.abs(x) < 0.5 / Math.pow(10, d)) x = 0;
  return (x > 0 ? "+" : "") + x.toFixed(d);
}
function lineLabel(g, side) {
  var l = g.line_home;
  if (l === null || l === undefined || !isFinite(l)) return "s/línea";
  var v = side === "home" ? l : -l;
  if (v === 0) return "PK";
  return (v > 0 ? "+" : "") + v.toFixed(1);
}
function kickoff(iso) {
  if (!iso) return "";
  var d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  return d.toLocaleString("es-MX", { weekday: "short", day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
}
function statusText(g) {
  if (g.state === "post") return g.status_detail || "Final";
  if (g.state === "pre") return kickoff(g.date) || (g.status_detail || "Programado");
  if (g.halftime) return "Medio tiempo";
  if ((g.period || 0) >= 5) return "TE " + (g.clock || "");
  return "Q" + (g.period || 1) + " " + (g.clock || "");
}
function probClass(p) { return p >= 0.6 ? "green" : (p <= 0.4 ? "rose" : "amber"); }
function teamCrest(t, size) {
  var color = displayColor(t), abbr = esc(t.abbr || "");
  var cls = "crest" + (size === "sm" ? " sm" : "");
  if (ASSETS.logos === false) {
    return '<span class="' + cls + ' fallback" style="background:' + esc(color) + ";color:" + textOn(color) +
      '">' + abbr + "</span>";
  }
  return '<img class="' + cls + '" src="' + esc(t.logo || logoUrl(t.abbr)) + '" alt="' + esc(t.name || t.abbr) +
    '" loading="lazy" data-abbr="' + abbr + '" data-color="' + esc(color) + '">';
}
/* Si el CDN de logos no está disponible (offline o red restringida) se
   sustituye la imagen por un escudo con los colores oficiales del equipo. */
function wireLogos() {
  var imgs = document.querySelectorAll("img.crest");
  Array.prototype.forEach.call(imgs, function (img) {
    if (img.dataset.wired) return;
    img.dataset.wired = "1";
    img.addEventListener("error", function () {
      var span = document.createElement("span");
      var bg = img.dataset.color || "#1E2761";
      span.className = img.className + " fallback";
      span.style.background = bg;
      span.style.color = textOn(bg);
      span.textContent = img.dataset.abbr || "";
      if (img.parentNode) img.parentNode.replaceChild(span, img);
    }, { once: true });
  });
}
function centsChip(label, p, cls) {
  return '<span class="mk ' + (cls || "") + '">' + esc(label) + " <b>" + pct(p, 0) + "</b></span>";
}
function downDistance(txt) {
  if (!txt) return "";
  return String(txt)
    .replace(/\b1st\b/g, "1ro").replace(/\b2nd\b/g, "2do")
    .replace(/\b3rd\b/g, "3ro").replace(/\b4th\b/g, "4to")
    .replace(/\s&\s/g, " y ").replace(/\bat\b/g, "en")
    .replace(/\bGoal\b/gi, "Gol");
}

/* -------------------------------------------------------------- render */
function renderKpis() {
  var s = S.summary || {};
  var liveCover = S.games.filter(function (g) {
    var p = g.probs || {};
    return g.state === "in" && p.p_home_cover !== undefined &&
      Math.max(p.p_home_cover, p.p_away_cover) < 0.65;
  }).length;
  var html = "";
  html += kpi("Partidos", s.games || 0, (s.live || 0) + " en vivo · " + (s.final || 0) + " finales · " + (s.scheduled || 0) + " por jugar", "");
  html += kpi("Locales ATS", (s.ats_home || 0) + "-" + (s.ats_away || 0) + (s.ats_push ? "-" + s.ats_push : ""),
    s.ats_home_pct === null || s.ats_home_pct === undefined ? "Sin partidos cerrados" : "Los locales cubren el " + s.ats_home_pct + " %", "amber");
  html += kpi("Favoritos que cubren", s.favorites_pct === null || s.favorites_pct === undefined ? "—" : s.favorites_pct + " %",
    (s.favorites_covered || 0) + " favoritos · " + (s.underdogs_covered || 0) + " no favoritos", "green");
  html += kpi("Coberturas abiertas", liveCover, "Partidos en vivo con el spread aún indefinido (< 65 %)", "");
  $("kpis").innerHTML = html;
}
function kpi(lbl, val, foot, cls) {
  return '<div class="kpi"><div class="lbl">' + esc(lbl) + '</div><div class="val ' + (cls || "") + '">' +
    esc(val) + '</div><div class="foot">' + esc(foot) + "</div></div>";
}

function teamRow(g, side) {
  var t = g[side], p = g.probs || {};
  var score = side === "home" ? g.home_score : g.away_score;
  var other = side === "home" ? g.away_score : g.home_score;
  var cls = "trow";
  if (g.state !== "pre") cls += score > other ? " win" : (score < other ? " loser" : "");
  var ball = (g.state === "in" && g.possession_home !== null && g.possession_home !== undefined &&
    (g.possession_home === (side === "home"))) ? "●" : "";
  var sub = [t.record || "", side === "home" ? "local" : "visitante", lineLabel(g, side)]
    .filter(function (x) { return x; }).join(" · ");
  return '<div class="' + cls + '">' + teamCrest(t) +
    '<div class="nm">' + esc(t.name || t.abbr) + "<small>" + esc(sub) + "</small></div>" +
    '<div class="ball">' + ball + "</div>" +
    '<div class="sc">' + (g.state === "pre" ? "—" : esc(score)) + "</div></div>";
}
function probRow(label, p, cls) {
  var w = Math.max(0, Math.min(100, 100 * (p || 0)));
  return '<div class="prow"><span class="who">' + esc(label) + '</span>' +
    '<span class="bar"><i class="' + cls + '" style="width:' + w.toFixed(1) + '%"></i></span>' +
    '<span class="pct">' + pct(p) + "</span></div>";
}
function gameCard(g) {
  var p = g.probs || {};
  var tag = g.state === "in"
    ? '<span class="tag live"><i></i>' + esc(statusText(g)) + "</span>"
    : (g.state === "post" ? '<span class="tag post">' + esc(statusText(g)) + "</span>"
      : '<span class="tag pre">' + esc(statusText(g)) + "</span>");
  if (g.state === "in" && g.red_zone) tag += ' <span class="tag rz">Zona roja</span>';

  var meta = [g.broadcast, g.venue].filter(function (x) { return x; }).join(" · ");
  var html = '<article class="game' + (g.state === "in" ? " islive" : "") + '">';
  html += '<div class="teamstrip"><i style="background:' + esc(displayColor(g.away)) + '"></i>' +
    '<i style="background:' + esc(displayColor(g.home)) + '"></i></div>';
  html += '<div class="ghead">' + tag + "<span>" + esc(meta) + "</span></div>";
  html += '<div class="teams">' + teamRow(g, "away") + teamRow(g, "home") + "</div>";

  var lineTxt = (g.line_home === null || g.line_home === undefined)
    ? "Sin línea publicada"
    : "Línea local <b>" + esc(lineLabel(g, "home")) + "</b>";
  html += '<div class="lines"><span>' + lineTxt + "</span>";
  if (g.line_total !== null && g.line_total !== undefined) html += "<span>Total <b>" + Number(g.line_total).toFixed(1) + "</b></span>";
  if (g.odds_provider) html += "<span>" + esc(g.odds_provider) + "</span>";
  html += "</div>";

  if (p.p_home_cover !== undefined) {
    if (g.state === "post") {
      var res = p.ats_result;
      var winner = res === "home" ? g.home.abbr : (res === "away" ? g.away.abbr : "");
      var pill = res === "push" ? '<span class="pill push">Push</span>'
        : '<span class="pill ok">Cubre ' + esc(winner) + "</span>";
      html += '<div class="res">' + pill +
        '<span class="sub">Margen vs línea <b class="num">' + signed(p.cover_margin_now) + "</b></span></div>";
      if (p.total_result) {
        html += '<div class="res"><span class="pill ' + (p.total_result === "over" ? "ok" : (p.total_result === "under" ? "no" : "push")) +
          '">' + (p.total_result === "over" ? "Over" : p.total_result === "under" ? "Under" : "Push total") +
          '</span><span class="sub">' + p.total_now + " pts vs " + Number(g.line_total).toFixed(1) + "</span></div>";
      }
    } else {
      html += '<div class="probs">' +
        probRow(g.away.abbr + " " + lineLabel(g, "away"), p.p_away_cover, probClass(p.p_away_cover)) +
        probRow(g.home.abbr + " " + lineLabel(g, "home"), p.p_home_cover, probClass(p.p_home_cover)) +
        (p.p_push > 0.005 ? probRow("Push", p.p_push, "amber") : "") + "</div>";
      var proj = "<span>Margen proyectado <b>" + signed(p.projected_margin) + "</b></span>";
      proj += "<span>Total proyectado <b>" + Number(p.projected_total).toFixed(1) + "</b></span>";
      if (p.p_over !== undefined) proj += "<span>Over <b>" + pct(p.p_over, 0) + "</b></span>";
      if (p.edge_home_cover !== undefined) proj += "<span>Edge local <b>" + signed(100 * p.edge_home_cover, 1) + " pp</b></span>";
      html += '<div class="proj">' + proj + "</div>";
    }
  } else {
    html += '<div class="proj"><span>Sin línea: sólo marcador y proyección <b>' + signed(p.projected_margin) + "</b></span></div>";
  }

  var mkeys = Object.keys(g.markets || {});
  if (mkeys.length) {
    var chips = mkeys.map(function (src) {
      var node = g.markets[src];
      var label = (src === "polymarket" ? "Polymarket" : "Kalshi") + " · " + g.home.abbr;
      return centsChip(label + (node.stale ? " *" : ""), node.p_home_win, src);
    });
    if (p.consensus_home_cover !== undefined) {
      chips.push(centsChip("Consenso cubre " + g.home.abbr, p.consensus_home_cover, "cons"));
    }
    html += '<div class="mkts">' + chips.join("") + "</div>";
  }

  if (g.state === "in") {
    var bits = [];
    if (g.down_distance) bits.push("<b>" + esc(downDistance(g.down_distance)) + "</b>");
    if (g.possession_home !== null && g.possession_home !== undefined) {
      bits.push("Balón: <b>" + esc(g.possession_home ? g.home.abbr : g.away.abbr) + "</b>");
    }
    if (g.last_play) bits.push(esc(g.last_play));
    if (bits.length) html += '<div class="situ">' + bits.join(" · ") + "</div>";
  }
  html += "</article>";
  return html;
}
function passesFilter(g) {
  if (S.filter === "all") return true;
  if (S.filter === "close") {
    var p = g.probs || {};
    return g.state !== "post" && p.p_home_cover !== undefined && Math.max(p.p_home_cover, p.p_away_cover) < 0.65;
  }
  return g.state === S.filter;
}
function renderGames() {
  var list = S.games.filter(passesFilter);
  $("games").innerHTML = list.length
    ? list.map(gameCard).join("")
    : '<div class="empty">No hay partidos con este filtro.</div>';
  wireLogos();
}

function sortGames(list) {
  var k = S.sort.key, dir = S.sort.dir;
  var val = function (g) {
    var p = g.probs || {};
    switch (k) {
      case "game": return (g.away.abbr || "") + (g.home.abbr || "");
      case "state": return { "in": 0, pre: 1, post: 2 }[g.state];
      case "line": return g.line_home === null || g.line_home === undefined ? 99 : g.line_home;
      case "cover": return (p.cover_margin_now === undefined || g.state === "pre") ? -99 : p.cover_margin_now;
      case "phome": return p.p_home_cover === undefined ? -1 : p.p_home_cover;
      case "paway": return p.p_away_cover === undefined ? -1 : p.p_away_cover;
      case "push": return p.p_push || 0;
      case "proj": return p.projected_margin;
      case "edge": return p.edge_home_cover === undefined ? -9 : p.edge_home_cover;
      case "total": return g.line_total === null || g.line_total === undefined ? -1 : g.line_total;
      case "pts": return p.total_now;
      case "projt": return p.projected_total;
      case "over": return p.p_over === undefined ? -1 : p.p_over;
      case "pwin": return p.p_home_win;
      case "pm": return (g.markets && g.markets.polymarket) ? g.markets.polymarket.p_home_win : -1;
      case "kal": return (g.markets && g.markets.kalshi) ? g.markets.kalshi.p_home_win : -1;
      case "cwin": return p.consensus_home_win === undefined ? -1 : p.consensus_home_win;
      case "div": return p.market_divergence === undefined ? -9 : Math.abs(p.market_divergence);
      case "mcover": return p.market_cover_consensus === undefined ? -1 : p.market_cover_consensus;
      case "ccover": return p.consensus_home_cover === undefined ? -1 : p.consensus_home_cover;
      case "vol": return Object.keys(g.markets || {}).reduce(function (a, k) { return a + (g.markets[k].volume || 0); }, 0);
      case "result": return p.total_result || "";
      default: return g.date || "";
    }
  };
  return list.slice().sort(function (a, b) {
    var x = val(a), y = val(b);
    if (x === y) return 0;
    return (x > y ? 1 : -1) * dir;
  });
}
function head(cols) {
  return "<thead><tr>" + cols.map(function (c) {
    return '<th data-sort="' + c[1] + '" class="' + (S.sort.key === c[1] ? "sorted" : "") + '">' + esc(c[0]) +
      (S.sort.key === c[1] ? (S.sort.dir > 0 ? " ▲" : " ▼") : "") + "</th>";
  }).join("") + "</tr></thead>";
}
function miniBar(p) {
  if (p === undefined || p === null) return "—";
  return '<span class="mini"><i style="width:' + (100 * p).toFixed(0) + '%"></i></span>' + pct(p);
}
function renderAts() {
  var cols = [["Partido", "game"], ["Estado", "state"], ["Marcador", "pts"], ["Línea local", "line"],
  ["Margen vs línea", "cover"], ["Prob. local cubre", "phome"], ["Prob. visitante", "paway"],
  ["Push", "push"], ["Margen proyectado", "proj"], ["Edge local", "edge"]];
  var rows = sortGames(S.games).map(function (g) {
    var p = g.probs || {};
    var edge = p.edge_home_cover;
    var edgeCls = edge === undefined ? "" : (edge > 0.02 ? "pos" : (edge < -0.02 ? "neg" : "flat"));
    var atsCell;
    if (g.state === "post" && p.ats_result) {
      atsCell = p.ats_result === "push" ? '<span class="pill push">Push</span>'
        : '<span class="pill ' + (p.ats_result === "home" ? "ok" : "no") + '">' +
        esc(p.ats_result === "home" ? g.home.abbr : g.away.abbr) + "</span>";
    }
    return '<tr class="row"><td>' + esc(g.away.abbr + " @ " + g.home.abbr) + "</td>" +
      "<td>" + esc(statusText(g)) + "</td>" +
      '<td class="num">' + (g.state === "pre" ? "—" : g.away_score + " - " + g.home_score) + "</td>" +
      '<td class="num">' + esc(lineLabel(g, "home")) + "</td>" +
      '<td class="num ' + (p.cover_margin_now > 0 ? "pos" : p.cover_margin_now < 0 ? "neg" : "flat") + '">' +
      (p.cover_margin_now === undefined || g.state === "pre" ? "—" : signed(p.cover_margin_now)) + "</td>" +
      "<td>" + (atsCell ? (p.ats_result === "home" || p.ats_result === "push" ? atsCell : "—") : miniBar(p.p_home_cover)) + "</td>" +
      "<td>" + (atsCell ? (p.ats_result === "away" || p.ats_result === "push" ? atsCell : "—") : miniBar(p.p_away_cover)) + "</td>" +
      '<td class="num">' + (p.p_push ? pct(p.p_push, 1) : "—") + "</td>" +
      '<td class="num">' + signed(p.projected_margin) + "</td>" +
      '<td class="num ' + edgeCls + '">' + (edge === undefined ? "—" : signed(100 * edge, 1) + " pp") + "</td></tr>";
  }).join("");
  $("ats-table").innerHTML = head(cols) + "<tbody>" + (rows || '<tr><td colspan="10" class="empty">Sin partidos.</td></tr>') + "</tbody>";
}
function renderTotals() {
  var cols = [["Partido", "game"], ["Estado", "state"], ["Total", "total"], ["Puntos", "pts"],
  ["Proyección", "projt"], ["Prob. Over", "over"], ["Resultado", "result"]];
  var rows = sortGames(S.games).map(function (g) {
    var p = g.probs || {};
    var res = p.total_result
      ? '<span class="pill ' + (p.total_result === "over" ? "ok" : p.total_result === "under" ? "no" : "push") + '">' +
      (p.total_result === "over" ? "Over" : p.total_result === "under" ? "Under" : "Push") + "</span>"
      : "—";
    return '<tr class="row"><td>' + esc(g.away.abbr + " @ " + g.home.abbr) + "</td>" +
      "<td>" + esc(statusText(g)) + "</td>" +
      '<td class="num">' + (g.line_total === null || g.line_total === undefined ? "—" : Number(g.line_total).toFixed(1)) + "</td>" +
      '<td class="num">' + p.total_now + "</td>" +
      '<td class="num">' + Number(p.projected_total).toFixed(1) + "</td>" +
      "<td>" + miniBar(p.p_over) + "</td><td>" + res + "</td></tr>";
  }).join("");
  $("totals-table").innerHTML = head(cols) + "<tbody>" + (rows || '<tr><td colspan="7" class="empty">Sin partidos.</td></tr>') + "</tbody>";
}
function renderSummary() {
  var s = S.summary || {};
  var rec = "";
  rec += '<div class="proj" style="gap:18px;margin-bottom:10px">' +
    "<span>Locales <b>" + (s.ats_home || 0) + "</b></span>" +
    "<span>Visitantes <b>" + (s.ats_away || 0) + "</b></span>" +
    "<span>Push <b>" + (s.ats_push || 0) + "</b></span>" +
    "<span>Over <b>" + (s.totals_over || 0) + "</b></span>" +
    "<span>Under <b>" + (s.totals_under || 0) + "</b></span></div>";
  var decided = (s.ats_home || 0) + (s.ats_away || 0);
  if (decided) {
    var w = 100 * (s.ats_home || 0) / decided;
    rec += '<div class="bar" style="height:12px"><i class="green" style="width:' + w.toFixed(1) + '%"></i></div>' +
      '<div class="sub" style="margin-top:6px">Los locales cubrieron ' + (s.ats_home_pct || 0) + " % de los " + decided + " partidos cerrados de esta jornada.</div>";
  } else {
    rec += '<div class="sub">Aún no hay partidos finalizados en esta jornada.</div>';
  }
  rec += '<div class="sub" style="margin-top:10px">Puntos anotados en la jornada: <b class="num">' + (s.points || 0) + "</b> · Partidos con línea: <b class=\"num\">" + (s.with_line || 0) + "</b></div>";
  $("ats-record").innerHTML = rec;

  var withEdge = S.games.filter(function (g) {
    var p = g.probs || {};
    return p.edge_home_cover !== undefined && g.state !== "post" && Math.abs(p.edge_home_cover) >= 0.01;
  });
  withEdge.sort(function (a, b) { return Math.abs(b.probs.edge_home_cover) - Math.abs(a.probs.edge_home_cover); });
  var rows = withEdge.slice(0, 8).map(function (g) {
    var p = g.probs;
    var homeSide = p.edge_home_cover > 0;
    var side = homeSide ? g.home.abbr + " " + lineLabel(g, "home") : g.away.abbr + " " + lineLabel(g, "away");
    var model = homeSide ? p.p_home_cover : p.p_away_cover;
    return '<tr class="row"><td>' + esc(g.away.abbr + " @ " + g.home.abbr) + "</td>" +
      "<td>" + esc(statusText(g)) + "</td><td>" + esc(side) + "</td>" +
      '<td class="num">' + pct(model) + "</td>" +
      '<td class="num pos">' + signed(100 * Math.abs(p.edge_home_cover), 1) + " pp</td></tr>";
  }).join("");
  $("edge-table").innerHTML = "<thead><tr><th>Partido</th><th>Estado</th><th>Lado del modelo</th><th>Prob. modelo</th><th>Ventaja</th></tr></thead><tbody>" +
    (rows || '<tr><td colspan="5" class="empty">Sin diferencias relevantes contra los momios publicados.</td></tr>') + "</tbody>";
  $("edge-note").textContent = "La línea del feed suele ser de cierre: en partidos ya iniciados la ventaja compara un modelo en vivo contra un precio previo al arranque.";

  renderChart();
}
function renderChart() {
  var list = S.games.filter(function (g) { return (g.probs || {}).p_home_cover !== undefined && g.state !== "post"; });
  if (!list.length) { $("chart").innerHTML = '<div class="empty">Sin partidos pendientes con línea.</div>'; return; }
  list.sort(function (a, b) {
    return Math.max(b.probs.p_home_cover, b.probs.p_away_cover) - Math.max(a.probs.p_home_cover, a.probs.p_away_cover);
  });
  var rowH = 26, padL = 118, padR = 56, padT = 14, w = 880;
  var h = padT + list.length * rowH + 26;
  var svg = '<svg viewBox="0 0 ' + w + " " + h + '" role="img" aria-label="Probabilidad de cubrir por partido">';
  var plotW = w - padL - padR;
  [0, 25, 50, 75, 100].forEach(function (g) {
    var x = padL + plotW * g / 100;
    svg += '<line x1="' + x + '" y1="' + padT + '" x2="' + x + '" y2="' + (padT + list.length * rowH) +
      '" stroke="#2A3666" stroke-width="1"' + (g === 50 ? ' stroke-dasharray="4 4"' : "") + "/>";
    svg += '<text x="' + x + '" y="' + (h - 8) + '" fill="#8895B3" font-size="11" text-anchor="middle">' + g + "%</text>";
  });
  list.forEach(function (g, i) {
    var p = g.probs;
    var homeSide = p.p_home_cover >= p.p_away_cover;
    var prob = homeSide ? p.p_home_cover : p.p_away_cover;
    var t = homeSide ? g.home : g.away;
    var y = padT + i * rowH;
    var bw = plotW * prob;
    svg += '<text x="' + (padL - 8) + '" y="' + (y + 16) + '" fill="#CADCFC" font-size="12" text-anchor="end">' +
      esc(t.abbr + " " + lineLabel(g, homeSide ? "home" : "away")) + "</text>";
    svg += '<rect x="' + padL + '" y="' + (y + 5) + '" width="' + plotW + '" height="14" fill="#1E2952" rx="3"/>';
    svg += '<rect x="' + padL + '" y="' + (y + 5) + '" width="' + bw.toFixed(1) + '" height="14" rx="3" fill="' +
      (g.state === "in" ? "#00D9FF" : "#3DD68C") + '" opacity="' + (g.state === "in" ? "1" : ".75") + '"/>';
    svg += '<text x="' + (padL + plotW + 8) + '" y="' + (y + 16) + '" fill="#CADCFC" font-size="12">' + pct(prob, 0) + "</text>";
  });
  svg += "</svg>";
  $("chart").innerHTML = svg;
}
function renderStatus() {
  var chip = $("status-chip"), txt = $("status-text");
  chip.className = "chip" + (S.loading ? " loading" : "") + (S.error ? " bad" : (S.online ? "" : " warn"));
  txt.textContent = S.loading ? "Actualizando…" : (S.error ? "Sin conexión al marcador" : (S.online ? "Datos en vivo" : "Instantánea local"));
  var meta = S.meta || {};
  var fase = { 1: "Pretemporada", 2: "Temporada regular", 3: "Postemporada", 4: "Pro Bowl" }[meta.seasontype] || "";
  $("subtitle").textContent = [meta.season ? "Temporada " + meta.season : "", fase, meta.week ? "Semana " + meta.week : ""]
    .filter(function (x) { return x; }).join(" · ") || "Jornada en curso";
  var when = S.updated ? new Date(S.updated) : null;
  $("updated").textContent = (when && !isNaN(when.getTime()))
    ? "Actualizado " + when.toLocaleTimeString("es-MX", { hour: "2-digit", minute: "2-digit", second: "2-digit" })
    : "";
  var mkOk = ["polymarket", "kalshi"].filter(function (k) { return (S.sourceStatus[k] || {}).ok; });
  $("foot").innerHTML = "Fuentes: " +
    (S.online ? "marcador y líneas de la API pública de ESPN" : "instantánea local (" + esc(S.source) + ")") +
    (mkOk.length ? " · mercados de " + mkOk.map(function (k) { return k === "polymarket" ? "Polymarket" : "Kalshi"; }).join(" y ") : " · sin mercados en esta lectura") +
    ". " + (S.error ? "Último intento del marcador: " + esc(S.error) + ". " : "") +
    "Escudos y colores son marcas registradas de cada club, usadas aquí en un tablero privado de análisis. " +
    "Modelo normal con pesos de números clave: herramienta de análisis, no es asesoría de apuestas.";
}
function renderSources() {
  var labels = { espn: "ESPN · marcador y líneas", polymarket: "Polymarket", kalshi: "Kalshi" };
  var html = Object.keys(labels).map(function (k) {
    var st = S.sourceStatus[k] || { ok: false, detail: "sin consultar" };
    return '<span class="chip src ' + (st.ok ? "ok" : "warn") + '"><span class="dot"></span>' +
      esc(labels[k]) + ' <em>' + esc(st.detail) + "</em></span>";
  }).join("");
  $("sources").innerHTML = html;
}
function renderMarkets() {
  var list = S.games.filter(function (g) { return Object.keys(g.markets || {}).length; });
  var cols = [["Partido", "game"], ["Estado", "state"], ["Modelo gana local", "pwin"],
  ["Polymarket", "pm"], ["Kalshi", "kal"], ["Consenso gana", "cwin"], ["Divergencia", "div"],
  ["Cubre: modelo", "phome"], ["Cubre: mercado", "mcover"], ["Consenso cubre", "ccover"], ["Volumen", "vol"]];
  var rows = sortGames(list).map(function (g) {
    var p = g.probs || {}, m = g.markets || {};
    var pm = m.polymarket, kal = m.kalshi;
    var vol = (pm ? pm.volume : 0) + (kal ? kal.volume : 0);
    var div = p.market_divergence;
    var divCls = div === undefined ? "" : (Math.abs(div) >= 0.05 ? (div > 0 ? "pos" : "neg") : "flat");
    var cell = function (node) {
      if (!node) return "—";
      return '<span class="num">' + pct(node.p_home_win, 1) + "</span>" + (node.stale ? ' <span class="stale">*</span>' : "");
    };
    return '<tr class="row"><td>' + teamCrest(g.away, "sm") + " " + esc(g.away.abbr) + " @ " +
      teamCrest(g.home, "sm") + " " + esc(g.home.abbr) + "</td>" +
      "<td>" + esc(statusText(g)) + "</td>" +
      '<td class="num">' + pct(p.p_home_win, 1) + "</td>" +
      "<td>" + cell(pm) + "</td><td>" + cell(kal) + "</td>" +
      '<td class="num">' + (p.consensus_home_win === undefined ? "—" : pct(p.consensus_home_win, 1)) + "</td>" +
      '<td class="num ' + divCls + '">' + (div === undefined ? "—" : signed(100 * div, 1) + " pp") + "</td>" +
      '<td class="num">' + (p.p_home_cover === undefined ? "—" : pct(p.p_home_cover, 1)) + "</td>" +
      '<td class="num">' + (p.market_cover_consensus === undefined ? "—" : pct(p.market_cover_consensus, 1)) + "</td>" +
      '<td class="num">' + (p.consensus_home_cover === undefined ? "—" : pct(p.consensus_home_cover, 1)) + "</td>" +
      '<td class="num">' + (vol ? "$" + Math.round(vol).toLocaleString("es-MX") : "—") + "</td></tr>";
  }).join("");
  $("markets-table").innerHTML = head(cols) + "<tbody>" +
    (rows || '<tr><td colspan="11" class="empty">Sin cotizaciones para esta jornada. Revisa el estado de las fuentes arriba.</td></tr>') +
    "</tbody>";
  var when = S.quotesAt ? new Date(S.quotesAt) : null;
  wireLogos();
  $("markets-note").textContent = "Todas las probabilidades son del equipo local. " +
    (when && !isNaN(when.getTime()) ? "Última lectura de mercados: " +
      when.toLocaleTimeString("es-MX", { hour: "2-digit", minute: "2-digit" }) + ". " : "") +
    "El asterisco marca una cotización conservada de la lectura anterior.";
}
function renderAll() {
  attachMarkets(S.games, S.quotes);
  S.games.forEach(evaluateGame);
  S.games.sort(function (a, b) {
    var ord = { "in": 0, pre: 1, post: 2 };
    var d = ord[a.state] - ord[b.state];
    return d !== 0 ? d : String(a.date).localeCompare(String(b.date));
  });
  S.summary = summarize(S.games);
  renderStatus(); renderSources(); renderKpis(); renderGames(); renderAts();
  renderTotals(); renderMarkets(); renderSummary();
}

/* ------------------------------------------------------------ refresco */
function weekOptions() {
  var st = parseInt($("stype").value, 10);
  var n = st === 2 ? 18 : (st === 1 ? 4 : 5);
  var names = st === 3 ? { 1: "Comodines", 2: "Divisional", 3: "Campeonato", 4: "Pro Bowl", 5: "Super Bowl" } : {};
  var cur = $("week").value;
  var html = '<option value="">Actual</option>';
  for (var i = 1; i <= n; i++) html += '<option value="' + i + '">' + (names[i] || "Semana " + i) + "</option>";
  $("week").innerHTML = html;
  if (cur) $("week").value = cur;
}
function buildUrl() {
  var season = parseInt($("season").value, 10);
  var st = $("stype").value, wk = $("week").value;
  var p = ["limit=100"];
  if (wk) {
    if (season) p.push("dates=" + season);
    if (st) p.push("seasontype=" + st);
    p.push("week=" + wk);
  }
  return ENDPOINT + "?" + p.join("&");
}
function fetchJson(url, timeoutMs) {
  var ctrl = typeof AbortController !== "undefined" ? new AbortController() : null;
  var timer = setTimeout(function () { if (ctrl) ctrl.abort(); }, timeoutMs || 15000);
  return fetch(url, { cache: "no-store", signal: ctrl ? ctrl.signal : undefined })
    .then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then(function (v) { clearTimeout(timer); return v; },
      function (e) { clearTimeout(timer); throw e; });
}
function errMsg(e) {
  if (e && e.name === "AbortError") return "tiempo de espera agotado";
  if (e && e.message === "Failed to fetch") return "bloqueado por el navegador (CORS o red)";
  return (e && e.message) ? e.message : "error de red";
}
function marketUrl(name) {
  var c = SOURCES[name] || {};
  if (name === "polymarket") {
    return (c.endpoint || "https://gamma-api.polymarket.com/events") + "?" +
      (c.query || "tag_slug=nfl&closed=false&limit=200");
  }
  return (c.endpoint || "https://api.elections.kalshi.com/trade-api/v2/markets") +
    "?series_ticker=" + (c.series_ticker || "KXNFLGAME") + "&status=open&limit=500";
}
function refresh() {
  if (S.loading) return;
  S.loading = true; renderStatus();
  var names = ["polymarket", "kalshi"].filter(function (n) { return (SOURCES[n] || {}).enabled !== false; });
  var jobs = [fetchJson(buildUrl(), 15000)].concat(names.map(function (n) { return fetchJson(marketUrl(n), 15000); }));
  Promise.all(jobs.map(function (pr) {
    return pr.then(function (v) { return { ok: true, value: v }; },
      function (e) { return { ok: false, error: e }; });
  })).then(function (res) {
    var espn = res[0];
    if (espn.ok) {
      var raw = espn.value;
      var games = (raw.events || []).map(parseEvent).filter(function (g) { return g; });
      S.games = games;
      S.meta = {
        season: (raw.season || {}).year || ((raw.leagues || [{}])[0].season || {}).year,
        seasontype: (raw.season || {}).type || parseInt($("stype").value, 10),
        week: (raw.week || {}).number || parseInt($("week").value, 10) || null
      };
      S.online = true; S.error = ""; S.updated = new Date().toISOString();
      S.sourceStatus.espn = { ok: true, detail: games.length + " partidos" };
      if (S.meta.season) $("season").value = S.meta.season;
      if (S.meta.seasontype) $("stype").value = String(S.meta.seasontype);
      persist();
    } else {
      S.online = false;
      S.error = errMsg(espn.error);
      S.sourceStatus.espn = { ok: false, detail: S.error };
    }

    var quotes = [];
    names.forEach(function (n, i) {
      var r = res[i + 1];
      if (r.ok) {
        var parsed = n === "polymarket" ? parsePolymarket(r.value) : parseKalshi(r.value);
        quotes = quotes.concat(parsed);
        S.sourceStatus[n] = { ok: true, detail: parsed.length + " mercados" };
        if (parsed.length) S.quotesAt = new Date().toISOString();
      } else {
        var kept = (S.quotes || []).filter(function (q) { return q.source === n; })
          .map(function (q) { var c = {}; Object.keys(q).forEach(function (k) { c[k] = q[k]; }); c.stale = true; return c; });
        quotes = quotes.concat(kept);
        S.sourceStatus[n] = { ok: false, detail: errMsg(r.error) + (kept.length ? " · se conserva la última lectura" : "") };
      }
    });
    ["polymarket", "kalshi"].forEach(function (n) {
      if (names.indexOf(n) < 0) S.sourceStatus[n] = { ok: false, detail: "desactivado en config" };
    });
    S.quotes = quotes;
    renderAll();
  }).then(function () {
    S.loading = false;
    S.nextIn = parseInt($("every").value, 10) || 0;
    renderStatus();
  });
}
function persist() {
  try {
    localStorage.setItem("nflDash", JSON.stringify({
      season: $("season").value, stype: $("stype").value, week: $("week").value, every: $("every").value
    }));
  } catch (e) { /* almacenamiento no disponible */ }
}
function restore() {
  try {
    var raw = localStorage.getItem("nflDash");
    if (!raw) return;
    var v = JSON.parse(raw);
    if (v.season) $("season").value = v.season;
    if (v.stype) $("stype").value = v.stype;
    if (v.every) $("every").value = v.every;
    weekOptions();
    if (v.week) $("week").value = v.week;
  } catch (e) { /* preferencias no recuperables */ }
}

/* -------------------------------------------------------------- eventos */
function bind() {
  document.querySelectorAll(".tabs button").forEach(function (b) {
    b.addEventListener("click", function () {
      document.querySelectorAll(".tabs button").forEach(function (x) { x.classList.remove("active"); });
      document.querySelectorAll("[data-panel]").forEach(function (x) { x.classList.remove("active"); });
      b.classList.add("active");
      document.querySelector('[data-panel="' + b.dataset.tab + '"]').classList.add("active");
    });
  });
  $("filters").addEventListener("click", function (e) {
    var b = e.target.closest(".f"); if (!b) return;
    S.filter = b.dataset.f;
    document.querySelectorAll("#filters .f").forEach(function (x) { x.classList.remove("active"); });
    b.classList.add("active");
    renderGames();
  });
  ["ats-table", "totals-table", "markets-table"].forEach(function (id) {
    $(id).addEventListener("click", function (e) {
      var th = e.target.closest("th[data-sort]"); if (!th) return;
      var k = th.dataset.sort;
      if (S.sort.key === k) S.sort.dir *= -1; else { S.sort.key = k; S.sort.dir = k === "game" || k === "state" ? 1 : -1; }
      renderAts(); renderTotals(); renderMarkets();
    });
  });
  $("reload").addEventListener("click", function () { refresh(); });
  $("stype").addEventListener("change", function () { weekOptions(); persist(); refresh(); });
  ["season", "week"].forEach(function (id) {
    $(id).addEventListener("change", function () { persist(); refresh(); });
  });
  $("every").addEventListener("change", function () {
    S.nextIn = parseInt($("every").value, 10) || 0; persist(); tickLabel();
  });
  document.addEventListener("visibilitychange", function () {
    if (!document.hidden && (parseInt($("every").value, 10) || 0) > 0) refresh();
  });
}
function tickLabel() {
  var every = parseInt($("every").value, 10) || 0;
  $("countdown").textContent = every ? "Próxima actualización en " + Math.max(0, S.nextIn) + " s" : "Actualización manual";
}
function tick() {
  var every = parseInt($("every").value, 10) || 0;
  if (every > 0 && !document.hidden) {
    S.nextIn -= 1;
    if (S.nextIn <= 0) { S.nextIn = every; refresh(); }
  }
  tickLabel();
}
function init() {
  $("season").value = (S.meta && S.meta.season) || new Date().getFullYear();
  if (S.meta && S.meta.seasontype) $("stype").value = String(S.meta.seasontype);
  weekOptions();
  if (LIVE.refresh_seconds) {
    var opt = String(LIVE.refresh_seconds);
    if ([].slice.call($("every").options).some(function (o) { return o.value === opt; })) $("every").value = opt;
  }
  restore();
  bind();
  renderAll();
  S.nextIn = parseInt($("every").value, 10) || 0;
  tickLabel();
  setInterval(tick, 1000);
  if (LIVE.fetch_on_load !== false) refresh();
}
init();
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

DEFAULT_SETTINGS = {
    "live": {
        "endpoint": ESPN_SCOREBOARD,
        "refresh_seconds": 30,
        "fetch_on_load": True,
    },
    "model": {
        "sigma_full_game": 13.2,
        "sigma_total": 10.6,
        "sigma_overtime": 5.5,
        "sigma_floor": 1.4,
        "possession_points": 1.1,
        "default_total": 44.0,
        "key_numbers": {
            "0": 0.15, "1": 1.1, "2": 1.2, "3": 3.4, "4": 1.3, "5": 1.0, "6": 1.9,
            "7": 2.6, "8": 1.2, "9": 1.1, "10": 2.0, "11": 1.1, "13": 1.1,
            "14": 1.8, "16": 1.1, "17": 1.7, "20": 1.3, "21": 1.4, "24": 1.3,
            "28": 1.2, "default": 0.9,
        },
    },
    "sources": {
        "polymarket": {"enabled": True, "endpoint": POLYMARKET_EVENTS,
                       "query": "tag_slug=nfl&closed=false&limit=200"},
        "kalshi": {"enabled": True, "endpoint": KALSHI_MARKETS, "series_ticker": KALSHI_NFL_SERIES},
    },
    "consensus": {"model_weight": 0.5},
    "assets": {"logos": True, "logo_template": LOGO_TEMPLATE},
    "defaults": {"seasontype": 2},
}


def load_config(path: str) -> dict:
    cfg = json.loads(json.dumps(DEFAULT_SETTINGS))
    if path and os.path.exists(path):
        with open(path, "r", encoding="utf-8") as fh:
            user = json.load(fh)
        for block, values in user.items():
            if isinstance(values, dict) and isinstance(cfg.get(block), dict):
                cfg[block].update(values)
            else:
                cfg[block] = values
    return cfg


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Dashboard NFL: resultados y probabilidad de cubrir el spread")
    ap.add_argument("--config", default=DEFAULT_CONFIG, help="Ruta de config.json")
    ap.add_argument("--out-dir", default=DEFAULT_OUT, help="Carpeta de salida")
    ap.add_argument("--season", type=int, default=None, help="Año de la temporada (ej. 2025)")
    ap.add_argument("--week", type=int, default=None, help="Número de semana")
    ap.add_argument("--seasontype", type=int, default=None, choices=[1, 2, 3, 4],
                    help="1 pretemporada · 2 regular · 3 postemporada · 4 Pro Bowl")
    ap.add_argument("--dates", default=None, help="Filtro de fechas de ESPN (YYYYMMDD o YYYYMMDD-YYYYMMDD)")
    ap.add_argument("--demo", action="store_true", help="Datos sintéticos: no requiere red")
    ap.add_argument("--no-markets", action="store_true",
                    help="Omite Polymarket y Kalshi en la instantánea")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    seasontype = args.seasontype or (cfg.get("defaults", {}).get("seasontype") if args.week else None)

    demo_meta = {"season": args.season or dt.date.today().year,
                 "seasontype": args.seasontype or 2,
                 "week": args.week or 3, "url": "demo"}

    if args.demo:
        games, meta, source = demo_games(cfg), demo_meta, "demo"
    else:
        try:
            games, meta = fetch_scoreboard(args.season, args.week, seasontype, args.dates)
            source = "espn"
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError) as exc:
            print("No se pudo consultar el marcador (%s). Se genera la instantánea con --demo;" % exc,
                  file=sys.stderr)
            print("el dashboard seguirá intentando la conexión en vivo desde el navegador.", file=sys.stderr)
            games, source = demo_games(cfg), "demo"
            meta = dict(demo_meta, week=args.week or 1, error=str(exc))

    if args.no_markets:
        quotes, status = [], {"polymarket": "desactivado", "kalshi": "desactivado"}
    elif source == "demo":
        quotes = demo_quotes(games, cfg)
        status = {"polymarket": "demo", "kalshi": "demo"}
    else:
        quotes, status = fetch_markets(cfg)
        for name, detail in status.items():
            if detail.startswith("error"):
                print("%s: %s" % (name, detail), file=sys.stderr)

    report = build_report(games, cfg, meta, source, quotes, status)

    os.makedirs(args.out_dir, exist_ok=True)
    json_path = os.path.join(args.out_dir, "nfl.json")
    html_path = os.path.join(args.out_dir, "nfl.html")
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    with open(html_path, "w", encoding="utf-8") as fh:
        fh.write(build_html(report))

    s = report["summary"]
    print("Partidos: %d (%d en vivo · %d finales · %d por jugar) · fuente: %s"
          % (s["games"], s["live"], s["final"], s["scheduled"], source))
    matched = sum(1 for g in report["games"] if g.get("markets"))
    print("Mercados de predicción: %s · partidos con cotización: %d"
          % (", ".join("%s %s" % (k, v) for k, v in (report["source_status"] or {}).items()) or "sin consultar",
             matched))
    print("Instantánea: %s" % json_path)
    print("Dashboard : %s" % html_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
