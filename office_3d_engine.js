/* ==========================================================================
   🎮 3D SİMS TARZI YAPAY ZEKA TİCARET OFİSİ (THREE.JS ENGINE)
   Patron: Efe (Siyah Takım Elbiseli, Yönetici Koltuğu, Dönen Sims Plumbob'u)
   Ajanlar: Scanner, TA Analyst, News/Macro, Risk Officer, Chief Analyst
   Dinamik Sims Konuşma Baloncukları & Ekran İçi Canlı Kâr/Zarar Göstergesi
   ========================================================================== */

let officeScene, officeCamera, officeRenderer, officeControls;
let officeInitialized = false;
let officeAnimFrameId = null;

// Karakter & Animasyon Referansları
let plumbobMesh = null;
let bossHeadMesh = null;
let agentHeads = {};
let officeDeskScreens = [];
let officeDeskLight = null;
let wallCanvasTexture = null;
let wallCanvasCtx = null;

// Kamera Hedefleri (Lerp / Yumuşak Geçiş İçin)
let camTargetPos = null;
let camLookTarget = null;
let camCurrentLook = null;

// Karakter Balon Çapaları (3D Dünya Konumu -> 2D Ekran Yansıtması)
const bubbleAnchors = {
    boss: { pos: null, el: null, bodyEl: null },
    scanner: { pos: null, el: null, bodyEl: null },
    ta: { pos: null, el: null, bodyEl: null },
    news: { pos: null, el: null, bodyEl: null },
    risk: { pos: null, el: null, bodyEl: null },
    chief: { pos: null, el: null, bodyEl: null },
    trade: { pos: null, el: null }
};

// Ses Efekti (Web Audio API - İndirme Gerektirmez)
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
            // Hafif klavye tuşu tıklaması
            osc.type = 'triangle';
            osc.frequency.setValueAtTime(600 + Math.random() * 200, now);
            osc.frequency.exponentialRampToValueAtTime(120, now + 0.04);
            gain.gain.setValueAtTime(0.04, now);
            gain.gain.exponentialRampToValueAtTime(0.001, now + 0.04);
            osc.start(now);
            osc.stop(now + 0.04);
        } else if (type === 'chime') {
            // Sims Plumbob kristal sesi
            osc.type = 'sine';
            osc.frequency.setValueAtTime(587.33, now); // D5
            osc.frequency.setValueAtTime(880.00, now + 0.08); // A5
            gain.gain.setValueAtTime(0.08, now);
            gain.gain.exponentialRampToValueAtTime(0.001, now + 0.35);
            osc.start(now);
            osc.stop(now + 0.35);
        } else if (type === 'trade') {
            // Canlı işlem açılış zili
            osc.type = 'square';
            osc.frequency.setValueAtTime(523.25, now);
            osc.frequency.setValueAtTime(659.25, now + 0.1);
            osc.frequency.setValueAtTime(783.99, now + 0.2);
            gain.gain.setValueAtTime(0.09, now);
            gain.gain.exponentialRampToValueAtTime(0.001, now + 0.45);
            osc.start(now);
            osc.stop(now + 0.45);
        }
    } catch (e) {
        // Ses desteklenmiyorsa sessizce geç
    }
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

    officeCamera.aspect = width / height;
    officeCamera.updateProjectionMatrix();
    officeRenderer.setSize(width, height);
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

    // 1. Scene & Fog
    officeScene = new THREE.Scene();
    officeScene.background = new THREE.Color(0x090e18);
    officeScene.fog = new THREE.FogExp2(0x090e18, 0.022);

    // 2. Camera
    officeCamera = new THREE.PerspectiveCamera(45, width / height, 0.1, 100);
    officeCamera.position.set(0, 5.2, 7.8);
    camCurrentLook = new THREE.Vector3(0, 1.4, 0);
    officeCamera.lookAt(camCurrentLook);

    // 3. Renderer
    officeRenderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "high-performance" });
    officeRenderer.setSize(width, height);
    officeRenderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    officeRenderer.shadowMap.enabled = true;
    officeRenderer.shadowMap.type = THREE.PCFSoftShadowMap;
    container.innerHTML = '';
    container.appendChild(officeRenderer.domElement);

    // 4. OrbitControls
    if (typeof THREE.OrbitControls !== 'undefined') {
        officeControls = new THREE.OrbitControls(officeCamera, officeRenderer.domElement);
        officeControls.enableDamping = true;
        officeControls.dampingFactor = 0.06;
        officeControls.maxPolarAngle = Math.PI / 2.05; // Yerin altına girmeyi engelle
        officeControls.minDistance = 2.5;
        officeControls.maxDistance = 22;
        officeControls.target.copy(camCurrentLook);
    }

    // 5. Işıklandırma
    setupOfficeLights();

    // 6. Ofis Mimarisi (Zemin, Gece Gökdelen Manzaralı Pencere, Duvarlar)
    buildOfficeArchitecture();

    // 7. Büyük Trading Toplantı Masası & Ekipmanlar
    buildTradingDesk();

    // 8. 👑 BAŞ KOLTUK / PATRON: EFE (Siyah Takım Elbise, Plumbob, İsimlik)
    buildBossEfe();

    // 9. 5 Uzman Yapay Zeka Ajanı (Scanner, TA, News, Risk, Chief)
    buildSpecialistAgents();

    // 10. Çapa Noktalarını DOM Elementlerine Bağla
    bindBubbleElements();

    officeInitialized = true;

    // Varsayılan kamera: Patron Efe'ye odaklanmış mod
    setOfficeCamera('boss');

    // Animasyon Döngüsünü Başlat
    if (!officeAnimFrameId) {
        animateOffice(0);
    }

    window.addEventListener('resize', resizeOffice3D);
}

