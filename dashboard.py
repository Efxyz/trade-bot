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

        .sims-bubble.friend-mehmet {
            border-color: rgba(45, 212, 191, 0.65) !important;
            box-shadow: 0 0 20px rgba(45, 212, 191, 0.3) !important;
            background: rgba(8, 28, 26, 0.68) !important;
        }
        .sims-bubble.friend-mehmet::after {
            border-top-color: rgba(45, 212, 191, 0.75);
        }

        .sims-bubble.friend-berat {
            border-color: rgba(96, 165, 250, 0.65) !important;
            box-shadow: 0 0 20px rgba(96, 165, 250, 0.3) !important;
            background: rgba(12, 22, 38, 0.68) !important;
        }
        .sims-bubble.friend-berat::after {
            border-top-color: rgba(96, 165, 250, 0.75);
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
                    <!-- Mehmet Bubble (Arkadaş) -->
                    <div id="bubble-mehmet" class="sims-bubble friend-mehmet" onclick="setOfficeCamera('chill')" title="Tıkla: Mehmet Konuşsun">
                        <div class="sims-bubble-header" style="color: #2dd4bf;">🏓 MEHMET (ARKADAŞ)</div>
                        <div class="sims-bubble-body" id="text-mehmet">Berat çay koysana kanka ya, semaver kaynıyor!</div>
                    </div>
                    <!-- Berat Bubble (Arkadaş) -->
                    <div id="bubble-berat" class="sims-bubble friend-berat" onclick="setOfficeCamera('chill')" title="Tıkla: Berat Konuşsun">
                        <div class="sims-bubble-header" style="color: #60a5fa;">⚽ BERAT (ARKADAŞ)</div>
                        <div class="sims-bubble-body" id="text-berat">Mehmet masa tenisinde dün şansın yaver gitti, gel rövanşa!</div>
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
                        <button class="office-hud-btn" id="btnCamChill" onclick="setOfficeCamera('chill')" title="Mehmet & Berat Oyun & Çay Alanı">🏓 Oyun & Çay</button>
                        <button class="office-hud-btn" id="btnToggleBubbles" onclick="cycleBubbleMode()" title="Baloncuk Görünümünü Değiştir (Akıllı/Tümü/Patron/Gizli)">💬 Balon</button>
                        <button class="office-hud-btn" id="btnOfficeFs" onclick="toggleOfficeFullscreen()" title="Tam Ekran Modu">⛶ Tam Ekran</button>
                        <button class="office-hud-btn" id="btnConfetti" onclick="triggerOfficeConfetti()" title="Kutlama & Konfeti Patlat">🎉 Konfeti</button>
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
   🎮 3D SİMS TARZI YAPAY ZEKA TİCARET OFİSİ (THREE.JS ENGINE) - v5.0.0
   Mükemmel Yaşayan Ofis Deneyimi:
   1. Masa Işık & Shader Bug'ı Çözüldü: Parlama/glare ve gölge çizgileri sıfırlandı.
   2. Monitörler Tam Çalışanlara Bakıyor: Kavisli ekranlar elemana dönük, optik mouse'lar eklendi.
   3. Sandalye Çevirme & Masadan Dolaşma: Sandalye arkaya döner, kalkar, masanın etrafından koridordan dolaşır.
   4. Kanepede Oturma: Dinlenme alanına giden eleman kanepeye oturur, çayını içer, sonra döner.
   5. Sırayla Konuşma: Kimse kimsenin üstüne konuşmaz, sıra sistemiyle tek tek şeffaf balonlar açılır.
   6. Konfeti Kutlaması: Kârlı işlemde veya butona basıldığında masaya renkli konfetiler patlar.
   7. Dört Tarafı Kapalı Lüks Oda: Dört duvarlı, tavan spotlu, giriş kapılı penthouse ofis.
   8. Mehmet & Berat: Masa tenisi, langırt, çay, sıfır iş, tam goygoy ve espriler.
   ========================================================================== */

let officeScene, officeCamera, officeRenderer, officeControls;
let officeInitialized = false;
let officeAnimFrameId = null;

// Karakterler ve Mobilya Referansları
let plumbobMesh = null;
let plumbobLight = null;
let bossGroup = null;
let bossHeadMesh = null;
let bossLeftArm = null;
let bossRightArm = null;
let portableWcLight = null;

// Arkadaşlar (Mehmet & Berat)
const friends = {};

// Uzman Ajanlar Sözlüğü (Scanner, TA, Risk, News, Chief)
const agents = {};

// Masa Monitörleri ve Ekranlar
let officeDeskScreens = [];
let bigWallTexture = null;
let bigWallCtx = null;
let bigWallScreenMesh = null;

// Konfeti Parçacık Sistemi
let confettiParticles = [];
let confettiActive = false;

// Sırayla Konuşma Yönetimi (Single Speaker Lock)
let activeSpeakerId = null;
let speechUnlockTimer = null;

// Otonom Eylem Sırası (Sadece 1 Eleman Aynı Anda Gezer - Çarpışma Önleyici)
let isAnyAgentWalking = false;

// Kamera Hedefleri
let camTargetPos = null;
let camLookTarget = null;
let camCurrentLook = null;

// Baloncuk Görünüm Modu & Zamanlayıcılar
let currentBubbleMode = window.innerWidth < 768 ? 'smart' : 'all';
let nextAutonomousActionTime = 5000;
let nextDialogueTime = 3000;
let nextFriendsGameTime = 6000;

// Karakter Balon Çapaları
const bubbleAnchors = {
    boss: { pos: null, el: null, bodyEl: null, isSpeaking: false },
    scanner: { pos: null, el: null, bodyEl: null, isSpeaking: false },
    ta: { pos: null, el: null, bodyEl: null, isSpeaking: false },
    news: { pos: null, el: null, bodyEl: null, isSpeaking: false },
    risk: { pos: null, el: null, bodyEl: null, isSpeaking: false },
    chief: { pos: null, el: null, bodyEl: null, isSpeaking: false },
    mehmet: { pos: null, el: null, bodyEl: null, isSpeaking: false },
    berat: { pos: null, el: null, bodyEl: null, isSpeaking: false },
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
            osc.type = 'sine';
            const f1 = 280 + Math.random() * 260;
            osc.frequency.setValueAtTime(f1, now);
            osc.frequency.linearRampToValueAtTime(f1 * 1.35, now + 0.06);
            gain.gain.setValueAtTime(0.04, now);
            gain.gain.exponentialRampToValueAtTime(0.001, now + 0.12);
            osc.start(now);
            osc.stop(now + 0.12);
        } else if (type === 'pingpong') {
            osc.type = 'sine';
            osc.frequency.setValueAtTime(800 + Math.random() * 300, now);
            osc.frequency.exponentialRampToValueAtTime(300, now + 0.05);
            gain.gain.setValueAtTime(0.05, now);
            gain.gain.exponentialRampToValueAtTime(0.001, now + 0.05);
            osc.start(now);
            osc.stop(now + 0.05);
        } else if (type === 'tea') {
            osc.type = 'sine';
            osc.frequency.setValueAtTime(1500, now);
            osc.frequency.exponentialRampToValueAtTime(900, now + 0.08);
            gain.gain.setValueAtTime(0.05, now);
            gain.gain.exponentialRampToValueAtTime(0.001, now + 0.09);
            osc.start(now);
            osc.stop(now + 0.09);
        } else if (type === 'confetti') {
            // Konfeti patlama sesi (Pop + Fanfare)
            osc.type = 'triangle';
            osc.frequency.setValueAtTime(220, now);
            osc.frequency.exponentialRampToValueAtTime(880, now + 0.08);
            osc.frequency.exponentialRampToValueAtTime(1760, now + 0.20);
            gain.gain.setValueAtTime(0.12, now);
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
// SIRAYLA KONUŞMA SİSTEMİ (BİRİ KONUŞURKEN DİĞERLERİ SUSAR)
// -------------------------------------------------------------
function triggerSpeech(charId, text, durationMs = 5000) {
    if (currentBubbleMode === 'off') return;
    if (currentBubbleMode === 'boss' && charId !== 'boss' && charId !== 'trade') return;

    // Eğer şu an biri konuşuyorsa ve bu acil Patron değilse bekle (sıra kuralı)
    if (activeSpeakerId !== null && activeSpeakerId !== charId && charId !== 'boss') {
        return;
    }

    // Önceki konuşan varsa kapat
    if (activeSpeakerId && activeSpeakerId !== charId && bubbleAnchors[activeSpeakerId]) {
        bubbleAnchors[activeSpeakerId].isSpeaking = false;
        if (bubbleAnchors[activeSpeakerId].el) {
            bubbleAnchors[activeSpeakerId].el.classList.remove('speaking');
        }
    }

    const anchor = bubbleAnchors[charId];
    if (!anchor || !anchor.el) return;

    if (anchor.bodyEl && text) {
        anchor.bodyEl.innerText = text;
    }

    activeSpeakerId = charId;
    anchor.isSpeaking = true;
    anchor.el.classList.add('speaking');
    playOfficeSound('talk');

    if (speechUnlockTimer) {
        clearTimeout(speechUnlockTimer);
    }

    speechUnlockTimer = setTimeout(() => {
        anchor.isSpeaking = false;
        if (anchor.el) anchor.el.classList.remove('speaking');
        activeSpeakerId = null;
    }, durationMs);
}

// -------------------------------------------------------------
// 🎉 KONFETİ PATLATMA SİSTEMİ (KÂRLI İŞLEM KUTLAMASI)
// -------------------------------------------------------------
function triggerOfficeConfetti() {
    playOfficeSound('confetti');

    // Patron Efe kollarını kaldırıp kutlar
    if (bossLeftArm && bossRightArm) {
        bossLeftArm.rotation.x = Math.PI * 0.9;
        bossRightArm.rotation.x = Math.PI * 0.9;
        setTimeout(() => {
            if (bossLeftArm && bossRightArm) {
                bossLeftArm.rotation.x = Math.PI / 3.2;
                bossRightArm.rotation.x = Math.PI / 3.2;
            }
        }, 3500);
    }

    triggerSpeech('boss', "🎉 Hedef Vuruldu! Kâr Kasada! Harika disiplin beyler!", 5000);

    // 120 adet renkli konfeti parçası üret
    const colors = [0x10b981, 0xf59e0b, 0x38bdf8, 0xec4899, 0xa855f7, 0xfacc15];
    const confettiGeo = new THREE.BoxGeometry(0.08, 0.08, 0.005);

    for (let i = 0; i < 120; i++) {
        const mat = new THREE.MeshBasicMaterial({ color: colors[Math.floor(Math.random() * colors.length)], side: THREE.DoubleSide });
        const mesh = new THREE.Mesh(confettiGeo, mat);

        // Masanın merkezinden yukarı doğru patlama başlangıcı
        mesh.position.set(
            (Math.random() - 0.5) * 2.0,
            2.2 + Math.random() * 0.8,
            (Math.random() - 0.5) * 3.0
        );

        mesh.rotation.set(Math.random() * Math.PI, Math.random() * Math.PI, Math.random() * Math.PI);

        confettiParticles.push({
            mesh: mesh,
            velocity: new THREE.Vector3(
                (Math.random() - 0.5) * 3.5,
                3.5 + Math.random() * 3.0,
                (Math.random() - 0.5) * 3.5
            ),
            rotSpeed: new THREE.Vector3(
                (Math.random() - 0.5) * 8,
                (Math.random() - 0.5) * 8,
                (Math.random() - 0.5) * 8
            ),
            life: 1.0
        });

        officeScene.add(mesh);
    }

    confettiActive = true;
}

function updateConfetti(deltaTime) {
    if (!confettiActive || confettiParticles.length === 0) return;

    for (let i = confettiParticles.length - 1; i >= 0; i--) {
        const p = confettiParticles[i];
        p.velocity.y -= 7.5 * deltaTime; // Yerçekimi
        p.mesh.position.addScaledVector(p.velocity, deltaTime);
        p.mesh.rotation.x += p.rotSpeed.x * deltaTime;
        p.mesh.rotation.y += p.rotSpeed.y * deltaTime;
        p.life -= deltaTime * 0.35;

        // Yere indiğinde veya süresi bittiğinde sil
        if (p.mesh.position.y <= 0.82 || p.life <= 0) {
            officeScene.remove(p.mesh);
            p.mesh.geometry.dispose();
            p.mesh.material.dispose();
            confettiParticles.splice(i, 1);
        }
    }

    if (confettiParticles.length === 0) {
        confettiActive = false;
    }
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
    officeScene.background = new THREE.Color(0x0c111d);
    officeScene.fog = new THREE.FogExp2(0x0c111d, 0.018);

    // 2. Kamera
    const initialFov = aspect < 1.0 ? Math.min(65, 45 / Math.max(0.68, aspect)) : 45;
    officeCamera = new THREE.PerspectiveCamera(initialFov, aspect, 0.1, 100);
    const isMobile = aspect < 1.0 || width < 768;
    officeCamera.position.set(0, isMobile ? 5.8 : 5.2, isMobile ? 8.8 : 7.8);
    camCurrentLook = new THREE.Vector3(0, 1.2, 0);
    officeCamera.lookAt(camCurrentLook);

    // 3. Renderer
    officeRenderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "high-performance" });
    officeRenderer.setSize(width, height);
    officeRenderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2.5));
    // Gölge çizgilerini önlemek için yumuşak filtre
    officeRenderer.shadowMap.enabled = false; // Masa striped shader bug'ını kökten bitirir!
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

    // 5. Işıklandırma (Masa Parlama Bug'ı Sıfırlandı, Müze Kalitesinde Yumuşak Işık)
    setupSoftOfficeLighting();

    // 6. DÖRT TARAFI KAPALI ODA MİMARİSİ (Akustik Ahşap Duvarlar, Tavan, Ön Giriş Kapısı)
    buildEnclosedFourWallOffice();

    // 7. TRADING MASASI (Gözü almayan mat koyu füme ahşap kaplama)
    buildTradingDesk();

    // 8. 👑 BAŞ KOLTUK / PATRON: EFE
    buildBossEfe();

    // 9. EFE'NİN ARKASINDAKİ DEV İKİLİ EKRAN (BTC Grafiği + Canlı Kâr/Zarar)
    buildGiantWallDualScreen();

    // 10. 5 UZMAN AJAN (Yüze Bakan Kavisli Monitörler, Mouse'lar, Dönen Sandalye Animasyonu)
    buildSpecialistAgents();

    // 11. 🏓 ⚽ PATRONUN ARKADAŞLARI: MEHMET & BERAT
    buildFriendsMehmetAndBerat();

    // 12. Çapa Noktalarını DOM Elementlerine Bağla
    bindBubbleElements();

    officeInitialized = true;

    setOfficeCamera('boss');

    setTimeout(() => {
        triggerSpeech('boss', "Piyasayı tarayın beyler, acele yok! Disiplin #1 kuralımız.", 6000);
    }, 1200);

    setTimeout(() => {
        triggerSpeech('mehmet', "Berat çay koysana kanka ya, semaver kaynıyor!", 5000);
    }, 3500);

    if (!officeAnimFrameId) {
        animateOffice(0);
    }

    window.addEventListener('resize', resizeOffice3D);
    window.addEventListener('orientationchange', () => {
        setTimeout(resizeOffice3D, 100);
    });
}

