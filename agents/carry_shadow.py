"""
Canlı ↔ backtest takibi (gölge backtest).

Canlı v3 motorunun başladığı andan şimdiye kadar AYNI motor kodu (CarryEngine) ve AYNI ayarlarla, Binance'in geçmiş
saatlik mum ve fonlama verisi üzerinde bir backtest koşar ve sonucu canlı paper hesapla karşılaştırır.

Amaç kârı ölçmek değil, doğru çalışmayı ölçmek: aynı günler karşılaştırıldığında piyasa şansı iki tarafta da aynıdır,
kalan fark yalnızca uygulamadan gelir (fiyat alma anı, kaçan dengeleme, yeniden başlatma, hesap hatası).

Güvenlik: canlı motorun kayıtları yalnızca OKUNUR. Gölge motor bellekte çalışır (Telegram yok, emir yok, canlı tablolara
yazmaz). Sonuç carry_state tablosunda key='shadow' satırında saklanır.

Bilinen küçük farklar (sapma sayılmaz):
  - Canlı motor dakikada bir adım atar, gölge motor saat başlarında. Canlının saatlik kasa kaydı o saatin ilk adımındaki
    değerdir; birkaç saniyelik/dakikalık fiyat farkı oluşur.
  - Gölge motorun ilk adımı canlı kurulum anında, o dakikanın fiyatlarıyla atılır (aynı mumlar, aynı sinyal).
  - Gölge motor bugünkü parametreleri kullanır; risk seviyesi değişiklikleri canlıdaki saatlerinde uygulanır.
"""
from __future__ import annotations

import bisect
import contextlib
import json
import math
import sqlite3
import threading
import time
from dataclasses import replace
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional, Tuple

import config
from agents.carry_agent import CarryEngine, CarryParams, MemoryCarryStore, SQLiteCarryStore, HOUR_MS, _fmt

DAY_MS = 24 * HOUR_MS
MIN_MS = 60_000
# Gölge motor saat başından 1 dk sonra adım atar (canlı dakikalık döngünün saatteki ilk adımı gibi). Binance fonlama
# kayıtlarını saat başından birkaç ms sonrasına yazar (örn. 00:00:00.001); tam saat başında adım atılsa o anki ödeme
# 7 günlük toplamın dışında kalır ve sinyal canlıdan ayrışırdı.
STEP_OFFSET_MS = MIN_MS
SHADOW_KEY = "shadow"
MAX_CURVE_POINTS = 2400
FAR_FUTURE_MS = 1 << 62
REBALANCE_REASONS = ("ilk_kurulum", "gunluk_dilim", "haftalik")

# Karar eşikleri
DIFF_WARN_PP = 1.0      # |canlı getiri − backtest getiri|, yüzde puan
DIFF_BAD_PP = 2.0
CORR_WARN = 0.95        # günlük getiri korelasyonu (en az MIN_DAYS_CORR gün sonra değerlendirilir)
CORR_BAD = 0.90
MIN_DAYS_CORR = 7
SIDE_WARN = 0.90        # aynı yöndeki coin oranı
SIDE_BAD = 0.75
WGAP_WARN = 15.0        # ağırlık farkı, brüt pozisyonun yüzdesi
WGAP_BAD = 30.0
MIN_W = 0.001           # özsermayenin %0,1'inden küçük pozisyon "yok" sayılır
LATE_MIN = 30           # planlı saatten bu kadar dakika sonra yapılan dengeleme "geç" sayılır

VERDICT_TEXT = {"uyumlu": "Uyumlu", "izle": "İzleniyor", "sapma": "Sapma var", "veri_az": "Veri birikiyor"}


class ShadowDataError(RuntimeError):
    """Piyasa verisi alınamadı ya da canlı kayıt yok: yanlış sonuç üretmek yerine karşılaştırma yapılmaz."""


def floor_hour(ms: int) -> int:
    return int(ms) // HOUR_MS * HOUR_MS


def parse_utc(s: str) -> int:
    return int(datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp() * 1000)


