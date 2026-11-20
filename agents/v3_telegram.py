"""
v3 Çok Faktörlü Motor — Telegram mesajları ve komut yanıtları.

Telegram'ın eski "Markdown" biçimi kullanılır: *kalın* ve `kod`. Alt çizgi ve köşeli parantez
mesajı bozabileceği için metinlerde kullanılmaz (bozulursa notifier düz metne düşer).
Saatler kullanıcıya Türkiye saatiyle (TSİ, UTC+3) gösterilir.
"""
from __future__ import annotations

import os
import threading
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

import config

TR_TZ = timezone(timedelta(hours=3))
HOUR_MS = 3_600_000
DAY_MS = 24 * HOUR_MS
LINE = "━━━━━━━━━━━━━━━━━━━"

COMMANDS = [
    ("durum", "Kasa, kâr/zarar ve risk özeti"),
    ("pozisyonlar", "Açık v3 pozisyonları"),
    ("rapor", "Bugünün raporu (şu ana kadar)"),
    ("yedek", "Kayıtların yedeğini şimdi gönder"),
    ("btc", "BTC piyasa durumu"),
    ("yardim", "Komut listesi"),
]
REASONS = {"ilk_kurulum": "İlk kurulum", "gunluk_dilim": "Günlük dengeleme", "haftalik": "Haftalık dengeleme",
           "dusus_kesici": "Düşüş kesicisi"}


# --------------------------------------------------------------------------------------
# Biçimlendirme
# --------------------------------------------------------------------------------------
def short(sym: str) -> str:
    return (sym or "").replace("USDT", "")


def usd(v, signed: bool = False) -> str:
    v = float(v or 0.0)
    if abs(v) < 0.005:
        v = 0.0
    sign = ("+" if v > 0 else "−" if v < 0 else "") if signed else ("−" if v < 0 else "")
    return f"{sign}${abs(v):,.2f}"


def pct(v, d: int = 2) -> str:
    v = float(v or 0.0)
    if abs(v) < 0.5 * 10 ** -d:
        v = 0.0
    sign = "+" if v > 0 else "−" if v < 0 else ""
    return f"{sign}{abs(v):.{d}f}%"


def icon(v) -> str:
    v = float(v or 0.0)
    return "🟢" if v > 0.004 else ("🔴" if v < -0.004 else "⚪")


def funding_text(paid) -> str:
    """funding_paid > 0: ödenen (maliyet), < 0: alınan (gelir)."""
    paid = float(paid or 0.0)
    if abs(paid) < 0.005:
        return "$0.00"
    return f"+${abs(paid):,.2f} gelir" if paid < 0 else f"−${abs(paid):,.2f} ödeme"


def utc_to_tr(s: Optional[str], fmt: str = "%d.%m %H:%M") -> str:
    if not s:
        return "—"
    try:
        dt = datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        return dt.astimezone(TR_TZ).strftime(fmt)
    except ValueError:
        return s


def _tr_hm(hour_utc: int, minute: int = 0) -> str:
    return f"{(hour_utc + 3) % 24:02d}:{minute:02d}"


def panel_url() -> Optional[str]:
    dom = (os.getenv("RAILWAY_PUBLIC_DOMAIN") or "").strip()
    return f"https://{dom}" if dom else None


def _age_text(last_step: Optional[str], now: Optional[str]) -> Optional[str]:
    try:
        a = datetime.strptime(last_step[:19], "%Y-%m-%d %H:%M:%S")
        b = datetime.strptime(now[:19], "%Y-%m-%d %H:%M:%S")
        sec = max(0, int((b - a).total_seconds()))
        return f"{sec} sn" if sec < 120 else f"{sec // 60} dk"
    except Exception:
        return None


def _engine(engine=None):
    if engine is not None:
        return engine
    from agents.carry_agent import get_live_engine
    return get_live_engine()


def _side_counts(positions):
    longs = sum(1 for p in positions if p["side"] == "LONG")
    return longs, len(positions) - longs


