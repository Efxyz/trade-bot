"""
Autonomous Self-Tuning & Adaptive Strategy Engine (Otonom Öğrenen & Kalibrasyon Motoru)
Quant Hedge Fund Adaptive Policy Model:
- Son 30-50 işlemin performansını analiz eder.
- Kazanma oranı, kâr faktörü, ortalama kâr/zarar ve matematiksel beklentiyi (Expectancy) hesaplar.
- SMC kalite barajını, dinamik stop mesafelerini, BTC chop eşiğini ve merdiven tetiklerini optimize eder.
- Değiştirilemez Güvenlik Anayasası (Immutable Guardrails) ile kasayı korur (Max %2 risk, max 20x kaldıraç).
"""
import os
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from core.database import (
    get_db_connection,
    save_tuning_log_db,
    get_latest_tuning_log_db
)
from config import (
    DATA_DIR,
    MIN_CONFLUENCE_SCORE,
    MIN_SCALP_SL_PCT,
    MAX_SCALP_SL_PCT,
    BTC_CHOP_MIN_RANGE_4H_PCT,
    LADDER_DYNAMIC_CHANNEL_PCT,
    MAX_HOLD_MINUTES,
    RISK_PER_TRADE_PCT,
    MAX_CONCURRENT_TRADES
)

ADAPTIVE_CONFIG_PATH = DATA_DIR / "adaptive_hyperparams.json"

# ========================================================
# 🛡️ DEĞİŞTİRİLEMEZ GÜVENLİK ANAYASASI (IMMUTABLE GUARDRAILS)
# Yapay zeka veya optimizasyon motoru bu sınırları ASLA aşamaz!
# ========================================================
SAFETY_GUARDRAILS = {
    "MAX_RISK_PER_TRADE_PCT": 2.0,       # Asla %2'nin üzerine çıkamaz
    "MAX_CONCURRENT_TRADES_HARD": 2,     # Asla 2'den fazla eşzamanlı pozisyon açamaz
    "MAX_LEVERAGE_ALLOWED": 20,          # Asla 20x'in üzerine çıkamaz
    "MAX_DAILY_DRAWDOWN_PCT": 6.0,       # Günlük %6 kayıpta sistem otomatik kilitlenir
    "MIN_SL_FLOOR_PCT": 0.80,            # Stop mesafesi gürültüye ezilmemek için %0.80'den dar olamaz
    "MAX_SL_CEILING_PCT": 1.60           # Stop mesafesi %1.60'tan geniş olamaz
}

