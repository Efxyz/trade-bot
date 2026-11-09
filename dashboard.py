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
        .bubble-quant {
            background: rgba(99, 102, 241, 0.08);
            border-left: 3px solid #818cf8;
            color: #e0e7ff;
            font-weight: 500;
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

        .sims-bubble.quant {
            border-color: rgba(99, 102, 241, 0.5) !important;
            box-shadow: 0 8px 30px rgba(0, 0, 0, 0.5), 0 0 15px rgba(99, 102, 241, 0.25) !important;
        }
        .sims-bubble.quant::after {
            border-top-color: rgba(99, 102, 241, 0.7);
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
                    <!-- Quant Simulation Agent Bubble -->
                    <div id="bubble-quant" class="sims-bubble quant" onclick="setOfficeCamera('table')" title="Tıkla: Masaya Yaklaş">
                        <div class="sims-bubble-header" style="color: #818cf8;">🎲 KUANT SİMÜLASYON</div>
                        <div class="sims-bubble-body" id="text-quant">10,000 Monte Carlo fiyat yolu koşturuldu, TP olasılığı %70+ filtrede!</div>
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

        // 3D Ofis Başlatma Köprüsü (Hata Korumalı)
        function initOrResizeOffice3D() {
            try {
                if (typeof init3DOffice === 'function' && !officeInitialized) {
                    init3DOffice();
                } else if (typeof resizeOffice3D === 'function') {
                    resizeOffice3D();
                }
            } catch (e) {
                console.error("Office init safeguard error:", e);
            }
        }

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
                try {
                    initOrResizeOffice3D();
                } catch (e) {
                    console.error("switchLeftView office error:", e);
                }
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
                            else if (b.role === 'QUANT') { roleClass = 'bubble-quant'; roleColor = '#818cf8'; }

                            let metricsHtml = '';
                            if (b.metrics) {
                                const isWin = b.metrics.vote === 'APPROVED';
                                metricsHtml = `
                                    <div style="display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; font-size: 10px; font-family: monospace;">
                                        <span style="background: rgba(99,102,241,0.18); border: 1px solid rgba(99,102,241,0.35); padding: 2px 6px; border-radius: 4px; color: #a5b4fc;">🎲 ${b.metrics.simulations || 10000} Yol</span>
                                        <span style="background: rgba(34,197,94,0.18); border: 1px solid rgba(34,197,94,0.35); padding: 2px 6px; border-radius: 4px; color: #4ade80;">TP İhtimali: %${b.metrics.win_rate}</span>
                                        <span style="background: rgba(239,68,68,0.18); border: 1px solid rgba(239,68,68,0.35); padding: 2px 6px; border-radius: 4px; color: #f87171;">SL Riski: %${b.metrics.loss_rate}</span>
                                        <span style="background: rgba(56,189,248,0.18); border: 1px solid rgba(56,189,248,0.35); padding: 2px 6px; border-radius: 4px; color: #38bdf8;">Beklenti: +${b.metrics.expectancy_r}R</span>
                                        <span style="background: ${isWin ? 'rgba(34,197,94,0.25)' : 'rgba(239,68,68,0.25)'}; border: 1px solid ${isWin ? '#22c55e' : '#ef4444'}; padding: 2px 6px; border-radius: 4px; color: #fff; font-weight: 700;">${isWin ? '🟢 ONAYLANDI' : '🔴 VETO'}</span>
                                    </div>
                                `;
                            }

                            bubblesHtml += `
                                <div class="dialogue-bubble ${roleClass}">
                                    <div class="speaker-title" style="color: ${roleColor};">
                                        <span>${b.avatar || '💬'}</span>
                                        <span>${b.agent_name || b.role}</span>
                                    </div>
                                    <div>${b.argument || ''}</div>
                                    ${metricsHtml}
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
   🎮 3D SİMS TARZI YAPAY ZEKA TİCARET OFİSİ (THREE.JS ENGINE) - v5.1.0
   Patron Efe Özel Sürümü:
   1. Duvar Tıkanması Çözüldü: Ön duvar ve tavan kaldırıldı; Kuşbakışı ve tüm açılardan %100 net görünüm.
   2. Masada Gerçek Oturuş: Üst bacaklar (thighs) yere tam paralel masaya uzanır, alt bacaklar dik iner.
   3. Masa Rengi Sabit & Tek Renk: Renk değiştirmeyen, parlamayan lüks koyu mat füme trading masası.
   4. Köşe Tuvalet & Açılır-Kapanır Kapı: Eleman kapıyı açar, içeri girer, kapı kapanır, ihtiyaç giderilir.
   5. Lavabo & El Yıkama: Tuvaletten çıkan eleman yanındaki aynalı lavaboya geçer, ellerini sabunla yıkar.
   6. Genişletilmiş Oturma & PlayStation Lounge: Ekstra kanepeler, 65" TV, PS5 konsolu ve animasyonlu oyun.
   7. Köşeye Alınan Oyun Alanı: Masa tenisi ve langırt köşeye çekildi, Mehmet & Berat izleme bankı eklendi.
   8. Mehmet & Berat Çoklu Dinlenme: PS5 koltuğu, çay köşesi, langırt ve masa tenisi arasında keyifli goygoy.
   ========================================================================== */

let officeScene, officeCamera, officeRenderer, officeControls;
let officeInitialized = false;
let officeAnimFrameId = null;

// WC Kapısı & Işığı & Lavabo
let wcDoorGroup = null;
let wcDoorTargetRot = 0;
let portableWcLight = null;

// TV & PlayStation Ekranı
let tvScreenCanvas = null;
let tvScreenCtx = null;
let tvScreenTexture = null;
let tvScreenMesh = null;

// Karakterler & Ajanlar
const friends = {};
const agents = {};
let bossGroup = null;
let bossHeadMesh = null;
let plumbobMesh = null;

// Masa Monitörleri ve Ekranlar
let officeDeskScreens = [];
let bigWallTexture = null;
let bigWallCtx = null;
let bigWallScreenMesh = null;

// Konfeti Parçacık Sistemi
let confettiParticles = [];
let confettiActive = false;
let lastKnownTradeStatus = null;

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
    quant: { pos: null, el: null, bodyEl: null, isSpeaking: false },
    mehmet: { pos: null, el: null, bodyEl: null, isSpeaking: false },
    berat: { pos: null, el: null, bodyEl: null, isSpeaking: false },
    trade: { pos: null, el: null, bodyEl: null, isSpeaking: false }
};

// -------------------------------------------------------------
// WEB AUDIO AMBİYANS & GERÇEKÇİ OFİS SESLERİ
// -------------------------------------------------------------
let officeAudioCtx = null;
let isOfficeAudioMuted = true;

function initOfficeAudio() {
    if (!officeAudioCtx) {
        const AudioContext = window.AudioContext || window.webkitAudioContext;
        if (AudioContext) officeAudioCtx = new AudioContext();
    }
    if (officeAudioCtx && officeAudioCtx.state === 'suspended') {
        officeAudioCtx.resume();
    }
}

function playOfficeSound(type) {
    if (isOfficeAudioMuted) return;
    initOfficeAudio();
    if (!officeAudioCtx) return;

    const ctx = officeAudioCtx;
    const now = ctx.currentTime;

    if (type === 'click') {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = 'sine';
        osc.frequency.setValueAtTime(800, now);
        osc.frequency.exponentialRampToValueAtTime(300, now + 0.04);
        gain.gain.setValueAtTime(0.08, now);
        gain.gain.linearRampToValueAtTime(0.001, now + 0.04);
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.start(now);
        osc.stop(now + 0.05);
    } else if (type === 'chime') {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = 'triangle';
        osc.frequency.setValueAtTime(523.25, now);
        osc.frequency.setValueAtTime(659.25, now + 0.08);
        gain.gain.setValueAtTime(0.07, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.35);
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.start(now);
        osc.stop(now + 0.36);
    } else if (type === 'talk') {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = 'sine';
        const baseFreq = 380 + Math.random() * 140;
        osc.frequency.setValueAtTime(baseFreq, now);
        osc.frequency.linearRampToValueAtTime(baseFreq + 60, now + 0.05);
        osc.frequency.linearRampToValueAtTime(baseFreq - 30, now + 0.12);
        gain.gain.setValueAtTime(0.05, now);
        gain.gain.linearRampToValueAtTime(0.001, now + 0.14);
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.start(now);
        osc.stop(now + 0.15);
    } else if (type === 'door') {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = 'sawtooth';
        osc.frequency.setValueAtTime(140, now);
        osc.frequency.linearRampToValueAtTime(90, now + 0.12);
        gain.gain.setValueAtTime(0.06, now);
        gain.gain.linearRampToValueAtTime(0.001, now + 0.12);
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.start(now);
        osc.stop(now + 0.13);
    } else if (type === 'water') {
        // Lavaboda el yıkama su sesi
        try {
            const bufferSize = ctx.sampleRate * 0.4;
            const buffer = ctx.createBuffer(1, bufferSize, ctx.sampleRate);
            const data = buffer.getChannelData(0);
            for (let i = 0; i < bufferSize; i++) {
                data[i] = (Math.random() * 2 - 1) * Math.exp(-i / (bufferSize * 0.6));
            }
            const noise = ctx.createBufferSource();
            noise.buffer = buffer;
            const filter = ctx.createBiquadFilter();
            filter.type = 'bandpass';
            filter.frequency.value = 1200;
            filter.Q.value = 1.5;
            const gain = ctx.createGain();
            gain.gain.setValueAtTime(0.05, now);
            gain.gain.exponentialRampToValueAtTime(0.001, now + 0.4);
            noise.connect(filter);
            filter.connect(gain);
            gain.connect(ctx.destination);
            noise.start(now);
            noise.stop(now + 0.4);
        } catch(e) {}
    } else if (type === 'pingpong') {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = 'sine';
        osc.frequency.setValueAtTime(1100, now);
        osc.frequency.exponentialRampToValueAtTime(400, now + 0.05);
        gain.gain.setValueAtTime(0.09, now);
        gain.gain.linearRampToValueAtTime(0.001, now + 0.05);
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.start(now);
        osc.stop(now + 0.06);
    } else if (type === 'confetti') {
        for (let i = 0; i < 4; i++) {
            setTimeout(() => {
                const osc = ctx.createOscillator();
                const gain = ctx.createGain();
                osc.type = 'triangle';
                const f = 400 + i * 220;
                osc.frequency.setValueAtTime(f, ctx.currentTime);
                osc.frequency.exponentialRampToValueAtTime(f * 2.2, ctx.currentTime + 0.18);
                gain.gain.setValueAtTime(0.09, ctx.currentTime);
                gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.22);
                osc.connect(gain);
                gain.connect(ctx.destination);
                osc.start(ctx.currentTime);
                osc.stop(ctx.currentTime + 0.23);
            }, i * 90);
        }
    } else if (type === 'tea') {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = 'sine';
        osc.frequency.setValueAtTime(450, now);
        osc.frequency.linearRampToValueAtTime(650, now + 0.22);
        gain.gain.setValueAtTime(0.04, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.24);
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.start(now);
        osc.stop(now + 0.25);
    }
}

function toggleOfficeSound() {
    isOfficeAudioMuted = !isOfficeAudioMuted;
    const btn = document.getElementById('btnOfficeAudio');
    if (btn) {
        btn.innerText = isOfficeAudioMuted ? '🔇' : '🔊';
        btn.style.color = isOfficeAudioMuted ? '#94a3b8' : '#22c55e';
    }
    if (!isOfficeAudioMuted) {
        initOfficeAudio();
        playOfficeSound('chime');
    }
}

// -------------------------------------------------------------
// SIRAYLA KONUŞMA SİSTEMİ (ACTIVE SPEAKER LOCK)
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
// 🎉 KONFETİ SİSTEMİ
// -------------------------------------------------------------
function triggerOfficeConfetti() {
    playOfficeSound('confetti');

    // Çalışanların kollarını kaldırıp sevinmesi
    Object.values(agents).forEach(ag => {
        if (ag && ag.leftArm && ag.rightArm) {
            ag.leftArm.rotation.x = -Math.PI / 1.5;
            ag.rightArm.rotation.x = -Math.PI / 1.5;
            setTimeout(() => {
                if (ag.state === 'SEATED_WORKING') {
                    ag.leftArm.rotation.x = Math.PI / 4;
                    ag.rightArm.rotation.x = Math.PI / 4;
                }
            }, 3000);
        }
    });

    triggerSpeech('boss', "🎉 Hedef Vuruldu! Kâr Kasada! Harika disiplin beyler!", 5000);

    const colors = [0x22c55e, 0x3b82f6, 0xf59e0b, 0xec4899, 0xa855f7, 0x06b6d4, 0xffffff];
    const confettiGeo = new THREE.BoxGeometry(0.08, 0.08, 0.005);

    for (let i = 0; i < 140; i++) {
        const mat = new THREE.MeshBasicMaterial({
            color: colors[Math.floor(Math.random() * colors.length)],
            side: THREE.DoubleSide
        });
        const mesh = new THREE.Mesh(confettiGeo, mat);

        const x = (Math.random() - 0.5) * 5.0;
        const y = 3.5 + Math.random() * 2.5;
        const z = (Math.random() - 0.5) * 4.5;
        mesh.position.set(x, y, z);

        mesh.rotation.x = Math.random() * Math.PI * 2;
        mesh.rotation.y = Math.random() * Math.PI * 2;
        mesh.rotation.z = Math.random() * Math.PI * 2;

        officeScene.add(mesh);

        confettiParticles.push({
            mesh: mesh,
            vx: (Math.random() - 0.5) * 0.8,
            vy: -1.0 - Math.random() * 1.4,
            vz: (Math.random() - 0.5) * 0.8,
            rotSpeedX: (Math.random() - 0.5) * 8.0,
            rotSpeedY: (Math.random() - 0.5) * 8.0,
            rotSpeedZ: (Math.random() - 0.5) * 8.0,
            life: 3.5 + Math.random() * 1.5
        });
    }

    confettiActive = true;
}

function updateConfetti(deltaTime) {
    if (!confettiActive || confettiParticles.length === 0) return;

    for (let i = confettiParticles.length - 1; i >= 0; i--) {
        const p = confettiParticles[i];
        p.life -= deltaTime;
        p.mesh.position.x += p.vx * deltaTime;
        p.mesh.position.y += p.vy * deltaTime;
        p.mesh.position.z += p.vz * deltaTime;

        p.mesh.rotation.x += p.rotSpeedX * deltaTime;
        p.mesh.rotation.y += p.rotSpeedY * deltaTime;
        p.mesh.rotation.z += p.rotSpeedZ * deltaTime;

        if (p.mesh.position.y < 0.78 || p.life <= 0) {
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
// 🎮 3D OFİS MOTORU BAŞLATMA
// -------------------------------------------------------------
function init3DOffice() {
    if (officeInitialized) return;
    const target = document.getElementById('officeCanvasTarget');
    if (!target) return;

    let width = target.clientWidth || target.offsetWidth;
    let height = target.clientHeight || target.offsetHeight;
    if (!width || width < 100) width = 800;
    if (!height || height < 100) height = 520;

    // 1. Sahne
    officeScene = new THREE.Scene();
    officeScene.background = new THREE.Color(0x0a0f1d);

    // 2. Kamera
    officeCamera = new THREE.PerspectiveCamera(38, width / height, 0.1, 100);
    camCurrentLook = new THREE.Vector3(0, 1.1, 0);
    officeCamera.position.set(0, 2.2, 0.5);
    officeCamera.lookAt(camCurrentLook);

    // 3. Renderer
    officeRenderer = new THREE.WebGLRenderer({
        antialias: true,
        powerPreference: 'high-performance',
        alpha: false
    });
    officeRenderer.setSize(width, height);
    officeRenderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    officeRenderer.shadowMap.enabled = false; // Masa gölge çizgilenme bug'ını tamamen bitirir!
    target.innerHTML = '';
    target.appendChild(officeRenderer.domElement);

    // 4. Orbit Controls
    if (typeof THREE.OrbitControls !== 'undefined') {
        officeControls = new THREE.OrbitControls(officeCamera, officeRenderer.domElement);
        officeControls.enableDamping = true;
        officeControls.dampingFactor = 0.06;
        officeControls.maxPolarAngle = Math.PI / 2.05;
        officeControls.minDistance = 2.0;
        officeControls.maxDistance = 22;
        officeControls.target.copy(camCurrentLook);
        officeControls.rotateSpeed = 0.85;
        officeControls.zoomSpeed = 1.0;
        officeControls.touches = {
            ONE: THREE.TOUCH.ROTATE,
            TWO: THREE.TOUCH.DOLLY_PAN
        };
    }

    // 5. Işıklandırma (Masa Parlama Bug'ı Sıfırlandı, Yumuşak Doğal Işık)
    setupSoftOfficeLighting();

    // 6. DUVAR ENGELİ KALDIRILMIŞ PENTHOUSE OFİS (Ön Duvar & Tavan Yok, %100 Açık Görünüm)
    buildLuxuryPenthouseOffice();

    // 7. TRADING MASASI (Sabit Tek Renk, Renk Değiştirmeyen Lüks Mat Füme Ahşap)
    buildTradingDesk();

    // 8. 👑 BAŞ KOLTUK / PATRON: EFE (Bacaklar Yere Tam Paralel Oturuş)
    buildBossEfe();

    // 9. EFE'NİN ARKASINDAKİ DEV İKİLİ DUVAR EKRANI (Canlı BTC + Kâr/Zarar)
    buildGiantWallDualScreen();

    // 10. 5 UZMAN AJAN (Bacaklar Yere Tam Paralel Oturuş, Elemana Bakan Kavisli Monitörler)
    buildSpecialistAgents();

    // 11. KÖŞE TUVALET (Açılır Kapı) & LAVABO (El Yıkama Aynalı Tezgah)
    buildCornerRestroomAndSink(-9.2, 0, -4.5);

    // 12. GENİŞLETİLMİŞ OTURMA & PLAYSTATION 5 LOUNGE (Ekstra Kanepeler, TV, PS5 Konsolu)
    buildExpandedLoungeAndPS5();

    // 13. SEMA VERLİ TÜRK ÇAYI KÖŞESİ
    buildTurkishTeaCorner(-5.8, 0, -4.2);

    // 14. KÖŞEYE ALINAN OYUN ALANI (Masa Tenisi, Langırt, İzleme Bankı)
    buildCornerGameArea();

    // 15. 🏓 ⚽ PATRONUN ARKADAŞLARI: MEHMET & BERAT (Sıfır İş, Goygoy, PS5, Çay, Langırt)
    buildFriendsMehmetAndBerat();

    // 16. Çapa Noktalarını DOM Elementlerine Bağla
    bindBubbleElements();

    officeInitialized = true;
    setTimeout(resizeOffice3D, 50);
    setTimeout(resizeOffice3D, 200);
    setTimeout(resizeOffice3D, 600);

    setOfficeCamera('boss');

    setTimeout(() => {
        triggerSpeech('boss', "Piyasayı tarayın beyler, acele yok! Disiplin #1 kuralımız.", 6000);
    }, 1200);

    setTimeout(() => {
        triggerSpeech('mehmet', "Berat PS5 kolunu hazırla kanka, rövanş maçı var!", 5000);
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
// IŞIKLANDIRMA SİSTEMİ (MASADA PARLAMA BUG'I SIFIR)
// -------------------------------------------------------------
function setupSoftOfficeLighting() {
    // 1. Doğal, yumuşak, gözü almayan ofis ortam ışığı
    const ambientLight = new THREE.AmbientLight(0xdce5f5, 0.95);
    officeScene.add(ambientLight);

    // 2. Yönlü difüze ışık (Gölgeler kapalı, çizgilenme yok)
    const ceilingLight = new THREE.DirectionalLight(0xfff8ee, 0.45);
    ceilingLight.position.set(3, 8, 4);
    officeScene.add(ceilingLight);

    // 3. Efe'nin arkasındaki duvara yumuşak estetik fon ışığı
    const backWallGlow = new THREE.PointLight(0x38bdf8, 0.5, 9);
    backWallGlow.position.set(0, 4.8, -5.8);
    officeScene.add(backWallGlow);

    // 4. Oyun ve Dinlenme Alanı Yumuşak Noktasal Işıkları
    const gameSpot = new THREE.PointLight(0x38bdf8, 0.5, 8);
    gameSpot.position.set(7.5, 3.8, -1.0);
    officeScene.add(gameSpot);

    const loungeSpot = new THREE.PointLight(0xf59e0b, 0.6, 8);
    loungeSpot.position.set(-7.0, 3.8, 1.5);
    officeScene.add(loungeSpot);
}

// -------------------------------------------------------------
// DUVAR ENGELİ OLMAYAN LÜKS PENTHOUSE OFİS
// (Ön Duvar & Tavan Kaldırıldı - Kamera Asla Takılmaz/Engellenmez)
// -------------------------------------------------------------
function buildLuxuryPenthouseOffice() {
    // 1. Zemin (Lüks Koyu Parke)
    const floorGeo = new THREE.PlaneGeometry(24, 20);
    const floorMat = new THREE.MeshLambertMaterial({ color: 0x121724 });
    const floor = new THREE.Mesh(floorGeo, floorMat);
    floor.rotation.x = -Math.PI / 2;
    officeScene.add(floor);

    // 2. Lüks Halı
    const rugGeo = new THREE.PlaneGeometry(13.0, 9.5);
    const rugMat = new THREE.MeshLambertMaterial({ color: 0x0a0f1c });
    const rug = new THREE.Mesh(rugGeo, rugMat);
    rug.rotation.x = -Math.PI / 2;
    rug.position.set(0, 0.015, 0);
    officeScene.add(rug);

    // 3. ARKA DUVAR (z = -6.2, Lüks Akustik Ahşap Çıtalar)
    const backWall = new THREE.Mesh(new THREE.BoxGeometry(24, 7.5, 0.2), new THREE.MeshLambertMaterial({ color: 0x0f1422 }));
    backWall.position.set(0, 3.75, -6.2);
    officeScene.add(backWall);

    const slatMat = new THREE.MeshLambertMaterial({ color: 0x241a14 });
    for (let x = -11.5; x <= 11.5; x += 0.55) {
        if (x > -3.8 && x < 3.8) continue; // Dev ekranın arkasını boş bırak
        const slat = new THREE.Mesh(new THREE.BoxGeometry(0.12, 7.2, 0.05), slatMat);
        slat.position.set(x, 3.75, -6.08);
        officeScene.add(slat);
    }

    // 4. SOL VE SAĞ MİMARİ KESİT DUVARLAR (Sadece arka yarıda, kameranın önünü asla kapatmaz)
    const leftWallBack = new THREE.Mesh(new THREE.BoxGeometry(0.2, 6.5, 6.0), new THREE.MeshLambertMaterial({ color: 0x111624 }));
    leftWallBack.position.set(-11.5, 3.25, -3.2);
    officeScene.add(leftWallBack);

    const rightWallBack = new THREE.Mesh(new THREE.BoxGeometry(0.2, 6.5, 6.0), new THREE.MeshLambertMaterial({ color: 0x111624 }));
    rightWallBack.position.set(11.5, 3.25, -3.2);
    officeScene.add(rightWallBack);

    // Alçak lüks mimari süpürgelik bordürü (Ön tarafta şık ve ferah)
    const borderMat = new THREE.MeshLambertMaterial({ color: 0x1e293b });
    const leftBorder = new THREE.Mesh(new THREE.BoxGeometry(0.15, 0.40, 14.0), borderMat);
    leftBorder.position.set(-11.5, 0.20, 3.0);
    officeScene.add(leftBorder);

    const rightBorder = new THREE.Mesh(new THREE.BoxGeometry(0.15, 0.40, 14.0), borderMat);
    rightBorder.position.set(11.5, 0.20, 3.0);
    officeScene.add(rightBorder);

    const frontBorder = new THREE.Mesh(new THREE.BoxGeometry(23.0, 0.40, 0.15), borderMat);
    frontBorder.position.set(0, 0.20, 8.5);
    officeScene.add(frontBorder);
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

    // Arka Plan
    ctx.fillStyle = '#090d16';
    ctx.fillRect(0, 0, 1024, 512);

    // Ortadan Bölücü İnce Çizgi
    ctx.strokeStyle = '#1e293b';
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.moveTo(512, 10);
    ctx.lineTo(512, 502);
    ctx.stroke();

    // ================= SOL PANEL: CANLI BTC (FUTURES) =================
    ctx.fillStyle = '#0f172a';
    ctx.fillRect(15, 15, 482, 482);

    ctx.fillStyle = '#38bdf8';
    ctx.font = 'bold 22px Inter, sans-serif';
    ctx.fillText('⚡ BTC/USDT FUTURES (4S REJİM)', 35, 52);

    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 38px monospace';
    ctx.fillText(`$${info.btcPrice || '76,500'}`, 35, 105);

    ctx.fillStyle = '#94a3b8';
    ctx.font = '16px Inter, sans-serif';
    ctx.fillText(`Rejim: ${info.btcStatus || 'DEAD_CHOP (Bant: %0.40)'}`, 35, 138);

    // Stilize Mum Grafiği
    const candleData = [
        { o: 60, c: 90, h: 105, l: 45, up: true },
        { o: 90, c: 75, h: 110, l: 70, up: false },
        { o: 75, c: 120, h: 135, l: 65, up: true },
        { o: 120, c: 110, h: 140, l: 100, up: false },
        { o: 110, c: 145, h: 160, l: 105, up: true },
        { o: 145, c: 135, h: 155, l: 125, up: false },
        { o: 135, c: 175, h: 190, l: 130, up: true },
        { o: 175, c: 160, h: 180, l: 150, up: false },
        { o: 160, c: 195, h: 210, l: 155, up: true },
        { o: 195, c: 185, h: 200, l: 175, up: false },
        { o: 185, c: 220, h: 235, l: 180, up: true }
    ];

    const chartBaseY = 440;
    candleData.forEach((c, idx) => {
        const cx = 55 + idx * 38;
        const color = c.up ? '#10b981' : '#ef4444';
        ctx.strokeStyle = color;
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(cx, chartBaseY - c.h);
        ctx.lineTo(cx, chartBaseY - c.l);
        ctx.stroke();

        ctx.fillStyle = color;
        const bodyTop = chartBaseY - Math.max(c.o, c.c);
        const bodyHeight = Math.max(Math.abs(c.c - c.o), 4);
        ctx.fillRect(cx - 10, bodyTop, 20, bodyHeight);
    });

    // ================= SAĞ PANEL: AÇIK POZİSYONLAR & PnL =================
    ctx.fillStyle = '#0f172a';
    ctx.fillRect(527, 15, 482, 482);

    ctx.fillStyle = '#f59e0b';
    ctx.font = 'bold 22px Inter, sans-serif';
    ctx.fillText('📊 AÇIK POZİSYON & PnL TAKİBİ', 547, 52);

    const positions = info.activePositions || [];
    if (positions.length === 0) {
        ctx.fillStyle = '#64748b';
        ctx.font = 'bold 20px Inter, sans-serif';
        ctx.fillText('💤 AKTİF İŞLEM YOK', 547, 180);
        ctx.font = '16px Inter, sans-serif';
        ctx.fillText('200+ Parite 15M Radar Taramasında.', 547, 215);
        ctx.fillText('Sermaye Koruma Kalkanı Devrede: %1.5 Risk', 547, 245);

        ctx.strokeStyle = '#1e293b';
        ctx.strokeRect(547, 280, 440, 160);
        ctx.fillStyle = '#38bdf8';
        ctx.font = '15px Inter, sans-serif';
        ctx.fillText('🏛️ Yatırım Komitesi: Chop Piyasada Beklemede', 567, 320);
        ctx.fillStyle = '#22c55e';
        ctx.fillText('🛡️ Kasa Kalkanı: %100 Hazır', 567, 360);
        ctx.fillStyle = '#94a3b8';
        ctx.fillText('📡 Tarama: Her 15 sn rotasyon canlı', 567, 400);
    } else {
        positions.slice(0, 2).forEach((pos, i) => {
            const cardY = 95 + i * 185;
            const pnl = Number(pos.unrealized_pnl_pct || 0);
            const isProfit = pnl >= 0;

            ctx.fillStyle = '#1e293b';
            ctx.fillRect(547, cardY, 442, 165);
            ctx.strokeStyle = isProfit ? '#10b981' : '#ef4444';
            ctx.lineWidth = 2;
            ctx.strokeRect(547, cardY, 442, 165);

            ctx.fillStyle = '#ffffff';
            ctx.font = 'bold 22px Inter, sans-serif';
            ctx.fillText(`${pos.symbol || 'PARİTE'} ${pos.direction || 'LONG'} ${pos.leverage || '5'}x`, 567, cardY + 38);

            ctx.fillStyle = isProfit ? '#10b981' : '#ef4444';
            ctx.font = 'bold 32px monospace';
            const pnlStr = (isProfit ? '+' : '') + pnl.toFixed(2) + '%';
            ctx.fillText(pnlStr, 567, cardY + 85);

            ctx.fillStyle = '#94a3b8';
            ctx.font = '15px Inter, sans-serif';
            ctx.fillText(`Giriş: $${pos.entry_price || '0'} | Fiyat: $${pos.live_price || '0'}`, 567, cardY + 120);
            ctx.fillText(`Kâr: $${pos.pnl_usd || '0.00'} | Süre: ${pos.elapsed_str || '0m'}`, 567, cardY + 145);
        });
    }
}

// -------------------------------------------------------------
// SEMA VERLİ TÜRK ÇAYI KÖŞESİ
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
// 🛋️ GENİŞLETİLMİŞ LOUNGE & PLAYSTATION 5 MERKEZİ
// (Ekstra Kanepeler, 65" TV, PS5 Konsolu, Oyun Ekranı)
// -------------------------------------------------------------
function buildExpandedLoungeAndPS5() {
    const loungeGroup = new THREE.Group();
    loungeGroup.position.set(-7.2, 0, 1.5);

    const sofaMat = new THREE.MeshLambertMaterial({ color: 0x1e293b });
    const sofaMat2 = new THREE.MeshLambertMaterial({ color: 0x283548 });

    // 1. ANA KANEPE (3 Kişilik Deri Kanepe - TV Karşısı)
    const sofa1 = new THREE.Group();
    sofa1.position.set(0, 0, -0.6);

    const s1Seat = new THREE.Mesh(new THREE.BoxGeometry(2.0, 0.28, 0.85), sofaMat);
    s1Seat.position.y = 0.35;
    sofa1.add(s1Seat);

    const s1Back = new THREE.Mesh(new THREE.BoxGeometry(2.0, 0.70, 0.22), sofaMat);
    s1Back.position.set(0, 0.72, -0.32);
    sofa1.add(s1Back);

    [-0.95, 0.95].forEach(sx => {
        const arm = new THREE.Mesh(new THREE.BoxGeometry(0.20, 0.50, 0.85), sofaMat);
        arm.position.set(sx, 0.50, 0);
        sofa1.add(arm);
    });
    loungeGroup.add(sofa1);

    // 2. EKSTRA KANEPE / BERJER (2 Kişilik Lüks Koltuk - Mehmet & Berat İçin)
    const sofa2 = new THREE.Group();
    sofa2.position.set(2.0, 0, 0.6);
    sofa2.rotation.y = -Math.PI / 2; // TV'ye ve ortaya dönük

    const s2Seat = new THREE.Mesh(new THREE.BoxGeometry(1.5, 0.28, 0.80), sofaMat2);
    s2Seat.position.y = 0.35;
    sofa2.add(s2Seat);

    const s2Back = new THREE.Mesh(new THREE.BoxGeometry(1.5, 0.70, 0.20), sofaMat2);
    s2Back.position.set(0, 0.72, -0.30);
    sofa2.add(s2Back);

    [-0.70, 0.70].forEach(sx => {
        const arm = new THREE.Mesh(new THREE.BoxGeometry(0.18, 0.50, 0.80), sofaMat2);
        arm.position.set(sx, 0.50, 0);
        sofa2.add(arm);
    });
    loungeGroup.add(sofa2);

    // 3. CAM SEHPA & PLAYSTATION KOLLARI
    const coffeeTable = new THREE.Group();
    coffeeTable.position.set(0, 0, 0.6);

    const tableLegMat = new THREE.MeshLambertMaterial({ color: 0x0f172a });
    const tableTop = new THREE.Mesh(new THREE.BoxGeometry(1.3, 0.04, 0.8), new THREE.MeshPhysicalMaterial({
        color: 0x38bdf8,
        transmission: 0.85,
        opacity: 0.7,
        transparent: true
    }));
    tableTop.position.y = 0.42;
    coffeeTable.add(tableTop);

    [[-0.55, -0.3], [0.55, -0.3], [-0.55, 0.3], [0.55, 0.3]].forEach(([lx, lz]) => {
        const leg = new THREE.Mesh(new THREE.CylinderGeometry(0.025, 0.025, 0.40, 12), tableLegMat);
        leg.position.set(lx, 0.20, lz);
        coffeeTable.add(leg);
    });

    // 🎮 PS5 Kolları Sehpa Üstünde
    [-0.2, 0.2].forEach(px => {
        const ctrl = new THREE.Mesh(new THREE.BoxGeometry(0.12, 0.03, 0.08), new THREE.MeshLambertMaterial({ color: 0xffffff }));
        ctrl.position.set(px, 0.45, 0);
        coffeeTable.add(ctrl);
    });
    loungeGroup.add(coffeeTable);

    // 4. MEDYA SEHPASI & 65" FLAT TV & PLAYSTATION 5 KONSOLU
    const tvStand = new THREE.Group();
    tvStand.position.set(-2.5, 0, 0.5);
    tvStand.rotation.y = Math.PI / 2; // Kanepelere dönük

    // Medya Konsolu
    const standMesh = new THREE.Mesh(new THREE.BoxGeometry(2.2, 0.48, 0.55), new THREE.MeshLambertMaterial({ color: 0x0f172a }));
    standMesh.position.y = 0.24;
    tvStand.add(standMesh);

    // PS5 Konsolu (Beyaz kavisli tasarım + mavi LED)
    const ps5 = new THREE.Mesh(new THREE.BoxGeometry(0.12, 0.38, 0.26), new THREE.MeshLambertMaterial({ color: 0xf8fafc }));
    ps5.position.set(0.7, 0.67, 0);
    tvStand.add(ps5);

    const ps5Led = new THREE.Mesh(new THREE.BoxGeometry(0.02, 0.35, 0.02), new THREE.MeshBasicMaterial({ color: 0x38bdf8 }));
    ps5Led.position.set(0.76, 0.67, 0);
    tvStand.add(ps5Led);

    // 65" TV Ekranı
    const tvFrame = new THREE.Mesh(new THREE.BoxGeometry(2.2, 1.3, 0.06), new THREE.MeshLambertMaterial({ color: 0x020617 }));
    tvFrame.position.set(0, 1.55, 0);
    tvStand.add(tvFrame);

    // TV Ekranı Dinamik Canvas (Canlı Video Oyunu Animasyonu)
    tvScreenCanvas = document.createElement('canvas');
    tvScreenCanvas.width = 512;
    tvScreenCanvas.height = 256;
    tvScreenCtx = tvScreenCanvas.getContext('2d');
    renderTVScreenGraphics(0);

    tvScreenTexture = new THREE.CanvasTexture(tvScreenCanvas);
    const tvDisplay = new THREE.Mesh(new THREE.PlaneGeometry(2.1, 1.2), new THREE.MeshBasicMaterial({ map: tvScreenTexture }));
    tvDisplay.position.set(0, 1.55, 0.035);
    tvStand.add(tvDisplay);

    loungeGroup.add(tvStand);
    officeScene.add(loungeGroup);
}

// TV Ekranında Animasyonlu Futbol/Oyun Döngüsü
function renderTVScreenGraphics(time) {
    if (!tvScreenCtx) return;
    const ctx = tvScreenCtx;

    // Yeşil Futbol Sahası
    ctx.fillStyle = '#15803d';
    ctx.fillRect(0, 0, 512, 256);

    // Beyaz Saha Çizgileri
    ctx.strokeStyle = '#ffffff';
    ctx.lineWidth = 4;
    ctx.strokeRect(20, 20, 472, 216);

    ctx.beginPath();
    ctx.moveTo(256, 20);
    ctx.lineTo(256, 236);
    ctx.stroke();

    ctx.beginPath();
    ctx.arc(256, 128, 45, 0, Math.PI * 2);
    ctx.stroke();

    // Hareket Eden Oyuncular & Top
    const ballX = 256 + Math.sin(time * 0.003) * 120;
    const ballY = 128 + Math.cos(time * 0.005) * 60;

    // Oyuncu 1 (Mehmet - Kırmızı)
    ctx.fillStyle = '#ef4444';
    ctx.beginPath();
    ctx.arc(ballX - 35, ballY - 10, 12, 0, Math.PI * 2);
    ctx.fill();

    // Oyuncu 2 (Berat - Mavi)
    ctx.fillStyle = '#3b82f6';
    ctx.beginPath();
    ctx.arc(ballX + 35, ballY + 10, 12, 0, Math.PI * 2);
    ctx.fill();

    // Top
    ctx.fillStyle = '#ffffff';
    ctx.beginPath();
    ctx.arc(ballX, ballY, 7, 0, Math.PI * 2);
    ctx.fill();

    // PS5 Skor Panosu
    ctx.fillStyle = 'rgba(15, 23, 42, 0.85)';
    ctx.fillRect(170, 25, 172, 34);
    ctx.fillStyle = '#f8fafc';
    ctx.font = 'bold 16px Inter, sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('MEHMET 2 - 1 BERAT', 256, 48);

    if (tvScreenTexture) tvScreenTexture.needsUpdate = true;
}

// -------------------------------------------------------------
// 🚻 KÖŞE TUVALET (AÇILIR KAPI) & AYNALI LAVABO (EL YIKAMA)
// -------------------------------------------------------------
function buildCornerRestroomAndSink(x, y, z) {
    const restroomGroup = new THREE.Group();
    restroomGroup.position.set(x, y, z);

    // 1. TUVALET KABİNİ (Sol ve arka duvarlar)
    const cabinMat = new THREE.MeshLambertMaterial({ color: 0x1e293b });
    const cabin = new THREE.Mesh(new THREE.BoxGeometry(1.6, 2.5, 1.6), cabinMat);
    cabin.position.y = 1.25;
    restroomGroup.add(cabin);

    // İç Mekan / Klozet (Kapı açıldığında içerisi görünür)
    const toiletBase = new THREE.Mesh(new THREE.CylinderGeometry(0.22, 0.18, 0.44, 14), new THREE.MeshLambertMaterial({ color: 0xffffff }));
    toiletBase.position.set(0, 0.22, -0.35);
    restroomGroup.add(toiletBase);

    const toiletTank = new THREE.Mesh(new THREE.BoxGeometry(0.44, 0.45, 0.22), new THREE.MeshLambertMaterial({ color: 0xffffff }));
    toiletTank.position.set(0, 0.55, -0.65);
    restroomGroup.add(toiletTank);

    // 2. AÇILIR-KAPANIR KABİN KAPISI (Menteşesi kenarda döner!)
    wcDoorGroup = new THREE.Group();
    wcDoorGroup.position.set(-0.70, 0, 0.81); // Menteşe noktası

    const doorLeaf = new THREE.Mesh(new THREE.BoxGeometry(1.35, 2.2, 0.05), new THREE.MeshLambertMaterial({ color: 0x334155 }));
    doorLeaf.position.set(0.675, 1.15, 0); // Menteşeden sağa uzanır
    wcDoorGroup.add(doorLeaf);

    const handle = new THREE.Mesh(new THREE.BoxGeometry(0.04, 0.14, 0.06), new THREE.MeshLambertMaterial({ color: 0xd4d4d8 }));
    handle.position.set(1.20, 1.05, 0.04);
    wcDoorGroup.add(handle);

    restroomGroup.add(wcDoorGroup);

    // Tabela: "WC / LAVABO"
    const sign = new THREE.Mesh(new THREE.BoxGeometry(0.8, 0.22, 0.06), new THREE.MeshBasicMaterial({ color: 0x0284c7 }));
    sign.position.set(0, 2.35, 0.82);
    restroomGroup.add(sign);

    // Dolu/Boş Durum Işığı (Yeşil = Boş, Kırmızı = Dolu)
    portableWcLight = new THREE.PointLight(0x10b981, 1.0, 3.5);
    portableWcLight.position.set(0, 2.35, 0.95);
    restroomGroup.add(portableWcLight);

    // 3. 🚰 AYNALI LAVABO TEZGAHI (TUVALETİN HEMEN YANINDA)
    const sinkGroup = new THREE.Group();
    sinkGroup.position.set(1.6, 0, 0); // Kabinin hemen sağında

    // Ahşap Dolaplı Tezgah
    const vanity = new THREE.Mesh(new THREE.BoxGeometry(0.9, 0.84, 0.65), new THREE.MeshLambertMaterial({ color: 0x0f172a }));
    vanity.position.y = 0.42;
    sinkGroup.add(vanity);

    // Beyaz Porselen Lavabo Çanağı
    const basin = new THREE.Mesh(new THREE.CylinderGeometry(0.24, 0.18, 0.14, 16), new THREE.MeshLambertMaterial({ color: 0xffffff }));
    basin.position.set(0, 0.90, 0);
    sinkGroup.add(basin);

    // Krom Modern Kuğu Batarya
    const faucet = new THREE.Mesh(new THREE.CylinderGeometry(0.02, 0.02, 0.22, 12), new THREE.MeshLambertMaterial({ color: 0xd4d4d8 }));
    faucet.position.set(0, 1.05, -0.18);
    sinkGroup.add(faucet);

    // Duvarda Ayna
    const mirror = new THREE.Mesh(new THREE.BoxGeometry(0.70, 0.95, 0.02), new THREE.MeshPhysicalMaterial({
        color: 0xe2e8f0,
        metalness: 0.95,
        roughness: 0.1
    }));
    mirror.position.set(0, 1.70, -0.32);
    sinkGroup.add(mirror);

    // Sabunluk
    const soap = new THREE.Mesh(new THREE.CylinderGeometry(0.04, 0.04, 0.12, 12), new THREE.MeshLambertMaterial({ color: 0x38bdf8 }));
    soap.position.set(0.30, 0.90, 0);
    sinkGroup.add(soap);

    restroomGroup.add(sinkGroup);
    officeScene.add(restroomGroup);
}

// -------------------------------------------------------------
// KÖŞEYE ALINAN OYUN ALANI (PING-PONG & LANGIRT & BANK)
// -------------------------------------------------------------
function buildCornerGameArea() {
    // 🏓 Masa Tenisi (Sağ arka köşede)
    const ppGroup = new THREE.Group();
    ppGroup.position.set(8.2, 0, -3.2);

    const ppTop = new THREE.Mesh(new THREE.BoxGeometry(2.4, 0.06, 1.4), new THREE.MeshLambertMaterial({ color: 0x0284c7 }));
    ppTop.position.y = 0.76;
    ppGroup.add(ppTop);

    const lineMat = new THREE.MeshBasicMaterial({ color: 0xffffff });
    const centerLine = new THREE.Mesh(new THREE.BoxGeometry(2.4, 0.005, 0.03), lineMat);
    centerLine.position.set(0, 0.795, 0);
    ppGroup.add(centerLine);

    const net = new THREE.Mesh(new THREE.BoxGeometry(0.04, 0.16, 1.5), new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.6 }));
    net.position.set(0, 0.87, 0);
    ppGroup.add(net);

    const legMat = new THREE.MeshLambertMaterial({ color: 0x0f172a });
    [[-1.0, -0.55], [1.0, -0.55], [-1.0, 0.55], [1.0, 0.55]].forEach(([lx, lz]) => {
        const leg = new THREE.Mesh(new THREE.CylinderGeometry(0.04, 0.04, 0.76, 12), legMat);
        leg.position.set(lx, 0.38, lz);
        ppGroup.add(leg);
    });
    officeScene.add(ppGroup);

    // ⚽ Langırt Masası (Hemen yanında)
    const foosballGroup = new THREE.Group();
    foosballGroup.position.set(8.2, 0, 0.5);

    const box = new THREE.Mesh(new THREE.BoxGeometry(1.6, 0.40, 0.95), new THREE.MeshLambertMaterial({ color: 0x991b1b }));
    box.position.y = 0.68;
    foosballGroup.add(box);

    const pitch = new THREE.Mesh(new THREE.PlaneGeometry(1.4, 0.75), new THREE.MeshBasicMaterial({ color: 0x15803d }));
    pitch.rotation.x = -Math.PI / 2;
    pitch.position.set(0, 0.75, 0);
    foosballGroup.add(pitch);

    [[-0.65, -0.38], [0.65, -0.38], [-0.65, 0.38], [0.65, 0.38]].forEach(([lx, lz]) => {
        const leg = new THREE.Mesh(new THREE.BoxGeometry(0.08, 0.70, 0.08), legMat);
        leg.position.set(lx, 0.35, lz);
        foosballGroup.add(leg);
    });
    officeScene.add(foosballGroup);

    // 🛋️ İzleme Bankı (Mehmet & Berat Oyun Seyir Koltuğu)
    const benchGroup = new THREE.Group();
    benchGroup.position.set(6.2, 0, 2.5);
    benchGroup.rotation.y = -Math.PI / 3;

    const benchSeat = new THREE.Mesh(new THREE.BoxGeometry(1.4, 0.12, 0.5), new THREE.MeshLambertMaterial({ color: 0x1e293b }));
    benchSeat.position.y = 0.42;
    benchGroup.add(benchSeat);

    const benchBack = new THREE.Mesh(new THREE.BoxGeometry(1.4, 0.45, 0.1), new THREE.MeshLambertMaterial({ color: 0x1e293b }));
    benchBack.position.set(0, 0.65, -0.2);
    benchGroup.add(benchBack);

    officeScene.add(benchGroup);
}

// -------------------------------------------------------------
// TRADING MASASI (TEK RENK, ASLA RENK DEĞİŞTİRMEYEN LÜKS MAT FÜME)
// -------------------------------------------------------------
function buildTradingDesk() {
    const tableGroup = new THREE.Group();

    // Genişlik: 2.0m, Uzunluk: 4.6m, Yükseklik: 0.78m
    const topGeo = new THREE.BoxGeometry(2.0, 0.06, 4.6);
    // Tek renk, sabit, koyu mat füme ahşap malzeme:
    const topMat = new THREE.MeshLambertMaterial({ color: 0x182030 });
    const tableTop = new THREE.Mesh(topGeo, topMat);
    tableTop.position.set(0, 0.78, 0);
    tableGroup.add(tableTop);

    // Çerçeve (Aynı sabit renkte)
    const trim = new THREE.Mesh(new THREE.BoxGeometry(2.02, 0.02, 4.62), topMat);
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
// 👑 BAŞ KOLTUK / PATRON: EFE (BACAKLAR YERE TAM PARALEL)
// -------------------------------------------------------------
function buildBossEfe() {
    // 1. Patron Döner Koltuğu
    const bossChair = new THREE.Group();
    bossChair.position.set(0, 0, -2.3);

    const seat = new THREE.Mesh(new THREE.BoxGeometry(0.75, 0.12, 0.70), new THREE.MeshLambertMaterial({ color: 0x111827 }));
    seat.position.y = 0.44;
    bossChair.add(seat);

    const back = new THREE.Mesh(new THREE.BoxGeometry(0.75, 0.95, 0.14), new THREE.MeshLambertMaterial({ color: 0x111827 }));
    back.position.set(0, 0.95, -0.32);
    bossChair.add(back);

    [-0.40, 0.40].forEach(ax => {
        const arm = new THREE.Mesh(new THREE.BoxGeometry(0.12, 0.45, 0.60), new THREE.MeshLambertMaterial({ color: 0xb45309 }));
        arm.position.set(ax, 0.65, 0);
        bossChair.add(arm);
    });

    const chairBase = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.05, 0.44, 16), new THREE.MeshLambertMaterial({ color: 0xd97706 }));
    chairBase.position.y = 0.22;
    bossChair.add(chairBase);
    officeScene.add(bossChair);

    // 2. Patron Efe Karakteri (Siyah Takım Elbise)
    bossGroup = new THREE.Group();
    bossGroup.position.set(0, 0, -2.3);

    const suitMat = new THREE.MeshLambertMaterial({ color: 0x090d16 });
    const skinMat = new THREE.MeshLambertMaterial({ color: 0xfbd0b0 });

    // 🦵 Bacaklar: Üst Bacak Yere Tam Paralel, Alt Bacak Yere Dik İner!
    const thighs = new THREE.Mesh(new THREE.BoxGeometry(0.42, 0.14, 0.38), suitMat);
    thighs.position.set(0, 0.44, 0.19); // Masaya doğru paralel uzanır
    bossGroup.add(thighs);

    const calves = new THREE.Mesh(new THREE.BoxGeometry(0.40, 0.40, 0.14), suitMat);
    calves.position.set(0, 0.20, 0.38); // Dizden yere dik iner
    bossGroup.add(calves);

    // Gövde
    const torso = new THREE.Mesh(new THREE.BoxGeometry(0.55, 0.58, 0.30), suitMat);
    torso.position.y = 0.74;
    bossGroup.add(torso);

    const collar = new THREE.Mesh(new THREE.BoxGeometry(0.20, 0.12, 0.02), new THREE.MeshLambertMaterial({ color: 0xffffff }));
    collar.position.set(0, 0.95, 0.16);
    bossGroup.add(collar);

    const tie = new THREE.Mesh(new THREE.BoxGeometry(0.08, 0.32, 0.025), new THREE.MeshLambertMaterial({ color: 0xb91c1c }));
    tie.position.set(0, 0.80, 0.17);
    bossGroup.add(tie);

    // Kollar (Masada dinlenir ve çalışır)
    const bossLeftArm = new THREE.Mesh(new THREE.BoxGeometry(0.12, 0.45, 0.12), suitMat);
    bossLeftArm.position.set(-0.34, 0.72, 0.16);
    bossLeftArm.rotation.x = Math.PI / 3.2;
    bossGroup.add(bossLeftArm);

    const bossRightArm = new THREE.Mesh(new THREE.BoxGeometry(0.12, 0.45, 0.12), suitMat);
    bossRightArm.position.set(0.34, 0.72, 0.16);
    bossRightArm.rotation.x = Math.PI / 3.2;
    bossGroup.add(bossRightArm);

    // Kafa
    const headGroup = new THREE.Group();
    headGroup.position.set(0, 1.18, 0);

    const head = new THREE.Mesh(new THREE.BoxGeometry(0.32, 0.34, 0.28), skinMat);
    headGroup.add(head);

    const hair = new THREE.Mesh(new THREE.BoxGeometry(0.34, 0.12, 0.30), new THREE.MeshLambertMaterial({ color: 0x171717 }));
    hair.position.set(0, 0.18, 0);
    headGroup.add(hair);

    bossHeadMesh = headGroup;
    bossGroup.add(headGroup);

    // Masadaki Laptop ve Altın İsimlik
    buildBossDeskItems(bossGroup);

    // Dönen Sims Plumbob'u (Işığı kaldırıldı, masaya yeşil ışık vurmaz!)
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

    // DİKKAT: plumbobLight kaldırıldı! Masada renk değişimi olmasını engeller.
    parentGroup.add(plumbobMesh);
}

function buildBossDeskItems(parentGroup) {
    const macBase = new THREE.Mesh(new THREE.BoxGeometry(0.48, 0.02, 0.32), new THREE.MeshLambertMaterial({ color: 0xd8e0e8 }));
    macBase.position.set(0, 0.82, 0.45);
    parentGroup.add(macBase);

    const macScreen = new THREE.Mesh(new THREE.BoxGeometry(0.48, 0.32, 0.02), new THREE.MeshBasicMaterial({ color: 0x0284c7 }));
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
// 5 UZMAN AJAN (BACAKLAR YERE TAM PARALEL OTURUŞ)
// -------------------------------------------------------------
function buildSpecialistAgents() {
    const agentConfigs = [
        {
            id: 'scanner',
            name: 'Scanner Ajanı',
            seatPos: [-1.55, 0, -0.75],
            seatRotY: Math.PI / 2, // Masaya dönük
            deskPos: [-0.60, 0.78, -0.75],
            suitColor: 0x0284c7,
            hairColor: 0x3f3f46,
            screenColor: 0x0369a1,
            hasGlasses: true
        },
        {
            id: 'ta',
            name: 'Teknik Analist',
            seatPos: [-1.55, 0, 0.75],
            seatRotY: Math.PI / 2, // Masaya dönük
            deskPos: [-0.60, 0.78, 0.75],
            suitColor: 0x9333ea,
            hairColor: 0x78350f,
            screenColor: 0x0369a1,
            hasGlasses: false
        },
        {
            id: 'risk',
            name: 'Risk Şefi',
            seatPos: [1.55, 0, -0.75],
            seatRotY: -Math.PI / 2, // Masaya dönük
            deskPos: [0.60, 0.78, -0.75],
            suitColor: 0xdc2626,
            hairColor: 0x18181b,
            screenColor: 0x0369a1,
            hasGlasses: false
        },
        {
            id: 'news',
            name: 'Haber & Makro',
            seatPos: [1.55, 0, 0.75],
            seatRotY: -Math.PI / 2, // Masaya dönük
            deskPos: [0.60, 0.78, 0.75],
            suitColor: 0xea580c,
            hairColor: 0x451a03,
            screenColor: 0x0369a1,
            hasGlasses: true
        },
        {
            id: 'chief',
            name: 'Baş Stratejist',
            seatPos: [1.35, 0, -1.8],
            seatRotY: -Math.PI / 2, // Masaya dönük
            deskPos: [0.95, 0.78, -1.5],
            suitColor: 0x059669,
            hairColor: 0x52525b,
            screenColor: 0x0369a1,
            hasGlasses: true
        },
        {
            id: 'quant',
            name: 'Kuant Simülasyon Uzmanı',
            seatPos: [-1.35, 0, -1.8],
            seatRotY: Math.PI / 2, // Masaya dönük (Chief'in tam karşısı)
            deskPos: [-0.95, 0.78, -1.5],
            suitColor: 0x4f46e5,   // Indigo Kuant Takım Elbisesi
            hairColor: 0x1e1b4b,
            screenColor: 0x6366f1, // Cyan/Indigo Kuant Fan Grafiği
            hasGlasses: true
        }
    ];

    agentConfigs.forEach(cfg => {
        createSingleWorker(cfg);
    });
}

function createSingleWorker(cfg) {
    const isRightSide = cfg.seatPos[0] > 0;

    // 1. BAĞIMSIZ DÖNER SANDALYE (Masada sabit kalır, eleman kalkarken döner)
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

    // 🦵 GERÇEKÇİ OTURUŞ: Üst bacak yere tam paralel, alt bacak yere dik iner!
    const legsGroup = new THREE.Group();

    // Üst Bacaklar (Thighs - Yere Tam Paralel!)
    const leftThigh = new THREE.Mesh(new THREE.BoxGeometry(0.13, 0.12, 0.36), clothMat);
    leftThigh.position.set(-0.13, 0.44, 0.18);
    legsGroup.add(leftThigh);

    const rightThigh = new THREE.Mesh(new THREE.BoxGeometry(0.13, 0.12, 0.36), clothMat);
    rightThigh.position.set(0.13, 0.44, 0.18);
    legsGroup.add(rightThigh);

    // Alt Bacaklar (Calves - Dizden yere dik iner)
    const leftCalf = new THREE.Mesh(new THREE.BoxGeometry(0.12, 0.38, 0.12), clothMat);
    leftCalf.position.set(-0.13, 0.21, 0.36);
    legsGroup.add(leftCalf);

    const rightCalf = new THREE.Mesh(new THREE.BoxGeometry(0.12, 0.38, 0.12), clothMat);
    rightCalf.position.set(0.13, 0.21, 0.36);
    legsGroup.add(rightCalf);

    bodyGroup.add(legsGroup);

    // Gövde
    const torso = new THREE.Mesh(new THREE.BoxGeometry(0.48, 0.52, 0.28), clothMat);
    torso.position.y = 0.70;
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

    // Kafa
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
        legsGroup: legsGroup,
        leftThigh: leftThigh,
        rightThigh: rightThigh,
        leftCalf: leftCalf,
        rightCalf: rightCalf,
        leftArm: leftArm,
        rightArm: rightArm,
        homePos: new THREE.Vector3(...cfg.seatPos),
        homeRotY: cfg.seatRotY,
        state: 'SEATED_WORKING',
        swivelProgress: 0,
        swivelTargetRot: 0,
        waypoints: [],
        currentWpIdx: 0,
        activityType: 0,
        destinationTimer: 0,
        destinationPhrase: ''
    };

    bubbleAnchors[cfg.id].pos = new THREE.Vector3(cfg.seatPos[0], 1.95, cfg.seatPos[2]);
    officeScene.add(agentGroup);
}

// Bacak Pozunu Ayarla (Oturuş: Üst Bacak Yere Paralel / Ayakta: Dik)
function setAgentLegsPose(ag, isSeated) {
    if (isSeated) {
        ag.leftThigh.position.set(-0.13, 0.44, 0.18);
        ag.leftThigh.scale.set(1, 1, 1);
        ag.rightThigh.position.set(0.13, 0.44, 0.18);
        ag.rightThigh.scale.set(1, 1, 1);

        ag.leftCalf.position.set(-0.13, 0.21, 0.36);
        ag.rightCalf.position.set(0.13, 0.21, 0.36);
    } else {
        // Ayakta yürürken bacaklar düz dik konuma geçer
        ag.leftThigh.position.set(-0.13, 0.30, 0);
        ag.leftThigh.scale.set(1, 1.4, 0.35);
        ag.rightThigh.position.set(0.13, 0.30, 0);
        ag.rightThigh.scale.set(1, 1.4, 0.35);

        ag.leftCalf.position.set(-0.13, 0.10, 0);
        ag.rightCalf.position.set(0.13, 0.10, 0);
    }
}

// 🖥️ MONİTÖRLERİN ELEMANA BAKMASI VE OPTİK MOUSE
function buildWorkerDeskEquipment(cfg, isRightSide) {
    const compGroup = new THREE.Group();
    compGroup.position.set(...cfg.deskPos);

    // Kavisli ekranlar elemana baksın:
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
// 🏓 ⚽ PATRONUN ARKADAŞLARI: MEHMET & BERAT
// -------------------------------------------------------------
function buildFriendsMehmetAndBerat() {
    createFriendCharacter({
        id: 'mehmet',
        name: 'Mehmet (Patronun Arkadaşı)',
        startPos: [7.5, 0, -2.5],
        startRotY: -Math.PI / 2,
        shirtColor: 0x0d9488,
        pantsColor: 0x1e293b,
        hairColor: 0x1c1917,
        initialPhrase: "Berat PS5 kolunu hazırla kanka, rövanş maçı var!"
    });

    createFriendCharacter({
        id: 'berat',
        name: 'Berat (Patronun Arkadaşı)',
        startPos: [7.5, 0, 1.2],
        startRotY: -Math.PI / 2,
        shirtColor: 0x2563eb,
        pantsColor: 0x0f172a,
        hairColor: 0x451a03,
        initialPhrase: "Langırt 7'de biter kanka, yenilen semaverden çayları koyar!"
    });
}

function createFriendCharacter(cfg) {
    const friendGroup = new THREE.Group();
    friendGroup.position.set(...cfg.startPos);
    friendGroup.rotation.y = cfg.startRotY;

    const bodyGroup = new THREE.Group();
    const shirtMat = new THREE.MeshLambertMaterial({ color: cfg.shirtColor });
    const pantsMat = new THREE.MeshLambertMaterial({ color: cfg.pantsColor });
    const skinMat = new THREE.MeshLambertMaterial({ color: 0xfbd0b0 });

    const legs = new THREE.Mesh(new THREE.BoxGeometry(0.34, 0.44, 0.16), pantsMat);
    legs.position.y = 0.22;
    bodyGroup.add(legs);

    const torso = new THREE.Mesh(new THREE.BoxGeometry(0.48, 0.52, 0.26), shirtMat);
    torso.position.y = 0.70;
    bodyGroup.add(torso);

    const leftArm = new THREE.Mesh(new THREE.BoxGeometry(0.11, 0.42, 0.11), shirtMat);
    leftArm.position.set(-0.28, 0.68, 0.10);
    leftArm.rotation.x = Math.PI / 5;
    bodyGroup.add(leftArm);

    const rightArm = new THREE.Mesh(new THREE.BoxGeometry(0.11, 0.42, 0.11), shirtMat);
    rightArm.position.set(0.28, 0.68, 0.10);
    rightArm.rotation.x = -Math.PI / 6;
    bodyGroup.add(rightArm);

    const headGroup = new THREE.Group();
    headGroup.position.set(0, 1.10, 0);

    const head = new THREE.Mesh(new THREE.BoxGeometry(0.28, 0.30, 0.26), skinMat);
    headGroup.add(head);

    const hair = new THREE.Mesh(new THREE.BoxGeometry(0.30, 0.10, 0.28), new THREE.MeshLambertMaterial({ color: cfg.hairColor }));
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
        leftArm: leftArm,
        rightArm: rightArm,
        currentSpot: 0
    };

    bubbleAnchors[cfg.id].pos = new THREE.Vector3(cfg.startPos[0], 2.05, cfg.startPos[2]);
    officeScene.add(friendGroup);
}

// -------------------------------------------------------------
// ÇAPA NOKTALARINI DOM ELEMENTLERİNE BAĞLA
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

    bubbleAnchors.quant.el = document.getElementById('bubble-quant');
    bubbleAnchors.quant.bodyEl = document.getElementById('text-quant');

    bubbleAnchors.mehmet.el = document.getElementById('bubble-mehmet');
    bubbleAnchors.mehmet.bodyEl = document.getElementById('text-mehmet');

    bubbleAnchors.berat.el = document.getElementById('bubble-berat');
    bubbleAnchors.berat.bodyEl = document.getElementById('text-berat');

    bubbleAnchors.trade.el = document.getElementById('tradeMonitorBubble');
}

// -------------------------------------------------------------
// OTONOM OFİS RUTİNİ: SANDALYE DÖNÜŞÜ, MASADAN DOLAŞMA, WC, LAVABO, PS5
// -------------------------------------------------------------
function updateAutonomousOfficeAI(deltaTime, time) {
    // TV Ekranı Oyun Grafiğini Döndür
    renderTVScreenGraphics(time);

    // WC Kapısı Hareketi (Lerp)
    if (wcDoorGroup) {
        wcDoorGroup.rotation.y = THREE.MathUtils.lerp(wcDoorGroup.rotation.y, wcDoorTargetRot, 0.12);
    }

    // 1. Rastgele Karakter Diyaloğu (Sırayla Konuşma)
    if (time > nextDialogueTime) {
        nextDialogueTime = time + 6500 + Math.random() * 4500;
        const allKeys = ['boss', 'scanner', 'ta', 'risk', 'news', 'chief', 'quant', 'mehmet', 'berat'];
        const chosen = allKeys[Math.floor(Math.random() * allKeys.length)];

        if (chosen === 'boss') {
            const bossLines = [
                "Piyasayı tarayın beyler, acele yok! Disiplin #1 kuralımız.",
                "Sermaye koruma kuralına sıkı sıkıya bağlıyız.",
                "Mehmet, Berat PS5'te sesinizi biraz kısın toplantıdayız haha!",
                "Radardaki hacimli hareketleri gözden kaçırmayın."
            ];
            triggerSpeech('boss', bossLines[Math.floor(Math.random() * bossLines.length)], 5000);
        } else if (chosen === 'mehmet') {
            const mLines = [
                "Berat PS5 kolunda lag var bahane bulma haha!",
                "Semaverden iki tavşan kanı çay kap gel de yeni tura geçelim kanka.",
                "Masa tenisinde bu sefer seni devireceğim oğlum!",
                "Langırt 7'de biter kanka, yenilen semaverin suyunu tazeler!"
            ];
            triggerSpeech('mehmet', mLines[Math.floor(Math.random() * mLines.length)], 4500);
        } else if (chosen === 'berat') {
            const bLines = [
                "Mehmet pas versene oğlum kaleciyle karşı karşıyayım!",
                "Masa tenisinde dün şansın yaver gitti kanka, gel rövanşa!",
                "İki çay koydum semaverden, kap gel sehpaya.",
                "Efe patrona helal olsun, ofisi saray gibi yapmış valla!"
            ];
            triggerSpeech('berat', bLines[Math.floor(Math.random() * bLines.length)], 4500);
        } else {
            const phr = {
                scanner: [
                    "200+ parite taranıyor, hacim anomalileri anlık takipte.",
                    "15m grafiklerde Bollinger sıkışması olan coinler filtreleniyor.",
                    "Ölü piyasa filtresi devrede, testere piyasada işlem açmıyoruz."
                ],
                ta: [
                    "BTC 4s bant daralması %0.40 seviyesinde, kırılım bekleniyor.",
                    "EMA 20 & 50 kesişimleri analiz masasında inceleniyor.",
                    "Destek ve direnç rejimleri netleşmeden acele karar yok."
                ],
                news: [
                    "Funding rate oranları dengeli, global haber akışı sakin.",
                    "Makro piyasada likidite şoku tespit edilmedi.",
                    "Kripto haber akışında kritik duyuru yok, radar stabil."
                ],
                risk: [
                    "Kasa Kalkanı devrede: Maks 5x kaldıraç, %1.5 risk tavanı.",
                    "Sermaye koruma modu devrede, stop seviyeleri korunuyor.",
                    "Günlük kayıp limiti devrede, disiplin tam."
                ],
                chief: [
                    "Efe Bey, piyasa şu an bekleme modunda. Sabır en büyük kârımız.",
                    "Trend teyidi gelmeden sermayeyi riske atmıyoruz.",
                    "Risk ve Teknik ekipleri tam koordinasyon halinde."
                ],
                quant: [
                    "10,000 Monte Carlo stokastik yol simüle ediliyor. Eşiğimiz %70!",
                    "GBM ve Jump Diffusion ile olasılık dağılımını hesaplıyorum.",
                    "Beklenen R-Multiple pozitif ve TP ihtimali %70'in üzerindeyse onay veririm.",
                    "10,000 simülasyonda Stop Loss riski yüksekse komiteyi anında veto ederim."
                ]
            }[chosen];
            if (phr) triggerSpeech(chosen, phr[Math.floor(Math.random() * phr.length)], 5000);
        }
    }

    // 2. Mehmet ve Berat Eğlence Döngüsü
    if (time > nextFriendsGameTime) {
        nextFriendsGameTime = time + 14000;
        const m = friends['mehmet'];
        const b = friends['berat'];
        if (m && b) {
            // Mehmet ve Berat sırayla mekan değiştirir: Masa Tenisi -> Langırt -> PS5 Kanepe -> Çay
            m.currentSpot = ((m.currentSpot || 0) + 1) % 4;
            if (m.currentSpot === 0) {
                // Masa tenisi
                m.group.position.set(7.5, 0, -3.2);
                b.group.position.set(9.0, 0, -3.2);
                triggerSpeech('mehmet', "Masa tenisinde bu sefer seni devireceğim!", 4500);
            } else if (m.currentSpot === 1) {
                // Langırt
                m.group.position.set(7.5, 0, 0.5);
                b.group.position.set(9.0, 0, 0.5);
                triggerSpeech('berat', "Langırt 7'de biter kanka, bahse var mısın?", 4500);
            } else if (m.currentSpot === 2) {
                // 🎮 PlayStation 5 Kanepesi
                m.group.position.set(-6.8, 0, 0.9);
                b.group.position.set(-5.8, 0, 1.4);
                triggerSpeech('mehmet', "Berat PS5'te pas at pas, kaleci boşta!", 4500);
            } else {
                // Çay Köşesi
                m.group.position.set(-5.5, 0, -3.8);
                b.group.position.set(-6.5, 0, -3.8);
                triggerSpeech('berat', "Semaverden iki tavşan kanı çay çekelim ya.", 4500);
            }
            bubbleAnchors.mehmet.pos = new THREE.Vector3(m.group.position.x, 2.05, m.group.position.z);
            bubbleAnchors.berat.pos = new THREE.Vector3(b.group.position.x, 2.05, b.group.position.z);
        }
    }

    // 3. Çalışanların Mola Döngüsü (Sadece 1 Eleman Aynı Anda Gezer)
    if (!isAnyAgentWalking && time > nextAutonomousActionTime) {
        nextAutonomousActionTime = time + 18000 + Math.random() * 8000;
        const eligibleAgents = Object.values(agents).filter(a => a.state === 'SEATED_WORKING');
        if (eligibleAgents.length > 0) {
            const chosenAgent = eligibleAgents[Math.floor(Math.random() * eligibleAgents.length)];
            const activityType = Math.floor(Math.random() * 3); // 0: Çay, 1: WC & Lavabo, 2: PS5 / Lounge
            startAgentActivityWithChairSwivel(chosenAgent, activityType);
        }
    }

    // Elemanların Yürüme ve Rutinlerini Güncelle
    Object.values(agents).forEach(ag => {
        updateSingleAgentMovement(ag, deltaTime, time);
    });
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
        // Çay Köşesine Gidiş (Masanın etrafından koridordan dolanır)
        ag.waypoints = [
            new THREE.Vector3(corridorX, 0, ag.homePos.z),
            new THREE.Vector3(corridorX, 0, 2.8),
            new THREE.Vector3(-4.5, 0, 2.8),
            new THREE.Vector3(-5.8, 0, -3.2)
        ];
        ag.destinationPhrase = "Tavşan kanı bir bardak çay alayım, piyasa takibi yoğun...";
        ag.returnWaypoints = [
            new THREE.Vector3(-5.8, 0, -3.2),
            new THREE.Vector3(-4.5, 0, 2.8),
            new THREE.Vector3(corridorX, 0, 2.8),
            new THREE.Vector3(corridorX, 0, ag.homePos.z),
            ag.homePos.clone()
        ];
    } else if (actionType === 1) {
        // 🚻 Köşe Tuvalete Gidiş (Kapı Açılır, Girer, Çıkar, Lavaboda El Yıkar)
        ag.waypoints = [
            new THREE.Vector3(corridorX, 0, ag.homePos.z),
            new THREE.Vector3(corridorX, 0, 2.8),
            new THREE.Vector3(-5.0, 0, 2.8),
            new THREE.Vector3(-8.8, 0, -3.2) // Tuvalet kapısının önü
        ];
        ag.destinationPhrase = "Kısa bir ihtiyaç molası...";
        ag.returnWaypoints = [
            new THREE.Vector3(-7.5, 0, -3.2),
            new THREE.Vector3(-5.0, 0, 2.8),
            new THREE.Vector3(corridorX, 0, 2.8),
            new THREE.Vector3(corridorX, 0, ag.homePos.z),
            ag.homePos.clone()
        ];
    } else {
        // 🛋️ GENİŞLETİLMİŞ LOUNGE & PS5 KANEPESİ
        ag.waypoints = [
            new THREE.Vector3(corridorX, 0, ag.homePos.z),
            new THREE.Vector3(corridorX, 0, 2.8),
            new THREE.Vector3(-6.8, 0, 1.2) // Lüks kanepe
        ];
        ag.destinationPhrase = "Lounge'da 5 dakika dinlenip PlayStation'da bir tur atayım.";
        ag.returnWaypoints = [
            new THREE.Vector3(-6.8, 0, 1.2),
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
        ag.bodyGroup.position.y = 0;
        setAgentLegsPose(ag, true); // Bacaklar yere tam paralel!
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
            setAgentLegsPose(ag, false); // Ayağa kalktı, bacaklar dik
        }
        return;
    }

    // AŞAMA 2: YÜRÜME (MASANIN ETRAFINDAN KORİDORLARDAN DOLAŞIR)
    if (ag.state === 'WALKING') {
        if (ag.currentWpIdx >= ag.waypoints.length) {
            if (ag.activityType === 1) {
                // 🚻 TUVALET KABİNİNE GİRİŞ AŞAMASI
                ag.state = 'WC_DOOR_OPENING';
                wcDoorTargetRot = -Math.PI / 2; // Kapı açılır!
                playOfficeSound('door');
                ag.destinationTimer = Date.now() + 800;
                return;
            } else {
                ag.state = 'AT_DESTINATION';
                ag.destinationTimer = Date.now() + 6000;
                triggerSpeech(ag.id, ag.destinationPhrase, 4500);

                if (ag.activityType === 0) {
                    playOfficeSound('tea');
                } else if (ag.activityType === 2) {
                    // 🛋️ KANEPEDE OTURMA & PS5
                    ag.group.rotation.y = Math.PI / 2; // Odaya ve TV'ye dönük
                    ag.bodyGroup.position.y = -0.15; // Kanepenin minderine oturur
                    setAgentLegsPose(ag, true);
                    ag.leftArm.rotation.x = Math.PI / 3; // PS5 kolunu tutar
                    ag.rightArm.rotation.x = Math.PI / 3;
                }
                return;
            }
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

            // Ayakta yürüme salınımı
            const walkCycle = time * 0.01;
            ag.leftThigh.position.z = Math.sin(walkCycle) * 0.15;
            ag.rightThigh.position.z = -Math.sin(walkCycle) * 0.15;
            ag.leftArm.rotation.x = -Math.sin(walkCycle) * 0.35;
            ag.rightArm.rotation.x = Math.sin(walkCycle) * 0.35;
        }
    } else if (ag.state === 'WC_DOOR_OPENING') {
        if (Date.now() > ag.destinationTimer) {
            // Eleman kabinin içine adım atar
            ag.group.position.set(-9.2, 0, -4.5);
            wcDoorTargetRot = 0; // Kapı kapanır!
            playOfficeSound('door');
            if (portableWcLight) portableWcLight.color.setHex(0xef4444); // DOLU IŞIĞI (KIRMIZI)
            ag.state = 'WC_INSIDE';
            ag.destinationTimer = Date.now() + 4000; // İçeride 4 saniye
        }
    } else if (ag.state === 'WC_INSIDE') {
        if (Date.now() > ag.destinationTimer) {
            // İhtiyaç giderildi, kapı açılır
            wcDoorTargetRot = -Math.PI / 2;
            playOfficeSound('door');
            if (portableWcLight) portableWcLight.color.setHex(0x10b981); // BOŞ IŞIĞI (YEŞİL)
            ag.state = 'WC_EXITING';
            ag.destinationTimer = Date.now() + 800;
        }
    } else if (ag.state === 'WC_EXITING') {
        if (Date.now() > ag.destinationTimer) {
            // Eleman tuvaletten çıkar ve yanındaki lavaboya geçer
            ag.group.position.set(-7.5, 0, -3.8); // Lavabo önü
            ag.group.rotation.y = Math.PI; // Aynaya/Lavaboya dönük
            wcDoorTargetRot = 0; // Kapı geri kapanır
            playOfficeSound('door');

            ag.state = 'WASHING_HANDS';
            ag.destinationTimer = Date.now() + 3500;
            triggerSpeech(ag.id, "Ellerimi sabunla bolca yıkadım, hijyen tamam!", 3500);
            playOfficeSound('water'); // El yıkama su sesi!
        }
    } else if (ag.state === 'WASHING_HANDS') {
        // Lavaboda el yıkama hareketi
        ag.leftArm.rotation.x = Math.PI / 2.8 + Math.sin(time * 0.02) * 0.15;
        ag.rightArm.rotation.x = Math.PI / 2.8 + Math.cos(time * 0.02) * 0.15;

        if (Date.now() > ag.destinationTimer) {
            // El yıkama bitti, masaya dönüş başlar
            ag.leftArm.rotation.x = 0;
            ag.rightArm.rotation.x = 0;
            ag.state = 'WALKING_BACK';
            ag.waypoints = ag.returnWaypoints;
            ag.currentWpIdx = 0;
        }
    } else if (ag.state === 'AT_DESTINATION') {
        if (Date.now() > ag.destinationTimer) {
            // Kanepeden veya dinlenmeden kalkış
            ag.bodyGroup.position.y = 0;
            setAgentLegsPose(ag, false);
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
                ag.leftThigh.position.z = Math.sin(walkCycle) * 0.15;
                ag.rightThigh.position.z = -Math.sin(walkCycle) * 0.15;
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
            setAgentLegsPose(ag, true); // Bacaklar masada yere tam paralel pozisyona geçer!
            isAnyAgentWalking = false; // Tekli kilit serbest!
        }
    }

    bubbleAnchors[ag.id].pos = new THREE.Vector3(ag.group.position.x, 1.95, ag.group.position.z);
}

// -------------------------------------------------------------
// BALONCUKLARIN 3D DÜNYADAN 2D EKRANA YANSITILMASI
// -------------------------------------------------------------
function updateBubblePositions() {
    if (!officeCamera || !officeRenderer) return;

    const width = officeRenderer.domElement.clientWidth;
    const height = officeRenderer.domElement.clientHeight;

    Object.keys(bubbleAnchors).forEach(key => {
        const item = bubbleAnchors[key];
        if (!item || !item.el || !item.pos) return;

        // Trade Bubble görünürlük kontrolü
        if (key === 'trade') {
            if (currentBubbleMode === 'off') {
                item.el.style.opacity = '0';
                return;
            }
        } else {
            // Karakter balonları
            if (currentBubbleMode === 'off') {
                item.el.style.opacity = '0';
                return;
            }
            if (currentBubbleMode === 'boss' && key !== 'boss') {
                item.el.style.opacity = '0';
                return;
            }
            if (!item.isSpeaking && currentBubbleMode === 'smart') {
                item.el.style.opacity = '0';
                return;
            }
        }

        const screenPos = item.pos.clone().project(officeCamera);

        // Kamera arkasındaysa gizle
        if (screenPos.z > 1.0) {
            item.el.style.opacity = '0';
            return;
        }

        const x = (screenPos.x * 0.5 + 0.5) * width;
        const y = (-screenPos.y * 0.5 + 0.5) * height;

        item.el.style.left = `${x}px`;
        item.el.style.top = `${y}px`;

        if (key === 'trade') {
            item.el.style.opacity = '1';
        } else if (item.isSpeaking || currentBubbleMode === 'all') {
            item.el.style.opacity = '1';
        }
    });
}

// -------------------------------------------------------------
// BALONCUK GÖRÜNÜM MODUNU DEĞİŞTİR
// -------------------------------------------------------------
function cycleBubbleMode() {
    const modes = ['all', 'smart', 'boss', 'off'];
    const idx = modes.indexOf(currentBubbleMode);
    currentBubbleMode = modes[(idx + 1) % modes.length];

    const btn = document.getElementById('btnToggleBubbles');
    if (btn) {
        const labels = {
            all: '💬 Balon: Tümü',
            smart: '💬 Balon: Akıllı',
            boss: '💬 Balon: Patron',
            off: '💬 Balon: Gizli'
        };
        btn.innerText = labels[currentBubbleMode];
    }
    playOfficeSound('click');
}

// -------------------------------------------------------------
// TAM EKRAN MODU
// -------------------------------------------------------------
function toggleOfficeFullscreen() {
    const container = document.getElementById('office3dContainer');
    if (!container) return;

    if (!document.fullscreenElement) {
        if (container.requestFullscreen) {
            container.requestFullscreen();
        } else if (container.webkitRequestFullscreen) {
            container.webkitRequestFullscreen();
        }
    } else {
        if (document.exitFullscreen) {
            document.exitFullscreen();
        }
    }
}

document.addEventListener('fullscreenchange', () => {
    const isFs = !!document.fullscreenElement;
    const btnExit = document.getElementById('btnExitOfficeFs');
    if (btnExit) btnExit.style.display = isFs ? 'block' : 'none';
    setTimeout(resizeOffice3D, 150);
});

// -------------------------------------------------------------
// KAMERA AÇILARI (DUVAR ENGELİ SIFIR - TÜM AÇILARDAN FERAH GÖRÜNÜM)
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
        camTargetPos = new THREE.Vector3(0, 2.2, isPortrait ? 0.8 : 0.5);
        camLookTarget = new THREE.Vector3(0, 1.4, -2.3);
        playOfficeSound('chime');
    } else if (mode === 'table') {
        const btn = document.getElementById('btnCamTable');
        if (btn) btn.classList.add('active');
        camTargetPos = new THREE.Vector3(0, isPortrait ? 4.8 : 4.0, isPortrait ? 5.2 : 4.5);
        camLookTarget = new THREE.Vector3(0, 1.1, 0);
        playOfficeSound('click');
    } else if (mode === 'iso') {
        const btn = document.getElementById('btnCamIso');
        if (btn) btn.classList.add('active');
        // Kuşbakışı: Duvar engeli olmadan tüm odayı 45 dereceden görür!
        camTargetPos = new THREE.Vector3(isPortrait ? 8.2 : 7.2, isPortrait ? 7.5 : 6.5, isPortrait ? 8.2 : 7.2);
        camLookTarget = new THREE.Vector3(0, 0.9, 0);
        playOfficeSound('click');
    } else if (mode === 'chill') {
        const btn = document.getElementById('btnCamChill');
        if (btn) btn.classList.add('active');
        // Dinlenme, TV, PS5 ve Çay Alanına Odak
        camTargetPos = new THREE.Vector3(-4.5, 3.8, 5.2);
        camLookTarget = new THREE.Vector3(-6.5, 1.1, 0.5);
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

    // 2. Canlı İşlem Baloncuğu (Masa rengini asla değiştirmeden sadece 2D balonu günceller!)
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

        if (statusPill) {
            statusPill.innerHTML = `⚡ <strong>CANLI İŞLEM:</strong> ${sym} (${pnlText})`;
            statusPill.style.color = isProfit ? '#10b981' : '#ef4444';
        }
    } else {
        if (tradeBubble) {
            tradeBubble.className = 'sims-trade-bubble idle';
            tradeBubble.innerHTML = `💤 AKTİF İŞLEM YOK (200 Parite Radarda)`;
        }

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

// -------------------------------------------------------------
// PENCERE BOYUTLANDIRMA VE DUYARLILIK
// -------------------------------------------------------------
function resizeOffice3D() {
    const target = document.getElementById('officeCanvasTarget');
    if (!target || !officeRenderer || !officeCamera) return;

    const width = target.clientWidth || target.offsetWidth;
    const height = target.clientHeight || target.offsetHeight;

    if (width > 0 && height > 0) {
        officeCamera.aspect = width / height;
        officeCamera.updateProjectionMatrix();
        officeRenderer.setSize(width, height);
    }
}

// -------------------------------------------------------------
// BAŞLATMA & BOYUTLANDIRMA KÖPRÜSÜ
// -------------------------------------------------------------
function initOrResizeOffice3D() {
    try {
        if (!officeInitialized) {
            init3DOffice();
        } else {
            resizeOffice3D();
        }
    } catch (e) {
        console.error("Office init/resize error:", e);
    }
}
window.initOrResizeOffice3D = initOrResizeOffice3D;
window.initOffice3D = initOrResizeOffice3D;

        // Başlangıç Sol Görünümü ve Canlı Polling
        try {
            switchLeftView(currentLeftView);
        } catch (e) {
            console.error("Initial switchLeftView error:", e);
        }

        // Canlı Polling Kesintisiz Başlatılır
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