// -------------------------------------------------------------
// IŞIKLANDIRMA SİSTEMİ (PARLAMA & SHADER ÇİZGİLERİ SIFIRLANDI)
// -------------------------------------------------------------
function setupSoftOfficeLighting() {
    // 1. Doğal, yumuşak, gözü almayan ofis ortam ışığı
    const ambientLight = new THREE.AmbientLight(0xdce5f5, 0.90);
    officeScene.add(ambientLight);

    // 2. Tavan yönlü difüze ışık (Gölgeler kapatıldı, şerit çizgiler bitti)
    const ceilingLight = new THREE.DirectionalLight(0xfff8ee, 0.50);
    ceilingLight.position.set(2, 8, 3);
    officeScene.add(ceilingLight);

    // 3. Efe'nin arkasındaki duvara yumuşak aydınlatma
    const backWallGlow = new THREE.PointLight(0x38bdf8, 0.6, 10);
    backWallGlow.position.set(0, 5.0, -5.8);
    officeScene.add(backWallGlow);

    // 4. Oyun ve Çay Alanı Işıkları
    const gameSpot = new THREE.PointLight(0x38bdf8, 0.7, 8);
    gameSpot.position.set(6.2, 4.0, 0);
    officeScene.add(gameSpot);

    const teaSpot = new THREE.PointLight(0xf59e0b, 0.7, 8);
    teaSpot.position.set(-6.2, 3.8, 0);
    officeScene.add(teaSpot);
}

// -------------------------------------------------------------
// DÖRT TARAFI KAPALI LÜKS OFİS ODASI
// -------------------------------------------------------------
function buildEnclosedFourWallOffice() {
    // 1. Zemin (Lüks Koyu Parke)
    const floorGeo = new THREE.PlaneGeometry(22, 18);
    const floorMat = new THREE.MeshLambertMaterial({ color: 0x121724 });
    const floor = new THREE.Mesh(floorGeo, floorMat);
    floor.rotation.x = -Math.PI / 2;
    officeScene.add(floor);

    // 2. Halı
    const rugGeo = new THREE.PlaneGeometry(12.5, 9.0);
    const rugMat = new THREE.MeshLambertMaterial({ color: 0x0a0f1c });
    const rug = new THREE.Mesh(rugGeo, rugMat);
    rug.rotation.x = -Math.PI / 2;
    rug.position.set(0, 0.015, 0);
    officeScene.add(rug);

    // 3. ARKA DUVAR (z = -6.2, Akustik Ahşap Çıtalar)
    const backWall = new THREE.Mesh(new THREE.BoxGeometry(22, 7.5, 0.2), new THREE.MeshLambertMaterial({ color: 0x0f1422 }));
    backWall.position.set(0, 3.75, -6.2);
    officeScene.add(backWall);

    const slatMat = new THREE.MeshLambertMaterial({ color: 0x2e2017 });
    for (let x = -10.5; x <= 10.5; x += 0.5) {
        if (x > -3.6 && x < 3.6) continue; // Dev ekranın arkası
        const slat = new THREE.Mesh(new THREE.BoxGeometry(0.12, 7.2, 0.05), slatMat);
        slat.position.set(x, 3.75, -6.08);
        officeScene.add(slat);
    }

    // 4. SOL DUVAR (x = -11.0, Çay Köşesi ve Dinlenme Bölgesi)
    const leftWall = new THREE.Mesh(new THREE.BoxGeometry(0.2, 7.5, 18), new THREE.MeshLambertMaterial({ color: 0x111624 }));
    leftWall.position.set(-11.0, 3.75, 0);
    officeScene.add(leftWall);

    // 5. SAĞ DUVAR (x = 11.0, Oyun Alanı Tarafı)
    const rightWall = new THREE.Mesh(new THREE.BoxGeometry(0.2, 7.5, 18), new THREE.MeshLambertMaterial({ color: 0x111624 }));
    rightWall.position.set(11.0, 3.75, 0);
    officeScene.add(rightWall);

    // 6. ÖN DUVAR (z = 6.2, Giriş Kapılı Ön Cephe)
    const frontWallLeft = new THREE.Mesh(new THREE.BoxGeometry(9.0, 7.5, 0.2), new THREE.MeshLambertMaterial({ color: 0x0f1422 }));
    frontWallLeft.position.set(-6.5, 3.75, 6.2);
    officeScene.add(frontWallLeft);

    const frontWallRight = new THREE.Mesh(new THREE.BoxGeometry(9.0, 7.5, 0.2), new THREE.MeshLambertMaterial({ color: 0x0f1422 }));
    frontWallRight.position.set(6.5, 3.75, 6.2);
    officeScene.add(frontWallRight);

    // Ön Giriş Çift Cam Kapı
    const doorGlass = new THREE.Mesh(new THREE.BoxGeometry(3.8, 4.0, 0.05), new THREE.MeshPhysicalMaterial({ color: 0x38bdf8, transparent: true, opacity: 0.35, roughness: 0.2 }));
    doorGlass.position.set(0, 2.0, 6.2);
    officeScene.add(doorGlass);

    // Kapı Üstü Ön Duvar Parçası
    const doorTopWall = new THREE.Mesh(new THREE.BoxGeometry(4.0, 3.5, 0.2), new THREE.MeshLambertMaterial({ color: 0x0f1422 }));
    doorTopWall.position.set(0, 5.75, 6.2);
    officeScene.add(doorTopWall);

    // 7. TAVAN (Gömme LED Işık Şeritleri)
    const ceiling = new THREE.Mesh(new THREE.PlaneGeometry(22, 18), new THREE.MeshLambertMaterial({ color: 0x0a0e18 }));
    ceiling.rotation.x = Math.PI / 2;
    ceiling.position.set(0, 7.5, 0);
    officeScene.add(ceiling);

    // Tavan LED Işık Kareleri
    const ledMat = new THREE.MeshBasicMaterial({ color: 0xfff8ee });
    [[-4, -2], [4, -2], [-4, 2], [4, 2], [0, 0]].forEach(([lx, lz]) => {
        const ledMesh = new THREE.Mesh(new THREE.PlaneGeometry(1.6, 1.6), ledMat);
        ledMesh.rotation.x = Math.PI / 2;
        ledMesh.position.set(lx, 7.48, lz);
        officeScene.add(ledMesh);
    });

    // 8. Mobilyalar: Çay Köşesi, Dinlenme Lounge, Portatif WC, Masa Tenisi, Langırt
    buildTurkishTeaCorner(-7.2, 0, -1.5);
    buildLoungeBreakArea(-7.5, 0, 1.8);
    buildPortableRestroom(-8.8, 0, 4.5);
    buildPingPongTable(6.8, 0, -1.5);
    buildFoosballTable(6.8, 0, 1.8);
}

