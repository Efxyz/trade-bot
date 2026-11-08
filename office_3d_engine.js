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
        const allKeys = ['boss', 'scanner', 'ta', 'risk', 'news', 'chief', 'mehmet', 'berat'];
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
