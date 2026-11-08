"""
All-in-One Trading Office Dashboard for Binance Futures Trade Bot
Visualizes the active trading desk like a real office:
- Active Scalps with Real SVG Candlestick Charts & Exact Green TP / Red SL levels
- Scanner & Analysis Desk: Live feed of coins examined and why approved/rejected
- News & Sentiment Desk (Sağ Alt): Live market news with Bullish/Bearish tags
- Bottom PnL Ledger & Realized Vault
"""
import os
import sys
import json
import webbrowser
import threading
from datetime import datetime
from pathlib import Path
from flask import Flask, jsonify, render_template_string, send_from_directory

from config import (
    CHARTS_DIR,
    DB_PATH,
    MAX_CONCURRENT_TRADES,
    BINANCE_ROUNDTRIP_FEE_PCT,
    PORTFOLIO_EQUITY_USDT
)
from core.binance_client import BinanceFuturesClient
from core.database import (
    get_all_signals,
    get_active_and_pending_signals,
    get_performance_stats
)
from agents.scanner_agent import get_scanner_logs, add_scanner_log
from agents.news_agent import get_live_news_feed, NewsAgent

app = Flask(__name__)
client = BinanceFuturesClient()
news_agent = NewsAgent()

_orchestrator = None

HTML_OFFICE_TEMPLATE = """
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>⚡ AI Fon Ofisi - Canlı İşlem Masası</title>
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
    <style>
        :root {
            --bg-body: #090d16;
            --panel-bg: #111622;
            --panel-border: #1f2738;
            --card-bg: #151c2c;
            --card-hover: #1a2337;
            --green: #10b981;
            --green-bg: rgba(16, 185, 129, 0.12);
            --red: #ef4444;
            --red-bg: rgba(239, 68, 68, 0.12);
            --cyan: #38bdf8;
            --cyan-bg: rgba(56, 189, 248, 0.12);
            --yellow: #f59e0b;
            --text-main: #f1f5f9;
            --text-muted: #8492a6;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            background-color: var(--bg-body);
            color: var(--text-main);
            font-family: 'Inter', -apple-system, sans-serif;
            height: 100vh;
            display: flex;
            flex-direction: column;
            overflow: hidden;
            user-select: none;
        }

        /* Top Header */
        .topbar {
            height: 50px;
            background: var(--panel-bg);
            border-bottom: 1px solid var(--panel-border);
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 0 16px;
            flex-shrink: 0;
        }
        .brand { display: flex; align-items: center; gap: 8px; font-weight: 700; font-size: 14px; }
        .brand-badge {
            background: linear-gradient(135deg, #0284c7, #2563eb);
            color: #fff; width: 26px; height: 26px; border-radius: 6px;
            display: flex; align-items: center; justify-content: center; font-size: 14px;
        }
        .topbar-stats { display: flex; align-items: center; gap: 18px; font-size: 12px; }
        .top-stat { display: flex; align-items: center; gap: 6px; }
        .top-stat .lbl { color: var(--text-muted); font-size: 10px; text-transform: uppercase; }
        .top-stat .val { font-family: 'JetBrains Mono', monospace; font-weight: 700; }
        .btn-scan {
            background: #2563eb; color: #fff; border: none; padding: 5px 12px;
            border-radius: 5px; font-size: 11px; font-weight: 600; cursor: pointer;
            transition: 0.15s;
        }
        .btn-scan:hover { background: #1d4ed8; }

        /* Office Workspace: 3-Column / Grid Layout */
        .workspace {
            display: grid;
            grid-template-columns: 1.6fr 1fr;
            grid-template-rows: 1fr 210px;
            gap: 10px;
            padding: 10px;
            flex: 1;
            overflow: hidden;
        }

        .panel {
            background: var(--panel-bg);
            border: 1px solid var(--panel-border);
            border-radius: 8px;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }
        .panel-header {
            padding: 8px 14px;
            border-bottom: 1px solid var(--panel-border);
            font-size: 11px;
            font-weight: 700;
            display: flex;
            align-items: center;
            justify-content: space-between;
            background: rgba(255,255,255,0.015);
            flex-shrink: 0;
            letter-spacing: 0.3px;
        }
        .panel-header .counter {
            background: var(--panel-border);
            color: var(--text-muted);
            padding: 2px 6px;
            border-radius: 8px;
            font-size: 10px;
        }

        /* Sol Sütun: Aktif Scalp Kartları & Gerçek Mini Mum Grafiği */
        .cards-list {
            padding: 10px;
            overflow-y: auto;
            flex: 1;
            display: flex;
            flex-direction: column;
            gap: 12px;
        }
        .pos-card {
            background: var(--card-bg);
            border: 1px solid var(--panel-border);
            border-radius: 8px;
            padding: 12px 14px;
            display: flex;
            flex-direction: column;
            gap: 8px;
            transition: 0.15s;
        }
        .pos-card:hover { border-color: var(--cyan); }
        .card-header {
            display: flex; justify-content: space-between; align-items: center;
        }
        .card-title { display: flex; align-items: center; gap: 8px; font-size: 15px; font-weight: 700; }
        .tag {
            font-size: 10px; font-weight: 700; padding: 2px 6px; border-radius: 4px; text-transform: uppercase;
        }
        .tag-long { background: var(--green-bg); color: var(--green); border: 1px solid var(--green); }
        .tag-short { background: var(--red-bg); color: var(--red); border: 1px solid var(--red); }
        .tag-lev { background: var(--cyan-bg); color: var(--cyan); border: 1px solid var(--cyan); }

        .card-pnl {
            font-family: 'JetBrains Mono', monospace; font-size: 18px; font-weight: 700;
        }
        .pnl-pos { color: var(--green); }
        .pnl-neg { color: var(--red); }

        /* Aktif İşlemler İki Kısımlı Bölüm ve Özet Barı */
        .active-summary-bar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 8px 12px;
            background: #141926;
            border-bottom: 1px solid var(--panel-border);
            font-size: 11px;
            font-weight: 600;
        }
        .sum-badge {
            padding: 2px 8px;
            border-radius: 4px;
            font-family: 'JetBrains Mono', monospace;
        }
        .sum-badge.all { background: #1a2337; color: #f1f5f9; }
        .sum-badge.green { background: rgba(16, 185, 129, 0.15); color: #10b981; }
        .sum-badge.red { background: rgba(239, 68, 68, 0.15); color: #ef4444; }

        .pos-section-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 7px 10px;
            border-radius: 6px;
            font-size: 11px;
            font-weight: 700;
            margin-top: 4px;
        }
        .pos-section-header.green-sec {
            background: rgba(16, 185, 129, 0.1);
            border-left: 3px solid #10b981;
            color: #10b981;
        }
        .pos-section-header.red-sec {
            background: rgba(239, 68, 68, 0.1);
            border-left: 3px solid #ef4444;
            color: #ef4444;
        }
        .pos-section-sub {
            font-size: 9px;
            font-weight: 500;
            color: var(--text-muted);
        }

        /* Yan Yana İki Sütunlu Grid: Sol = Kar, Sağ = Zarar */
        .active-two-cols {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
            flex: 1;
            overflow: hidden;
            padding: 8px;
        }
        .active-sub-col {
            display: flex;
            flex-direction: column;
            overflow: hidden;
            background: rgba(13, 18, 28, 0.4);
            border: 1px solid var(--panel-border);
            border-radius: 8px;
            padding: 6px;
        }
        .cards-sub-list {
            flex: 1;
            overflow-y: auto;
            display: flex;
            flex-direction: column;
            gap: 10px;
            padding: 4px;
            margin-top: 6px;
        }

        .card-elapsed {
            font-size: 10px;
            font-family: 'JetBrains Mono', monospace;
            font-weight: 600;
            background: rgba(255, 255, 255, 0.06);
            color: #94a3b8;
            padding: 2px 7px;
            border-radius: 4px;
            border: 1px solid rgba(255, 255, 255, 0.08);
        }
        .btn-clear {
            background: rgba(239, 68, 68, 0.12);
            border: 1px solid rgba(239, 68, 68, 0.35);
            color: #ef4444;
            padding: 3px 10px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
        }
        .btn-clear:hover {
            background: rgba(239, 68, 68, 0.25);
            border-color: #ef4444;
            transform: translateY(-1px);
        }
        .btn-panic {
            background: rgba(239, 68, 68, 0.15);
            border: 1px solid rgba(239, 68, 68, 0.4);
            color: #ef4444;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 10px;
            font-weight: 700;
            cursor: pointer;
            transition: all 0.2s;
        }
        .btn-panic:hover {
            background: #ef4444;
            color: #fff;
            transform: translateY(-1px);
        }

        /* Gerçek Mini SVG Mum Grafiği Kutusu */
        .mini-chart-box {
            background: #0d121c;
            border: 1px solid var(--panel-border);
            border-radius: 6px;
            padding: 8px 10px;
            position: relative;
        }
        .chart-svg {
            width: 100%; height: 110px; display: block; overflow: visible;
        }

        /* Proximity Badges Row */
        .proximity-row {
            display: flex; justify-content: space-between; font-size: 11px;
            font-family: 'JetBrains Mono', monospace; font-weight: 600;
            background: rgba(0,0,0,0.2); padding: 6px 10px; border-radius: 4px;
        }
        .prox-sl { color: var(--red); }
        .prox-tp { color: var(--green); }

        /* Sağ Taraf Split: Üstte Tarama Masası, Altta Haber Masası */
        .right-split {
            display: grid;
            grid-template-rows: 1.1fr 1fr;
            gap: 10px;
            overflow: hidden;
        }

        /* 📡 Tarama Masası (Neden Elendi / Uygun Bulundu) */
        .log-list {
            padding: 8px;
            overflow-y: auto;
            flex: 1;
            display: flex;
            flex-direction: column;
            gap: 6px;
        }
        .log-item {
            background: #141926;
            border: 1px solid var(--panel-border);
            border-radius: 6px;
            padding: 8px 10px;
            font-size: 11px;
            display: flex;
            flex-direction: column;
            gap: 3px;
        }
        .log-item.approved { border-left: 3px solid var(--green); }
        .log-item.rejected { border-left: 3px solid #64748b; }

        .log-top { display: flex; justify-content: space-between; align-items: center; }
        .log-sym { font-weight: 700; font-family: 'JetBrains Mono', monospace; }
        .log-time { color: var(--text-muted); font-size: 10px; }
        .log-reason { font-size: 11px; color: var(--text-muted); line-height: 1.3; }
        .badge-appr { color: var(--green); font-weight: 700; }
        .badge-rej { color: #94a3b8; font-weight: 600; }

        /* 📰 Sağ Altta Haber & Duygu Masası */
        .news-list {
            padding: 8px;
            overflow-y: auto;
            flex: 1;
            display: flex;
            flex-direction: column;
            gap: 6px;
        }
        .news-item {
            background: #141926;
            border: 1px solid var(--panel-border);
            border-radius: 6px;
            padding: 7px 10px;
            font-size: 11px;
            display: flex;
            flex-direction: column;
            gap: 2px;
        }
        .news-meta {
            display: flex; justify-content: space-between; align-items: center; font-size: 10px; color: var(--text-muted);
        }
        .news-title {
            font-size: 11px; font-weight: 500; line-height: 1.35; color: #e2e8f0;
        }

        /* 🏛️ Ajanlar Yatırım Komitesi Tartışma Odası */
        .debate-tabs {
            display: flex; gap: 6px; align-items: center;
        }
        .debate-tab-btn {
            background: rgba(255, 255, 255, 0.04);
            border: 1px solid var(--panel-border);
            color: var(--text-muted);
            padding: 3px 9px;
            border-radius: 4px;
            font-size: 10px;
            font-weight: 700;
            cursor: pointer;
            transition: all 0.2s;
        }
        .debate-tab-btn.active {
            background: rgba(56, 189, 248, 0.16);
            border-color: #38bdf8;
            color: #38bdf8;
        }
        .debate-list {
            padding: 8px;
            overflow-y: auto;
            flex: 1;
            display: flex;
            flex-direction: column;
            gap: 10px;
        }
        .debate-card {
            background: #101622;
            border: 1px solid var(--panel-border);
            border-radius: 8px;
            padding: 9px 11px;
            display: flex;
            flex-direction: column;
            gap: 8px;
        }
        .debate-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            padding-bottom: 6px;
        }
        .debate-sym {
            font-weight: 800;
            font-size: 12px;
            display: flex;
            align-items: center;
            gap: 6px;
        }
        .debate-score {
            font-family: 'JetBrains Mono', monospace;
            font-size: 10.5px;
            font-weight: 800;
            padding: 2px 7px;
            border-radius: 4px;
        }
        .debate-score-approved {
            background: rgba(34, 197, 94, 0.15);
            border: 1px solid #22c55e;
            color: #22c55e;
        }
        .debate-score-rejected {
            background: rgba(239, 68, 68, 0.15);
            border: 1px solid #ef4444;
            color: #ef4444;
        }
        .dialogue-bubble {
            padding: 6px 9px;
            border-radius: 6px;
            font-size: 10.5px;
            line-height: 1.4;
            display: flex;
            flex-direction: column;
            gap: 2px;
        }
        .bubble-bull {
            background: rgba(34, 197, 94, 0.06);
            border-left: 3px solid #22c55e;
            color: #dcfce7;
        }
        .bubble-bear {
            background: rgba(239, 68, 68, 0.06);
            border-left: 3px solid #ef4444;
            color: #fee2e2;
        }
        .bubble-macro {
            background: rgba(56, 189, 248, 0.06);
            border-left: 3px solid #38bdf8;
            color: #e0f2fe;
        }
        .bubble-chief {
            background: rgba(245, 158, 11, 0.08);
            border-left: 3px solid #f59e0b;
            color: #fef3c7;
            font-weight: 600;
        }
        .speaker-title {
            font-size: 9px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            opacity: 0.9;
            display: flex;
            align-items: center;
            gap: 4px;
        }
        .sent-bull { color: var(--green); font-weight: 700; }
        .sent-bear { color: var(--red); font-weight: 700; }
        .sent-neut { color: var(--cyan); font-weight: 600; }

        /* Tauric Research Episodik Hafıza & Refleksiyon Kartları */
        .reflection-card {
            background: rgba(15, 23, 42, 0.7);
            border: 1px solid rgba(148, 163, 184, 0.15);
            border-radius: 6px;
            padding: 9px 12px;
            display: flex;
            flex-direction: column;
            gap: 6px;
            transition: all 0.2s;
        }
        .reflection-card:hover {
            border-color: rgba(56, 189, 248, 0.35);
            background: rgba(15, 23, 42, 0.9);
        }
        .reflection-top {
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        .reflection-lesson {
            font-size: 11px;
            line-height: 1.45;
            color: #e2e8f0;
        }

        /* Alt Kısım: PnL Kasası & Geçmiş */
        .bottom-panel {
            grid-column: 1 / -1;
        }
        .table-scroll { flex: 1; overflow-y: auto; }
        table { width: 100%; border-collapse: collapse; font-size: 11px; }
        th {
            background: #151b28; color: var(--text-muted); font-size: 10px; text-transform: uppercase;
            padding: 8px 12px; text-align: left; position: sticky; top: 0; border-bottom: 1px solid var(--panel-border);
        }
        td { padding: 8px 12px; border-bottom: 1px solid rgba(255,255,255,0.03); }
        tr:hover td { background: rgba(255,255,255,0.02); }
        .mono { font-family: 'JetBrains Mono', monospace; font-weight: 600; }

        /* 📈 Canlı TradingView BTC Futures Grafiği ve Görünüm Seçici Stilleri */
        .view-tab-btn {
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid var(--panel-border);
            color: var(--text-muted);
            padding: 4px 10px;
            border-radius: 5px;
            font-size: 11px;
            font-weight: 700;
            cursor: pointer;
            transition: all 0.2s;
            display: inline-flex;
            align-items: center;
            gap: 6px;
        }
        .view-tab-btn:hover {
            background: rgba(255, 255, 255, 0.09);
            color: #fff;
        }
        .view-tab-btn.active {
            background: rgba(56, 189, 248, 0.18);
            border-color: #38bdf8;
            color: #38bdf8;
        }

        /* Zaman Dilimi Butonları (15D, 1S, 4S, 1G) */
        .tf-btn {
            background: transparent;
            border: 1px solid transparent;
            color: var(--text-muted);
            padding: 2px 7px;
            border-radius: 3px;
            font-size: 10px;
            font-family: 'JetBrains Mono', monospace;
            font-weight: 700;
            cursor: pointer;
            transition: all 0.15s;
        }
        .tf-btn:hover {
            color: #fff;
            background: rgba(255, 255, 255, 0.08);
        }
        .tf-btn.active {
            background: #2563eb;
            border-color: #3b82f6;
            color: #fff;
        }

        /* Tam Ekran Butonları */
        .btn-fullscreen {
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid var(--panel-border);
            color: var(--text-muted);
            padding: 3px 8px;
            border-radius: 4px;
            font-size: 10px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
        }
        .btn-fullscreen:hover {
            background: rgba(56, 189, 248, 0.15);
            border-color: #38bdf8;
            color: #38bdf8;
        }
        .btn-exit-fullscreen {
            position: absolute;
            top: 14px;
            right: 14px;
            z-index: 1000000;
            background: rgba(239, 68, 68, 0.9);
            color: #fff;
            border: none;
            padding: 6px 14px;
            border-radius: 6px;
            font-size: 12px;
            font-weight: 700;
            cursor: pointer;
            box-shadow: 0 4px 15px rgba(0,0,0,0.5);
            transition: 0.2s;
        }
        .btn-exit-fullscreen:hover {
            background: #dc2626;
            transform: scale(1.05);
        }

        /* Canlı BTC Futures Grafik Kapsayıcısı */
        .btc-chart-wrapper {
            flex: 1;
            width: 100%;
            height: 100%;
            min-height: 380px;
            display: flex;
            flex-direction: column;
            position: relative;
            overflow: hidden;
            background: #090d16;
        }
        .btc-chart-wrapper.is-fullscreen {
            position: fixed;
            top: 0;
            left: 0;
            width: 100vw;
            height: 100vh;
            z-index: 999999;
            padding: 10px;
            background: #090d16;
        }

        /* 📱 Mobil ve Tablet Cihazlar İçin Tam Duyarlı (Responsive) Tasarım */
        @media (max-width: 1024px) {
            body {
                height: auto;
                min-height: 100vh;
                overflow-y: auto;
                user-select: auto;
            }
            .topbar {
                height: auto;
                padding: 10px 14px;
                flex-direction: column;
                gap: 8px;
                align-items: flex-start;
            }
            .topbar-right {
                width: 100%;
                justify-content: space-between;
                flex-wrap: wrap;
                gap: 6px;
            }
            .workspace {
                display: flex;
                flex-direction: column;
                height: auto;
                overflow: visible;
                padding: 8px;
                gap: 12px;
            }
            .active-two-cols {
                grid-template-columns: 1fr;
                height: auto;
                max-height: 480px;
            }
            .bottom-panel {
                height: auto;
                min-height: 280px;
            }
            .panel {
                min-height: 260px;
            }
        }
    </style>
</head>
<body>

    <!-- Top Bar -->
    <div class="topbar">
        <div class="brand">
            <div class="brand-badge">⚡</div>
            <span>AI Ticaret Ofisi Terminali</span>
            <span style="font-size: 10px; background: rgba(16,185,129,0.15); color: #10b981; padding: 2px 7px; border-radius: 10px; font-weight: 600;">● OFİS CANLI</span>
            <span id="wsBadge" style="font-size: 10px; background: rgba(56,189,248,0.15); color: #38bdf8; padding: 2px 7px; border-radius: 10px; font-weight: 600;">⚡ WSS AKTİF</span>
        </div>

        <div class="topbar-stats">
            <div class="top-stat" style="cursor: pointer;" onclick="switchLeftView('btc')" title="Tıkla: Canlı BTC Mum Grafiğini Aç">
                <span class="lbl">BTC Rejimi:</span>
                <span class="val" id="topBtc" style="color: var(--yellow);">TARANIYOR</span>
            </div>
            <div class="top-stat">
                <span class="lbl">Kasa Kalkanı:</span>
                <span class="val" id="topShieldQuota" style="color: var(--green);">0/4 Pozisyon</span>
            </div>
            <div class="top-stat">
                <span class="lbl">Fon Kasası:</span>
                <span class="val" id="topEquity" style="color: #38bdf8;">$1,000.00</span>
            </div>
            <div class="top-stat">
                <span class="lbl">Net Kasa Kârı:</span>
                <span class="val" id="topRealized" style="color: var(--green);">+0.0%</span>
            </div>
            <div class="top-stat">
                <span class="lbl">Canlı PnL:</span>
                <span class="val" id="topUnrealized" style="color: var(--text-muted);">%0.0</span>
            </div>
            <div class="top-stat">
                <span class="lbl">Ödenen Komisyon:</span>
                <span class="val" id="topFees" style="color: #f59e0b;">-%0.0</span>
            </div>
            <div class="top-stat">
                <span class="lbl">Win Rate:</span>
                <span class="val" id="topWinRate" style="color: var(--yellow);">%0.0</span>
            </div>
            <div class="top-stat">
                <span class="lbl">Kâr Faktörü:</span>
                <span class="val" id="topProfitFactor" style="color: #38bdf8;">0.0</span>
            </div>
            <div style="display: flex; gap: 6px; align-items: center;">
                <button class="btn-scan" style="background: rgba(245,158,11,0.18); color: #f59e0b; border: 1px solid rgba(245,158,11,0.4);" onclick="switchLeftView('btc')" title="Canlı BTC Vadeli Mum Grafiğini Aç">📈 BTC Grafik</button>
                <button class="btn-scan" onclick="triggerScan()">⚡ Tara</button>
            </div>
        </div>
    </div>

    <!-- Main Workspace -->
    <div class="workspace">

        <!-- 1. SOL SÜTUN: Canlı BTC Futures Grafiği & Aktif Pozisyonlar Masası -->
        <div class="panel" id="leftPanel">
            <div class="panel-header" style="display: flex; justify-content: space-between; align-items: center; gap: 8px; flex-wrap: wrap;">
                <div style="display: flex; align-items: center; gap: 6px;">
                    <button class="view-tab-btn active" id="tabViewBtc" onclick="switchLeftView('btc')">
                        📈 CANLI BTC (FUTURES)
                    </button>
                    <button class="view-tab-btn" id="tabViewPositions" onclick="switchLeftView('positions')">
                        ⚡ POZİSYONLAR (<span id="activeCountBtn">0</span>)
                    </button>
                    <button class="view-tab-btn" id="tabViewSplit" onclick="switchLeftView('split')">
                        🔲 İKİLİ GÖRÜNÜM
                    </button>
                    <span class="counter" id="activeCount" style="display: none;">0 Aktif</span>
                </div>
                
                <div style="display: flex; align-items: center; gap: 6px;">
                    <!-- 15D, 1S, 4S, 1G Zaman Dilimi Seçici -->
                    <div id="btcTfGroup" style="display: flex; gap: 3px; align-items: center; background: rgba(0,0,0,0.3); padding: 2px 6px; border-radius: 4px; border: 1px solid var(--panel-border);">
                        <span style="font-size: 9.5px; color: var(--text-muted); font-weight: 700;">PERİYOT:</span>
                        <button class="tf-btn active" id="tf-15" onclick="changeBtcTimeframe('15')">15D</button>
                        <button class="tf-btn" id="tf-60" onclick="changeBtcTimeframe('60')">1S</button>
                        <button class="tf-btn" id="tf-240" onclick="changeBtcTimeframe('240')">4S</button>
                        <button class="tf-btn" id="tf-D" onclick="changeBtcTimeframe('D')">1G</button>
                    </div>
                    <button class="btn-fullscreen" onclick="toggleBtcFullscreen()" title="Grafiği Tam Ekran Yap">⛶ Tam Ekran</button>
                </div>
            </div>

            <!-- CANLI TRADINGVIEW BITCOIN FUTURES GRAFİĞİ -->
            <div id="btcChartContainer" class="btc-chart-wrapper">
                <button class="btn-exit-fullscreen" id="btnExitFs" onclick="toggleBtcFullscreen()" style="display: none;">✕ Tam Ekrandan Çık (ESC)</button>
                <div id="tv_chart_target" style="width: 100%; height: 100%;"></div>
            </div>

            <!-- AKTİF POZİSYONLAR ALANI -->
            <div id="positionsContainer" style="display: none; flex-direction: column; flex: 1; overflow: hidden;">
                <!-- En Üst: Ne kadar aktif işlem olduğu özeti -->
                <div class="active-summary-bar">
                    <span class="sum-badge all">🎯 Toplam: <strong id="totalActiveCount">0</strong> Aktif</span>
                    <div style="display: flex; gap: 6px; align-items: center;">
                        <span class="sum-badge green">🟢 Kârda: <strong id="greenActiveCount">0</strong></span>
                        <span class="sum-badge red">🔴 Zararda: <strong id="redActiveCount">0</strong></span>
                        <button class="btn-panic" onclick="closeAllPositions()" title="Tüm açık işlemleri anlık fiyattan kapat">🚫 Tümünü Kapat</button>
                    </div>
                </div>
                <!-- Yan Yana İki Sütunlu Grid: Sol = KÂR, Sağ = ZARAR -->
                <div class="active-two-cols">
                    <!-- SOL SÜTUN: 🟢 KÂRDAKİ POZİSYONLAR -->
                    <div class="active-sub-col">
                        <div class="pos-section-header green-sec">
                            <span>🟢 KÂRDAKİLER (<span id="profitColCount">0</span>)</span>
                            <span class="pos-section-sub">En çok kârdan aza doğru ↓</span>
                        </div>
                        <div class="cards-sub-list" id="profitList">
                            <div style="text-align: center; color: var(--text-muted); padding: 30px 10px; font-size: 11px;">
                                Kârda pozisyon aranıyor...
                            </div>
                        </div>
                    </div>

                    <!-- SAĞ SÜTUN: 🔴 ZARARDAKİ POZİSYONLAR -->
                    <div class="active-sub-col">
                        <div class="pos-section-header red-sec">
                            <span>🔴 ZARARDAKİLER (<span id="lossColCount">0</span>)</span>
                            <span class="pos-section-sub">En çok zarardan aza doğru ↓</span>
                        </div>
                        <div class="cards-sub-list" id="lossList">
                            <div style="text-align: center; color: var(--text-muted); padding: 30px 10px; font-size: 11px;">
                                Zararda pozisyon yok.
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- 2. SAĞ SÜTUN: Ofis Çalışanları Masası (Tarama & Haber) -->
        <div class="right-split">

            <!-- Üst: 📡 Analiz Masası (Neden Elendi / Uygun Bulundu & Kontrol Sıklığı) -->
            <div class="panel">
                <div class="panel-header">
                    <span>📡 15M TARAMA & SCALP MASASI (200+ PARİTE ROTASYONU)</span>
                    <span class="counter" id="logCount">Canlı Rotasyon</span>
                </div>
                <div class="log-list" id="logList">
                    <div style="text-align: center; color: var(--text-muted); padding: 20px; font-size: 11px;">
                        Taranan coinler inceleniyor...
                    </div>
                </div>
            </div>

            <!-- Alt (Sağ Alt): 🏛️ Ajanlar Yatırım Komitesi & Haber Masası & AI Hafıza & Otonom Kalibrasyon -->
            <div class="panel">
                <div class="panel-header">
                    <div class="debate-tabs">
                        <button class="debate-tab-btn active" id="tabDebateBtn" onclick="switchRightTab('debate')">🏛️ KOMİTE</button>
                        <button class="debate-tab-btn" id="tabReflectBtn" onclick="switchRightTab('reflections')">🧠 HAFIZA</button>
                        <button class="debate-tab-btn" id="tabTuningBtn" onclick="switchRightTab('tuning')">🧬 OTONOM ÖĞRENME</button>
                        <button class="debate-tab-btn" id="tabNewsBtn" onclick="switchRightTab('news')">📰 HABER</button>
                    </div>
                    <span class="counter" id="debateCounter" style="color: #38bdf8;">Canlı Tartışma Odası</span>
                </div>
                
                <!-- Canlı Ajanlar Tartışma Odası (Tab 1) -->
                <div class="debate-list" id="debateList">
                    <div style="text-align: center; color: var(--text-muted); padding: 25px; font-size: 11px;">
                        🏛️ Ajanlar taranan pariteleri karşılıklı tartışmak üzere hazır bekliyor...
                    </div>
                </div>

                <!-- 🧠 Tauric Research Episodik Hafıza Defteri (Tab 2) -->
                <div class="debate-list" id="reflectionsList" style="display: none; flex-direction: column; gap: 8px;">
                    <div style="text-align: center; color: var(--text-muted); padding: 25px; font-size: 11px;">
                        🧠 AI Hafıza Defteri yükleniyor...
                    </div>
                </div>

                <!-- 🧬 Otonom Kendi Kendini Geliştirme & Parametre Kalibrasyonu (Tab 3) -->
                <div class="debate-list" id="tuningList" style="display: none; flex-direction: column; gap: 8px;">
                    <div style="text-align: center; color: var(--text-muted); padding: 25px; font-size: 11px;">
                        🧬 Otonom Öğrenme Motoru yükleniyor...
                    </div>
                </div>

                <!-- Haber Akışı (Tab 4) -->
                <div class="news-list" id="newsList" style="display: none;">
                    <div style="text-align: center; color: var(--text-muted); padding: 20px; font-size: 11px;">
                        Piyasa haberleri çekiliyor...
                    </div>
                </div>
            </div>

        </div>

        <!-- 3. ALT BÖLÜM: PnL Kasası & Tamamlanan İşlemler -->
        <div class="panel bottom-panel">
            <div class="panel-header">
                <div style="display: flex; align-items: center; gap: 12px;">
                    <span>💰 PnL KASASI & TAMAMLANAN İŞLEM DEFTERİ</span>
                    <button class="btn-clear" onclick="clearTradeHistory()">🗑️ Geçmişi Temizle</button>
                </div>
                <span class="counter" id="historyCount">0 İşlem</span>
            </div>
            <div class="table-scroll">
                <table>
                    <thead>
                        <tr>
                            <th>Kapanış</th>
                            <th>Parite</th>
                            <th>Yön</th>
                            <th>Kaldıraç</th>
                            <th>Giriş Fiyatı</th>
                            <th>Çıkış Fiyatı</th>
                            <th>Sonuç</th>
                            <th>Net Marjin PnL</th>
                        </tr>
                    </thead>
                    <tbody id="historyBody">
                        <tr><td colspan="8" style="text-align: center; color: var(--text-muted); padding: 20px;">Kapanan işlem kaydı yok.</td></tr>
                    </tbody>
                </table>
            </div>
        </div>

    </div>

    <script>
        let prevProfitHtml = '';
        let prevLossHtml = '';
        let prevLogsHtml = '';
        let prevDebatesHtml = '';
        let prevReflectHtml = '';
        let prevTuningHtml = '';
        let prevNewsHtml = '';
        let prevHistHtml = '';

        // Sol Panel Görünüm Modları: 'btc' (Sadece BTC), 'positions' (Sadece Pozisyonlar), 'split' (İkili)
        let currentLeftView = localStorage.getItem('leftViewMode') || 'btc';
        let currentBtcInterval = localStorage.getItem('btcInterval') || '15';
        let tvWidget = null;
        let lastRenderedInterval = null;

        function switchLeftView(mode) {
            currentLeftView = mode;
            localStorage.setItem('leftViewMode', mode);

            const btcContainer = document.getElementById('btcChartContainer');
            const posContainer = document.getElementById('positionsContainer');
            const tfGroup = document.getElementById('btcTfGroup');
            const tabBtc = document.getElementById('tabViewBtc');
            const tabPos = document.getElementById('tabViewPositions');
            const tabSplit = document.getElementById('tabViewSplit');

            if (tabBtc) tabBtc.classList.toggle('active', mode === 'btc');
            if (tabPos) tabPos.classList.toggle('active', mode === 'positions');
            if (tabSplit) tabSplit.classList.toggle('active', mode === 'split');

            if (mode === 'btc') {
                if (btcContainer) {
                    btcContainer.style.display = 'flex';
                    btcContainer.style.flex = '1';
                    btcContainer.style.height = '100%';
                    btcContainer.style.borderBottom = 'none';
                }
                if (posContainer) posContainer.style.display = 'none';
                if (tfGroup) tfGroup.style.display = 'flex';
                renderTradingView();
            } else if (mode === 'positions') {
                if (btcContainer) btcContainer.style.display = 'none';
                if (posContainer) {
                    posContainer.style.display = 'flex';
                    posContainer.style.flex = '1';
                    posContainer.style.height = '100%';
                }
                if (tfGroup) tfGroup.style.display = 'none';
            } else if (mode === 'split') {
                if (btcContainer) {
                    btcContainer.style.display = 'flex';
                    btcContainer.style.flex = '1.1';
                    btcContainer.style.height = '52%';
                    btcContainer.style.borderBottom = '1px solid var(--panel-border)';
                }
                if (posContainer) {
                    posContainer.style.display = 'flex';
                    posContainer.style.flex = '1';
                    posContainer.style.height = '48%';
                }
                if (tfGroup) tfGroup.style.display = 'flex';
                renderTradingView();
            }
        }

        function changeBtcTimeframe(tf) {
            currentBtcInterval = tf;
            localStorage.setItem('btcInterval', tf);
            ['15', '60', '240', 'D'].forEach(t => {
                const btn = document.getElementById('tf-' + t);
                if (btn) btn.classList.toggle('active', t === tf);
            });
            renderTradingView(true);
        }

        function renderTradingView(force = false) {
            const target = document.getElementById('tv_chart_target');
            if (!target) return;
            
            if (!force && lastRenderedInterval === currentBtcInterval && target.innerHTML.trim() !== '') {
                return;
            }

            ['15', '60', '240', 'D'].forEach(t => {
                const btn = document.getElementById('tf-' + t);
                if (btn) btn.classList.toggle('active', t === currentBtcInterval);
            });

            if (typeof TradingView !== 'undefined') {
                target.innerHTML = '';
                lastRenderedInterval = currentBtcInterval;
                try {
                    tvWidget = new TradingView.widget({
                        "autosize": true,
                        "symbol": "BINANCE:BTCUSDT.P",
                        "interval": currentBtcInterval,
                        "timezone": "Europe/Istanbul",
                        "theme": "dark",
                        "style": "1",
                        "locale": "tr",
                        "toolbar_bg": "#111622",
                        "enable_publishing": false,
                        "hide_top_toolbar": false,
                        "hide_legend": false,
                        "save_image": false,
                        "container_id": "tv_chart_target",
                        "studies": [
                            "MASimple@tv-basicstudies",
                            "RSI@tv-basicstudies"
                        ],
                        "allow_symbol_change": true,
                        "calendar": false,
                        "support_host": "https://www.tradingview.com"
                    });
                } catch(e) {
                    console.error("TradingView widget init error:", e);
                }
            } else {
                target.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#8492a6;font-size:12px;">📈 TradingView Canlı Mum Akışı Yükleniyor...</div>';
                setTimeout(() => renderTradingView(force), 500);
            }
        }

        function toggleBtcFullscreen() {
            const chartWrapper = document.getElementById('btcChartContainer');
            const exitBtn = document.getElementById('btnExitFs');
            if (!chartWrapper) return;
            const isFs = chartWrapper.classList.toggle('is-fullscreen');
            if (exitBtn) exitBtn.style.display = isFs ? 'block' : 'none';
            if (isFs) {
                chartWrapper.style.display = 'flex';
            } else {
                switchLeftView(currentLeftView);
            }
            setTimeout(() => renderTradingView(true), 150);
        }

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                const chartWrapper = document.getElementById('btcChartContainer');
                if (chartWrapper && chartWrapper.classList.contains('is-fullscreen')) {
                    toggleBtcFullscreen();
                }
            }
        });

        let activeRightTab = 'debate';
        function switchRightTab(tab) {
            activeRightTab = tab;
            const debateList = document.getElementById('debateList');
            const reflectList = document.getElementById('reflectionsList');
            const tuningList = document.getElementById('tuningList');
            const newsList = document.getElementById('newsList');

            const tabDebateBtn = document.getElementById('tabDebateBtn');
            const tabReflectBtn = document.getElementById('tabReflectBtn');
            const tabTuningBtn = document.getElementById('tabTuningBtn');
            const tabNewsBtn = document.getElementById('tabNewsBtn');
            const counter = document.getElementById('debateCounter');

            if (debateList) debateList.style.display = (tab === 'debate' ? 'flex' : 'none');
            if (reflectList) reflectList.style.display = (tab === 'reflections' ? 'flex' : 'none');
            if (tuningList) tuningList.style.display = (tab === 'tuning' ? 'flex' : 'none');
            if (newsList) newsList.style.display = (tab === 'news' ? 'flex' : 'none');

            if (tabDebateBtn) tabDebateBtn.classList.toggle('active', tab === 'debate');
            if (tabReflectBtn) tabReflectBtn.classList.toggle('active', tab === 'reflections');
            if (tabTuningBtn) tabTuningBtn.classList.toggle('active', tab === 'tuning');
            if (tabNewsBtn) tabNewsBtn.classList.toggle('active', tab === 'news');

            if (counter) {
                if (tab === 'debate') {
                    counter.innerText = 'Canlı Tartışma Odası';
                    counter.style.color = '#38bdf8';
                } else if (tab === 'reflections') {
                    counter.innerText = 'Tauric Episodik Hafıza';
                    counter.style.color = '#a855f7';
                } else if (tab === 'tuning') {
                    counter.innerText = 'Otonom Kalibrasyon';
                    counter.style.color = '#10b981';
                } else {
                    counter.innerText = 'Canlı RSS';
                    counter.style.color = '#f59e0b';
                }
            }
        }

        async function fetchTerminal() {
            try {
                const res = await fetch('/api/data');
                if (!res.ok) {
                    console.warn('/api/data HTTP status:', res.status);
                    return;
                }
                const data = await res.json();
                if (!data || data.error || !Array.isArray(data.active_positions)) {
                    console.warn('Geçersiz veri paketi:', data);
                    return;
                }
                renderAll(data);
            } catch (err) {
                console.error("fetchTerminal exception:", err);
            }
        }

        function fmtP(val) {
            const num = Number(val);
            if (isNaN(num)) return '0';
            if (num >= 100) return num.toFixed(2);
            if (num >= 1) return num.toFixed(4);
            return num.toPrecision(5);
        }

        // SVG Mini Çizgi Grafiği Renderer (Line Chart with Area Gradient & Exact Green TP / Red SL Lines)
        function renderMiniLineChart(candles, entry, live, sl, tp, isLong, symbol) {
            const width = 360;
            const height = 115;
            const pad = 14;

            // Fiyat noktalarını hazırla (kullanıcı her pozisyonda akıcı çizgi grafik görsün)
            let prices = [];
            if (candles && candles.length >= 3) {
                prices = candles.map(c => Number(c.close));
            } else {
                const steps = 12;
                const diff = (live - entry) / steps;
                for (let i = 0; i < steps; i++) {
                    const base = entry + (diff * i);
                    const noise = (i % 2 === 0 ? 1 : -1) * (base * 0.001);
                    prices.push(base + noise);
                }
            }
            // En son noktayı anlık canlı fiyata bağla
            prices.push(live);

            const n = prices.length;

            // Fiyat sınırlarını belirle ve taşmayı önlemek için %10 tampon ekle
            let minP = Math.min(sl, tp, ...prices, live, entry);
            let maxP = Math.max(sl, tp, ...prices, live, entry);
            const rawRange = (maxP - minP) || 1;
            const padVal = rawRange * 0.10;
            minP -= padVal;
            maxP += padVal;
            const range = maxP - minP;

            const scaleY = p => Math.max(pad, Math.min(height - pad, height - pad - (((p - minP) / range) * (height - (pad * 2)))));

            const ySl = scaleY(sl);
            const yTp = scaleY(tp);
            const yEntry = scaleY(entry);
            const yLive = scaleY(live);

            const stepX = (width - 70) / (n - 1);
            const startX = 25;

            // Çizgi noktalarını ve alan doldurma yolunu oluştur
            let pathD = '';
            let areaD = '';
            const points = [];

            prices.forEach((p, i) => {
                const x = startX + (i * stepX);
                const y = scaleY(p);
                points.push({ x, y });
                if (i === 0) {
                    pathD += `M ${x.toFixed(1)} ${y.toFixed(1)}`;
                    areaD += `M ${x.toFixed(1)} ${y.toFixed(1)}`;
                } else {
                    pathD += ` L ${x.toFixed(1)} ${y.toFixed(1)}`;
                    areaD += ` L ${x.toFixed(1)} ${y.toFixed(1)}`;
                }
            });

            const lastPt = points[points.length - 1];
            const bottomY = height - pad;
            areaD += ` L ${lastPt.x.toFixed(1)} ${bottomY} L ${points[0].x.toFixed(1)} ${bottomY} Z`;

            // Çizgi rengi: Long ise gök mavisi, Short ise parlak turuncu
            const lineColor = isLong ? '#38bdf8' : '#fb923c';
            const gradId = `grad_${symbol}_${Math.floor(Math.random() * 10000)}`;

            return `
                <svg class="chart-svg" viewBox="0 0 ${width} ${height}">
                    <defs>
                        <linearGradient id="${gradId}" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stop-color="${lineColor}" stop-opacity="0.32"/>
                            <stop offset="100%" stop-color="${lineColor}" stop-opacity="0.02"/>
                        </linearGradient>
                    </defs>

                    <!-- Background Grid -->
                    <line x1="0" y1="${height/2}" x2="${width}" y2="${height/2}" stroke="#1f2738" stroke-dasharray="3,3" />

                    <!-- 🟢 Yeşil Take Profit (Hedef) Çizgisi -->
                    <line x1="0" y1="${yTp}" x2="${width}" y2="${yTp}" stroke="#10b981" stroke-width="1.5" stroke-dasharray="4,3" />
                    <text x="${width - 5}" y="${yTp > 15 ? yTp - 3 : yTp + 10}" fill="#10b981" font-size="9" font-family="JetBrains Mono" font-weight="700" text-anchor="end">🎯 TP: $${fmtP(tp)}</text>

                    <!-- 🔴 Kırmızı Stop Loss (Zarar Kes) Çizgisi -->
                    <line x1="0" y1="${ySl}" x2="${width}" y2="${ySl}" stroke="#ef4444" stroke-width="1.5" stroke-dasharray="4,3" />
                    <text x="${width - 5}" y="${ySl > 15 ? ySl - 3 : ySl + 10}" fill="#ef4444" font-size="9" font-family="JetBrains Mono" font-weight="700" text-anchor="end">🛑 SL: $${fmtP(sl)}</text>

                    <!-- ⚪ Beyaz Giriş Çizgisi -->
                    <line x1="0" y1="${yEntry}" x2="${width}" y2="${yEntry}" stroke="#94a3b8" stroke-width="1" stroke-dasharray="2,2" />
                    <text x="5" y="${yEntry > 15 ? yEntry - 3 : yEntry + 10}" fill="#94a3b8" font-size="9" font-family="JetBrains Mono">💰 Giriş: $${fmtP(entry)}</text>

                    <!-- Alan Doldurma Gradient -->
                    <path d="${areaD}" fill="url(#${gradId})" />

                    <!-- 📈 Ana Fiyat Çizgisi (Smooth Line Chart) -->
                    <path d="${pathD}" fill="none" stroke="${lineColor}" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round" />

                    <!-- 🔵 Canlı Fiyat İşaretçisi (Mavi Parlayan Pin) -->
                    <line x1="0" y1="${yLive}" x2="${lastPt.x}" y2="${yLive}" stroke="${lineColor}" stroke-width="1" stroke-dasharray="2,2" opacity="0.3" />
                    <circle cx="${lastPt.x}" cy="${lastPt.y}" r="4" fill="${lineColor}" />
                    <circle cx="${lastPt.x}" cy="${lastPt.y}" r="8" fill="none" stroke="${lineColor}" opacity="0.5">
                        <animate attributeName="r" values="5;10;5" dur="1.8s" repeatCount="indefinite"/>
                        <animate attributeName="opacity" values="0.6;0.1;0.6" dur="1.8s" repeatCount="indefinite"/>
                    </circle>
                    <text x="${width - 10}" y="${lastPt.y + 3}" fill="${lineColor}" font-size="10" font-family="JetBrains Mono" font-weight="700" text-anchor="end">📍 $${fmtP(live)}</text>
                </svg>
            `;
        }

        function renderAll(data) {
            if (!data) return;

            // 1. Topbar
            const wsBadge = document.getElementById('wsBadge');
            if (wsBadge) {
                if (data.ws_connected) {
                    wsBadge.innerText = '⚡ WSS CANLI';
                    wsBadge.style.color = '#38bdf8';
                    wsBadge.style.background = 'rgba(56,189,248,0.15)';
                } else {
                    wsBadge.innerText = '● WSS HAZIR';
                    wsBadge.style.color = '#8492a6';
                    wsBadge.style.background = 'rgba(132,146,166,0.15)';
                }
            }

            const btc = data.btc_regime || {};
            if (btc.status) {
                const btcEl = document.getElementById('topBtc');
                const btcTxt = btc.status + ' ($' + (btc.btc_price ? Number(btc.btc_price).toLocaleString() : '0') + ')';
                if (btcEl && btcEl.innerText !== btcTxt) btcEl.innerText = btcTxt;
                if (btcEl) btcEl.style.color = btc.status === 'BULLISH' ? 'var(--green)' : (btc.status === 'DUMP_ALERT' ? 'var(--red)' : 'var(--yellow)');
            }

            if (data.total_unrealized_pnl !== undefined) {
                const unPnl = Number(data.total_unrealized_pnl).toFixed(1);
                const unPnlEl = document.getElementById('topUnrealized');
                const unTxt = (unPnl >= 0 ? '+' : '') + unPnl + '%';
                if (unPnlEl && unPnlEl.innerText !== unTxt) {
                    unPnlEl.innerText = unTxt;
                    unPnlEl.className = 'val ' + (unPnl >= 0 ? 'pnl-pos' : 'pnl-neg');
                }
            }

            const stats = data.stats || {};
            // Kasa Kalkanı Kotası
            const shieldEl = document.getElementById('topShieldQuota');
            const maxTrades = data.max_concurrent_trades || 4;
            const currentTrades = (data.active_positions || []).length;
            if (shieldEl) {
                shieldEl.innerText = `${currentTrades}/${maxTrades} Pozisyon`;
                shieldEl.style.color = currentTrades >= maxTrades ? 'var(--red)' : (currentTrades >= 2 ? 'var(--yellow)' : 'var(--green)');
            }

            // Fon Kasası ($)
            const equityEl = document.getElementById('topEquity');
            if (equityEl && stats.portfolio_balance !== undefined) {
                equityEl.innerText = '$' + Number(stats.portfolio_balance).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
            }

            // Net Kasa Kârı ($ ve %)
            if (stats.net_dollar_gain !== undefined) {
                const dollarVal = Number(stats.net_dollar_gain);
                const dollarSign = dollarVal >= 0 ? '+$' : '-$';
                const totPnl = stats.total_pnl_pct !== undefined ? Number(stats.total_pnl_pct).toFixed(1) : '0';
                const realEl = document.getElementById('topRealized');
                const totTxt = `${dollarSign}${Math.abs(dollarVal).toFixed(2)} (${totPnl >= 0 ? '+' : ''}${totPnl}%)`;
                if (realEl && realEl.innerText !== totTxt) realEl.innerText = totTxt;
                if (realEl) realEl.style.color = dollarVal >= 0 ? 'var(--green)' : 'var(--red)';
            }

            // Ödenen Toplam Komisyon
            const feesEl = document.getElementById('topFees');
            if (feesEl) {
                const fees = Number(stats.total_fee_pct || 0).toFixed(1);
                feesEl.innerText = '-%' + fees;
            }

            // Win Rate
            const winEl = document.getElementById('topWinRate');
            if (winEl) {
                winEl.innerText = '%' + Number(stats.win_rate || 0).toFixed(1);
            }

            // Kâr Faktörü
            const pfEl = document.getElementById('topProfitFactor');
            if (pfEl) {
                pfEl.innerText = Number(stats.profit_factor || 0).toFixed(2);
            }

            // 2. Sol Sütun: İki Kısımlı Aktif Kartlar & Çizgi Grafiği (Kârdakiler vs Zarardakiler)
            const activeList = data.active_positions;
            if (Array.isArray(activeList)) {
                const totalCount = activeList.length;
                const activeCountEl = document.getElementById('activeCount');
                if (activeCountEl) activeCountEl.innerText = totalCount + ' İşlem';
                const activeBtnEl = document.getElementById('activeCountBtn');
                if (activeBtnEl) activeBtnEl.innerText = totalCount;
                const totalEl = document.getElementById('totalActiveCount');
                if (totalEl) totalEl.innerText = totalCount;

                const profitListEl = document.getElementById('profitList');
                const lossListEl = document.getElementById('lossList');

                if (totalCount === 0) {
                    const emptyMsg = '<div style="text-align: center; color: var(--text-muted); padding: 30px 10px; font-size: 11px;">Aktif scalp pozisyonu aranıyor...</div>';
                    if (profitListEl) profitListEl.innerHTML = emptyMsg;
                    if (lossListEl) lossListEl.innerHTML = emptyMsg;
                    prevProfitHtml = '';
                    prevLossHtml = '';
                    const grEl = document.getElementById('greenActiveCount');
                    const rdEl = document.getElementById('redActiveCount');
                    const pColEl = document.getElementById('profitColCount');
                    const lColEl = document.getElementById('lossColCount');
                    if (grEl) grEl.innerText = '0';
                    if (rdEl) rdEl.innerText = '0';
                    if (pColEl) pColEl.innerText = '0';
                    if (lColEl) lColEl.innerText = '0';
                } else {
                    // Pozisyonların net ve brüt PnL ve mesafe hesaplamaları
                    const processed = activeList.map(pos => {
                        const isLong = pos.direction === 'LONG';
                        const entry = Number(pos.actual_entry_price || pos.entry_min);
                        const live = Number(pos.live_price || entry);
                        const sl = Number(pos.stop_loss);
                        const tp = Number(pos.take_profit_1 || pos.take_profit_2);
                        const lev = Number(pos.leverage || 10);

                        const rawDiff = isLong ? (live - entry) / entry : (entry - live) / entry;
                        const grossPnlPct = rawDiff * lev * 100;
                        const feePct = (pos.fee_pct !== undefined && pos.fee_pct !== 0.0) ? Number(pos.fee_pct) : (0.10 * lev);
                        const netPnlPct = grossPnlPct - feePct;
                        const isProfit = netPnlPct >= 0;

                        const distTp = isLong ? ((tp - live) / live) * 100 : ((live - tp) / live) * 100;
                        const distSl = isLong ? ((live - sl) / live) * 100 : ((sl - live) / live) * 100;

                        return {
                            ...pos,
                            isLong, entry, live, sl, tp, lev,
                            grossPnlPct, feePct, netPnlPct, isProfit, distTp, distSl
                        };
                    });

                    // 1. KÂRDAKİ POZİSYONLAR: En yüksek net kârdan en aza doğru sıralı
                    const profitPositions = processed
                        .filter(p => p.isProfit)
                        .sort((a, b) => b.netPnlPct - a.netPnlPct);

                    // 2. ZARARDAKİ POZİSYONLAR: En çok net zarardan en aza doğru sıralı
                    const lossPositions = processed
                        .filter(p => !p.isProfit)
                        .sort((a, b) => a.netPnlPct - b.netPnlPct);

                    const grEl = document.getElementById('greenActiveCount');
                    const rdEl = document.getElementById('redActiveCount');
                    const pColEl = document.getElementById('profitColCount');
                    const lColEl = document.getElementById('lossColCount');
                    if (grEl) grEl.innerText = profitPositions.length;
                    if (rdEl) rdEl.innerText = lossPositions.length;
                    if (pColEl) pColEl.innerText = profitPositions.length;
                    if (lColEl) lColEl.innerText = lossPositions.length;

                    function renderCardHtml(pos) {
                        const lineSvg = renderMiniLineChart(pos.recent_candles || [], pos.entry, pos.live, pos.sl, pos.tp, pos.isLong, pos.symbol);
                        const elapsed = pos.elapsed_str || '1 dk';

                        let protectionBadge = '';
                        if (pos.ladder_name) {
                            protectionBadge = `<span class="tag" style="background:rgba(245,158,11,0.22); color:#f59e0b; font-weight:700;">${pos.ladder_name}</span>`;
                        } else if (pos.ladder_step > 0) {
                            protectionBadge = `<span class="tag" style="background:rgba(245,158,11,0.22); color:#f59e0b; font-weight:700;">🪜 Basamak ${pos.ladder_step}</span>`;
                        } else if (pos.status === 'ACTIVE_BE') {
                            protectionBadge = '<span class="tag" style="background:rgba(56,189,248,0.2); color:#38bdf8; font-weight:700;">🛡️ BE+</span>';
                        } else if (pos.trailing_stop && Number(pos.trailing_stop) > 0) {
                            protectionBadge = '<span class="tag" style="background:rgba(245,158,11,0.2); color:#f59e0b; font-weight:700;">⚡ Dinamik Kanal</span>';
                        }

                        return `
                            <div class="pos-card" id="card-${pos.symbol}">
                                <div class="card-header">
                                    <div class="card-title">
                                        <span>${pos.symbol}</span>
                                        <span class="tag ${pos.isLong ? 'tag-long' : 'tag-short'}">${pos.direction}</span>
                                        <span class="tag tag-lev">${pos.lev}x</span>
                                        ${protectionBadge}
                                    </div>
                                    <div style="display: flex; align-items: center; gap: 8px;">
                                        <span class="card-elapsed">⏱️ ${elapsed}</span>
                                        <div style="text-align: right;">
                                            <div class="card-pnl ${pos.isProfit ? 'pnl-pos' : 'pnl-neg'}">
                                                ${pos.isProfit ? '+' : ''}${pos.netPnlPct.toFixed(2)}% Net
                                            </div>
                                            <div style="font-size: 8.5px; color: var(--text-muted); font-family: 'JetBrains Mono', monospace;">
                                                Brüt: ${(pos.grossPnlPct >= 0 ? '+' : '') + pos.grossPnlPct.toFixed(2)}% | Kom: -${pos.feePct.toFixed(2)}%
                                            </div>
                                        </div>
                                    </div>
                                </div>

                                <!-- Canlı Fiyat Çizgi Grafiği -->
                                <div class="mini-chart-box">
                                    ${lineSvg}
                                </div>

                                <!-- Mesafe ve Kasa Marjin Bilgileri -->
                                <div class="proximity-row">
                                    <span class="prox-sl">🛑 SL: %${pos.distSl.toFixed(2)}</span>
                                    <span style="color: var(--text-muted); font-size: 10px; font-family: 'JetBrains Mono';">💵 Marjin: $${pos.allocated_margin_usdt || 200}</span>
                                    <span class="prox-tp">🎯 TP: %${pos.distTp.toFixed(2)}</span>
                                </div>
                            </div>
                        `;
                    }

                    // Sol Sütun (KÂR): En yüksek kârdan en aza doğru
                    let profitHtml = '';
                    if (profitPositions.length === 0) {
                        profitHtml = '<div style="color: var(--text-muted); font-size: 11px; padding: 25px 10px; text-align: center;">Şu an kârda pozisyon yok.</div>';
                    } else {
                        profitPositions.forEach(p => { profitHtml += renderCardHtml(p); });
                    }
                    if (profitListEl && profitHtml !== prevProfitHtml) {
                        profitListEl.innerHTML = profitHtml;
                        prevProfitHtml = profitHtml;
                    }

                    // Sağ Sütun (ZARAR): En çok zarardan en aza doğru
                    let lossHtml = '';
                    if (lossPositions.length === 0) {
                        lossHtml = '<div style="color: var(--green); font-size: 11px; padding: 25px 10px; text-align: center; font-weight: 600;">✨ Harika! Zararda pozisyon yok.</div>';
                    } else {
                        lossPositions.forEach(p => { lossHtml += renderCardHtml(p); });
                    }
                    if (lossListEl && lossHtml !== prevLossHtml) {
                        lossListEl.innerHTML = lossHtml;
                        prevLossHtml = lossHtml;
                    }
                }
            }

            // 3. Sağ Üst: 📡 15M Tarama & Saatlik Kontrol Sıklığı Günlüğü
            const logs = data.scanner_logs;
            if (Array.isArray(logs) && logs.length > 0) {
                const logList = document.getElementById('logList');
                let logHtml = '';
                logs.forEach(l => {
                    const isAppr = l.status === 'APPROVED';
                    let reasonTxt = l.reason || '';
                    if (reasonTxt.indexOf('[Son 1 Saatte') !== -1) {
                        const parts = reasonTxt.split('[Son 1 Saatte');
                        const prefix = parts[0];
                        const testPart = parts[1].replace(']', '').trim();
                        reasonTxt = prefix + '<br><span style="color:#38bdf8; font-weight:600; background:rgba(56,189,248,0.12); padding:1px 6px; border-radius:3px; display:inline-block; margin-top:2px;">⏱️ Bu Saatte ' + testPart + '</span>';
                    }
                    logHtml += `
                        <div class="log-item ${isAppr ? 'approved' : 'rejected'}">
                            <div class="log-top">
                                <span class="log-sym">${l.symbol}</span>
                                <span class="${isAppr ? 'badge-appr' : 'badge-rej'}">${isAppr ? '✅ FIRSAT BULUNDU' : '❌ ELENDİ'}</span>
                                <span class="log-time">${l.time}</span>
                            </div>
                            <div class="log-reason">${reasonTxt} ${l.details ? `(${l.details})` : ''}</div>
                        </div>
                    `;
                });
                if (logHtml !== prevLogsHtml) {
                    logList.innerHTML = logHtml;
                    prevLogsHtml = logHtml;
                }
            }

            // 3.5 Sağ Alt: 🏛️ Ajanlar Yatırım Komitesi Tartışma Odası
            const debates = data.committee_debates;
            const debateList = document.getElementById('debateList');
            if (debateList) {
                if (!Array.isArray(debates) || debates.length === 0) {
                    const emptyMsg = '<div style="text-align: center; color: var(--text-muted); padding: 25px; font-size: 11px;">🏛️ Ajanlar parite taramasında tartışmak üzere hazır bekliyor...</div>';
                    if (prevDebatesHtml !== emptyMsg) {
                        debateList.innerHTML = emptyMsg;
                        prevDebatesHtml = emptyMsg;
                    }
                } else {
                    let dHtml = '';
                    debates.forEach(d => {
                        const isAppr = d.consensus_verdict === 'APPROVED';
                        const score = Number(d.consensus_score || 0).toFixed(1);
                        const dataObj = d.debate_data || {};
                        const dialogue = dataObj.debate_dialogue || [];

                        let bubblesHtml = '';
                        dialogue.forEach(b => {
                            let roleClass = 'bubble-bull';
                            let roleColor = '#22c55e';
                            if (b.role === 'BEAR') { roleClass = 'bubble-bear'; roleColor = '#ef4444'; }
                            else if (b.role === 'MACRO') { roleClass = 'bubble-macro'; roleColor = '#38bdf8'; }
                            else if (b.role === 'CHIEF') { roleClass = 'bubble-chief'; roleColor = '#f59e0b'; }

                            bubblesHtml += `
                                <div class="dialogue-bubble ${roleClass}">
                                    <div class="speaker-title" style="color: ${roleColor};">
                                        <span>${b.avatar || '💬'}</span>
                                        <span>${b.agent_name || b.role}</span>
                                    </div>
                                    <div>${b.argument || ''}</div>
                                </div>
                            `;
                        });

                        dHtml += `
                            <div class="debate-card">
                                <div class="debate-header">
                                    <div class="debate-sym">
                                        <span>${d.symbol}</span>
                                        <span class="tag ${d.direction === 'LONG' ? 'tag-long' : 'tag-short'}">${d.direction}</span>
                                        <span style="font-size: 9.5px; color: var(--text-muted); font-family: 'JetBrains Mono';">${d.time_str || ''}</span>
                                    </div>
                                    <span class="debate-score ${isAppr ? 'debate-score-approved' : 'debate-score-rejected'}">
                                        ${isAppr ? '✅ ONAYLANDI' : '🚫 VETO EDİLDİ'} (${score}/10)
                                    </span>
                                </div>
                                <div style="display: flex; flex-direction: column; gap: 6px;">
                                    ${bubblesHtml}
                                </div>
                            </div>
                        `;
                    });

                    if (dHtml !== prevDebatesHtml) {
                        debateList.innerHTML = dHtml;
                        prevDebatesHtml = dHtml;
                    }
                }
            }

            // 3.6 Sağ Alt: 🧠 AI Hafıza & Çıkarılan Dersler (Tauric Reflections)
            const reflections = data.trade_reflections;
            const reflectList = document.getElementById('reflectionsList');
            if (reflectList && Array.isArray(reflections)) {
                if (reflections.length === 0) {
                    const emptyMsg = '<div style="text-align: center; color: var(--text-muted); padding: 25px; font-size: 11px;">🧠 Henüz kayıtlı geçmiş işlem dersi yok. Kapanan her işlemde sistem buraya somut dersler kaydeder.</div>';
                    if (prevReflectHtml !== emptyMsg) {
                        reflectList.innerHTML = emptyMsg;
                        prevReflectHtml = emptyMsg;
                    }
                } else {
                    let rHtml = '';
                    reflections.forEach(r => {
                        const pnl = Number(r.pnl_pct || 0);
                        const isWin = pnl >= 0;
                        const pnlSign = isWin ? '+' : '';
                        let badgeColor = isWin ? '#22c55e' : '#ef4444';
                        let badgeBg = isWin ? 'rgba(34, 197, 94, 0.15)' : 'rgba(239, 68, 68, 0.15)';
                        let statusIcon = '🏁';
                        if (r.status === 'HIT_TP') statusIcon = '🎯';
                        else if (r.status && r.status.includes('LADDER')) statusIcon = '🪜';
                        else if (r.status === 'CLOSED_BE') statusIcon = '🛡️';
                        else if (r.status === 'TIMEOUT_EXIT') statusIcon = '⏱️';
                        else if (r.status === 'HIT_SL') statusIcon = '🛑';

                        rHtml += `
                            <div class="reflection-card" style="border-left: 3px solid ${badgeColor};">
                                <div class="reflection-top">
                                    <div style="display: flex; align-items: center; gap: 6px;">
                                        <span style="font-weight: 700; color: #fff;">${r.symbol}</span>
                                        <span class="tag ${r.direction === 'LONG' ? 'tag-long' : 'tag-short'}">${r.direction}</span>
                                        <span style="font-size: 9.5px; color: var(--text-muted); font-family: 'JetBrains Mono';">${r.time_str || ''}</span>
                                    </div>
                                    <div style="display: flex; align-items: center; gap: 5px;">
                                        <span style="font-size: 10px; font-weight: 700; padding: 2px 6px; border-radius: 4px; background: ${badgeBg}; color: ${badgeColor};">
                                            ${statusIcon} ${r.status} (${pnlSign}${pnl.toFixed(2)}%)
                                        </span>
                                    </div>
                                </div>
                                <div class="reflection-lesson">
                                    ${r.lesson}
                                </div>
                            </div>
                        `;
                    });
                    if (rHtml !== prevReflectHtml) {
                        reflectList.innerHTML = rHtml;
                        prevReflectHtml = rHtml;
                    }
                }
            }

            // 3.7 Sağ Alt: 🧬 Otonom Öğrenme & Kalibrasyon (Self-Tuning Engine)
            const tuning = data.tuning_info;
            const tuningList = document.getElementById('tuningList');
            if (tuningList && tuning) {
                const hScore = tuning.health_score || 75;
                const pFactor = tuning.profit_factor || 1.0;
                const winR = tuning.win_rate || 50;
                const expVal = Number(tuning.expectancy || 0).toFixed(2);
                const expSign = expVal >= 0 ? '+' : '';
                const p = tuning.tuned_params || {};

                let tHtml = `
                    <div class="reflection-card" style="border-left: 3px solid #10b981; background: rgba(16, 185, 129, 0.04);">
                        <div class="reflection-top">
                            <span style="font-weight: 700; color: #10b981; font-size: 12px;">🧬 Otonom Öğrenme Motoru</span>
                            <span style="font-size: 10px; background: rgba(16, 185, 129, 0.15); color: #10b981; padding: 2px 7px; border-radius: 4px; font-weight: 700;">
                                Sağlık Skoru: ${hScore}/100
                            </span>
                        </div>
                        <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 6px; margin-top: 4px; font-size: 10px; text-align: center;">
                            <div style="background: rgba(255,255,255,0.03); padding: 4px; border-radius: 4px;">
                                <div style="color: var(--text-muted);">Kazanma Oranı</div>
                                <div style="font-weight: 700; color: ${winR >= 50 ? '#10b981' : '#ef4444'}; font-size: 11px;">%${winR}</div>
                            </div>
                            <div style="background: rgba(255,255,255,0.03); padding: 4px; border-radius: 4px;">
                                <div style="color: var(--text-muted);">Beklenti (E)</div>
                                <div style="font-weight: 700; color: ${expVal >= 0 ? '#10b981' : '#ef4444'}; font-size: 11px;">${expSign}${expVal}%</div>
                            </div>
                            <div style="background: rgba(255,255,255,0.03); padding: 4px; border-radius: 4px;">
                                <div style="color: var(--text-muted);">Kâr Faktörü</div>
                                <div style="font-weight: 700; color: ${pFactor >= 1.0 ? '#10b981' : '#ef4444'}; font-size: 11px;">${pFactor}</div>
                            </div>
                        </div>
                        <div style="font-size: 10px; color: #cbd5e1; margin-top: 6px; line-height: 1.4; border-top: 1px dashed rgba(255,255,255,0.1); padding-top: 5px;">
                            <strong>⚙️ Aktif Kalibre Parametreler:</strong><br>
                            • SMC Kalite Barajı: <span style="color:#38bdf8; font-weight:700;">${p.min_confluence_score || 76}/100</span><br>
                            • Fitil Korumalı Stop Mesafesi: <span style="color:#f59e0b; font-weight:700;">%${p.min_scalp_sl_pct || 0.95} - %${p.max_scalp_sl_pct || 1.35}</span><br>
                            • BTC Dead Chop Eşiği: <span style="color:#ef4444; font-weight:700;">4s &lt; %${p.btc_chop_min_range_4h_pct || 0.80}</span><br>
                            • Değiştirilemez Kasa Kalkanı: <span style="color:#10b981; font-weight:700;">Maks %2.0 Risk (Kilitli 🔒)</span>
                        </div>
                        <div style="font-size: 9.5px; color: #94a3b8; margin-top: 4px;">
                            <strong>💡 Son Öğrenme Raporu:</strong> ${tuning.summary || 'Parametreler optimize edildi.'}
                        </div>
                        <button onclick="runCalibrationNow()" class="btn-clear" style="border-color:#10b981; color:#10b981; padding: 5px 10px; margin-top: 6px; font-weight: 700; width: 100%;">
                            🧬 Şimdi Analiz Et ve Optimize Et
                        </button>
                    </div>
                `;

                if (tHtml !== prevTuningHtml) {
                    tuningList.innerHTML = tHtml;
                    prevTuningHtml = tHtml;
                }
            }

            // 4. Sağ Alt: 📰 Canlı Haber & Sentiment Masası
            const news = data.news_feed;
            if (Array.isArray(news) && news.length > 0) {
                const newsList = document.getElementById('newsList');
                let newsHtml = '';
                news.forEach(n => {
                    let sentClass = 'sent-neut';
                    if (n.sentiment === 'BULLISH') sentClass = 'sent-bull';
                    if (n.sentiment === 'BEARISH') sentClass = 'sent-bear';

                    newsHtml += `
                        <div class="news-item">
                            <div class="news-meta">
                                <span>${n.source || 'RSS'}</span>
                                <span class="${sentClass}">${n.sentiment}</span>
                                <span>${n.time}</span>
                            </div>
                            <div class="news-title">${n.title}</div>
                        </div>
                    `;
                });
                if (newsHtml !== prevNewsHtml) {
                    newsList.innerHTML = newsHtml;
                    prevNewsHtml = newsHtml;
                }
            }

            // 5. Alt Kısım: PnL Geçmiş Tablosu
            const history = data.trade_history;
            if (Array.isArray(history) && history.length > 0) {
                document.getElementById('historyCount').innerText = history.length + ' İşlem';
                const historyBody = document.getElementById('historyBody');
                let histHtml = '';
                history.forEach(tr => {
                    const isLong = tr.direction === 'LONG';
                    const pnl = Number(tr.simulated_pnl_pct || 0);
                    const pnlSign = pnl > 0 ? '+' : '';
                    const pnlClass = pnl > 0 ? 'pnl-pos' : (pnl < 0 ? 'pnl-neg' : '');

                    const feePct = tr.fee_pct ? Number(tr.fee_pct) : (0.10 * Number(tr.leverage || 10));
                    const grossPct = tr.gross_pnl_pct !== undefined && tr.gross_pnl_pct !== 0.0 ? Number(tr.gross_pnl_pct) : (pnl + feePct);
                    const grossSign = grossPct > 0 ? '+' : '';

                    let resBadge = tr.status;
                    if (tr.status === 'HIT_TP' || tr.status === 'HIT_TP2') resBadge = '<span style="color:var(--green); font-weight:700;">🎯 Vur-Kaç Kâr</span>';
                    else if (tr.status && (tr.status.startsWith('LADDER_STEP_') || tr.status === 'LADDER_PROFIT_EXIT')) resBadge = `<span style="color:#f59e0b; font-weight:700;">${tr.ladder_name || '🪜 Merdiven Kârı'}</span>`;
                    else if (tr.status === 'TRAILING_STOP_EXIT') resBadge = '<span style="color:#f59e0b; font-weight:700;">⚡ Dinamik Kanal</span>';
                    else if (tr.status === 'CLOSED_BE') resBadge = '<span style="color:var(--cyan); font-weight:700;">🛡️ BE+ (Komisyon Korumalı)</span>';
                    else if (tr.status === 'TIMEOUT_EXIT') resBadge = '<span style="color:var(--yellow); font-weight:700;">⏱️ 45dk Çıkış</span>';
                    else if (tr.status === 'MANUAL_CLOSE') resBadge = '<span style="color:#a855f7; font-weight:700;">🛑 El İle Kapatıldı</span>';
                    else if (tr.status === 'HIT_SL') resBadge = '<span style="color:var(--red); font-weight:700;">🛑 Stop Loss</span>';

                    histHtml += `
                        <tr>
                            <td style="color: var(--text-muted); font-size: 10px;">${tr.closed_at || tr.created_at}</td>
                            <td><strong>${tr.symbol}</strong></td>
                            <td><span class="tag ${isLong ? 'tag-long' : 'tag-short'}">${tr.direction}</span></td>
                            <td><span class="tag tag-lev">${tr.leverage}x</span></td>
                            <td class="mono">$${tr.actual_entry_price || tr.entry_min}</td>
                            <td class="mono">$${tr.exit_price || '-'}</td>
                            <td>${resBadge}</td>
                            <td>
                                <div class="mono ${pnlClass}" style="font-size: 12px; font-weight: 700;">
                                    ${pnlSign}${pnl.toFixed(2)}% Net
                                </div>
                                <div style="font-size: 8.5px; color: var(--text-muted); font-family: 'JetBrains Mono', monospace;">
                                    Brüt: ${grossSign}${grossPct.toFixed(2)}% | Kom: -${feePct.toFixed(2)}%
                                </div>
                            </td>
                        </tr>
                    `;
                });
                if (histHtml !== prevHistHtml) {
                    historyBody.innerHTML = histHtml;
                    prevHistHtml = histHtml;
                }
            }
        }

        async function triggerScan() {
            const btn = document.querySelector('.btn-scan');
            btn.innerText = '⏳...';
            try {
                await fetch('/api/scan', { method: 'POST' });
                await fetchTerminal();
            } catch(e) {}
            btn.innerText = '⚡ Tara';
        }

        async function closeAllPositions() {
            if (!confirm("Tüm açık pozisyonları anlık piyasa fiyatından kapatmak istediğinize emin misiniz?")) return;
            const btn = document.querySelector('.btn-panic');
            if (btn) btn.innerText = '⏳ Kapatılıyor...';
            try {
                await fetch('/api/close-all-positions', { method: 'POST' });
                await fetchTerminal();
            } catch(e) {}
            if (btn) btn.innerText = '🚫 Tümünü Kapat';
        }

        async function clearTradeHistory() {
            if (!confirm("Tamamlanan işlem defterini ve kasa istatistiklerini temizlemek istediğinize emin misiniz? (Aktif işlemler korunur)")) return;
            const btn = document.querySelector('.btn-clear');
            if (btn) btn.innerText = '⏳...';
            try {
                await fetch('/api/clear-history', { method: 'POST' });
                prevHistHtml = '';
                const historyBody = document.getElementById('historyBody');
                if (historyBody) historyBody.innerHTML = '<tr><td colspan="8" style="text-align: center; color: var(--text-muted); padding: 20px;">Kapanan işlem kaydı yok.</td></tr>';
                const histCountEl = document.getElementById('historyCount');
                if (histCountEl) histCountEl.innerText = '0 İşlem';
                await fetchTerminal();
            } catch(e) {}
            if (btn) btn.innerText = '🗑️ Geçmişi Temizle';
        }

        async function runCalibrationNow() {
            const btn = document.querySelector('.btn-clear[onclick*="runCalibrationNow"]') || event?.target;
            if (btn) btn.innerText = '⏳ Analiz Ediliyor...';
            try {
                const res = await fetch('/api/tuning/calibrate', { method: 'POST' });
                const json = await res.json();
                const sumMsg = json.summary || 'Parametreler optimize edildi.';
                alert('🧬 Otonom Kalibrasyon Tamamlandı: ' + sumMsg);
                await fetchTerminal();
            } catch(e) {
                alert('Kalibrasyon hatası: ' + e);
            }
            if (btn) btn.innerText = '🧬 Şimdi Analiz Et ve Optimize Et';
        }

        // Başlangıç Sol Görünümü ve Canlı Polling
        switchLeftView(currentLeftView);
        fetchTerminal();
        setInterval(fetchTerminal, 2000);
    </script>
</body>
</html>
"""