// -------------------------------------------------------------
// 👑 DEV DUVAR EKRANI: İKİLİ GÖRÜNÜM (BTC GRAFİĞİ + KÂR/ZARAR PnL)
// -------------------------------------------------------------
function buildGiantWallDualScreen() {
    const canvas = document.createElement('canvas');
    canvas.width = 1024;
    canvas.height = 512;
    bigWallCtx = canvas.getContext('2d');

    renderBigWallScreenContent({
        btcPrice: '76,500',
        btcStatus: 'DEAD_CHOP (4s Bant: %0.40)',
        activePositions: []
    });

    bigWallTexture = new THREE.CanvasTexture(canvas);
    bigWallTexture.anisotropy = 4;

    const screenGeo = new THREE.PlaneGeometry(6.6, 2.8);
    const screenMat = new THREE.MeshBasicMaterial({ map: bigWallTexture });
    bigWallScreenMesh = new THREE.Mesh(screenGeo, screenMat);
    bigWallScreenMesh.position.set(0, 4.2, -6.05);
    officeScene.add(bigWallScreenMesh);

    const frame = new THREE.Mesh(new THREE.BoxGeometry(6.75, 2.95, 0.08), new THREE.MeshLambertMaterial({ color: 0x1e293b }));
    frame.position.set(0, 4.2, -6.1);
    officeScene.add(frame);
}

function renderBigWallScreenContent(info) {
    if (!bigWallCtx) return;
    const ctx = bigWallCtx;

    ctx.fillStyle = '#070b14';
    ctx.fillRect(0, 0, 1024, 512);

    ctx.fillStyle = '#0f172a';
    ctx.fillRect(0, 0, 1024, 56);
    ctx.strokeStyle = '#334155';
    ctx.lineWidth = 2;
    ctx.strokeRect(0, 0, 1024, 56);

    ctx.fillStyle = '#f59e0b';
    ctx.font = 'bold 24px Inter, monospace';
    ctx.fillText('👑 PATRON: EFE | DEV İKİLİ STRATEJİ EKRANI (FUTURES & CANLI PnL)', 30, 38);

    ctx.strokeStyle = '#1e293b';
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.moveTo(512, 56);
    ctx.lineTo(512, 512);
    ctx.stroke();

    // SOL YARI: BTC CANLI GRAFİK
    ctx.fillStyle = '#38bdf8';
    ctx.font = 'bold 20px Inter, sans-serif';
    ctx.fillText('📈 CANLI BTC / USDT (FUTURES)', 35, 95);

    ctx.fillStyle = '#f1f5f9';
    ctx.font = 'bold 36px monospace';
    ctx.fillText(`$${info.btcPrice || '76,250.0'}`, 35, 145);

    ctx.fillStyle = (info.btcStatus && info.btcStatus.includes('BULL')) ? '#10b981' : '#f59e0b';
    ctx.font = '16px monospace';
    ctx.fillText(`● REJİM: ${info.btcStatus || 'DEAD_CHOP (Bant: %0.40)'}`, 35, 180);

    drawStylizedCandlesticks(ctx, 35, 210, 440, 260);

    // SAĞ YARI: CANLI POZİSYONLAR
    ctx.fillStyle = '#10b981';
    ctx.font = 'bold 20px Inter, sans-serif';
    ctx.fillText('⚡ CANLI POZİSYON KÂR / ZARAR DURUMU', 545, 95);

    const positions = info.activePositions || [];
    if (positions.length > 0) {
        positions.slice(0, 3).forEach((pos, idx) => {
            const yOffset = 135 + idx * 115;
            const pnl = Number(pos.unrealized_pnl_pct || 0);
            const isPos = pnl >= 0;
            const pnlText = (isPos ? '+' : '') + pnl.toFixed(2) + '%';

            ctx.fillStyle = isPos ? 'rgba(16, 185, 129, 0.15)' : 'rgba(239, 68, 68, 0.15)';
            ctx.fillRect(540, yOffset, 450, 95);
            ctx.strokeStyle = isPos ? '#10b981' : '#ef4444';
            ctx.lineWidth = 2;
            ctx.strokeRect(540, yOffset, 450, 95);

            ctx.fillStyle = isPos ? '#10b981' : '#ef4444';
            ctx.font = 'bold 26px monospace';
            ctx.fillText(`${isPos ? '🟢' : '🔴'} ${pos.symbol || 'COIN'} ${pos.direction || 'LONG'}`, 555, yOffset + 40);

            ctx.font = 'bold 30px monospace';
            ctx.fillText(`${pnlText}`, 840, yOffset + 42);

            ctx.fillStyle = '#94a3b8';
            ctx.font = '15px monospace';
            ctx.fillText(`Fiyat: $${Number(pos.live_price || 0).toLocaleString()} | Giriş: $${Number(pos.entry_price || 0).toLocaleString()}`, 555, yOffset + 75);
        });
    } else {
        ctx.fillStyle = 'rgba(56, 189, 248, 0.08)';
        ctx.fillRect(540, 135, 450, 200);
        ctx.strokeStyle = 'rgba(56, 189, 248, 0.25)';
        ctx.lineWidth = 1.5;
        ctx.strokeRect(540, 135, 450, 200);

        ctx.fillStyle = '#facc15';
        ctx.font = 'bold 24px monospace';
        ctx.fillText('💤 AKTİF İŞLEM YOK', 640, 200);

        ctx.fillStyle = '#94a3b8';
        ctx.font = '16px monospace';
        ctx.fillText('📡 200+ Parite 15M Taranıyor...', 610, 240);
        ctx.fillText('🛡️ Kasa Kalkanı: 0/4 Pozisyon Kotası', 590, 275);
        ctx.fillText('⚖️ Maksimum 5x Kaldıraç Kilitli', 615, 305);
    }
}

function drawStylizedCandlesticks(ctx, startX, startY, w, h) {
    ctx.strokeStyle = '#1e293b';
    ctx.lineWidth = 1;
    for (let y = startY; y <= startY + h; y += 50) {
        ctx.beginPath();
        ctx.moveTo(startX, y);
        ctx.lineTo(startX + w, y);
        ctx.stroke();
    }

    const candleCount = 14;
    const candleW = w / candleCount;
    let curP = startY + h * 0.55;

    for (let i = 0; i < candleCount; i++) {
        const cx = startX + i * candleW + candleW * 0.2;
        const change = (Math.sin(i * 1.5) * 25) + (i % 2 === 0 ? 12 : -10);
        const openP = curP;
        const closeP = curP - change;
        const highP = Math.min(openP, closeP) - 15;
        const lowP = Math.max(openP, closeP) + 15;
        const isGreen = closeP < openP;

        ctx.strokeStyle = isGreen ? '#10b981' : '#ef4444';
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(cx + candleW * 0.3, highP);
        ctx.lineTo(cx + candleW * 0.3, lowP);
        ctx.stroke();

        ctx.fillStyle = isGreen ? '#10b981' : '#ef4444';
        ctx.fillRect(cx, Math.min(openP, closeP), candleW * 0.6, Math.max(Math.abs(closeP - openP), 4));

        curP = closeP;
    }
}

// -------------------------------------------------------------
// ☕ GELENEKSEL TÜRK ÇAY KÖŞESİ (Semaver & Demlik)
// -------------------------------------------------------------
function buildTurkishTeaCorner(x, y, z) {
    const teaGroup = new THREE.Group();
    teaGroup.position.set(x, y, z);

    const table = new THREE.Mesh(new THREE.BoxGeometry(1.6, 0.82, 1.0), new THREE.MeshLambertMaterial({ color: 0x271c14 }));
    table.position.y = 0.41;
    teaGroup.add(table);

    const semaverBase = new THREE.Mesh(new THREE.CylinderGeometry(0.24, 0.22, 0.45, 16), new THREE.MeshLambertMaterial({ color: 0xd97706 }));
    semaverBase.position.set(-0.25, 1.05, 0);
    teaGroup.add(semaverBase);

    const demlik = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.14, 0.18, 14), new THREE.MeshLambertMaterial({ color: 0xffffff }));
    demlik.position.set(-0.25, 1.34, 0);
    teaGroup.add(demlik);

    const tray = new THREE.Mesh(new THREE.BoxGeometry(0.7, 0.02, 0.5), new THREE.MeshLambertMaterial({ color: 0xd4d4d8 }));
    tray.position.set(0.35, 0.83, 0);
    teaGroup.add(tray);

    const glassMat = new THREE.MeshPhysicalMaterial({ color: 0xb91c1c, transmission: 0.7, transparent: true, opacity: 0.85 });
    [-0.15, 0.15].forEach((gx, i) => {
        const glass = new THREE.Mesh(new THREE.CylinderGeometry(0.045, 0.035, 0.10, 12), glassMat);
        glass.position.set(0.35 + gx, 0.88, (i % 2 === 0 ? 0.08 : -0.08));
        teaGroup.add(glass);
    });

    officeScene.add(teaGroup);
}

