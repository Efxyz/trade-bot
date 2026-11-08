/* ==========================================================================
   🎮 3D SİMS TARZI YAPAY ZEKA TİCARET OFİSİ (THREE.JS ENGINE) - v4.0.0
   Özellikler:
   1. Arkadaşlar: Mehmet & Berat (Çalışmıyor, Masa Tenisi, Langırt, Çay/Goygoy)
   2. Bağımsız Sandalyeler: Yürürken sandalyeyle yürüme bug'ı tamamen giderildi.
   3. Herkese Özel Bilgisayar & Mouse: Monitörler çalışanlara bakıyor, optik mouse'lar eklendi.
   4. Şeffaf Glassmorphic Baloncuklar: Sadece konuşunca açılır, söner. Zengin esprili cümleler.
   5. Dinlenme & Çay Köşesi: Semaverli Türk çay köşesi, deri lounge, çay/sigara dinlenme alanı.
   6. Portatif Tuvalet: Gereksiz duvar kapısı yerine portatif kabin WC.
   7. Şehir Silüeti Kaldırıldı: Arkada sade, lüks ahşap akustik çıtalı penthouse duvarı.
   8. Dev İkili Ekran: Efe'nin arkasındaki dev ekranda Canlı BTC Grafiği + Açık Pozisyonlar Kâr/Zarar.
   9. Yumuşak Işıklandırma: Masadaki parlama/glare bug'ı giderildi.
   ========================================================================== */

let officeScene, officeCamera, officeRenderer, officeControls;
let officeInitialized = false;
let officeAnimFrameId = null;

// Karakterler ve Mobilya Referansları
let plumbobMesh = null;
let plumbobLight = null;
let bossGroup = null;
let bossHeadMesh = null;
let portableWcLight = null;
let portableWcSign = null;

// Arkadaşlar (Mehmet & Berat)
const friends = {};

// Uzman Ajanlar Sözlüğü (Scanner, TA, Risk, News, Chief)
const agents = {};

// Masa Monitörleri ve Ekranlar
let officeDeskScreens = [];
let bigWallTexture = null;
let bigWallCtx = null;
let bigWallScreenMesh = null;

// Kamera Hedefleri
let camTargetPos = null;
let camLookTarget = null;
let camCurrentLook = null;

// Baloncuk Görünüm Modu & Zamanlayıcılar
let currentBubbleMode = window.innerWidth < 768 ? 'smart' : 'all';
let bubbleSpeechTimers = {};
let nextAutonomousActionTime = 4000;
let nextDialogueTime = 2500;
let nextFriendsGameTime = 5000;

