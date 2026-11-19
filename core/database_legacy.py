"""
Eski FAST (1m) ve SÜPER FAST (1s) motorlarının veritabanı katmanı.
Motorlar kapatıldı (config: ENABLE_FAST_ENGINE / ENABLE_SUPER_FAST_ENGINE = False); bu fonksiyonlar yalnızca
dashboard'daki geçmiş istatistik/sıfırlama uç noktaları için korunur. core.database üzerinden yeniden dışa aktarılır.
"""
import json
import random
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple, Union

from core.database import get_db_connection, reconcile_partial_pnl  # noqa: F401

# ==============================================================================
# ⚡ FAST BOT VERİTABANI VE İŞLEM YÖNETİM KATMANI (1m SERİ İŞLEMLER / BAĞIMSIZ KASA)
# ==============================================================================

def save_fast_signal(data: Dict) -> int:
    """FAST bot için yeni 1m hızlı scalping sinyalini kaydeder ve doğrudan aktif pozisyona alır."""
    import json
    with get_db_connection() as conn:
        cursor = conn.cursor()
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry_price = data.get("actual_entry_price") or data.get("current_price") or data["entry_min"]
        fast_meta_str = data.get("fast_meta")
        if isinstance(fast_meta_str, dict):
            fast_meta_str = json.dumps(fast_meta_str, ensure_ascii=False)
        elif not fast_meta_str:
            fast_meta_str = ""

        cursor.execute("""
            INSERT INTO fast_signals (
                symbol, direction, leverage, entry_min, entry_max,
                actual_entry_price, entered_at,
                stop_loss, take_profit_1, take_profit_2, risk_reward,
                risk_grade, news_summary, ta_reasons, chart_entry_png, status,
                allocated_margin_usdt, risk_usd, highest_price, lowest_price,
                fast_meta
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', ?, ?, ?, ?, ?)
        """, (
            data["symbol"], data["direction"], data.get("leverage", 10),
            data["entry_min"], data["entry_max"],
            entry_price, current_time,
            data["stop_loss"], data["take_profit_1"], data.get("take_profit_2", data["take_profit_1"]),
            data.get("risk_reward", 1.5), data.get("risk_grade", "FAST Scalp"),
            data.get("news_summary", "⚡ FAST 1m Sinyali"), data.get("ta_reasons", ""),
            data.get("chart_entry_png", ""),
            data.get("allocated_margin_usdt", 75.0),
            data.get("risk_usd", 15.0),
            entry_price, entry_price,
            fast_meta_str
        ))
        conn.commit()
        return cursor.lastrowid

def update_fast_signal_status(signal_id: int, updates: Dict):
    """FAST bot işlem durumunu veya fiyatlarını günceller."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        set_clauses = []
        values = []
        for key, value in updates.items():
            set_clauses.append(f"{key} = ?")
            values.append(value)
        values.append(signal_id)
        sql = f"UPDATE fast_signals SET {', '.join(set_clauses)} WHERE id = ?"
        cursor.execute(sql, values)
        conn.commit()

def get_fast_active_and_pending_signals() -> List[Dict]:
    """FAST bot açık ve aktif scalping işlemlerini getirir."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM fast_signals
            WHERE status IN ('ACTIVE', 'PENDING_ENTRY', 'ACTIVE_BE', 'ACTIVE_LADDER', 'ACTIVE_PARTIAL_TP1')
            ORDER BY id DESC
        """)
        return [dict(row) for row in cursor.fetchall()]

def get_fast_all_signals(limit: int = 50) -> List[Dict]:
    """FAST bot tüm geçmiş ve aktif işlemlerini son kapatılan en üstte olacak şekilde getirir."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM fast_signals
            ORDER BY COALESCE(closed_at, created_at) DESC, id DESC
            LIMIT ?
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]