// -------------------------------------------------------------
// IŞIKLANDIRMA SİSTEMİ
// -------------------------------------------------------------
function setupOfficeLights() {
    // Yumuşak modern ofis ortam ışığı
    const ambientLight = new THREE.AmbientLight(0xdce7ff, 0.9);
    officeScene.add(ambientLight);

    // Ana yönlü ışık (Soft Shadows)
    const dirLight = new THREE.DirectionalLight(0xffffff, 1.1);
    dirLight.position.set(6, 12, 8);
    dirLight.castShadow = true;
    dirLight.shadow.mapSize.width = 1024;
    dirLight.shadow.mapSize.height = 1024;
    dirLight.shadow.camera.near = 0.5;
    dirLight.shadow.camera.far = 30;
    dirLight.shadow.bias = -0.001;
    officeScene.add(dirLight);

    // Patron Efe'nin üstündeki sıcak altın tepe spotu
    const bossSpot = new THREE.PointLight(0xfbbf24, 1.4, 9);
    bossSpot.position.set(0, 4.2, -2.2);
    officeScene.add(bossSpot);

    // Masa üstü dinamik işlem ışığı (Pozisyon kâr/zararına göre renk değiştirir)
    officeDeskLight = new THREE.PointLight(0x38bdf8, 1.2, 8);
    officeDeskLight.position.set(0, 2.0, 0.1);
    officeScene.add(officeDeskLight);
}

// -------------------------------------------------------------
// OFİS MİMARİSİ: Zemin, Halı, Şehir Silüeti Penceresi, TV Ekranı
// -------------------------------------------------------------
function buildOfficeArchitecture() {
    // 1. Zemin: Koyu Lüks Parke
    const floorGeo = new THREE.PlaneGeometry(24, 20);
    const floorMat = new THREE.MeshStandardMaterial({
        color: 0x161d2b,
        roughness: 0.4,
        metalness: 0.1
    });
    const floor = new THREE.Mesh(floorGeo, floorMat);
    floor.rotation.x = -Math.PI / 2;
    floor.position.y = 0;
    floor.receiveShadow = true;
    officeScene.add(floor);

    // 2. Masa Altı Yönetici Halısı (Lacivert / Antrasit & Altın Çerçeveli)
    const rugGeo = new THREE.PlaneGeometry(13.5, 9.5);
    const rugMat = new THREE.MeshStandardMaterial({
        color: 0x0c1322,
        roughness: 0.9,
        metalness: 0.05
    });
    const rug = new THREE.Mesh(rugGeo, rugMat);
    rug.rotation.x = -Math.PI / 2;
    rug.position.set(0, 0.015, 0.1);
    rug.receiveShadow = true;
    officeScene.add(rug);

    // Halı altın bordür çizgisi
    const borderGeo = new THREE.RingGeometry(4.7, 4.8, 4);
    const borderMat = new THREE.MeshBasicMaterial({ color: 0xd97706, side: THREE.DoubleSide });
    const rugBorder = new THREE.Mesh(borderGeo, borderMat);
    rugBorder.rotation.x = -Math.PI / 2;
    rugBorder.position.set(0, 0.02, 0.1);
    rugBorder.scale.set(1.4, 1.0, 1.0);
    officeScene.add(rugBorder);

    // 3. Arka Duvar & Panoramik Şehir Manzarası Penceresi
    const backWallGeo = new THREE.BoxGeometry(24, 9, 0.3);
    const backWallMat = new THREE.MeshStandardMaterial({ color: 0x101726, roughness: 0.7 });
    const backWall = new THREE.Mesh(backWallGeo, backWallMat);
    backWall.position.set(0, 4.5, -6.5);
    officeScene.add(backWall);

    // Pencere Boşluğu & Çerçevesi
    const windowFrameGeo = new THREE.BoxGeometry(15, 5.5, 0.4);
    const windowFrameMat = new THREE.MeshStandardMaterial({ color: 0x050811, metalness: 0.8, roughness: 0.2 });
    const windowFrame = new THREE.Mesh(windowFrameGeo, windowFrameMat);
    windowFrame.position.set(0, 4.2, -6.4);
    officeScene.add(windowFrame);

    // Pencere Camı (Hafif Mavi Yansıma)
    const glassGeo = new THREE.PlaneGeometry(14.6, 5.1);
    const glassMat = new THREE.MeshPhysicalMaterial({
        color: 0x60a5fa,
        transparent: true,
        opacity: 0.2,
        roughness: 0.1,
        transmission: 0.7
    });
    const glass = new THREE.Mesh(glassGeo, glassMat);
    glass.position.set(0, 4.2, -6.35);
    officeScene.add(glass);

    // 4. Pencere Dışındaki Gece Gökdelen Silüeti (Wall Street / Cyber NYC)
    buildSkylineCity();

    // 5. Duvardaki Canlı Borsa Ekranı (Wall Display)
    buildWallDisplay();

    // 6. Ofis Saksı Bitkileri (Köşelerde Monstera & Ficus)
    buildPottedPlant(-5.5, 0, -5.2);
    buildPottedPlant(5.5, 0, -5.2);

    // 7. Su Sebili / Kahve İstasyonu (Köşede)
    buildCoffeeBar(5.8, 0, -2.5);
}