// Karakter Balon Çapaları (3D Dünya Konumu -> 2D Ekran Yansıtması)
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
            const f1 = 280 + Math.random() * 280;
            osc.frequency.setValueAtTime(f1, now);
            osc.frequency.linearRampToValueAtTime(f1 * 1.35, now + 0.07);
            gain.gain.setValueAtTime(0.04, now);
            gain.gain.exponentialRampToValueAtTime(0.001, now + 0.12);
            osc.start(now);
            osc.stop(now + 0.12);
        } else if (type === 'pingpong') {
            // Masa tenisi topu sekme sesi
            osc.type = 'sine';
            osc.frequency.setValueAtTime(800 + Math.random() * 300, now);
            osc.frequency.exponentialRampToValueAtTime(300, now + 0.05);
            gain.gain.setValueAtTime(0.06, now);
            gain.gain.exponentialRampToValueAtTime(0.001, now + 0.05);
            osc.start(now);
            osc.stop(now + 0.05);
        } else if (type === 'tea') {
            // Çay bardağı tıkırtısı / demlik sesi
            osc.type = 'sine';
            osc.frequency.setValueAtTime(1500, now);
            osc.frequency.exponentialRampToValueAtTime(900, now + 0.08);
            gain.gain.setValueAtTime(0.05, now);
            gain.gain.exponentialRampToValueAtTime(0.001, now + 0.09);
            osc.start(now);
            osc.stop(now + 0.09);
        } else if (type === 'trade') {
            osc.type = 'square';
            osc.frequency.setValueAtTime(523.25, now);
            osc.frequency.setValueAtTime(659.25, now + 0.1);
            osc.frequency.setValueAtTime(783.99, now + 0.2);
            gain.gain.setValueAtTime(0.08, now);
            gain.gain.exponentialRampToValueAtTime(0.001, now + 0.40);
            osc.start(now);
            osc.stop(now + 0.40);
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
// DİNAMİK KONUŞMA BALONCUKLARI SİSTEMİ (ŞEFFAF FADE IN & FADE OUT)
// -------------------------------------------------------------
function triggerSpeech(charId, text, durationMs = 5000) {
    if (currentBubbleMode === 'off') return;
    if (currentBubbleMode === 'boss' && charId !== 'boss' && charId !== 'trade') return;

    const anchor = bubbleAnchors[charId];
    if (!anchor || !anchor.el) return;

    if (anchor.bodyEl && text) {
        anchor.bodyEl.innerText = text;
    }

    anchor.isSpeaking = true;
    anchor.el.classList.add('speaking');
    playOfficeSound('talk');

    if (bubbleSpeechTimers[charId]) {
        clearTimeout(bubbleSpeechTimers[charId]);
    }

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
    officeScene.background = new THREE.Color(0x0a0f1d);
    officeScene.fog = new THREE.FogExp2(0x0a0f1d, 0.018);

    // 2. Kamera
    const initialFov = aspect < 1.0 ? Math.min(65, 45 / Math.max(0.68, aspect)) : 45;
    officeCamera = new THREE.PerspectiveCamera(initialFov, aspect, 0.1, 100);
    const isMobile = aspect < 1.0 || width < 768;
    officeCamera.position.set(0, isMobile ? 5.8 : 5.2, isMobile ? 8.8 : 7.8);
    camCurrentLook = new THREE.Vector3(0, 1.2, 0);
    officeCamera.lookAt(camCurrentLook);

    // 3. Renderer (Yüksek Kalite)
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

    // 5. Işıklandırma (Parlama & Glare Bug'ı Tamamen Giderilmiş)
    setupOfficeLights();

    // 6. Ofis Mimarisi: Ahşap Akustik Duvarlar, Çay Köşesi, Portatif WC, Masa Tenisi & Langırt Alanı
    buildOfficeArchitecture();

    // 7. Trading Masası & Monitörler (Yumuşak mat kaplama, optik mouse'lar)
    buildTradingDesk();

    // 8. 👑 BAŞ KOLTUK / PATRON: EFE (Siyah Takım Elbise, Işıklı Plumbob, MacBook, Altın İsimlik)
    buildBossEfe();

    // 9. Efe'nin Arkasındaki Dev Ekranda İKİLİ GÖRÜNÜM (BTC Grafiği + Canlı Kâr/Zarar)
    buildGiantWallDualScreen();

    // 10. 5 Uzman Yapay Zeka Ajanı (Bağımsız Sandalyeler, Yüze Bakan Monitörler & Mouse'lar)
    buildSpecialistAgents();

    // 11. 🏓 ⚽ PATRONUN ARKADAŞLARI: MEHMET & BERAT (Çalışmaz, Gezer, Masa Tenisi, Langırt, Çay)
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
// IŞIKLANDIRMA SİSTEMİ (MASADAKİ PARLAMA BUG'I ÇÖZÜLDÜ)
// -------------------------------------------------------------
function setupOfficeLights() {
    // Dengeli ortam ışığı
    const ambientLight = new THREE.AmbientLight(0xdbe6f7, 0.88);
    officeScene.add(ambientLight);

    // Ana yumuşak yönlü ışık
    const dirLight = new THREE.DirectionalLight(0xffffff, 0.85);
    dirLight.position.set(5, 11, 7);
    dirLight.castShadow = true;
    dirLight.shadow.mapSize.width = 1024;
    dirLight.shadow.mapSize.height = 1024;
    dirLight.shadow.bias = -0.001;
    officeScene.add(dirLight);

    // Patron Efe Tepe Spotu (Sıcak Altın)
    const bossSpot = new THREE.PointLight(0xfbbf24, 1.2, 8);
    bossSpot.position.set(0, 3.8, -2.4);
    officeScene.add(bossSpot);

    // Çay ve Oyun Alanı Spotu
    const gameSpot = new THREE.PointLight(0x38bdf8, 0.9, 9);
    gameSpot.position.set(6.2, 4.0, 0);
    officeScene.add(gameSpot);

    const teaSpot = new THREE.PointLight(0xf59e0b, 0.8, 8);
    teaSpot.position.set(-6.2, 3.8, 0);
    officeScene.add(teaSpot);
}

// -------------------------------------------------------------
// OFİS MİMARİSİ: ŞEHİR SİLÜETİ KALDIRILDI, ÇAY KÖŞESİ, PORTATİF WC
// -------------------------------------------------------------
function buildOfficeArchitecture() {
    // 1. Zemin (Lüks Koyu Meşe Parke)
    const floorGeo = new THREE.PlaneGeometry(24, 20);
    const floorMat = new THREE.MeshStandardMaterial({ color: 0x141a27, roughness: 0.55, metalness: 0.08 });
    const floor = new THREE.Mesh(floorGeo, floorMat);
    floor.rotation.x = -Math.PI / 2;
    floor.receiveShadow = true;
    officeScene.add(floor);

    // 2. Ana İşlem Masası Halısı
    const rugGeo = new THREE.PlaneGeometry(12.5, 9.0);
    const rugMat = new THREE.MeshStandardMaterial({ color: 0x0c1322, roughness: 0.9 });
    const rug = new THREE.Mesh(rugGeo, rugMat);
    rug.rotation.x = -Math.PI / 2;
    rug.position.set(0, 0.015, 0);
    rug.receiveShadow = true;
    officeScene.add(rug);

    // 3. Arka Duvar (Şehir silüeti kaldırıldı; modern koyu ahşap akustik çıtalı duvar)
    buildAcousticBackWall();

    // 4. ☕ GELENEKSEL TÜRK ÇAY KÖŞESİ (Semaver, Demlik, İnce Belli Bardaklar)
    buildTurkishTeaCorner(-6.2, 0, -1.2);

    // 5. 🛋️ ÇALIŞAN DİNLENME & ÇAY-SİGARA KÖŞESİ (Lüks Deri Kanepe, Sehpa)
    buildLoungeBreakArea(-6.5, 0, 1.8);

    // 6. 🚻 MODERN PORTATİF KABİN TUVALET (Gereksiz kapı yerine kabin WC)
    buildPortableRestroom(-8.0, 0, 4.2);

    // 7. 🏓 MASA TENİSİ (PING-PONG) MASASI (Mehmet & Berat Oyun Alanı)
    buildPingPongTable(6.2, 0, -1.2);

    // 8. ⚽ LANGIRT MASASI (FOOSBALL) (Mehmet & Berat Oyun Alanı)
    buildFoosballTable(6.2, 0, 1.5);

    // 9. Saksı Bitkileri
    buildPottedPlant(-9.5, 0, -4.5);
    buildPottedPlant(9.5, 0, -4.5);
}

// Şehir silüeti yerine modern ahşap akustik çıtalı lüks duvar
function buildAcousticBackWall() {
    const wallGeo = new THREE.BoxGeometry(24, 8.5, 0.3);
    const wallMat = new THREE.MeshStandardMaterial({ color: 0x111624, roughness: 0.75 });
    const backWall = new THREE.Mesh(wallGeo, wallMat);
    backWall.position.set(0, 4.25, -6.5);
    officeScene.add(backWall);

    // Akustik Dikey Ahşap Çıtalar (Minimalist Penthouse Dekoru)
    const slatMat = new THREE.MeshStandardMaterial({ color: 0x3d2b1f, roughness: 0.6 });
    for (let x = -11.5; x <= 11.5; x += 0.45) {
        // Dev ekranın arkasına gelen kısmı açık bırak
        if (x > -3.5 && x < 3.5) continue;
        const slat = new THREE.Mesh(new THREE.BoxGeometry(0.12, 8.0, 0.08), slatMat);
        slat.position.set(x, 4.25, -6.32);
        officeScene.add(slat);
    }
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

    // Efe'nin tam arkasındaki devasa 85-inç İkili Monitör
    const screenGeo = new THREE.PlaneGeometry(6.6, 2.8);
    const screenMat = new THREE.MeshBasicMaterial({ map: bigWallTexture });
    bigWallScreenMesh = new THREE.Mesh(screenGeo, screenMat);
    bigWallScreenMesh.position.set(0, 4.2, -6.3);
    officeScene.add(bigWallScreenMesh);

    // Ekranın lüks altın/metal çerçevesi
    const frameGeo = new THREE.BoxGeometry(6.75, 2.95, 0.08);
    const frameMat = new THREE.MeshStandardMaterial({ color: 0x1e293b, metalness: 0.8, roughness: 0.2 });
    const frame = new THREE.Mesh(frameGeo, frameMat);
    frame.position.set(0, 4.2, -6.35);
    officeScene.add(frame);
}

// Dev Ekrandaki İkili Görünümü Dinamik Çizen Fonksiyon
function renderBigWallScreenContent(info) {
    if (!bigWallCtx) return;
    const ctx = bigWallCtx;

    // Arka plan: Koyu donanma mavisi / siyah
    ctx.fillStyle = '#070b14';
    ctx.fillRect(0, 0, 1024, 512);

    // Üst Bar: Başlık
    ctx.fillStyle = '#0f172a';
    ctx.fillRect(0, 0, 1024, 56);
    ctx.strokeStyle = '#334155';
    ctx.lineWidth = 2;
    ctx.strokeRect(0, 0, 1024, 56);

    ctx.fillStyle = '#f59e0b';
    ctx.font = 'bold 24px Inter, monospace';
    ctx.fillText('👑 PATRON: EFE | DEV İKİLİ STRATEJİ EKRANI (FUTURES & CANLI PnL)', 30, 38);

    // İkili Görünüm Ayırıcı Dikey Çizgi
    ctx.strokeStyle = '#1e293b';
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.moveTo(512, 56);
    ctx.lineTo(512, 512);
    ctx.stroke();

    // ================= SOL YARI: 📈 CANLI BTC VADELİ MUM GRAFİĞİ =================
    ctx.fillStyle = '#38bdf8';
    ctx.font = 'bold 20px Inter, sans-serif';
    ctx.fillText('📈 CANLI BTC / USDT (FUTURES)', 35, 95);

    ctx.fillStyle = '#f1f5f9';
    ctx.font = 'bold 36px monospace';
    ctx.fillText(`$${info.btcPrice || '76,250.0'}`, 35, 145);

    ctx.fillStyle = (info.btcStatus && info.btcStatus.includes('BULL')) ? '#10b981' : '#f59e0b';
    ctx.font = '16px monospace';
    ctx.fillText(`● REJİM: ${info.btcStatus || 'DEAD_CHOP (Bant: %0.40)'}`, 35, 180);

    // Stilize 15D Mum Grafiği Çizimi
    drawStylizedCandlesticks(ctx, 35, 210, 440, 260);

    // ================= SAĞ YARI: ⚡ AÇIK POZİSYONLAR & KÂR/ZARAR PnL =================
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
            const dollarText = (pos.gross_pnl_pct !== undefined ? (isPos ? '+$' : '-$') + Math.abs(pos.gross_pnl_pct).toFixed(2) : '');

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
        // Açık Pozisyon Yok: Sermaye Koruma & Tarama Durumu
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

// Mum Grafiği Çizici Yardımcı
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
    const baseP = startY + h * 0.55;
    let curP = baseP;

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
// ☕ GELENEKSEL TÜRK ÇAY KÖŞESİ (Semaver, Demlik, İnce Belli Bardak)
// -------------------------------------------------------------
function buildTurkishTeaCorner(x, y, z) {
    const teaGroup = new THREE.Group();
    teaGroup.position.set(x, y, z);

    // Ahşap Çay Masası
    const tableGeo = new THREE.BoxGeometry(1.6, 0.82, 1.0);
    const tableMat = new THREE.MeshStandardMaterial({ color: 0x271c14, roughness: 0.6 });
    const table = new THREE.Mesh(tableGeo, tableMat);
    table.position.y = 0.41;
    table.castShadow = true;
    teaGroup.add(table);

    // Nostaljik Pirinç/Bakır Semaver
    const semaverBaseGeo = new THREE.CylinderGeometry(0.24, 0.22, 0.45, 16);
    const brassMat = new THREE.MeshStandardMaterial({ color: 0xd97706, metalness: 0.85, roughness: 0.2 });
    const semaverBase = new THREE.Mesh(semaverBaseGeo, brassMat);
    semaverBase.position.set(-0.25, 1.05, 0);
    teaGroup.add(semaverBase);

    // Üstündeki Porselen Demlik
    const demlikGeo = new THREE.CylinderGeometry(0.12, 0.14, 0.18, 14);
    const demlikMat = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.3 });
    const demlik = new THREE.Mesh(demlikGeo, demlikMat);
    demlik.position.set(-0.25, 1.34, 0);
    teaGroup.add(demlik);

    // İnce Belli Çay Bardakları Tepsisi
    const trayGeo = new THREE.BoxGeometry(0.7, 0.02, 0.5);
    const trayMat = new THREE.MeshStandardMaterial({ color: 0xd4d4d8, metalness: 0.9 });
    const tray = new THREE.Mesh(trayGeo, trayMat);
    tray.position.set(0.35, 0.83, 0);
    teaGroup.add(tray);

    // İnce Belli Çay Bardakları (Tavşan Kanı Çaylı)
    const glassMat = new THREE.MeshPhysicalMaterial({ color: 0xb91c1c, transmission: 0.7, transparent: true, opacity: 0.85, roughness: 0.1 });
    [-0.15, 0.15].forEach((gx, i) => {
        const glass = new THREE.Mesh(new THREE.CylinderGeometry(0.045, 0.035, 0.10, 12), glassMat);
        glass.position.set(0.35 + gx, 0.88, (i % 2 === 0 ? 0.08 : -0.08));
        teaGroup.add(glass);
    });

    officeScene.add(teaGroup);
}

// -------------------------------------------------------------
// 🛋️ DİNLENME & ÇAY-SİGARA KÖŞESİ (LOUNGE KANEPE & SEHPA)
// -------------------------------------------------------------
function buildLoungeBreakArea(x, y, z) {
    const loungeGroup = new THREE.Group();
    loungeGroup.position.set(x, y, z);

    // Lüks Deri İkili Kanepe (Çalışanlar Dinlenmeye Gelir)
    const sofaMat = new THREE.MeshStandardMaterial({ color: 0x1e293b, roughness: 0.5 });
    
    // Kanepe Oturağı
    const sofaSeat = new THREE.Mesh(new THREE.BoxGeometry(1.8, 0.28, 0.85), sofaMat);
    sofaSeat.position.y = 0.35;
    sofaSeat.castShadow = true;
    loungeGroup.add(sofaSeat);

    // Kanepe Sırtlığı
    const sofaBack = new THREE.Mesh(new THREE.BoxGeometry(1.8, 0.70, 0.22), sofaMat);
    sofaBack.position.set(0, 0.72, -0.32);
    loungeGroup.add(sofaBack);

    // Kanepe Yan Kolçakları
    [-0.85, 0.85].forEach(sx => {
        const arm = new THREE.Mesh(new THREE.BoxGeometry(0.20, 0.50, 0.85), sofaMat);
        arm.position.set(sx, 0.50, 0);
        loungeGroup.add(arm);
    });

    // Küçük Yuvarlak Cam Sehpa
    const tableBase = new THREE.Mesh(new THREE.CylinderGeometry(0.04, 0.25, 0.42, 16), new THREE.MeshStandardMaterial({ color: 0x0f172a, metalness: 0.9 }));
    tableBase.position.set(0, 0.21, 0.95);
    loungeGroup.add(tableBase);

    const glassTop = new THREE.Mesh(new THREE.CylinderGeometry(0.45, 0.45, 0.03, 16), new THREE.MeshPhysicalMaterial({ color: 0x38bdf8, transmission: 0.8, opacity: 0.7, transparent: true }));
    glassTop.position.set(0, 0.43, 0.95);
    loungeGroup.add(glassTop);

    // Sehpa Üstündeki Küllük
    const ashtray = new THREE.Mesh(new THREE.CylinderGeometry(0.08, 0.07, 0.03, 12), new THREE.MeshStandardMaterial({ color: 0xe2e8f0 }));
    ashtray.position.set(0, 0.45, 0.95);
    loungeGroup.add(ashtray);

    officeScene.add(loungeGroup);
}

// -------------------------------------------------------------
// 🚻 PORTATİF KABİN TUVALET (MODERN KOMPOZİT BOOTH WC)
// -------------------------------------------------------------
function buildPortableRestroom(x, y, z) {
    const wcGroup = new THREE.Group();
    wcGroup.position.set(x, y, z);

    // Kabin Gövdesi (Antrasit / Modern Prefabrik Modül)
    const cabinGeo = new THREE.BoxGeometry(1.4, 2.4, 1.4);
    const cabinMat = new THREE.MeshStandardMaterial({ color: 0x1e293b, roughness: 0.6 });
    const cabin = new THREE.Mesh(cabinGeo, cabinMat);
    cabin.position.y = 1.2;
    cabin.castShadow = true;
    wcGroup.add(cabin);

    // Kabin Kapısı
    const doorGeo = new THREE.BoxGeometry(0.9, 2.1, 0.06);
    const doorMat = new THREE.MeshStandardMaterial({ color: 0x334155, roughness: 0.5 });
    const door = new THREE.Mesh(doorGeo, doorMat);
    door.position.set(0, 1.08, 0.71);
    wcGroup.add(door);

    // Metalik Kapı Kolu
    const handle = new THREE.Mesh(new THREE.BoxGeometry(0.04, 0.18, 0.08), new THREE.MeshStandardMaterial({ color: 0xd4d4d8, metalness: 0.95 }));
    handle.position.set(0.35, 1.05, 0.75);
    wcGroup.add(handle);

    // "🚻 PORTATİF WC" Tabelası
    const sign = new THREE.Mesh(new THREE.BoxGeometry(0.8, 0.22, 0.06), new THREE.MeshStandardMaterial({ color: 0x0284c7, emissive: 0x0369a1, emissiveIntensity: 0.7 }));
    sign.position.set(0, 2.25, 0.72);
    wcGroup.add(sign);
    portableWcSign = sign;

    // Meşguliyet Işığı (Yeşil = Boş, Turuncu = Dolu)
    portableWcLight = new THREE.PointLight(0x10b981, 1.3, 4.0);
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

    // Mavi / Yeşil Masa Tablası (Standart Ölçüler)
    const topGeo = new THREE.BoxGeometry(2.4, 0.06, 1.4);
    const topMat = new THREE.MeshStandardMaterial({ color: 0x0284c7, roughness: 0.35 });
    const tableTop = new THREE.Mesh(topGeo, topMat);
    tableTop.position.y = 0.76;
    tableTop.castShadow = true;
    tableGroup.add(tableTop);

    // Beyaz Çizgiler (Kenar ve Orta Çizgi)
    const lineMat = new THREE.MeshBasicMaterial({ color: 0xffffff });
    const centerLine = new THREE.Mesh(new THREE.BoxGeometry(2.4, 0.005, 0.03), lineMat);
    centerLine.position.set(0, 0.795, 0);
    tableGroup.add(centerLine);

    // Masa Tenisi Filesi (Ortadaki Dikey File)
    const netGeo = new THREE.BoxGeometry(0.04, 0.16, 1.5);
    const netMat = new THREE.MeshStandardMaterial({ color: 0xffffff, transparent: true, opacity: 0.7, roughness: 0.8 });
    const net = new THREE.Mesh(netGeo, netMat);
    net.position.set(0, 0.87, 0);
    tableGroup.add(net);

    // Çelik Ayaklar
    const legMat = new THREE.MeshStandardMaterial({ color: 0x0f172a, metalness: 0.8 });
    [[-1.0, -0.55], [1.0, -0.55], [-1.0, 0.55], [1.0, 0.55]].forEach(([lx, lz]) => {
        const leg = new THREE.Mesh(new THREE.CylinderGeometry(0.04, 0.04, 0.76, 12), legMat);
        leg.position.set(lx, 0.38, lz);
        tableGroup.add(leg);
    });

    // Raketler & Top
    const racketMat = new THREE.MeshStandardMaterial({ color: 0xef4444 });
    const racket1 = new THREE.Mesh(new THREE.CylinderGeometry(0.09, 0.09, 0.02, 14), racketMat);
    racket1.position.set(-0.8, 0.80, 0.3);
    tableGroup.add(racket1);

    const racket2 = new THREE.Mesh(new THREE.CylinderGeometry(0.09, 0.09, 0.02, 14), new THREE.MeshStandardMaterial({ color: 0x1e293b }));
    racket2.position.set(0.8, 0.80, -0.3);
    tableGroup.add(racket2);

    const ball = new THREE.Mesh(new THREE.SphereGeometry(0.03, 12, 12), new THREE.MeshBasicMaterial({ color: 0xffffff }));
    ball.position.set(0.1, 0.82, 0.1);
    tableGroup.add(ball);

    officeScene.add(tableGroup);
}

// -------------------------------------------------------------
// ⚽ LANGIRT MASASI (FOOSBALL TABLE) (MEHMET & BERAT)
// -------------------------------------------------------------
function buildFoosballTable(x, y, z) {
    const foosballGroup = new THREE.Group();
    foosballGroup.position.set(x, y, z);

    // Langırt Ahşap Kasası
    const boxGeo = new THREE.BoxGeometry(1.8, 0.38, 1.0);
    const woodMat = new THREE.MeshStandardMaterial({ color: 0xb45309, roughness: 0.4 });
    const box = new THREE.Mesh(boxGeo, woodMat);
    box.position.y = 0.70;
    box.castShadow = true;
    foosballGroup.add(box);

    // Yeşil Saha Zemini
    const pitchGeo = new THREE.BoxGeometry(1.65, 0.02, 0.85);
    const pitchMat = new THREE.MeshStandardMaterial({ color: 0x15803d, roughness: 0.5 });
    const pitch = new THREE.Mesh(pitchGeo, pitchMat);
    pitch.position.y = 0.75;
    foosballGroup.add(pitch);

    // Metalik Çubuklar (Kollar)
    const rodMat = new THREE.MeshStandardMaterial({ color: 0xe2e8f0, metalness: 0.95 });
    [-0.55, -0.25, 0.05, 0.35, 0.55].forEach(rx => {
        const rod = new THREE.Mesh(new THREE.CylinderGeometry(0.015, 0.015, 1.4, 10), rodMat);
        rod.rotation.x = Math.PI / 2;
        rod.position.set(rx, 0.82, 0);
        foosballGroup.add(rod);
    });

    // 4 Sağlam Bacak
    const legMat = new THREE.MeshStandardMaterial({ color: 0x1e293b, roughness: 0.7 });
    [[-0.8, -0.42], [0.8, -0.42], [-0.8, 0.42], [0.8, 0.42]].forEach(([lx, lz]) => {
        const leg = new THREE.Mesh(new THREE.BoxGeometry(0.12, 0.70, 0.12), legMat);
        leg.position.set(lx, 0.35, lz);
        foosballGroup.add(leg);
    });

    officeScene.add(foosballGroup);
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
        const leaf = new THREE.Mesh(new THREE.SphereGeometry(0.3, 8, 8), leafMat);
        leaf.scale.set(0.8, 1.4, 0.1);
        const angle = (i / 7) * Math.PI * 2;
        leaf.position.set(Math.cos(angle) * 0.3, 1.1 + Math.sin(i) * 0.2, Math.sin(angle) * 0.3);
        leaf.rotation.set(0.4, angle, 0.3);
        plantGroup.add(leaf);
    }

    officeScene.add(plantGroup);
}