def get_fast_performance_stats() -> Dict:
    """FAST botun bağımsız $1000 USDT kasalı kaldıraçlı performans özetini hesaplar."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                COUNT(*) as total_trades,
                SUM(CASE WHEN simulated_pnl_pct > 0 THEN 1 ELSE 0 END) as win_count,
                SUM(CASE WHEN simulated_pnl_pct < 0 THEN 1 ELSE 0 END) as loss_count,
                SUM(CASE WHEN simulated_pnl_pct = 0 THEN 1 ELSE 0 END) as be_count,
                AVG(simulated_pnl_pct) as avg_pnl_pct,
                SUM(simulated_pnl_pct) as total_pnl_pct,
                SUM(gross_pnl_pct) as total_gross_pnl_pct,
                SUM(fee_pct) as total_fee_pct,
                SUM(COALESCE(allocated_margin_usdt, 75.0) * (simulated_pnl_pct / 100.0)) as actual_net_dollar_gain,
                SUM(CASE WHEN simulated_pnl_pct > 0 THEN (COALESCE(allocated_margin_usdt, 75.0) * (simulated_pnl_pct / 100.0)) ELSE 0 END) as sum_dollar_wins,
                SUM(CASE WHEN simulated_pnl_pct < 0 THEN ABS(COALESCE(allocated_margin_usdt, 75.0) * (simulated_pnl_pct / 100.0)) ELSE 0 END) as sum_dollar_losses
            FROM fast_signals
            WHERE status NOT IN ('ACTIVE', 'PENDING_ENTRY', 'ACTIVE_BE', 'ACTIVE_LADDER', 'ACTIVE_PARTIAL_TP1')
              AND simulated_pnl_pct IS NOT NULL
        """)
        row = dict(cursor.fetchone() or {})
        total = row.get("total_trades") or 0
        wins = row.get("win_count") or 0
        losses = row.get("loss_count") or 0
        sum_wins = row.get("sum_dollar_wins") or 0.0
        sum_losses = row.get("sum_dollar_losses") or 0.0

        row["win_rate"] = round((wins / total * 100), 2) if total > 0 else 0.0
        row["profit_factor"] = round((sum_wins / sum_losses), 2) if sum_losses > 0 else (99.0 if sum_wins > 0 else 0.0)
        
        total_pnl = row.get("total_pnl_pct") or 0.0
        row["total_pnl_pct"] = round(total_pnl, 2)
        row["total_gross_pnl_pct"] = round(row.get("total_gross_pnl_pct") or 0.0, 2)
        row["total_fee_pct"] = round(row.get("total_fee_pct") or 0.0, 2)
        row["sum_wins"] = round(sum_wins, 2)
        row["sum_losses"] = round(sum_losses, 2)
        
        # FAST Bot Bağımsız $1000 Kasa Bakiyesi
        net_dollar_gain = row.get("actual_net_dollar_gain") or 0.0
        row["net_dollar_gain"] = round(net_dollar_gain, 2)
        row["portfolio_balance"] = round(1000.0 + net_dollar_gain, 2)

        # Günlük FAST PnL
        from datetime import datetime, timezone, timedelta
        tr_tz = timezone(timedelta(hours=3))
        now_tr = datetime.now(timezone.utc).astimezone(tr_tz)
        today_start_tr = now_tr.replace(hour=0, minute=0, second=0, microsecond=0)
        today_start = today_start_tr.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute("""
            SELECT 
                COUNT(*) as today_trades,
                SUM(CASE WHEN simulated_pnl_pct > 0 THEN 1 ELSE 0 END) as today_wins,
                SUM(CASE WHEN simulated_pnl_pct < 0 THEN 1 ELSE 0 END) as today_losses,
                SUM(simulated_pnl_pct) as today_net_pnl_pct,
                SUM(fee_pct) as today_fee_pct,
                SUM(COALESCE(allocated_margin_usdt, 75.0) * (simulated_pnl_pct / 100.0)) as today_dollar_gain
            FROM fast_signals
            WHERE status NOT IN ('ACTIVE', 'PENDING_ENTRY', 'ACTIVE_BE', 'ACTIVE_LADDER', 'ACTIVE_PARTIAL_TP1')
              AND closed_at >= ?
              AND simulated_pnl_pct IS NOT NULL
        """, (today_start,))
        t_row = dict(cursor.fetchone() or {})
        t_trades = t_row.get("today_trades") or 0
        t_wins = t_row.get("today_wins") or 0
        t_losses = t_row.get("today_losses") or 0
        t_dollar = round(t_row.get("today_dollar_gain") or 0.0, 2)
        t_pct = round(t_row.get("today_net_pnl_pct") or 0.0, 2)
        t_wr = round((t_wins / t_trades * 100.0), 1) if t_trades > 0 else 0.0

        row["today_trades"] = t_trades
        row["today_wins"] = t_wins
        row["today_losses"] = t_losses
        row["today_fee_pct"] = round(t_row.get("today_fee_pct") or 0.0, 2)
        row["today_net_pnl_pct"] = t_pct
        row["today_dollar_gain"] = t_dollar
        row["today_win_rate"] = t_wr
        row["today_date_str"] = now_tr.strftime("%Y-%m-%d")

        return row

def add_fast_scanner_log_db(symbol: str, status: str, reason: str, details: str = ""):
    """FAST bot taranan parite kararlarını kaydeder."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        time_str = datetime.now().strftime("%H:%M:%S")
        cursor.execute("""
            INSERT INTO fast_scanner_logs (time_str, symbol, status, reason, details)
            VALUES (?, ?, ?, ?, ?)
        """, (time_str, symbol, status, reason, details))
        conn.commit()

def get_fast_scanner_logs_db(limit: int = 40) -> List[Dict]:
    """FAST ofis masası için taranan son 1m kararlarını getirir."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT time_str as time, symbol, status, reason, details
            FROM fast_scanner_logs
            ORDER BY id DESC
            LIMIT ?
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]

def close_all_fast_positions_db(client=None) -> int:
    """FAST bot tüm açık pozisyonları anlık fiyattan kapatır."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, symbol, direction, actual_entry_price, leverage, allocated_margin_usdt
            FROM fast_signals
            WHERE status IN ('ACTIVE', 'PENDING_ENTRY', 'ACTIVE_BE', 'ACTIVE_LADDER', 'ACTIVE_PARTIAL_TP1')
        """)
        active_trades = cursor.fetchall()
        if not active_trades:
            return 0

        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        closed_count = 0

        for t in active_trades:
            sig_id = t["id"]
            symbol = t["symbol"]
            direction = t["direction"]
            entry_p = float(t["actual_entry_price"])
            lev = int(t["leverage"] or 10)
            margin = float(t["allocated_margin_usdt"] or 75.0)

            exit_price = entry_p
            if client:
                try:
                    price_info = client.get_ticker_price(symbol)
                    if price_info and "price" in price_info:
                        exit_price = float(price_info["price"])
                except Exception:
                    pass

            raw_gain_pct = ((exit_price - entry_p) / entry_p) * 100.0 if direction == "LONG" else ((entry_p - exit_price) / entry_p) * 100.0
            gross_margin = raw_gain_pct * lev
            fee_pct = 0.10 * lev
            net_margin = gross_margin - fee_pct

            cursor.execute("""
                UPDATE fast_signals
                SET status = 'EMERGENCY_CLOSED',
                    closed_at = ?,
                    exit_price = ?,
                    gross_pnl_pct = ?,
                    fee_pct = ?,
                    simulated_pnl_pct = ?
                WHERE id = ?
            """, (current_time, exit_price, round(gross_margin, 2), round(fee_pct, 2), round(net_margin, 2), sig_id))
            closed_count += 1

        conn.commit()
        return closed_count

