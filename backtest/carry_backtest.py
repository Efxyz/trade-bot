"""
Fonlama motoru backtest'i — canlı CarryEngine'i saatlik simüle saatle çalıştırır.

Kullanım:
  python -m backtest.carry_backtest                    # 3 yıl, varsayılan ayarlar, 7 farklı dengeleme günü
  python -m backtest.carry_backtest --years 1 --shifts 1
  python -m backtest.carry_backtest --refresh          # veriyi yeniden indir

Veri: data/backtest_cache/carry/<SYM>_1h.json ([open_ms, o, h, l, c, quote_vol]) ve <SYM>_funding.json ([ms, rate]).
"""
from __future__ import annotations

import argparse
import bisect
import json
import math
import time
from dataclasses import replace
from pathlib import Path
from typing import Dict, List

import config
from agents.carry_agent import CarryEngine, CarryParams, MemoryCarryStore, HOUR_MS

CACHE = Path(config.DATA_DIR) / "backtest_cache" / "carry"
BASE = "https://fapi.binance.com"


# --------------------------------------------------------------------------------------
# Veri
# --------------------------------------------------------------------------------------
def download(symbols: List[str], years: float = 3.0, refresh: bool = False, end_years_ago: float = 0.0) -> None:
    import requests
    CACHE.mkdir(parents=True, exist_ok=True)
    end = (int(time.time() * 1000) - int(end_years_ago * 365 * 24) * HOUR_MS) // HOUR_MS * HOUR_MS
    start = end - int(years * 365 * 24) * HOUR_MS
    sess = requests.Session()

    def get(path, params):
        for _ in range(6):
            r = sess.get(BASE + path, params=params, timeout=20)
            if r.status_code in (418, 429):
                time.sleep(int(r.headers.get("Retry-After", 30)))
                continue
            r.raise_for_status()
            return r.json()
        raise RuntimeError("rate limited")

    for s in symbols:
        kf, ff = CACHE / f"{s}_1h.json", CACHE / f"{s}_funding.json"
        if refresh or not kf.exists():
            rows, cur = [], start
            while cur < end:
                b = get("/fapi/v1/klines", {"symbol": s, "interval": "1h", "startTime": cur, "endTime": end - 1, "limit": 1500})
                if not b:
                    break
                rows += [[int(x[0]), float(x[1]), float(x[2]), float(x[3]), float(x[4]), float(x[7])] for x in b]
                cur = int(b[-1][0]) + HOUR_MS
                time.sleep(0.15)
            kf.write_text(json.dumps(rows))
        if refresh or not ff.exists():
            rows, cur = [], start
            while cur < end:
                b = get("/fapi/v1/fundingRate", {"symbol": s, "startTime": cur, "endTime": end - 1, "limit": 1000})
                if not b:
                    break
                rows += [[int(x["fundingTime"]), float(x["fundingRate"])] for x in b]
                cur = int(b[-1]["fundingTime"]) + 1
                time.sleep(0.25)
            ff.write_text(json.dumps(rows))
        print(f"  {s} hazır", flush=True)


class SimCarryData:
    def __init__(self, symbols: List[str]):
        self.ts: Dict[str, List[int]] = {}
        self.close: Dict[str, List[float]] = {}
        self.fts: Dict[str, List[int]] = {}
        self.frate: Dict[str, List[float]] = {}
        for s in symbols:
            kf, ff = CACHE / f"{s}_1h.json", CACHE / f"{s}_funding.json"
            if not kf.exists() or not ff.exists():
                continue
            k = json.loads(kf.read_text())
            if len(k) < 24 * 40:
                continue
            k = sorted({r[0]: r for r in k}.values())
            self.ts[s] = [r[0] for r in k]
            self.close[s] = [r[4] for r in k]
            f = sorted(json.loads(ff.read_text()))
            self.fts[s] = [r[0] for r in f]
            self.frate[s] = [r[1] for r in f]
        self.t = 0

    def span(self):
        return min(v[0] for v in self.ts.values()), max(v[-1] for v in self.ts.values()) + HOUR_MS

    def now_ms(self) -> int:
        return self.t

    def _last_closed(self, s: str) -> int:
        # open_ts + 1h <= now  <=>  open_ts <= now - 1h
        return bisect.bisect_right(self.ts[s], self.t - HOUR_MS)

    def hourly_closes(self, symbol: str, n: int) -> List[float]:
        if symbol not in self.ts:
            return []
        i = self._last_closed(symbol)
        # Veri boşluğu olan (listelenmemiş / askıya alınmış) coin: son mum 3 saatten eskiyse kullanılmaz
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
        out = {}
        for s in symbols:
            if s in self.ts:
                i = self._last_closed(s)
                if i > 0 and self.ts[s][i - 1] >= self.t - 4 * HOUR_MS:
                    out[s] = self.close[s][i - 1]
        return out