// Pencere arkasındaki 3D Gökdelenler
function buildSkylineCity() {
    const cityGroup = new THREE.Group();
    cityGroup.position.set(0, 0, -11);

    const bldgColors = [0x0b1329, 0x070c1b, 0x0f1938, 0x091024];
    const windowMats = [
        new THREE.MeshBasicMaterial({ color: 0xfacc15 }), // Sarı ışıklı pencereler
        new THREE.MeshBasicMaterial({ color: 0x38bdf8 }), // Cyan pencereler
        new THREE.MeshBasicMaterial({ color: 0xffffff })  // Beyaz ışıklar
    ];

    for (let i = 0; i < 20; i++) {
        const posX = -14 + i * 1.5 + (Math.random() - 0.5) * 0.8;
        const bldgHeight = 5 + Math.random() * 8;
        const bldgWidth = 1.0 + Math.random() * 1.2;
        const bldgDepth = 1.0 + Math.random() * 1.2;

        const bldgGeo = new THREE.BoxGeometry(bldgWidth, bldgHeight, bldgDepth);
        const bldgMat = new THREE.MeshStandardMaterial({
            color: bldgColors[i % bldgColors.length],
            roughness: 0.6
        });
        const bldg = new THREE.Mesh(bldgGeo, bldgMat);
        bldg.position.set(posX, bldgHeight / 2 - 1, (Math.random() - 0.5) * 2);
        cityGroup.add(bldg);

        // Rastgele parlayan neon pencereler
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

// Duvardaki Canlı Bilgi Ekranı (Wall Display)
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

// Saksı Bitkisi (Monstera / Salon Palmiyesi)
function buildPottedPlant(x, y, z) {
    const plantGroup = new THREE.Group();
    plantGroup.position.set(x, y, z);

    // Beyaz seramik saksı
    const potGeo = new THREE.CylinderGeometry(0.4, 0.3, 0.8, 16);
    const potMat = new THREE.MeshStandardMaterial({ color: 0xf8fafc, roughness: 0.2 });
    const pot = new THREE.Mesh(potGeo, potMat);
    pot.position.y = 0.4;
    pot.castShadow = true;
    plantGroup.add(pot);

    // Saksı toprağı
    const soilGeo = new THREE.CylinderGeometry(0.38, 0.38, 0.1, 16);
    const soilMat = new THREE.MeshStandardMaterial({ color: 0x3d2817, roughness: 0.9 });
    const soil = new THREE.Mesh(soilGeo, soilMat);
    soil.position.y = 0.8;
    plantGroup.add(soil);

    // Yeşil yapraklar
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

// Kahve İstasyonu & Espresso Makinesi
function buildCoffeeBar(x, y, z) {
    const barGroup = new THREE.Group();
    barGroup.position.set(x, y, z);

    // Ahşap sehpa
    const standGeo = new THREE.BoxGeometry(1.2, 1.1, 0.8);
    const standMat = new THREE.MeshStandardMaterial({ color: 0x1f293d, roughness: 0.5 });
    const stand = new THREE.Mesh(standGeo, standMat);
    stand.position.y = 0.55;
    stand.castShadow = true;
    barGroup.add(stand);

    // Espresso Makinesi (Gümüş / Metalik)
    const machineGeo = new THREE.BoxGeometry(0.6, 0.5, 0.5);
    const machineMat = new THREE.MeshStandardMaterial({ color: 0xd1d5db, metalness: 0.85, roughness: 0.2 });
    const machine = new THREE.Mesh(machineGeo, machineMat);
    machine.position.set(0, 1.35, 0);
    barGroup.add(machine);

    // Kahve Fincanı
    const cupGeo = new THREE.CylinderGeometry(0.08, 0.06, 0.1, 12);
    const cupMat = new THREE.MeshStandardMaterial({ color: 0xffffff });
    const cup = new THREE.Mesh(cupGeo, cupMat);
    cup.position.set(0.4, 1.15, 0.1);
    barGroup.add(cup);

    officeScene.add(barGroup);
}

// -------------------------------------------------------------
// BÜYÜK TRADİNG TOPLANTI MASASI & MONİTÖRLER
// -------------------------------------------------------------
function buildTradingDesk() {
    const tableGroup = new THREE.Group();

    // 1. Ana Masa Tablası: Koyu Ceviz / Lüks Mat Siyah & Altın Kenarlık
    const topGeo = new THREE.BoxGeometry(6.4, 0.14, 3.2);
    const topMat = new THREE.MeshStandardMaterial({
        color: 0x182030,
        roughness: 0.35,
        metalness: 0.2
    });
    const tableTop = new THREE.Mesh(topGeo, topMat);
    tableTop.position.set(0, 1.05, 0.1);
    tableTop.castShadow = true;
    tableTop.receiveShadow = true;
    tableGroup.add(tableTop);

    // Masanın altın kenar çıtası
    const trimGeo = new THREE.BoxGeometry(6.46, 0.04, 3.26);
    const trimMat = new THREE.MeshStandardMaterial({ color: 0xf59e0b, metalness: 0.8, roughness: 0.2 });
    const trim = new THREE.Mesh(trimGeo, trimMat);
    trim.position.set(0, 1.09, 0.1);
    tableGroup.add(trim);

    // Masa Ayakları: 4 Adet Ağır Çelik Kolon
    const legGeo = new THREE.CylinderGeometry(0.08, 0.08, 1.05, 16);
    const legMat = new THREE.MeshStandardMaterial({ color: 0x0f172a, metalness: 0.9, roughness: 0.3 });
    [
        [-2.8, -1.2],
        [2.8, -1.2],
        [-2.8, 1.4],
        [2.8, 1.4]
    ].forEach(([lx, lz]) => {
        const leg = new THREE.Mesh(legGeo, legMat);
        leg.position.set(lx, 0.525, lz);
        leg.castShadow = true;
        tableGroup.add(leg);
    });

    // 2. Masanın Merkezindeki Trading Monitör Grubu (Dual & Triple Kavisli Ekranlar)
    buildDeskTradingMonitors(tableGroup);

    officeScene.add(tableGroup);
}

// Masa üstündeki parlak monitörler
function buildDeskTradingMonitors(parentGroup) {
    const screenGeo = new THREE.BoxGeometry(1.2, 0.65, 0.05);
    
    // Varsayılan ekran materyali (Cyber Blue)
    const baseScreenMat = new THREE.MeshStandardMaterial({
        color: 0x0284c7,
        emissive: 0x0369a1,
        emissiveIntensity: 0.8,
        roughness: 0.2
    });

    // Merkez Ekran 1 (Scanner & TA karşısı)
    const scr1 = new THREE.Mesh(screenGeo, baseScreenMat.clone());
    scr1.position.set(-0.8, 1.55, 0.1);
    scr1.rotation.y = Math.PI / 12;
    parentGroup.add(scr1);
    officeDeskScreens.push(scr1);

    // Merkez Ekran 2 (Risk & Macro karşısı)
    const scr2 = new THREE.Mesh(screenGeo, baseScreenMat.clone());
    scr2.position.set(0.8, 1.55, 0.1);
    scr2.rotation.y = -Math.PI / 12;
    parentGroup.add(scr2);
    officeDeskScreens.push(scr2);

    // Ekran Standları (Metalik Ayaklar)
    const standGeo = new THREE.CylinderGeometry(0.04, 0.06, 0.4, 12);
    const standMat = new THREE.MeshStandardMaterial({ color: 0x334155, metalness: 0.8 });
    const st1 = new THREE.Mesh(standGeo, standMat);
    st1.position.set(-0.8, 1.25, 0.1);
    parentGroup.add(st1);

    const st2 = new THREE.Mesh(standGeo, standMat);
    st2.position.set(0.8, 1.25, 0.1);
    parentGroup.add(st2);

    // Canlı İşlem Balonunun Çapa Noktası (Monitörlerin Hemen Üstü)
    bubbleAnchors.trade.pos = new THREE.Vector3(0, 2.1, 0.1);
}

// -------------------------------------------------------------
// 👑 BAŞ KOLTUK / PATRON: EFE
// Siyah Takım Elbise, Altın İsimlik, Executive Koltuk, Sims Plumbob
// -------------------------------------------------------------
function buildBossEfe() {
    const bossGroup = new THREE.Group();
    bossGroup.position.set(0, 0, -2.2); // Masanın tam başı, içeri doğru bakıyor
    bossGroup.rotation.y = 0; // +Z yönüne (masaya ve ekibe) bakıyor

    // 1. Executive Yönetici Koltuğu (Siyah Deri & Altın Çerçeveli Yüksek Sırtlık)
    const chairGroup = new THREE.Group();
    
    // Yıldız ayak & amortisör
    const chairPistonGeo = new THREE.CylinderGeometry(0.06, 0.06, 0.5, 16);
    const chromeMat = new THREE.MeshStandardMaterial({ color: 0xe2e8f0, metalness: 0.9, roughness: 0.1 });
    const piston = new THREE.Mesh(chairPistonGeo, chromeMat);
    piston.position.y = 0.25;
    chairGroup.add(piston);

    // Koltuk minderi (Koyu siyah kapitone deri)
    const seatGeo = new THREE.BoxGeometry(0.85, 0.12, 0.8);
    const leatherMat = new THREE.MeshStandardMaterial({ color: 0x090c10, roughness: 0.35, metalness: 0.1 });
    const seat = new THREE.Mesh(seatGeo, leatherMat);
    seat.position.y = 0.55;
    seat.castShadow = true;
    chairGroup.add(seat);

    // Yüksek Yönetici Sırtlığı
    const backGeo = new THREE.BoxGeometry(0.8, 1.2, 0.12);
    const back = new THREE.Mesh(backGeo, leatherMat);
    back.position.set(0, 1.15, -0.38);
    back.rotation.x = -0.06;
    back.castShadow = true;
    chairGroup.add(back);

    // Altın Kolçaklar
    const goldMat = new THREE.MeshStandardMaterial({ color: 0xf59e0b, metalness: 0.85, roughness: 0.2 });
    [-0.42, 0.42].forEach(ax => {
        const armGeo = new THREE.BoxGeometry(0.08, 0.25, 0.6);
        const arm = new THREE.Mesh(armGeo, goldMat);
        arm.position.set(ax, 0.78, -0.05);
        chairGroup.add(arm);
    });
    bossGroup.add(chairGroup);

    // 2. Patron Efe'nin Gövdesi: Siyah Özel Dikim Takım Elbise
    const suitMat = new THREE.MeshStandardMaterial({ color: 0x0a0c10, roughness: 0.4, metalness: 0.1 });
    const shirtMat = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.3 }); // Kar beyazı gömlek
    const tieMat = new THREE.MeshStandardMaterial({ color: 0x000000, roughness: 0.1, metalness: 0.2 }); // Siyah kravat

    // Bacaklar (Takım Pantolonu, koltukta oturur pozisyonda)
    const legsGeo = new THREE.BoxGeometry(0.65, 0.22, 0.65);
    const legs = new THREE.Mesh(legsGeo, suitMat);
    legs.position.set(0, 0.66, 0.05);
    bossGroup.add(legs);

    // Gövde (Siyah Takım Elbise Ceketi)
    const torsoGeo = new THREE.BoxGeometry(0.68, 0.68, 0.38);
    const torso = new THREE.Mesh(torsoGeo, suitMat);
    torso.position.set(0, 1.1, -0.05);
    torso.castShadow = true;
    bossGroup.add(torso);

    // Beyaz Gömlek Yakası
    const collarGeo = new THREE.BoxGeometry(0.24, 0.14, 0.2);
    const collar = new THREE.Mesh(collarGeo, shirtMat);
    collar.position.set(0, 1.4, 0.08);
    bossGroup.add(collar);

    // Siyah Kravat
    const tieGeo = new THREE.BoxGeometry(0.08, 0.34, 0.04);
    const tie = new THREE.Mesh(tieGeo, tieMat);
    tie.position.set(0, 1.25, 0.16);
    bossGroup.add(tie);

    // Altın Yaka İğnesi (Gold Lapel Pin)
    const pinGeo = new THREE.BoxGeometry(0.04, 0.04, 0.02);
    const pin = new THREE.Mesh(pinGeo, goldMat);
    pin.position.set(-0.2, 1.32, 0.15);
    bossGroup.add(pin);

    // Kollar & Eller (Masanın üzerinde durur)
    const armGeo = new THREE.BoxGeometry(0.14, 0.5, 0.14);
    [-0.38, 0.38].forEach(ax => {
        const arm = new THREE.Mesh(armGeo, suitMat);
        arm.position.set(ax, 1.05, 0.15);
        arm.rotation.x = Math.PI / 3.5;
        bossGroup.add(arm);
    });

    // 3. Baş & Saç
    const headGroup = new THREE.Group();
    headGroup.position.set(0, 1.62, -0.02);

    const skinMat = new THREE.MeshStandardMaterial({ color: 0xf5c6a5, roughness: 0.5 });
    const headGeo = new THREE.BoxGeometry(0.36, 0.38, 0.34);
    const head = new THREE.Mesh(headGeo, skinMat);
    head.castShadow = true;
    headGroup.add(head);

    // Şık Modern Siyah Saç
    const hairMat = new THREE.MeshStandardMaterial({ color: 0x171717, roughness: 0.7 });
    const hairGeo = new THREE.BoxGeometry(0.38, 0.14, 0.36);
    const hair = new THREE.Mesh(hairGeo, hairMat);
    hair.position.set(0, 0.18, -0.01);
    headGroup.add(hair);

    bossHeadMesh = headGroup;
    bossGroup.add(headGroup);

    // 4. Efe'nin Önündeki Altın İsimlik: "👑 PATRON: EFE"
    buildBossNameplate(bossGroup);

    // 5. Masasındaki Kişisel Eşyalar: Apple MacBook & Espresso Fincanı
    buildBossDeskItems(bossGroup);

    // 6. ✨ DÖNEN SİMS PLUMBOB (Yeşil Kristal Elmas)
    buildSimsPlumbob(bossGroup);

    // Çapa Noktası: Patron Efe'nin Kafasının Üstü
    bubbleAnchors.boss.pos = new THREE.Vector3(0, 2.75, -2.2);

    officeScene.add(bossGroup);
}

// Dönen Klasik Yeşil Sims Plumbob Kristali
function buildSimsPlumbob(parentGroup) {
    // Çift piramitli Sims Elması
    const plumbobGeo = new THREE.OctahedronGeometry(0.18, 0);
    plumbobGeo.scale(0.8, 1.6, 0.8); // Dikey elmas formu

    const plumbobMat = new THREE.MeshStandardMaterial({
        color: 0x22c55e,
        emissive: 0x16a34a,
        emissiveIntensity: 0.9,
        roughness: 0.15,
        metalness: 0.4
    });

    plumbobMesh = new THREE.Mesh(plumbobGeo, plumbobMat);
    plumbobMesh.position.set(0, 2.3, -0.02);
    parentGroup.add(plumbobMesh);
}

// Altın Patron İsimliği: "👑 PATRON: EFE"
function buildBossNameplate(parentGroup) {
    const canvas = document.createElement('canvas');
    canvas.width = 256;
    canvas.height = 64;
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = '#b45309'; // Parlak altın/pirinç taban
    ctx.fillRect(0, 0, 256, 64);
    ctx.strokeStyle = '#fef08a';
    ctx.lineWidth = 4;
    ctx.strokeRect(4, 4, 248, 56);
    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 24px Inter, sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('👑 PATRON: EFE', 128, 40);

    const plateTex = new THREE.CanvasTexture(canvas);
    const plateGeo = new THREE.BoxGeometry(0.8, 0.22, 0.12);
    const plateMat = new THREE.MeshStandardMaterial({
        map: plateTex,
        metalness: 0.7,
        roughness: 0.25
    });
    const plate = new THREE.Mesh(plateGeo, plateMat);
    plate.position.set(0, 1.18, 0.85); // Masanın üstünde, Efe'nin önünde
    plate.rotation.x = -0.3; // Öne hafif eğik
    parentGroup.add(plate);
}

// Patron Efe'nin Masasındaki MacBook & Espresso Fincanı
function buildBossDeskItems(parentGroup) {
    // MacBook (Gümüş Alüminyum & Parlayan Ekran)
    const macBaseGeo = new THREE.BoxGeometry(0.5, 0.02, 0.35);
    const macMat = new THREE.MeshStandardMaterial({ color: 0xd8e0e8, metalness: 0.85, roughness: 0.2 });
    const macBase = new THREE.Mesh(macBaseGeo, macMat);
    macBase.position.set(0, 1.13, 0.5);
    parentGroup.add(macBase);

    const macScreenGeo = new THREE.BoxGeometry(0.5, 0.34, 0.02);
    const macScreenMat = new THREE.MeshStandardMaterial({
        color: 0x0f172a,
        emissive: 0x38bdf8,
        emissiveIntensity: 0.6
    });
    const macScreen = new THREE.Mesh(macScreenGeo, macScreenMat);
    macScreen.position.set(0, 1.28, 0.35);
    macScreen.rotation.x = -0.2;
    parentGroup.add(macScreen);

    // Beyaz İtalyan Porselen Espresso Fincanı & Tabağı
    const saucerGeo = new THREE.CylinderGeometry(0.1, 0.08, 0.02, 16);
    const saucerMat = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.2 });
    const saucer = new THREE.Mesh(saucerGeo, saucerMat);
    saucer.position.set(0.45, 1.12, 0.55);
    parentGroup.add(saucer);

    const cupGeo = new THREE.CylinderGeometry(0.06, 0.05, 0.08, 16);
    const cup = new THREE.Mesh(cupGeo, saucerMat);
    cup.position.set(0.45, 1.16, 0.55);
    parentGroup.add(cup);

    // Akıllı Telefon (Gold iPhone)
    const phoneGeo = new THREE.BoxGeometry(0.12, 0.015, 0.22);
    const phoneMat = new THREE.MeshStandardMaterial({ color: 0xfacc15, metalness: 0.9, roughness: 0.2 });
    const phone = new THREE.Mesh(phoneGeo, phoneMat);
    phone.position.set(-0.45, 1.12, 0.55);
    parentGroup.add(phone);
}