def clear_fast_closed_trades_db():
    """FAST bot kapanmış geçmiş işlem kayıtlarını temizler."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM fast_signals WHERE status NOT IN ('ACTIVE', 'PENDING_ENTRY', 'ACTIVE_BE', 'ACTIVE_LADDER', 'ACTIVE_PARTIAL_TP1')")
        conn.commit()

def reset_fast_bot_db():
    """FAST bot (1m) tüm açık ve kapalı işlemlerini ve tarama günlüklerini sıfırlar. Kasa $1000'dan temiz başlar."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM fast_signals;")
        cursor.execute("DELETE FROM fast_scanner_logs;")
        conn.commit()

def check_fast_side_stoploss_guard(direction: str, max_consecutive_losses: int = 2, cooldown_minutes: int = 30) -> Tuple[bool, str]:
    """FAST bot için yön bazlı seri zarar kalkanı."""
    from datetime import datetime, timezone, timedelta
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, symbol, direction, status, simulated_pnl_pct, closed_at
                FROM fast_signals
                WHERE direction = ?
                  AND status NOT IN ('PENDING_ENTRY', 'ACTIVE', 'ACTIVE_BE', 'ACTIVE_LADDER', 'ACTIVE_PARTIAL_TP1')
                  AND closed_at IS NOT NULL
                ORDER BY closed_at DESC, id DESC
                LIMIT 10
            """, (direction,))
            rows = cursor.fetchall()
            if not rows:
                return False, ""

            consecutive_losses = 0
            last_loss_closed_at = None

            for r in rows:
                pnl = float(r["simulated_pnl_pct"] or 0.0)
                if pnl < 0:
                    consecutive_losses += 1
                    if last_loss_closed_at is None:
                        last_loss_closed_at = r["closed_at"]
                else:
                    break

            if consecutive_losses >= max_consecutive_losses and last_loss_closed_at:
                loss_dt = datetime.strptime(str(last_loss_closed_at)[:19], "%Y-%m-%d %H:%M:%S")
                now = datetime.now()
                elapsed_min = (now - loss_dt).total_seconds() / 60.0
                if elapsed_min < cooldown_minutes:
                    remaining_min = int(cooldown_minutes - elapsed_min)
                    reason = f"⚡ FAST YÖN KALKANI: {direction} yönünde peş peşe {consecutive_losses} zarar. {remaining_min} dk donduruldu."
                    return True, reason
    except Exception:
        pass
    return False, ""


def generate_fast_hourly_summary_report() -> Dict:
    """FAST Bot için son 1 saatte tamamlanan işlemleri, açık pozisyonları ve kümülatif PnL'i derler."""
    from datetime import datetime, timedelta, timezone
    tr_tz = timezone(timedelta(hours=3))
    now_tr = datetime.now(timezone.utc).astimezone(tr_tz)

    cutoff = datetime.now() - timedelta(hours=1)
    cutoff_str = cutoff.strftime("%Y-%m-%d %H:%M:%S")

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM fast_signals
            WHERE status NOT IN ('PENDING_ENTRY', 'ACTIVE', 'ACTIVE_BE', 'ACTIVE_LADDER', 'ACTIVE_PARTIAL_TP1')
              AND closed_at IS NOT NULL
              AND closed_at >= ?
            ORDER BY closed_at ASC
        """, (cutoff_str,))
        trades_1h = [dict(r) for r in cursor.fetchall()]

        cursor.execute("""
            SELECT * FROM fast_signals
            WHERE status IN ('ACTIVE', 'ACTIVE_BE', 'ACTIVE_LADDER', 'ACTIVE_PARTIAL_TP1')
            ORDER BY created_at DESC
        """)
        active_trades = [dict(r) for r in cursor.fetchall()]

    stats = get_fast_performance_stats()
    current_equity = stats.get("portfolio_balance", 1000.0)

    total_count = len(trades_1h)
    wins = [t for t in trades_1h if (t.get("simulated_pnl_pct") or 0.0) > 0]
    losses = [t for t in trades_1h if (t.get("simulated_pnl_pct") or 0.0) < 0]
    bes = [t for t in trades_1h if (t.get("simulated_pnl_pct") or 0.0) == 0]

    total_net_pnl_pct = sum((t.get("simulated_pnl_pct") or 0.0) for t in trades_1h)
    total_gross_pnl_pct = sum((t.get("gross_pnl_pct") or 0.0) for t in trades_1h)
    total_fee_pct = sum((t.get("fee_pct") or 0.0) for t in trades_1h)

    # Dolar bazlı kâr/zarar hesabı (allocated_margin * pnl_pct / 100)
    total_dollar_gain = sum(
        (t.get("allocated_margin_usdt") or 75.0) * ((t.get("simulated_pnl_pct") or 0.0) / 100.0)
        for t in trades_1h
    )

    win_rate = (len(wins) / total_count * 100.0) if total_count > 0 else 0.0

    return {
        "date_str": now_tr.strftime("%d.%m.%Y"),
        "time_str": now_tr.strftime("%H:%M"),
        "total_trades": total_count,
        "win_count": len(wins),
        "loss_count": len(losses),
        "be_count": len(bes),
        "win_rate": round(win_rate, 1),
        "net_pnl_pct": round(total_net_pnl_pct, 2),
        "gross_pnl_pct": round(total_gross_pnl_pct, 2),
        "fee_pct": round(total_fee_pct, 2),
        "dollar_pnl": round(total_dollar_gain, 2),
        "current_equity": round(current_equity, 2),
        "trades": trades_1h,
        "active_trades": active_trades,
        "overall_stats": stats
    }


def format_fast_hourly_telegram_message(report: Dict) -> str:
    """FAST 1-saatlik raporunu Telegram Markdown formatına dönüştürür."""
    date_str = report["date_str"]
    time_str = report["time_str"]
    total_1h = report["total_trades"]
    wins_1h = report["win_count"]
    losses_1h = report["loss_count"]
    win_rate_1h = report["win_rate"]
    net_pnl_1h = report["net_pnl_pct"]
    dollar_pnl_1h = report["dollar_pnl"]
    equity = report["current_equity"]
    stats = report.get("overall_stats", {})

    pnl_sign_1h = "+" if dollar_pnl_1h >= 0 else ""
    pnl_emoji_1h = "🟢" if dollar_pnl_1h > 0 else ("🔴" if dollar_pnl_1h < 0 else "⚪")
    pct_sign_1h = "+" if net_pnl_1h >= 0 else ""

    # Günlük FAST Verileri
    today_trades = stats.get("today_trades", 0)
    today_wins = stats.get("today_wins", 0)
    today_losses = stats.get("today_losses", 0)
    today_dollar = stats.get("today_dollar_gain", 0.0)
    today_pct = stats.get("today_net_pnl_pct", 0.0)
    today_wr = round((today_wins / today_trades * 100.0), 1) if today_trades > 0 else 0.0
    today_sign = "+" if today_dollar >= 0 else ""
    today_emoji = "🟢" if today_dollar > 0 else ("🔴" if today_dollar < 0 else "⚪")

    # Kümülatif Genel Toplam
    all_trades = stats.get("total_trades", 0)
    all_net_dollar = stats.get("net_dollar_gain", 0.0)
    all_wr = stats.get("win_rate", 0.0)
    all_sign = "+" if all_net_dollar >= 0 else ""
    all_emoji = "🟢" if all_net_dollar > 0 else ("🔴" if all_net_dollar < 0 else "⚪")

    lines = []
    lines.append("⚡ *FAST SCALPER (1m) SAATLİK RAPOR*")
    lines.append(f"⏱️ *Saat:* `{time_str}` | *Tarih:* `{date_str}` (TSİ)")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"💼 *FAST Fon Kasası:* `${equity:,.2f} USDT`")
    lines.append(f"{pnl_emoji_1h} *Son 1 Saat PnL:* *{pnl_sign_1h}${dollar_pnl_1h:.2f}* ({pct_sign_1h}%{net_pnl_1h:.2f})")
    lines.append(f"🎯 *Son 1 Saat İşlem:* `{total_1h}` adet (✅ `{wins_1h}` Win | 🛑 `{losses_1h}` Loss)")
    if total_1h > 0:
        lines.append(f"📊 *1 Saatlik Win Rate:* *%{win_rate_1h:.1f}*")
    lines.append(f"💸 *1 Saatlik Komisyon:* `-%{report['fee_pct']:.2f}`")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━\n")

    if total_1h == 0:
        lines.append("😴 *Son 1 saatte tamamlanan işlem bulunmuyor.*")
        lines.append("_(1 dakikalık mikro trendlerde yüksek confluence şartı taranıyor)._\n")
    else:
        lines.append("📋 *SON 1 SAATTE KAPANAN İŞLEMLER:*")
        for i, t in enumerate(report["trades"], 1):
            sym = t.get("symbol", "")
            d = t.get("direction", "")
            lev = t.get("leverage", 10)
            pnl = t.get("simulated_pnl_pct", 0.0)
            sign = "+" if pnl > 0 else ""
            status = t.get("status", "")
            status_badge = "🎯 TP" if "TP" in status else ("🪜 LADDER" if "LADDER" in status else ("🛡️ BE" if "BE" in status else ("⏱️ ZAMAN AŞIMI" if "TIMEOUT" in status else "🛑 SL")))
            t_margin = t.get("allocated_margin_usdt") or 75.0
            t_dollar = round(t_margin * (pnl / 100.0), 2)
            t_dollar_sign = "+" if t_dollar >= 0 else ""
            pnl_icon = "🟢" if pnl > 0 else ("🔴" if pnl < 0 else "⚪")

            lines.append(f"{i}. {pnl_icon} *{sym}* ({d} {lev}x) ➔ *{sign}%{pnl:.2f}* ({t_dollar_sign}${t_dollar:.2f}) [{status_badge}]")
        lines.append("")

    active = report.get("active_trades", [])
    if active:
        lines.append(f"📡 *AÇIKTA BEKLEYEN POZİSYONLAR ({len(active)}/10):*")
        for a in active:
            lines.append(f"• `{a.get('symbol')}` ({a.get('direction')} {a.get('leverage', 10)}x) | Giriş: `{a.get('actual_entry_price') or a.get('entry_min')}` | Stop: `{a.get('stop_loss')}`")
        lines.append("")

    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("📊 *GÜNLÜK & GENEL TOPLAM SONUÇ:*")
    lines.append(f"• *Bugünkü FAST PnL:* {today_emoji} *{today_sign}${today_dollar:.2f}* ({today_sign}%{today_pct:.2f}) | `{today_trades}` İşlem (WR: %{today_wr})")
    lines.append(f"• *Kümülatif Toplam:* {all_emoji} *{all_sign}${all_net_dollar:.2f}* | `{all_trades}` İşlem | WR: *%{all_wr:.1f}*")
    lines.append(f"• *Kasa Durumu:* Başlangıç: $1,000.00 ➔ Güncel: *${equity:,.2f}*")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("⚡ _FAST Scalper: 1 Dakikalık Çoklu-Ajan Mikro Motoru_")

    return "\n".join(lines)


# ==============================================================================
# SÜPER FAST BOT METOTLARI (SANİYELİK HFT & BAĞIMSIZ $1000 KASA)
# ==============================================================================

def save_super_fast_signal(data: Dict) -> int:
    """Yeni bir Süper FAST saniyelik mikro pozisyonunu kaydeder."""
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry_price = data.get("actual_entry_price") or data["entry_min"]
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO super_fast_signals (
                symbol, direction, leverage, entry_min, entry_max,
                actual_entry_price, entered_at,
                stop_loss, take_profit_1, take_profit_2, risk_reward,
                risk_grade, news_summary, ta_reasons, chart_entry_png, status,
                allocated_margin_usdt, risk_usd, highest_price, lowest_price,
                super_fast_meta
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', ?, ?, ?, ?, ?)
        """, (
            data["symbol"], data["direction"], data.get("leverage", 10),
            data["entry_min"], data["entry_max"],
            entry_price, current_time,
            data["stop_loss"], data["take_profit_1"], data.get("take_profit_2", data["take_profit_1"]),
            data.get("risk_reward", 1.4), data.get("risk_grade", "Süper FAST HFT"),
            data.get("news_summary", "⚡⚡ SÜPER FAST Saniyelik"), data.get("ta_reasons", ""),
            data.get("chart_entry_png", ""),
            data.get("allocated_margin_usdt", 35.0), data.get("risk_usd", 7.5),
            entry_price, entry_price,
            json.dumps(data.get("super_fast_meta", {}))
        ))
        conn.commit()
        return cursor.lastrowid