# --------------------------------------------------------------------------------------
# Gün hesabı (TSİ takvim günü)
# --------------------------------------------------------------------------------------
def day_window(date_tr: str):
    d = datetime.strptime(date_tr, "%Y-%m-%d").replace(tzinfo=TR_TZ)
    start = int(d.astimezone(timezone.utc).timestamp() * 1000)
    return start, start + DAY_MS


def today_tr(now_ms: Optional[int] = None) -> str:
    dt = datetime.fromtimestamp(now_ms / 1000, tz=timezone.utc) if now_ms else datetime.now(timezone.utc)
    return dt.astimezone(TR_TZ).strftime("%Y-%m-%d")


def compute_day(store, capital: float, snap: Dict, date_tr: str, now_ms: int) -> Dict:
    """Bir TSİ gününün özeti: başlangıç/bitiş kasası, dolumlar, maliyet, fonlama, dengeleme sayısı."""
    start, end = day_window(date_tr)
    is_today = now_ms < end
    e0 = store.equity_at_or_before(start)
    base = float(e0["equity"]) if e0 else float(capital)
    if is_today:
        eq_end, f_end = float(snap["equity"]), snap.get("funding_paid")
    else:
        e1 = store.equity_at_or_before(end)
        eq_end = float(e1["equity"]) if e1 else float(snap["equity"])
        f_end = e1.get("funding_paid") if e1 else None
    fills = store.between("carry_fills", start, min(end, now_ms + 1))
    rebs = store.between("carry_rebalances", start, min(end, now_ms + 1))
    if e0 is None:
        funding = f_end if f_end is not None else None          # motor bu gün başladı: kümülatif = günlük
    elif e0.get("funding_paid") is not None and f_end is not None:
        funding = float(f_end) - float(e0["funding_paid"])
    else:
        funding = None                                          # eski kayıtlarda sayaç yok
    pnl = eq_end - base
    return {
        "date": date_tr, "is_today": is_today, "equity_start": base, "equity_end": eq_end,
        "pnl": pnl, "pnl_pct": pnl / base * 100 if base else 0.0,
        "n_fills": len(fills), "turnover": sum(f["notional"] or 0 for f in fills),
        "fees": sum(f["fee"] or 0 for f in fills), "realized": sum(f["realized_pnl"] or 0 for f in fills),
        "n_rebalances": len(rebs), "funding": funding,
    }


# --------------------------------------------------------------------------------------
# Mesajlar
# --------------------------------------------------------------------------------------
def help_text() -> str:
    lines = ["🤖 *Komutlar*", LINE] + [f"/{c} — {d}" for c, d in COMMANDS]
    lines += [LINE, f"v3 motoru portföyü her gün {_tr_hm(config.CARRY_REBALANCE_HOUR_UTC)}'te (TSİ) kendisi dengeler; "
                    "elle işlem gerekmez."]
    return "\n".join(lines)


def startup_message(snap: Optional[Dict]) -> str:
    lines = ["🟢 *Trade Bot v3 aktif*", LINE,
             "🤖 Motor: çok faktörlü (trend + momentum + fonlama) · sanal işlem"]
    if snap:
        lines.append(f"💼 Kasa: `{usd(snap['equity'])}` ({pct(snap['pnl_pct'])}) · {len(snap['positions'])} pozisyon")
        pr = snap.get("params") or {}
        if pr.get("target_vol"):
            lines.append(f"🎚️ Risk seviyesi %{pr['target_vol'] * 100:.0f} · kesici {pct(pr.get('dd_cut', 0) * 100, 0)}")
    lines += [f"🕒 Dengeleme {_tr_hm(config.CARRY_REBALANCE_HOUR_UTC)} · yedek "
              f"{_tr_hm(config.MAINTENANCE_HOUR_UTC, config.MAINTENANCE_MINUTE_UTC)} · gün sonu raporu 23:50 (TSİ)",
              "💬 /durum /pozisyonlar /rapor /yedek /yardim"]
    url = panel_url()
    if url:
        lines.append(f"🌐 Panel: {url}")
    return "\n".join(lines)