// -------------------------------------------------------------
// 5 UZMAN YAPAY ZEKA AJANI
// -------------------------------------------------------------
function buildSpecialistAgents() {
    // 1. SCANNER AGENT (Cyber Blue - 200+ Pariteyi Tarar)
    buildSingleAgent({
        id: 'scanner',
        name: 'Scanner Agent',
        pos: [-2.1, 0, -0.6],
        rotY: Math.PI / 2, // Masanın merkezine bakıyor
        suitColor: 0x1d4ed8, // Parlak Mavi
        hairColor: 0x334155,
        anchorOffset: [0, 2.2, 0]
    });

    // 2. TA ANALYST (Purple - Mum, EMA, RSI, Bollinger Uzmanı)
    buildSingleAgent({
        id: 'ta',
        name: 'Teknik Analist',
        pos: [-2.1, 0, 0.8],
        rotY: Math.PI / 2,
        suitColor: 0x7e22ce, // Mor / Eflatun
        hairColor: 0x475569,
        hasGlasses: true,
        anchorOffset: [0, 2.2, 0]
    });

    // 3. NEWS & MACRO AGENT (Amber / Orange - Küresel İstihbarat)
    buildSingleAgent({
        id: 'news',
        name: 'Haber & Makro Ajanı',
        pos: [2.1, 0, 0.8],
        rotY: -Math.PI / 2,
        suitColor: 0xd97706, // Amber / Turuncu
        hairColor: 0x1e293b,
        anchorOffset: [0, 2.2, 0]
    });

    // 4. RISK OFFICER (Crimson Red - Kasa Kalkanı & Disiplin Şefi)
    buildSingleAgent({
        id: 'risk',
        name: 'Risk & Kasa Şefi',
        pos: [2.1, 0, -0.6],
        rotY: -Math.PI / 2,
        suitColor: 0xb91c1c, // Bordo / Kırmızı
        hairColor: 0x0f172a,
        anchorOffset: [0, 2.2, 0]
    });

    // 5. CHIEF ANALYST (Emerald Green - Patron Efe'nin Sağında Rapor Sunuyor)
    buildSingleAgent({
        id: 'chief',
        name: 'Baş Stratejist',
        pos: [1.15, 0, -1.8],
        rotY: -Math.PI / 4, // Efe ve masaya dönük
        suitColor: 0x059669, // Zümrüt Yeşili
        hairColor: 0x18181b,
        isStanding: true,
        anchorOffset: [0, 2.3, 0]
    });
}