// -------------------------------------------------------------
// TRADING MASASI (YUMUŞAK MAT KAPLAMA, GLARSIZ)
// -------------------------------------------------------------
function buildTradingDesk() {
    const tableGroup = new THREE.Group();

    // Genişlik: 2.0m, Uzunluk: 4.6m, Üst yüzey yüksekliği: y = 0.78m
    const topGeo = new THREE.BoxGeometry(2.0, 0.06, 4.6);
    // Mat koyu füme kaplama (Parlama sıfırlandı)
    const topMat = new THREE.MeshStandardMaterial({ color: 0x182030, roughness: 0.65, metalness: 0.1 });
    const tableTop = new THREE.Mesh(topGeo, topMat);
    tableTop.position.set(0, 0.78, 0);
    tableTop.castShadow = true;
    tableTop.receiveShadow = true;
    tableGroup.add(tableTop);

    // İnce altın beveled kenarlık
    const trim = new THREE.Mesh(new THREE.BoxGeometry(2.04, 0.02, 4.64), new THREE.MeshStandardMaterial({ color: 0xd97706, roughness: 0.5, metalness: 0.3 }));
    trim.position.set(0, 0.80, 0);
    tableGroup.add(trim);

    // Ayaklar
    const legMat = new THREE.MeshStandardMaterial({ color: 0x0f172a, metalness: 0.8 });
    [[-0.9, -2.1], [0.9, -2.1], [-0.9, 2.1], [0.9, 2.1]].forEach(([lx, lz]) => {
        const leg = new THREE.Mesh(new THREE.CylinderGeometry(0.06, 0.06, 0.78, 16), legMat);
        leg.position.set(lx, 0.39, lz);
        leg.castShadow = true;
        tableGroup.add(leg);
    });

    // Masanın Ortasındaki Küçük Canlı İşlem Ekranı
    const centerDisplayGeo = new THREE.BoxGeometry(0.8, 0.40, 0.04);
    const centerMat = new THREE.MeshStandardMaterial({ color: 0x0284c7, emissive: 0x0369a1, emissiveIntensity: 0.7 });
    const centerScr = new THREE.Mesh(centerDisplayGeo, centerMat);
    centerScr.position.set(0, 1.02, 0);
    tableGroup.add(centerScr);
    officeDeskScreens.push(centerScr);

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

    const chromeMat = new THREE.MeshStandardMaterial({ color: 0xe2e8f0, metalness: 0.9 });
    const leatherMat = new THREE.MeshStandardMaterial({ color: 0x090c10, roughness: 0.35 });
    const goldMat = new THREE.MeshStandardMaterial({ color: 0xf59e0b, metalness: 0.85 });

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
    const suitMat = new THREE.MeshStandardMaterial({ color: 0x0a0c10, roughness: 0.32, metalness: 0.2 });
    const shirtMat = new THREE.MeshStandardMaterial({ color: 0xffffff });
    const tieMat = new THREE.MeshStandardMaterial({ color: 0x000000 });

    const legs = new THREE.Mesh(new THREE.BoxGeometry(0.55, 0.18, 0.55), suitMat);
    legs.position.set(0, 0.54, 0.05);
    bossGroup.add(legs);

    const torso = new THREE.Mesh(new THREE.BoxGeometry(0.60, 0.58, 0.34), suitMat);
    torso.position.set(0, 0.90, -0.05);
    bossGroup.add(torso);

    const collar = new THREE.Mesh(new THREE.BoxGeometry(0.22, 0.12, 0.18), shirtMat);
    collar.position.set(0, 1.15, 0.07);
    bossGroup.add(collar);

    const tie = new THREE.Mesh(new THREE.BoxGeometry(0.07, 0.30, 0.04), tieMat);
    tie.position.set(0, 1.02, 0.14);
    bossGroup.add(tie);

    [-0.34, 0.34].forEach(ax => {
        const arm = new THREE.Mesh(new THREE.BoxGeometry(0.12, 0.42, 0.12), suitMat);
        arm.position.set(ax, 0.85, 0.18);
        arm.rotation.x = Math.PI / 3.2;
        bossGroup.add(arm);
    });

    // Baş & Saç
    const headGroup = new THREE.Group();
    headGroup.position.set(0, 1.35, -0.02);

    const head = new THREE.Mesh(new THREE.BoxGeometry(0.32, 0.34, 0.30), new THREE.MeshStandardMaterial({ color: 0xf5c6a5 }));
    headGroup.add(head);

    const hair = new THREE.Mesh(new THREE.BoxGeometry(0.34, 0.12, 0.32), new THREE.MeshStandardMaterial({ color: 0x171717 }));
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

    const plumbobMat = new THREE.MeshStandardMaterial({ color: 0x22c55e, emissive: 0x16a34a, emissiveIntensity: 1.0, roughness: 0.15 });
    plumbobMesh = new THREE.Mesh(plumbobGeo, plumbobMat);
    plumbobMesh.position.set(0, 1.95, -0.02);

    plumbobLight = new THREE.PointLight(0x22c55e, 1.2, 3.0);
    plumbobLight.position.set(0, 1.95, -0.02);
    parentGroup.add(plumbobLight);

    parentGroup.add(plumbobMesh);
}