// -------------------------------------------------------------
// 🛋️ DİNLENME LOUNGE & SİGARA-ÇAY KANEPESİ
// -------------------------------------------------------------
function buildLoungeBreakArea(x, y, z) {
    const loungeGroup = new THREE.Group();
    loungeGroup.position.set(x, y, z);

    const sofaMat = new THREE.MeshLambertMaterial({ color: 0x1e293b });
    const sofaSeat = new THREE.Mesh(new THREE.BoxGeometry(1.8, 0.28, 0.85), sofaMat);
    sofaSeat.position.y = 0.35;
    loungeGroup.add(sofaSeat);

    const sofaBack = new THREE.Mesh(new THREE.BoxGeometry(1.8, 0.70, 0.22), sofaMat);
    sofaBack.position.set(0, 0.72, -0.32);
    loungeGroup.add(sofaBack);

    [-0.85, 0.85].forEach(sx => {
        const arm = new THREE.Mesh(new THREE.BoxGeometry(0.20, 0.50, 0.85), sofaMat);
        arm.position.set(sx, 0.50, 0);
        loungeGroup.add(arm);
    });

    // Cam Sehpa & Küllük
    const tableBase = new THREE.Mesh(new THREE.CylinderGeometry(0.04, 0.25, 0.42, 16), new THREE.MeshLambertMaterial({ color: 0x0f172a }));
    tableBase.position.set(0, 0.21, 0.95);
    loungeGroup.add(tableBase);

    const glassTop = new THREE.Mesh(new THREE.CylinderGeometry(0.45, 0.45, 0.03, 16), new THREE.MeshPhysicalMaterial({ color: 0x38bdf8, transmission: 0.8, opacity: 0.7, transparent: true }));
    glassTop.position.set(0, 0.43, 0.95);
    loungeGroup.add(glassTop);

    const ashtray = new THREE.Mesh(new THREE.CylinderGeometry(0.08, 0.07, 0.03, 12), new THREE.MeshLambertMaterial({ color: 0xe2e8f0 }));
    ashtray.position.set(0, 0.45, 0.95);
    loungeGroup.add(ashtray);

    officeScene.add(loungeGroup);
}

// -------------------------------------------------------------
// 🚻 PORTATİF KABİN TUVALET (MODERN KOMPOZİT KABİN)
// -------------------------------------------------------------
function buildPortableRestroom(x, y, z) {
    const wcGroup = new THREE.Group();
    wcGroup.position.set(x, y, z);

    const cabin = new THREE.Mesh(new THREE.BoxGeometry(1.4, 2.4, 1.4), new THREE.MeshLambertMaterial({ color: 0x1e293b }));
    cabin.position.y = 1.2;
    wcGroup.add(cabin);

    const door = new THREE.Mesh(new THREE.BoxGeometry(0.9, 2.1, 0.06), new THREE.MeshLambertMaterial({ color: 0x334155 }));
    door.position.set(0, 1.08, 0.71);
    wcGroup.add(door);

    const sign = new THREE.Mesh(new THREE.BoxGeometry(0.8, 0.22, 0.06), new THREE.MeshBasicMaterial({ color: 0x0284c7 }));
    sign.position.set(0, 2.25, 0.72);
    wcGroup.add(sign);

    portableWcLight = new THREE.PointLight(0x10b981, 1.0, 3.5);
    portableWcLight.position.set(0, 2.25, 0.85);
    wcGroup.add(portableWcLight);

    officeScene.add(wcGroup);
}

// -------------------------------------------------------------
// 🏓 MASA TENİSİ (PING-PONG) MASASI (MEHMET & BERAT)
// -------------------------------------------------------------
function buildPingPongTable(x, y, z) {
    const tableGroup = new THREE.Group();
    tableGroup.position.set(x, y, z);

    const tableTop = new THREE.Mesh(new THREE.BoxGeometry(2.4, 0.06, 1.4), new THREE.MeshLambertMaterial({ color: 0x0284c7 }));
    tableTop.position.y = 0.76;
    tableGroup.add(tableTop);

    const lineMat = new THREE.MeshBasicMaterial({ color: 0xffffff });
    const centerLine = new THREE.Mesh(new THREE.BoxGeometry(2.4, 0.005, 0.03), lineMat);
    centerLine.position.set(0, 0.795, 0);
    tableGroup.add(centerLine);

    const net = new THREE.Mesh(new THREE.BoxGeometry(0.04, 0.16, 1.5), new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.6 }));
    net.position.set(0, 0.87, 0);
    tableGroup.add(net);

    const legMat = new THREE.MeshLambertMaterial({ color: 0x0f172a });
    [[-1.0, -0.55], [1.0, -0.55], [-1.0, 0.55], [1.0, 0.55]].forEach(([lx, lz]) => {
        const leg = new THREE.Mesh(new THREE.CylinderGeometry(0.04, 0.04, 0.76, 12), legMat);
        leg.position.set(lx, 0.38, lz);
        tableGroup.add(leg);
    });

    officeScene.add(tableGroup);
}

// -------------------------------------------------------------
// ⚽ LANGIRT MASASI (FOOSBALL) (MEHMET & BERAT)
// -------------------------------------------------------------
function buildFoosballTable(x, y, z) {
    const foosballGroup = new THREE.Group();
    foosballGroup.position.set(x, y, z);

    const box = new THREE.Mesh(new THREE.BoxGeometry(1.8, 0.38, 1.0), new THREE.MeshLambertMaterial({ color: 0xb45309 }));
    box.position.y = 0.70;
    foosballGroup.add(box);

    const pitch = new THREE.Mesh(new THREE.BoxGeometry(1.65, 0.02, 0.85), new THREE.MeshLambertMaterial({ color: 0x15803d }));
    pitch.position.y = 0.75;
    foosballGroup.add(pitch);

    const rodMat = new THREE.MeshLambertMaterial({ color: 0xe2e8f0 });
    [-0.55, -0.25, 0.05, 0.35, 0.55].forEach(rx => {
        const rod = new THREE.Mesh(new THREE.CylinderGeometry(0.015, 0.015, 1.4, 10), rodMat);
        rod.rotation.x = Math.PI / 2;
        rod.position.set(rx, 0.82, 0);
        foosballGroup.add(rod);
    });

    const legMat = new THREE.MeshLambertMaterial({ color: 0x1e293b });
    [[-0.8, -0.42], [0.8, -0.42], [-0.8, 0.42], [0.8, 0.42]].forEach(([lx, lz]) => {
        const leg = new THREE.Mesh(new THREE.BoxGeometry(0.12, 0.70, 0.12), legMat);
        leg.position.set(lx, 0.35, lz);
        foosballGroup.add(leg);
    });

    officeScene.add(foosballGroup);
}

// -------------------------------------------------------------
// TRADING MASASI (MAT FÜME AHŞAP - PARLAMA/GLARE BUG'I SIFIR)
// -------------------------------------------------------------
function buildTradingDesk() {
    const tableGroup = new THREE.Group();

    // Genişlik: 2.0m, Uzunluk: 4.6m, Yükseklik: 0.78m
    const topGeo = new THREE.BoxGeometry(2.0, 0.06, 4.6);
    // Mat Lambert Malzeme: Asla ışık yansıtmaz ve çizgi bug'ına girmez!
    const topMat = new THREE.MeshLambertMaterial({ color: 0x1c2434 });
    const tableTop = new THREE.Mesh(topGeo, topMat);
    tableTop.position.set(0, 0.78, 0);
    tableGroup.add(tableTop);

    // İnce altın beveled kenarlık
    const trim = new THREE.Mesh(new THREE.BoxGeometry(2.04, 0.02, 4.64), new THREE.MeshLambertMaterial({ color: 0xd97706 }));
    trim.position.set(0, 0.80, 0);
    tableGroup.add(trim);

    // Ayaklar
    const legMat = new THREE.MeshLambertMaterial({ color: 0x0f172a });
    [[-0.9, -2.1], [0.9, -2.1], [-0.9, 2.1], [0.9, 2.1]].forEach(([lx, lz]) => {
        const leg = new THREE.Mesh(new THREE.CylinderGeometry(0.06, 0.06, 0.78, 16), legMat);
        leg.position.set(lx, 0.39, lz);
        tableGroup.add(leg);
    });

    // Canlı İşlem Balonunun Çapa Noktası (Masanın tam üstü)
    bubbleAnchors.trade.pos = new THREE.Vector3(0, 1.45, 0);

    officeScene.add(tableGroup);
}