function buildSingleAgent(cfg) {
    const agentGroup = new THREE.Group();
    agentGroup.position.set(...cfg.pos);
    agentGroup.rotation.y = cfg.rotY;

    // Koltuk (Ayakta olan Chief hariç)
    if (!cfg.isStanding) {
        const chairSeatGeo = new THREE.BoxGeometry(0.65, 0.1, 0.65);
        const chairMat = new THREE.MeshStandardMaterial({ color: 0x1e293b, roughness: 0.6 });
        const chair = new THREE.Mesh(chairSeatGeo, chairMat);
        chair.position.y = 0.52;
        chair.castShadow = true;
        agentGroup.add(chair);

        const chairBackGeo = new THREE.BoxGeometry(0.65, 0.75, 0.1);
        const chairBack = new THREE.Mesh(chairBackGeo, chairMat);
        chairBack.position.set(0, 0.95, -0.32);
        agentGroup.add(chairBack);

        const legGeo = new THREE.CylinderGeometry(0.04, 0.04, 0.5, 12);
        const leg = new THREE.Mesh(legGeo, new THREE.MeshStandardMaterial({ color: 0x475569 }));
        leg.position.y = 0.25;
        agentGroup.add(leg);
    }

    // Gövde & Kıyafet
    const clothMat = new THREE.MeshStandardMaterial({ color: cfg.suitColor, roughness: 0.45 });
    const torsoGeo = new THREE.BoxGeometry(0.55, cfg.isStanding ? 0.8 : 0.6, 0.32);
    const torso = new THREE.Mesh(torsoGeo, clothMat);
    torso.position.y = cfg.isStanding ? 1.15 : 1.0;
    torso.castShadow = true;
    agentGroup.add(torso);

    // Kollar
    const armGeo = new THREE.BoxGeometry(0.12, 0.45, 0.12);
    [-0.32, 0.32].forEach(ax => {
        const arm = new THREE.Mesh(armGeo, clothMat);
        arm.position.set(ax, cfg.isStanding ? 1.05 : 0.95, 0.12);
        arm.rotation.x = Math.PI / 4;
        agentGroup.add(arm);
    });

    // Baş & Saç
    const headGroup = new THREE.Group();
    headGroup.position.set(0, cfg.isStanding ? 1.7 : 1.48, 0);

    const skinMat = new THREE.MeshStandardMaterial({ color: 0xfbd0b0, roughness: 0.6 });
    const headGeo = new THREE.BoxGeometry(0.3, 0.32, 0.28);
    const head = new THREE.Mesh(headGeo, skinMat);
    head.castShadow = true;
    headGroup.add(head);

    const hairMat = new THREE.MeshStandardMaterial({ color: cfg.hairColor, roughness: 0.8 });
    const hairGeo = new THREE.BoxGeometry(0.32, 0.12, 0.3);
    const hair = new THREE.Mesh(hairGeo, hairMat);
    hair.position.set(0, 0.16, 0);
    headGroup.add(hair);

    // Gözlük (Opsiyonel)
    if (cfg.hasGlasses) {
        const glassesGeo = new THREE.BoxGeometry(0.26, 0.06, 0.04);
        const glassesMat = new THREE.MeshStandardMaterial({ color: 0x0284c7, metalness: 0.8 });
        const glasses = new THREE.Mesh(glassesGeo, glassesMat);
        glasses.position.set(0, 0.02, 0.16);
        headGroup.add(glasses);
    }

    agentHeads[cfg.id] = headGroup;
    agentGroup.add(headGroup);

    // Çapa Noktasını Hesapla
    bubbleAnchors[cfg.id].pos = new THREE.Vector3(
        cfg.pos[0] + cfg.anchorOffset[0],
        cfg.pos[1] + cfg.anchorOffset[1],
        cfg.pos[2] + cfg.anchorOffset[2]
    );

    officeScene.add(agentGroup);
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
}

