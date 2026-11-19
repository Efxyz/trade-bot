"""Backtest sonuç metrikleri: beklenti, profit factor, çıkış nedeni / yön / vade kırılımları, dönem tutarlılığı."""
import math
from collections import defaultdict
from typing import Dict, List

ACTIVE = {"ACTIVE", "ACTIVE_BE", "ACTIVE_LADDER", "ACTIVE_PARTIAL_TP1", "PENDING_ENTRY"}


def _usd(t: Dict) -> float:
    return float(t.get("allocated_margin_usdt") or 0.0) * float(t.get("simulated_pnl_pct") or 0.0) / 100.0


def _fee_usd(t: Dict) -> float:
    return float(t.get("allocated_margin_usdt") or 0.0) * float(t.get("fee_pct") or 0.0) / 100.0


def summarize(trades: List[Dict]) -> Dict:
    closed = [t for t in trades if t.get("status") not in ACTIVE and t.get("simulated_pnl_pct") is not None]
    n = len(closed)
    pnl = [_usd(t) for t in closed]
    wins = [p for p in pnl if p > 0]
    losses = [p for p in pnl if p < 0]
    gross_win, gross_loss = sum(wins), -sum(losses)
    fees = sum(_fee_usd(t) for t in closed)
    funding = sum(float(t.get("funding_usd") or 0.0) for t in closed)
    mean = sum(pnl) / n if n else 0.0
    sd = math.sqrt(sum((p - mean) ** 2 for p in pnl) / (n - 1)) if n > 1 else 0.0
    # Basit en büyük düşüş (kapanış sırasına göre kümülatif)
    eq, peak, mdd = 0.0, 0.0, 0.0
    for t in sorted(closed, key=lambda x: str(x.get("closed_at"))):
        eq += _usd(t)
        peak = max(peak, eq)
        mdd = max(mdd, peak - eq)
    return {
        "trades": n,
        "open_at_end": len(trades) - n,
        "win_rate_pct": round(len(wins) / n * 100, 1) if n else 0.0,
        "net_usd": round(sum(pnl), 2),
        "expectancy_usd": round(mean, 3),
        "expectancy_t_stat": round(mean / (sd / math.sqrt(n)), 2) if n > 1 and sd > 0 else 0.0,
        "profit_factor": round(gross_win / gross_loss, 2) if gross_loss > 0 else (99.0 if gross_win > 0 else 0.0),
        "avg_win_usd": round(gross_win / len(wins), 2) if wins else 0.0,
        "avg_loss_usd": round(-gross_loss / len(losses), 2) if losses else 0.0,
        "fees_usd": round(fees, 2),
        "net_before_fees_usd": round(sum(pnl) + fees, 2),
        "funding_usd": round(funding, 2),
        "max_drawdown_usd": round(mdd, 2),
    }


def breakdown(trades: List[Dict], key: str) -> Dict[str, Dict]:
    groups = defaultdict(list)
    for t in trades:
        if t.get("status") in ACTIVE:
            continue
        groups[str(t.get(key))].append(t)
    out = {}
    for k, rows in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        pnl = [_usd(t) for t in rows]
        out[k] = {"n": len(rows), "net_usd": round(sum(pnl), 2), "avg_usd": round(sum(pnl) / len(rows), 2),
                  "win_rate_pct": round(sum(1 for p in pnl if p > 0) / len(rows) * 100, 1)}
    return out


def by_period(trades: List[Dict], n_folds: int = 3) -> List[Dict]:
    """Kronolojik eşit parçalarda performans (dönemler arası tutarlılık / walk-forward kontrolü)."""
    closed = sorted([t for t in trades if t.get("status") not in ACTIVE], key=lambda x: str(x.get("closed_at")))
    if not closed:
        return []
    size = max(1, math.ceil(len(closed) / n_folds))
    res = []
    for i in range(0, len(closed), size):
        chunk = closed[i:i + size]
        s = summarize(chunk)
        s["from"] = str(chunk[0].get("closed_at"))[:16]
        s["to"] = str(chunk[-1].get("closed_at"))[:16]
        res.append(s)
    return res


def full_report(result: Dict) -> Dict:
    trades = result["trades"]
    return {
        "summary": summarize(trades),
        "by_exit": breakdown(trades, "status"),
        "by_direction": breakdown(trades, "direction"),
        "by_timeframe": breakdown(trades, "timeframe"),
        "by_period": by_period(trades),
        "rejections": result.get("rejections", {}),
    }


def format_report(rep: Dict, title: str = "") -> str:
    s = rep["summary"]
    lines = [f"=== {title} ===" if title else "===",
             f"İşlem: {s['trades']} (açık kalan {s['open_at_end']}) | WR %{s['win_rate_pct']} | PF {s['profit_factor']} | "
             f"Net ${s['net_usd']} | Beklenti ${s['expectancy_usd']}/işlem (t={s['expectancy_t_stat']})",
             f"Ort. kazanç ${s['avg_win_usd']} / kayıp ${s['avg_loss_usd']} | Komisyon ${s['fees_usd']} | "
             f"Komisyonsuz net ${s['net_before_fees_usd']} | Fonlama ${s['funding_usd']} | Maks DD ${s['max_drawdown_usd']}"]
    for name in ("by_exit", "by_direction", "by_timeframe"):
        lines.append(f"-- {name}: " + "; ".join(f"{k}: n={v['n']} ${v['net_usd']} (WR %{v['win_rate_pct']})" for k, v in rep[name].items()))
    lines.append("-- dönemler: " + " | ".join(f"{p['from']}→{p['to']}: n={p['trades']} ${p['net_usd']} PF {p['profit_factor']}" for p in rep["by_period"]))
    if rep.get("rejections"):
        lines.append("-- elemeler: " + ", ".join(f"{k}={v}" for k, v in sorted(rep["rejections"].items(), key=lambda kv: -kv[1])))
    return "\n".join(lines)
