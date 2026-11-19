"""
Backtest komut satırı.

Örnekler:
  python -m backtest.run --days 30
  python -m backtest.run --days 45 --variants baseline,no_mc,no_quality
  python -m backtest.run --days 30 --symbols BTCUSDT,ETHUSDT,SOLUSDT

Varyantlar config sabitlerini (ve onları import etmiş modülleri) geçici olarak değiştirerek
filtre/çıkış kurallarının katkısını ölçer (ablation).
"""
import argparse
import importlib
import json
import sys
import time
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.data import aligned_window, load_klines  # noqa: E402
from backtest.engine import BacktestConfig, BacktestEngine  # noqa: E402
from backtest.report import full_report, format_report  # noqa: E402

DEFAULT_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "BNBUSDT",
                   "ADAUSDT", "AVAXUSDT", "SUIUSDT", "NEARUSDT", "LTCUSDT", "DOTUSDT"]
INTERVALS = ["1m", "15m", "30m", "1h", "4h"]
PATCH_MODULES = ["config", "agents.tracker_agent", "agents.ta_agent", "agents.risk_agent", "main"]

# Varyant: (BacktestConfig alanları, config sabit geçersiz kılmaları)
VARIANTS = {
    "baseline": ({}, {}),
    "no_mc": ({"use_mc_gate": False}, {}),
    "no_quality": ({"use_quality_gate": False}, {}),
    "no_mc_no_quality": ({"use_mc_gate": False, "use_quality_gate": False}, {}),
    "no_stagnation_exit": ({}, {"ENABLE_MOMENTUM_STAGNATION_EXIT": False}),
    "no_early_invalidation": ({}, {"EARLY_INVALIDATION_ENABLED": False}),
    "only_15m": ({"allowed_timeframes": ["15m"]}, {}),
    "no_4h_compass": ({"use_4h_compass": False}, {}),
    "scoring_dedup": ({}, {"SCORING_DEDUP": True}),
    "regime_rr": ({}, {"USE_REGIME_MIN_RR": True}),
    "no_step1_partial": ({}, {"LADDER_STEP1_PARTIAL_PCT": 0.0}),
    # Eski dar merdiven + erken çıkışlar (v2.0 varsayılanları) — karşılaştırma için
    "legacy_ladder": ({}, {
        "ATR_LADDER_ENABLED": True,
        "LADDER_STEP1_PARTIAL_PCT": 0.35,
        "ENABLE_MOMENTUM_STAGNATION_EXIT": True,
        "EARLY_INVALIDATION_ENABLED": True,
        "LADDER_STEPS": __import__("config").LEGACY_LADDER_STEPS,
    }),
}


@contextmanager
def config_overrides(overrides: dict):
    saved = []
    try:
        for mod_name in PATCH_MODULES:
            mod = importlib.import_module(mod_name)
            for k, v in overrides.items():
                if hasattr(mod, k) or mod_name == "config":
                    saved.append((mod, k, getattr(mod, k, None), hasattr(mod, k)))
                    setattr(mod, k, v)
        yield
    finally:
        for mod, k, old, existed in reversed(saved):
            if existed:
                setattr(mod, k, old)
            else:
                delattr(mod, k)


def load_data(symbols, start_ms, end_ms, refresh=False):
    data = {}
    for s in sorted(set(symbols) | {"BTCUSDT"}):
        data[s] = {}
        for iv in INTERVALS:
            data[s][iv] = load_klines(s, iv, start_ms, end_ms, refresh=refresh)
        print(f"  veri: {s} " + " ".join(f"{iv}={len(data[s][iv])}" for iv in INTERVALS), flush=True)
    return data


def main(argv=None):
    ap = argparse.ArgumentParser(description="Trade-Bot backtest (canlı strateji kodu ile)")
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--warmup-days", type=int, default=10)
    ap.add_argument("--symbols", type=str, default=",".join(DEFAULT_SYMBOLS))
    ap.add_argument("--variants", type=str, default="baseline")
    ap.add_argument("--scan-minutes", type=int, default=15)
    ap.add_argument("--end-days-ago", type=int, default=0, help="Pencereyi geçmişe kaydırır (örneklem dışı doğrulama)")
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--out", type=str, default="")
    args = ap.parse_args(argv)

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    import time as _t
    start_ms, end_ms = aligned_window(args.days, args.warmup_days,
                                      now_ms=int(_t.time() * 1000) - args.end_days_ago * 86_400_000)
    sim_start = start_ms + args.warmup_days * 86_400_000
    print(f"Veri yükleniyor ({len(symbols)} sembol, {args.days}+{args.warmup_days} gün)...", flush=True)
    data = load_data(symbols, start_ms, end_ms, refresh=args.refresh)

    reports = {}
    for name in [v.strip() for v in args.variants.split(",") if v.strip()]:
        cfg_kw, overrides = VARIANTS[name]
        cfg = BacktestConfig(symbols=symbols, start_ms=sim_start, end_ms=end_ms,
                             scan_every_minutes=args.scan_minutes, **cfg_kw)
        t0 = time.time()
        with config_overrides(overrides):
            result = BacktestEngine(cfg, data).run()
        rep = full_report(result)
        rep["runtime_sec"] = round(time.time() - t0, 1)
        reports[name] = rep
        print(format_report(rep, f"{name} ({rep['runtime_sec']} sn)"), flush=True)

    out = Path(args.out) if args.out else ROOT / "data" / "backtest_reports" / f"bt_{int(time.time())}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"args": vars(args), "reports": reports}, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Rapor kaydedildi: {out}")
    return reports


if __name__ == "__main__":
    main()