def update_super_fast_signal_status(signal_id: int, updates: Dict):
    """Süper FAST sinyalinin durumunu veya canlı kâr/zararını günceller."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        set_clauses = []
        values = []
        for key, val in updates.items():
            if key in ("super_fast_meta",) and isinstance(val, (dict, list)):
                val = json.dumps(val)
            set_clauses.append(f"{key} = ?")
            values.append(val)
        values.append(signal_id)
        sql = f"UPDATE super_fast_signals SET {', '.join(set_clauses)} WHERE id = ?"
        cursor.execute(sql, values)
        conn.commit()


def get_super_fast_active_and_pending_signals() -> List[Dict]:
    """Süper FAST bot açık ve aktif saniyelik scalping işlemlerini getirir."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM super_fast_signals
            WHERE status IN ('ACTIVE', 'PENDING_ENTRY', 'ACTIVE_BE', 'ACTIVE_LADDER', 'ACTIVE_PARTIAL_TP1')
            ORDER BY id DESC
        """)
        return [dict(row) for row in cursor.fetchall()]


def get_super_fast_all_signals(limit: int = 50) -> List[Dict]:
    """Süper FAST bot son sinyallerini ve işlemlerini son kapatılan en üstte olacak şekilde getirir."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM super_fast_signals
            ORDER BY COALESCE(closed_at, created_at) DESC, id DESC
            LIMIT ?
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]


