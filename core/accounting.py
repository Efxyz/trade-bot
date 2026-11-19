"""
Saf muhasebe yardımcıları (I/O yok, birim testlenebilir).
- Fonlama (funding) maliyeti tahmini
- Fonlamanın net marjin PnL yüzdesine yansıtılması
"""
from datetime import datetime, timedelta

FUNDING_HOURS_UTC = (0, 8, 16)  # Binance USDT-M çoğu sembol için 8 saatlik uzlaşma saatleri (UTC)


def count_funding_settlements(entered_utc: datetime, closed_utc: datetime) -> int:
    """(entered, closed] aralığında kaç fonlama uzlaşma anı (00/08/16 UTC) geçtiğini sayar."""
    if not entered_utc or not closed_utc or closed_utc <= entered_utc:
        return 0
    count = 0
    t = entered_utc.replace(minute=0, second=0, microsecond=0)
    while t <= closed_utc:
        if t > entered_utc and t.hour in FUNDING_HOURS_UTC:
            count += 1
        t += timedelta(hours=1)
    return count


def estimate_funding_usd(entered_utc: datetime, closed_utc: datetime, notional_usd: float,
                         funding_rate: float, is_long: bool) -> float:
    """
    Pozisyonun ödediği (+) veya aldığı (-) fonlama tutarı ($).
    Pozitif oran: LONG öder, SHORT alır. Uzlaşma anlarındaki oran bilinmediği için kapanış anındaki
    güncel oran yaklaşık değer olarak kullanılır.
    """
    n = count_funding_settlements(entered_utc, closed_utc)
    if n == 0 or not notional_usd or not funding_rate:
        return 0.0
    per = notional_usd * funding_rate
    return round(n * (per if is_long else -per), 4)


def apply_funding_to_pnl(net_pnl_pct: float, gross_pnl_pct: float, margin_usd: float, funding_usd: float):
    """Fonlama maliyetini marjin bazlı net PnL yüzdesinden düşer. Döner: (net_pct, gross_pct)."""
    if not margin_usd or not funding_usd:
        return net_pnl_pct, gross_pnl_pct
    delta_pct = funding_usd / margin_usd * 100.0
    return round(net_pnl_pct - delta_pct, 2), gross_pnl_pct