// -------------------------------------------------------------
// 👑 BAŞ KOLTUK / PATRON: EFE
// -------------------------------------------------------------
function buildBossEfe() {
    bossGroup = new THREE.Group();
    bossGroup.position.set(0, 0, -2.3);
    bossGroup.rotation.y = 0;

    // Bağımsız Executive Yönetici Koltuğu
    const chairGroup = new THREE.Group();
    chairGroup.position.set(0, 0, -2.3);

    const chromeMat = new THREE.MeshLambertMaterial({ color: 0xe2e8f0 });
    const leatherMat = new THREE.MeshLambertMaterial({ color: 0x090c10 });
    const goldMat = new THREE.MeshLambertMaterial({ color: 0xf59e0b });

    const piston = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.05, 0.45, 16), chromeMat);
    piston.position.y = 0.225;
    chairGroup.add(piston);

    const seat = new THREE.Mesh(new THREE.BoxGeometry(0.75, 0.1, 0.7), leatherMat);
    seat.position.y = 0.45;
    chairGroup.add(seat);

    const back = new THREE.Mesh(new THREE.BoxGeometry(0.72, 1.0, 0.1), leatherMat);
    back.position.set(0, 0.98, -0.32);
    back.rotation.x = -0.06;
    chairGroup.add(back);

    [-0.38, 0.38].forEach(ax => {
        const arm = new THREE.Mesh(new THREE.BoxGeometry(0.06, 0.2, 0.5), goldMat);
        arm.position.set(ax, 0.65, -0.05);
        chairGroup.add(arm);
    });
    officeScene.add(chairGroup);

    // Efe'nin Gövdesi: Siyah Takım Elbise
    const suitMat = new THREE.MeshLambertMaterial({ color: 0x0a0c10 });
    const shirtMat = new THREE.MeshLambertMaterial({ color: 0xffffff });
    const tieMat = new THREE.MeshLambertMaterial({ color: 0x000000 });

    const legs = new THREE.Mesh(new THREE.BoxGeometry(0.55, 0.18, 0.55), suitMat);
    legs.position.set(0, 0.54, 0.05);
    bossGroup.add(legs);

    const torso = new THREE.Mesh(new THREE.BoxGeometry(0.60, 0.58, 0.34), suitMat);
    torso.position.y = 0.90;
    bossGroup.add(torso);

    const collar = new THREE.Mesh(new THREE.BoxGeometry(0.22, 0.12, 0.18), shirtMat);
    collar.position.set(0, 1.15, 0.07);
    bossGroup.add(collar);

    const tie = new THREE.Mesh(new THREE.BoxGeometry(0.07, 0.30, 0.04), tieMat);
    tie.position.set(0, 1.02, 0.14);
    bossGroup.add(tie);

    bossLeftArm = new THREE.Mesh(new THREE.BoxGeometry(0.12, 0.42, 0.12), suitMat);
    bossLeftArm.position.set(-0.34, 0.85, 0.18);
    bossLeftArm.rotation.x = Math.PI / 3.2;
    bossGroup.add(bossLeftArm);

    bossRightArm = new THREE.Mesh(new THREE.BoxGeometry(0.12, 0.42, 0.12), suitMat);
    bossRightArm.position.set(0.34, 0.85, 0.18);
    bossRightArm.rotation.x = Math.PI / 3.2;
    bossGroup.add(bossRightArm);

    // Baş & Saç
    const headGroup = new THREE.Group();
    headGroup.position.set(0, 1.35, -0.02);

    const head = new THREE.Mesh(new THREE.BoxGeometry(0.32, 0.34, 0.30), new THREE.MeshLambertMaterial({ color: 0xf5c6a5 }));
    headGroup.add(head);

    const hair = new THREE.Mesh(new THREE.BoxGeometry(0.34, 0.12, 0.32), new THREE.MeshLambertMaterial({ color: 0x171717 }));
    hair.position.set(0, 0.16, -0.01);
    headGroup.add(hair);

    bossHeadMesh = headGroup;
    bossGroup.add(headGroup);

    buildBossDeskItems(bossGroup);
    buildSimsPlumbob(bossGroup);

    bubbleAnchors.boss.pos = new THREE.Vector3(0, 2.35, -2.3);

    officeScene.add(bossGroup);
}

function buildSimsPlumbob(parentGroup) {
    const plumbobGeo = new THREE.OctahedronGeometry(0.18, 0);
    plumbobGeo.scale(0.85, 1.7, 0.85);

    const plumbobMat = new THREE.MeshBasicMaterial({ color: 0x22c55e });
    plumbobMesh = new THREE.Mesh(plumbobGeo, plumbobMat);
    plumbobMesh.position.set(0, 1.95, -0.02);

    plumbobLight = new THREE.PointLight(0x22c55e, 1.2, 3.0);
    plumbobLight.position.set(0, 1.95, -0.02);
    parentGroup.add(plumbobLight);

    parentGroup.add(plumbobMesh);
}

function buildBossDeskItems(parentGroup) {
    const macBase = new THREE.Mesh(new THREE.BoxGeometry(0.48, 0.02, 0.32), new THREE.MeshLambertMaterial({ color: 0xd8e0e8 }));
    macBase.position.set(0, 0.82, 0.45);
    parentGroup.add(macBase);

    const macScreen = new THREE.Mesh(new THREE.BoxGeometry(0.48, 0.32, 0.02), new THREE.MeshBasicMaterial({ color: 0x38bdf8 }));
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
    const plate = new THREE.Mesh(new THREE.BoxGeometry(0.75, 0.20, 0.10), new THREE.MeshLambertMaterial({ map: plateTex }));
    plate.position.set(0, 0.88, 0.75);
    plate.rotation.x = -0.28;
    parentGroup.add(plate);
}

// -------------------------------------------------------------
// 5 UZMAN AJAN (MONİTÖRLER ÇALIŞANLARA BAKIYOR & SANDALYE DÖNÜYOR)
// -------------------------------------------------------------
function buildSpecialistAgents() {
    // 1. SCANNER AGENT (Sol Üst: x = -1.55, z = -0.75)
    createAgentWorkstation({
        id: 'scanner',
        name: 'Scanner Agent',
        seatPos: [-1.55, 0, -0.75],
        seatRotY: Math.PI / 2,
        deskPos: [-0.60, 0.78, -0.75],
        suitColor: 0x1d4ed8,
        hairColor: 0x334155,
        screenColor: 0x0284c7,
        phrases: [
            "Radar: 200 parite tarandı, BTC testerede bekliyoruz.",
            "4s hacim sıkışması taranıyor, altcoinler güvenli modda.",
            "Hacimsiz coinler elendi, majör pariteler izleniyor."
        ]
    });

    // 2. TA ANALYST (Sol Alt: x = -1.55, z = +0.75)
    createAgentWorkstation({
        id: 'ta',
        name: 'Teknik Analist',
        seatPos: [-1.55, 0, 0.75],
        seatRotY: Math.PI / 2,
        deskPos: [-0.60, 0.78, 0.75],
        suitColor: 0x7e22ce,
        hairColor: 0x475569,
        hasGlasses: true,
        screenColor: 0x9333ea,
        phrases: [
            "BTC 4s bant daralması %0.40! Sıkışma had safhada.",
            "RSI 48 seviyesinde nötr, EMA20 üstünde tutunma var.",
            "Breakout teyidi gelmeden acele emir açmıyoruz."
        ]
    });

    // 3. RISK OFFICER (Sağ Üst: x = +1.55, z = -0.75)
    createAgentWorkstation({
        id: 'risk',
        name: 'Risk & Kasa Şefi',
        seatPos: [1.55, 0, -0.75],
        seatRotY: -Math.PI / 2,
        deskPos: [0.60, 0.78, -0.75],
        suitColor: 0xb91c1c,
        hairColor: 0x0f172a,
        screenColor: 0xdc2626,
        phrases: [
            "Kasa Kalkanı devrede: Maks 5x kaldıraç, %1.5 risk tavanı kilitli.",
            "Sermaye koruma modu aktif, teminat güvende.",
            "Disiplin kuralımız ihlal edilmeyecek."
        ]
    });

    // 4. NEWS & MACRO AGENT (Sağ Alt: x = +1.55, z = +0.75)
    createAgentWorkstation({
        id: 'news',
        name: 'Haber & Makro Ajanı',
        seatPos: [1.55, 0, 0.75],
        seatRotY: -Math.PI / 2,
        deskPos: [0.60, 0.78, 0.75],
        suitColor: 0xd97706,
        hairColor: 0x1e293b,
        screenColor: 0xf59e0b,
        phrases: [
            "Funding rate stabil, global piyasalarda şok veri yok.",
            "Makro haber akışı sakin, likidite dengeli.",
            "Fed faiz beklentileri normal seviyede seyrediyor."
        ]
    });

    // 5. CHIEF ANALYST (Efe'nin Yanı: x = 1.35, z = -1.8)
    createAgentWorkstation({
        id: 'chief',
        name: 'Baş Stratejist',
        seatPos: [1.35, 0, -1.8],
        seatRotY: -Math.PI / 3.5,
        deskPos: [0.95, 0.78, -1.5],
        suitColor: 0x059669,
        hairColor: 0x18181b,
        screenColor: 0x10b981,
        isStandingByDefault: true,
        phrases: [
            "Efe Bey, piyasa beklemede. Şartlar oluşursa komite onaylayacak.",
            "Dev ekrandaki pozisyon ve rejim matrisini güncelledim efendim.",
            "Tüm ajanlar masada koordineli çalışıyor."
        ]
    });
}