def get_super_fast_performance_stats() -> Dict:
    """Süper FAST botun bağımsız $1000 USDT kasalı kaldıraçlı performans özetini hesaplar."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                COUNT(*) as total_trades,
                SUM(CASE WHEN simulated_pnl_pct > 0 THEN 1 ELSE 0 END) as win_count,
                SUM(CASE WHEN simulated_pnl_pct < 0 THEN 1 ELSE 0 END) as loss_count,
                SUM(CASE WHEN simulated_pnl_pct = 0 THEN 1 ELSE 0 END) as be_count,
                AVG(simulated_pnl_pct) as avg_pnl_pct,
                SUM(simulated_pnl_pct) as total_pnl_pct,
                SUM(gross_pnl_pct) as total_gross_pnl_pct,
                SUM(fee_pct) as total_fee_pct,
                SUM(COALESCE(allocated_margin_usdt, 35.0) * (simulated_pnl_pct / 100.0)) as actual_net_dollar_gain,
                SUM(CASE WHEN simulated_pnl_pct > 0 THEN (COALESCE(allocated_margin_usdt, 35.0) * (simulated_pnl_pct / 100.0)) ELSE 0 END) as sum_dollar_wins,
                SUM(CASE WHEN simulated_pnl_pct < 0 THEN ABS(COALESCE(allocated_margin_usdt, 35.0) * (simulated_pnl_pct / 100.0)) ELSE 0 END) as sum_dollar_losses
            FROM super_fast_signals
            WHERE status NOT IN ('ACTIVE', 'PENDING_ENTRY', 'ACTIVE_BE', 'ACTIVE_LADDER', 'ACTIVE_PARTIAL_TP1')
              AND simulated_pnl_pct IS NOT NULL
        """)
        row = dict(cursor.fetchone() or {})
        total = row.get("total_trades") or 0
        wins = row.get("win_count") or 0
        losses = row.get("loss_count") or 0
        sum_wins = row.get("sum_dollar_wins") or 0.0
        sum_losses = row.get("sum_dollar_losses") or 0.0

        row["win_rate"] = round((wins / total * 100), 2) if total > 0 else 0.0
        row["profit_factor"] = round((sum_wins / sum_losses), 2) if sum_losses > 0 else (99.0 if sum_wins > 0 else 0.0)
        
        total_pnl = row.get("total_pnl_pct") or 0.0
        row["total_pnl_pct"] = round(total_pnl, 2)
        row["total_gross_pnl_pct"] = round(row.get("total_gross_pnl_pct") or 0.0, 2)
        row["total_fee_pct"] = round(row.get("total_fee_pct") or 0.0, 2)
        row["sum_wins"] = round(sum_wins, 2)
        row["sum_losses"] = round(sum_losses, 2)
        
        # Süper FAST Bağımsız $1000 Kasa Bakiyesi
        net_dollar_gain = row.get("actual_net_dollar_gain") or 0.0
        row["net_dollar_gain"] = round(net_dollar_gain, 2)
        row["portfolio_balance"] = round(1000.0 + net_dollar_gain, 2)

        # Günlük Süper FAST PnL
        from datetime import datetime, timezone, timedelta
        tr_tz = timezone(timedelta(hours=3))
        now_tr = datetime.now(timezone.utc).astimezone(tr_tz)
        today_start_tr = now_tr.replace(hour=0, minute=0, second=0, microsecond=0)
        today_start = today_start_tr.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute("""
            SELECT 
                COUNT(*) as today_trades,
                SUM(CASE WHEN simulated_pnl_pct > 0 THEN 1 ELSE 0 END) as today_wins,
                SUM(CASE WHEN simulated_pnl_pct < 0 THEN 1 ELSE 0 END) as today_losses,
                SUM(simulated_pnl_pct) as today_net_pnl_pct,
                SUM(fee_pct) as today_fee_pct,
                SUM(COALESCE(allocated_margin_usdt, 35.0) * (simulated_pnl_pct / 100.0)) as today_dollar_gain
            FROM super_fast_signals
            WHERE status NOT IN ('ACTIVE', 'PENDING_ENTRY', 'ACTIVE_BE', 'ACTIVE_LADDER', 'ACTIVE_PARTIAL_TP1')
              AND closed_at >= ?
              AND simulated_pnl_pct IS NOT NULL
        """, (today_start,))
        today_row = dict(cursor.fetchone() or {})
        t_trades = today_row.get("today_trades") or 0
        t_wins = today_row.get("today_wins") or 0

        row["today_trades"] = t_trades
        row["today_wins"] = t_wins
        row["today_losses"] = today_row.get("today_losses") or 0
        row["today_fee_pct"] = round(today_row.get("today_fee_pct") or 0.0, 2)
        row["today_net_pnl_pct"] = round(today_row.get("today_net_pnl_pct") or 0.0, 2)
        row["today_dollar_gain"] = round(today_row.get("today_dollar_gain") or 0.0, 2)
        row["today_win_rate"] = round((t_wins / t_trades * 100.0), 1) if t_trades > 0 else 0.0
        row["today_date_str"] = now_tr.strftime("%Y-%m-%d")

        return row