@app.after_request
def add_no_cache_headers(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@app.route("/")
def index():
    return render_template_string(HTML_OFFICE_TEMPLATE)

@app.route("/charts/<path:filename>")
def serve_chart(filename):
    return send_from_directory(CHARTS_DIR, filename)

_terminal_cache = {
    "btc_regime": {"status": "NEUTRAL", "btc_price": 0, "summary": "Piyasa taranıyor..."},
    "stats": {},
    "total_unrealized_pnl": 0.0,
    "active_positions": [],
    "scanner_logs": [],
    "news_feed": [],
    "trade_history": [],
    "committee_debates": [],
    "trade_reflections": [],
    "tuning_info": {}
}

# İlk açılışta ekranın boş kalmaması veya gidip gelmemesi için DB'den anında besle
try:
    from core.database import (
        get_scanner_logs_db, get_news_feed_db, get_performance_stats,
        get_all_signals, get_active_and_pending_signals, get_latest_debates_db,
        get_recent_reflections_db
    )
    from core.self_tuning_engine import SelfTuningEngine
    _terminal_cache["stats"] = get_performance_stats() or {}
    _terminal_cache["scanner_logs"] = get_scanner_logs_db(limit=40) or []
    _terminal_cache["news_feed"] = get_news_feed_db(limit=25) or []
    _all_init = get_all_signals(limit=40) or []
    _terminal_cache["trade_history"] = [s for s in _all_init if s.get("status") not in ("ACTIVE", "PENDING_ENTRY", "ACTIVE_BE", "ACTIVE_LADDER")]
    _terminal_cache["active_positions"] = get_active_and_pending_signals() or []
    _terminal_cache["committee_debates"] = get_latest_debates_db(limit=8) or []
    _terminal_cache["trade_reflections"] = get_recent_reflections_db(limit=15) or []
    _terminal_cache["tuning_info"] = SelfTuningEngine.run_calibration_cycle(min_trades_required=5) or {}
except Exception:
    pass
_cache_lock = threading.Lock()
_updater_started = False

def update_terminal_cache_loop():
    """Arka planda piyasa ve pozisyon verilerini kesintisiz ve hatasız günceller (Sıfır Donma, Sıfır Gidip Gelme)."""
    global _terminal_cache
    cached_tickers = {}
    cached_klines = {}

    import time
    while True:
        try:
            # 1. Binance Tickers
            try:
                fresh_tickers = client.get_24hr_tickers()
                if fresh_tickers:
                    cached_tickers = fresh_tickers
            except Exception:
                pass

            # 2. BTC Rejimi
            try:
                btc_regime = client.get_btc_regime()
            except Exception:
                with _cache_lock:
                    btc_regime = _terminal_cache.get("btc_regime", {"status": "NEUTRAL", "btc_price": 0})

            # 3. İstatistikler & Veritabanı
            try:
                stats = get_performance_stats()
                active_signals = get_active_and_pending_signals()
                all_sigs = get_all_signals(limit=40)
                history = [s for s in all_sigs if s.get("status") not in ("ACTIVE", "PENDING_ENTRY", "ACTIVE_BE", "ACTIVE_LADDER")]
                scanner_logs = get_scanner_logs()
                news_feed = get_live_news_feed()
                if not news_feed:
                    news_feed = news_agent.fetch_latest_market_news()
                debates = get_latest_debates_db(limit=8)
                reflections = get_recent_reflections_db(limit=15)
            except Exception:
                with _cache_lock:
                    stats = _terminal_cache.get("stats", {})
                    active_signals = []
                    history = _terminal_cache.get("trade_history", [])
                    scanner_logs = _terminal_cache.get("scanner_logs", [])
                    news_feed = _terminal_cache.get("news_feed", [])
                    debates = _terminal_cache.get("committee_debates", [])
                    reflections = _terminal_cache.get("trade_reflections", [])

            # 4. Aktif Pozisyonlar ve Çizgi Fiyatları
            active_positions = []
            total_unrealized_pnl = 0.0

            from core.binance_streamer import get_live_price, is_streamer_connected

            for sig in active_signals:
                symbol = sig["symbol"]
                ws_price = get_live_price(symbol)
                ticker = cached_tickers.get(symbol, {})
                entry_price = sig.get("actual_entry_price") or sig["entry_min"]
                live_price = ws_price if ws_price else ticker.get("lastPrice", entry_price)
                leverage = sig.get("leverage", 10)
                direction = sig["direction"]

                gross_pnl_pct = 0.0
                fee_pct = round(BINANCE_ROUNDTRIP_FEE_PCT * leverage, 2)
                net_pnl_pct = 0.0
                if entry_price > 0:
                    if direction == "LONG":
                        raw_diff = (live_price - entry_price) / entry_price
                    else:
                        raw_diff = (entry_price - live_price) / entry_price
                    gross_pnl_pct = round(raw_diff * leverage * 100, 2)
                    net_pnl_pct = round(gross_pnl_pct - fee_pct, 2)
                    total_unrealized_pnl += net_pnl_pct

                # Mum verisini çek (başarısız olursa son hafızadakini koru)
                try:
                    klines = client.get_klines(symbol, interval="15m", limit=16)
                    if klines:
                        cached_klines[symbol] = klines
                except Exception:
                    pass

                entered_str = sig.get("entered_at") or sig.get("created_at")
                elapsed_str = "1 dk"
                if entered_str:
                    try:
                        t_str = str(entered_str).replace('T', ' ').split('.')[0]
                        dt = datetime.strptime(t_str, "%Y-%m-%d %H:%M:%S")
                        diff_sec = max(0, int((datetime.now() - dt).total_seconds()))
                        mins = diff_sec // 60
                        secs = diff_sec % 60
                        if mins == 0:
                            elapsed_str = f"{secs} sn"
                        elif mins < 60:
                            elapsed_str = f"{mins} dk"
                        else:
                            elapsed_str = f"{mins // 60} sa {mins % 60} dk"
                    except Exception:
                        pass

                sig_dict = dict(sig)
                sig_dict["elapsed_str"] = elapsed_str
                sig_dict["live_price"] = live_price
                sig_dict["unrealized_pnl_pct"] = net_pnl_pct
                sig_dict["gross_pnl_pct"] = gross_pnl_pct
                sig_dict["fee_pct"] = fee_pct
                sig_dict["ladder_step"] = sig.get("ladder_step") or 0
                sig_dict["ladder_name"] = sig.get("ladder_name") or ""
                sig_dict["recent_candles"] = cached_klines.get(symbol, [])
                active_positions.append(sig_dict)

            # Atomik Olarak Önbelleği Güncelle
            with _cache_lock:
                _terminal_cache = {
                    "ws_connected": is_streamer_connected(),
                    "btc_regime": btc_regime,
                    "stats": stats,
                    "max_concurrent_trades": MAX_CONCURRENT_TRADES,
                    "total_unrealized_pnl": round(total_unrealized_pnl, 2),
                    "active_positions": active_positions,
                    "scanner_logs": scanner_logs if scanner_logs else _terminal_cache.get("scanner_logs", []),
                    "news_feed": news_feed if news_feed else _terminal_cache.get("news_feed", []),
                    "trade_history": history if history else _terminal_cache.get("trade_history", []),
                    "committee_debates": debates if debates else _terminal_cache.get("committee_debates", []),
                    "trade_reflections": reflections if reflections else _terminal_cache.get("trade_reflections", []),
                    "tuning_info": _terminal_cache.get("tuning_info", {})
                }

        except Exception:
            pass

        time.sleep(1.0)

@app.route("/api/data")
def api_data():
    with _cache_lock:
        return jsonify(_terminal_cache)

@app.route("/api/reflections")
def api_reflections():
    from core.database import get_recent_reflections_db
    return jsonify(get_recent_reflections_db(limit=30))

@app.route("/api/tuning", methods=["GET"])
def api_tuning():
    from core.self_tuning_engine import SelfTuningEngine
    return jsonify(SelfTuningEngine.run_calibration_cycle(min_trades_required=5))

@app.route("/api/tuning/calibrate", methods=["POST"])
def api_tuning_calibrate():
    global _terminal_cache
    from core.self_tuning_engine import SelfTuningEngine
    res = SelfTuningEngine.run_calibration_cycle(min_trades_required=5)
    with _cache_lock:
        _terminal_cache["tuning_info"] = res
    return jsonify(res)

@app.route("/api/scan", methods=["POST"])
def api_scan():
    global _orchestrator
    if _orchestrator:
        threading.Thread(target=_orchestrator.run_cycle, daemon=True).start()
        return jsonify({"status": "Scan started in background"})
    else:
        from main import TradingBotOrchestrator
        orch = TradingBotOrchestrator()
        threading.Thread(target=orch.run_cycle, daemon=True).start()
        return jsonify({"status": "Scan triggered"})

@app.route("/api/close-all-positions", methods=["POST"])
def api_close_all_positions():
    from core.database import close_all_active_signals_db, get_performance_stats, get_all_signals
    count = close_all_active_signals_db(client=client)
    with _cache_lock:
        _terminal_cache["active_positions"] = []
        _terminal_cache["total_unrealized_pnl"] = 0.0
        _terminal_cache["stats"] = get_performance_stats()
        _all_init = get_all_signals(limit=40) or []
        _terminal_cache["trade_history"] = [s for s in _all_init if s.get("status") not in ("ACTIVE", "PENDING_ENTRY", "ACTIVE_BE", "ACTIVE_LADDER")]
    return jsonify({"status": "closed", "count": count})

@app.route("/api/clear-history", methods=["POST"])
def api_clear_history():
    from core.database import clear_closed_trades_db, get_performance_stats
    clear_closed_trades_db()
    with _cache_lock:
        _terminal_cache["trade_history"] = []
        _terminal_cache["stats"] = get_performance_stats()
    return jsonify({"status": "cleared"})

import socket

def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0

def start_dashboard(orchestrator=None, port=5000, auto_open=True):
    global _orchestrator, _updater_started
    _orchestrator = orchestrator

    # Bulut ve Yerel Ortam Dinamik Port ve Host Desteği (Railway, Render, VPS uyumlu)
    port = int(os.environ.get("PORT", port))
    host = os.environ.get("HOST", "0.0.0.0")

    if not _updater_started:
        threading.Thread(target=update_terminal_cache_loop, daemon=True, name="CacheUpdater").start()
        _updater_started = True

    url = f"http://{'127.0.0.1' if host == '0.0.0.0' else host}:{port}"
    # Yerel ortamda port kullanımını denetle (Bulut ortamında kontrolü atla)
    if os.environ.get("RAILWAY_ENVIRONMENT") is None and os.environ.get("RENDER") is None and is_port_in_use(port):
        print(f"\n🌐 [Canlı Ofis Terminali Zaten Aktif]: {url}")
        if auto_open:
            try:
                webbrowser.open(url)
            except Exception:
                pass
        return None

    def run_app():
        import logging
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.ERROR)
        app.run(host=host, port=port, debug=False, use_reloader=False)

    server_thread = threading.Thread(target=run_app, daemon=True, name="DashboardServer")
    server_thread.start()
    print(f"\n🌐 [Canlı Ofis Terminali Hazır]: {url}")

    if auto_open:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    return server_thread

if __name__ == "__main__":
    print("🚀 [Başlatılıyor] Binance Futures AI Ticaret Ofisi...")
    from main import TradingBotOrchestrator
    orch = TradingBotOrchestrator()
    start_dashboard(orchestrator=orch, auto_open=False)

    # 7/24 Kesintisiz Arka Plan Döngüsünü Başlat
    threading.Thread(target=orch.run_forever, kwargs={"skip_dashboard": True}, daemon=True).start()

    print("Kapatmak için Ctrl+C tuşlarına basabilirsiniz.")
    try:
        while True:
            threading.Event().wait(1)
    except KeyboardInterrupt:
        print("\nTerminal kapatıldı.")