# --------------------------------------------------------------------------------------
# Veri
# --------------------------------------------------------------------------------------
class SeriesData:
    """
    Önceden çekilmiş seriler üzerinde CarryData (backtest/carry_backtest.SimCarryData ile aynı anlam).
    klines: {sym: [[açılış_ms, kapanış], ...]}   funding: {sym: [[zaman_ms, oran], ...]}
    spot:   {t_ms: {sym: fiyat}} saat başı olmayan anlar için (canlı ilk kurulum anı) dakikalık fiyatlar.
    Yalnızca t anına kadar KAPANMIŞ mumlar görünür (geleceği görmez).
    """

    def __init__(self, klines: Dict[str, List], funding: Dict[str, List], spot: Optional[Dict[int, Dict[str, float]]] = None):
        self.spot = {int(k): dict(v) for k, v in (spot or {}).items()}
        self.ts: Dict[str, List[int]] = {}
        self.close: Dict[str, List[float]] = {}
        self.fts: Dict[str, List[int]] = {}
        self.frate: Dict[str, List[float]] = {}
        for s, rows in klines.items():
            rows = sorted({int(r[0]): r for r in rows}.values(), key=lambda r: int(r[0]))
            if rows:
                self.ts[s] = [int(r[0]) for r in rows]
                self.close[s] = [float(r[1]) for r in rows]
        for s, rows in funding.items():
            rows = sorted({int(r[0]): r for r in rows}.values(), key=lambda r: int(r[0]))
            self.fts[s] = [int(r[0]) for r in rows]
            self.frate[s] = [float(r[1]) for r in rows]
        self.t = 0

    def now_ms(self) -> int:
        return self.t

    def _last_closed(self, s: str) -> int:
        return bisect.bisect_right(self.ts[s], self.t - HOUR_MS)   # açılış + 1 saat <= t

    def hourly_closes(self, symbol: str, n: int) -> List[float]:
        if symbol not in self.ts:
            return []
        i = self._last_closed(symbol)
        if i == 0 or self.ts[symbol][i - 1] < self.t - 4 * HOUR_MS:
            return []
        return self.close[symbol][max(0, i - n):i]

    def funding_history(self, symbol: str, start_ms: int, end_ms: int) -> List[Dict]:
        if symbol not in self.fts:
            return []
        a = bisect.bisect_left(self.fts[symbol], start_ms)
        b = bisect.bisect_right(self.fts[symbol], end_ms)
        return [{"time": self.fts[symbol][i], "rate": self.frate[symbol][i]} for i in range(a, b)]

    def prices(self, symbols: List[str]) -> Dict[str, float]:
        spot = self.spot.get(self.t) or {}
        out = {}
        for s in symbols:
            if spot.get(s):
                out[s] = float(spot[s])
            elif s in self.ts:
                i = self._last_closed(s)
                if i > 0 and self.ts[s][i - 1] >= self.t - 4 * HOUR_MS:
                    out[s] = self.close[s][i - 1]
        return out


def _get_json(sess, url: str, params: Dict):
    from core.binance_client import BinanceFuturesClient
    last = None
    for attempt in range(4):
        if BinanceFuturesClient.is_rate_limited():
            raise ShadowDataError("Binance hız sınırı beklemesi sürüyor; karşılaştırma ertelendi")
        try:
            r = sess.get(url, params=params, timeout=15)
        except Exception as e:
            last = f"bağlantı hatası: {e}"
            time.sleep(1.5 * (attempt + 1))
            continue
        if r.status_code in (418, 429):          # canlı motorun öncelikli; ısrar etmeden bırak
            raise ShadowDataError(f"Binance hız sınırı ({r.status_code}); karşılaştırma ertelendi")
        if r.status_code >= 500:
            last = f"Binance {r.status_code}"
            time.sleep(1.5 * (attempt + 1))
            continue
        if r.status_code != 200:
            raise ShadowDataError(f"Binance {r.status_code}: {str(r.text)[:120]}")
        return r.json()
    raise ShadowDataError(last or "Binance yanıt vermedi")