// -------------------------------------------------------------
// 3D DÜNYADAN 2D EKRANA BALON YANSITMASI (60 FPS PROJECTION)
// -------------------------------------------------------------
function updateBubblePositions() {
    if (!officeRenderer || !officeCamera) return;
    const target = document.getElementById('officeCanvasTarget');
    if (!target) return;
    const rect = target.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) return;

    Object.keys(bubbleAnchors).forEach(key => {
        const item = bubbleAnchors[key];
        if (!item || !item.pos || !item.el) return;

        const p = item.pos.clone();
        p.project(officeCamera);

        // Kamera arkasındaysa gizle
        if (p.z > 1 || p.z < -1) {
            item.el.style.opacity = '0';
            item.el.style.pointerEvents = 'none';
            return;
        }

        const screenX = (p.x * 0.5 + 0.5) * rect.width;
        const screenY = (-(p.y * 0.5) + 0.5) * rect.height;

        item.el.style.left = screenX + 'px';
        item.el.style.top = screenY + 'px';
        item.el.style.opacity = '1';
        item.el.style.pointerEvents = 'auto';
    });
}

// -------------------------------------------------------------
// KAMERA KONTROLLERİ & YUMUŞAK GEÇİŞ (CAMERA PRESETS)
// -------------------------------------------------------------
function setOfficeCamera(mode = 'boss') {
    ['btnCamBoss', 'btnCamTable', 'btnCamIso'].forEach(id => {
        const btn = document.getElementById(id);
        if (btn) btn.classList.remove('active');
    });

    if (mode === 'boss') {
        const btn = document.getElementById('btnCamBoss');
        if (btn) btn.classList.add('active');
        // Patron Efe'ye sinematik yakın çekim
        camTargetPos = new THREE.Vector3(0, 2.3, -0.4);
        camLookTarget = new THREE.Vector3(0, 1.7, -2.2);
        playOfficeSound('chime');
    } else if (mode === 'table') {
        const btn = document.getElementById('btnCamTable');
        if (btn) btn.classList.add('active');
        // Masayı ve tüm ajanları gören açı
        camTargetPos = new THREE.Vector3(0, 4.2, 4.4);
        camLookTarget = new THREE.Vector3(0, 1.3, 0.1);
        playOfficeSound('click');
    } else if (mode === 'iso') {
        const btn = document.getElementById('btnCamIso');
        if (btn) btn.classList.add('active');
        // Sims tarzı klasik izometrik kuşbakışı
        camTargetPos = new THREE.Vector3(7.2, 7.8, 8.2);
        camLookTarget = new THREE.Vector3(0, 1.2, 0);
        playOfficeSound('click');
    }
}

