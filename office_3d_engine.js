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