def add_super_fast_scanner_log_db(symbol: str, status: str, reason: str, details: str = ""):
    """Süper FAST tarayıcı olayını veritabanına kaydeder."""
    time_str = datetime.now().strftime("%H:%M:%S")
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO super_fast_scanner_logs (time_str, symbol, status, reason, details)
            VALUES (?, ?, ?, ?, ?)
        """, (time_str, symbol, status, reason, details))
        conn.commit()


def get_super_fast_scanner_logs_db(limit: int = 50) -> List[Dict]:
    """Süper FAST bot son tarama kayıtlarını getirir."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT time_str as time, symbol, status, reason, details
            FROM super_fast_scanner_logs
            ORDER BY id DESC
            LIMIT ?
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]


def close_all_super_fast_positions_db(client=None) -> int:
    """Tüm açık Süper FAST pozisyonlarını anlık piyasa fiyatıyla acilen kapatır."""
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    closed_count = 0

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM super_fast_signals WHERE status IN ('ACTIVE', 'ACTIVE_BE', 'ACTIVE_LADDER', 'ACTIVE_PARTIAL_TP1')")
        open_trades = [dict(r) for r in cursor.fetchall()]

        if not open_trades:
            return 0

        tickers = {}
        if client:
            try:
                tickers = client.get_24hr_tickers()
            except Exception:
                pass

        for t in open_trades:
            sig_id = t["id"]
            sym = t["symbol"]
            direction = t["direction"]
            entry_p = float(t["actual_entry_price"])
            lev = int(t["leverage"] or 10)

            ticker = tickers.get(sym, {})
            exit_price = ticker.get("lastPrice", entry_p)

            if direction == "LONG":
                raw_diff = (exit_price - entry_p) / entry_p
            else:
                raw_diff = (entry_p - exit_price) / entry_p

            gross_margin = raw_diff * lev * 100.0
            fee_pct = 0.10 * lev
            net_margin = gross_margin - fee_pct

            cursor.execute("""
                UPDATE super_fast_signals
                SET status = 'EMERGENCY_CLOSED',
                    closed_at = ?,
                    exit_price = ?,
                    gross_pnl_pct = ?,
                    fee_pct = ?,
                    simulated_pnl_pct = ?
                WHERE id = ?
            """, (current_time, exit_price, round(gross_margin, 2), round(fee_pct, 2), round(net_margin, 2), sig_id))
            closed_count += 1

        conn.commit()
        return closed_count


