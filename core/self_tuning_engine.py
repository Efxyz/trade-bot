"""
Autonomous Self-Tuning & Adaptive Strategy Engine (Otonom Kendi Kendini Eğiten & Kalibrasyon Motoru)
Quant Hedge Fund Adaptive Policy Model:
- Son tamamlanan işlemleri (15m Ana Bot, 1m FAST Bot ve SÜPER FAST Bot) çoklu zaman diliminde birleştirerek analiz eder.
- Causal Loss Attribution (Kök Neden Analizi): Kayıpların fitil avı, testere zaman aşımı veya trend dönüşü olup olmadığını ayrıştırır.
- Market Regime Diagnosis: Piyasanın yönsel momentumunu ve volatilite rejimini saptar.
- Counterfactual Simulation: Hangi stop payı ve SMC barajının kârı maksimize edeceğini simüle eder.
- OTONOM ONAY & OTOMATİK EĞİTİM: İnsan müdahalesine gerek duymadan güvenli parametreleri otomatik onaylar ve canlıya alır.
- OTONOM ÖĞRENME RAPORLARI: Çıkarılan kurumsal dersleri, hipotezleri ve parametre deltalarını raporlayıp kalıcı hafızaya yazar.
- Değiştirilemez Güvenlik Anayasası (Immutable Guardrails) ile kasayı korur (Max %2 risk, max 20x kaldıraç).
"""
import os
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from core.database import (
    get_db_connection,
    save_tuning_log_db,
    get_latest_tuning_log_db,
    save_learning_report_db,
    get_learning_reports_db
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
    MAX_CONCURRENT_TRADES,
    ENABLE_FAST_ENGINE,
    ENABLE_SUPER_FAST_ENGINE
)

ADAPTIVE_CONFIG_PATH = DATA_DIR / "adaptive_hyperparams.json"

# ========================================================
# 🛡️ DEĞİŞTİRİLEMEZ GÜVENLİK ANAYASASI (IMMUTABLE GUARDRAILS)
# Yapay zeka veya optimizasyon motoru bu sınırları ASLA aşamaz!
# ========================================================
SAFETY_GUARDRAILS = {
    "MAX_RISK_PER_TRADE_PCT": 2.0,                   # Asla %2'nin üzerine çıkamaz
    "MAX_CONCURRENT_TRADES_HARD": MAX_CONCURRENT_TRADES,  # Ana bot eşzamanlı pozisyon sınırı
    "MAX_LEVERAGE_ALLOWED": 20,                      # Asla 20x'in üzerine çıkamaz
    "MAX_DAILY_DRAWDOWN_PCT": 6.0,                   # Günlük %6 kayıpta sistem kilitlenir
    "MIN_SL_FLOOR_PCT": 0.80,                        # Stop mesafesi gürültüye ezilmemek için %0.80'den dar olamaz
    "MAX_SL_CEILING_PCT": 1.60,                      # Stop mesafesi %1.60'tan geniş olamaz
    "MIN_CONFLUENCE_FLOOR": 58,                      # Confluence tabanı 58'den düşük olamaz
    "MAX_CONFLUENCE_CEILING": 68,                    # Confluence tavanı felç olmamak için 68'den yüksek olamaz
    "MAX_BTC_CHOP_CEILING": 0.85                     # BTC Chop tavanı kilitlenmeyi önlemek için %0.85'ten yüksek olamaz
}