function buildBossDeskItems(parentGroup) {
    const macBase = new THREE.Mesh(new THREE.BoxGeometry(0.48, 0.02, 0.32), new THREE.MeshStandardMaterial({ color: 0xd8e0e8, metalness: 0.85 }));
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
    const plate = new THREE.Mesh(new THREE.BoxGeometry(0.75, 0.20, 0.10), new THREE.MeshStandardMaterial({ map: plateTex, metalness: 0.75 }));
    plate.position.set(0, 0.88, 0.75);
    plate.rotation.x = -0.28;
    parentGroup.add(plate);

    // Fincan
    const saucer = new THREE.Mesh(new THREE.CylinderGeometry(0.09, 0.07, 0.015, 16), new THREE.MeshStandardMaterial({ color: 0xffffff }));
    saucer.position.set(0.42, 0.82, 0.48);
    parentGroup.add(saucer);

    const cup = new THREE.Mesh(new THREE.CylinderGeometry(0.055, 0.045, 0.07, 16), new THREE.MeshStandardMaterial({ color: 0xffffff }));
    cup.position.set(0.42, 0.855, 0.48);
    parentGroup.add(cup);
}

// -------------------------------------------------------------
// 5 UZMAN AJAN (BAĞIMSIZ SANDALYELER & ÇALIŞANA BAKAN MONİTÖRLER)
// -------------------------------------------------------------
function buildSpecialistAgents() {
    // 1. SCANNER AGENT (Sol Üst: x = -1.55, z = -0.75)
    createAgentWorkstation({
        id: 'scanner',
        name: 'Scanner Agent',
        seatPos: [-1.55, 0, -0.75],
        seatRotY: Math.PI / 2, // Masaya doğru bakıyor
        deskPos: [-0.60, 0.78, -0.75],
        suitColor: 0x1d4ed8, // Mavi
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
        suitColor: 0x7e22ce, // Mor
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
        suitColor: 0xb91c1c, // Kırmızı
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
        suitColor: 0xd97706, // Amber
        hairColor: 0x1e293b,
        screenColor: 0xf59e0b,
        phrases: [
            "Funding rate stabil, global piyasalarda şok veri yok.",
            "Makro haber akışı sakin, likidite dengeli.",
            "Fed faiz beklentileri normal seviyede seyrediyor."
        ]
    });

    // 5. CHIEF ANALYST (Masanın Başı / Efe'nin Yanı: x = 1.35, z = -1.8)
    createAgentWorkstation({
        id: 'chief',
        name: 'Baş Stratejist',
        seatPos: [1.35, 0, -1.8],
        seatRotY: -Math.PI / 3.5,
        deskPos: [0.95, 0.78, -1.5],
        suitColor: 0x059669, // Yeşil
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

// Tek Bir Ajanın Bağımsız Sandalyesi, Masadaki Monitörleri ve Karakterini İnşa Eder
function createAgentWorkstation(cfg) {
    const isRightSide = cfg.seatPos[0] > 0;
    const isChief = cfg.id === 'chief';

    // 1. BAĞIMSIZ SANDALYE (Sahneye direkt eklenir, ajanla birlikte yürümez!)
    const chairGroup = new THREE.Group();
    chairGroup.position.set(...cfg.seatPos);
    chairGroup.rotation.y = cfg.seatRotY;

    const chairSeat = new THREE.Mesh(new THREE.BoxGeometry(0.55, 0.08, 0.55), new THREE.MeshStandardMaterial({ color: 0x1e293b, roughness: 0.6 }));
    chairSeat.position.y = 0.44;
    chairGroup.add(chairSeat);

    const chairBack = new THREE.Mesh(new THREE.BoxGeometry(0.55, 0.65, 0.08), new THREE.MeshStandardMaterial({ color: 0x1e293b, roughness: 0.6 }));
    chairBack.position.set(0, 0.80, -0.27);
    chairGroup.add(chairBack);

    const chairLeg = new THREE.Mesh(new THREE.CylinderGeometry(0.04, 0.04, 0.44, 12), new THREE.MeshStandardMaterial({ color: 0x475569 }));
    chairLeg.position.y = 0.22;
    chairGroup.add(chairLeg);

    officeScene.add(chairGroup);

    // 2. ÇALIŞANA BAKAN MONİTÖRLER & OPTİK MOUSE
    buildWorkerDeskEquipment(cfg, isRightSide);

    // 3. KARAKTER MODELİ (Sadece karakter hareket eder)
    const agentGroup = new THREE.Group();
    agentGroup.position.set(...cfg.seatPos);
    agentGroup.rotation.y = cfg.seatRotY;

    const bodyGroup = new THREE.Group();
    const clothMat = new THREE.MeshStandardMaterial({ color: cfg.suitColor, roughness: 0.45 });
    const skinMat = new THREE.MeshStandardMaterial({ color: 0xfbd0b0 });

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

// Çalışanın Önündeki Çift Monitör & Optik Mouse (Yüzü Tam Çalışana Bakar)
function buildWorkerDeskEquipment(cfg, isRightSide) {
    const compGroup = new THREE.Group();
    compGroup.position.set(...cfg.deskPos);
    // Sol taraftakiler için (x < 0) ekranlar sola bakar (+PI/2), sağdakiler için sağa bakar (-PI/2)
    compGroup.rotation.y = isRightSide ? -Math.PI / 2 : Math.PI / 2;

    const screenMat = new THREE.MeshStandardMaterial({
        color: cfg.screenColor,
        emissive: cfg.screenColor,
        emissiveIntensity: 0.75,
        roughness: 0.3
    });

    // 1. Ana Ekran
    const scr1 = new THREE.Mesh(new THREE.BoxGeometry(0.48, 0.30, 0.02), screenMat);
    scr1.position.set(-0.25, 0.24, 0);
    scr1.rotation.y = 0.14;
    compGroup.add(scr1);
    officeDeskScreens.push(scr1);

    // 2. Yan Takip Ekranı
    const scr2 = new THREE.Mesh(new THREE.BoxGeometry(0.44, 0.28, 0.02), screenMat);
    scr2.position.set(0.24, 0.23, 0);
    scr2.rotation.y = -0.16;
    compGroup.add(scr2);
    officeDeskScreens.push(scr2);

    // Metalik Stand
    const standMat = new THREE.MeshStandardMaterial({ color: 0x334155, metalness: 0.8 });
    const standBar = new THREE.Mesh(new THREE.BoxGeometry(0.70, 0.03, 0.03), standMat);
    standBar.position.set(0, 0.22, -0.05);
    compGroup.add(standBar);

    const standPost = new THREE.Mesh(new THREE.CylinderGeometry(0.025, 0.025, 0.22, 12), standMat);
    standPost.position.set(0, 0.11, -0.05);
    compGroup.add(standPost);

    // Klavye
    const kb = new THREE.Mesh(new THREE.BoxGeometry(0.40, 0.012, 0.14), new THREE.MeshStandardMaterial({ color: 0x1e293b }));
    kb.position.set(-0.06, 0.015, 0.22);
    compGroup.add(kb);

    // 🖱️ OPTİK MOUSE & MOUSE PAD
    const pad = new THREE.Mesh(new THREE.BoxGeometry(0.65, 0.005, 0.28), new THREE.MeshStandardMaterial({ color: 0x090e17, roughness: 0.9 }));
    pad.position.set(0, 0.005, 0.22);
    compGroup.add(pad);

    const mouse = new THREE.Mesh(new THREE.BoxGeometry(0.065, 0.018, 0.10), new THREE.MeshStandardMaterial({ color: 0x0f172a, roughness: 0.3 }));
    mouse.position.set(0.22, 0.016, 0.22);
    compGroup.add(mouse);

    // Mouse LED Işığı
    const mouseLed = new THREE.Mesh(new THREE.BoxGeometry(0.01, 0.005, 0.03), new THREE.MeshBasicMaterial({ color: 0x38bdf8 }));
    mouseLed.position.set(0.22, 0.026, 0.22);
    compGroup.add(mouseLed);

    officeScene.add(compGroup);
}

// -------------------------------------------------------------
// 🏓 ⚽ PATRONUN ARKADAŞLARI: MEHMET & BERAT
// (Çalışmıyor! Masa Tenisi, Langırt, Çay, Espriler & Goygoy)
// -------------------------------------------------------------
function buildFriendsMehmetAndBerat() {
    // MEHMET (Cool nane yeşili hoodie, bej pantolon, raket tutar)
    createFriendCharacter({
        id: 'mehmet',
        name: 'Mehmet (Patronun Arkadaşı)',
        startPos: [5.2, 0, -1.2], // Masa tenisi başında
        startRotY: Math.PI / 2,
        suitColor: 0x0d9488, // Nane Yeşili / Turkuaz Hoodie
        hairColor: 0x292524,
        phrases: [
            "Berat çay koysana kanka ya, semaver kaynıyor!",
            "Masa tenisinde dün 11-4 yendim seni unutma!",
            "Efe patron oldu bize çay bile ısmarlamıyor haha.",
            "Langırtın kalecisini çok iyi çeviriyorum bu sefer affetmem.",
            "Kanka Bitcoin rekor kırar mı sence? gerçi bana ne Efe düşünsün.",
            "Ofisin çayı da efsaneymiş, demlik tam kıvamında."
        ]
    });

    // BERAT (Lacivert / Bordo kolej ceketi, spor ayakkabı, langırt başında)
    createFriendCharacter({
        id: 'berat',
        name: 'Berat (Patronun Arkadaşı)',
        startPos: [7.2, 0, -1.2], // Masa tenisinin diğer ucu
        startRotY: -Math.PI / 2,
        suitColor: 0x1e3a8a, // Lacivert Kolej Ceketi
        hairColor: 0x1c1917,
        phrases: [
            "Mehmet masa tenisinde rüzgar vardı o yüzden yendin, gel rövanşa!",
            "Çayı ben koydum zaten, şekeri sen getir.",
            "Efe'ye bak takım elbiseyle Wall Street kurdu gibi oturuyor maşallah.",
            "Langırt 7'de biter kanka, bahse var mısın?",
            "Ajanlar da harıl harıl çalışıyor valla, kolay gelsin beyler.",
            "Masa tenisinde bu sefer falso vereceğim gör bak."
        ]
    });
}

function createFriendCharacter(cfg) {
    const friendGroup = new THREE.Group();
    friendGroup.position.set(...cfg.startPos);
    friendGroup.rotation.y = cfg.startRotY;

    const bodyGroup = new THREE.Group();
    const clothMat = new THREE.MeshStandardMaterial({ color: cfg.suitColor, roughness: 0.5 });
    const pantsMat = new THREE.MeshStandardMaterial({ color: 0x334155, roughness: 0.6 });
    const skinMat = new THREE.MeshStandardMaterial({ color: 0xfbd0b0 });

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

    // Baş & Saç
    const headGroup = new THREE.Group();
    headGroup.position.set(0, 1.14, 0);

    const head = new THREE.Mesh(new THREE.BoxGeometry(0.28, 0.30, 0.26), skinMat);
    headGroup.add(head);

    const hair = new THREE.Mesh(new THREE.BoxGeometry(0.30, 0.12, 0.28), new THREE.MeshStandardMaterial({ color: cfg.hairColor, roughness: 0.8 }));
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

// -------------------------------------------------------------
// 3D DÜNYADAN 2D EKRANA BALON YANSITMASI
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
// OTONOM RUTİNLER: ÇALIŞANLAR VE ARKADAŞLAR
// -------------------------------------------------------------
function updateAutonomousOfficeAI(deltaTime, time) {
    // 1. Zengin & Esprili Diyalog Döngüsü (Her 6-9 saniyede bir konuşma)
    if (time > nextDialogueTime) {
        nextDialogueTime = time + 6500 + Math.random() * 4000;
        const allKeys = ['boss', 'scanner', 'ta', 'risk', 'news', 'chief', 'mehmet', 'berat'];
        const chosen = allKeys[Math.floor(Math.random() * allKeys.length)];

        if (chosen === 'boss') {
            const bossLines = [
                "Piyasayı tarayın beyler, acele yok! Sermaye koruma kuralımız #1.",
                "Mehmet, Berat sesinizi azaltın komite toplantıdayız haha!",
                "Risk Şefi, kaldıraç ve marjini çift kontrol et.",
                "Trend teyidi gelmeden tek bir cent bile riske atılmayacak."
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

    // 2. Mehmet ve Berat Aktivite Değişimi (Masa Tenisi, Langırt, Çay Köşesi, Efe'nin Yanı)
    if (time > nextFriendsGameTime) {
        nextFriendsGameTime = time + 14000 + Math.random() * 8000;
        const gameType = Math.floor(Math.random() * 4); // 0: PingPong, 1: Langırt, 2: Çay Köşesi, 3: Efe Ziyareti
        switchFriendsActivity(gameType);
    }

    // 3. Çalışanların Yürüme Rutini (Kahve / Portatif WC / Dinlenme Lounge / Rapor)
    if (time > nextAutonomousActionTime) {
        nextAutonomousActionTime = time + 18000 + Math.random() * 10000;
        const candidateIds = ['scanner', 'ta', 'risk', 'news'];
        const seatedCandidates = candidateIds.filter(id => agents[id] && agents[id].state === 'SEATED_WORKING');

        if (seatedCandidates.length > 0) {
            const walker = agents[seatedCandidates[Math.floor(Math.random() * seatedCandidates.length)]];
            const actionType = Math.floor(Math.random() * 4);
            startAgentActivity(walker, actionType);
        }
    }

    // Kemik ve Yürüme Animasyonları
    Object.keys(agents).forEach(id => updateSingleAgentMovement(agents[id], deltaTime, time));
    Object.keys(friends).forEach(id => updateFriendMovement(friends[id], deltaTime, time));
}

// Mehmet & Berat'ın Aktiviteleri Arasında Geçiş
function switchFriendsActivity(actType) {
    const m = friends['mehmet'];
    const b = friends['berat'];
    if (!m || !b) return;

    if (actType === 0) {
        // Masa Tenisi Maçı
        m.waypoints = [new THREE.Vector3(5.0, 0, -1.2)];
        b.waypoints = [new THREE.Vector3(7.4, 0, -1.2)];
        m.state = 'WALKING';
        b.state = 'WALKING';
        m.targetState = 'PLAYING_PINGPONG';
        b.targetState = 'PLAYING_PINGPONG';
        m.finalRotY = Math.PI / 2;
        b.finalRotY = -Math.PI / 2;
        triggerSpeech('mehmet', "Berat masa tenisinde bu sefer seni devireceğim!", 4500);
    } else if (actType === 1) {
        // Langırt Maçı
        m.waypoints = [new THREE.Vector3(5.2, 0, 1.5)];
        b.waypoints = [new THREE.Vector3(7.2, 0, 1.5)];
        m.state = 'WALKING';
        b.state = 'WALKING';
        m.targetState = 'PLAYING_FOOSBALL';
        b.targetState = 'PLAYING_FOOSBALL';
        m.finalRotY = Math.PI / 2;
        b.finalRotY = -Math.PI / 2;
        triggerSpeech('berat', "Langırt 7'de biter kanka, bahse var mısın?", 4500);
    } else if (actType === 2) {
        // Çay Köşesinde Çay İçme
        m.waypoints = [new THREE.Vector3(0, 0, 3.2), new THREE.Vector3(-5.2, 0, -1.2)];
        b.waypoints = [new THREE.Vector3(0, 0, 3.2), new THREE.Vector3(-4.5, 0, -1.2)];
        m.state = 'WALKING';
        b.state = 'WALKING';
        m.targetState = 'DRINKING_TEA';
        b.targetState = 'DRINKING_TEA';
        m.finalRotY = -Math.PI / 2;
        b.finalRotY = Math.PI / 2;
        triggerSpeech('mehmet', "Kanka semaverden iki tavşan kanı çay çekelim ya.", 4500);
        playOfficeSound('tea');
    } else {
        // Efe'ye Selam Verme / Goygoy
        m.waypoints = [new THREE.Vector3(2.2, 0, -2.1)];
        b.waypoints = [new THREE.Vector3(2.8, 0, -2.1)];
        m.state = 'WALKING';
        b.state = 'WALKING';
        m.targetState = 'CHATTING_WITH_BOSS';
        b.targetState = 'CHATTING_WITH_BOSS';
        m.finalRotY = -Math.PI / 2;
        b.finalRotY = -Math.PI / 2;
        triggerSpeech('mehmet', "Efe patron oldu bizi tanımaz artık haha!", 4500);
    }
}

function updateFriendMovement(fr, deltaTime, time) {
    if (fr.state === 'PLAYING_PINGPONG') {
        // Raket sallama hareketi
        fr.rightArm.rotation.x = Math.PI / 3 + Math.sin(time * 0.008) * 0.35;
        if (Math.random() < 0.015) playOfficeSound('pingpong');
        return;
    }

    if (fr.state === 'PLAYING_FOOSBALL') {
        // Langırt kolu çevirme hareketi
        fr.leftArm.rotation.x = Math.PI / 4 + Math.sin(time * 0.01) * 0.25;
        fr.rightArm.rotation.x = Math.PI / 4 + Math.cos(time * 0.01) * 0.25;
        return;
    }

    if (fr.state === 'DRINKING_TEA' || fr.state === 'CHATTING_WITH_BOSS') {
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

// Bir Ajan İçin Aktivite Başlatır (Yürürken Sandalye Masada Kalır!)
function startAgentActivity(ag, actionType) {
    const isLeft = ag.homePos.x < 0;
    const corridorX = isLeft ? -2.4 : 2.4;
    ag.state = 'WALKING';
    ag.currentWpIdx = 0;
    ag.activityType = actionType;

    if (actionType === 0) {
        // Çay Köşesine Gidiş
        ag.waypoints = [
            new THREE.Vector3(corridorX, 0, ag.homePos.z),
            new THREE.Vector3(corridorX, 0, 2.2),
            new THREE.Vector3(-5.0, 0, -1.2)
        ];
        ag.destinationPhrase = "Tavşan kanı bir bardak çay alayım, piyasa takibi yoğun...";
        ag.returnAction = () => { ag.waypoints = [new THREE.Vector3(corridorX, 0, 2.2), new THREE.Vector3(corridorX, 0, ag.homePos.z), ag.homePos.clone()]; };
    } else if (actionType === 1) {
        // Portatif WC'ye Gidiş
        ag.waypoints = [
            new THREE.Vector3(corridorX, 0, ag.homePos.z),
            new THREE.Vector3(corridorX, 0, 2.5),
            new THREE.Vector3(-7.2, 0, 4.2)
        ];
        ag.destinationPhrase = "Kısa bir ihtiyaç molası...";
        ag.returnAction = () => { ag.waypoints = [new THREE.Vector3(corridorX, 0, 2.5), new THREE.Vector3(corridorX, 0, ag.homePos.z), ag.homePos.clone()]; };
    } else if (actionType === 2) {
        // Dinlenme / Sigara Lounge Alanına Gidiş
        ag.waypoints = [
            new THREE.Vector3(corridorX, 0, ag.homePos.z),
            new THREE.Vector3(corridorX, 0, 1.8),
            new THREE.Vector3(-5.6, 0, 1.8)
        ];
        ag.destinationPhrase = "Lounge'da 5 dakika dinlenip bir çay-sigara molası veriyorum.";
        ag.returnAction = () => { ag.waypoints = [new THREE.Vector3(corridorX, 0, 1.8), new THREE.Vector3(corridorX, 0, ag.homePos.z), ag.homePos.clone()]; };
    } else {
        // Patrona Rapor Sunma
        ag.waypoints = [
            new THREE.Vector3(corridorX, 0, ag.homePos.z),
            new THREE.Vector3(corridorX, 0, -2.1),
            new THREE.Vector3(isLeft ? -1.0 : 1.0, 0, -2.1)
        ];
        ag.destinationPhrase = "Efe Bey, son tarama ve risk özetini getirdim.";
        ag.returnAction = () => { ag.waypoints = [new THREE.Vector3(corridorX, 0, -2.1), new THREE.Vector3(corridorX, 0, ag.homePos.z), ag.homePos.clone()]; };
    }
}

function updateSingleAgentMovement(ag, deltaTime, time) {
    if (ag.state === 'SEATED_WORKING') {
        ag.leftArm.rotation.x = Math.PI / 3.5 + Math.sin(time * 0.005) * 0.05;
        ag.rightArm.rotation.x = Math.PI / 3.5 + Math.cos(time * 0.005) * 0.05;
        ag.leftLeg.rotation.x = 0;
        ag.rightLeg.rotation.x = 0;
        ag.bodyGroup.position.y = 0;
        return;
    }

    if (ag.state === 'WALKING') {
        if (ag.currentWpIdx >= ag.waypoints.length) {
            ag.state = 'AT_DESTINATION';
            ag.destinationTimer = Date.now() + 4500;
            triggerSpeech(ag.id, ag.destinationPhrase, 4000);

            if (ag.activityType === 0) {
                playOfficeSound('tea');
            } else if (ag.activityType === 1) {
                if (portableWcLight) portableWcLight.color.setHex(0xf59e0b); // WC Dolu
            } else if (ag.activityType === 3) {
                setTimeout(() => {
                    triggerSpeech('boss', "Güzel analiz, disiplinli devam ediyoruz.", 4000);
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
    } else if (ag.state === 'AT_DESTINATION') {
        if (Date.now() > ag.destinationTimer) {
            if (ag.activityType === 1 && portableWcLight) {
                portableWcLight.color.setHex(0x10b981); // WC Boş
            }
            ag.state = 'WALKING_BACK';
            ag.returnAction();
            ag.currentWpIdx = 0;
        }
    } else if (ag.state === 'WALKING_BACK') {
        if (ag.currentWpIdx >= ag.waypoints.length) {
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

    // 3. Otonom Ofis Yapay Zekası (Ajanlar ve Arkadaşlar)
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

    // 1. Dev Arka Plandaki İkili Ekranı Güncelle
    renderBigWallScreenContent({
        btcPrice: btc.btc_price ? Number(btc.btc_price).toLocaleString('en-US', {minimumFractionDigits: 1}) : '76,500.0',
        btcStatus: `${btc.status || 'DEAD_CHOP'} (4s Bant: %${btc.range_pct || '0.40'})`,
        activePositions: positions
    });
    if (bigWallTexture) bigWallTexture.needsUpdate = true;

    // 2. Bilgisayar Ekranı Canlı İşlem Baloncuğu
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
                scr.material.emissiveIntensity = 0.9;
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
                scr.material.emissive.setHex(0x0284c7);
                scr.material.emissiveIntensity = 0.6;
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