def fetch_market(symbols: List[str], start_ms: int, end_ms: int, session=None, base_url: Optional[str] = None,
                 pause_s: float = 0.05, funding_end_ms: Optional[int] = None) -> Tuple[Dict[str, List], Dict[str, List]]:
    """
    Açılışı start_ms'den itibaren olan ve end_ms'ye kadar KAPANMIŞ saatlik mumlar ([açılış_ms, kapanış]) ile
    funding_end_ms (varsayılan end_ms) dahil fonlama olayları ([zaman_ms, oran]). Herhangi bir hata ShadowDataError fırlatır.
    """
    import requests
    sess = session or requests.Session()
    base = (base_url or config.BINANCE_FUTURES_BASE_URL).rstrip("/")
    start_ms, end_ms = int(start_ms), int(end_ms)
    f_end = int(funding_end_ms if funding_end_ms is not None else end_ms)
    klines: Dict[str, List] = {}
    funding: Dict[str, List] = {}
    for s in symbols:
        rows, cur = [], start_ms
        for _ in range(50):
            if cur > end_ms - HOUR_MS:
                break
            b = _get_json(sess, base + "/fapi/v1/klines", {"symbol": s, "interval": "1h", "startTime": cur,
                                                            "endTime": end_ms - 1, "limit": 1500})
            if not b:
                break
            rows += [[int(x[0]), float(x[4])] for x in b if int(x[0]) + HOUR_MS <= end_ms]
            nxt = int(b[-1][0]) + HOUR_MS
            if len(b) < 1500 or nxt <= cur:
                break
            cur = nxt
            time.sleep(pause_s)
        frows, cur = [], start_ms
        for _ in range(50):
            b = _get_json(sess, base + "/fapi/v1/fundingRate", {"symbol": s, "startTime": cur, "endTime": f_end,
                                                                 "limit": 1000})
            if not b:
                break
            frows += [[int(x["fundingTime"]), float(x["fundingRate"])] for x in b if int(x["fundingTime"]) <= f_end]
            nxt = int(b[-1]["fundingTime"]) + 1
            if len(b) < 1000 or nxt <= cur:
                break
            cur = nxt
            time.sleep(pause_s)
        klines[s], funding[s] = rows, frows
        time.sleep(pause_s)
    return klines, funding


def fetch_spot_prices(symbols: List[str], t_ms: int, session=None, base_url: Optional[str] = None,
                      pause_s: float = 0.05) -> Dict[str, float]:
    """t_ms anındaki fiyat: o dakikanın 1 dakikalık mumu (ilk yarısındaysa açılış, ikinci yarısındaysa kapanış)."""
    import requests
    sess = session or requests.Session()
    base = (base_url or config.BINANCE_FUTURES_BASE_URL).rstrip("/")
    m0 = int(t_ms) // MIN_MS * MIN_MS
    out: Dict[str, float] = {}
    for s in symbols:
        b = _get_json(sess, base + "/fapi/v1/klines", {"symbol": s, "interval": "1m", "startTime": m0, "limit": 1})
        if b and int(b[0][0]) == m0:
            out[s] = float(b[0][4]) if int(t_ms) - m0 >= MIN_MS // 2 else float(b[0][1])
        time.sleep(pause_s)
    return out


# --------------------------------------------------------------------------------------
# Canlı kayıtlar
# --------------------------------------------------------------------------------------
def live_inputs(store) -> Dict:
    """Canlı motorun durumu ve geçmişi (yalnızca okuma). Başlangıç = son 'ilk kurulum' dengelemesi."""
    st = store.load()
    if not st:
        raise ShadowDataError("Canlı motor durumu bulunamadı")
    rebs = store.between("carry_rebalances", 0, FAR_FUTURE_MS)
    starts = [r for r in rebs if r.get("reason") == "ilk_kurulum"]
    if starts:
        t0 = int(starts[-1]["ts_ms"])
    elif rebs:
        t0 = int(rebs[0]["ts_ms"])
    elif st.get("started_ms"):
        t0 = int(st["started_ms"])
    else:
        raise ShadowDataError("Canlı motor henüz portföy kurmadı")
    changes = []
    for c in st.get("risk_changes") or []:
        try:
            at = parse_utc(c["at"])
        except (KeyError, TypeError, ValueError):
            continue
        if at >= t0:
            changes.append({"at_ms": at, "at": c["at"], "from": float(c["from"]), "to": float(c["to"])})
    held = set(st.get("positions") or {})
    for _, snap in st.get("qty_history") or []:
        held |= {k for k, v in snap.items() if v}
    return {
        "state": st, "t0_ms": t0, "capital": float(st.get("capital") or config.CARRY_CAPITAL_USDT),
        "last_step_ms": int(st.get("last_step_ms") or 0),
        "rebalances": [r for r in rebs if int(r["ts_ms"]) >= t0],
        "fills": store.between("carry_fills", t0, FAR_FUTURE_MS),
        "equity": store.between("carry_equity", floor_hour(t0), FAR_FUTURE_MS),
        "risk_changes": sorted(changes, key=lambda c: c["at_ms"]),
        "held_symbols": held,
    }