def clear_super_fast_closed_trades_db():
    """Süper FAST bot kapanmış geçmiş işlem kayıtlarını temizler."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM super_fast_signals WHERE status NOT IN ('ACTIVE', 'PENDING_ENTRY', 'ACTIVE_BE', 'ACTIVE_LADDER', 'ACTIVE_PARTIAL_TP1')")
        conn.commit()


def reset_super_fast_bot_db():
    """Süper FAST bot (1s) tüm açık ve kapalı işlemlerini ve tarama günlüklerini sıfırlar. Kasa $1000'dan temiz başlar."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM super_fast_signals;")
        cursor.execute("DELETE FROM super_fast_scanner_logs;")
        conn.commit()


def check_super_fast_side_stoploss_guard(direction: str, max_consecutive_losses: int = 3, cooldown_minutes: int = 15) -> Tuple[bool, str]:
    """Süper FAST bot için yön bazlı seri zarar kalkanı."""
    from datetime import datetime, timezone, timedelta
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, symbol, direction, status, simulated_pnl_pct, closed_at
                FROM super_fast_signals
                WHERE direction = ?
                  AND status NOT IN ('PENDING_ENTRY', 'ACTIVE', 'ACTIVE_BE', 'ACTIVE_LADDER', 'ACTIVE_PARTIAL_TP1')
                  AND closed_at IS NOT NULL
                ORDER BY closed_at DESC, id DESC
                LIMIT 10
            """, (direction,))
            rows = cursor.fetchall()
            if not rows:
                return False, ""

            consecutive_losses = 0
            last_loss_closed_at = None

            for r in rows:
                pnl = float(r["simulated_pnl_pct"] or 0.0)
                if pnl < 0:
                    consecutive_losses += 1
                    if last_loss_closed_at is None:
                        last_loss_closed_at = r["closed_at"]
                else:
                    break

            if consecutive_losses >= max_consecutive_losses and last_loss_closed_at:
                loss_dt = datetime.strptime(str(last_loss_closed_at)[:19], "%Y-%m-%d %H:%M:%S")
                now = datetime.now()
                elapsed_min = (now - loss_dt).total_seconds() / 60.0
                if elapsed_min < cooldown_minutes:
                    remaining_min = int(cooldown_minutes - elapsed_min)
                    reason = f"⚡⚡ SÜPER FAST YÖN KALKANI: {direction} yönünde peş peşe {consecutive_losses} zarar. {remaining_min} dk donduruldu."
                    return True, reason
    except Exception:
        pass
    return False, ""


def generate_super_fast_hourly_summary_report() -> Dict:
    """Süper FAST Bot için son 1 saatte tamamlanan saniyelik işlemleri, açık pozisyonları ve PnL'i derler."""
    from datetime import datetime, timedelta, timezone
    tr_tz = timezone(timedelta(hours=3))
    now_tr = datetime.now(timezone.utc).astimezone(tr_tz)

    cutoff = datetime.now() - timedelta(hours=1)
    cutoff_str = cutoff.strftime("%Y-%m-%d %H:%M:%S")

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM super_fast_signals
            WHERE status NOT IN ('PENDING_ENTRY', 'ACTIVE', 'ACTIVE_BE', 'ACTIVE_LADDER', 'ACTIVE_PARTIAL_TP1')
              AND closed_at IS NOT NULL
              AND closed_at >= ?
            ORDER BY closed_at ASC
        """, (cutoff_str,))
        trades_1h = [dict(r) for r in cursor.fetchall()]

        cursor.execute("""
            SELECT * FROM super_fast_signals
            WHERE status IN ('ACTIVE', 'ACTIVE_BE', 'ACTIVE_LADDER', 'ACTIVE_PARTIAL_TP1')
            ORDER BY created_at DESC
        """)
        active_trades = [dict(r) for r in cursor.fetchall()]

    stats = get_super_fast_performance_stats()
    current_equity = stats.get("portfolio_balance", 1000.0)

    total_count = len(trades_1h)
    wins = [t for t in trades_1h if (t.get("simulated_pnl_pct") or 0.0) > 0]
    losses = [t for t in trades_1h if (t.get("simulated_pnl_pct") or 0.0) < 0]
    bes = [t for t in trades_1h if (t.get("simulated_pnl_pct") or 0.0) == 0]

    total_net_pnl_pct = sum((t.get("simulated_pnl_pct") or 0.0) for t in trades_1h)
    total_gross_pnl_pct = sum((t.get("gross_pnl_pct") or 0.0) for t in trades_1h)
    total_fee_pct = sum((t.get("fee_pct") or 0.0) for t in trades_1h)

    total_dollar_gain = sum(
        (t.get("allocated_margin_usdt") or 35.0) * ((t.get("simulated_pnl_pct") or 0.0) / 100.0)
        for t in trades_1h
    )

    win_rate = (len(wins) / total_count * 100.0) if total_count > 0 else 0.0

    return {
        "date_str": now_tr.strftime("%d.%m.%Y"),
        "time_str": now_tr.strftime("%H:%M"),
        "total_trades": total_count,
        "win_count": len(wins),
        "loss_count": len(losses),
        "be_count": len(bes),
        "win_rate": round(win_rate, 1),
        "net_pnl_pct": round(total_net_pnl_pct, 2),
        "gross_pnl_pct": round(total_gross_pnl_pct, 2),
        "fee_pct": round(total_fee_pct, 2),
        "dollar_pnl": round(total_dollar_gain, 2),
        "current_equity": round(current_equity, 2),
        "trades": trades_1h,
        "active_trades": active_trades,
        "overall_stats": stats
    }


def format_super_fast_hourly_telegram_message(report: Dict) -> str:
    """Süper FAST 1-saatlik raporunu Telegram Markdown formatına dönüştürür."""
    date_str = report["date_str"]
    time_str = report["time_str"]
    total_1h = report["total_trades"]
    wins_1h = report["win_count"]
    losses_1h = report["loss_count"]
    win_rate_1h = report["win_rate"]
    net_pnl_1h = report["net_pnl_pct"]
    dollar_pnl_1h = report["dollar_pnl"]
    equity = report["current_equity"]
    stats = report.get("overall_stats", {})

    pnl_sign_1h = "+" if dollar_pnl_1h >= 0 else ""
    pnl_emoji_1h = "🟢" if dollar_pnl_1h > 0 else ("🔴" if dollar_pnl_1h < 0 else "⚪")
    pct_sign_1h = "+" if net_pnl_1h >= 0 else ""

    today_trades = stats.get("today_trades", 0)
    today_wins = stats.get("today_wins", 0)
    today_losses = stats.get("today_losses", 0)
    today_dollar = stats.get("today_dollar_gain", 0.0)
    today_pct = stats.get("today_net_pnl_pct", 0.0)
    today_wr = round((today_wins / today_trades * 100.0), 1) if today_trades > 0 else 0.0
    today_sign = "+" if today_dollar >= 0 else ""
    today_emoji = "🟢" if today_dollar > 0 else ("🔴" if today_dollar < 0 else "⚪")

    all_trades = stats.get("total_trades", 0)
    all_net_dollar = stats.get("net_dollar_gain", 0.0)
    all_wr = stats.get("win_rate", 0.0)
    all_sign = "+" if all_net_dollar >= 0 else ""
    all_emoji = "🟢" if all_net_dollar > 0 else ("🔴" if all_net_dollar < 0 else "⚪")

    lines = []
    lines.append("⚡⚡ *SÜPER FAST (Saniyelik HFT) SAATLİK RAPOR*")
    lines.append(f"⏱️ *Saat:* `{time_str}` | *Tarih:* `{date_str}` (TSİ)")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"💼 *Süper FAST Fon Kasası:* `${equity:,.2f} USDT`")
    lines.append(f"{pnl_emoji_1h} *Son 1 Saat PnL:* *{pnl_sign_1h}${dollar_pnl_1h:.2f}* ({pct_sign_1h}%{net_pnl_1h:.2f})")
    lines.append(f"🎯 *Son 1 Saat İşlem:* `{total_1h}` adet (✅ `{wins_1h}` Win | 🛑 `{losses_1h}` Loss)")
    if total_1h > 0:
        lines.append(f"📊 *1 Saatlik Win Rate:* *%{win_rate_1h:.1f}*")
    lines.append(f"💸 *1 Saatlik Komisyon:* `-%{report['fee_pct']:.2f}`")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━\n")

    if total_1h == 0:
        lines.append("😴 *Son 1 saatte tamamlanan saniyelik işlem bulunmuyor.*")
        lines.append("_(Saniyelik mikro dalgalanmalarda emir akış momentumu taranıyor)._\n")
    else:
        lines.append("📋 *SON 1 SAATTE KAPANAN MİKRO İŞLEMLER:*")
        for i, t in enumerate(report["trades"], 1):
            sym = t.get("symbol", "")
            d = t.get("direction", "")
            lev = t.get("leverage", 10)
            pnl = t.get("simulated_pnl_pct", 0.0)
            sign = "+" if pnl > 0 else ""
            status = t.get("status", "")
            status_badge = "🎯 TP" if "TP" in status else ("🪜 LADDER" if "LADDER" in status else ("🛡️ BE" if "BE" in status else ("⏱️ ZAMAN AŞIMI" if "TIMEOUT" in status else "🛑 SL")))
            t_margin = t.get("allocated_margin_usdt") or 35.0
            t_dollar = round(t_margin * (pnl / 100.0), 2)
            t_dollar_sign = "+" if t_dollar >= 0 else ""
            pnl_icon = "🟢" if pnl > 0 else ("🔴" if pnl < 0 else "⚪")

            lines.append(f"{i}. {pnl_icon} *{sym}* ({d} {lev}x) ➔ *{sign}%{pnl:.2f}* ({t_dollar_sign}${t_dollar:.2f}) [{status_badge}]")
        lines.append("")

    active = report.get("active_trades", [])
    if active:
        lines.append(f"📡 *AÇIKTA BEKLEYEN MİKRO POZİSYONLAR ({len(active)}/20):*")
        for a in active:
            lines.append(f"• `{a.get('symbol')}` ({a.get('direction')} {a.get('leverage', 10)}x) | Giriş: `{a.get('actual_entry_price') or a.get('entry_min')}` | Stop: `{a.get('stop_loss')}`")
        lines.append("")

    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("📊 *GÜNLÜK & GENEL TOPLAM SONUÇ:*")
    lines.append(f"• *Bugünkü Süper FAST PnL:* {today_emoji} *{today_sign}${today_dollar:.2f}* ({today_sign}%{today_pct:.2f}) | `{today_trades}` İşlem (WR: %{today_wr})")
    lines.append(f"• *Kümülatif Toplam:* {all_emoji} *{all_sign}${all_net_dollar:.2f}* | `{all_trades}` İşlem | WR: *%{all_wr:.1f}*")
    lines.append(f"• *Kasa Durumu:* Başlangıç: $1,000.00 ➔ Güncel: *${equity:,.2f}*")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("⚡⚡ _SÜPER FAST: Saniyelik Mikro-Tick Yüksek Frekans Motoru_")

    return "\n".join(lines)