# --------------------------------------------------------------------------------------
# Koşu ve istatistik
# --------------------------------------------------------------------------------------
def run(data: SimCarryData, params: CarryParams, start_ms: int, end_ms: int) -> Dict:
    store = MemoryCarryStore()
    eng = CarryEngine(data, store, params)
    t = start_ms // HOUR_MS * HOUR_MS
    while t <= end_ms:
        data.t = t
        eng.step()
        t += HOUR_MS
    return {"engine": eng, "store": store}


def stats(store: MemoryCarryStore, capital: float, eng: CarryEngine) -> Dict:
    eq = [r["equity"] for r in store.equity]
    ts = [r["ts_ms"] for r in store.equity]
    rets = [eq[i] / eq[i - 1] - 1 for i in range(1, len(eq)) if eq[i - 1] > 0]
    n = len(rets)
    mu = sum(rets) / n if n else 0.0
    sd = math.sqrt(sum((r - mu) ** 2 for r in rets) / (n - 1)) if n > 1 else 0.0
    hy = 24 * 365
    peak, mdd = eq[0], 0.0
    for v in eq:
        peak = max(peak, v)
        mdd = min(mdd, v / peak - 1)
    years = (ts[-1] - ts[0]) / (hy * HOUR_MS) if len(ts) > 1 else 1
    # Aylık
    from datetime import datetime, timezone
    months: Dict[str, List[float]] = {}
    for t_, v in zip(ts, eq):
        months.setdefault(datetime.fromtimestamp(t_ / 1000, tz=timezone.utc).strftime("%Y-%m"), []).append(v)
    keys = sorted(months)
    mret, prev = [], eq[0]
    for k in keys:
        mret.append(months[k][-1] / prev - 1)
        prev = months[k][-1]
    yearly: Dict[str, Dict] = {}
    for y in sorted({k[:4] for k in keys}):
        ys = [(t_, v) for t_, v in zip(ts, eq) if datetime.fromtimestamp(t_ / 1000, tz=timezone.utc).year == int(y)]
        yr = [ys[i][1] / ys[i - 1][1] - 1 for i in range(1, len(ys))]
        if len(yr) > 24 * 30:
            m = sum(yr) / len(yr)
            s_ = math.sqrt(sum((r - m) ** 2 for r in yr) / (len(yr) - 1))
            yearly[y] = {"ret_%": round((ys[-1][1] / ys[0][1] - 1) * 100, 1),
                         "sharpe": round(m / s_ * math.sqrt(hy), 2) if s_ else 0.0}
    st = eng.state
    return {
        "final_equity": round(eq[-1], 2), "total_ret_%": round((eq[-1] / capital - 1) * 100, 1),
        "cagr_%": round(((eq[-1] / capital) ** (1 / years) - 1) * 100, 1) if years > 0 else 0.0,
        "sharpe": round(mu / sd * math.sqrt(hy), 2) if sd else 0.0,
        "ann_vol_%": round(sd * math.sqrt(hy) * 100, 1), "max_dd_%": round(mdd * 100, 1),
        "positive_months_%": round(100 * sum(1 for r in mret if r > 0) / len(mret), 0) if mret else 0,
        "worst_month_%": round(min(mret) * 100, 1) if mret else 0, "best_month_%": round(max(mret) * 100, 1) if mret else 0,
        "fees_usd": round(st["fees_paid"], 2), "funding_paid_usd": round(st["funding_paid"], 2),
        "fills": st["n_fills"], "fills_per_week": round(st["n_fills"] / (years * 52.14), 1) if years else 0,
        "rebalances": st["n_rebalances"], "years": round(years, 2), "yearly": yearly,
        "avg_leverage": round(sum(r["gross_exposure"] / r["equity"] for r in store.equity) / len(store.equity), 2),
        "max_leverage": round(max(r["gross_exposure"] / r["equity"] for r in store.equity), 2),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=float, default=3.0)
    ap.add_argument("--shifts", type=int, default=7, help="Farklı dengeleme günü sayısı (yol bağımlılığı testi)")
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--fee", type=float, default=None)
    ap.add_argument("--k", type=int, default=None)
    ap.add_argument("--lookback-days", type=int, default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--tranches", type=int, default=None, help="1 = haftalık tek dengeleme, 7 = günlük dilimli")
    ap.add_argument("--target-vol", type=float, default=None, help="Portföy hedef yıllık volatilitesi (örn. 0.20)")
    ap.add_argument("--gross-cap", type=float, default=None, help="Brüt kaldıraç tavanı (notional / özsermaye)")
    ap.add_argument("--dd-cut", type=float, default=None, help="Kesici eşiği (örn. -0.20); restore = yarısı")
    ap.add_argument("--oos", action="store_true",
                    help="Örneklem dışı: stratejinin tasarlandığı 3 yıldan ÖNCEKİ 3 yıl (ayrı önbellek)")
    a = ap.parse_args()
    global CACHE
    base = CarryParams()
    if a.oos:
        CACHE = CACHE.parent / "carry_oos"
        download(base.universe, years=a.years + 0.1, refresh=a.refresh, end_years_ago=3.0)
    else:
        download(base.universe, years=a.years, refresh=a.refresh)
    data = SimCarryData(base.universe)
    first, last = data.span()
    start = max(first + (base.vol_lookback_h + 24) * HOUR_MS, last - int(a.years * 365 * 24) * HOUR_MS)
    results = {}
    ap_tr = a.tranches if a.tranches is not None else base.tranches
    for d in range(a.shifts):
        # Dilimli modda kaydırma = dengeleme SAATİ (0,3,6..), haftalık modda = dengeleme GÜNÜ
        p = replace(base, tranches=ap_tr)
        p = replace(p, rebalance_hour=(d * 3) % 24) if ap_tr > 1 else replace(p, rebalance_weekday=d)
        if a.fee is not None:
            p = replace(p, fee_rate=a.fee)
        if a.target_vol is not None:
            p = replace(p, portfolio_target_vol=a.target_vol)
        if a.gross_cap is not None:
            p = replace(p, gross_cap=a.gross_cap)
        if a.dd_cut is not None:
            p = replace(p, dd_cut=a.dd_cut, dd_restore=a.dd_cut / 2)
        if a.k is not None:
            p = replace(p, k=a.k)
        if a.lookback_days is not None:
            p = replace(p, funding_lookback_h=24 * a.lookback_days)
        r = run(data, p, start, last)
        s = stats(r["store"], p.capital, r["engine"])
        results[f"gun{d}"] = s
        print(f"kaydirma={d}  Sharpe={s['sharpe']}  CAGR={s['cagr_%']}%  maxDD={s['max_dd_%']}%  "
              f"pozitif_ay={s['positive_months_%']}%  en_kotu_ay={s['worst_month_%']}%  komisyon=${s['fees_usd']}  "
              f"fonlama=${s['funding_paid_usd']}  dolum/hafta={s['fills_per_week']}  yillik={s['yearly']}", flush=True)
    vals = list(results.values())
    summary = {k: round(sum(v[k] for v in vals) / len(vals), 2) for k in ("sharpe", "cagr_%", "max_dd_%", "positive_months_%", "worst_month_%", "fills_per_week")}
    summary["min_sharpe"] = min(v["sharpe"] for v in vals)
    summary["worst_dd_%"] = min(v["max_dd_%"] for v in vals)
    summary["avg_leverage"] = round(sum(v["avg_leverage"] for v in vals) / len(vals), 2)
    summary["max_leverage"] = max(v["max_leverage"] for v in vals)
    yrs = {}
    for v in vals:
        for y, d in v["yearly"].items():
            yrs.setdefault(y, []).append(d["ret_%"])
    summary["yearly_ret_%"] = {y: [min(r), round(sum(r) / len(r), 1), max(r)] for y, r in sorted(yrs.items())}
    print("ORTALAMA:", json.dumps(summary, ensure_ascii=False))
    if a.out:
        Path(a.out).write_text(json.dumps({"summary": summary, "runs": results}, indent=1, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