# --------------------------------------------------------------------------------------
# Gölge koşu
# --------------------------------------------------------------------------------------
def params_for(base: CarryParams, target_vol: float) -> CarryParams:
    """Risk seviyesine göre parametreler; kesici eşikleri risk seviyesiyle orantılı ölçeklenir (canlıdaki kural)."""
    ratio = target_vol / base.portfolio_target_vol if base.portfolio_target_vol else 1.0
    return replace(base, portfolio_target_vol=target_vol, dd_cut=base.dd_cut * ratio, dd_restore=base.dd_restore * ratio)


def step_times(start_ms: int, end_ms: int, offset_ms: int = STEP_OFFSET_MS) -> List[int]:
    """İlk adım canlının kurulum anında (saat başı olmasa da), sonrakiler her saat başından offset_ms sonra (end_ms saati dahil)."""
    start_ms, end_ms = int(start_ms), int(end_ms)
    hours = range(floor_hour(start_ms) + HOUR_MS, floor_hour(end_ms) + 1, HOUR_MS)
    return [start_ms] + [h + offset_ms for h in hours]


def replay(data: SeriesData, base: CarryParams, start_ms: int, end_ms: int, risk_changes: List[Dict]):
    """Gölge motoru canlının kurulum anından end_ms'ye çalıştırır; risk değişiklikleri canlıdaki saatlerinde uygulanır."""
    changes = sorted(risk_changes, key=lambda c: c["at_ms"])
    tv0 = float(changes[0]["from"]) if changes else float(base.portfolio_target_vol)
    store = MemoryCarryStore()
    eng = CarryEngine(data, store, params_for(base, tv0))     # bildirim yok, sessiz
    i = 0
    for t in step_times(start_ms, end_ms):
        while i < len(changes) and changes[i]["at_ms"] <= t:
            eng.p = params_for(base, float(changes[i]["to"]))
            i += 1
        data.t = t
        eng.step()
    return eng, store


# --------------------------------------------------------------------------------------
# Karşılaştırma
# --------------------------------------------------------------------------------------
def _pearson(a: List[float], b: List[float]) -> Optional[float]:
    n = len(a)
    if n < 3:
        return None
    ma, mb = sum(a) / n, sum(b) / n
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((y - mb) ** 2 for y in b)
    if va <= 0 or vb <= 0:
        return None
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / math.sqrt(va * vb)


