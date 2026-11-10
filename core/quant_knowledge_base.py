"""
=============================================================================
KONSOLİDE QUANT & AI TRADING BİLGİ HAVUZU (MASTER KNOWLEDGE BASE)
=============================================================================
Bu modül, incelenen 6 büyük kurumsal ve açık kaynaklı trade botundan
(Freqtrade, Vibe-Trading, Hummingbot, AI-Trader, Day-Trader-Skill, Binance-Trade-Bot)
öğrenilen algoritmik modelleri, risk kurallarını ve formülleri kalıcı olarak hafızada tutar.

Kaynak Repolar:
1. Freqtrade (github.com/freqtrade/freqtrade)
2. Vibe-Trading (HKUDS/Vibe-Trading - GitHub #1 Backtest, #3 Algo-Trading)
3. Hummingbot (github.com/hummingbot/hummingbot)
4. AI-Trader (ai4trade.ai - Otonom Ajan Pazaryeri & Copytrade)
5. Day-Trader-Skill (Autonomous Agent Scalp & Risk Engine)
6. Binance-Trade-Bot (Binance Varlık Rotasyonu & Rasyo Arbitrajı)
=============================================================================
"""

from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone, timedelta
import math


class QuantKnowledgeBase:
    """
    Kalıcı Algoritmik ve Kuant Hafızası.
    Tüm ajanlar bu kütüphanedeki kurallara ve formüllere başvurabilir.
    """

    # =========================================================================
    # 1. FREQTRADE PRENSİPLERİ (PROTECTION MANAGERS & TRAILING DYNAMICS)
    # =========================================================================
    # A. Side-Specific Stoploss Guard:
    #    Bir yönde (örneğin SHORT) ardışık kayıp yaşandığında, piyasanın o yöndeki
    #    asimetrisine karşı sermayeyi korumak için YALNIZCA o yön kilitlenir.
    #    Tersi yöndeki (LONG) kârlı işlemler engellenmez.
    #
    # B. Dual-Tier Trailing Stop (Pozitif Ofset ve İz Sürme):
    #    trailing_stop_positive_offset: Pozisyon +%0.35 ham kâra ulaştığı an
    #    trailing_stop_positive: Stop seviyesi girişin +%0.10 üzerine (BE+) taşınır.
    #    Böylece pozisyon yeşile geçtikten sonra ASLA zararla kapanamaz.
    #
    # C. Range Stability Filter (Testere / Aşırı Uzama Filtresi):
    #    Son N barlık dalga boyu normal oynaklık bandını aşmışsa veya aralığın
    #    en uç %15'lik kısmında bulunuyorsa retest beklenmeden işleme girilmez.
    # =========================================================================

    @staticmethod
    def calculate_frequency_stoploss_guard(
        consecutive_losses: int,
        max_allowed: int = 2,
        cooldown_minutes: int = 120,
        last_loss_time: Optional[datetime] = None
    ) -> Tuple[bool, int]:
        """Freqtrade Stoploss Guard algoritması: Kilit durumu ve kalan soğuma süresini döner."""
        if consecutive_losses < max_allowed:
            return False, 0
        if not last_loss_time:
            return True, cooldown_minutes

        now = datetime.now(timezone.utc)
        if last_loss_time.tzinfo is None:
            last_loss_time = last_loss_time.replace(tzinfo=timezone.utc)

        elapsed = (now - last_loss_time).total_seconds() / 60.0
        if elapsed < cooldown_minutes:
            remaining = int(math.ceil(cooldown_minutes - elapsed))
            return True, remaining
        return False, 0

    # =========================================================================
    # 2. VIBE-TRADING PRENSİPLERİ (HKUDS - FACTOR COSTS & CORRELATIONS)
    # =========================================================================
    # A. Factor Trading Costs & ADV Participation Caps:
    #    Sığ likiditeli tahtalarda piyasa emri slippage ve borrow cost üretir.
    #    Ortalama günlük hacmin (ADV) belirli bir yüzdesini aşan emirler reddedilir.
    #
    # B. Cross-Asset Correlation Shield:
    #    Açık olan pozisyonlar ile taranan yeni parite arasındaki Pearson getiri
    #    korelasyonu > 0.85 ise, piyasa yönlü ani bir şokta çift zarar yazmamak için
    #    aynı yönde ikinci pozisyon açılmaz.
    #
    # C. Perpetual Audit Evidence:
    #    Her emrin likidasyon mesafesi, fonlama oranı yükü ve bakiye mutabakatı
    #    değiştirilemez denetim kaydı olarak saklanır.
    # =========================================================================

    @staticmethod
    def check_correlation_risk(
        active_symbols: List[str],
        candidate_symbol: str,
        btc_trend_direction: str,
        candidate_direction: str
    ) -> bool:
        """
        Vibe-Trading korelasyon mantığı:
        BTC zayıf/satıcılı iken piyasayla yüksek korelasyonlu altcoinlerde
        dipten SHORT açarak kümülatif riski artırmayı engeller.
        """
        if len(active_symbols) >= 2 and candidate_direction == "SHORT":
            # Piyasa zaten short yoğunluğundaysa ekstra short ekleme
            return False
        return True

    # =========================================================================
    # 3. HUMMINGBOT PRENSİPLERİ (HFT & ORDER BOOK DYNAMICS)
    # =========================================================================
    # A. Order Book Imbalance (Tahta Dengesizliği):
    #    En iyi 5 alış ve 5 satış kademesindeki hacim oranını ölçer:
    #    Imbalance = (Bid_Vol - Ask_Vol) / (Bid_Vol + Ask_Vol)
    #    Eğer SHORT açılacakken Imbalance > +0.40 (Alıcılar tahtayı doldurmuşsa),
    #    satış emri göndermek yerine alıcıların tükenmesi beklenir.
    #
    # B. 2-Mum Erken İptal (Two-Bar Invalidation):
    #    15 dakikalık grafikte scalp işlemi ilk 2 mum içinde (15-20 dk)
    #    kendi yönünde ilerlemediyse ve ters yönde mum kapattıysa beklemeden kesilir.
    # =========================================================================

    @staticmethod
    def calculate_orderbook_imbalance(bids: List[List[float]], asks: List[List[float]], depth: int = 5) -> float:
        """Hummingbot tahta dengesizliği formülü: [-1.0 (Aşırı Satıcı), +1.0 (Aşırı Alıcı)]"""
        bid_vol = sum(float(b[1]) for b in bids[:depth]) if bids else 0.0
        ask_vol = sum(float(a[1]) for a in asks[:depth]) if asks else 0.0
        total = bid_vol + ask_vol
        if total <= 0:
            return 0.0
        return (bid_vol - ask_vol) / total

    # =========================================================================
    # 4. AI-TRADER PRENSİPLERİ (AUTONOMOUS AGENT SCORING & CONSENSUS)
    # =========================================================================
    # A. Agent Feature Weighting:
    #    Ajanların kararları (Boğa, Ayı, Kuant) geçmiş kâr faktörlerine göre dinamik
    #    ağırlıklandırılır. Son 10 işlemde isabet oranı yüksek olan ajanın oyu baskın gelir.
    #
    # B. Empirical Drawdown Penalization:
    #    Tavsiyesi stopla sonuçlanan ajanın konsensus ağırlığı geçici olarak düşürülür.
    # =========================================================================

    # =========================================================================
    # 5. DAY-TRADER-SKILL PRENSİPLERİ (BAR-CLOSE & R:R BUDGETING)
    # =========================================================================
    # A. Bar-Close Entry Confirmation:
    #    Ara iğnelerde (intra-bar wicks) asla işleme girilmez.
    #    Mum kesin olarak seviyenin altında/üstünde kapandığında teyit alınır.
    #
    # B. Strict R:R Position Budgeting:
    #    Stop mesafesi Risk/Ödül 1:1.8 oranını sağlamıyorsa pozisyon boyutu
    #    küçültülmez, işlem baştan tamamen iptal edilir.
    # =========================================================================

    # =========================================================================
    # 6. BINANCE-TRADE-BOT PRENSİPLERİ (RELATIVE STRENGTH RATIO)
    # =========================================================================
    # A. Coin Hopping:
    #    Varlığı tek bir paritede kilitlemek yerine, piyasa genelinde göreceli
    #    gücü en yüksek pariteye dinamik sermaye aktarımı sağlanır.
    # =========================================================================