class SelfTuningEngine:
    """Geçmiş işlemleri analiz edip strateji parametrelerini otonom kalibre eden motor."""

    @staticmethod
    def get_current_params() -> Dict:
        """Mevcut aktif adaptif parametreleri döner (Varsayılan veya kalibre edilmiş)."""
        defaults = {
            "min_confluence_score": MIN_CONFLUENCE_SCORE,
            "min_scalp_sl_pct": MIN_SCALP_SL_PCT,
            "max_scalp_sl_pct": MAX_SCALP_SL_PCT,
            "btc_chop_min_range_4h_pct": BTC_CHOP_MIN_RANGE_4H_PCT,
            "ladder_dynamic_channel_pct": LADDER_DYNAMIC_CHANNEL_PCT,
            "max_hold_minutes": MAX_HOLD_MINUTES,
            "risk_per_trade_pct": RISK_PER_TRADE_PCT,
            "max_concurrent_trades": MAX_CONCURRENT_TRADES,
            "last_calibrated_at": "Henüz kalibrasyon yapılmadı (Varsayılan ayarlar)",
            "adaptation_level": "Base Standard"
        }
        if ADAPTIVE_CONFIG_PATH.exists():
            try:
                with open(ADAPTIVE_CONFIG_PATH, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                    defaults.update(saved)
            except Exception:
                pass
        return defaults

    @classmethod
    def run_calibration_cycle(cls, min_trades_required: int = 10) -> Dict:
        """
        Son işlemleri inceler, matematiksel beklentiyi (Expectancy) hesaplar
        ve stratejiyi en karlı parametrelere kalibre eder.
        """
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, symbol, direction, status, simulated_pnl_pct, gross_pnl_pct, fee_pct,
                       ladder_step, created_at, closed_at
                FROM signals
                WHERE status NOT IN ('ACTIVE', 'PENDING_ENTRY', 'ACTIVE_BE', 'ACTIVE_LADDER')
                  AND simulated_pnl_pct IS NOT NULL
                ORDER BY id DESC
                LIMIT 50
            """)
            trades = [dict(r) for r in cursor.fetchall()]

        total_trades = len(trades)
        if total_trades < min_trades_required:
            curr_p = cls.get_current_params()
            return {
                "status": "INSUFFICIENT_DATA",
                "message": f"Kalibrasyon için en az {min_trades_required} tamamlanmış işlem gerekli (Şu an: {total_trades}).",
                "summary": f"Henüz yeterli kapalı işlem verisi yok ({total_trades}/{min_trades_required}). Sistem varsayılan güvenli parametrelerle çalışıyor.",
                "health_score": 75,
                "trades_analyzed": total_trades,
                "win_rate": 50.0,
                "profit_factor": 1.0,
                "expectancy": 0.0,
                "current_params": curr_p,
                "tuned_params": curr_p
            }

        # 1. TEMEL PERFORMANS METRİKLERİ
        wins = [t for t in trades if (t["simulated_pnl_pct"] or 0) > 0]
        losses = [t for t in trades if (t["simulated_pnl_pct"] or 0) < 0]
        timeouts = [t for t in trades if t["status"] == "TIMEOUT_EXIT"]
        ladders = [t for t in trades if "LADDER" in (t["status"] or "")]

        win_count = len(wins)
        loss_count = len(losses)
        win_rate = (win_count / total_trades) * 100.0 if total_trades > 0 else 0.0

        avg_win = (sum(t["simulated_pnl_pct"] for t in wins) / win_count) if win_count > 0 else 0.0
        avg_loss = abs(sum(t["simulated_pnl_pct"] for t in losses) / loss_count) if loss_count > 0 else 0.0

        profit_factor = (sum(t["simulated_pnl_pct"] for t in wins) / sum(abs(t["simulated_pnl_pct"]) for t in losses)) if loss_count > 0 and sum(abs(t["simulated_pnl_pct"]) for t in losses) > 0 else 1.0
        
        # Matematiksel Beklenti (Expectancy E = (W% * AvgWin) - (L% * AvgLoss))
        expectancy = ((win_rate / 100.0) * avg_win) - (((100.0 - win_rate) / 100.0) * avg_loss)

        # 2. ADAPTİF PARAMETRE AYARLAMA (SELF-TUNING HEURISTICS)
        current = cls.get_current_params()
        tuned = dict(current)
        changes = []

        # A) Confluence Barajı Kalibrasyonu
        if win_rate < 48.0 or expectancy < 0.0:
            # Kazanma oranı zayıfsa barajı yükselt (Sadece kusursuz sinyaller)
            new_score = min(82, current.get("min_confluence_score", 76) + 2)
            if new_score != current.get("min_confluence_score"):
                tuned["min_confluence_score"] = new_score
                changes.append(f"Zayıf win-rate (%{win_rate:.1f}) nedeniyle SMC kalite barajı {new_score}/100 seviyesine yükseltildi.")
        elif win_rate >= 62.0 and expectancy > 1.5:
            # Çok yüksek başarı varsa hafif gevşetip daha çok fırsat yakala
            new_score = max(76, current.get("min_confluence_score", 76) - 1)
            if new_score != current.get("min_confluence_score"):
                tuned["min_confluence_score"] = new_score
                changes.append(f"Yüksek win-rate (%{win_rate:.1f}) ödülü: SMC barajı {new_score}/100 seviyesine optimize edildi.")

        # B) Stop-Loss Mesafesi Kalibrasyonu (Fitil Koruması)
        # Hızlı stop olan işlemler çoksa (%1.0'den dar stoplar gürültüye gidiyorsa)
        quick_losses = [t for t in losses if t["status"] == "HIT_SL" and (t["simulated_pnl_pct"] or 0) <= -12.0]
        if len(quick_losses) >= 3:
            new_sl_min = min(SAFETY_GUARDRAILS["MAX_SL_CEILING_PCT"], round(current.get("min_scalp_sl_pct", 0.95) + 0.10, 2))
            if new_sl_min != current.get("min_scalp_sl_pct"):
                tuned["min_scalp_sl_pct"] = new_sl_min
                changes.append(f"Likidite fitili kayıpları tespit edildi: Minimum stop payı %{new_sl_min:.2f} seviyesine genişletildi (Gürültü Koruması).")

        # C) BTC Chop Kalkanı Kalibrasyonu
        # Eğer zaman aşımı (TIMEOUT) kayıpları toplam işlemlerin %30'unu geçiyorsa piyasa yatay demektir
        if len(timeouts) / total_trades > 0.28:
            new_chop = round(min(1.20, current.get("btc_chop_min_range_4h_pct", 0.80) + 0.05), 2)
            if new_chop != current.get("btc_chop_min_range_4h_pct"):
                tuned["btc_chop_min_range_4h_pct"] = new_chop
                changes.append(f"Yatay piyasa zaman aşımları yüksek (%{len(timeouts)/total_trades*100:.0f}): BTC Dead Chop kalkanı %{new_chop:.2f} eşiğine sıkılaştırıldı.")

        # D) Merdiven Kâr Kanalı İyileştirmesi
        if len(ladders) >= 5 and avg_win < 4.0:
            new_channel = round(max(0.18, current.get("ladder_dynamic_channel_pct", 0.25) - 0.03), 2)
            tuned["ladder_dynamic_channel_pct"] = new_channel
            changes.append(f"Merdiven stop takip kanalı %{new_channel:.2f} olarak daraltıldı (Zirveden dönüşte daha çok kâr cebte kalacak).")

        # 3. GÜVENLİK ANAYASASI DENETİMİ (ENFORCE IMMUTABLE BOUNDS)
        tuned["risk_per_trade_pct"] = min(SAFETY_GUARDRAILS["MAX_RISK_PER_TRADE_PCT"], tuned.get("risk_per_trade_pct", 2.0))
        tuned["max_concurrent_trades"] = min(SAFETY_GUARDRAILS["MAX_CONCURRENT_TRADES_HARD"], tuned.get("max_concurrent_trades", 2))
        tuned["min_scalp_sl_pct"] = max(SAFETY_GUARDRAILS["MIN_SL_FLOOR_PCT"], min(SAFETY_GUARDRAILS["MAX_SL_CEILING_PCT"] - 0.25, tuned.get("min_scalp_sl_pct", 1.0)))
        if tuned.get("min_scalp_sl_pct", 1.0) >= tuned.get("max_scalp_sl_pct", 1.35):
            tuned["max_scalp_sl_pct"] = round(tuned["min_scalp_sl_pct"] + 0.30, 2)
        tuned["max_scalp_sl_pct"] = min(SAFETY_GUARDRAILS["MAX_SL_CEILING_PCT"], tuned.get("max_scalp_sl_pct", 1.45))
        tuned["last_calibrated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        tuned["adaptation_level"] = "Self-Calibrated Active"

        # Sağlık Skoru (0-100)
        health_score = int(min(100, max(20, (win_rate * 0.5) + (profit_factor * 20.0) + (expectancy * 10.0))))

        summary_text = " | ".join(changes) if changes else "Mevcut parametreler piyasa rejimiyle tam uyumlu. Değişikliğe gerek duyulmadı."

        # Dosyaya kaydet
        try:
            with open(ADAPTIVE_CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(tuned, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"⚠️ [SelfTuning] Config yazma hatası: {e}")

        # Veritabanına kaydet
        try:
            save_tuning_log_db(
                trades_analyzed=total_trades,
                win_rate=round(win_rate, 2),
                profit_factor=round(profit_factor, 2),
                expectancy=round(expectancy, 2),
                tuning_summary=summary_text,
                params_dict=tuned
            )
        except Exception as e:
            print(f"⚠️ [SelfTuning] DB kayıt hatası: {e}")

        return {
            "status": "SUCCESS",
            "trades_analyzed": total_trades,
            "win_rate": round(win_rate, 2),
            "profit_factor": round(profit_factor, 2),
            "expectancy": round(expectancy, 2),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "health_score": health_score,
            "changes": changes,
            "summary": summary_text,
            "tuned_params": tuned,
            "guardrails_status": "LOCKED_AND_VERIFIED",
            "calibrated_at": tuned["last_calibrated_at"]
        }