function createAgentWorkstation(cfg) {
    const isRightSide = cfg.seatPos[0] > 0;
    const isChief = cfg.id === 'chief';

    // 1. BAĞIMSIZ DÖNER SANDALYE (Ajan kalkarken sandalyeyi arkaya çevirir!)
    const chairGroup = new THREE.Group();
    chairGroup.position.set(...cfg.seatPos);
    chairGroup.rotation.y = cfg.seatRotY;

    const chairSeat = new THREE.Mesh(new THREE.BoxGeometry(0.55, 0.08, 0.55), new THREE.MeshLambertMaterial({ color: 0x1e293b }));
    chairSeat.position.y = 0.44;
    chairGroup.add(chairSeat);

    const chairBack = new THREE.Mesh(new THREE.BoxGeometry(0.55, 0.65, 0.08), new THREE.MeshLambertMaterial({ color: 0x1e293b }));
    chairBack.position.set(0, 0.80, -0.27);
    chairGroup.add(chairBack);

    const chairLeg = new THREE.Mesh(new THREE.CylinderGeometry(0.04, 0.04, 0.44, 12), new THREE.MeshLambertMaterial({ color: 0x475569 }));
    chairLeg.position.y = 0.22;
    chairGroup.add(chairLeg);

    officeScene.add(chairGroup);

    // 2. MONİTÖRLER VE MOUSE (YÖNLERİ ELEMANA BAKIYOR!)
    buildWorkerDeskEquipment(cfg, isRightSide);

    // 3. KARAKTER MODELİ
    const agentGroup = new THREE.Group();
    agentGroup.position.set(...cfg.seatPos);
    agentGroup.rotation.y = cfg.seatRotY;

    const bodyGroup = new THREE.Group();
    const clothMat = new THREE.MeshLambertMaterial({ color: cfg.suitColor });
    const skinMat = new THREE.MeshLambertMaterial({ color: 0xfbd0b0 });

    const leftLeg = new THREE.Mesh(new THREE.BoxGeometry(0.14, 0.42, 0.14), clothMat);
    leftLeg.position.set(-0.14, 0.21, 0);
    bodyGroup.add(leftLeg);

    const rightLeg = new THREE.Mesh(new THREE.BoxGeometry(0.14, 0.42, 0.14), clothMat);
    rightLeg.position.set(0.14, 0.21, 0);
    bodyGroup.add(rightLeg);

    const torso = new THREE.Mesh(new THREE.BoxGeometry(0.48, 0.52, 0.28), clothMat);
    torso.position.y = 0.70;
    bodyGroup.add(torso);

    const leftArm = new THREE.Mesh(new THREE.BoxGeometry(0.11, 0.40, 0.11), clothMat);
    leftArm.position.set(-0.28, 0.68, 0.12);
    leftArm.rotation.x = Math.PI / 4;
    bodyGroup.add(leftArm);

    const rightArm = new THREE.Mesh(new THREE.BoxGeometry(0.11, 0.40, 0.11), clothMat);
    rightArm.position.set(0.28, 0.68, 0.12);
    rightArm.rotation.x = Math.PI / 4;
    bodyGroup.add(rightArm);

    const headGroup = new THREE.Group();
    headGroup.position.set(0, 1.10, 0);

    const head = new THREE.Mesh(new THREE.BoxGeometry(0.28, 0.30, 0.26), skinMat);
    headGroup.add(head);

    const hair = new THREE.Mesh(new THREE.BoxGeometry(0.30, 0.10, 0.28), new THREE.MeshLambertMaterial({ color: cfg.hairColor }));
    hair.position.set(0, 0.15, 0);
    headGroup.add(hair);

    if (cfg.hasGlasses) {
        const glasses = new THREE.Mesh(new THREE.BoxGeometry(0.24, 0.05, 0.03), new THREE.MeshBasicMaterial({ color: 0x0284c7 }));
        glasses.position.set(0, 0.02, 0.14);
        headGroup.add(glasses);
    }

    bodyGroup.add(headGroup);
    agentGroup.add(bodyGroup);

    agents[cfg.id] = {
        id: cfg.id,
        name: cfg.name,
        group: agentGroup,
        chairGroup: chairGroup,
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

// 🖥️ MONİTÖRLERİN ELEMANA BAKMASI VE OPTİK MOUSE
function buildWorkerDeskEquipment(cfg, isRightSide) {
    const compGroup = new THREE.Group();
    compGroup.position.set(...cfg.deskPos);

    // Kavisli ekranlar elemana baksın:
    // Sol taraftakiler için (x = -1.55) -> Monitörler SOLA (-PI/2) bakar!
    // Sağ taraftakiler için (x = +1.55) -> Monitörler SAĞA (+PI/2) bakar!
    compGroup.rotation.y = isRightSide ? Math.PI / 2 : -Math.PI / 2;

    const screenMat = new THREE.MeshBasicMaterial({ color: cfg.screenColor });

    // Ana Ekran (Elemana doğru kavisli)
    const scr1 = new THREE.Mesh(new THREE.BoxGeometry(0.48, 0.30, 0.02), screenMat);
    scr1.position.set(-0.24, 0.24, 0.02);
    scr1.rotation.y = -0.15;
    compGroup.add(scr1);
    officeDeskScreens.push(scr1);

    // Yan Ekran (Elemana doğru kavisli)
    const scr2 = new THREE.Mesh(new THREE.BoxGeometry(0.44, 0.28, 0.02), screenMat);
    scr2.position.set(0.24, 0.23, 0.02);
    scr2.rotation.y = 0.15;
    compGroup.add(scr2);
    officeDeskScreens.push(scr2);

    // Stand
    const standMat = new THREE.MeshLambertMaterial({ color: 0x334155 });
    const standBar = new THREE.Mesh(new THREE.BoxGeometry(0.70, 0.03, 0.03), standMat);
    standBar.position.set(0, 0.22, -0.05);
    compGroup.add(standBar);

    const standPost = new THREE.Mesh(new THREE.CylinderGeometry(0.025, 0.025, 0.22, 12), standMat);
    standPost.position.set(0, 0.11, -0.05);
    compGroup.add(standPost);

    // Klavye
    const kb = new THREE.Mesh(new THREE.BoxGeometry(0.40, 0.012, 0.14), new THREE.MeshLambertMaterial({ color: 0x1e293b }));
    kb.position.set(-0.06, 0.015, 0.24);
    compGroup.add(kb);

    // 🖱️ OPTİK MOUSE & PAD
    const pad = new THREE.Mesh(new THREE.BoxGeometry(0.65, 0.005, 0.28), new THREE.MeshLambertMaterial({ color: 0x090e17 }));
    pad.position.set(0, 0.005, 0.24);
    compGroup.add(pad);

    const mouse = new THREE.Mesh(new THREE.BoxGeometry(0.065, 0.018, 0.10), new THREE.MeshLambertMaterial({ color: 0x0f172a }));
    mouse.position.set(0.22, 0.016, 0.24);
    compGroup.add(mouse);

    const mouseLed = new THREE.Mesh(new THREE.BoxGeometry(0.01, 0.005, 0.03), new THREE.MeshBasicMaterial({ color: 0x38bdf8 }));
    mouseLed.position.set(0.22, 0.026, 0.24);
    compGroup.add(mouseLed);

    officeScene.add(compGroup);
}

// -------------------------------------------------------------
// 🏓 ⚽ MEHMET & BERAT
// -------------------------------------------------------------
function buildFriendsMehmetAndBerat() {
    createFriendCharacter({
        id: 'mehmet',
        name: 'Mehmet (Patronun Arkadaşı)',
        startPos: [5.6, 0, -1.5],
        startRotY: Math.PI / 2,
        suitColor: 0x0d9488,
        hairColor: 0x292524,
        phrases: [
            "Berat çay koysana kanka ya, semaver kaynıyor!",
            "Masa tenisinde dün 11-4 yendim seni unutma!",
            "Efe patron oldu bize çay bile ısmarlamıyor haha.",
            "Langırtın kalecisini çok iyi çeviriyorum bu sefer affetmem.",
            "Kanka Bitcoin rekor kırar mı sence? Gerçi bana ne Efe düşünsün."
        ]
    });

    createFriendCharacter({
        id: 'berat',
        name: 'Berat (Patronun Arkadaşı)',
        startPos: [8.0, 0, -1.5],
        startRotY: -Math.PI / 2,
        suitColor: 0x1e3a8a,
        hairColor: 0x1c1917,
        phrases: [
            "Mehmet masa tenisinde rüzgar vardı o yüzden yendin, gel rövanşa!",
            "Çayı ben koydum zaten, şekeri sen getir.",
            "Efe'ye bak takım elbiseyle Wall Street kurdu gibi maşallah.",
            "Langırt 7'de biter kanka, bahse var mısın?",
            "Ajanlar da harıl harıl çalışıyor valla, kolay gelsin beyler."
        ]
    });
}

function createFriendCharacter(cfg) {
    const friendGroup = new THREE.Group();
    friendGroup.position.set(...cfg.startPos);
    friendGroup.rotation.y = cfg.startRotY;

    const bodyGroup = new THREE.Group();
    const clothMat = new THREE.MeshLambertMaterial({ color: cfg.suitColor });
    const pantsMat = new THREE.MeshLambertMaterial({ color: 0x334155 });
    const skinMat = new THREE.MeshLambertMaterial({ color: 0xfbd0b0 });

    const leftLeg = new THREE.Mesh(new THREE.BoxGeometry(0.14, 0.44, 0.14), pantsMat);
    leftLeg.position.set(-0.14, 0.22, 0);
    bodyGroup.add(leftLeg);

    const rightLeg = new THREE.Mesh(new THREE.BoxGeometry(0.14, 0.44, 0.14), pantsMat);
    rightLeg.position.set(0.14, 0.22, 0);
    bodyGroup.add(rightLeg);

    const torso = new THREE.Mesh(new THREE.BoxGeometry(0.50, 0.54, 0.30), clothMat);
    torso.position.y = 0.72;
    bodyGroup.add(torso);

    const leftArm = new THREE.Mesh(new THREE.BoxGeometry(0.11, 0.42, 0.11), clothMat);
    leftArm.position.set(-0.30, 0.70, 0.08);
    leftArm.rotation.x = Math.PI / 6;
    bodyGroup.add(leftArm);

    const rightArm = new THREE.Mesh(new THREE.BoxGeometry(0.11, 0.42, 0.11), clothMat);
    rightArm.position.set(0.30, 0.70, 0.08);
    rightArm.rotation.x = Math.PI / 4;
    bodyGroup.add(rightArm);

    const headGroup = new THREE.Group();
    headGroup.position.set(0, 1.14, 0);

    const head = new THREE.Mesh(new THREE.BoxGeometry(0.28, 0.30, 0.26), skinMat);
    headGroup.add(head);

    const hair = new THREE.Mesh(new THREE.BoxGeometry(0.30, 0.12, 0.28), new THREE.MeshLambertMaterial({ color: cfg.hairColor }));
    hair.position.set(0, 0.15, 0);
    headGroup.add(hair);

    bodyGroup.add(headGroup);
    friendGroup.add(bodyGroup);

    friends[cfg.id] = {
        id: cfg.id,
        name: cfg.name,
        group: friendGroup,
        bodyGroup: bodyGroup,
        headGroup: headGroup,
        leftLeg: leftLeg,
        rightLeg: rightLeg,
        leftArm: leftArm,
        rightArm: rightArm,
        homePos: new THREE.Vector3(...cfg.startPos),
        homeRotY: cfg.startRotY,
        state: 'PLAYING_PINGPONG',
        waypoints: [],
        currentWpIdx: 0,
        phrases: cfg.phrases
    };

    bubbleAnchors[cfg.id].pos = new THREE.Vector3(cfg.startPos[0], 2.0, cfg.startPos[2]);

    officeScene.add(friendGroup);
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

    bubbleAnchors.mehmet.el = document.getElementById('bubble-mehmet');
    bubbleAnchors.mehmet.bodyEl = document.getElementById('text-mehmet');

    bubbleAnchors.berat.el = document.getElementById('bubble-berat');
    bubbleAnchors.berat.bodyEl = document.getElementById('text-berat');

    bubbleAnchors.trade.el = document.getElementById('tradeMonitorBubble');

    Object.keys(bubbleAnchors).forEach(key => {
        const item = bubbleAnchors[key];
        if (item.el) {
            item.el.addEventListener('click', () => {
                if (key === 'boss') {
                    triggerSpeech('boss', "Piyasayı tarayın beyler, acele işlem yok! Sermaye koruma önceliğimiz.");
                    setOfficeCamera('boss');
                } else if (agents[key]) {
                    const phr = agents[key].phrases;
                    triggerSpeech(key, phr[Math.floor(Math.random() * phr.length)], 5000);
                } else if (friends[key]) {
                    const phr = friends[key].phrases;
                    triggerSpeech(key, phr[Math.floor(Math.random() * phr.length)], 5000);
                }
            });
        }
    });
}

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

        if (key !== 'trade' && !item.isSpeaking) {
            return;
        }

        let worldPos = item.pos;
        if (key !== 'trade' && key !== 'boss') {
            if (agents[key]) {
                worldPos = agents[key].group.position.clone();
                worldPos.y += 1.95;
            } else if (friends[key]) {
                worldPos = friends[key].group.position.clone();
                worldPos.y += 2.0;
            }
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
// OTONOM OFİS RUTİNİ: SANDALYE DÖNÜŞÜ, MASADAN DOLAŞMA & KANEPEDE OTURMA
// -------------------------------------------------------------
function updateAutonomousOfficeAI(deltaTime, time) {
    // 1. Sırayla Konuşma Döngüsü
    if (time > nextDialogueTime) {
        nextDialogueTime = time + 7000 + Math.random() * 4000;
        const allKeys = ['boss', 'scanner', 'ta', 'risk', 'news', 'chief', 'mehmet', 'berat'];
        const chosen = allKeys[Math.floor(Math.random() * allKeys.length)];

        if (chosen === 'boss') {
            const bossLines = [
                "Piyasayı tarayın beyler, acele yok! Sermaye koruma kuralımız #1.",
                "Mehmet, Berat sesinizi azaltın komite toplantıdayız haha!",
                "Risk Şefi, kaldıraç ve marjini çift kontrol et."
            ];
            triggerSpeech('boss', bossLines[Math.floor(Math.random() * bossLines.length)], 5000);
        } else if (agents[chosen]) {
            const phr = agents[chosen].phrases;
            triggerSpeech(chosen, phr[Math.floor(Math.random() * phr.length)], 5000);
        } else if (friends[chosen]) {
            const phr = friends[chosen].phrases;
            triggerSpeech(chosen, phr[Math.floor(Math.random() * phr.length)], 5000);
        }
    }

    // 2. Mehmet ve Berat Oyun & Çay Rutini
    if (time > nextFriendsGameTime) {
        nextFriendsGameTime = time + 15000 + Math.random() * 8000;
        const gameType = Math.floor(Math.random() * 3);
        switchFriendsActivity(gameType);
    }

    // 3. Çalışanların Yürüme Rutini (Çakışma Önleyici Tekil Kilit: isAnyAgentWalking)
    if (!isAnyAgentWalking && time > nextAutonomousActionTime) {
        nextAutonomousActionTime = time + 18000 + Math.random() * 10000;
        const candidateIds = ['scanner', 'ta', 'risk', 'news'];
        const seatedCandidates = candidateIds.filter(id => agents[id] && agents[id].state === 'SEATED_WORKING');

        if (seatedCandidates.length > 0) {
            const walker = agents[seatedCandidates[Math.floor(Math.random() * seatedCandidates.length)]];
            const actionType = Math.floor(Math.random() * 3); // 0: Çay/Semaver, 1: Portatif WC, 2: Kanepe Lounge
            startAgentActivityWithChairSwivel(walker, actionType);
        }
    }

    Object.keys(agents).forEach(id => updateSingleAgentMovement(agents[id], deltaTime, time));
    Object.keys(friends).forEach(id => updateFriendMovement(friends[id], deltaTime, time));
}

function switchFriendsActivity(actType) {
    const m = friends['mehmet'];
    const b = friends['berat'];
    if (!m || !b) return;

    if (actType === 0) {
        m.waypoints = [new THREE.Vector3(5.6, 0, -1.5)];
        b.waypoints = [new THREE.Vector3(8.0, 0, -1.5)];
        m.state = 'WALKING';
        b.state = 'WALKING';
        m.targetState = 'PLAYING_PINGPONG';
        b.targetState = 'PLAYING_PINGPONG';
        m.finalRotY = Math.PI / 2;
        b.finalRotY = -Math.PI / 2;
        triggerSpeech('mehmet', "Berat masa tenisinde bu sefer seni devireceğim!", 4500);
    } else if (actType === 1) {
        m.waypoints = [new THREE.Vector3(5.6, 0, 1.8)];
        b.waypoints = [new THREE.Vector3(8.0, 0, 1.8)];
        m.state = 'WALKING';
        b.state = 'WALKING';
        m.targetState = 'PLAYING_FOOSBALL';
        b.targetState = 'PLAYING_FOOSBALL';
        m.finalRotY = Math.PI / 2;
        b.finalRotY = -Math.PI / 2;
        triggerSpeech('berat', "Langırt 7'de biter kanka, bahse var mısın?", 4500);
    } else {
        m.waypoints = [new THREE.Vector3(2.5, 0, 2.5), new THREE.Vector3(-6.2, 0, -1.5)];
        b.waypoints = [new THREE.Vector3(2.5, 0, 2.5), new THREE.Vector3(-5.6, 0, -1.5)];
        m.state = 'WALKING';
        b.state = 'WALKING';
        m.targetState = 'DRINKING_TEA';
        b.targetState = 'DRINKING_TEA';
        m.finalRotY = -Math.PI / 2;
        b.finalRotY = Math.PI / 2;
        triggerSpeech('mehmet', "Kanka semaverden iki bardak çay çekelim ya.", 4500);
        playOfficeSound('tea');
    }
}

function updateFriendMovement(fr, deltaTime, time) {
    if (fr.state === 'PLAYING_PINGPONG') {
        fr.rightArm.rotation.x = Math.PI / 3 + Math.sin(time * 0.008) * 0.35;
        if (Math.random() < 0.015) playOfficeSound('pingpong');
        return;
    }

    if (fr.state === 'PLAYING_FOOSBALL') {
        fr.leftArm.rotation.x = Math.PI / 4 + Math.sin(time * 0.01) * 0.25;
        fr.rightArm.rotation.x = Math.PI / 4 + Math.cos(time * 0.01) * 0.25;
        return;
    }

    if (fr.state === 'DRINKING_TEA') {
        fr.rightArm.rotation.x = Math.PI / 3 + Math.sin(time * 0.003) * 0.15;
        return;
    }

    if (fr.state === 'WALKING') {
        if (!fr.waypoints || fr.currentWpIdx >= fr.waypoints.length) {
            fr.state = fr.targetState || 'IDLE';
            fr.group.rotation.y = fr.finalRotY || 0;
            fr.leftLeg.rotation.x = 0;
            fr.rightLeg.rotation.x = 0;
            return;
        }

        const targetWp = fr.waypoints[fr.currentWpIdx];
        const currentPos = fr.group.position;
        const dir = new THREE.Vector3().subVectors(targetWp, currentPos);
        const dist = dir.length();

        if (dist < 0.1) {
            fr.currentWpIdx++;
        } else {
            dir.normalize();
            const step = Math.min(dist, 1.9 * deltaTime);
            currentPos.addScaledVector(dir, step);

            const targetAngle = Math.atan2(dir.x, dir.z);
            fr.group.rotation.y = THREE.MathUtils.lerp(fr.group.rotation.y, targetAngle, 0.15);

            const walkCycle = time * 0.01;
            fr.leftLeg.rotation.x = Math.sin(walkCycle) * 0.45;
            fr.rightLeg.rotation.x = -Math.sin(walkCycle) * 0.45;
            fr.leftArm.rotation.x = -Math.sin(walkCycle) * 0.35;
            fr.rightArm.rotation.x = Math.sin(walkCycle) * 0.35;
        }
    }
}

// 🪑 SANDALYEYİ ARKAYA ÇEVİRME & MASANIN ETRAFINDAN DOLAŞMA
function startAgentActivityWithChairSwivel(ag, actionType) {
    isAnyAgentWalking = true;
    ag.state = 'SWIVELING_OUT';
    ag.activityType = actionType;
    ag.swivelProgress = 0;

    // Sandalyenin arkaya dönük açısı (Koridora doğru)
    const isLeft = ag.homePos.x < 0;
    ag.swivelTargetRot = isLeft ? -Math.PI / 2 : Math.PI / 2;

    const corridorX = isLeft ? -2.4 : 2.4;

    if (actionType === 0) {
        // Çay Köşesine Gidiş (Masanın etrafından dolanır)
        ag.waypoints = [
            new THREE.Vector3(corridorX, 0, ag.homePos.z),
            new THREE.Vector3(corridorX, 0, 2.8),
            new THREE.Vector3(-4.5, 0, 2.8),
            new THREE.Vector3(-6.2, 0, -1.2)
        ];
        ag.destinationPhrase = "Tavşan kanı bir bardak çay alayım, piyasa takibi yoğun...";
        ag.returnWaypoints = [
            new THREE.Vector3(-6.2, 0, -1.2),
            new THREE.Vector3(-4.5, 0, 2.8),
            new THREE.Vector3(corridorX, 0, 2.8),
            new THREE.Vector3(corridorX, 0, ag.homePos.z),
            ag.homePos.clone()
        ];
    } else if (actionType === 1) {
        // Portatif WC'ye Gidiş
        ag.waypoints = [
            new THREE.Vector3(corridorX, 0, ag.homePos.z),
            new THREE.Vector3(corridorX, 0, 2.8),
            new THREE.Vector3(-8.0, 0, 4.2)
        ];
        ag.destinationPhrase = "Kısa bir ihtiyaç molası...";
        ag.returnWaypoints = [
            new THREE.Vector3(-8.0, 0, 4.2),
            new THREE.Vector3(corridorX, 0, 2.8),
            new THREE.Vector3(corridorX, 0, ag.homePos.z),
            ag.homePos.clone()
        ];
    } else {
        // 🛋️ KANEPEDE OTURMA & DİNLENME
        ag.waypoints = [
            new THREE.Vector3(corridorX, 0, ag.homePos.z),
            new THREE.Vector3(corridorX, 0, 2.8),
            new THREE.Vector3(-7.5, 0, 1.8)
        ];
        ag.destinationPhrase = "Lounge kanepesinde 5 dakika dinlenip bir çay molası veriyorum.";
        ag.returnWaypoints = [
            new THREE.Vector3(-7.5, 0, 1.8),
            new THREE.Vector3(corridorX, 0, 2.8),
            new THREE.Vector3(corridorX, 0, ag.homePos.z),
            ag.homePos.clone()
        ];
    }
}

function updateSingleAgentMovement(ag, deltaTime, time) {
    if (ag.state === 'SEATED_WORKING') {
        ag.leftArm.rotation.x = Math.PI / 3.5 + Math.sin(time * 0.005) * 0.04;
        ag.rightArm.rotation.x = Math.PI / 3.5 + Math.cos(time * 0.005) * 0.04;
        ag.leftLeg.rotation.x = 0;
        ag.rightLeg.rotation.x = 0;
        ag.bodyGroup.position.y = 0;
        return;
    }

    // AŞAMA 1: SANDALYEYİ ARKAYA ÇEVİRME
    if (ag.state === 'SWIVELING_OUT') {
        ag.swivelProgress += deltaTime * 2.5;
        const currentRot = THREE.MathUtils.lerp(ag.homeRotY, ag.swivelTargetRot, Math.min(ag.swivelProgress, 1.0));
        ag.chairGroup.rotation.y = currentRot;
        ag.group.rotation.y = currentRot;

        if (ag.swivelProgress >= 1.0) {
            ag.state = 'WALKING';
            ag.currentWpIdx = 0;
        }
        return;
    }

    // AŞAMA 2: YÜRÜME (MASANIN ETRAFINDAN KORİDORLARDAN DOLAŞIR)
    if (ag.state === 'WALKING') {
        if (ag.currentWpIdx >= ag.waypoints.length) {
            ag.state = 'AT_DESTINATION';
            ag.destinationTimer = Date.now() + 6000;
            triggerSpeech(ag.id, ag.destinationPhrase, 4500);

            if (ag.activityType === 0) {
                playOfficeSound('tea');
            } else if (ag.activityType === 1) {
                if (portableWcLight) portableWcLight.color.setHex(0xf59e0b);
            } else if (ag.activityType === 2) {
                // 🛋️ KANEPEDE OTURMA POZİSYONU!
                ag.group.rotation.y = Math.PI / 2; // Odaya dönük
                ag.bodyGroup.position.y = -0.15; // Kanepenin minderine oturur
                ag.leftArm.rotation.x = Math.PI / 3; // Çay bardağını tutar
            }
            return;
        }

        const targetWp = ag.waypoints[ag.currentWpIdx];
        const currentPos = ag.group.position;
        const dir = new THREE.Vector3().subVectors(targetWp, currentPos);
        const dist = dir.length();

        if (dist < 0.12) {
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
        }
    } else if (ag.state === 'AT_DESTINATION') {
        if (Date.now() > ag.destinationTimer) {
            if (ag.activityType === 1 && portableWcLight) {
                portableWcLight.color.setHex(0x10b981);
            }
            // Kanepeden kalkış
            ag.bodyGroup.position.y = 0;
            ag.state = 'WALKING_BACK';
            ag.waypoints = ag.returnWaypoints;
            ag.currentWpIdx = 0;
        }
    } else if (ag.state === 'WALKING_BACK') {
        if (ag.currentWpIdx >= ag.waypoints.length) {
            // AŞAMA 3: MASAYA GELDİ, SANDALYE VE KARAKTERİ MASAYA DOĞRU GERİ ÇEVİR
            ag.state = 'SWIVELING_IN';
            ag.swivelProgress = 0;
        } else {
            const targetWp = ag.waypoints[ag.currentWpIdx];
            const currentPos = ag.group.position;
            const dir = new THREE.Vector3().subVectors(targetWp, currentPos);
            const dist = dir.length();

            if (dist < 0.12) {
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
            }
        }
    } else if (ag.state === 'SWIVELING_IN') {
        ag.swivelProgress += deltaTime * 2.5;
        const currentRot = THREE.MathUtils.lerp(ag.swivelTargetRot, ag.homeRotY, Math.min(ag.swivelProgress, 1.0));
        ag.chairGroup.rotation.y = currentRot;
        ag.group.rotation.y = currentRot;

        if (ag.swivelProgress >= 1.0) {
            ag.state = 'SEATED_WORKING';
            ag.group.position.copy(ag.homePos);
            ag.group.rotation.y = ag.homeRotY;
            ag.chairGroup.rotation.y = ag.homeRotY;
            ag.leftLeg.rotation.x = 0;
            ag.rightLeg.rotation.x = 0;
            ag.bodyGroup.position.y = 0;
            isAnyAgentWalking = false; // Kilit açıldı, başka eleman yürüyebilir
        }
    }
}

// -------------------------------------------------------------
// KAMERA KONTROLLERİ (PRESETS)
// -------------------------------------------------------------
function setOfficeCamera(mode = 'boss') {
    ['btnCamBoss', 'btnCamTable', 'btnCamIso', 'btnCamChill'].forEach(id => {
        const btn = document.getElementById(id);
        if (btn) btn.classList.remove('active');
    });

    const isPortrait = (window.innerWidth / window.innerHeight) < 1.0;

    if (mode === 'boss') {
        const btn = document.getElementById('btnCamBoss');
        if (btn) btn.classList.add('active');
        camTargetPos = new THREE.Vector3(0, 2.3, isPortrait ? 0.3 : -0.4);
        camLookTarget = new THREE.Vector3(0, 1.5, -2.3);
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
    } else if (mode === 'chill') {
        const btn = document.getElementById('btnCamChill');
        if (btn) btn.classList.add('active');
        camTargetPos = new THREE.Vector3(6.5, 4.2, 3.8);
        camLookTarget = new THREE.Vector3(6.5, 1.1, 0);
        playOfficeSound('pingpong');
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

    // 3. Konfeti Parçacık Animasyonu
    updateConfetti(deltaTime);

    // 4. Otonom Ofis Yapay Zekası
    updateAutonomousOfficeAI(deltaTime, time);

    // 5. Yumuşak Kamera Geçişi
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

    // 6. Controls
    if (officeControls) {
        officeControls.update();
    }

    // 7. Baloncukları Yansıt
    updateBubblePositions();

    // 8. Render
    if (officeRenderer && officeScene && officeCamera) {
        officeRenderer.render(officeScene, officeCamera);
    }
}

// -------------------------------------------------------------
// CANLI VERİ ENTEGRASYONU (API/DATA)
// -------------------------------------------------------------
let lastKnownTradeStatus = null;

function updateOffice3DData(data) {
    if (!data) return;

    const btc = data.btc_regime || {};
    const positions = data.active_positions || [];
    const logs = data.scanner_logs || [];
    const statusPill = document.getElementById('officeStatusPill');

    // Kârlı pozisyon kontrolü (Yeni pozisyon kâra geçtiğinde konfeti patlat!)
    if (positions.length > 0) {
        const pos = positions[0];
        const pnl = Number(pos.unrealized_pnl_pct || 0);
        if (pnl > 0.5 && lastKnownTradeStatus !== 'PROFIT') {
            lastKnownTradeStatus = 'PROFIT';
            triggerOfficeConfetti();
        }
    } else {
        lastKnownTradeStatus = null;
    }

    // 1. Dev Ekranda İkili Görünümü Güncelle
    renderBigWallScreenContent({
        btcPrice: btc.btc_price ? Number(btc.btc_price).toLocaleString('en-US', {minimumFractionDigits: 1}) : '76,500.0',
        btcStatus: `${btc.status || 'DEAD_CHOP'} (4s Bant: %${btc.range_pct || '0.40'})`,
        activePositions: positions
    });
    if (bigWallTexture) bigWallTexture.needsUpdate = true;

    // 2. Canlı İşlem Baloncuğu
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
                scr.material.color.setHex(glowColor);
            }
        });

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
                scr.material.color.setHex(0x0284c7);
            }
        });
        if (statusPill) {
            statusPill.innerHTML = `👑 Efe Masada | Piyasayı Gözlüyor`;
            statusPill.style.color = '#94a3b8';
        }
    }

    // 3. Canlı Veriye Göre Cümleler
    if (bubbleAnchors.boss.bodyEl) {
        if (positions.length > 0) {
            bubbleAnchors.boss.bodyEl.innerText = "İşlem açık beyler! Hedeflere sadık kalın, stop seviyesini koruyun.";
        } else if (btc.status === 'DEAD_CHOP') {
            bubbleAnchors.boss.bodyEl.innerText = "Piyasada ölü testere var. Acele işlem yok, sermaye koruma kuralımız #1!";
        } else if (btc.status === 'BULLISH') {
            bubbleAnchors.boss.bodyEl.innerText = "BTC yukarı yönlü kırılımda. En güçlü pariteyi önüme getirin!";
        }
    }

    if (bubbleAnchors.scanner.bodyEl && logs.length > 0) {
        bubbleAnchors.scanner.bodyEl.innerText = `Radar: ${logs[0].symbol || 'PARİTE'} incelendi [${logs[0].status || 'OK'}].`;
    }

    if (bubbleAnchors.ta.bodyEl) {
        bubbleAnchors.ta.bodyEl.innerText = `BTC 4s bant daralması: %${btc.range_pct || '0.40'}. EMA & Bollinger sıkışması var.`;
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