// -------------------------------------------------------------
// ANİMASYON DÖNGÜSÜ (RENDER LOOP)
// -------------------------------------------------------------
function animateOffice(time) {
    officeAnimFrameId = requestAnimationFrame(animateOffice);

    // 1. Sims Plumbob Animasyonu: Sürekli Dönüş + Yumuşak Yukarı/Aşağı Yüzme
    if (plumbobMesh) {
        plumbobMesh.rotation.y += 0.025;
        plumbobMesh.position.y = 2.3 + Math.sin(time * 0.003) * 0.06;
    }

    // 2. Karakterlerin Nefes Alma & Hafif Kafa Hareketleri
    if (bossHeadMesh) {
        bossHeadMesh.rotation.x = Math.sin(time * 0.0018) * 0.04;
        bossHeadMesh.rotation.y = Math.sin(time * 0.001) * 0.08;
    }
    Object.keys(agentHeads).forEach((key, idx) => {
        const head = agentHeads[key];
        if (head) {
            head.rotation.x = Math.sin(time * 0.002 + idx) * 0.05;
            head.rotation.y = Math.cos(time * 0.0015 + idx) * 0.06;
        }
    });

    // 3. Yumuşak Kamera Geçişi (Lerp Interpolation)
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

    // 4. OrbitControls Güncellemesi
    if (officeControls) {
        officeControls.update();
    }

    // 5. Baloncuk Pozisyonlarını 2D Ekrana Yansıt
    updateBubblePositions();

    // 6. Sahneyi Çiz
    if (officeRenderer && officeScene && officeCamera) {
        officeRenderer.render(officeScene, officeCamera);
    }
}