def status_message(snap: Dict, today: Optional[Dict] = None) -> str:
    pos = snap["positions"]
    n_long, n_short = _side_counts(pos)
    lev = snap["gross_exposure"] / snap["equity"] if snap["equity"] else 0.0
    lines = ["📊 *v3 Durum*", LINE,
             f"💼 Kasa: `{usd(snap['equity'])}`",
             f"{icon(snap['pnl'])} Toplam: *{usd(snap['pnl'], True)}* ({pct(snap['pnl_pct'])})"]
    if today:
        lines.append(f"{icon(today['pnl'])} Bugün: *{usd(today['pnl'], True)}* ({pct(today['pnl_pct'])})")
    pr = snap.get("params") or {}
    if pr.get("target_vol"):
        lines.append(f"🎚️ Risk seviyesi %{pr['target_vol'] * 100:.0f} · kesici {pct(pr.get('dd_cut', 0) * 100, 0)}")
    lines += [f"📉 Zirveden: {pct(snap['drawdown_pct'])} · risk ölçeği {snap['scale']:.1f}x",
              f"📌 {len(pos)} pozisyon ({n_long} LONG / {n_short} SHORT) · brüt {usd(snap['gross_exposure'])} ({lev:.2f}x)",
              f"💸 Toplam komisyon {usd(snap['fees_paid'])} · fonlama {funding_text(snap['funding_paid'])}",
              f"🔁 Son dengeleme {utc_to_tr(snap.get('last_rebalance'))} · sonraki {utc_to_tr(snap.get('next_rebalance'))} (TSİ)"]
    age = _age_text(snap.get("last_step"), snap.get("server_time"))
    if age:
        lines.append(f"❤️ Motor çalışıyor · son adım {age} önce")
    if snap["scale"] < 1:
        lines.append(f"⚠️ Düşüş kesicisi devrede: risk {snap['scale']:.1f}x")
    return "\n".join(lines)


def positions_message(snap: Dict) -> str:
    pos = sorted(snap["positions"], key=lambda p: -abs(p["notional"]))
    if not pos:
        return "💤 Açık v3 pozisyonu yok. Motor bir sonraki dengelemede portföyü kuracak."
    lines = [f"📌 *v3 Açık Pozisyonlar* ({len(pos)})", LINE]
    for side, title in (("LONG", "🟢 LONG"), ("SHORT", "🔴 SHORT")):
        grp = [p for p in pos if p["side"] == side]
        if not grp:
            continue
        lines.append(f"*{title}*")
        for p in grp:
            ret = (p["price"] / p["avg_price"] - 1) * 100 * (1 if side == "LONG" else -1) if p["avg_price"] else 0.0
            lines.append(f"`{short(p['symbol']):<5} {usd(abs(p['notional'])):>8} {usd(p['upnl'], True):>8} {pct(ret, 1):>7}`")
    tot = sum(p["upnl"] for p in pos)
    lines += [LINE, f"{icon(tot)} Açık K/Z toplamı: *{usd(tot, True)}*",
              "Sütunlar: coin · büyüklük · K/Z · getiri"]
    return "\n".join(lines)


