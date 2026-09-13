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

# Colores primarios por equipo (respaldo cuando el feed no trae color)
TEAM_COLORS = {
    "ARI": "#97233F", "ATL": "#A71930", "BAL": "#241773", "BUF": "#00338D",
    "CAR": "#0085CA", "CHI": "#0B162A", "CIN": "#FB4F14", "CLE": "#311D00",
    "DAL": "#041E42", "DEN": "#FB4F14", "DET": "#0076B6", "GB": "#203731",
    "HOU": "#03202F", "IND": "#002C5F", "JAX": "#006778", "KC": "#E31837",
    "LAC": "#0080C6", "LAR": "#003594", "LV": "#000000", "MIA": "#008E97",
    "MIN": "#4F2683", "NE": "#002244", "NO": "#D3BC8D", "NYG": "#0B2265",
    "NYJ": "#125740", "PHI": "#004C54", "PIT": "#FFB612", "SEA": "#002244",
    "SF": "#AA0000", "TB": "#D50A0A", "TEN": "#0C2340", "WSH": "#5A1414",
}


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
        color = t.get("color") or ""
        return {
            "id": str(t.get("id") or ""),
            "abbr": abbr,
            "name": t.get("displayName") or t.get("name") or abbr,
            "short": t.get("shortDisplayName") or t.get("name") or abbr,
            "location": t.get("location") or "",
            "color": ("#" + color) if color and not color.startswith("#") else (color or TEAM_COLORS.get(abbr, "#1E2761")),
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
        return {"id": abbr, "abbr": abbr, "name": "%s %s" % (loc, nick), "short": nick,
                "location": loc, "color": TEAM_COLORS.get(abbr, "#1E2761"),
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


def build_report(games: List[dict], cfg: dict, meta: dict, source: str) -> dict:
    for g in games:
        evaluate_game(g, cfg)
    games.sort(key=lambda g: ({"in": 0, "pre": 1, "post": 2}.get(g.get("state"), 3), g.get("date") or ""))
    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "source": source,
        "meta": meta,
        "config": cfg,
        "team_colors": TEAM_COLORS,
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
.trow{display:grid;grid-template-columns:14px 1fr auto auto;align-items:center;gap:9px}
.trow .sq{width:12px;height:12px;border-radius:3px;box-shadow:0 0 0 1px rgba(255,255,255,.15) inset}
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
    <h3>Datos</h3>
    <p id="method-source">Marcador, situación de campo y líneas provienen de la API pública de
    resultados de ESPN, consultada directamente desde el navegador en cada refresco.</p>
    <h3>Límites</h3>
    <ul>
      <li>No modela posición en el campo, downs restantes, tiempos fuera ni lesiones.</li>
      <li>Las líneas del feed suelen ser de cierre, no en vivo: el <i>edge</i> mostrado
      compara un modelo en vivo contra un precio previo al partido.</li>
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
var COLORS = BOOT.team_colors || {};
var ENDPOINT = LIVE.endpoint || "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard";

var S = {
  games: BOOT.games || [],
  meta: BOOT.meta || {},
  summary: BOOT.summary || {},
  source: BOOT.source || "demo",
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
  var color = t.color ? (t.color.charAt(0) === "#" ? t.color : "#" + t.color) : (COLORS[abbr] || "#1E2761");
  return {
    id: String(t.id || ""), abbr: abbr,
    name: t.displayName || t.name || abbr,
    short: t.shortDisplayName || t.name || abbr,
    location: t.location || "", color: color, record: rec
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
  return '<div class="' + cls + '">' +
    '<i class="sq" style="background:' + esc(t.color || "#1E2761") + '"></i>' +
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
  $("foot").innerHTML = "Fuente: " + (S.online ? "API pública de resultados de ESPN, consultada desde este navegador." : "instantánea generada localmente (" + esc(S.source) + ").") +
    (S.error ? " Último intento: " + esc(S.error) + "." : "") +
    " Modelo normal con pesos de números clave. Herramienta de análisis: no es asesoría de apuestas.";
}
function renderAll() {
  S.games.forEach(evaluateGame);
  S.games.sort(function (a, b) {
    var ord = { "in": 0, pre: 1, post: 2 };
    var d = ord[a.state] - ord[b.state];
    return d !== 0 ? d : String(a.date).localeCompare(String(b.date));
  });
  S.summary = summarize(S.games);
  renderStatus(); renderKpis(); renderGames(); renderAts(); renderTotals(); renderSummary();
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
function refresh() {
  if (S.loading) return;
  S.loading = true; renderStatus();
  var ctrl = typeof AbortController !== "undefined" ? new AbortController() : null;
  var timer = setTimeout(function () { if (ctrl) ctrl.abort(); }, 15000);
  fetch(buildUrl(), { cache: "no-store", signal: ctrl ? ctrl.signal : undefined })
    .then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then(function (raw) {
      var games = (raw.events || []).map(parseEvent).filter(function (g) { return g; });
      S.games = games;
      S.meta = {
        season: (raw.season || {}).year || ((raw.leagues || [{}])[0].season || {}).year,
        seasontype: (raw.season || {}).type || parseInt($("stype").value, 10),
        week: (raw.week || {}).number || parseInt($("week").value, 10) || null
      };
      S.online = true; S.error = ""; S.updated = new Date().toISOString();
      if (S.meta.season) $("season").value = S.meta.season;
      if (S.meta.seasontype) { $("stype").value = String(S.meta.seasontype); }
      renderAll();
      persist();
    })
    .catch(function (e) {
      S.online = false;
      S.error = (e && e.name === "AbortError") ? "tiempo de espera agotado" : (e && e.message ? e.message : "error de red");
      renderStatus();
    })
    .then(function () {
      clearTimeout(timer);
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
  ["ats-table", "totals-table"].forEach(function (id) {
    $(id).addEventListener("click", function (e) {
      var th = e.target.closest("th[data-sort]"); if (!th) return;
      var k = th.dataset.sort;
      if (S.sort.key === k) S.sort.dir *= -1; else { S.sort.key = k; S.sort.dir = k === "game" || k === "state" ? 1 : -1; }
      renderAts(); renderTotals();
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
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    seasontype = args.seasontype or (cfg.get("defaults", {}).get("seasontype") if args.week else None)

    if args.demo:
        games = demo_games(cfg)
        meta = {"season": args.season or dt.date.today().year,
                "seasontype": args.seasontype or 2,
                "week": args.week or 3, "url": "demo"}
        source = "demo"
    else:
        try:
            games, meta = fetch_scoreboard(args.season, args.week, seasontype, args.dates)
            source = "espn"
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError) as exc:
            print("No se pudo consultar el marcador (%s). Se genera la instantánea con --demo;" % exc,
                  file=sys.stderr)
            print("el dashboard seguirá intentando la conexión en vivo desde el navegador.", file=sys.stderr)
            games = demo_games(cfg)
            meta = {"season": args.season or dt.date.today().year,
                    "seasontype": args.seasontype or 2, "week": args.week or 1,
                    "url": "demo", "error": str(exc)}
            source = "demo"

    report = build_report(games, cfg, meta, source)

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
    print("Instantánea: %s" % json_path)
    print("Dashboard : %s" % html_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