// -------------------------------------------------------------
// CANLI VERİ ENTEGRASYONU (API/DATA İLE OTOMATİK BESLENİR)
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

        // Monitörleri ve Masa Işığını Canlı Kâr/Zarar Rengine Boya
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

        // Üst Bilgi Rozeti
        if (statusPill) {
            statusPill.innerHTML = `⚡ <strong>CANLI İŞLEM:</strong> ${sym} (${pnlText})`;
            statusPill.style.color = isProfit ? '#10b981' : '#ef4444';
        }
    } else {
        // Aktif İşlem Yok: Standart Mavi Tarama Modu
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

    // 2. Patron Efe'nin Dinamik Konuşması
    if (bubbleAnchors.boss.bodyEl) {
        if (positions.length > 0) {
            bubbleAnchors.boss.bodyEl.innerText = "İşlem açık beyler! Hedeflere sadık kalın, stop seviyesini koruyun.";
        } else if (btc.status === 'DEAD_CHOP') {
            bubbleAnchors.boss.bodyEl.innerText = "Piyasada ölü testere var. Acele işlem yok, sermaye koruma kuralımız #1!";
        } else if (btc.status === 'BULLISH') {
            bubbleAnchors.boss.bodyEl.innerText = "BTC yukarı yönlü kırılımda. En güçlü pariteyi önüme getirin!";
        } else if (btc.status === 'DUMP_ALERT') {
            bubbleAnchors.boss.bodyEl.innerText = "Sert düşüş alarmı! Risk Şefi, kaldıraçları ve teminatı kilitle.";
        } else {
            bubbleAnchors.boss.bodyEl.innerText = "Piyasayı tarayın beyler, disiplin en büyük kârımızdır.";
        }
    }

    // 3. Scanner Agent Konuşması (Son taranan coin)
    if (bubbleAnchors.scanner.bodyEl && logs.length > 0) {
        const lastLog = logs[0];
        const coin = lastLog.symbol || 'PARİTE';
        const stat = lastLog.status || 'TARANDI';
        bubbleAnchors.scanner.bodyEl.innerText = `Radar: ${coin} incelendi [${stat}]. 200 parite döngüsü canlı.`;
    }

    // 4. TA Analyst Konuşması (BTC 4s bant daralması)
    if (bubbleAnchors.ta.bodyEl) {
        const range = btc.range_pct !== undefined ? btc.range_pct : '0.40';
        bubbleAnchors.ta.bodyEl.innerText = `BTC 4s bant daralması: %${range}. EMA & Bollinger sıkışmasını gözlüyorum.`;
    }

    // 5. News & Macro Agent Konuşması
    if (bubbleAnchors.news.bodyEl) {
        bubbleAnchors.news.bodyEl.innerText = "Funding rate stabil, global piyasalarda acil likidite şoku yok.";
    }

    // 6. Risk Officer Konuşması
    if (bubbleAnchors.risk.bodyEl) {
        bubbleAnchors.risk.bodyEl.innerText = "Kasa Kalkanı devrede: Maks 5x kaldıraç, %1.5 risk tavanı kilitli.";
    }

    // 7. Chief Analyst Konuşması
    if (bubbleAnchors.chief.bodyEl) {
        if (positions.length > 0) {
            bubbleAnchors.chief.bodyEl.innerText = "Efe Bey, açılan pozisyon risk/ödül oranına uygun şekilde takip ediliyor.";
        } else {
            bubbleAnchors.chief.bodyEl.innerText = "Efe Bey, piyasa şu an beklemede. Şartlar netleşirse komite onaylayacak.";
        }
    }

    // 8. Duvardaki TV Ticker'ını Güncelle
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