def daily_report_message(engine=None, date_tr: Optional[str] = None, final: bool = True,
                         now_ms: Optional[int] = None) -> str:
    eng = _engine(engine)
    snap = eng.snapshot()
    now_ms = now_ms or eng.data.now_ms()
    date_tr = date_tr or today_tr(now_ms)
    d = compute_day(eng.store, eng.state["capital"], snap, date_tr, now_ms)
    pos = snap["positions"]
    n_long, n_short = _side_counts(pos)
    title = "📊 *v3 Gün Sonu Raporu*" if final else "📊 *v3 Bugünün Raporu* (şu ana kadar)"
    disp = datetime.strptime(date_tr, "%Y-%m-%d").strftime("%d.%m.%Y")
    lines = [f"{title} · {disp}", LINE,
             f"💼 Kasa: `{usd(d['equity_end'])}`",
             f"{icon(d['pnl'])} Gün: *{usd(d['pnl'], True)}* ({pct(d['pnl_pct'])})",
             f"📈 Toplam: *{usd(snap['pnl'], True)}* ({pct(snap['pnl_pct'])}) · zirveden {pct(snap['drawdown_pct'])}",
             "",
             f"🔁 {d['n_rebalances']} dengeleme · {d['n_fills']} dolum · işlem hacmi {usd(d['turnover'])}",
             f"💸 Komisyon {usd(d['fees'])}" + (f" · fonlama {funding_text(d['funding'])}" if d["funding"] is not None else "")]
    if pos:
        lev = snap["gross_exposure"] / snap["equity"] if snap["equity"] else 0.0
        best = max(pos, key=lambda p: p["upnl"])
        worst = min(pos, key=lambda p: p["upnl"])
        lines.append(f"📌 {len(pos)} pozisyon ({n_long} LONG / {n_short} SHORT) · brüt {usd(snap['gross_exposure'])} ({lev:.2f}x)")
        lines.append(f"🏅 En iyi {short(best['symbol'])} {usd(best['upnl'], True)} · "
                     f"en kötü {short(worst['symbol'])} {usd(worst['upnl'], True)} (açık K/Z)")
    if snap["scale"] < 1:
        lines.append(f"⚠️ Düşüş kesicisi devrede: risk {snap['scale']:.1f}x")
    try:
        from agents.carry_shadow import load_result
        tl = tracking_line(load_result(eng.store), now_ms)
        if tl:
            lines.append(tl)
    except Exception:
        pass
    url = panel_url()
    if url:
        lines += [LINE, f"🌐 {url}"]
    return "\n".join(lines)


TRACK_ICON = {"uyumlu": "✅", "izle": "🟡", "sapma": "🔴"}
TRACK_TEXT = {"uyumlu": "Uyumlu", "izle": "İzleniyor", "sapma": "Sapma var"}


def tracking_line(res: Optional[Dict], now_ms: int) -> Optional[str]:
    """Canlı ↔ backtest takibinin tek satırlık özeti (son 26 saatte karşılaştırma yoksa gösterilmez)."""
    if not res or res.get("status") != "ok" or not res.get("run_ms"):
        return None
    if now_ms - int(res["run_ms"]) > 26 * HOUR_MS:
        return None
    v = res.get("verdict")
    if v not in TRACK_TEXT:
        return "🧪 Backtest takibi: veri birikiyor"
    live, sh = res.get("live") or {}, res.get("shadow") or {}
    diff = float(res.get("diff_pp") or 0.0)
    line = (f"🧪 Backtest takibi: {TRACK_ICON[v]} {TRACK_TEXT[v]} · canlı {pct(live.get('ret_pct'))}"
            f" / backtest {pct(sh.get('ret_pct'))} (fark {'+' if diff > 0.005 else '−' if diff < -0.005 else ''}"
            f"{abs(diff):.2f} puan)")
    if v != "uyumlu":
        line += " · ayrıntı panelde"
    return line


EXPECT = {  # backtest (kesici risk seviyesine eşit): yıllık getiri, en kötü düşüş, en kötü ay
    0.10: ("~%12–14", "~%8–12", "−%5"),
    0.15: ("~%19–21", "~%11–17", "−%7"),
    0.20: ("~%25–30", "~%15–22", "−%10"),
    0.30: ("~%37–45", "~%20–33", "−%15"),
}


def expectation(target_vol: float):
    key = min(EXPECT, key=lambda k: abs(k - float(target_vol or 0)))
    return EXPECT[key]


def risk_change_message(change: Dict, params, light: Dict) -> str:
    ann, dd, month = expectation(change["to"])
    up = change["to"] > change["from"]
    lines = [f"🎚️ *Risk seviyesi güncellendi* · %{change['from'] * 100:.0f} → %{change['to'] * 100:.0f}", LINE,
             f"{'📈' if up else '📉'} Pozisyonlar bir sonraki dengelemede ({utc_to_tr(light.get('next_rebalance'))} TSİ) "
             f"~{change['factor']:.1f} katına {'çıkacak' if up else 'inecek'}.",
             f"🛡️ Düşüş kesicisi: {pct(params.dd_cut * 100, 0)} (zirveden bu kadar düşerse risk yarıya iner)",
             f"🧪 Backtest beklentisi: yıllık {ann} · en kötü düşüş {dd} · en kötü ay {month}",
             "Canlıda sonuçların bir miktar daha düşük olması beklenmeli."]
    return "\n".join(lines)


