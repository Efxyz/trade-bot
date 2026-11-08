"""
All-in-One Trading Office Dashboard for Binance Futures Trade Bot (v2.2.0)
Visualizes the active trading desk like a real office:
- Live Interactive Binance Futures Bitcoin Candlestick Chart (15m, 1h, 4h, 1D)
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
    <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
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
        .log-item.protected { border-left: 3px solid #38bdf8; background: rgba(56, 189, 248, 0.04); }

        .log-top { display: flex; justify-content: space-between; align-items: center; }
        .log-sym { font-weight: 700; font-family: 'JetBrains Mono', monospace; }
        .log-time { color: var(--text-muted); font-size: 10px; }
        .log-reason { font-size: 11px; color: #cbd5e1; line-height: 1.55; margin-top: 3px; }
        .log-reason strong { color: #f1f5f9; }
        .badge-appr { color: var(--green); font-weight: 700; }
        .badge-rej { color: #94a3b8; font-weight: 600; }
        .badge-prot { color: #38bdf8; font-weight: 700; background: rgba(56,189,248,0.12); padding: 1px 7px; border-radius: 4px; font-size: 10px; }

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

        /* ==================== 🎮 3D SİMS OFİS & PATRON EFE STİLLERİ ==================== */
        .office-3d-wrapper {
            position: relative;
            width: 100%;
            height: 100%;
            flex: 1;
            overflow: hidden;
            background: radial-gradient(circle at 50% 40%, #151d2c 0%, #080c14 100%);
            border-radius: 4px;
        }

        /* 3D Ofis Tam Ekran (Fullscreen) Modu (Mobil & Masaüstü) */
        .office-3d-wrapper.is-fullscreen {
            position: fixed !important;
            top: 0 !important;
            left: 0 !important;
            width: 100vw !important;
            height: 100vh !important;
            z-index: 999999 !important;
            border-radius: 0 !important;
            margin: 0 !important;
            padding: 0 !important;
            background: #090e18 !important;
        }

        #officeCanvasTarget {
            width: 100%;
            height: 100%;
            position: absolute;
            inset: 0;
            outline: none;
            touch-action: none;
        }

        .office-bubbles-overlay {
            position: absolute;
            inset: 0;
            pointer-events: none;
            z-index: 10;
            overflow: hidden;
        }

        /* Sims Tarzı Şeffaf & Dinamik Konuşma / Düşünce Baloncuğu (Cam Efekti) */
        .sims-bubble {
            position: absolute;
            transform: translate(-50%, -90%) scale(0.92);
            background: rgba(10, 16, 28, 0.62) !important;
            border: 1.5px solid rgba(255, 255, 255, 0.22) !important;
            border-radius: 12px;
            padding: 8px 12px;
            color: #f1f5f9;
            font-size: 11px;
            max-width: 220px;
            box-shadow: 0 8px 30px rgba(0, 0, 0, 0.5), 0 0 15px rgba(255, 255, 255, 0.06);
            backdrop-filter: blur(14px) !important;
            -webkit-backdrop-filter: blur(14px) !important;
            opacity: 0;
            pointer-events: none;
            transition: opacity 0.4s ease, transform 0.35s cubic-bezier(0.16, 1, 0.3, 1);
            cursor: pointer;
            line-height: 1.35;
            user-select: text;
        }

        /* Konuşma anında yumuşakça belirir */
        .sims-bubble.speaking {
            opacity: 1 !important;
            pointer-events: auto !important;
            transform: translate(-50%, -100%) scale(1) !important;
        }

        .sims-bubble::after {
            content: '';
            position: absolute;
            bottom: -7px;
            left: 50%;
            transform: translateX(-50%);
            border-width: 7px 6px 0 6px;
            border-style: solid;
            border-color: rgba(10, 16, 28, 0.75) transparent transparent transparent;
        }

        /* Karakterlere Özel Renk ve Parlama Efektleri (Cam Efektli Şeffaf Zeminler) */
        .sims-bubble.boss {
            border-color: rgba(245, 158, 11, 0.65) !important;
            box-shadow: 0 0 22px rgba(245, 158, 11, 0.3), 0 8px 25px rgba(0,0,0,0.6) !important;
            background: rgba(28, 20, 8, 0.68) !important;
        }
        .sims-bubble.boss::after {
            border-top-color: rgba(245, 158, 11, 0.75);
        }

        .sims-bubble.scanner {
            border-color: rgba(56, 189, 248, 0.65) !important;
            box-shadow: 0 0 20px rgba(56, 189, 248, 0.3) !important;
            background: rgba(8, 22, 38, 0.68) !important;
        }
        .sims-bubble.scanner::after {
            border-top-color: rgba(56, 189, 248, 0.75);
        }

        .sims-bubble.ta {
            border-color: rgba(168, 85, 247, 0.65) !important;
            box-shadow: 0 0 20px rgba(168, 85, 247, 0.3) !important;
            background: rgba(24, 10, 38, 0.68) !important;
        }
        .sims-bubble.ta::after {
            border-top-color: rgba(168, 85, 247, 0.75);
        }

        .sims-bubble.news {
            border-color: rgba(251, 146, 60, 0.65) !important;
            box-shadow: 0 0 20px rgba(251, 146, 60, 0.3) !important;
            background: rgba(32, 16, 8, 0.68) !important;
        }
        .sims-bubble.news::after {
            border-top-color: rgba(251, 146, 60, 0.75);
        }

        .sims-bubble.risk {
            border-color: rgba(239, 68, 68, 0.65) !important;
            box-shadow: 0 0 20px rgba(239, 68, 68, 0.3) !important;
            background: rgba(34, 8, 8, 0.68) !important;
        }
        .sims-bubble.risk::after {
            border-top-color: rgba(239, 68, 68, 0.75);
        }

        .sims-bubble.chief {
            border-color: rgba(16, 185, 129, 0.65) !important;
            box-shadow: 0 0 20px rgba(16, 185, 129, 0.3) !important;
            background: rgba(8, 30, 20, 0.68) !important;
        }
        .sims-bubble.chief::after {
            border-top-color: rgba(16, 185, 129, 0.75);
        }

        .sims-bubble-header {
            display: flex;
            align-items: center;
            gap: 5px;
            font-weight: 800;
            font-size: 10px;
            text-transform: uppercase;
            margin-bottom: 4px;
            letter-spacing: 0.5px;
        }
        .sims-bubble.boss .sims-bubble-header { color: #facc15; }
        .sims-bubble.scanner .sims-bubble-header { color: #38bdf8; }
        .sims-bubble.ta .sims-bubble-header { color: #c084fc; }
        .sims-bubble.news .sims-bubble-header { color: #fb923c; }
        .sims-bubble.risk .sims-bubble-header { color: #f87171; }
        .sims-bubble.chief .sims-bubble-header { color: #34d399; }

        .sims-bubble-body {
            font-size: 11px;
            color: #f1f5f9;
            font-family: 'Inter', sans-serif;
            font-weight: 500;
        }

        /* Bilgisayar Monitörü Üstündeki Canlı İşlem Baloncuğu */
        .sims-trade-bubble {
            position: absolute;
            transform: translate(-50%, -100%);
            background: rgba(10, 15, 26, 0.95);
            border-radius: 8px;
            padding: 7px 11px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 10.5px;
            box-shadow: 0 8px 24px rgba(0,0,0,0.7);
            pointer-events: auto;
            cursor: pointer;
            white-space: nowrap;
            z-index: 12;
            transition: all 0.2s ease;
        }
        .sims-trade-bubble.profit {
            border: 1.5px solid #10b981;
            box-shadow: 0 0 22px rgba(16, 185, 129, 0.5);
            color: #10b981;
            animation: pulse-trade-glow 2s infinite ease-in-out;
        }
        .sims-trade-bubble.loss {
            border: 1.5px solid #ef4444;
            box-shadow: 0 0 22px rgba(239, 68, 68, 0.5);
            color: #ef4444;
            animation: pulse-trade-glow 2s infinite ease-in-out;
        }
        .sims-trade-bubble.idle {
            border: 1px dashed rgba(132, 146, 166, 0.4);
            color: var(--text-muted);
            font-size: 10px;
        }
        @keyframes pulse-trade-glow {
            0%, 100% { transform: translate(-50%, -100%) scale(1); }
            50% { transform: translate(-50%, -108%) scale(1.05); }
        }

        /* 3D Office HUD Controls Bar */
        .office-hud-bar {
            position: absolute;
            top: 10px;
            left: 10px;
            right: 10px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 6px 12px;
            background: rgba(15, 22, 36, 0.88);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 8px;
            backdrop-filter: blur(10px);
            z-index: 20;
            pointer-events: auto;
            gap: 8px;
            flex-wrap: wrap;
        }
        .office-hud-left {
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .office-badge {
            background: linear-gradient(135deg, #f59e0b, #ec4899);
            color: #fff;
            font-weight: 800;
            font-size: 9.5px;
            padding: 3px 7px;
            border-radius: 5px;
            letter-spacing: 0.5px;
        }
        .office-title {
            font-size: 11px;
            color: #e2e8f0;
        }
        .office-title strong {
            color: #facc15;
            letter-spacing: 0.5px;
        }
        .office-hud-controls {
            display: flex;
            gap: 4px;
            align-items: center;
            flex-wrap: wrap;
        }
        .office-hud-btn {
            background: rgba(255, 255, 255, 0.06);
            border: 1px solid rgba(255, 255, 255, 0.12);
            color: #cbd5e1;
            font-size: 10px;
            font-weight: 600;
            padding: 4px 9px;
            border-radius: 5px;
            cursor: pointer;
            transition: all 0.2s ease;
        }
        .office-hud-btn:hover {
            background: rgba(255, 255, 255, 0.16);
            color: #fff;
        }
        .office-hud-btn.active {
            background: rgba(245, 158, 11, 0.25);
            border-color: #f59e0b;
            color: #facc15;
        }
        .office-status-pill {
            font-size: 10px;
            color: #94a3b8;
            background: rgba(0, 0, 0, 0.35);
            padding: 3px 8px;
            border-radius: 12px;
            border: 1px solid rgba(255, 255, 255, 0.05);
        }

        /* 📱 Mobil ve Tablet Cihazlar İçin Özel İyileştirmeler (Responsive Adaptation) */
        @media (max-width: 1024px) {
            #leftPanel.office-view-active {
                height: 68vh !important;
                min-height: 480px !important;
            }
            .office-3d-wrapper {
                min-height: 480px;
                height: 100%;
            }
            .office-hud-bar {
                top: 6px;
                left: 6px;
                right: 6px;
                padding: 4px 6px;
                gap: 4px;
                background: rgba(10, 16, 28, 0.94);
            }
            .office-title {
                display: none;
            }
            .office-status-pill {
                display: none;
            }
            .office-hud-btn {
                font-size: 9px;
                padding: 3px 6px;
            }
            .sims-bubble {
                max-width: 155px;
                font-size: 9.5px;
                padding: 5px 8px;
                border-radius: 8px;
            }
            .sims-bubble-header {
                font-size: 8.5px;
                margin-bottom: 2px;
            }
            .sims-bubble-body {
                font-size: 9px;
                line-height: 1.25;
            }
            .sims-trade-bubble {
                font-size: 9px;
                padding: 4px 8px;
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
                <button class="btn-scan" style="background: linear-gradient(135deg, rgba(245, 158, 11, 0.25), rgba(168, 85, 247, 0.25)); color: #facc15; border: 1px solid rgba(245, 158, 11, 0.5); font-weight: 700;" onclick="switchLeftView('office')" title="Sims Tarzı 3D Yapay Zeka İşlem Ofisi">🎮 3D Ofis</button>
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
                    <button class="view-tab-btn" id="tabViewOffice" onclick="switchLeftView('office')" style="border-color: rgba(245, 158, 11, 0.4); color: #facc15;">
                        🎮 3D OFİS (PATRON: EFE)
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

            <!-- 3D SİMS TARZI OFİS ALANI (PATRON: EFE & AJANLAR) -->
            <div id="office3dContainer" class="office-3d-wrapper" style="display: none;">
                <button class="btn-exit-fullscreen" id="btnExitOfficeFs" onclick="toggleOfficeFullscreen()" style="display: none;">✕ Tam Ekrandan Çık (ESC)</button>
                <div id="officeCanvasTarget"></div>
                
                <!-- 2D Sims Konuşma Baloncukları & Canlı İşlem Göstergesi Katmanı -->
                <div id="officeOverlay" class="office-bubbles-overlay">
                    <!-- Boss Efe Bubble -->
                    <div id="bubble-boss" class="sims-bubble boss" onclick="setOfficeCamera('boss')" title="Tıkla: Patron Efe'ye Odaklan">
                        <div class="sims-bubble-header">👑 PATRON: EFE</div>
                        <div class="sims-bubble-body" id="text-boss">Piyasayı tarayın beyler, acele yok, sermaye koruma önceliğimiz!</div>
                    </div>
                    <!-- Scanner Agent Bubble -->
                    <div id="bubble-scanner" class="sims-bubble scanner" onclick="setOfficeCamera('table')" title="Tıkla: Masaya Odaklan">
                        <div class="sims-bubble-header">📡 SCANNER AGENT</div>
                        <div class="sims-bubble-body" id="text-scanner">200+ parite taranıyor...</div>
                    </div>
                    <!-- TA Analyst Bubble -->
                    <div id="bubble-ta" class="sims-bubble ta" onclick="setOfficeCamera('table')" title="Tıkla: Masaya Odaklan">
                        <div class="sims-bubble-header">📊 TEKNİK ANALİST</div>
                        <div class="sims-bubble-body" id="text-ta">BTC 4s bant daralması inceleniyor.</div>
                    </div>
                    <!-- News Agent Bubble -->
                    <div id="bubble-news" class="sims-bubble news" onclick="setOfficeCamera('table')" title="Tıkla: Masaya Odaklan">
                        <div class="sims-bubble-header">📰 HABER & MAKRO</div>
                        <div class="sims-bubble-body" id="text-news">Funding rate stabil, kritik haber yok.</div>
                    </div>
                    <!-- Risk Officer Bubble -->
                    <div id="bubble-risk" class="sims-bubble risk" onclick="setOfficeCamera('table')" title="Tıkla: Masaya Odaklan">
                        <div class="sims-bubble-header">🛡️ RİSK ŞEFİ</div>
                        <div class="sims-bubble-body" id="text-risk">Kasa Kalkanı devrede: Maks 5x kaldıraç.</div>
                    </div>
                    <!-- Chief Analyst Bubble -->
                    <div id="bubble-chief" class="sims-bubble chief" onclick="setOfficeCamera('table')" title="Tıkla: Masaya Odaklan">
                        <div class="sims-bubble-header">🏛️ BAŞ STRATEJİST</div>
                        <div class="sims-bubble-body" id="text-chief">Efe Bey, piyasa şu an chop bölgesinde, bekliyoruz.</div>
                    </div>
                    <!-- Bilgisayar Ekranı Canlı İşlem Baloncuğu -->
                    <div id="tradeMonitorBubble" class="sims-trade-bubble idle" onclick="switchLeftView('positions')" title="Tıkla: Pozisyon Detaylarını Aç">
                        💤 AKTİF İŞLEM YOK (200 Parite Radarda)
                    </div>
                </div>

                <!-- 3D Ofis Üst Kontrol HUD Çubuğu -->
                <div class="office-hud-bar">
                    <div class="office-hud-left">
                        <span class="office-badge">🎮 3D OFİS</span>
                        <span class="office-title">PATRON: <strong>EFE</strong></span>
                    </div>
                    <div class="office-hud-controls">
                        <button class="office-hud-btn active" id="btnCamBoss" onclick="setOfficeCamera('boss')" title="Patron Efe'ye Odaklan">👑 Patron Efe</button>
                        <button class="office-hud-btn" id="btnCamTable" onclick="setOfficeCamera('table')" title="Ajanların Masasına Odaklan">📊 Masa</button>
                        <button class="office-hud-btn" id="btnCamIso" onclick="setOfficeCamera('iso')" title="İzometrik Kuşbakışı">🏢 Kuşbakışı</button>
                        <button class="office-hud-btn" id="btnToggleBubbles" onclick="cycleBubbleMode()" title="Baloncuk Görünümünü Değiştir (Akıllı/Tümü/Patron/Gizli)">💬 Balon</button>
                        <button class="office-hud-btn" id="btnOfficeFs" onclick="toggleOfficeFullscreen()" title="Tam Ekran Modu">⛶ Tam Ekran</button>
                        <button class="office-hud-btn" id="btnOfficeAudio" onclick="toggleOfficeSound()" title="Ofis Sesi">🔊</button>
                    </div>
                    <div class="office-hud-right">
                        <span id="officeStatusPill" class="office-status-pill">👑 Efe Masada | Piyasayı Gözlüyor</span>
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
            const officeContainer = document.getElementById('office3dContainer');
            const tfGroup = document.getElementById('btcTfGroup');
            const tabBtc = document.getElementById('tabViewBtc');
            const tabPos = document.getElementById('tabViewPositions');
            const tabSplit = document.getElementById('tabViewSplit');
            const tabOffice = document.getElementById('tabViewOffice');

            if (tabBtc) tabBtc.classList.toggle('active', mode === 'btc');
            if (tabPos) tabPos.classList.toggle('active', mode === 'positions');
            if (tabSplit) tabSplit.classList.toggle('active', mode === 'split');
            if (tabOffice) tabOffice.classList.toggle('active', mode === 'office');

            if (mode === 'btc') {
                if (btcContainer) {
                    btcContainer.style.display = 'flex';
                    btcContainer.style.flex = '1';
                    btcContainer.style.height = '100%';
                    btcContainer.style.borderBottom = 'none';
                }
                if (posContainer) posContainer.style.display = 'none';
                if (officeContainer) officeContainer.style.display = 'none';
                if (tfGroup) tfGroup.style.display = 'flex';
                renderTradingView();
            } else if (mode === 'positions') {
                if (btcContainer) btcContainer.style.display = 'none';
                if (officeContainer) officeContainer.style.display = 'none';
                if (posContainer) {
                    posContainer.style.display = 'flex';
                    posContainer.style.flex = '1';
                    posContainer.style.height = '100%';
                }
                if (tfGroup) tfGroup.style.display = 'none';
            } else if (mode === 'split') {
                if (officeContainer) officeContainer.style.display = 'none';
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
            } else if (mode === 'office') {
                if (btcContainer) btcContainer.style.display = 'none';
                if (posContainer) posContainer.style.display = 'none';
                if (officeContainer) {
                    officeContainer.style.display = 'flex';
                    officeContainer.style.flex = '1';
                    officeContainer.style.height = '100%';
                }
                if (tfGroup) tfGroup.style.display = 'none';
                const leftPanel = document.getElementById('leftPanel');
                if (leftPanel) leftPanel.classList.add('office-view-active');
                initOrResizeOffice3D();
            }
            if (mode !== 'office') {
                const leftPanel = document.getElementById('leftPanel');
                if (leftPanel) leftPanel.classList.remove('office-view-active');
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
                    const isProt = l.status === 'PROTECTED';
                    let statusClass = isAppr ? 'approved' : (isProt ? 'protected' : 'rejected');
                    let statusBadge = isAppr ? '<span class="badge-appr">✅ FIRSAT BULUNDU</span>' : (isProt ? '<span class="badge-prot">🛡️ SERMAYE KORUMASI</span>' : '<span class="badge-rej">❌ ELENDİ</span>');

                    let reasonTxt = l.reason || '';
                    if (reasonTxt.indexOf('[Son 1 Saatte') !== -1) {
                        const parts = reasonTxt.split('[Son 1 Saatte');
                        const prefix = parts[0];
                        const testPart = parts[1].replace(']', '').trim();
                        reasonTxt = prefix + '<br><span style="color:#38bdf8; font-weight:600; background:rgba(56,189,248,0.12); padding:1px 6px; border-radius:3px; display:inline-block; margin-top:4px;">⏱️ Bu Saatte ' + testPart + '</span>';
                    }
                    logHtml += `
                        <div class="log-item ${statusClass}">
                            <div class="log-top">
                                <span class="log-sym">${l.symbol}</span>
                                ${statusBadge}
                                <span class="log-time">${l.time}</span>
                            </div>
                            <div class="log-reason">${reasonTxt} ${l.details ? `<br><span style="font-size:10px; color:#38bdf8; opacity:0.85; font-style:italic;">💡 Mod: ${l.details}</span>` : ''}</div>
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

            // 7. 3D Sims Ofis Verilerini Canlı Güncelle
            if (typeof updateOffice3DData === 'function') {
                updateOffice3DData(data);
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

/* ==========================================================================
   🎮 3D SİMS TARZI YAPAY ZEKA TİCARET OFİSİ (THREE.JS ENGINE) - v3.0.0
   Tam Anlamıyla Yaşayan Ofis Simülasyonu:
   1. Masa & Karakter Ergonomisi: Masaya girme bug'ı tamamen giderildi.
   2. Herkesin Kendi Bilgisayarı: Her ajanın masada çift monitörlü işlem terminali.
   3. Şeffaf & Dinamik Baloncuklar: Glassmorphic şeffaflık, konuştukça açılır ve söner.
   4. Otonom Ofis Rutini: Çalışanlar kalkar, yürür, kahve alır, tuvalete gider, patrona rapor sunar!
   ========================================================================== */

let officeScene, officeCamera, officeRenderer, officeControls;
let officeInitialized = false;
let officeAnimFrameId = null;

// Karakterler ve Mobilya Referansları
let plumbobMesh = null;
let plumbobLight = null;
let bossGroup = null;
let bossHeadMesh = null;
let wcSignLight = null;
let wcSignMesh = null;

// Ajanlar Sözlüğü (Navigasyon, Kemikler ve Durum Yönetimi)
const agents = {};

// Masa Monitörleri ve Işıklar
let officeDeskScreens = [];
let officeDeskLight = null;
let wallCanvasTexture = null;
let wallCanvasCtx = null;

// Kamera Hedefleri (Lerp / Yumuşak Geçiş İçin)
let camTargetPos = null;
let camLookTarget = null;
let camCurrentLook = null;

// Baloncuk Görünüm Modu & Zamanlayıcılar
let currentBubbleMode = window.innerWidth < 768 ? 'smart' : 'all';
let bubbleSpeechTimers = {};
let nextAutonomousActionTime = 6000;
let nextDialogueTime = 3000;

// Karakter Balon Çapaları (3D Dünya Konumu -> 2D Ekran Yansıtması)
const bubbleAnchors = {
    boss: { pos: null, el: null, bodyEl: null, isSpeaking: false },
    scanner: { pos: null, el: null, bodyEl: null, isSpeaking: false },
    ta: { pos: null, el: null, bodyEl: null, isSpeaking: false },
    news: { pos: null, el: null, bodyEl: null, isSpeaking: false },
    risk: { pos: null, el: null, bodyEl: null, isSpeaking: false },
    chief: { pos: null, el: null, bodyEl: null, isSpeaking: false },
    trade: { pos: null, el: null }
};

// Ses Efekti (Web Audio API)
let officeAudioEnabled = true;
let audioCtx = null;

function getAudioContext() {
    if (!audioCtx) {
        const AudioContextClass = window.AudioContext || window.webkitAudioContext;
        if (AudioContextClass) audioCtx = new AudioContextClass();
    }
    if (audioCtx && audioCtx.state === 'suspended') {
        audioCtx.resume();
    }
    return audioCtx;
}

function playOfficeSound(type = 'click') {
    if (!officeAudioEnabled) return;
    try {
        const ctx = getAudioContext();
        if (!ctx) return;
        const now = ctx.currentTime;
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.connect(gain);
        gain.connect(ctx.destination);

        if (type === 'click') {
            osc.type = 'triangle';
            osc.frequency.setValueAtTime(600 + Math.random() * 200, now);
            osc.frequency.exponentialRampToValueAtTime(120, now + 0.04);
            gain.gain.setValueAtTime(0.04, now);
            gain.gain.exponentialRampToValueAtTime(0.001, now + 0.04);
            osc.start(now);
            osc.stop(now + 0.04);
        } else if (type === 'chime') {
            osc.type = 'sine';
            osc.frequency.setValueAtTime(587.33, now);
            osc.frequency.setValueAtTime(880.00, now + 0.08);
            gain.gain.setValueAtTime(0.08, now);
            gain.gain.exponentialRampToValueAtTime(0.001, now + 0.35);
            osc.start(now);
            osc.stop(now + 0.35);
        } else if (type === 'talk') {
            // Sims tarzı sevimli gevezelik sesi
            osc.type = 'sine';
            const f1 = 300 + Math.random() * 250;
            osc.frequency.setValueAtTime(f1, now);
            osc.frequency.linearRampToValueAtTime(f1 * 1.4, now + 0.07);
            gain.gain.setValueAtTime(0.05, now);
            gain.gain.exponentialRampToValueAtTime(0.001, now + 0.14);
            osc.start(now);
            osc.stop(now + 0.14);
        } else if (type === 'coffee') {
            // Espresso buharı / fincan sesi
            osc.type = 'triangle';
            osc.frequency.setValueAtTime(1200, now);
            osc.frequency.exponentialRampToValueAtTime(400, now + 0.12);
            gain.gain.setValueAtTime(0.06, now);
            gain.gain.exponentialRampToValueAtTime(0.001, now + 0.15);
            osc.start(now);
            osc.stop(now + 0.15);
        } else if (type === 'trade') {
            osc.type = 'square';
            osc.frequency.setValueAtTime(523.25, now);
            osc.frequency.setValueAtTime(659.25, now + 0.1);
            osc.frequency.setValueAtTime(783.99, now + 0.2);
            gain.gain.setValueAtTime(0.09, now);
            gain.gain.exponentialRampToValueAtTime(0.001, now + 0.45);
            osc.start(now);
            osc.stop(now + 0.45);
        }
    } catch (e) {}
}

function toggleOfficeSound() {
    officeAudioEnabled = !officeAudioEnabled;
    const btn = document.getElementById('btnOfficeAudio');
    if (btn) {
        btn.innerText = officeAudioEnabled ? '🔊 Ses: Açık' : '🔇 Ses: Kapalı';
        btn.classList.toggle('active', officeAudioEnabled);
    }
    if (officeAudioEnabled) playOfficeSound('chime');
}

function cycleBubbleMode() {
    if (currentBubbleMode === 'smart') {
        currentBubbleMode = 'all';
    } else if (currentBubbleMode === 'all') {
        currentBubbleMode = 'boss';
    } else if (currentBubbleMode === 'boss') {
        currentBubbleMode = 'off';
    } else {
        currentBubbleMode = 'smart';
    }

    const btn = document.getElementById('btnToggleBubbles');
    if (btn) {
        const labels = {
            smart: '💬 Balon: Akıllı',
            all: '💬 Balon: Tümü',
            boss: '💬 Balon: Patron',
            off: '💬 Balon: Gizli'
        };
        btn.innerText = labels[currentBubbleMode] || '💬 Balon';
    }
    playOfficeSound('click');
}

// -------------------------------------------------------------
// DİNAMİK KONUŞMA BALONCUKLARI SİSTEMİ (FADE IN & FADE OUT)
// -------------------------------------------------------------
function triggerSpeech(charId, text, durationMs = 5000) {
    if (currentBubbleMode === 'off') return;
    if (currentBubbleMode === 'boss' && charId !== 'boss' && charId !== 'trade') return;

    const anchor = bubbleAnchors[charId];
    if (!anchor || !anchor.el) return;

    if (anchor.bodyEl && text) {
        anchor.bodyEl.innerText = text;
    }

    // Baloncuğu şeffaf halden aç
    anchor.isSpeaking = true;
    anchor.el.classList.add('speaking');
    playOfficeSound('talk');

    // Var olan zamanlayıcıyı sıfırla
    if (bubbleSpeechTimers[charId]) {
        clearTimeout(bubbleSpeechTimers[charId]);
    }

    // Belirli süre sonra yumuşakça söndür
    bubbleSpeechTimers[charId] = setTimeout(() => {
        anchor.isSpeaking = false;
        anchor.el.classList.remove('speaking');
    }, durationMs);
}

// -------------------------------------------------------------
// TAM EKRAN (FULLSCREEN) YÖNETİMİ
// -------------------------------------------------------------
function toggleOfficeFullscreen() {
    const wrapper = document.getElementById('office3dContainer');
    const btnExit = document.getElementById('btnExitOfficeFs');
    const btnFs = document.getElementById('btnOfficeFs');
    if (!wrapper) return;

    const isFs = wrapper.classList.toggle('is-fullscreen');
    if (btnExit) btnExit.style.display = isFs ? 'block' : 'none';
    if (btnFs) btnFs.innerText = isFs ? '✕ Çıkış' : '⛶ Tam Ekran';

    setTimeout(resizeOffice3D, 40);
    setTimeout(resizeOffice3D, 250);
    playOfficeSound('click');
}

document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        const wrapper = document.getElementById('office3dContainer');
        if (wrapper && wrapper.classList.contains('is-fullscreen')) {
            toggleOfficeFullscreen();
        }
    }
});

// -------------------------------------------------------------
// 3D OFİS BAŞLATMA & BOYUTLANDIRMA
// -------------------------------------------------------------
function initOrResizeOffice3D() {
    if (!officeInitialized) {
        initOffice3D();
    } else {
        resizeOffice3D();
    }
}

function resizeOffice3D() {
    if (!officeRenderer || !officeCamera) return;
    const container = document.getElementById('officeCanvasTarget');
    if (!container) return;
    const width = container.clientWidth || 600;
    const height = container.clientHeight || 450;
    if (width === 0 || height === 0) return;

    const aspect = width / height;
    officeCamera.aspect = aspect;

    if (aspect < 1.0) {
        officeCamera.fov = Math.min(65, 45 / Math.max(0.68, aspect));
    } else {
        officeCamera.fov = 45;
    }

    officeCamera.updateProjectionMatrix();
    officeRenderer.setSize(width, height);
    officeRenderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2.5));
}

function initOffice3D() {
    const container = document.getElementById('officeCanvasTarget');
    if (!container) return;
    if (typeof THREE === 'undefined') {
        console.error("Three.js henüz yüklenemedi.");
        return;
    }

    const width = container.clientWidth || 600;
    const height = container.clientHeight || 450;
    const aspect = width / height;

    // 1. Sahne & Sis
    officeScene = new THREE.Scene();
    officeScene.background = new THREE.Color(0x090e18);
    officeScene.fog = new THREE.FogExp2(0x090e18, 0.02);

    // 2. Kamera
    const initialFov = aspect < 1.0 ? Math.min(65, 45 / Math.max(0.68, aspect)) : 45;
    officeCamera = new THREE.PerspectiveCamera(initialFov, aspect, 0.1, 100);
    const isMobile = aspect < 1.0 || width < 768;
    officeCamera.position.set(0, isMobile ? 5.6 : 5.0, isMobile ? 8.6 : 7.6);
    camCurrentLook = new THREE.Vector3(0, 1.2, 0);
    officeCamera.lookAt(camCurrentLook);

    // 3. Renderer
    officeRenderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "high-performance" });
    officeRenderer.setSize(width, height);
    officeRenderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2.5));
    officeRenderer.shadowMap.enabled = true;
    officeRenderer.shadowMap.type = THREE.PCFSoftShadowMap;
    officeRenderer.domElement.style.touchAction = 'none';
    container.innerHTML = '';
    container.appendChild(officeRenderer.domElement);

    // 4. OrbitControls
    if (typeof THREE.OrbitControls !== 'undefined') {
        officeControls = new THREE.OrbitControls(officeCamera, officeRenderer.domElement);
        officeControls.enableDamping = true;
        officeControls.dampingFactor = 0.06;
        officeControls.maxPolarAngle = Math.PI / 2.05;
        officeControls.minDistance = 2.2;
        officeControls.maxDistance = 25;
        officeControls.target.copy(camCurrentLook);
        officeControls.rotateSpeed = 0.85;
        officeControls.zoomSpeed = 1.0;
        officeControls.touches = {
            ONE: THREE.TOUCH.ROTATE,
            TWO: THREE.TOUCH.DOLLY_PAN
        };
    }

    // 5. Işıklandırma
    setupOfficeLights();

    // 6. Ofis Mimarisi: Zemin, Halı, Manzara Penceresi, Kahve İstasyonu & WC Kapısı
    buildOfficeArchitecture();

    // 7. Kusursuz Ergonomik Trading Masası & Monitörler (Masanın içine girme bug'ı 0)
    buildTradingDesk();

    // 8. 👑 BAŞ KOLTUK / PATRON: EFE (Siyah Takım Elbise, Işıklı Plumbob, Altın İsimlik)
    buildBossEfe();

    // 9. 5 Uzman Yapay Zeka Ajanı (Kendi Çalışma Masaları, Çift Monitörleri ve Yürüme Kemikleri)
    buildSpecialistAgents();

    // 10. Çapa Noktalarını DOM Elementlerine Bağla
    bindBubbleElements();

    officeInitialized = true;

    // Varsayılan kamera açısı
    setOfficeCamera('boss');

    // Başlangıçta Patron Efe ekibe hoş geldin der
    setTimeout(() => {
        triggerSpeech('boss', "Piyasayı tarayın beyler, acele yok, sermaye koruma önceliğimiz!", 6000);
    }, 1200);

    // Animasyon Döngüsünü Başlat
    if (!officeAnimFrameId) {
        animateOffice(0);
    }

    window.addEventListener('resize', resizeOffice3D);
    window.addEventListener('orientationchange', () => {
        setTimeout(resizeOffice3D, 100);
    });
}

// -------------------------------------------------------------
// IŞIKLANDIRMA SİSTEMİ
// -------------------------------------------------------------
function setupOfficeLights() {
    const ambientLight = new THREE.AmbientLight(0xdce7ff, 0.95);
    officeScene.add(ambientLight);

    const dirLight = new THREE.DirectionalLight(0xffffff, 1.15);
    dirLight.position.set(6, 12, 8);
    dirLight.castShadow = true;
    dirLight.shadow.mapSize.width = 1024;
    dirLight.shadow.mapSize.height = 1024;
    dirLight.shadow.bias = -0.001;
    officeScene.add(dirLight);

    // Patron Efe Tepe Spotu
    const bossSpot = new THREE.PointLight(0xfbbf24, 1.6, 9);
    bossSpot.position.set(0, 4.2, -2.4);
    officeScene.add(bossSpot);

    // Efe Rim Işığı
    const bossRimLight = new THREE.PointLight(0x38bdf8, 0.7, 6);
    bossRimLight.position.set(0, 2.0, -3.6);
    officeScene.add(bossRimLight);

    // Masa Dinamik İşlem Işığı
    officeDeskLight = new THREE.PointLight(0x38bdf8, 1.2, 8);
    officeDeskLight.position.set(0, 1.8, 0);
    officeScene.add(officeDeskLight);
}

// -------------------------------------------------------------
// OFİS MİMARİSİ: Kahve Barı, WC Kapısı, Panoramik Pencere, Zemin
// -------------------------------------------------------------
function buildOfficeArchitecture() {
    // 1. Zemin
    const floorGeo = new THREE.PlaneGeometry(24, 20);
    const floorMat = new THREE.MeshStandardMaterial({ color: 0x141a27, roughness: 0.45, metalness: 0.12 });
    const floor = new THREE.Mesh(floorGeo, floorMat);
    floor.rotation.x = -Math.PI / 2;
    floor.receiveShadow = true;
    officeScene.add(floor);

    // 2. Yönetici Halısı
    const rugGeo = new THREE.PlaneGeometry(13.5, 9.5);
    const rugMat = new THREE.MeshStandardMaterial({ color: 0x0c1322, roughness: 0.85 });
    const rug = new THREE.Mesh(rugGeo, rugMat);
    rug.rotation.x = -Math.PI / 2;
    rug.position.set(0, 0.015, 0);
    rug.receiveShadow = true;
    officeScene.add(rug);

    // Halı altın bordürü
    const borderGeo = new THREE.RingGeometry(4.7, 4.8, 4);
    const borderMat = new THREE.MeshBasicMaterial({ color: 0xd97706, side: THREE.DoubleSide });
    const rugBorder = new THREE.Mesh(borderGeo, borderMat);
    rugBorder.rotation.x = -Math.PI / 2;
    rugBorder.position.set(0, 0.02, 0);
    rugBorder.scale.set(1.4, 1.0, 1.0);
    officeScene.add(rugBorder);

    // 3. Arka Duvar & Panoramik Şehir Penceresi
    const backWallGeo = new THREE.BoxGeometry(24, 9, 0.3);
    const backWallMat = new THREE.MeshStandardMaterial({ color: 0x101726, roughness: 0.7 });
    const backWall = new THREE.Mesh(backWallGeo, backWallMat);
    backWall.position.set(0, 4.5, -6.5);
    officeScene.add(backWall);

    // Pencere & Gökdelenler
    const windowFrameGeo = new THREE.BoxGeometry(15, 5.5, 0.4);
    const windowFrameMat = new THREE.MeshStandardMaterial({ color: 0x050811, metalness: 0.8 });
    const windowFrame = new THREE.Mesh(windowFrameGeo, windowFrameMat);
    windowFrame.position.set(0, 4.2, -6.4);
    officeScene.add(windowFrame);

    const glassGeo = new THREE.PlaneGeometry(14.6, 5.1);
    const glassMat = new THREE.MeshPhysicalMaterial({ color: 0x60a5fa, transparent: true, opacity: 0.2, transmission: 0.7 });
    const glass = new THREE.Mesh(glassGeo, glassMat);
    glass.position.set(0, 4.2, -6.35);
    officeScene.add(glass);

    buildSkylineCity();
    buildWallDisplay();

    // 4. ☕ ESPRESSO KAHVE İSTASYONU (Sağ Arka Köşe: x = 5.0, z = 2.0)
    buildCoffeeStation(5.0, 0, 2.0);

    // 5. 🚻 TUVALET / WC KAPISI (Sol Arka Köşe: x = -5.0, z = 2.0)
    buildRestroomDoor(-5.0, 0, 2.0);

    // 6. Saksı Bitkileri
    buildPottedPlant(-5.6, 0, -4.8);
    buildPottedPlant(5.6, 0, -4.8);
}

function buildSkylineCity() {
    const cityGroup = new THREE.Group();
    cityGroup.position.set(0, 0, -11);

    const bldgColors = [0x0b1329, 0x070c1b, 0x0f1938, 0x091024];
    const windowMats = [
        new THREE.MeshBasicMaterial({ color: 0xfacc15 }),
        new THREE.MeshBasicMaterial({ color: 0x38bdf8 }),
        new THREE.MeshBasicMaterial({ color: 0xffffff })
    ];

    for (let i = 0; i < 20; i++) {
        const posX = -14 + i * 1.5 + (Math.random() - 0.5) * 0.8;
        const bldgHeight = 5 + Math.random() * 8;
        const bldgWidth = 1.0 + Math.random() * 1.2;
        const bldgDepth = 1.0 + Math.random() * 1.2;

        const bldgGeo = new THREE.BoxGeometry(bldgWidth, bldgHeight, bldgDepth);
        const bldgMat = new THREE.MeshStandardMaterial({ color: bldgColors[i % bldgColors.length], roughness: 0.6 });
        const bldg = new THREE.Mesh(bldgGeo, bldgMat);
        bldg.position.set(posX, bldgHeight / 2 - 1, (Math.random() - 0.5) * 2);
        cityGroup.add(bldg);

        if (Math.random() > 0.3) {
            const winGeo = new THREE.PlaneGeometry(0.15, 0.2);
            const winMat = windowMats[Math.floor(Math.random() * windowMats.length)];
            for (let y = 1; y < bldgHeight - 1; y += 0.8) {
                const winMesh = new THREE.Mesh(winGeo, winMat);
                winMesh.position.set(posX + (Math.random() - 0.5) * 0.4, y, bldg.position.z + bldgDepth / 2 + 0.02);
                cityGroup.add(winMesh);
            }
        }
    }
    officeScene.add(cityGroup);
}

function buildWallDisplay() {
    const canvas = document.createElement('canvas');
    canvas.width = 512;
    canvas.height = 128;
    wallCanvasCtx = canvas.getContext('2d');
    wallCanvasCtx.fillStyle = '#060a12';
    wallCanvasCtx.fillRect(0, 0, 512, 128);
    wallCanvasCtx.fillStyle = '#f59e0b';
    wallCanvasCtx.font = 'bold 24px monospace';
    wallCanvasCtx.fillText('⚡ AI FUND OFFICE LIVE', 30, 45);
    wallCanvasCtx.fillStyle = '#38bdf8';
    wallCanvasCtx.font = '18px monospace';
    wallCanvasCtx.fillText('BTC FUTURES DESK | BOSS: EFE', 30, 80);

    wallCanvasTexture = new THREE.CanvasTexture(canvas);
    const wallScreenGeo = new THREE.PlaneGeometry(5.0, 1.25);
    const wallScreenMat = new THREE.MeshBasicMaterial({ map: wallCanvasTexture });
    const wallScreen = new THREE.Mesh(wallScreenGeo, wallScreenMat);
    wallScreen.position.set(-4.5, 5.0, -6.3);
    officeScene.add(wallScreen);
}

// ☕ Kahve & Espresso İstasyonu
function buildCoffeeStation(x, y, z) {
    const stationGroup = new THREE.Group();
    stationGroup.position.set(x, y, z);

    // Ahşap bar tezgahı
    const counterGeo = new THREE.BoxGeometry(1.6, 0.85, 0.9);
    const counterMat = new THREE.MeshStandardMaterial({ color: 0x1f293d, roughness: 0.5 });
    const counter = new THREE.Mesh(counterGeo, counterMat);
    counter.position.y = 0.425;
    counter.castShadow = true;
    stationGroup.add(counter);

    // Mermer tezgah üstü
    const marbleGeo = new THREE.BoxGeometry(1.66, 0.05, 0.96);
    const marbleMat = new THREE.MeshStandardMaterial({ color: 0xe2e8f0, roughness: 0.2 });
    const marble = new THREE.Mesh(marbleGeo, marbleMat);
    marble.position.y = 0.875;
    stationGroup.add(marble);

    // İtalyan Espresso Makinesi
    const machineGeo = new THREE.BoxGeometry(0.65, 0.55, 0.55);
    const machineMat = new THREE.MeshStandardMaterial({ color: 0xd1d5db, metalness: 0.9, roughness: 0.2 });
    const machine = new THREE.Mesh(machineGeo, machineMat);
    machine.position.set(-0.25, 1.17, 0);
    stationGroup.add(machine);

    // Kırmızı güç ışığı
    const ledGeo = new THREE.SphereGeometry(0.02, 8, 8);
    const ledMat = new THREE.MeshBasicMaterial({ color: 0xef4444 });
    const led = new THREE.Mesh(ledGeo, ledMat);
    led.position.set(-0.25, 1.35, 0.29);
    stationGroup.add(led);

    // Kahve Fincanları Grubu
    const cupMat = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.3 });
    [-0.05, 0.15, 0.35].forEach((cx, idx) => {
        const cupGeo = new THREE.CylinderGeometry(0.06, 0.05, 0.09, 12);
        const cup = new THREE.Mesh(cupGeo, cupMat);
        cup.position.set(cx, 0.94, 0.15 + (idx % 2) * 0.1);
        stationGroup.add(cup);
    });

    officeScene.add(stationGroup);
}

// 🚻 Tuvalet / WC Kapısı & Işıklı Tabelası
function buildRestroomDoor(x, y, z) {
    const wcGroup = new THREE.Group();
    wcGroup.position.set(x, y, z);

    // Kapı Kasası & Duvar Paneli
    const frameGeo = new THREE.BoxGeometry(1.4, 2.5, 0.15);
    const frameMat = new THREE.MeshStandardMaterial({ color: 0x0f172a, roughness: 0.6 });
    const frame = new THREE.Mesh(frameGeo, frameMat);
    frame.position.y = 1.25;
    wcGroup.add(frame);

    // Buzlu Cam Kapı Kanadı
    const doorGeo = new THREE.BoxGeometry(1.15, 2.3, 0.08);
    const doorMat = new THREE.MeshPhysicalMaterial({ color: 0x38bdf8, roughness: 0.3, transmission: 0.6, transparent: true, opacity: 0.85 });
    const door = new THREE.Mesh(doorGeo, doorMat);
    door.position.set(0, 1.15, 0.02);
    wcGroup.add(door);

    // Krom Kapı Kolu
    const handleGeo = new THREE.CylinderGeometry(0.02, 0.02, 0.25, 8);
    const handleMat = new THREE.MeshStandardMaterial({ color: 0xe2e8f0, metalness: 0.95 });
    const handle = new THREE.Mesh(handleGeo, handleMat);
    handle.position.set(-0.45, 1.1, 0.08);
    wcGroup.add(handle);

    // Kapı Üstü Neon Tabela: "🚻 WC"
    const signGeo = new THREE.BoxGeometry(0.8, 0.25, 0.08);
    const signMat = new THREE.MeshStandardMaterial({ color: 0x0284c7, emissive: 0x0369a1, emissiveIntensity: 0.8 });
    wcSignMesh = new THREE.Mesh(signGeo, signMat);
    wcSignMesh.position.set(0, 2.65, 0.1);
    wcGroup.add(wcSignMesh);

    // Kapı Dolu/Boş Işığı (Yeşil = Boş, Turuncu = Dolu)
    wcSignLight = new THREE.PointLight(0x10b981, 1.2, 4);
    wcSignLight.position.set(0, 2.65, 0.25);
    wcGroup.add(wcSignLight);

    officeScene.add(wcGroup);
}

function buildPottedPlant(x, y, z) {
    const plantGroup = new THREE.Group();
    plantGroup.position.set(x, y, z);

    const potGeo = new THREE.CylinderGeometry(0.4, 0.3, 0.8, 16);
    const potMat = new THREE.MeshStandardMaterial({ color: 0xf8fafc, roughness: 0.2 });
    const pot = new THREE.Mesh(potGeo, potMat);
    pot.position.y = 0.4;
    pot.castShadow = true;
    plantGroup.add(pot);

    const leafMat = new THREE.MeshStandardMaterial({ color: 0x15803d, roughness: 0.4, side: THREE.DoubleSide });
    for (let i = 0; i < 7; i++) {
        const leafGeo = new THREE.SphereGeometry(0.3, 8, 8);
        leafGeo.scale(0.8, 1.4, 0.1);
        const leaf = new THREE.Mesh(leafGeo, leafMat);
        const angle = (i / 7) * Math.PI * 2;
        leaf.position.set(Math.cos(angle) * 0.3, 1.1 + Math.sin(i) * 0.2, Math.sin(angle) * 0.3);
        leaf.rotation.set(0.4, angle, 0.3);
        plantGroup.add(leaf);
    }

    officeScene.add(plantGroup);
}

// -------------------------------------------------------------
// KUSURSUZ ERGONOMİK TRADING MASASI (BUG & İÇE GİRME %100 GİDERİLDİ)
// -------------------------------------------------------------
function buildTradingDesk() {
    const tableGroup = new THREE.Group();

    // Standart masa ölçüleri: Genişlik: 2.2m (X: -1.1 ile +1.1), Uzunluk: 4.8m (Z: -2.4 ile +2.4)
    // Masa tablası üst seviyesi: y = 0.78m (Ergonomik çalışma yüksekliği)
    const topGeo = new THREE.BoxGeometry(2.2, 0.06, 4.8);
    const topMat = new THREE.MeshStandardMaterial({ color: 0x182030, roughness: 0.35, metalness: 0.25 });
    const tableTop = new THREE.Mesh(topGeo, topMat);
    tableTop.position.set(0, 0.78, 0);
    tableTop.castShadow = true;
    tableTop.receiveShadow = true;
    tableGroup.add(tableTop);

    // Altın beveled kenarlık
    const trimGeo = new THREE.BoxGeometry(2.24, 0.02, 4.84);
    const trimMat = new THREE.MeshStandardMaterial({ color: 0xf59e0b, metalness: 0.85, roughness: 0.2 });
    const trim = new THREE.Mesh(trimGeo, trimMat);
    trim.position.set(0, 0.80, 0);
    tableGroup.add(trim);

    // Masa Ayakları: 4 Adet Ağır Çelik Kolon
    const legGeo = new THREE.CylinderGeometry(0.06, 0.06, 0.78, 16);
    const legMat = new THREE.MeshStandardMaterial({ color: 0x0f172a, metalness: 0.9, roughness: 0.3 });
    [
        [-0.95, -2.2],
        [0.95, -2.2],
        [-0.95, 2.2],
        [0.95, 2.2]
    ].forEach(([lx, lz]) => {
        const leg = new THREE.Mesh(legGeo, legMat);
        leg.position.set(lx, 0.39, lz);
        leg.castShadow = true;
        tableGroup.add(leg);
    });

    // Masanın Ortasındaki Canlı İşlem Ana Göstergesi (Holografik Panel)
    const centerDisplayGeo = new THREE.BoxGeometry(0.9, 0.45, 0.04);
    const centerMat = new THREE.MeshStandardMaterial({ color: 0x0284c7, emissive: 0x0369a1, emissiveIntensity: 0.8 });
    const centerScr = new THREE.Mesh(centerDisplayGeo, centerMat);
    centerScr.position.set(0, 1.05, 0);
    tableGroup.add(centerScr);
    officeDeskScreens.push(centerScr);

    // Canlı İşlem Balonunun Çapa Noktası
    bubbleAnchors.trade.pos = new THREE.Vector3(0, 1.45, 0);

    officeScene.add(tableGroup);
}

// -------------------------------------------------------------
// 👑 BAŞ KOLTUK / PATRON: EFE
// Siyah Takım Elbise, Işıklı Sims Plumbob'u, Altın İsimlik, Apple MacBook
// -------------------------------------------------------------
function buildBossEfe() {
    bossGroup = new THREE.Group();
    bossGroup.position.set(0, 0, -2.4); // Masanın başı (z = -2.4), +Z'ye bakıyor
    bossGroup.rotation.y = 0;

    // 1. Executive Yönetici Koltuğu (Siyah Deri & Altın Çerçeveli)
    const chairGroup = new THREE.Group();
    const chromeMat = new THREE.MeshStandardMaterial({ color: 0xe2e8f0, metalness: 0.9, roughness: 0.1 });
    const leatherMat = new THREE.MeshStandardMaterial({ color: 0x090c10, roughness: 0.35, metalness: 0.15 });
    const goldMat = new THREE.MeshStandardMaterial({ color: 0xf59e0b, metalness: 0.85, roughness: 0.2 });

    const piston = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.05, 0.45, 16), chromeMat);
    piston.position.y = 0.225;
    chairGroup.add(piston);

    const seat = new THREE.Mesh(new THREE.BoxGeometry(0.75, 0.1, 0.7), leatherMat);
    seat.position.y = 0.45;
    seat.castShadow = true;
    chairGroup.add(seat);

    const back = new THREE.Mesh(new THREE.BoxGeometry(0.72, 1.0, 0.1), leatherMat);
    back.position.set(0, 0.98, -0.32);
    back.rotation.x = -0.06;
    back.castShadow = true;
    chairGroup.add(back);

    [-0.38, 0.38].forEach(ax => {
        const arm = new THREE.Mesh(new THREE.BoxGeometry(0.06, 0.2, 0.5), goldMat);
        arm.position.set(ax, 0.65, -0.05);
        chairGroup.add(arm);
    });
    bossGroup.add(chairGroup);

    // 2. Patron Efe'nin Gövdesi: Siyah Özel Dikim Takım Elbise
    const suitMat = new THREE.MeshStandardMaterial({ color: 0x0e1117, roughness: 0.32, metalness: 0.25 });
    const shirtMat = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.25 });
    const tieMat = new THREE.MeshStandardMaterial({ color: 0x000000, roughness: 0.1, metalness: 0.3 });

    // Oturan bacaklar (Masanın altında rahatça durur)
    const legs = new THREE.Mesh(new THREE.BoxGeometry(0.55, 0.18, 0.55), suitMat);
    legs.position.set(0, 0.54, 0.05);
    bossGroup.add(legs);

    // Gövde (Ceket)
    const torso = new THREE.Mesh(new THREE.BoxGeometry(0.60, 0.58, 0.34), suitMat);
    torso.position.set(0, 0.90, -0.05);
    torso.castShadow = true;
    bossGroup.add(torso);

    // Beyaz Gömlek Yakası & Siyah Kravat
    const collar = new THREE.Mesh(new THREE.BoxGeometry(0.22, 0.12, 0.18), shirtMat);
    collar.position.set(0, 1.15, 0.07);
    bossGroup.add(collar);

    const tie = new THREE.Mesh(new THREE.BoxGeometry(0.07, 0.30, 0.04), tieMat);
    tie.position.set(0, 1.02, 0.14);
    bossGroup.add(tie);

    // Altın Yaka İğnesi
    const pin = new THREE.Mesh(new THREE.BoxGeometry(0.035, 0.035, 0.02), goldMat);
    pin.position.set(-0.18, 1.10, 0.13);
    bossGroup.add(pin);

    // Kollar & Eller (Masanın üstüne uzanır, klavye/laptop yanında durur)
    [-0.34, 0.34].forEach(ax => {
        const arm = new THREE.Mesh(new THREE.BoxGeometry(0.12, 0.42, 0.12), suitMat);
        arm.position.set(ax, 0.85, 0.18);
        arm.rotation.x = Math.PI / 3.2;
        bossGroup.add(arm);
    });

    // 3. Baş & Saç
    const headGroup = new THREE.Group();
    headGroup.position.set(0, 1.35, -0.02);

    const skinMat = new THREE.MeshStandardMaterial({ color: 0xf5c6a5, roughness: 0.5 });
    const head = new THREE.Mesh(new THREE.BoxGeometry(0.32, 0.34, 0.30), skinMat);
    head.castShadow = true;
    headGroup.add(head);

    const hair = new THREE.Mesh(new THREE.BoxGeometry(0.34, 0.12, 0.32), new THREE.MeshStandardMaterial({ color: 0x171717, roughness: 0.7 }));
    hair.position.set(0, 0.16, -0.01);
    headGroup.add(hair);

    bossHeadMesh = headGroup;
    bossGroup.add(headGroup);

    // 4. Efe'nin Masasındaki Apple MacBook & Altın İsimlik
    buildBossDeskItems(bossGroup);

    // 5. ✨ IŞIK SAÇAN DÖNEN SİMS PLUMBOB (Yeşil Kristal)
    buildSimsPlumbob(bossGroup);

    bubbleAnchors.boss.pos = new THREE.Vector3(0, 2.35, -2.4);

    officeScene.add(bossGroup);
}

function buildSimsPlumbob(parentGroup) {
    const plumbobGeo = new THREE.OctahedronGeometry(0.18, 0);
    plumbobGeo.scale(0.85, 1.7, 0.85);

    const plumbobMat = new THREE.MeshStandardMaterial({
        color: 0x22c55e,
        emissive: 0x16a34a,
        emissiveIntensity: 1.0,
        roughness: 0.15,
        metalness: 0.4
    });

    plumbobMesh = new THREE.Mesh(plumbobGeo, plumbobMat);
    plumbobMesh.position.set(0, 1.95, -0.02);

    plumbobLight = new THREE.PointLight(0x22c55e, 1.2, 3.0);
    plumbobLight.position.set(0, 1.95, -0.02);
    parentGroup.add(plumbobLight);

    parentGroup.add(plumbobMesh);
}

function buildBossDeskItems(parentGroup) {
    // Apple MacBook Pro (Gümüş Alüminyum & Parlayan Ekran)
    const macBase = new THREE.Mesh(new THREE.BoxGeometry(0.48, 0.02, 0.32), new THREE.MeshStandardMaterial({ color: 0xd8e0e8, metalness: 0.85, roughness: 0.2 }));
    macBase.position.set(0, 0.82, 0.45);
    parentGroup.add(macBase);

    const macScreen = new THREE.Mesh(new THREE.BoxGeometry(0.48, 0.32, 0.02), new THREE.MeshStandardMaterial({ color: 0x0f172a, emissive: 0x38bdf8, emissiveIntensity: 0.7 }));
    macScreen.position.set(0, 0.96, 0.31);
    macScreen.rotation.x = -0.25;
    parentGroup.add(macScreen);

    // Altın İsimlik: "👑 PATRON: EFE"
    const canvas = document.createElement('canvas');
    canvas.width = 512;
    canvas.height = 128;
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = '#b45309';
    ctx.fillRect(0, 0, 512, 128);
    ctx.strokeStyle = '#fef08a';
    ctx.lineWidth = 8;
    ctx.strokeRect(6, 6, 500, 116);
    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 44px Inter, sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('👑 PATRON: EFE', 256, 80);

    const plateTex = new THREE.CanvasTexture(canvas);
    const plate = new THREE.Mesh(new THREE.BoxGeometry(0.75, 0.20, 0.10), new THREE.MeshStandardMaterial({ map: plateTex, metalness: 0.75, roughness: 0.25 }));
    plate.position.set(0, 0.88, 0.75);
    plate.rotation.x = -0.28;
    parentGroup.add(plate);

    // Beyaz İtalyan Porselen Espresso Fincanı
    const saucer = new THREE.Mesh(new THREE.CylinderGeometry(0.09, 0.07, 0.015, 16), new THREE.MeshStandardMaterial({ color: 0xffffff }));
    saucer.position.set(0.42, 0.82, 0.48);
    parentGroup.add(saucer);

    const cup = new THREE.Mesh(new THREE.CylinderGeometry(0.055, 0.045, 0.07, 16), new THREE.MeshStandardMaterial({ color: 0xffffff }));
    cup.position.set(0.42, 0.855, 0.48);
    parentGroup.add(cup);
}

// -------------------------------------------------------------
// 5 UZMAN AJAN (HERKESİN KENDİ BİLGİSAYARI & ÇALIŞMA MASASI)
// -------------------------------------------------------------
function buildSpecialistAgents() {
    // 1. SCANNER AGENT (Sol Üst: x = -1.55, z = -0.7, Doğuya/Masaya Bakar)
    createAgentWorkstation({
        id: 'scanner',
        name: 'Scanner Agent',
        seatPos: [-1.55, 0, -0.7],
        seatRotY: Math.PI / 2,
        deskPos: [-0.65, 0.78, -0.7],
        suitColor: 0x1d4ed8, // Siber Mavi
        hairColor: 0x334155,
        screenColor: 0x0284c7, // Cyan Radar
        chartType: 'RADAR 200+ SCAN',
        phrases: [
            "Radar: 200 parite tarandı, piyasada hacim bekliyoruz.",
            "BTC testerede, altcoinlerde acele işlem yok.",
            "Kırılım sinyalleri taranıyor, masadayım."
        ]
    });

    // 2. TA ANALYST (Sol Alt: x = -1.55, z = +0.7, Doğuya/Masaya Bakar)
    createAgentWorkstation({
        id: 'ta',
        name: 'Teknik Analist',
        seatPos: [-1.55, 0, 0.7],
        seatRotY: Math.PI / 2,
        deskPos: [-0.65, 0.78, 0.7],
        suitColor: 0x7e22ce, // Mor / Eflatun
        hairColor: 0x475569,
        hasGlasses: true,
        screenColor: 0x9333ea, // Mor Mum Grafik
        chartType: 'BTC 4S BOLLINGER',
        phrases: [
            "BTC 4s bant daralması %0.40, sıkışma devam ediyor.",
            "EMA20 ve RSI uyumsuzluğu takip ediliyor.",
            "Breakout teyidi gelmeden emir açmıyoruz."
        ]
    });

    // 3. RISK OFFICER (Sağ Üst: x = +1.55, z = -0.7, Batıya/Masaya Bakar)
    createAgentWorkstation({
        id: 'risk',
        name: 'Risk & Kasa Şefi',
        seatPos: [1.55, 0, -0.7],
        seatRotY: -Math.PI / 2,
        deskPos: [0.65, 0.78, -0.7],
        suitColor: 0xb91c1c, // Bordo / Kırmızı
        hairColor: 0x0f172a,
        screenColor: 0xdc2626, // Kırmızı Kalkan
        chartType: '5X LEVERAGE CAP',
        phrases: [
            "Kasa Kalkanı devrede: Maksimum 5x kaldıraç kilitli.",
            "İşlem başına %1.5 sermaye riski tavanı onaylandı.",
            "Teminat oranları güvende, risk kontrol altında."
        ]
    });

    // 4. NEWS & MACRO AGENT (Sağ Alt: x = +1.55, z = +0.7, Batıya/Masaya Bakar)
    createAgentWorkstation({
        id: 'news',
        name: 'Haber & Makro Ajanı',
        seatPos: [1.55, 0, 0.7],
        seatRotY: -Math.PI / 2,
        deskPos: [0.65, 0.78, 0.7],
        suitColor: 0xd97706, // Amber / Turuncu
        hairColor: 0x1e293b,
        screenColor: 0xf59e0b, // Amber Bloomberg Terminal
        chartType: 'MACRO FEED / RATES',
        phrases: [
            "Funding rate stabil, global piyasalarda şok veri yok.",
            "Makro haber akışı sakin, likidite dengeli.",
            "Fed faiz beklentileri ve fonlama oranları normal."
        ]
    });

    // 5. CHIEF ANALYST (Patron Efe'nin Yanı / Masanın Baş Köşesi: x = 1.3, z = -1.9)
    createAgentWorkstation({
        id: 'chief',
        name: 'Baş Stratejist',
        seatPos: [1.3, 0, -1.9],
        seatRotY: -Math.PI / 3.5,
        deskPos: [0.95, 0.78, -1.5],
        suitColor: 0x059669, // Zümrüt Yeşili
        hairColor: 0x18181b,
        screenColor: 0x10b981,
        chartType: 'COMMITTEE MATRIX',
        isStandingByDefault: true,
        phrases: [
            "Efe Bey, piyasa şu an beklemede. Şartlar oluşursa komite onaylayacak.",
            "Tüm ajanlar masada koordineli çalışıyor.",
            "Trend teyidi durumunda hazır bekliyoruz."
        ]
    });
}

// Tek Bir Ajanın Çalışma Masası, Monitörleri ve Karakterini İnşa Eder
function createAgentWorkstation(cfg) {
    const isRightSide = cfg.seatPos[0] > 0;
    const isChief = cfg.id === 'chief';

    // 1. Karakter Grubu (Root)
    const agentGroup = new THREE.Group();
    agentGroup.position.set(...cfg.seatPos);
    agentGroup.rotation.y = cfg.seatRotY;

    // 2. Koltuk (Chief ayakta başlar, diğerleri oturur)
    const chairGroup = new THREE.Group();
    chairGroup.position.set(0, 0, 0);

    const chairSeat = new THREE.Mesh(new THREE.BoxGeometry(0.55, 0.08, 0.55), new THREE.MeshStandardMaterial({ color: 0x1e293b, roughness: 0.6 }));
    chairSeat.position.y = 0.44;
    chairSeat.castShadow = true;
    chairGroup.add(chairSeat);

    const chairBack = new THREE.Mesh(new THREE.BoxGeometry(0.55, 0.65, 0.08), new THREE.MeshStandardMaterial({ color: 0x1e293b, roughness: 0.6 }));
    chairBack.position.set(0, 0.80, -0.27);
    chairGroup.add(chairBack);

    const chairLeg = new THREE.Mesh(new THREE.CylinderGeometry(0.04, 0.04, 0.44, 12), new THREE.MeshStandardMaterial({ color: 0x475569, metalness: 0.8 }));
    chairLeg.position.y = 0.22;
    chairGroup.add(chairLeg);

    agentGroup.add(chairGroup);

    // 3. Karakter Kemikleri & Gövdesi
    const bodyGroup = new THREE.Group();
    bodyGroup.position.y = 0;

    const clothMat = new THREE.MeshStandardMaterial({ color: cfg.suitColor, roughness: 0.45 });
    const skinMat = new THREE.MeshStandardMaterial({ color: 0xfbd0b0, roughness: 0.6 });

    // Bacaklar
    const leftLeg = new THREE.Mesh(new THREE.BoxGeometry(0.14, 0.42, 0.14), clothMat);
    leftLeg.position.set(-0.14, 0.21, 0);
    bodyGroup.add(leftLeg);

    const rightLeg = new THREE.Mesh(new THREE.BoxGeometry(0.14, 0.42, 0.14), clothMat);
    rightLeg.position.set(0.14, 0.21, 0);
    bodyGroup.add(rightLeg);

    // Gövde
    const torso = new THREE.Mesh(new THREE.BoxGeometry(0.48, 0.52, 0.28), clothMat);
    torso.position.y = 0.70;
    torso.castShadow = true;
    bodyGroup.add(torso);

    // Kollar
    const leftArm = new THREE.Mesh(new THREE.BoxGeometry(0.11, 0.40, 0.11), clothMat);
    leftArm.position.set(-0.28, 0.68, 0.12);
    leftArm.rotation.x = Math.PI / 4;
    bodyGroup.add(leftArm);

    const rightArm = new THREE.Mesh(new THREE.BoxGeometry(0.11, 0.40, 0.11), clothMat);
    rightArm.position.set(0.28, 0.68, 0.12);
    rightArm.rotation.x = Math.PI / 4;
    bodyGroup.add(rightArm);

    // Baş & Saç
    const headGroup = new THREE.Group();
    headGroup.position.set(0, 1.10, 0);

    const head = new THREE.Mesh(new THREE.BoxGeometry(0.28, 0.30, 0.26), skinMat);
    head.castShadow = true;
    headGroup.add(head);

    const hair = new THREE.Mesh(new THREE.BoxGeometry(0.30, 0.10, 0.28), new THREE.MeshStandardMaterial({ color: cfg.hairColor, roughness: 0.8 }));
    hair.position.set(0, 0.15, 0);
    headGroup.add(hair);

    if (cfg.hasGlasses) {
        const glasses = new THREE.Mesh(new THREE.BoxGeometry(0.24, 0.05, 0.03), new THREE.MeshStandardMaterial({ color: 0x0284c7, metalness: 0.8 }));
        glasses.position.set(0, 0.02, 0.14);
        headGroup.add(glasses);
    }

    bodyGroup.add(headGroup);
    agentGroup.add(bodyGroup);

    // 4. Masadaki Kendi Bilgisayarı (Herkesin Önündeki Çift Monitör & Klavye)
    buildAgentDeskComputer(cfg);

    // Ajanı Sözlüğe Kaydet
    agents[cfg.id] = {
        id: cfg.id,
        name: cfg.name,
        group: agentGroup,
        bodyGroup: bodyGroup,
        headGroup: headGroup,
        leftLeg: leftLeg,
        rightLeg: rightLeg,
        leftArm: leftArm,
        rightArm: rightArm,
        homePos: new THREE.Vector3(...cfg.seatPos),
        homeRotY: cfg.seatRotY,
        state: isChief ? 'IDLE_STAND' : 'SEATED_WORKING',
        stateTime: 0,
        waypoints: [],
        currentWpIdx: 0,
        phrases: cfg.phrases
    };

    bubbleAnchors[cfg.id].pos = new THREE.Vector3(cfg.seatPos[0], 1.95, cfg.seatPos[2]);

    officeScene.add(agentGroup);
}

// Her Ajanın Önündeki Özel Çift Monitörlü İşlem İstasyonu
function buildAgentDeskComputer(cfg) {
    const isRight = cfg.seatPos[0] > 0;
    const compGroup = new THREE.Group();
    compGroup.position.set(...cfg.deskPos);
    // Monitörlerin yüzü ajana doğru dönük olmalı
    compGroup.rotation.y = isRight ? -Math.PI / 2 : Math.PI / 2;

    const screenMat = new THREE.MeshStandardMaterial({
        color: cfg.screenColor,
        emissive: cfg.screenColor,
        emissiveIntensity: 0.85,
        roughness: 0.2
    });

    // 1. Ana Analiz Ekranı
    const scr1 = new THREE.Mesh(new THREE.BoxGeometry(0.48, 0.30, 0.02), screenMat);
    scr1.position.set(-0.25, 0.24, 0);
    scr1.rotation.y = 0.15;
    compGroup.add(scr1);
    officeDeskScreens.push(scr1);

    // 2. Yan Takip Ekranı (Dikey/Kavisli)
    const scr2 = new THREE.Mesh(new THREE.BoxGeometry(0.44, 0.28, 0.02), screenMat);
    scr2.position.set(0.24, 0.23, 0);
    scr2.rotation.y = -0.18;
    compGroup.add(scr2);
    officeDeskScreens.push(scr2);

    // Metalik Monitör Standı
    const standMat = new THREE.MeshStandardMaterial({ color: 0x334155, metalness: 0.85 });
    const standBar = new THREE.Mesh(new THREE.BoxGeometry(0.70, 0.03, 0.03), standMat);
    standBar.position.set(0, 0.22, -0.05);
    compGroup.add(standBar);

    const standPost = new THREE.Mesh(new THREE.CylinderGeometry(0.025, 0.025, 0.22, 12), standMat);
    standPost.position.set(0, 0.11, -0.05);
    compGroup.add(standPost);

    // Masa Üstü Mekanik Klavye & Mouse Pad
    const pad = new THREE.Mesh(new THREE.BoxGeometry(0.65, 0.005, 0.30), new THREE.MeshStandardMaterial({ color: 0x090e17, roughness: 0.8 }));
    pad.position.set(0, 0.005, 0.24);
    compGroup.add(pad);

    const kb = new THREE.Mesh(new THREE.BoxGeometry(0.40, 0.012, 0.14), new THREE.MeshStandardMaterial({ color: 0x1e293b }));
    kb.position.set(-0.06, 0.015, 0.24);
    compGroup.add(kb);

    const mouse = new THREE.Mesh(new THREE.BoxGeometry(0.06, 0.015, 0.10), new THREE.MeshStandardMaterial({ color: 0x38bdf8, emissive: 0x0284c7, emissiveIntensity: 0.3 }));
    mouse.position.set(0.22, 0.015, 0.24);
    compGroup.add(mouse);

    officeScene.add(compGroup);
}

// -------------------------------------------------------------
// SİMS BALONCUKLARINI DOM ELEMENTLERİNE BAĞLAMA
// -------------------------------------------------------------
function bindBubbleElements() {
    bubbleAnchors.boss.el = document.getElementById('bubble-boss');
    bubbleAnchors.boss.bodyEl = document.getElementById('text-boss');

    bubbleAnchors.scanner.el = document.getElementById('bubble-scanner');
    bubbleAnchors.scanner.bodyEl = document.getElementById('text-scanner');

    bubbleAnchors.ta.el = document.getElementById('bubble-ta');
    bubbleAnchors.ta.bodyEl = document.getElementById('text-ta');

    bubbleAnchors.news.el = document.getElementById('bubble-news');
    bubbleAnchors.news.bodyEl = document.getElementById('text-news');

    bubbleAnchors.risk.el = document.getElementById('bubble-risk');
    bubbleAnchors.risk.bodyEl = document.getElementById('text-risk');

    bubbleAnchors.chief.el = document.getElementById('bubble-chief');
    bubbleAnchors.chief.bodyEl = document.getElementById('text-chief');

    bubbleAnchors.trade.el = document.getElementById('tradeMonitorBubble');

    // Herhangi bir karaktere veya balonuna tıklandığında anında konuşturalım
    Object.keys(bubbleAnchors).forEach(key => {
        const item = bubbleAnchors[key];
        if (item.el) {
            item.el.addEventListener('click', () => {
                if (key === 'boss') {
                    triggerSpeech('boss', "Acele işlem yok! Kriterler net: Sermaye koruma kuralımız #1.");
                    setOfficeCamera('boss');
                } else if (agents[key]) {
                    const phr = agents[key].phrases;
                    const randPhrase = phr[Math.floor(Math.random() * phr.length)];
                    triggerSpeech(key, randPhrase, 5000);
                }
            });
        }
    });
}

// -------------------------------------------------------------
// 3D DÜNYADAN 2D EKRANA BALON YANSITMASI (ŞEFFAF & DİNAMİK)
// -------------------------------------------------------------
function updateBubblePositions() {
    if (!officeRenderer || !officeCamera) return;
    const target = document.getElementById('officeCanvasTarget');
    if (!target) return;
    const rect = target.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) return;

    const isMobile = rect.width < 700;
    const bubbleHalfW = isMobile ? 70 : 100;

    Object.keys(bubbleAnchors).forEach(key => {
        const item = bubbleAnchors[key];
        if (!item || !item.el) return;

        // Trade balonu her zaman görünür, diğer karakterler konuştukça (.speaking sınıfıyla) açılır
        if (key !== 'trade' && !item.isSpeaking) {
            return;
        }

        // Çapa pozisyonu karakterin anlık konumuna göre dinamik takip eder (Yürürken kafasını izler!)
        let worldPos = item.pos;
        if (key !== 'trade' && key !== 'boss' && agents[key]) {
            worldPos = agents[key].group.position.clone();
            worldPos.y += 1.95;
        }

        if (!worldPos) return;

        const p = worldPos.clone();
        p.project(officeCamera);

        if (p.z > 1 || p.z < -1) {
            item.el.style.opacity = '0';
            item.el.style.pointerEvents = 'none';
            return;
        }

        const screenX = (p.x * 0.5 + 0.5) * rect.width;
        const screenY = (-(p.y * 0.5) + 0.5) * rect.height;

        const clampedX = Math.max(bubbleHalfW + 6, Math.min(rect.width - bubbleHalfW - 6, screenX));
        const clampedY = Math.max(isMobile ? 38 : 45, Math.min(rect.height - 10, screenY));

        item.el.style.left = clampedX + 'px';
        item.el.style.top = clampedY + 'px';
    });
}

// -------------------------------------------------------------
// OTONOM OFİS RUTİNİ: KAHVE ALMA, TUVALET, PATRONA RAPOR VERME
// -------------------------------------------------------------
function updateAutonomousOfficeAI(deltaTime, time) {
    // 1. Periyodik Konuşma Döngüsü (Her 8-12 saniyede bir karakter konuşur)
    if (time > nextDialogueTime) {
        nextDialogueTime = time + 8000 + Math.random() * 5000;
        const availableSpeakers = ['boss', 'scanner', 'ta', 'risk', 'news', 'chief'];
        const chosen = availableSpeakers[Math.floor(Math.random() * availableSpeakers.length)];
        if (chosen === 'boss') {
            const bossLines = [
                "Disiplin #1 kuralımız, acele yok beyler.",
                "Piyasayı tarayın, güçlü kırılım görürseniz masaya getirin.",
                "Sermaye kalkanı devrede, gereksiz risk almıyoruz."
            ];
            triggerSpeech('boss', bossLines[Math.floor(Math.random() * bossLines.length)], 5000);
        } else if (agents[chosen]) {
            const phr = agents[chosen].phrases;
            triggerSpeech(chosen, phr[Math.floor(Math.random() * phr.length)], 5000);
        }
    }

    // 2. Otonom Yürüme Eylemi Tetikleyici (Her 16-24 saniyede bir çalışan kalkıp dolaşır)
    if (time > nextAutonomousActionTime) {
        nextAutonomousActionTime = time + 16000 + Math.random() * 10000;
        
        // Sadece şu an oturan çalışanlardan birini seç
        const candidateIds = ['scanner', 'ta', 'risk', 'news'];
        const seatedCandidates = candidateIds.filter(id => agents[id] && agents[id].state === 'SEATED_WORKING');
        
        if (seatedCandidates.length > 0) {
            const walkerId = seatedCandidates[Math.floor(Math.random() * seatedCandidates.length)];
            const walker = agents[walkerId];
            
            // Yapılacak Eylemi Seç: Kahve (0), Tuvalet (1), Patrona Rapor (2)
            const actionType = Math.floor(Math.random() * 3);
            startAgentActivity(walker, actionType);
        }
    }

    // 3. Çalışanların Yürüme ve Kemik Animasyonlarını Güncelle
    Object.keys(agents).forEach(id => {
        updateSingleAgentMovement(agents[id], deltaTime, time);
    });
}

// Bir Ajan İçin Aktivite Başlatır (Waypoints / Koridor Navigasyonu)
function startAgentActivity(ag, actionType) {
    const isLeft = ag.homePos.x < 0;
    const corridorX = isLeft ? -2.4 : 2.4;
    ag.state = 'WALKING';
    ag.currentWpIdx = 0;
    ag.activityType = actionType;

    if (actionType === 0) {
        // ☕ KAHVEYE GİDİŞ: Sandalyeden çık -> Koridora geç -> Ön koridora yürü -> Kahve makinesine yanaş
        ag.waypoints = [
            new THREE.Vector3(corridorX, 0, ag.homePos.z),
            new THREE.Vector3(corridorX, 0, 2.0),
            new THREE.Vector3(4.2, 0, 2.0)
        ];
        ag.destinationPhrase = "☕ Taze bir espresso alayım, piyasa takibi yoğun geçiyor...";
        ag.returnAction = () => { ag.waypoints = [ new THREE.Vector3(corridorX, 0, 2.0), new THREE.Vector3(corridorX, 0, ag.homePos.z), ag.homePos.clone() ]; };
    } else if (actionType === 1) {
        // 🚻 TUVALETE GİDİŞ: Koridora geç -> WC kapısına yanaş
        ag.waypoints = [
            new THREE.Vector3(corridorX, 0, ag.homePos.z),
            new THREE.Vector3(corridorX, 0, 2.0),
            new THREE.Vector3(-4.2, 0, 2.0)
        ];
        ag.destinationPhrase = "🚻 Kısa bir ihtiyaç molası...";
        ag.returnAction = () => { ag.waypoints = [ new THREE.Vector3(corridorX, 0, 2.0), new THREE.Vector3(corridorX, 0, ag.homePos.z), ag.homePos.clone() ]; };
    } else {
        // 👑 PATRONA RAPOR GÖTÜRME: Koridora geç -> Patronun masasının sağına yürü
        ag.waypoints = [
            new THREE.Vector3(corridorX, 0, ag.homePos.z),
            new THREE.Vector3(corridorX, 0, -2.0),
            new THREE.Vector3(isLeft ? -1.1 : 1.1, 0, -2.0)
        ];
        ag.destinationPhrase = "Efe Bey, son piyasa ve tarama özetini getirdim.";
        ag.returnAction = () => { ag.waypoints = [ new THREE.Vector3(corridorX, 0, -2.0), new THREE.Vector3(corridorX, 0, ag.homePos.z), ag.homePos.clone() ]; };
    }
}

// Tek Bir Ajanın Adım Adım Yürümesini ve Kemiklerini Hareket Ettirir
function updateSingleAgentMovement(ag, deltaTime, time) {
    if (ag.state === 'SEATED_WORKING') {
        // Otururken hafif nefes alma ve klavyede yazma hareketi
        ag.leftArm.rotation.x = Math.PI / 3.5 + Math.sin(time * 0.005) * 0.05;
        ag.rightArm.rotation.x = Math.PI / 3.5 + Math.cos(time * 0.005) * 0.05;
        ag.leftLeg.rotation.x = 0;
        ag.rightLeg.rotation.x = 0;
        ag.bodyGroup.position.y = 0;
        return;
    }

    if (ag.state === 'WALKING') {
        if (ag.currentWpIdx >= ag.waypoints.length) {
            // Hedefe ulaşıldı!
            ag.state = 'AT_DESTINATION';
            ag.destinationTimer = Date.now() + 4500;
            triggerSpeech(ag.id, ag.destinationPhrase, 4000);

            if (ag.activityType === 0) {
                playOfficeSound('coffee');
            } else if (ag.activityType === 1) {
                // WC meşgul ışığını turuncu yap
                if (wcSignLight) wcSignLight.color.setHex(0xf59e0b);
            } else if (ag.activityType === 2) {
                // Patron Efe başını sallar ve yanıt verir
                setTimeout(() => {
                    triggerSpeech('boss', "Güzel rapor, temkinli kalıp devam ediyoruz.", 4000);
                }, 1500);
            }
            return;
        }

        const targetWp = ag.waypoints[ag.currentWpIdx];
        const currentPos = ag.group.position;
        const dir = new THREE.Vector3().subVectors(targetWp, currentPos);
        const dist = dir.length();

        if (dist < 0.1) {
            ag.currentWpIdx++;
        } else {
            dir.normalize();
            // Yürüme hızı: saniyede 1.8 birim
            const step = Math.min(dist, 1.8 * deltaTime);
            currentPos.addScaledVector(dir, step);

            // Gittiği yöne doğru yumuşakça dön
            const targetAngle = Math.atan2(dir.x, dir.z);
            ag.group.rotation.y = THREE.MathUtils.lerp(ag.group.rotation.y, targetAngle, 0.15);

            // Sims Yürüme Animasyonu: Bacak ve kol salınımı
            const walkCycle = time * 0.01;
            ag.leftLeg.rotation.x = Math.sin(walkCycle) * 0.45;
            ag.rightLeg.rotation.x = -Math.sin(walkCycle) * 0.45;
            ag.leftArm.rotation.x = -Math.sin(walkCycle) * 0.35;
            ag.rightArm.rotation.x = Math.sin(walkCycle) * 0.35;
            ag.bodyGroup.position.y = Math.abs(Math.sin(walkCycle * 2)) * 0.04; // Adım atarken hafif zıplama
        }
    } else if (ag.state === 'AT_DESTINATION') {
        // Hedefte bekleme süresi bittiğinde geri masaya dönüş yolunu başlat
        if (Date.now() > ag.destinationTimer) {
            if (ag.activityType === 1 && wcSignLight) {
                // WC ışığını tekrar yeşil yap
                wcSignLight.color.setHex(0x10b981);
            }
            ag.state = 'WALKING_BACK';
            ag.returnAction();
            ag.currentWpIdx = 0;
        }
    } else if (ag.state === 'WALKING_BACK') {
        if (ag.currentWpIdx >= ag.waypoints.length) {
            // Masaya geri oturdu!
            ag.state = 'SEATED_WORKING';
            ag.group.position.copy(ag.homePos);
            ag.group.rotation.y = ag.homeRotY;
            ag.leftLeg.rotation.x = 0;
            ag.rightLeg.rotation.x = 0;
            ag.bodyGroup.position.y = 0;
        } else {
            const targetWp = ag.waypoints[ag.currentWpIdx];
            const currentPos = ag.group.position;
            const dir = new THREE.Vector3().subVectors(targetWp, currentPos);
            const dist = dir.length();

            if (dist < 0.1) {
                ag.currentWpIdx++;
            } else {
                dir.normalize();
                const step = Math.min(dist, 1.8 * deltaTime);
                currentPos.addScaledVector(dir, step);

                const targetAngle = Math.atan2(dir.x, dir.z);
                ag.group.rotation.y = THREE.MathUtils.lerp(ag.group.rotation.y, targetAngle, 0.15);

                const walkCycle = time * 0.01;
                ag.leftLeg.rotation.x = Math.sin(walkCycle) * 0.45;
                ag.rightLeg.rotation.x = -Math.sin(walkCycle) * 0.45;
                ag.leftArm.rotation.x = -Math.sin(walkCycle) * 0.35;
                ag.rightArm.rotation.x = Math.sin(walkCycle) * 0.35;
                ag.bodyGroup.position.y = Math.abs(Math.sin(walkCycle * 2)) * 0.04;
            }
        }
    }
}

// -------------------------------------------------------------
// KAMERA KONTROLLERİ (PRESETS)
// -------------------------------------------------------------
function setOfficeCamera(mode = 'boss') {
    ['btnCamBoss', 'btnCamTable', 'btnCamIso'].forEach(id => {
        const btn = document.getElementById(id);
        if (btn) btn.classList.remove('active');
    });

    const isPortrait = (window.innerWidth / window.innerHeight) < 1.0;

    if (mode === 'boss') {
        const btn = document.getElementById('btnCamBoss');
        if (btn) btn.classList.add('active');
        camTargetPos = new THREE.Vector3(0, 2.3, isPortrait ? 0.3 : -0.4);
        camLookTarget = new THREE.Vector3(0, 1.5, -2.4);
        playOfficeSound('chime');
    } else if (mode === 'table') {
        const btn = document.getElementById('btnCamTable');
        if (btn) btn.classList.add('active');
        camTargetPos = new THREE.Vector3(0, isPortrait ? 4.8 : 4.2, isPortrait ? 5.6 : 4.4);
        camLookTarget = new THREE.Vector3(0, 1.1, 0);
        playOfficeSound('click');
    } else if (mode === 'iso') {
        const btn = document.getElementById('btnCamIso');
        if (btn) btn.classList.add('active');
        camTargetPos = new THREE.Vector3(isPortrait ? 8.6 : 7.2, isPortrait ? 9.2 : 7.8, isPortrait ? 9.6 : 8.2);
        camLookTarget = new THREE.Vector3(0, 1.0, 0);
        playOfficeSound('click');
    }
}

// -------------------------------------------------------------
// ANİMASYON DÖNGÜSÜ (RENDER LOOP)
// -------------------------------------------------------------
let lastFrameTime = 0;

function animateOffice(time) {
    officeAnimFrameId = requestAnimationFrame(animateOffice);

    const deltaTime = lastFrameTime ? Math.min((time - lastFrameTime) / 1000, 0.1) : 0.016;
    lastFrameTime = time;

    // 1. Dönen Sims Plumbob'u
    if (plumbobMesh) {
        plumbobMesh.rotation.y += 0.025;
        const bobY = 1.95 + Math.sin(time * 0.003) * 0.06;
        plumbobMesh.position.y = bobY;
        if (plumbobLight) plumbobLight.position.y = bobY;
    }

    // 2. Patron Efe'nin Hafif Kafa Hareketi
    if (bossHeadMesh) {
        bossHeadMesh.rotation.x = Math.sin(time * 0.0018) * 0.04;
        bossHeadMesh.rotation.y = Math.sin(time * 0.001) * 0.08;
    }

    // 3. Yaşayan Ofis Otonom Yapay Zekası (Yürüme, Kahve Alma, Tuvalet)
    updateAutonomousOfficeAI(deltaTime, time);

    // 4. Yumuşak Kamera Geçişi
    if (camTargetPos && officeCamera) {
        officeCamera.position.lerp(camTargetPos, 0.05);
        if (camLookTarget && camCurrentLook) {
            camCurrentLook.lerp(camLookTarget, 0.05);
            if (officeControls) {
                officeControls.target.copy(camCurrentLook);
            } else {
                officeCamera.lookAt(camCurrentLook);
            }
        }
        if (officeCamera.position.distanceTo(camTargetPos) < 0.02) {
            camTargetPos = null;
        }
    }

    // 5. Controls
    if (officeControls) {
        officeControls.update();
    }

    // 6. Baloncukları Yansıt
    updateBubblePositions();

    // 7. Render
    if (officeRenderer && officeScene && officeCamera) {
        officeRenderer.render(officeScene, officeCamera);
    }
}

// -------------------------------------------------------------
// CANLI VERİ ENTEGRASYONU (API/DATA)
// -------------------------------------------------------------
function updateOffice3DData(data) {
    if (!data) return;

    const btc = data.btc_regime || {};
    const positions = data.active_positions || [];
    const logs = data.scanner_logs || [];
    const statusPill = document.getElementById('officeStatusPill');

    // 1. Bilgisayar Ekranı Canlı İşlem Baloncuğu & Ekran Işıkları
    const tradeBubble = bubbleAnchors.trade.el;
    if (positions.length > 0) {
        const pos = positions[0];
        const pnl = Number(pos.unrealized_pnl_pct || 0);
        const isProfit = pnl >= 0;
        const pnlText = (isProfit ? '+' : '') + pnl.toFixed(2) + '%';
        const sym = pos.symbol || 'POZİSYON';
        const dir = pos.direction || 'LONG';

        if (tradeBubble) {
            tradeBubble.className = 'sims-trade-bubble ' + (isProfit ? 'profit' : 'loss');
            tradeBubble.innerHTML = `
                <div style="font-weight: 800; font-size: 11px;">
                    ${isProfit ? '🟢' : '🔴'} ${sym} ${dir} ${pnlText}
                </div>
                <div style="font-size: 9px; opacity: 0.85; margin-top: 2px;">
                    Fiyat: $${Number(pos.live_price || 0).toLocaleString()} | ${pos.elapsed_str || ''}
                </div>
            `;
        }

        const glowColor = isProfit ? 0x10b981 : 0xef4444;
        officeDeskScreens.forEach(scr => {
            if (scr.material) {
                scr.material.emissive.setHex(glowColor);
                scr.material.emissiveIntensity = 1.0;
            }
        });
        if (officeDeskLight) {
            officeDeskLight.color.setHex(glowColor);
            officeDeskLight.intensity = 1.8;
        }

        if (statusPill) {
            statusPill.innerHTML = `⚡ <strong>CANLI İŞLEM:</strong> ${sym} (${pnlText})`;
            statusPill.style.color = isProfit ? '#10b981' : '#ef4444';
        }
    } else {
        if (tradeBubble) {
            tradeBubble.className = 'sims-trade-bubble idle';
            tradeBubble.innerHTML = `💤 AKTİF İŞLEM YOK (200 Parite Radarda)`;
        }
        officeDeskScreens.forEach(scr => {
            if (scr.material) {
                scr.material.emissive.setHex(0x0284c7);
                scr.material.emissiveIntensity = 0.7;
            }
        });
        if (officeDeskLight) {
            officeDeskLight.color.setHex(0x38bdf8);
            officeDeskLight.intensity = 1.2;
        }
        if (statusPill) {
            statusPill.innerHTML = `👑 Efe Masada | Piyasayı Gözlüyor`;
            statusPill.style.color = '#94a3b8';
        }
    }

    // 2. Canlı Rejime Göre Patron Efe ve Ajanların Cümlelerini Güncelle
    if (bubbleAnchors.boss.bodyEl) {
        if (positions.length > 0) {
            bubbleAnchors.boss.bodyEl.innerText = "İşlem açık beyler! Hedeflere sadık kalın, stop seviyesini koruyun.";
        } else if (btc.status === 'DEAD_CHOP') {
            bubbleAnchors.boss.bodyEl.innerText = "Piyasada ölü testere var. Acele işlem yok, sermaye koruma kuralımız #1!";
        } else if (btc.status === 'BULLISH') {
            bubbleAnchors.boss.bodyEl.innerText = "BTC yukarı yönlü kırılımda. En güçlü pariteyi önüme getirin!";
        } else if (btc.status === 'DUMP_ALERT') {
            bubbleAnchors.boss.bodyEl.innerText = "Sert düşüş alarmı! Risk Şefi, kaldıraçları ve teminatı kilitle.";
        }
    }

    if (bubbleAnchors.scanner.bodyEl && logs.length > 0) {
        const lastLog = logs[0];
        bubbleAnchors.scanner.bodyEl.innerText = `Radar: ${lastLog.symbol || 'PARİTE'} incelendi [${lastLog.status || 'OK'}].`;
    }

    if (bubbleAnchors.ta.bodyEl) {
        const range = btc.range_pct !== undefined ? btc.range_pct : '0.40';
        bubbleAnchors.ta.bodyEl.innerText = `BTC 4s bant daralması: %${range}. EMA & Bollinger sıkışmasını gözlüyorum.`;
    }

    if (wallCanvasCtx && wallCanvasTexture && btc.btc_price) {
        wallCanvasCtx.fillStyle = '#060a12';
        wallCanvasCtx.fillRect(0, 0, 512, 128);
        wallCanvasCtx.fillStyle = '#f59e0b';
        wallCanvasCtx.font = 'bold 24px monospace';
        wallCanvasCtx.fillText(`⚡ BTC: $${Number(btc.btc_price).toLocaleString()} [${btc.status || 'OK'}]`, 20, 45);
        wallCanvasCtx.fillStyle = positions.length > 0 ? '#10b981' : '#38bdf8';
        wallCanvasCtx.font = '18px monospace';
        wallCanvasCtx.fillText(positions.length > 0 ? `AKTİF POZİSYON: ${positions[0].symbol}` : `SERMAYE KORUMA MODU | PATRON: EFE`, 20, 85);
        wallCanvasTexture.needsUpdate = true;
    }
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