def _std(xs: List[float]) -> Optional[float]:
    if len(xs) < 2:
        return None
    m = sum(xs) / len(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def _qty_at(qty_history, t_ms: int) -> Dict[str, float]:
    """t_ms'den ÖNCEKİ son pozisyon kaydı (dengelemeden sonraki miktarlar)."""
    q: Dict[str, float] = {}
    for ts, snap in qty_history or []:
        if ts < t_ms:
            q = snap
        else:
            break
    return dict(q)


def _weights(qty: Dict[str, float], prices: Dict[str, float], equity: float) -> Dict[str, float]:
    out = {}
    if not equity:
        return out
    for s, q in qty.items():
        p = prices.get(s)
        if q and p:
            w = q * p / equity
            if abs(w) >= MIN_W:
                out[s] = w
    return out


def _num(row: Dict, key: str, fallback) -> float:
    v = row.get(key)
    return float(v) if v is not None else float(fallback or 0.0)


def _due_ms(ts_ms: int, p: CarryParams) -> int:
    return ts_ms - ((ts_ms - p.rebalance_hour * HOUR_MS) % DAY_MS)


def compare(li: Dict, eng: CarryEngine, sstore: MemoryCarryStore, data: SeriesData, start_ms: int, end_ms: int,
            base: CarryParams) -> Dict:
    cap = li["capital"]
    L = {int(r["ts_ms"]): r for r in li["equity"] if start_ms <= int(r["ts_ms"]) <= end_ms}
    Sh = {int(r["ts_ms"]): r for r in sstore.equity if start_ms <= int(r["ts_ms"]) <= end_ms}
    common = sorted(set(L) & set(Sh))
    curve = [[_fmt(t), round(float(L[t]["equity"]), 2) if t in L else None, round(float(r["equity"]), 2)]
             for t, r in sorted(Sh.items())]
    if len(curve) > MAX_CURVE_POINTS:
        k = math.ceil(len(curve) / MAX_CURVE_POINTS)
        curve = curve[::k] + ([curve[-1]] if (len(curve) - 1) % k else [])
    res: Dict = {
        "start": _fmt(start_ms), "start_ms": start_ms, "end": _fmt(end_ms), "end_ms": end_ms,
        "live_start": _fmt(li["t0_ms"]), "capital": cap, "curve": curve,
        "risk_changes": [{"at": c["at"], "from": c["from"], "to": c["to"]} for c in li["risk_changes"]],
        "params": {"target_vol": eng.p.portfolio_target_vol, "tranches": eng.p.tranches, "fee_rate": eng.p.fee_rate,
                   "slippage_rate": eng.p.slippage_rate, "n_universe": len(eng.p.universe)},
    }
    if not common:
        res.update(verdict="veri_az", reasons=[], notes=["Henüz ortak saatlik kasa kaydı yok; ilk tam saatten sonra karşılaştırılır."],
                   hours=0, days=0.0)
        return res
    t_end = common[-1]
    le, se = float(L[t_end]["equity"]), float(Sh[t_end]["equity"])
    gaps = [(float(L[t]["equity"]) - float(Sh[t]["equity"])) / cap * 100 for t in common]

    # Günlük (UTC gün sınırı) getiriler
    marks = [common[0]] + [t for t in common[1:] if t % DAY_MS == 0]
    if marks[-1] != t_end:
        marks.append(t_end)
    lr = [float(L[b]["equity"]) / float(L[a]["equity"]) - 1 for a, b in zip(marks, marks[1:])]
    sr = [float(Sh[b]["equity"]) / float(Sh[a]["equity"]) - 1 for a, b in zip(marks, marks[1:])]
    dif = [x - y for x, y in zip(lr, sr)]
    te = _std(dif)

    # Dengeleme ve dolumlar (karşılaştırılan son saatin sonuna kadar)
    lim = t_end + HOUR_MS
    lrebs = [r for r in li["rebalances"] if int(r["ts_ms"]) < lim]
    srebs = [r for r in sstore.rebalances if int(r["ts_ms"]) < lim]
    lday = {_fmt(int(r["ts_ms"]))[:10] for r in lrebs if r.get("reason") in REBALANCE_REASONS}
    sday = {_fmt(int(r["ts_ms"]))[:10] for r in srebs if r.get("reason") in REBALANCE_REASONS}
    late = [_fmt(int(r["ts_ms"]))[:16] for r in lrebs if r.get("reason") in ("gunluk_dilim", "haftalik")
            and base.tranches > 1 and int(r["ts_ms"]) - _due_ms(int(r["ts_ms"]), base) > LATE_MIN * MIN_MS]

    # Pozisyonlar: aynı saatteki (dengeleme sonrası) miktarlar, aynı fiyatlarla
    lq = _qty_at(li["state"].get("qty_history"), lim)
    sq = _qty_at(eng.state.get("qty_history"), lim)
    t_save = data.t
    data.t = t_end
    prices = data.prices(sorted(set(lq) | set(sq)))
    data.t = t_save
    lw, sw = _weights(lq, prices, le), _weights(sq, prices, se)
    union = sorted(set(lw) | set(sw))
    same = sum(1 for s in union if s in lw and s in sw and (lw[s] > 0) == (sw[s] > 0))
    denom = max(sum(abs(v) for v in lw.values()), sum(abs(v) for v in sw.values()))
    wgap = sum(abs(lw.get(s, 0.0) - sw.get(s, 0.0)) for s in union) / denom * 100 if denom > 0 else 0.0
    rows = sorted(({"symbol": s, "live_w": round(lw.get(s, 0.0) * 100, 2), "shadow_w": round(sw.get(s, 0.0) * 100, 2)}
                   for s in union), key=lambda r: -abs(r["live_w"] - r["shadow_w"]))

    lst, sst = li["state"], eng.state
    res.update({
        "t_end": _fmt(t_end), "t_end_ms": t_end, "hours": len(common), "days": round((t_end - common[0]) / DAY_MS, 2),
        "live": {"equity": round(le, 4), "ret_pct": round((le / cap - 1) * 100, 4),
                 "fees": round(_num(L[t_end], "fees_paid", lst.get("fees_paid")), 4),
                 "funding": round(_num(L[t_end], "funding_paid", lst.get("funding_paid")), 4),
                 "n_rebalances": len(lrebs), "n_fills": sum(1 for f in li["fills"] if int(f["ts_ms"]) < lim)},
        "shadow": {"equity": round(se, 4), "ret_pct": round((se / cap - 1) * 100, 4),
                   "fees": round(_num(Sh[t_end], "fees_paid", sst.get("fees_paid")), 4),
                   "funding": round(_num(Sh[t_end], "funding_paid", sst.get("funding_paid")), 4),
                   "n_rebalances": len(srebs), "n_fills": sum(1 for f in sstore.fills if int(f["ts_ms"]) < lim)},
        "diff_pp": round((le - se) / cap * 100, 4), "max_gap_pp": round(max(abs(g) for g in gaps), 4),
        "daily": {"n": len(lr), "corr": None if _pearson(lr, sr) is None else round(_pearson(lr, sr), 4),
                  "te_pp": None if te is None else round(te * 100, 4),
                  "max_diff_pp": round(max((abs(x) for x in dif), default=0.0) * 100, 4)},
        "positions": {"n": len(union), "same_side": same, "side_ratio": round(same / len(union), 4) if union else 1.0,
                      "weight_gap_pct": round(wgap, 2), "rows": rows[:12]},
        "rebalance_days": {"missed": sorted(sday - lday), "extra": sorted(lday - sday), "late": late[-10:]},
    })
    res["verdict"], res["reasons"], res["notes"] = judge(res)
    return res


def judge(m: Dict) -> Tuple[str, List[str], List[str]]:
    """Sonuç: uyumlu / izle / sapma, nedenler ve bilgi notları."""
    bad: List[str] = []
    warn: List[str] = []
    notes: List[str] = []
    d = m["diff_pp"]
    if abs(d) > DIFF_BAD_PP:
        bad.append(f"Canlı ile backtest arasında {d:+.2f} puan getiri farkı var (sınır ±{DIFF_BAD_PP:.0f}).")
    elif abs(d) > DIFF_WARN_PP:
        warn.append(f"Getiri farkı {d:+.2f} puan (normalde ±0,3 içinde kalır).")
    p = m["positions"]
    if p["n"]:
        txt = f"Pozisyonların {p['same_side']}/{p['n']} kadarı aynı yönde, ağırlık farkı %{p['weight_gap_pct']:.1f}."
        if p["side_ratio"] < SIDE_BAD or p["weight_gap_pct"] > WGAP_BAD:
            bad.append(txt)
        elif p["side_ratio"] < SIDE_WARN or p["weight_gap_pct"] > WGAP_WARN:
            warn.append(txt)
    dd = m["daily"]
    if m["days"] >= MIN_DAYS_CORR and dd["corr"] is not None:
        if dd["corr"] < CORR_BAD:
            bad.append(f"Günlük getiriler birbirini izlemiyor (korelasyon {dd['corr']:.2f}).")
        elif dd["corr"] < CORR_WARN:
            warn.append(f"Günlük getiri uyumu zayıf (korelasyon {dd['corr']:.2f}).")
    else:
        notes.append(f"Günlük getiri uyumu {MIN_DAYS_CORR} gün dolunca değerlendirilecek (şu an {m['days']:.1f} gün).")
    rd = m["rebalance_days"]
    if len(rd["missed"]) >= 2:
        bad.append(f"{len(rd['missed'])} gün dengeleme yapılmamış: {', '.join(rd['missed'][-5:])}.")
    elif rd["missed"]:
        warn.append(f"Dengeleme yapılmayan gün: {rd['missed'][0]}.")
    if rd["late"]:
        notes.append(f"Geç yapılan dengeleme (planlı saatten {LATE_MIN} dk sonra): {', '.join(rd['late'][-3:])} UTC.")
    if rd["extra"]:
        notes.append(f"Backtestte olmayan dengeleme günü: {', '.join(rd['extra'][-3:])} (başlangıç saati ya da kesici).")
    verdict = "sapma" if bad else "izle" if warn else "uyumlu"
    return verdict, bad + warn, notes


# --------------------------------------------------------------------------------------
# Kayıt
# --------------------------------------------------------------------------------------
def _db_path(store) -> Optional[str]:
    return getattr(store, "db_path", None)


def save_result(res: Dict, store) -> None:
    path = _db_path(store)
    if not path:
        store.shadow_result = json.loads(json.dumps(res))
        return
    with contextlib.closing(sqlite3.connect(path, timeout=30.0)) as c, c:
        c.execute("CREATE TABLE IF NOT EXISTS carry_state (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        c.execute("INSERT OR REPLACE INTO carry_state(key, value) VALUES(?, ?)", (SHADOW_KEY, json.dumps(res)))


def load_result(store) -> Optional[Dict]:
    path = _db_path(store)
    if not path:
        v = getattr(store, "shadow_result", None)
        return json.loads(json.dumps(v)) if v else None
    try:
        with contextlib.closing(sqlite3.connect(path, timeout=30.0)) as c:
            r = c.execute("SELECT value FROM carry_state WHERE key=?", (SHADOW_KEY,)).fetchone()
    except sqlite3.OperationalError:
        return None
    return json.loads(r[0]) if r else None


# --------------------------------------------------------------------------------------
# Çalıştırma ve zamanlama
# --------------------------------------------------------------------------------------
_RUN_LOCK = threading.Lock()
_RUNNING = threading.Event()
_SCHED_STARTED = False


def is_running() -> bool:
    return _RUNNING.is_set()


def run_shadow(store=None, now_ms: Optional[int] = None, fetch: Optional[Callable] = None,
               base_params: Optional[CarryParams] = None, fetch_spot: Optional[Callable] = None) -> Dict:
    """Canlı kayıtları okur, gölge backtesti koşar, karşılaştırır ve sonucu kaydeder. Hata canlı motoru etkilemez."""
    if not _RUN_LOCK.acquire(blocking=False):
        return {"status": "calisiyor"}
    _RUNNING.set()
    t_wall = time.time()
    store = store if store is not None else SQLiteCarryStore()
    now_ms = int(now_ms or time.time() * 1000)
    try:
        base = base_params or CarryParams()
        li = live_inputs(store)
        base = replace(base, capital=li["capital"])
        t0 = li["t0_ms"]
        start = floor_hour(t0)                       # karşılaştırılan ilk saatlik kasa kaydı
        end = floor_hour(min(now_ms, li["last_step_ms"] or now_ms) - 5 * MIN_MS)
        spot: Dict[str, float] = {}
        if end < start:
            res = {"verdict": "veri_az", "reasons": [], "hours": 0, "days": 0.0, "curve": [],
                   "notes": ["Canlı motor yeni başladı; ilk karşılaştırma ilk tam saatten sonra yapılır."],
                   "start": _fmt(start), "start_ms": start, "end": _fmt(start), "end_ms": start,
                   "live_start": _fmt(t0), "capital": li["capital"]}
        else:
            n_bars = max(base.vol_lookback_h, base.xsmom_lookback_h, base.tsmom_lookback_h) + 1
            pre_h = max(n_bars, base.funding_lookback_h) + 48
            syms = sorted(set(base.universe) | li["held_symbols"])
            klines, funding = (fetch or fetch_market)(syms, start - pre_h * HOUR_MS, end,
                                                      funding_end_ms=end + STEP_OFFSET_MS)
            missing = [s for s in base.universe if not klines.get(s)]
            if missing:
                raise ShadowDataError(f"Mum verisi alınamadı: {', '.join(missing[:5])}")
            if t0 % HOUR_MS:                         # canlı kurulum saat başında değil: o dakikanın fiyatları
                prev = load_result(store) or {}
                spot = prev.get("spot_t0") if prev.get("live_start_ms") == t0 else None
                if not spot:
                    spot = (fetch_spot or fetch_spot_prices)(syms, t0)
                if [s for s in base.universe if not spot.get(s)]:
                    raise ShadowDataError("Kurulum anının dakikalık fiyatları alınamadı")
            data = SeriesData(klines, funding, spot={t0: spot} if spot else None)
            eng, sstore = replay(data, base, t0, end, li["risk_changes"])
            res = compare(li, eng, sstore, data, start, end, base)
        res.update({"status": "ok", "run_at": _fmt(now_ms), "run_ms": now_ms, "live_start_ms": t0, "spot_t0": spot,
                    "duration_s": round(time.time() - t_wall, 1), "last_error": None})
        save_result(res, store)
        return res
    except Exception as e:
        err = {"time": _fmt(now_ms), "time_ms": now_ms, "error": str(e)[:300]}
        prev = load_result(store) or {"status": "hata", "verdict": "veri_az"}
        prev["last_error"] = err
        try:
            save_result(prev, store)
        except Exception:
            pass
        print(f"⚠️ [Takip] Canlı ↔ backtest karşılaştırması yapılamadı: {err['error']}")
        return {"status": "hata", "error": err["error"]}
    finally:
        _RUNNING.clear()
        _RUN_LOCK.release()


def is_due(res: Optional[Dict], now_ms: int, live_last_reb_ms: Optional[int], every_h: Optional[float] = None) -> bool:
    """6 saatte bir; ayrıca karşılaştırmaya girmemiş yeni bir dengeleme varsa ondan 10 dk sonra. Hatadan sonra 30 dk bekler."""
    every_h = config.SHADOW_RUN_EVERY_H if every_h is None else every_h
    res = res or {}
    err = res.get("last_error")
    if err and now_ms - int(err.get("time_ms") or 0) < 30 * MIN_MS:
        return False
    if not res.get("run_ms"):
        return True
    if now_ms - int(res["run_ms"]) >= every_h * HOUR_MS:
        return True
    end_ms = int(res.get("end_ms") or 0)
    return bool(live_last_reb_ms and live_last_reb_ms >= end_ms + HOUR_MS and now_ms - live_last_reb_ms >= 10 * MIN_MS)


def due_now(store=None, now_ms: Optional[int] = None) -> bool:
    store = store if store is not None else SQLiteCarryStore()
    now_ms = int(now_ms or time.time() * 1000)
    st = store.load() or {}
    if not st.get("last_rebalance_ms"):
        return False                              # canlı motor henüz portföy kurmadı
    return is_due(load_result(store), now_ms, st.get("last_rebalance_ms"))


def run_in_background() -> bool:
    if is_running():
        return False
    threading.Thread(target=run_shadow, daemon=True, name="ShadowBacktestManual").start()
    return True


def start_scheduler(first_delay_s: float = 180.0, check_every_s: float = 300.0):
    """Arka plan zamanlayıcısı (tek kez başlar). Canlı motor ya da takip kapalıysa başlamaz."""
    global _SCHED_STARTED
    if _SCHED_STARTED or not (config.ENABLE_SHADOW_TRACKING and config.ENABLE_CARRY_ENGINE):
        return None
    _SCHED_STARTED = True

    def _loop():
        time.sleep(first_delay_s)
        store = SQLiteCarryStore()
        while True:
            try:
                if due_now(store):
                    res = run_shadow(store)
                    if res.get("status") == "ok":
                        print(f"🧪 [Takip] Canlı ↔ backtest: {VERDICT_TEXT.get(res.get('verdict'), res.get('verdict'))}"
                              f" · fark {float(res.get('diff_pp') or 0):+.2f} puan · {res.get('duration_s')} sn")
            except Exception as e:
                print(f"⚠️ [Takip] Zamanlayıcı hatası: {e}")
            time.sleep(check_every_s)

    th = threading.Thread(target=_loop, daemon=True, name="ShadowBacktest")
    th.start()
    print(f"🧪 [Takip] Canlı ↔ backtest karşılaştırması: her {config.SHADOW_RUN_EVERY_H:g} saatte bir ve her dengelemeden sonra.")
    return th