class SelfTuningEngine:
    """Geçmiş işlemleri analiz edip kendini otonom eğiten ve parametreleri optimize eden motor."""

    @staticmethod
    def get_current_params() -> Dict:
        """Mevcut aktif adaptif parametreleri döner (Varsayılan veya v2 kalibre edilmiş)."""
        defaults = {
            "schema_version": 2,
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
                if isinstance(saved, dict) and saved.get("schema_version") == 2:
                    defaults.update(saved)
                else:
                    # Eski v1 kirlenmiş parametreleri (kapalı 1m/1s botlardan gelen) sıfırla
                    with open(ADAPTIVE_CONFIG_PATH, "w", encoding="utf-8") as fw:
                        json.dump(defaults, fw, indent=4, ensure_ascii=False)
            except Exception:
                pass

        # 🛡️ Güvenlik Tavanı Koruması
        if defaults.get("min_confluence_score", 65) > SAFETY_GUARDRAILS["MAX_CONFLUENCE_CEILING"]:
            defaults["min_confluence_score"] = SAFETY_GUARDRAILS["MAX_CONFLUENCE_CEILING"]
        if defaults.get("min_confluence_score", 65) < SAFETY_GUARDRAILS["MIN_CONFLUENCE_FLOOR"]:
            defaults["min_confluence_score"] = SAFETY_GUARDRAILS["MIN_CONFLUENCE_FLOOR"]
        if defaults.get("btc_chop_min_range_4h_pct", 0.70) > SAFETY_GUARDRAILS["MAX_BTC_CHOP_CEILING"]:
            defaults["btc_chop_min_range_4h_pct"] = SAFETY_GUARDRAILS["MAX_BTC_CHOP_CEILING"]

        return defaults

    @classmethod
    def get_all_completed_trades(cls, limit_per_bot: int = 40) -> List[Dict]:
        """Yalnızca aktif motorların tamamlanmış kapalı işlemlerini toplar."""
        all_trades = []
        sources = [("signals", "15m_STANDART")]
        if ENABLE_FAST_ENGINE:
            sources.append(("fast_signals", "1m_FAST"))
        if ENABLE_SUPER_FAST_ENGINE:
            sources.append(("super_fast_signals", "SÜPER_FAST_HFT"))
        with get_db_connection() as conn:
            cursor = conn.cursor()
            for table, bot_name in sources:
                try:
                    cursor.execute(f"""
                        SELECT id, symbol, direction, status, simulated_pnl_pct, gross_pnl_pct, fee_pct,
                               ladder_step, created_at, closed_at
                        FROM {table}
                        WHERE status NOT IN ('ACTIVE', 'PENDING_ENTRY', 'ACTIVE_BE', 'ACTIVE_LADDER')
                          AND simulated_pnl_pct IS NOT NULL
                        ORDER BY id DESC
                        LIMIT ?
                    """, (limit_per_bot,))
                    for r in cursor.fetchall():
                        d = dict(r)
                        d["bot_source"] = bot_name
                        all_trades.append(d)
                except Exception:
                    pass

        # Tarihe göre en yeniden en eskiye sırala
        all_trades.sort(key=lambda x: str(x.get("closed_at") or x.get("created_at") or ""), reverse=True)
        return all_trades

    @classmethod
    def analyze_loss_attribution(cls, losses: List[Dict]) -> Dict:
        """Kayıpların altında yatan kök nedenleri analiz eder (Causal Attribution)."""
        if not losses:
            return {"wick_hunt_pct": 0, "timeout_pct": 0, "reversal_pct": 0, "be_friction_pct": 0, "summary": "Kayıp işlem yok."}

        total_loss = len(losses)
        wick_hunt = 0
        timeout = 0
        reversal = 0
        be_friction = 0

        for t in losses:
            status = t.get("status", "")
            pnl = t.get("simulated_pnl_pct") or 0.0
            
            # Zaman farkı hesabı
            duration_mins = 30
            try:
                c_at = datetime.fromisoformat(str(t.get("created_at")).replace(" ", "T"))
                cl_at = datetime.fromisoformat(str(t.get("closed_at")).replace(" ", "T"))
                duration_mins = (cl_at - c_at).total_seconds() / 60.0
            except Exception:
                pass

            if status == "TIMEOUT_EXIT":
                timeout += 1
            elif status == "CLOSED_BE" or abs(pnl) < 1.0:
                be_friction += 1
            elif status == "HIT_SL" and duration_mins < 15:
                wick_hunt += 1
            else:
                reversal += 1

        wick_pct = round((wick_hunt / total_loss) * 100.0, 1)
        to_pct = round((timeout / total_loss) * 100.0, 1)
        rev_pct = round((reversal / total_loss) * 100.0, 1)
        be_pct = round((be_friction / total_loss) * 100.0, 1)

        summary_parts = []
        if wick_pct > 25:
            summary_parts.append(f"Kayıpların %{wick_pct}'i girişten sonraki ilk 15dk içinde likidite avı fitillerinden kaynaklandı.")
        if to_pct > 25:
            summary_parts.append(f"Kayıpların %{to_pct}'i yatay testere piyasasında zaman aşımına uğradı.")
        if rev_pct > 30:
            summary_parts.append(f"Kayıpların %{rev_pct}'i sert trend kırılımı ve momentum dönüşüyle gerçekleşti.")
        if be_pct > 20:
            summary_parts.append(f"Kayıpların %{be_pct}'i başa-baş stopta komisyon erimesi nedeniyle oluştu.")

        if not summary_parts:
            summary_parts.append("Kayıp dağılımı normal sınırlarında dengeli seyrediyor.")

        return {
            "wick_hunt_pct": wick_pct,
            "timeout_pct": to_pct,
            "reversal_pct": rev_pct,
            "be_friction_pct": be_pct,
            "total_losses": total_loss,
            "summary": " ".join(summary_parts)
        }

    @classmethod
    def diagnose_market_regime(cls, trades: List[Dict]) -> Dict:
        """İşlem sonuçları ve yönsel başarıdan anlık piyasa rejimini teşhis eder."""
        if not trades:
            return {"regime_name": "Belirsiz / Veri Yok", "bias": "BALANCED", "summary": "Yeterli veri yok."}

        shorts = [t for t in trades if t.get("direction") == "SHORT"]
        longs = [t for t in trades if t.get("direction") == "LONG"]

        short_wins = len([t for t in shorts if (t.get("simulated_pnl_pct") or 0) > 0])
        long_wins = len([t for t in longs if (t.get("simulated_pnl_pct") or 0) > 0])

        short_wr = (short_wins / len(shorts) * 100.0) if shorts else 50.0
        long_wr = (long_wins / len(longs) * 100.0) if longs else 50.0

        timeouts = len([t for t in trades if t.get("status") == "TIMEOUT_EXIT"])
        timeout_ratio = timeouts / len(trades) if trades else 0.0

        if timeout_ratio >= 0.35:
            regime = "Düşük Volatiliteli Yatay Testere (Dead Chop)"
            bias = "NEUTRAL"
            summary = "Piyasada likidite sıkışması ve yön kararsızlığı hakim. Testere tuzağı riski yüksek."
        elif short_wr >= 70.0 and long_wr < 45.0:
            regime = "Ayı Baskılı Trend & SHORT Üstünlüğü"
            bias = "SHORT_FAVORED"
            summary = "Piyasada genel satış baskısı hakim; SHORT pozisyonlar TP'ye koşarken LONG denemeleri ezilmektedir."
        elif long_wr >= 70.0 and short_wr < 45.0:
            regime = "Güçlü Boğa İvmesi & LONG Üstünlüğü"
            bias = "LONG_FAVORED"
            summary = "Alıcılar piyasaya hakim; LONG işlemler yüksek momentumla kâr üretmektedir."
        else:
            regime = "Çift Yönlü Dinamik Salınım (Mean-Reverting)"
            bias = "BALANCED"
            summary = "Piyasa iki yönlü kanal içinde salınıyor; destek ve direnç tepkileri organik çalışıyor."

        return {
            "regime_name": regime,
            "bias": bias,
            "short_win_rate": round(short_wr, 1),
            "long_win_rate": round(long_wr, 1),
            "timeout_ratio_pct": round(timeout_ratio * 100.0, 1),
            "summary": summary
        }

    @classmethod
    def run_autonomous_training_cycle(cls, min_trades_required: int = 5, auto_commit: bool = True) -> Dict:
        """
        Kendi kendini eğiten otonom öğrenme döngüsü:
        1. 3 botun tüm kapalı işlemlerini inceler.
        2. Kök neden ve piyasa rejim analizi yapar.
        3. Matematiksel beklentiyi (Expectancy) maksimize edecek parametreleri hesaplar.
        4. GÜVENLİK ANAYASASINI denetler (Max %2 risk asla aşılamaz).
        5. Otomatik onaylar, yapılandırmaya yazar ve kalıcı öğrenme raporunu DB'ye kaydeder.
        """
        tr_tz = timezone(timedelta(hours=3))
        now_tr = datetime.now(timezone.utc).astimezone(tr_tz)
        time_str = now_tr.strftime("%H:%M:%S")
        date_str = now_tr.strftime("%Y-%m-%d %H:%M:%S")

        trades = cls.get_all_completed_trades(limit_per_bot=30)
        total_trades = len(trades)
        current = cls.get_current_params()

        # Mevcut epoch sayısını hesapla (Tablonun varlığını garantiye al)
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS autonomous_learning_reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    time_str TEXT NOT NULL,
                    epoch_num INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    health_score INTEGER NOT NULL,
                    trades_analyzed INTEGER NOT NULL,
                    win_rate REAL NOT NULL,
                    profit_factor REAL NOT NULL,
                    expectancy REAL NOT NULL,
                    regime_diagnosis TEXT NOT NULL,
                    loss_attribution_json TEXT NOT NULL,
                    win_factors_json TEXT NOT NULL,
                    hypotheses_json TEXT NOT NULL,
                    parameter_deltas_json TEXT NOT NULL,
                    summary TEXT NOT NULL
                )
            """)
            cursor.execute("SELECT COUNT(*) FROM autonomous_learning_reports")
            epoch_num = (cursor.fetchone()[0] or 0) + 1

        if total_trades < min_trades_required:
            report_payload = {
                "epoch_num": epoch_num,
                "status": "INSUFFICIENT_DATA",
                "health_score": 75,
                "trades_analyzed": total_trades,
                "win_rate": 50.0,
                "profit_factor": 1.0,
                "expectancy": 0.0,
                "regime_diagnosis": "Yeterli kapalı işlem verisi henüz toplanmadı.",
                "loss_attribution": [],
                "win_factors": [],
                "hypotheses": [
                    "💡 [Veri Toplama]: Otonom öğrenmenin ilk kalibrasyon döngüsünü tamamlaması için en az 5 kapalı işlem bekleniyor.",
                    "🛡️ [Güvenlik Protokolü]: Sistem şu an varsayılan defansif parametrelerle (%2.0 risk tavanı, 65 kalite barajı) çalışmaktadır."
                ],
                "parameter_deltas": [],
                "summary": f"Henüz yeterli işlem verisi yok ({total_trades}/{min_trades_required}). Sistem varsayılan parametrelerle çalışmaya devam ediyor.",
                "current_params": current,
                "tuned_params": current,
                "calibrated_at": date_str
            }
            save_learning_report_db(report_payload)
            return report_payload

        # 1. PERFORMANS METRİKLERİ
        wins = [t for t in trades if (t.get("simulated_pnl_pct") or 0) > 0]
        losses = [t for t in trades if (t.get("simulated_pnl_pct") or 0) < 0]
        win_count = len(wins)
        loss_count = len(losses)
        win_rate = (win_count / total_trades) * 100.0 if total_trades > 0 else 0.0

        avg_win = (sum(t.get("simulated_pnl_pct") or 0 for t in wins) / win_count) if win_count > 0 else 0.0
        avg_loss = abs(sum(t.get("simulated_pnl_pct") or 0 for t in losses) / loss_count) if loss_count > 0 else 0.0

        profit_factor = (sum(t.get("simulated_pnl_pct") or 0 for t in wins) / sum(abs(t.get("simulated_pnl_pct") or 0) for t in losses)) if loss_count > 0 and sum(abs(t.get("simulated_pnl_pct") or 0) for t in losses) > 0 else 1.0
        profit_factor = min(20.0, round(profit_factor, 2))

        # Matematiksel Beklenti (Expectancy E = (W% * AvgWin) - (L% * AvgLoss))
        expectancy = ((win_rate / 100.0) * avg_win) - (((100.0 - win_rate) / 100.0) * avg_loss)
        expectancy = round(expectancy, 2)

        # 2. KÖK NEDEN & REJİM ANALİZİ
        loss_analysis = cls.analyze_loss_attribution(losses)
        regime_diag = cls.diagnose_market_regime(trades)

        # 3. KENDİNİ EĞİTME & PARAMETRE OPTİMİZASYON MANTIĞI
        tuned = dict(current)
        param_deltas = []
        hypotheses = []

        # A) Confluence Barajı Adaptasyonu
        curr_conf = current.get("min_confluence_score", 65)
        if win_rate < 55.0 or expectancy < 0.0:
            new_conf = min(SAFETY_GUARDRAILS["MAX_CONFLUENCE_CEILING"], curr_conf + 1)
            if new_conf != curr_conf:
                tuned["min_confluence_score"] = new_conf
                param_deltas.append({
                    "param_name": "SMC Kalite Barajı",
                    "key": "min_confluence_score",
                    "old_val": curr_conf,
                    "new_val": new_conf,
                    "delta": f"+{new_conf - curr_conf}",
                    "reason": f"Düşük kazanma oranı (%{win_rate:.1f}) nedeniyle kalite çıtası yükseltildi."
                })
                hypotheses.append(f"💡 [Kalite Optimizasyonu]: Kazanma oranını %65+ üzerine çekmek için minimum SMC giriş barajı {new_conf}/100 seviyesine yükseltildi; zayıf sinyaller ayıklandı.")
        elif win_rate >= 65.0 and expectancy >= 0.40:
            new_conf = max(SAFETY_GUARDRAILS["MIN_CONFLUENCE_FLOOR"], min(curr_conf - 1, 64))
            if new_conf != curr_conf:
                tuned["min_confluence_score"] = new_conf
                param_deltas.append({
                    "param_name": "SMC Kalite Barajı",
                    "key": "min_confluence_score",
                    "old_val": curr_conf,
                    "new_val": new_conf,
                    "delta": f"-{curr_conf - new_conf}",
                    "reason": f"Yüksek başarı (%{win_rate:.1f}) ve pozitif beklenti (E: {expectancy:+.2f}%) ile fırsat akışı genişletildi."
                })
                hypotheses.append(f"💡 [Alfa Genişlemesi]: Sistem %{win_rate:.1f} kazanma oranıyla yüksek alfa ürettiğinden SMC barajı {new_conf}/100 seviyesine optimize edilerek daha fazla karlı kurulum yakalanması hedeflendi.")

        # B) Stop Mesafesi (Fitil Avı Koruması & Simetrik Gevşeme)
        curr_sl_min = current.get("min_scalp_sl_pct", MIN_SCALP_SL_PCT)
        if loss_analysis.get("wick_hunt_pct", 0) >= 25.0:
            new_sl_min = min(SAFETY_GUARDRAILS["MAX_SL_CEILING_PCT"] - 0.20, round(curr_sl_min + 0.10, 2))
            if new_sl_min != curr_sl_min:
                tuned["min_scalp_sl_pct"] = new_sl_min
                param_deltas.append({
                    "param_name": "Fitil Korumalı Stop",
                    "key": "min_scalp_sl_pct",
                    "old_val": curr_sl_min,
                    "new_val": new_sl_min,
                    "delta": f"+%{round(new_sl_min - curr_sl_min, 2)}",
                    "reason": "Likidite fitili kayıplarını bertaraf etmek için stop payı genişletildi."
                })
                hypotheses.append(f"💡 [Likidite Kalkanı]: Kayıpların %{loss_analysis.get('wick_hunt_pct')}'i erken fitillerden kaynaklandığı için stop payı %{new_sl_min:.2f}'ye genişletildi; piyasa gürültüsüne kurban gitme riski önlendi.")
        elif loss_analysis.get("wick_hunt_pct", 0) < 20.0 and curr_sl_min > MIN_SCALP_SL_PCT:
            new_sl_min = max(MIN_SCALP_SL_PCT, round(curr_sl_min - 0.10, 2))
            if new_sl_min != curr_sl_min:
                tuned["min_scalp_sl_pct"] = new_sl_min
                param_deltas.append({
                    "param_name": "Fitil Korumalı Stop",
                    "key": "min_scalp_sl_pct",
                    "old_val": curr_sl_min,
                    "new_val": new_sl_min,
                    "delta": f"-%{round(curr_sl_min - new_sl_min, 2)}",
                    "reason": f"Erken fitil oranı (%{loss_analysis.get('wick_hunt_pct')}) düşük olduğu için minimum stop tabanı normale çekildi."
                })
                hypotheses.append(f"💡 [Dar Stop Verimliliği]: Erken fitil avı %{loss_analysis.get('wick_hunt_pct')} seviyesine düştüğünden minimum stop tabanı %{new_sl_min:.2f}'ye indirildi; daha fazla kaliteli 15m kurulum önü açıldı.")

        # C) BTC Chop Kalkanı (Simetrik Gevşeme Dahil)
        curr_chop = current.get("btc_chop_min_range_4h_pct", BTC_CHOP_MIN_RANGE_4H_PCT)
        if loss_analysis.get("timeout_pct", 0) >= 30.0 or regime_diag.get("timeout_ratio_pct", 0) >= 30.0:
            new_chop = round(min(SAFETY_GUARDRAILS["MAX_BTC_CHOP_CEILING"], curr_chop + 0.05), 2)
            if new_chop != curr_chop:
                tuned["btc_chop_min_range_4h_pct"] = new_chop
                param_deltas.append({
                    "param_name": "BTC Dead Chop Eşiği",
                    "key": "btc_chop_min_range_4h_pct",
                    "old_val": curr_chop,
                    "new_val": new_chop,
                    "delta": f"+%{round(new_chop - curr_chop, 2)}",
                    "reason": "Yatay testere piyasasında gereksiz işlem ve zaman aşımını engellemek için sıkılaştırıldı."
                })
                hypotheses.append(f"💡 [Testere Kalkanı]: Pozisyonların %{loss_analysis.get('timeout_pct')}'i yatay piyasada takılı kaldığından 4s BTC Dead Chop eşiği %{new_chop:.2f}'ye sıkılaştırıldı.")
        elif loss_analysis.get("timeout_pct", 0) < 20.0 and curr_chop > BTC_CHOP_MIN_RANGE_4H_PCT:
            new_chop = round(max(BTC_CHOP_MIN_RANGE_4H_PCT, curr_chop - 0.05), 2)
            if new_chop != curr_chop:
                tuned["btc_chop_min_range_4h_pct"] = new_chop
                param_deltas.append({
                    "param_name": "BTC Dead Chop Eşiği",
                    "key": "btc_chop_min_range_4h_pct",
                    "old_val": curr_chop,
                    "new_val": new_chop,
                    "delta": f"-%{round(curr_chop - new_chop, 2)}",
                    "reason": f"Zaman aşımı oranı (%{loss_analysis.get('timeout_pct')}) düşük olduğu için BTC Dead Chop eşiği gevşetildi."
                })
                hypotheses.append(f"💡 [Tarama Genişlemesi]: Yatay sıkışma kayıpları düşük (%{loss_analysis.get('timeout_pct')}) olduğundan BTC Chop eşiği %{new_chop:.2f}'ye çekildi.")

        # D) Merdiven Kâr Kanalı İyileştirmesi
        curr_ladder_chan = current.get("ladder_dynamic_channel_pct", 0.25)
        ladders = [t for t in trades if "LADDER" in str(t.get("status") or "")]
        if len(ladders) >= 3 and avg_win < 3.5:
            new_ladder = round(max(0.18, curr_ladder_chan - 0.03), 2)
            if new_ladder != curr_ladder_chan:
                tuned["ladder_dynamic_channel_pct"] = new_ladder
                param_deltas.append({
                    "param_name": "Merdiven Takip Kanalı",
                    "key": "ladder_dynamic_channel_pct",
                    "old_val": curr_ladder_chan,
                    "new_val": new_ladder,
                    "delta": f"-%{round(curr_ladder_chan - new_ladder, 2)}",
                    "reason": "Zirveden dönüşte daha fazla kârın kasada kalması için takip kanalı daraltıldı."
                })
                hypotheses.append(f"💡 [Kâr Kilitleme]: Merdiven takip kanalı %{new_ladder:.2f} seviyesine daraltılarak kâr zirvelerinden dönüşte kazancın geri verilmesi engellendi.")

        # Eğer hiçbir parametre değişikliğine gerek yoksa genel optimallik hipotezi ekle
        if not hypotheses:
            hypotheses.append("💡 [Piyasa Uyumu]: Aktif parametreler mevcut piyasa rejiminde optimum düzeydedir. Aşırı uyumdan (overfitting) kaçınmak için parametreler korundu.")
            hypotheses.append(f"💡 [Kasa Disiplini]: Kazanma oranı %{win_rate:.1f} ve Matematiksel Beklenti E: {expectancy:+.2f}% ile kasayı koruyarak pozitif büyüme hedefleniyor.")

        # Rejim hipotezi ekle
        hypotheses.append(f"💡 [Piyasa Rejimi]: {regime_diag.get('regime_name')} - {regime_diag.get('summary')}")

        # 4. GÜVENLİK ANAYASASINI UYGULA (IMMUTABLE GUARDRAILS)
        tuned["schema_version"] = 2
        tuned["risk_per_trade_pct"] = min(SAFETY_GUARDRAILS["MAX_RISK_PER_TRADE_PCT"], tuned.get("risk_per_trade_pct", 2.0))
        if win_rate >= 60.0 and expectancy > 0.0:
            tuned["max_concurrent_trades"] = MAX_CONCURRENT_TRADES
        else:
            tuned["max_concurrent_trades"] = min(SAFETY_GUARDRAILS["MAX_CONCURRENT_TRADES_HARD"], tuned.get("max_concurrent_trades", MAX_CONCURRENT_TRADES))
        tuned["min_confluence_score"] = max(SAFETY_GUARDRAILS["MIN_CONFLUENCE_FLOOR"], min(SAFETY_GUARDRAILS["MAX_CONFLUENCE_CEILING"], tuned.get("min_confluence_score", MIN_CONFLUENCE_SCORE)))
        tuned["btc_chop_min_range_4h_pct"] = max(0.55, min(SAFETY_GUARDRAILS["MAX_BTC_CHOP_CEILING"], tuned.get("btc_chop_min_range_4h_pct", BTC_CHOP_MIN_RANGE_4H_PCT)))
        tuned["min_scalp_sl_pct"] = max(SAFETY_GUARDRAILS["MIN_SL_FLOOR_PCT"], min(SAFETY_GUARDRAILS["MAX_SL_CEILING_PCT"] - 0.20, tuned.get("min_scalp_sl_pct", MIN_SCALP_SL_PCT)))
        tuned["max_scalp_sl_pct"] = min(SAFETY_GUARDRAILS["MAX_SL_CEILING_PCT"], round(max(MAX_SCALP_SL_PCT, tuned["min_scalp_sl_pct"] + 0.30), 2))
        tuned["last_calibrated_at"] = date_str
        tuned["adaptation_level"] = "Autonomous Self-Trained Active"

        # Sağlık Skoru (0-100)
        health_score = int(min(100, max(25, (win_rate * 0.5) + (profit_factor * 20.0) + (expectancy * 12.0))))

        status_label = "AUTO_APPROVED" if param_deltas else "OPTIMAL_NO_CHANGE"
        summary_text = (
            f"Otonom Eğitim Döngüsü #{epoch_num} Tamamlandı: " +
            (" | ".join([f"{d['param_name']}: {d['old_val']} → {d['new_val']}" for d in param_deltas]) if param_deltas else "Parametreler mevcut rejim için ideal bulundu, korundu.")
        )

        # 5. OTONOM ONAY & DİSK/DB KAYDI
        if auto_commit:
            try:
                with open(ADAPTIVE_CONFIG_PATH, "w", encoding="utf-8") as f:
                    json.dump(tuned, f, indent=4, ensure_ascii=False)
            except Exception as e:
                print(f"⚠️ [SelfTuning] Config yazma hatası: {e}")

        # Raporu DB'ye kaydet
        report_data = {
            "epoch_num": epoch_num,
            "status": status_label,
            "health_score": health_score,
            "trades_analyzed": total_trades,
            "win_rate": round(win_rate, 2),
            "profit_factor": round(profit_factor, 2),
            "expectancy": expectancy,
            "regime_diagnosis": f"{regime_diag.get('regime_name')}: {regime_diag.get('summary')}",
            "loss_attribution": loss_analysis,
            "win_factors": [
                f"Toplam Kârlı İşlem: {win_count}/{total_trades} (%{win_rate:.1f})",
                f"Ortalama Kazanç: %{avg_win:.2f} | Ortalama Kayıp: %{avg_loss:.2f}",
                f"Yön Üstünlüğü: SHORT Win-Rate %{regime_diag.get('short_win_rate')} | LONG Win-Rate %{regime_diag.get('long_win_rate')}"
            ],
            "hypotheses": hypotheses,
            "parameter_deltas": param_deltas,
            "summary": summary_text
        }

        try:
            save_learning_report_db(report_data)
            save_tuning_log_db(
                trades_analyzed=total_trades,
                win_rate=round(win_rate, 2),
                profit_factor=round(profit_factor, 2),
                expectancy=expectancy,
                tuning_summary=summary_text,
                params_dict=tuned
            )
        except Exception as e:
            print(f"⚠️ [SelfTuning] DB kayıt hatası: {e}")

        report_data["current_params"] = current
        report_data["tuned_params"] = tuned
        report_data["calibrated_at"] = date_str
        report_data["changes"] = [d["reason"] for d in param_deltas]
        return report_data

    # Geriye dönük uyumluluk
    @classmethod
    def run_calibration_cycle(cls, min_trades_required: int = 5) -> Dict:
        return cls.run_autonomous_training_cycle(min_trades_required=min_trades_required, auto_commit=True)
