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
