"""
Chart Generation Agent
Renders high-resolution, dark-themed TradingView-style candlestick charts with
EMAs, RSI, Volume, Entry Zone, Stop-Loss and Take-Profit overlays as PNG images.
"""
import os
import time
from typing import List, Dict
import matplotlib
matplotlib.use("Agg")  # Headless backend (no GUI window required)
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from datetime import datetime
from config import CHARTS_DIR

class ChartAgent:
    def __init__(self, output_dir=CHARTS_DIR):
        self.output_dir = output_dir

    def generate_chart(self, setup: Dict, candles: List[Dict], suffix: str = "entry") -> str:
        """
        Setup ve mum verilerine göre profesyonel analiz grafiği çizip PNG dosyası olarak kaydeder.
        Döner: Kaydedilen dosyanın mutlak yolu (str)
        """
        symbol = setup["symbol"]
        direction = setup["direction"]
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{symbol}_{direction}_{suffix}_{timestamp_str}.png"
        filepath = os.path.join(self.output_dir, filename)

        # Son 45 mumu görselleştirelim (net ve okunaklı olması için)
        plot_candles = candles[-45:]
        n = len(plot_candles)
        indices = list(range(n))

        # 3 Panelli Düzen: [Mum Grafiği (oran 6), RSI (oran 2), Hacim (oran 2)]
        fig, (ax_main, ax_rsi, ax_vol) = plt.subplots(
            nrows=3, ncols=1, figsize=(12, 9),
            gridspec_kw={"height_ratios": [6, 2, 2]},
            facecolor="#131722", sharex=True
        )

        # Arka plan renkleri (TradingView Dark Theme)
        for ax in (ax_main, ax_rsi, ax_vol):
            ax.set_facecolor("#1e222d")
            ax.tick_params(colors="#848e9c", labelsize=9)
            ax.grid(True, color="#2a2e39", linestyle="--", alpha=0.6)
            for spine in ax.spines.values():
                spine.set_color("#2a2e39")

        # Renk paleti
        up_color = "#10b981"
        down_color = "#ef4444"

        # 1. ÇİZGİ GRAFİĞİ ÇİZİMİ (Line Chart)
        closes = [c["close"] for c in plot_candles]
        line_color = "#38bdf8" if direction == "LONG" else "#fb923c"
        ax_main.plot(indices, closes, color=line_color, linewidth=2.3, label=f"{symbol} Fiyat Çizgisi", zorder=3)
        min_p = min(closes)
        ax_main.fill_between(indices, closes, min_p * 0.999, color=line_color, alpha=0.12, zorder=2)

        # Son Fiyat Noktası (Canlı Pin)
        last_idx = indices[-1]
        last_close = closes[-1]
        ax_main.scatter([last_idx], [last_close], color=line_color, s=40, zorder=5)

        # EMA Çizgileri
        indicators = setup.get("indicators", {})
        ema20_all = indicators.get("ema20", [])
        ema50_all = indicators.get("ema50", [])

        if ema20_all and len(ema20_all) >= n:
            ema20_slice = ema20_all[-n:]
            valid_x = [i for i, v in enumerate(ema20_slice) if v is not None]
            valid_y = [v for v in ema20_slice if v is not None]
            ax_main.plot(valid_x, valid_y, color="#f59e0b", linewidth=1.4, label="EMA 20", zorder=4)

        if ema50_all and len(ema50_all) >= n:
            ema50_slice = ema50_all[-n:]
            valid_x = [i for i, v in enumerate(ema50_slice) if v is not None]
            valid_y = [v for v in ema50_slice if v is not None]
            ax_main.plot(valid_x, valid_y, color="#3b82f6", linewidth=1.4, label="EMA 50", zorder=4)

        # VWAP Çizgisi
        vwap_all = indicators.get("vwap", [])
        if vwap_all and len(vwap_all) >= n:
            vwap_slice = vwap_all[-n:]
            ax_main.plot(indices, vwap_slice, color="#c084fc", linewidth=1.5, linestyle=":", label="VWAP", zorder=4)

        # SMC: Fair Value Gap (FVG) Alanı Çizimi
        smc = setup.get("smc_data", {})
        fvg_data = smc.get("fvg", {})
        active_fvg = fvg_data.get("bullish_fvg") if direction == "LONG" else fvg_data.get("bearish_fvg")
        if active_fvg:
            fvg_col = "#10b981" if direction == "LONG" else "#ef4444"
            ax_main.axhspan(active_fvg["bottom"], active_fvg["top"], color=fvg_col, alpha=0.15, label=f"SMC FVG Bölgesi")

        # Fiyat Seviyeleri (Giriş, SL, TP1, TP2)
        entry_p = setup["current_price"]
        sl_p = setup["stop_loss"]
        tp1_p = setup["take_profit_1"]
        tp2_p = setup["take_profit_2"]

        ax_main.axhline(entry_p, color="#ffffff", linestyle="--", linewidth=1.2, label=f"Giriş: {entry_p}", alpha=0.9)
        ax_main.axhline(sl_p, color="#f23645", linestyle="-", linewidth=1.5, label=f"SL (-{setup['sl_pct']}%): {sl_p}")
        ax_main.axhline(tp1_p, color="#10b981", linestyle="--", linewidth=1.3, label=f"TP 1: {tp1_p}")
        ax_main.axhline(tp2_p, color="#059669", linestyle="-", linewidth=1.5, label=f"TP 2 (+{setup['tp2_pct']}%): {tp2_p}")

        ax_main.legend(loc="upper left", facecolor="#131722", edgecolor="#2a2e39", labelcolor="#d1d4dc", fontsize=8)

        # Başlık ve Rozet
        leverage = setup.get("leverage", 10)
        timeframe = setup.get("timeframe", "15m")
        score = setup.get("confluence_score", 0)
        score_badge = f" [SMC Skor: {score}/100]" if score else ""
        lev_badge = f"{timeframe} [20x SNIPER SCALP]" if leverage == 20 else f"{timeframe} [10x HIZLI SCALP]"
        dir_color = "#38bdf8" if leverage == 20 else (up_color if direction == "LONG" else down_color)
        title = f"{symbol}  |  {direction} ({lev_badge}{score_badge})  |  R:R = 1:{setup['risk_reward']}"
        ax_main.set_title(title, fontsize=11, fontweight="bold", color=dir_color, pad=12)

        # 2. RSI PANELİ
        rsi_all = indicators.get("rsi", [])
        if rsi_all and len(rsi_all) >= n:
            rsi_slice = rsi_all[-n:]
            ax_rsi.plot(indices, rsi_slice, color="#a855f7", linewidth=1.5, label="RSI(14)")
            ax_rsi.axhline(70, color="#ef4444", linestyle=":", alpha=0.7)
            ax_rsi.axhline(30, color="#22c55e", linestyle=":", alpha=0.7)
            ax_rsi.set_ylim(15, 85)
            ax_rsi.set_ylabel("RSI", color="#848e9c", fontsize=9)

        # 3. HACİM (VOLUME) PANELİ
        volumes = [c["volume"] for c in plot_candles]
        vol_colors = [up_color if c["close"] >= c["open"] else down_color for c in plot_candles]
        ax_vol.bar(indices, volumes, color=vol_colors, alpha=0.7, width=0.7)
        ax_vol.set_ylabel("Hacim", color="#848e9c", fontsize=9)

        # X ekseni etiketleri (Tarih / Saat)
        step = max(1, n // 6)
        x_ticks = indices[::step]
        x_labels = [
            datetime.fromtimestamp(plot_candles[i]["timestamp"] / 1000).strftime("%m-%d %H:%M")
            for i in x_ticks
        ]
        ax_vol.set_xticks(x_ticks)
        ax_vol.set_xticklabels(x_labels, rotation=0, color="#848e9c", fontsize=8)

        # Kaydet ve temizle
        plt.tight_layout()
        fig.savefig(filepath, dpi=120, facecolor=fig.get_facecolor(), edgecolor="none")
        plt.close(fig)

        return filepath