def rebalance_message(row: Dict, before: Dict[str, float], after: Dict[str, float], equity: float, state: Dict) -> str:
    def side(q):
        return "L" if q > 0 else "S"
    opened = sorted(s for s, q in after.items() if q and not before.get(s))
    closed = sorted(s for s, q in before.items() if q and not after.get(s))
    flipped = sorted(s for s, q in after.items() if q and before.get(s) and (before[s] > 0) != (q > 0))
    resized = sum(1 for s, q in after.items()
                  if q and before.get(s) and s not in flipped and abs(q - before[s]) > 1e-12)
    n_long = sum(1 for q in after.values() if q > 0)
    n_short = sum(1 for q in after.values() if q < 0)
    capital = float(state.get("capital") or 0.0)
    lines = [f"🔁 *v3 {REASONS.get(row.get('reason'), row.get('reason'))}* · {utc_to_tr(row.get('ts'))} TSİ", LINE,
             f"🧾 {row.get('n_orders', 0)} emir · işlem hacmi {usd(row.get('turnover_usdt'))} · maliyet {usd(row.get('fees'))}"]
    if opened:
        lines.append("🆕 Açılan: " + ", ".join(f"{short(s)} ({side(after[s])})" for s in opened))
    if closed:
        lines.append("❌ Kapanan: " + ", ".join(short(s) for s in closed))
    if flipped:
        lines.append("🔄 Yön değiştiren: " + ", ".join(f"{short(s)} ({side(before[s])}→{side(after[s])})" for s in flipped))
    if resized:
        lines.append(f"⚖️ Boyutu ayarlanan: {resized} coin")
    lines.append(f"📌 Portföy: {n_long} LONG / {n_short} SHORT")
    lines.append(f"💼 Kasa: `{usd(equity)}` ({pct((equity / capital - 1) * 100 if capital else 0.0)})")
    if row.get("reason") == "dusus_kesici":
        lines.append(f"⚠️ Risk ölçeği {float(state.get('scale', 1.0)):.1f}x'e düşürüldü")
    return "\n".join(lines)


# --------------------------------------------------------------------------------------
# Komut ve zamanlanmış gönderim yardımcıları
# --------------------------------------------------------------------------------------
def status_text(engine=None) -> str:
    eng = _engine(engine)
    snap = eng.snapshot()
    now_ms = eng.data.now_ms()
    today = compute_day(eng.store, eng.state["capital"], snap, today_tr(now_ms), now_ms)
    return status_message(snap, today)


def positions_text(engine=None) -> str:
    return positions_message(_engine(engine).snapshot())


def send_daily_report(notifier, date_tr: str, engine=None) -> bool:
    if notifier is None or not getattr(notifier, "has_telegram", False):
        return False
    return bool(notifier.send_text_message(daily_report_message(engine, date_tr, final=True)))


_REPORT_LOCK = threading.Lock()


def send_scheduled_daily_report(notifier, date_tr: str) -> bool:
    """
    Gün sonu raporunu o gün için yalnızca BİR KEZ gönderir. Ana döngü ve panel döngüsü aynı anda
    tetiklese bile kilit + "gönderildi" kaydı çift gönderimi önler. SMC kapalıyken v3 raporu gider.
    """
    from core.database import is_daily_report_sent_db, mark_daily_report_sent_db
    if notifier is None:
        return False
    with _REPORT_LOCK:
        if is_daily_report_sent_db(date_tr):
            return False
        if config.ENABLE_SMC_ENGINE:
            sent = bool((notifier.send_daily_summary_report(target_date_str=date_tr) or {}).get("sent", False))
        else:
            sent = send_daily_report(notifier, date_tr)
        if sent:
            mark_daily_report_sent_db(date_tr)
        return sent
