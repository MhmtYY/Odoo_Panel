/* Odoo Yönetim Paneli arayüzü: kabuk, API, yönlendirme, iş takibi, ortak parçalar.
   Ekranlar ekran_platform.js ve ekran_odoo.js'te; hepsi app.js olarak birleştirilir (araclar/arayuz_derle.py). */
const $ = (s, k = document) => k.querySelector(s);
const $$ = (s, k = document) => [...k.querySelectorAll(s)];
const esc = (m) => String(m ?? "").replace(/[&<>"']/g, (h) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[h]));

const S = { ben: null, csrf: "", odoolar: null, bosBellek: null, tema: "light", saglik: null };
const depo = {
    al(a) { try { return localStorage.getItem("oyp_" + a); } catch { return null; } },
    yaz(a, d) { try { localStorage.setItem("oyp_" + a, d); } catch { /* özel pencerede depolama olmayabilir */ } },
};
let R = { ekran: "odoolar" };

/* ---------- biçimlendirme ---------- */
const DK = 60e3, SA = 3600e3, GUN = 86400e3;
const AYLAR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"];
const iki = (n) => String(n).padStart(2, "0");
const ms = (iso) => (iso ? new Date(iso).getTime() : null);
const gunBasi = (t) => { const g = new Date(t); g.setHours(0, 0, 0, 0); return g.getTime(); };
function gunEtiketi(t) {
    const fark = Math.round((gunBasi(Date.now()) - gunBasi(t)) / GUN);
    if (fark === 0) return "Bugün";
    if (fark === 1) return "Dün";
    const g = new Date(t);
    return `${g.getDate()} ${AYLAR[g.getMonth()]} ${g.getFullYear()}`;
}
function goreli(iso) {
    const t = typeof iso === "number" ? iso : ms(iso);
    if (!t) return "-";
    const f = Date.now() - t;
    if (f < DK) return "az önce";
    if (f < SA) return `${Math.floor(f / DK)} dakika önce`;
    if (f < GUN) return `${Math.floor(f / SA)} saat önce`;
    return `${Math.floor(f / GUN)} gün önce`;
}
function saat(iso) { const g = new Date(ms(iso)); return `${iki(g.getHours())}:${iki(g.getMinutes())}`; }
function tarihSaat(iso) { if (!iso) return "-"; const g = new Date(ms(iso)); return `${iki(g.getDate())}.${iki(g.getMonth() + 1)}.${g.getFullYear()} ${saat(iso)}`; }
const sayi = (n, b = 1) => Number(n).toLocaleString("tr-TR", { maximumFractionDigits: b, minimumFractionDigits: 0 });
function boyutMb(mb) { if (mb == null) return "-"; return mb >= 1024 ? `${sayi(mb / 1024)} GB` : `${sayi(mb, 0)} MB`; }
const boyutBayt = (b) => boyutMb(b / 1048576);
const kisa = (sha) => (sha ? String(sha).slice(0, 7) : "-");
const alanAdi = (adres) => String(adres || "").replace(/^https?:\/\//, "");

/* ---------- simgeler ---------- */
const IKONLAR = {
    odoolar: '<rect x="3" y="4" width="18" height="6" rx="1.5"/><rect x="3" y="14" width="18" height="6" rx="1.5"/><path d="M7 7h.01M7 17h.01"/>',
    kullanici: '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0"/><path d="M16 4.8a3.5 3.5 0 0 1 0 6.4M18 14.6a6.5 6.5 0 0 1 3.5 5.4"/>',
    denetim: '<rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 4h6v3H9zM9 12h6M9 16h4"/>',
    deploy: '<circle cx="6" cy="5" r="2"/><circle cx="6" cy="19" r="2"/><circle cx="18" cy="8" r="2"/><path d="M6 7v10M18 10c0 4-6 3-12 5"/>',
    izleme: '<path d="M3 12h4l3-7 4 14 3-7h4"/>',
    log: '<path d="M8 6h13M8 12h13M8 18h13M3.5 6h.01M3.5 12h.01M3.5 18h.01"/>',
    yedek: '<ellipse cx="12" cy="5.5" rx="8" ry="3"/><path d="M4 5.5v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6M4 11.5v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6"/>',
    modul: '<path d="M12 3l8 4.5v9L12 21l-8-4.5v-9z"/><path d="M4 7.5l8 4.5 8-4.5M12 12v9"/>',
    ayar: '<path d="M4 7h9M17 7h3M4 17h3M11 17h9"/><circle cx="15" cy="7" r="2"/><circle cx="9" cy="17" r="2"/>',
    dis: '<path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>',
    gunes: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
    ay: '<path d="M20 14.5A8.5 8.5 0 1 1 9.5 4a7 7 0 0 0 10.5 10.5z"/>',
    cikis: '<path d="M10 4H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h4M15 8l4 4-4 4M19 12H9"/>',
    menu: '<path d="M4 7h16M4 12h16M4 17h16"/>',
    tik: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    uyari: '<path d="M12 4l9 16H3z"/><path d="M12 10v4.5M12 17.5h.01"/>',
    hata: '<path d="M7 7l10 10M17 7L7 17"/>',
    saat: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    ok: '<path d="M4 12h16M14 6l6 6-6 6"/>',
    geri: '<path d="M4 9h11a5 5 0 0 1 0 10H9"/><path d="M8 5L4 9l4 4"/>',
    yenile: '<path d="M20 11a8 8 0 0 0-14-4.5L4 9M4 13a8 8 0 0 0 14 4.5l2-2.5"/><path d="M4 4v5h5M20 20v-5h-5"/>',
    indir: '<path d="M12 4v11M7 11l5 5 5-5M4 20h16"/>',
    yukle: '<path d="M12 16V5M7 9l5-5 5 5M4 20h16"/>',
    ara: '<circle cx="11" cy="11" r="7"/><path d="M20 20l-4-4"/>',
    pr: '<circle cx="6" cy="6" r="2"/><circle cx="6" cy="18" r="2"/><circle cx="18" cy="18" r="2"/><path d="M6 8v8M18 16V9a2 2 0 0 0-2-2h-3M15 4l-3 3 3 3"/>',
    webhook: '<path d="M13 3L5 14h6l-1 7 8-11h-6z"/>',
    el: '<path d="M8 5v14l11-7z"/>',
    dur: '<rect x="7" y="6" width="3.5" height="12" rx="1"/><rect x="13.5" y="6" width="3.5" height="12" rx="1"/>',
    artik: '<path d="M12 5v14M5 12h14"/>',
    don: '<path d="M21 12a9 9 0 1 1-3-6.7"/>',
    anahtar: '<circle cx="8" cy="15" r="4"/><path d="M11 12l9-9M16 7l3 3"/>',
    bilgi: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>',
    kopya: '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/>',
};
const GITHUB_YOL = "M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z";
function ikon(ad, b = 16, ek = "") {
    if (ad === "github") return `<svg width="${b}" height="${b}" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true" ${ek}><path d="${GITHUB_YOL}"/></svg>`;
    return `<svg width="${b}" height="${b}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" ${ek}>${IKONLAR[ad] || ""}</svg>`;
}
const LOGO = TASARIM.logoYan;

/* ---------- küçük parçalar ---------- */
function uyariKutu(tur, html, ik) {
    const simge = ik || { kirmizi: "uyari", sari: "uyari", mavi: "bilgi", gri: "bilgi" }[tur];
    return `<div class="uyari-kutu ${tur}">${ikon(simge, 16)}<div>${html}</div></div>`;
}
function rozetDurum(durum) {
    if (durum === "running") return `<span class="rozet calisiyor"><i class="nokta calisiyor"></i>Çalışıyor</span>`;
    if (!durum || durum === "yok") return `<span class="rozet"><i class="nokta durdu"></i>Konteyner yok</span>`;
    return `<span class="rozet"><i class="nokta durdu"></i>Durduruldu</span>`;
}
const SERI_ADI = (seri) => (seri ? `Odoo ${seri}` : "Odoo");
function olcer(oran, sinif = "") { return `<div class="olcer ${sinif}"><i style="width:${Math.min(100, Math.max(0, oran)).toFixed(1)}%"></i></div>`; }
function bosDurum(baslik, metin, dugmeler = "", simge = "bilgi") {
    return `<div class="kart bos-durum">${ikon(simge, 30, 'class="soluk"')}<h2 class="uste-az">${baslik}</h2><p class="soluk">${metin}</p>${dugmeler ? `<div class="dugmeler">${dugmeler}</div>` : ""}</div>`;
}
function hataKart(e) {
    return uyariKutu("kirmizi", `<strong>Yüklenemedi.</strong> ${esc(e && e.message ? e.message : e)} <button class="btn kucuk" data-eylem="yeniden-ciz">Tekrar dene</button>`);
}

/* ---------- yetki ---------- */
const yetkili = (y) => !!(S.ben && S.ben.yetkiler.includes(y));
const tumKapsam = () => !!(S.ben && S.ben.kapsam === "*");
const bulOdoo = (id) => (S.odoolar || []).find((o) => o.id === id);
function tekOdoo() {
    if (tumKapsam() || !S.odoolar) return null;
    return S.odoolar.length === 1 ? S.odoolar[0] : null;
}

/* ---------- API ---------- */
class ApiHata extends Error {
    constructor(kod, mesaj) { super(mesaj); this.kod = kod; }
}
async function api(yontem, yol, govde, secenek = {}) {
    const basliklar = {};
    let veri;
    if (secenek.ham !== undefined) { veri = secenek.ham; basliklar["Content-Type"] = secenek.tur || "application/octet-stream"; }
    else if (govde !== undefined) { veri = JSON.stringify(govde); basliklar["Content-Type"] = "application/json"; }
    if (yontem !== "GET") basliklar["X-CSRF"] = S.csrf;
    let yanit;
    try {
        yanit = await fetch(yol, { method: yontem, headers: basliklar, body: veri, credentials: "same-origin", cache: "no-store" });
    } catch (e) {
        throw new ApiHata(0, "Sunucuya ulaşılamıyor. Bağlantınızı denetleyin.");
    }
    let j = {};
    try { j = await yanit.json(); } catch { /* boş yanıt */ }
    if (yanit.status === 401 && !secenek.giris) { oturumBitti(j.hata); throw new ApiHata(401, j.hata || "Oturum kapandı."); }
    if (!yanit.ok) throw new ApiHata(yanit.status, j.hata || `İstek başarısız (${yanit.status}).`);
    return j;
}
const ajan = {
    al: (yol) => api("GET", "/api/ajan/" + yol),
    gonder: (yol, govde = {}) => api("POST", "/api/ajan/" + yol, govde),
};
async function odoolariYukle() {
    const v = await ajan.al("odoolar");
    S.odoolar = v.odoolar;
    S.bosBellek = v.bos_bellek_mb ?? null;
    return S.odoolar;
}
function oturumBitti(mesaj) {
    if (!S.ben) return;
    S.ben = null;
    pencereKapat();
    girisCiz(mesaj || "Oturum süresi doldu, tekrar giriş yapın.");
}

/* ---------- bildirim ve pencere ---------- */
function bildir(mesaj, hata = false) {
    const el = document.createElement("div");
    el.className = "bildirim" + (hata ? " kirmizi" : "");
    el.innerHTML = ikon(hata ? "uyari" : "tik", 16) + "<span></span>";
    el.querySelector("span").textContent = mesaj;
    const kap = $("#bildirimler");
    const p = $("#pencere");
    if (p.open && kap.parentElement !== p) p.appendChild(kap);
    if (!p.open && kap.parentElement !== document.body) document.body.appendChild(kap);
    kap.appendChild(el);
    setTimeout(() => el.remove(), hata ? 7000 : 4000);
}
async function kopyala(metin) {
    try { await navigator.clipboard.writeText(metin); bildir("Kopyalandı."); }
    catch { bildir("Panoya yazılamadı; metni elle seçip kopyalayın.", true); }
}
let pencereSayac = 0;
function pencereAc(baslik, html, secenek = {}) {
    const p = $("#pencere");
    pencereSayac++;
    p.className = "pencere" + (secenek.genis ? " genis" : "");
    p.dataset.is = secenek.is || "";
    $("#pencere-baslik").innerHTML = baslik;
    const g = $("#pencere-govde");
    g.innerHTML = html;
    g.scrollTop = 0;
    if (!p.open) p.showModal();
    const ilk = g.querySelector("[autofocus]");
    if (ilk) ilk.focus();
    return g;
}
function pencereKapat() {
    const p = $("#pencere");
    pencereSayac++;
    p.dataset.is = "";
    if (p.open) p.close();
    const kap = $("#bildirimler");
    if (kap.parentElement !== document.body) document.body.appendChild(kap);
}
function onayPenceresi({ baslik, metin, dugme, tehlike = false, tur = "sari", evet }) {
    const g = pencereAc(baslik, `${uyariKutu(tur, metin)}
        <div class="dugmeler"><button class="btn ${tehlike ? "tehlike" : "birincil"}" id="onay-evet">${esc(dugme)}</button>
        <button class="btn" data-eylem="pencere-kapat">Vazgeç</button></div>`);
    $("#onay-evet", g).addEventListener("click", (e) => { e.currentTarget.disabled = true; evet(); });
}
/* Geri dönüşü zor işlemde adres elle yazılır (ajan da aynı denetimi yapar) */
function adresOnayi({ baslik, metin, beklenen, dugme, evet }) {
    const g = pencereAc(baslik, `${uyariKutu("kirmizi", metin)}
        <label class="alan">Onaylamak için adresi aynen yazın: <strong>${esc(beklenen)}</strong>
            <input id="onay-alan" autocomplete="off" spellcheck="false" autofocus></label>
        <div class="dugmeler"><button class="btn tehlike" id="onay-evet" disabled>${esc(dugme)}</button>
        <button class="btn" data-eylem="pencere-kapat">Vazgeç</button></div>`);
    const alan = $("#onay-alan", g), d = $("#onay-evet", g);
    alan.addEventListener("input", () => { d.disabled = alan.value.trim().toLowerCase() !== beklenen; });
    d.addEventListener("click", () => { d.disabled = true; evet(alan.value.trim().toLowerCase()); });
}
/* Bir isteği gönderir; hata olursa bildirir. Dönen değer yanıt ya da null. */
async function dene(islev, hataMetni) {
    try { return await islev(); }
    catch (e) {
        if (e.kod !== 401) bildir(`${hataMetni ? hataMetni + ": " : ""}${e.message}`, true);
        return null;
    }
}

/* ---------- iş takibi ---------- */
const IS_DURUM = {
    bekliyor: ["Sırada bekliyor", "islem"], calisiyor: ["Çalışıyor", "islem"], tamam: ["Tamamlandı", "basarili"],
    hata: ["Başarısız", "hata"], atlandi: ["Atlandı", ""],
};
const IZLENEN = new Map();
function isSonucMetni(k) {
    const s = k.sonuc || {};
    if (k.durum === "hata") return s.engel ? `Deploy durdu: ${s.engel}` : (s.hata || k.hata || "İş başarısız oldu.");
    if (k.durum === "atlandi") return k.not || "Yerine daha yeni bir istek geldi.";
    return "";
}
function isGovdesi(k) {
    const adimlar = (k.adimlar || []).map((a) => {
        const simge = { tamam: ikon("tik", 14, 'class="ic-yesil"'), hata: ikon("hata", 14, 'class="ic-kirmizi"'), engel: ikon("uyari", 14, 'class="ic-kirmizi"'), calisiyor: ikon("don", 14, 'class="donen ic-tur"') }[a.durum] || ikon("saat", 14);
        return `<li>${simge}<span>${esc(a.ad)}${a.sure != null && a.durum !== "calisiyor" ? ` <span class="soluk kucuk-yazi">${sayi(a.sure)} sn</span>` : ""}</span></li>`;
    }).join("");
    const [yazi, sinif] = IS_DURUM[k.durum] || [k.durum, ""];
    const sonuc = isSonucMetni(k);
    const uyarilar = (k.uyarilar || []).map((u) => `<li>${ikon("uyari", 14, 'class="ic-sari"')}<span>${esc(u)}</span></li>`).join("");
    return `<p class="kucuk-yazi" style="display:flex;gap:.5rem;align-items:center;flex-wrap:wrap">
            <span class="rozet ${sinif}">${k.durum === "calisiyor" ? ikon("don", 11, 'class="donen"') : ""}${esc(yazi)}</span>
            <span class="soluk">${esc(k.aciklama || k.tur)}${k.kullanici ? ` · ${esc(k.kullanici)}` : ""}</span></p>
        ${sonuc ? uyariKutu(k.durum === "atlandi" ? "gri" : "kirmizi", esc(sonuc)) : ""}
        ${adimlar ? `<ul class="denetim-liste uste-az">${adimlar}</ul>` : ""}
        ${uyarilar ? `<ul class="denetim-liste uste-az">${uyarilar}</ul>` : ""}
        <details ${k.durum === "hata" ? "open" : ""} class="uste-az"><summary class="soluk kucuk-yazi" style="cursor:pointer">Kayıt</summary>
            <pre class="kayit" id="is-kayit">${(k.cikti || "").split("\n").map(logSatiriHtml).join("")}</pre></details>`;
}
function logSatiriHtml(s) {
    const sinif = /HATA|ERROR|CRITICAL|DURDU/.test(s) ? "k-hata" : /UYARI|WARNING/.test(s) ? "k-uyari" : /^== ADIM/.test(s) ? "k-yesil" : "";
    return `<span class="${sinif}">${esc(s)}</span>\n`;
}
/* İşi pencerede izler; pencere kapansa da iş sunucuda sürer ve bitince bildirim gelir. */
function isIzle(isKaydi, baslik, secenek = {}) {
    const id = isKaydi.id;
    if (!secenek.arkada) {
        pencereAc(esc(baslik), `<div id="is-govde">${isGovdesi(isKaydi)}</div>
            <div class="dugmeler" id="is-dugmeler"><button class="btn" data-eylem="pencere-kapat">Arka planda devam etsin</button></div>`, { is: id, genis: true });
    }
    if (IZLENEN.has(id)) return;
    IZLENEN.set(id, { baslik, ...secenek });
    const yokla = async () => {
        let k;
        try { k = await ajan.al(`isler/${id}`); }
        catch (e) { if (e.kod === 401) { IZLENEN.delete(id); return; } setTimeout(yokla, 3000); return; }
        const p = $("#pencere");
        const gorunur = p.open && p.dataset.is === id;
        if (gorunur) {
            const kayit = $("#is-kayit");
            const altta = !kayit || kayit.scrollTop + kayit.clientHeight >= kayit.scrollHeight - 20;
            const acik = kayit && kayit.closest("details").open;
            $("#is-govde").innerHTML = isGovdesi(k);
            const yeni = $("#is-kayit");
            if (acik) yeni.closest("details").open = true;
            if (altta) yeni.scrollTop = yeni.scrollHeight;
        }
        if (k.durum === "bekliyor" || k.durum === "calisiyor") { setTimeout(yokla, 1200); return; }
        const bilgi = IZLENEN.get(id);
        IZLENEN.delete(id);
        if (gorunur) {
            const ek = bilgi.kapanis ? bilgi.kapanis(k) : "";
            $("#is-dugmeler").innerHTML = `${ek}<button class="btn ${ek ? "" : "birincil"}" data-eylem="is-kapat">Kapat</button>`;
        } else {
            bildir(`${bilgi.baslik}: ${IS_DURUM[k.durum] ? IS_DURUM[k.durum][0].toLowerCase() : k.durum}.`, k.durum === "hata");
        }
        if (bilgi.bitince) await bilgi.bitince(k);
        arkadaYenile();
    };
    setTimeout(yokla, 600);
}
async function isBaslat(istek, baslik, secenek = {}) {
    const k = await dene(istek, baslik);
    if (k && k.id) isIzle(k, baslik, secenek);
    return k;
}

/* ---------- menü ve yönlendirme ---------- */
const PLATFORM_MENU = [
    { ad: "odoolar", baslik: "Odoo'lar", ikon: "odoolar" },
    { ad: "kullanicilar", baslik: "Kullanıcılar ve roller", ikon: "kullanici", yetki: "kullanicilar" },
    { ad: "denetim", baslik: "Denetim kaydı", ikon: "denetim", yetki: "izle" },
];
const ODOO_SEKMELER = [
    { ad: "deploylar", baslik: "Deploylar", ikon: "deploy" },
    { ad: "izleme", baslik: "İzleme", ikon: "izleme" },
    { ad: "loglar", baslik: "Loglar", ikon: "log" },
    { ad: "yedekler", baslik: "Yedekler", ikon: "yedek", yetki: "yedekAl" },
    { ad: "moduller", baslik: "Modüller", ikon: "modul" },
    { ad: "ayarlar", baslik: "Ayarlar", ikon: "ayar", yetkiler: ["github", "stagingYenile", "sil", "bagla"] },
];
const sekmeAcik = (s) => (!s.yetki || yetkili(s.yetki)) && (!s.yetkiler || s.yetkiler.some(yetkili));
function menuAcik(m) {
    if (m.yetki && !yetkili(m.yetki)) return false;
    if (m.ad === "odoolar" && tekOdoo()) return false;
    return true;
}
function rotaCoz() {
    const p = location.hash.replace(/^#\/?/, "").split("/").filter(Boolean).map(decodeURIComponent);
    if (p[0] === "odoo" && p[1]) {
        const sekme = ODOO_SEKMELER.find((s) => s.ad === p[3] && sekmeAcik(s));
        return { ekran: "odoo", odoo: p[1], ortam: p[2] === "staging" ? "staging" : "production", sekme: sekme ? sekme.ad : "deploylar" };
    }
    const m = PLATFORM_MENU.find((x) => x.ad === p[0]);
    if (m && menuAcik(m)) return { ekran: m.ad };
    const tek = tekOdoo();
    return tek ? { ekran: "odoo", odoo: tek.id, ortam: "production", sekme: "deploylar" } : { ekran: "odoolar" };
}
const odooRota = (id, ortam = "production", sekme = "deploylar") => `#/odoo/${encodeURIComponent(id)}/${ortam}/${sekme}`;
function git(h) { if (location.hash === h) { R = rotaCoz(); ciz(); } else location.hash = h; }

/* ---------- kabuk ---------- */
function kabukKur() {
    if ($("#yan")) return;
    $("#kok").innerHTML = `
        <div class="uygulama">
            <aside class="yan" id="yan" aria-label="Ana menü"></aside>
            <div class="yan-ortu" data-eylem="menu-kapat"></div>
            <div class="govde">
                <header class="mobil-ust">
                    <button class="yan-ikon" data-eylem="menu-ac" aria-label="Menüyü aç">${ikon("menu", 22)}</button>
                    <span class="marka-logo">${LOGO}</span><span class="marka-ad">Odoo Yönetim Paneli</span>
                </header>
                <main class="icerik" id="icerik"></main>
            </div>
        </div>`;
}
function odooNoktasi(o) {
    const p = o.ortamlar.production;
    if (!p) return ["durdu", "Production yok"];
    if (p.mesgul) return ["uyari", "İşlem sürüyor"];
    return p.durum === "running" ? ["calisiyor", "Çalışıyor"] : ["durdu", "Durduruldu"];
}
function yanCiz() {
    const yan = $("#yan");
    if (!yan) return;
    const liste = S.odoolar || [];
    const tek = tekOdoo();
    const secili = R.ekran === "odoo" ? R.odoo : null;
    const calisan = liste.filter((o) => o.ortamlar.production && o.ortamlar.production.durum === "running").length;
    const menu = PLATFORM_MENU.filter(menuAcik).map((m) => `
        <a class="yan-oge ${R.ekran === m.ad ? "etkin" : ""}" href="#/${m.ad}">${ikon(m.ikon)}<span>${esc(m.baslik)}</span>
            ${m.ad === "odoolar" ? `<span class="sayi">${calisan}/${liste.length}</span>` : ""}</a>`).join("");
    const odoolar = liste.map((o) => {
        const [nokta, yazi] = odooNoktasi(o);
        return `<a class="yan-oge ${secili === o.id ? "etkin" : ""}" href="${odooRota(o.id)}" title="${esc(o.firma)}: ${yazi}">
            <i class="nokta ${nokta}" aria-label="${yazi}"></i><span class="yan-odoo-ad">${esc(o.firma)}</span><span class="sayi">${esc(o.seri || "")}</span></a>`;
    }).join("");
    const ben = S.ben;
    yan.innerHTML = `
        <div class="marka"><span class="marka-logo">${LOGO}</span>
            <div style="min-width:0"><div class="marka-ad">Odoo Yönetim Paneli</div><div class="marka-alt tasma-kes">${esc(tek ? tek.firma : "Çoklu Odoo Yönetimi")}</div></div></div>
        ${menu ? `<nav aria-label="Panel">${menu}</nav>` : ""}
        <div class="yan-bolum"><span>${tumKapsam() ? "Odoo'lar" : "Erişebildiğiniz Odoo'lar"}</span></div>
        <nav aria-label="Odoo'lar">${odoolar || `<span class="yan-oge soluk" style="cursor:default">Henüz yok</span>`}</nav>
        <div class="yan-alt">
            <div class="yan-kullanici">
                <span class="avatar">${esc(ben.kullanici.slice(0, 2).toUpperCase())}</span>
                <div class="yan-kullanici-ad" style="flex:1;min-width:0"><div class="tasma-kes">${esc(ben.kullanici)}</div>
                    <div class="yan-kullanici-rol">${esc(ben.rol_adi)}</div></div>
                <button class="yan-ikon" data-eylem="sifre-degistir" title="Şifremi değiştir" aria-label="Şifremi değiştir">${ikon("anahtar", 17)}</button>
                <button class="yan-ikon" data-eylem="tema" title="Temayı değiştir" aria-label="Temayı değiştir">${ikon(S.tema === "dark" ? "gunes" : "ay", 17)}</button>
                <button class="yan-ikon" data-eylem="cikis" title="Çıkış" aria-label="Çıkış">${ikon("cikis", 17)}</button>
            </div>
        </div>`;
}

/* Ekran çizimi: veri yüklenirken eski içerik kalır; 250 ms'den uzun sürerse "yükleniyor" görünür. */
let cizimNo = 0;
let temizleyiciler = [];
function temizle() { temizleyiciler.forEach((f) => f()); temizleyiciler = []; }
async function ciz(secenek = {}) {
    if (!S.ben) return;
    const no = ++cizimNo;
    kabukKur();
    if (!S.odoolar) await dene(odoolariYukle, "Odoo listesi");
    if (no !== cizimNo) return;
    yanCiz();
    const kap = $("#icerik");
    const bekle = secenek.sessiz ? null : setTimeout(() => { if (no === cizimNo) kap.innerHTML = `<p class="soluk" style="padding:1rem 0">${ikon("don", 15, 'class="donen"')} Yükleniyor...</p>`; }, 250);
    let html, sonra;
    try {
        if (R.ekran === "odoo") [html, sonra] = await odooEkrani(R);
        else [html, sonra] = await PLATFORM[R.ekran]();
    } catch (e) {
        html = e.kod === 404 ? bosDurum("Bulunamadı", esc(e.message), `<a class="btn" href="#/odoolar">Odoo'lara dön</a>`, "uyari") : hataKart(e);
    }
    clearTimeout(bekle);
    if (no !== cizimNo) return;
    temizle();
    kap.innerHTML = html;
    if (sonra) sonra();
}
/* İş bittiğinde ya da arka planda: formlu ekranlarda yazılan metin kaybolmasın diye yalnız güvenli ekranlar yeniden çizilir */
async function arkadaYenile() {
    if (!S.ben) return;
    await dene(odoolariYukle);
    yanCiz();
    const formlu = R.ekran === "odoo" && R.sekme === "ayarlar";
    if (!formlu && !$("#pencere").open) ciz({ sessiz: true });
}

/* ---------- giriş ---------- */
function girisCiz(mesaj) {
    temizle();
    $("#kok").innerHTML = `
        <section class="giris">
            <form class="kart giris-kart" data-form="giris">
                <span class="marka-logo">${LOGO}</span><h1 style="font-size:1.25rem">Odoo Yönetim Paneli</h1>
                <p class="soluk">Hesabınızla giriş yapın</p>
                ${mesaj ? uyariKutu("sari", esc(mesaj)) : ""}
                <label class="alan">Kullanıcı adı<input name="k" autocomplete="username" autocapitalize="none" spellcheck="false" required autofocus></label>
                <label class="alan">Şifre<input name="s" type="password" autocomplete="current-password" required></label>
                <button class="btn birincil genis uste" type="submit">Giriş yap</button>
                <p class="soluk kucuk-yazi uste-az" id="giris-hata" role="alert"></p>
            </form>
        </section>`;
    const ilk = $("#kok [autofocus]");
    if (ilk) ilk.focus();
}
async function benYukle() {
    const ben = await api("GET", "/api/ben", undefined, { giris: true });
    S.ben = ben;
    S.csrf = ben.csrf;
    S.odoolar = null;
}

/* ---------- olay dağıtımı ---------- */
const EYLEM = {
    "pencere-kapat": pencereKapat,
    /* biten işin penceresi kapanınca ekran yeni durumla çizilir */
    "is-kapat": () => { pencereKapat(); ciz({ sessiz: true }); },
    "menu-ac": () => document.body.classList.add("menu-acik"),
    "menu-kapat": () => document.body.classList.remove("menu-acik"),
    "yeniden-ciz": () => ciz(),
    kopyala: (el) => kopyala(el.dataset.metin),
    tema() {
        S.tema = S.tema === "dark" ? "light" : "dark";
        document.documentElement.dataset.theme = S.tema;
        depo.yaz("tema", S.tema);
        yanCiz();
    },
    async cikis() {
        await dene(() => api("POST", "/api/cikis", {}));
        S.ben = null;
        S.odoolar = null;
        pencereKapat();
        girisCiz();
    },
    "sifre-degistir"() {
        pencereAc("Şifremi değiştir", `
            <form data-form="sifre-degistir">
                <label class="alan">Şimdiki şifre<input name="eski" type="password" required autocomplete="current-password" autofocus></label>
                <label class="alan">Yeni şifre<input name="yeni" type="password" required minlength="10" autocomplete="new-password"></label>
                <p class="soluk kucuk-yazi uste-az">En az 10 karakter.</p>
                <div class="dugmeler"><button class="btn birincil" type="submit">Değiştir</button><button class="btn" type="button" data-eylem="pencere-kapat">Vazgeç</button></div>
            </form>`);
    },
    "is-ac"(el) {
        dene(async () => {
            const k = await ajan.al(`isler/${el.dataset.is}`);
            isIzle(k, k.aciklama || k.tur);
        }, "İş");
    },
};
const DEGIS = {};
const FORM = {
    async giris(f) {
        const d = f.querySelector("button[type=submit]");
        d.disabled = true;
        try {
            const sonuc = await api("POST", "/api/giris", { kullanici: f.elements.k.value.trim(), sifre: f.elements.s.value }, { giris: true });
            S.csrf = sonuc.csrf;
            await benYukle();
            S.saglik = await ajan.al("saglik").catch(() => null);
            $("#kok").innerHTML = "";
            R = { ekran: "odoolar" };
            await dene(odoolariYukle, "Odoo listesi");
            R = rotaCoz();
            ciz();
        } catch (e) {
            $("#giris-hata").textContent = e.message;
            d.disabled = false;
        }
    },
    async "sifre-degistir"(f) {
        const sonuc = await dene(() => api("POST", "/api/sifrem", { eski: f.elements.eski.value, yeni: f.elements.yeni.value }), "Şifre");
        if (sonuc) { pencereKapat(); bildir("Şifreniz değiştirildi."); }
    },
};
document.addEventListener("click", (e) => {
    const el = e.target.closest("[data-eylem]");
    if (el && !el.disabled) {
        const f = EYLEM[el.dataset.eylem];
        if (f) { e.preventDefault(); f(el, e); return; }
    }
    if (e.target.closest("#yan a")) document.body.classList.remove("menu-acik");
    const satir = e.target.closest("tr[data-hedef]");
    if (satir && !e.target.closest("button, a, input, select")) git(satir.dataset.hedef);
});
document.addEventListener("change", (e) => {
    const el = e.target.closest("[data-degis]");
    if (el && DEGIS[el.dataset.degis]) DEGIS[el.dataset.degis](el, e);
});
document.addEventListener("submit", (e) => {
    const el = e.target.closest("[data-form]");
    if (el && FORM[el.dataset.form]) { e.preventDefault(); FORM[el.dataset.form](el, e); }
});
window.addEventListener("hashchange", () => {
    if (!S.ben) return;
    R = rotaCoz();
    ciz();
    window.scrollTo(0, 0);
    document.body.classList.remove("menu-acik");
});
