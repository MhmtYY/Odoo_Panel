"use strict";
/* ---- tasarim.js ---- */
/* Tasarım: önceki petrol-turkuaz tasarım, Kaydırmalı O logosu. birlestir.py hangi tasarımla derlenecekse onu ekler. */
const TASARIM = {
    ad: "petrol",
    logoYan: "<svg viewBox=\"0 0 120 120\" aria-hidden=\"true\"><path fill=\"#0F2E39\" d=\"M12.16 85.08A45.98 45.98 0 0 1 91.79 39.11L71.88 50.60A22.99 22.99 0 0 0 32.07 73.59Z\"/><path fill=\"#00A79D\" d=\"M28.21 80.89A45.98 45.98 0 0 0 107.84 34.92L87.93 46.41A22.99 22.99 0 0 1 48.12 69.40Z\"/></svg>",
    logoGiris: "<svg viewBox=\"0 0 120 120\" aria-hidden=\"true\"><path fill=\"#0F2E39\" d=\"M12.16 85.08A45.98 45.98 0 0 1 91.79 39.11L71.88 50.60A22.99 22.99 0 0 0 32.07 73.59Z\"/><path fill=\"#00A79D\" d=\"M28.21 80.89A45.98 45.98 0 0 0 107.84 34.92L87.93 46.41A22.99 22.99 0 0 1 48.12 69.40Z\"/></svg>",
    logoGirisKoyu: "<svg viewBox=\"0 0 120 120\" aria-hidden=\"true\"><path fill=\"#0F2E39\" d=\"M12.16 85.08A45.98 45.98 0 0 1 91.79 39.11L71.88 50.60A22.99 22.99 0 0 0 32.07 73.59Z\"/><path fill=\"#00A79D\" d=\"M28.21 80.89A45.98 45.98 0 0 0 107.84 34.92L87.93 46.41A22.99 22.99 0 0 1 48.12 69.40Z\"/></svg>",
};

/* ---- temel.js ---- */
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

/* ---- ekran_platform.js ---- */
/* Panel düzeyindeki ekranlar: Odoo listesi, yeni Odoo kur, mevcut Odoo'yu bağla, kullanıcılar, denetim kaydı */
const PLATFORM = {};
const KAYNAK_ADI = { vtest: "test platformu", erp: "ERP", diger: "dış kurulum", panel: "panel" };

/* ---------- Odoo'lar ---------- */
PLATFORM.odoolar = async () => {
    const l = await odoolariYukle();
    yanCiz();
    const dugmeler = `
        ${yetkili("bagla") && tumKapsam() ? `<button class="btn" data-eylem="mevcut-bagla">${ikon("ara", 15)}Mevcut Odoo'yu bağla</button>` : ""}
        ${yetkili("kur") ? `<button class="btn birincil" data-eylem="yeni-odoo">${ikon("artik", 15)}Yeni Odoo kur</button>` : ""}`;
    if (!l.length) {
        return [bosDurum(yetkili("kur") ? "Henüz Odoo yok" : "Erişebildiğiniz Odoo yok",
            yetkili("kur") ? "Yeni bir Odoo kurun ya da sunucuda çalışan bir Odoo'yu panele bağlayın." : "Hesabınıza atanmış Odoo yok. Panel yöneticisiyle görüşün.",
            dugmeler, "odoolar")];
    }
    const calisan = l.filter((o) => o.ortamlar.production && o.ortamlar.production.durum === "running").length;
    const toplam = l.reduce((t, o) => t + Object.values(o.ortamlar).reduce((a, x) => a + ((x && x.kaynak && x.kaynak.bellek_mb) || 0), 0), 0);
    const dikkat = [];
    l.forEach((o) => {
        const p = o.ortamlar.production;
        if (p && p.bekleyen) dikkat.push({ ikon: "saat", sinif: "ic-sari", baslik: `${o.firma}: production'a alınmayı bekleyen commit`, alt: `${kisa(p.bekleyen.commit)} ${p.bekleyen.baslik || ""}`, hedef: odooRota(o.id) });
        if (p && p.durum !== "running") dikkat.push({ ikon: "dur", sinif: "ic-gri", baslik: `${o.firma}: production çalışmıyor`, alt: "Kullanıcılar giriş yapamıyor", hedef: odooRota(o.id, "production", "izleme") });
    });
    return [`
    <div class="baslik-satiri">
        <div><p class="ust-etiket">Panel</p><h1>Odoo'lar</h1>
            <p class="soluk">${l.length} Odoo, ${calisan} çalışıyor. Ortamların kullandığı bellek ${esc(boyutMb(toplam))}${S.bosBellek != null ? `, sunucuda boş ${esc(boyutMb(S.bosBellek))}` : ""}.</p></div>
        <div class="dugmeler" style="margin:0">${dugmeler}</div>
    </div>
    ${dikkat.length ? `<div class="dikkat-listesi">${dikkat.map((d) => `<a class="dikkat" href="${d.hedef}" style="color:inherit;text-decoration:none">${ikon(d.ikon, 16, `class="${d.sinif}" style="margin-top:.15rem"`)}<span><strong>${esc(d.baslik)}</strong><small>${esc(d.alt)}</small></span></a>`).join("")}</div>` : ""}
    <div class="kart tablo-kap">
        <table class="tablo kartli">
            <thead><tr><th>Odoo</th><th>Sürüm</th><th>Production</th><th>Staging</th><th>Kod deposu</th><th>Bellek</th><th class="sag">İşlemler</th></tr></thead>
            <tbody>${l.map(odooSatir).join("")}</tbody>
        </table>
    </div>`];
};
function ortamHucre(ort) {
    if (!ort) return `<span class="soluk kucuk-yazi">Yok</span>`;
    if (ort.mesgul) return `<span class="rozet islem">${ikon("don", 11, 'class="donen"')}İşlem sürüyor</span>`;
    if (ort.durum !== "running") return rozetDurum("exited");
    return `<span style="display:inline-flex;gap:.4rem;align-items:center"><i class="nokta calisiyor"></i>${ort.commit ? `<span class="hash">${esc(kisa(ort.commit))}</span>` : `<span class="kucuk-yazi">Çalışıyor</span>`}</span>`;
}
function odooSatir(o) {
    const p = o.ortamlar.production || {};
    const bellek = Object.values(o.ortamlar).reduce((a, x) => a + ((x && x.kaynak && x.kaynak.bellek_mb) || 0), 0);
    return `<tr class="tiklanir" data-hedef="${odooRota(o.id)}">
        <td><a class="ana-yazi" href="${odooRota(o.id)}">${esc(o.firma)}</a><small><code>${esc(alanAdi(p.adres))}</code></small>
            ${o.tur === "bagli" ? `<small style="display:flex;gap:.3rem;flex-wrap:wrap;margin-top:.2rem"><span class="etiket">${ikon("ara", 11)}bağlandı: ${esc(KAYNAK_ADI[o.kaynak] || o.kaynak)}</span></small>` : ""}</td>
        <td data-etiket="Sürüm"><span class="rozet surum">${esc(o.seri || "-")}</span></td>
        <td data-etiket="Production">${ortamHucre(o.ortamlar.production)}</td>
        <td data-etiket="Staging">${ortamHucre(o.ortamlar.staging)}</td>
        <td data-etiket="Kod deposu">${o.depo ? `<span class="kucuk-yazi tasma-kes" style="display:inline-flex;gap:.3rem;align-items:center">${ikon("github", 13)}${esc(o.depo.ad)}</span>` : `<span class="soluk kucuk-yazi">${o.tur === "bagli" ? "-" : "Bağlı değil"}</span>`}</td>
        <td data-etiket="Bellek"><span class="kucuk-yazi kirilmaz">${bellek ? esc(boyutMb(bellek)) : "-"}</span></td>
        <td class="sag"><div class="islemler">
            ${p.adres ? `<a class="btn kucuk" href="${esc(p.adres)}" target="_blank" rel="noopener noreferrer">Aç ${ikon("dis", 12)}</a>` : ""}
            ${o.tur === "panel" && yetkili("kur") ? `<button class="btn kucuk" data-eylem="giris-bilgisi" data-odoo="${esc(o.id)}">Giriş bilgisi</button>` : ""}
        </div></td>
    </tr>`;
}
EYLEM["giris-bilgisi"] = (el) => dene(async () => {
    const g = await ajan.al(`odoolar/${el.dataset.odoo}/giris`);
    pencereAc("Giriş bilgisi", `
        ${uyariKutu("mavi", "Kurulumda üretilen yönetici şifresi. Odoo'da değiştirildiyse burada eskisi görünür.")}
        <div class="bilgi-satir"><span>Adres</span><a href="${esc(g.adres)}" target="_blank" rel="noopener noreferrer"><code>${esc(alanAdi(g.adres))}</code></a></div>
        <div class="bilgi-satir"><span>Kullanıcı</span><code>${esc(g.kullanici)}</code></div>
        <div class="bilgi-satir"><span>Şifre</span><code>${esc(g.sifre)}</code><button class="btn kucuk" data-eylem="kopyala" data-metin="${esc(g.sifre)}">Kopyala</button></div>
        <div class="dugmeler"><button class="btn birincil" data-eylem="pencere-kapat">Kapat</button></div>`);
}, "Giriş bilgisi");

/* ---------- Yeni Odoo kur ---------- */
EYLEM["yeni-odoo"] = async () => {
    pencereAc("Yeni Odoo kur", `<p class="soluk">${ikon("don", 14, 'class="donen"')} Şablon bilgisi alınıyor...</p>`);
    const belirtec = pencereSayac;
    const s = await dene(() => ajan.al("sablon"), "Şablon");
    if (belirtec !== pencereSayac) return;
    const sablon = s && s.sablon;
    pencereAc("Yeni Odoo kur", `
        <form data-form="yeni-odoo">
            <div class="form-izgara">
                <label class="alan">Ad (adresin ilk parçası)<input name="id" required pattern="[a-z][a-z0-9\\-]{1,20}[a-z0-9]" maxlength="22" autocomplete="off" spellcheck="false" autofocus placeholder="ornekfirma"></label>
                <label class="alan">Firma adı<input name="firma" maxlength="120" autocomplete="off" placeholder="Örnek Firma A.Ş."></label>
            </div>
            <p class="kucuk-yazi soluk uste-az">Adres: <code id="yeni-adres">ad.${esc(S.saglik ? S.saglik.alan : "panel.vekosis.com")}</code>. Küçük harfle başlar; küçük harf, rakam ve tire.</p>
            <h4 class="uste">Başlangıç</h4>
            <label class="secenek"><input type="radio" name="baslangic" value="bos" checked><span><strong>Boş Odoo</strong><small>Yalnız temel modül ve Türkçe. Modüller sonra depodan ya da Uygulamalar ekranından gelir.</small></span></label>
            <label class="secenek ${sablon ? "" : "gizli"}"><input type="radio" name="baslangic" value="sablon" ${sablon ? "" : "disabled"}><span><strong>Test platformunun tam şablonu</strong><small>Bütün modüller kurulu ve ayarlı${sablon ? ` (<code>${esc(sablon.ad)}</code>)` : ""}.</small></span></label>
            <label class="onay-satir uste-az ${sablon ? "" : "gizli"}" id="ornek-satir"><input type="checkbox" name="ornek" checked> Kurgusal örnek veriyle gelsin (müşteri Ayarlar'dan silebilir)</label>
            <label class="alan uste">İmaj<input name="imaj" value="${esc(sablon ? sablon.imaj : "")}" required spellcheck="false" autocomplete="off" placeholder="vekosis/test20:20261108-1"></label>
            <p class="soluk kucuk-yazi">Kurulumda yönetici şifresi üretilir ve bir kez gösterilir; sonradan "Giriş bilgisi" ile görülür.</p>
            <div class="dugmeler"><button class="btn birincil" type="submit">Kur</button><button class="btn" type="button" data-eylem="pencere-kapat">Vazgeç</button></div>
        </form>`);
    const f = $("#pencere-govde form");
    const alan = S.saglik ? S.saglik.alan : "panel.vekosis.com";
    f.elements.id.addEventListener("input", () => { $("#yeni-adres").textContent = `${f.elements.id.value || "ad"}.${alan}`; });
    f.addEventListener("change", () => {
        const sab = f.elements.baslangic.value === "sablon";
        if (sab && sablon) f.elements.imaj.value = sablon.imaj;
        f.elements.imaj.readOnly = sab;
    });
};
FORM["yeni-odoo"] = async (f) => {
    const govde = {
        id: f.elements.id.value.trim(), firma: f.elements.firma.value.trim(), baslangic: f.elements.baslangic.value,
        ornek: f.elements.ornek.checked, imaj: f.elements.imaj.value.trim(),
    };
    await isBaslat(() => ajan.gonder("odoolar", govde), `Kuruluyor: ${govde.id}`, {
        kapanis: (k) => (k.durum === "tamam" ? `<button class="btn birincil" data-eylem="giris-bilgisi" data-odoo="${esc(govde.id)}">Giriş bilgisini göster</button>
            <a class="btn" href="${odooRota(govde.id)}" data-eylem="pencere-kapat-git">Odoo'ya git</a>` : ""),
    });
};
EYLEM["pencere-kapat-git"] = (el) => { pencereKapat(); git(el.getAttribute("href")); };

/* ---------- Mevcut Odoo'yu bağla ---------- */
EYLEM["mevcut-bagla"] = async () => {
    pencereAc("Mevcut Odoo'yu bağla", `<p class="soluk">${ikon("don", 14, 'class="donen"')} Sunucudaki Odoo konteynerleri taranıyor...</p>`, { genis: true });
    const v = await dene(() => ajan.al("bulunanlar"), "Tarama");
    if (!v) return;
    const satirlar = v.bulunanlar.map((b) => `<tr>
        <td class="ana-yazi"><code>${esc(b.konteyner)}</code><small>${esc(b.adres ? alanAdi(b.adres) : "adres bulunamadı")}</small></td>
        <td data-etiket="Kaynak">${esc(KAYNAK_ADI[b.kaynak] || b.kaynak)}</td>
        <td data-etiket="İmaj"><code class="kucuk-yazi">${esc(b.imaj)}</code></td>
        <td data-etiket="Durum">${rozetDurum(b.durum)}</td>
        <td class="sag">${b.bagli_odoo ? `<a class="btn kucuk" href="${odooRota(b.bagli_odoo)}" data-eylem="pencere-kapat-git">Bağlı: ${esc(b.bagli_odoo)}</a>`
            : `<button class="btn kucuk birincil" data-eylem="bagla-sec" data-konteyner="${esc(b.konteyner)}" data-ad="${esc(b.onerilen_ad)}">Bağla</button>`}</td></tr>`).join("");
    pencereAc("Mevcut Odoo'yu bağla", `
        ${uyariKutu("mavi", "Bağlarken hiçbir şey yeniden başlatılmaz, compose dosyasına dokunulmaz. Panel izler, kendi yedeğini alır ve production'dan staging açabilir. Durdurma ve başlatma ayrıca izin verilince açılır; bağlanan kurulumda deploy yok.")}
        <div class="tablo-kap uste-az"><table class="tablo kartli"><thead><tr><th>Konteyner</th><th>Kaynak</th><th>İmaj</th><th>Durum</th><th></th></tr></thead>
        <tbody>${satirlar || `<tr><td colspan="5" class="soluk">Panelin yönetmediği Odoo konteyneri bulunamadı.</td></tr>`}</tbody></table></div>
        <div id="bagla-form"></div>
        <div class="dugmeler"><button class="btn" data-eylem="pencere-kapat">Kapat</button></div>`, { genis: true });
};
EYLEM["bagla-sec"] = (el) => {
    $("#bagla-form").innerHTML = `<form data-form="bagla" class="kart kart-ic uste">
        <h3><code>${esc(el.dataset.konteyner)}</code> bağlanıyor</h3>
        <input type="hidden" name="konteyner" value="${esc(el.dataset.konteyner)}">
        <div class="form-izgara">
            <label class="alan">Paneldeki adı<input name="id" value="${esc(el.dataset.ad)}" required pattern="[a-z][a-z0-9\\-]{1,20}[a-z0-9]" autocomplete="off" spellcheck="false"></label>
            <label class="alan">Firma adı<input name="firma" autocomplete="off" placeholder="Görünecek ad"></label>
        </div>
        <div class="dugmeler"><button class="btn birincil" type="submit">Bağla</button></div></form>`;
    $("#bagla-form input[name=firma]").focus();
};
FORM.bagla = async (f) => {
    const govde = { konteyner: f.elements.konteyner.value, id: f.elements.id.value.trim(), firma: f.elements.firma.value.trim() };
    const v = await dene(() => ajan.gonder("bagla", govde), "Bağlama");
    if (!v) return;
    pencereKapat();
    bildir(`${govde.id} bağlandı.`);
    await dene(odoolariYukle);
    git(odooRota(v.odoo.id));
};

/* ---------- Kullanıcılar ---------- */
PLATFORM.kullanicilar = async () => {
    const v = await api("GET", "/api/kullanicilar");
    const kapsamYazi = (k) => (k.kapsam === "*" ? "Tümü" : k.kapsam.length ? k.kapsam.map((id) => (bulOdoo(id) || { firma: id }).firma).join(", ") : "Hiçbiri");
    return [`
    <div class="baslik-satiri"><div><p class="ust-etiket">Panel</p><h1>Kullanıcılar ve roller</h1>
        <p class="soluk">Kullanıcı yalnız erişimi verilen Odoo'ları görür. Rol neyi yapabileceğini belirler.</p></div>
        <button class="btn birincil" data-eylem="kullanici-ekle">${ikon("artik", 15)}Yeni kullanıcı</button></div>
    <div class="kart tablo-kap" style="margin-bottom:1rem"><table class="tablo kartli">
        <thead><tr><th>Kullanıcı</th><th>Rol</th><th>Erişim</th><th>Son giriş</th><th class="sag">İşlemler</th></tr></thead>
        <tbody>${v.kullanicilar.map((k) => `<tr>
            <td class="ana-yazi">${esc(k.ad)}<small>Eklenme: ${esc(tarihSaat(k.olusturma).slice(0, 10))}</small></td>
            <td data-etiket="Rol"><span class="rozet ${k.rol === "platform" ? "uyari" : k.rol === "yonetici" ? "surum" : ""}">${esc(v.roller[k.rol] || k.rol)}</span></td>
            <td data-etiket="Erişim">${esc(kapsamYazi(k))}</td>
            <td data-etiket="Son giriş">${esc(goreli(k.son_giris))}</td>
            <td class="sag"><div class="islemler">${k.ad === S.ben.kullanici ? `<span class="soluk kucuk-yazi">siz</span>` : `
                ${k.rol !== "platform" ? `<button class="btn kucuk" data-eylem="kullanici-duzenle" data-ad="${esc(k.ad)}" data-rol="${esc(k.rol)}" data-kapsam="${esc(JSON.stringify(k.kapsam))}">Düzenle</button>` : ""}
                <button class="btn kucuk" data-eylem="kullanici-sifre" data-ad="${esc(k.ad)}">Şifre sıfırla</button>
                <button class="btn kucuk tehlike-cizgi" data-eylem="kullanici-sil" data-ad="${esc(k.ad)}">Sil</button>`}
            </div></td></tr>`).join("")}</tbody>
    </table></div>
    <h2 style="margin-bottom:.5rem">Rol ve yetki tablosu</h2>
    <div class="kart tablo-kap"><table class="tablo matris-tablo">
        <thead><tr><th>Yetki</th><th>Platform yöneticisi</th><th>Yönetici</th><th>Kullanıcı</th></tr></thead>
        <tbody>${YETKI_TABLOSU.map(([ad, p, y, k]) => `<tr><td>${esc(ad)}</td>${[p, y, k].map((x) => `<td>${x ? ikon("tik", 16, 'class="ic-yesil" aria-label="Var"') : `<span class="soluk" aria-label="Yok">-</span>`}</td>`).join("")}</tr>`).join("")}</tbody>
    </table></div>`];
};
const YETKI_TABLOSU = [
    ["Odoo kurma", 1, 1, 1], ["Durdurma ve başlatma", 1, 1, 1], ["Yedek alma ve indirme", 1, 1, 1], ["İzleme ve log", 1, 1, 1],
    ["Geri yükleme", 1, 1, 0], ["Odoo silme", 1, 1, 0], ["Modül yükleme (zip)", 1, 1, 0], ["Deploy ve geri alma", 1, 1, 0],
    ["Staging açma ve yenileme", 1, 1, 0], ["GitHub bağlama", 1, 1, 0], ["Kullanıcı yönetimi", 1, 1, 0],
    ["Mevcut Odoo'yu bağlama (bütün Odoo'lara erişimi olan)", 1, 1, 0],
];
function kapsamSecimi(secili) {
    const tum = secili === "*";
    const liste = (S.odoolar || []).map((o) => `<label class="onay-satir"><input type="checkbox" name="kapsam" value="${esc(o.id)}" ${tum || (Array.isArray(secili) && secili.includes(o.id)) ? "checked" : ""}> ${esc(o.firma)} <code class="kucuk-yazi">${esc(o.id)}</code></label>`).join("");
    return `<fieldset class="uste-az" style="border:0;padding:0;margin:0"><legend class="kucuk-yazi">Erişebileceği Odoo'lar</legend>
        ${tumKapsam() ? `<label class="onay-satir"><input type="checkbox" name="tum" ${tum ? "checked" : ""}> <strong>Tümü</strong> (sonradan kurulanlar dahil)</label>` : ""}
        <div style="display:grid;gap:.15rem;max-height:220px;overflow:auto">${liste}</div></fieldset>`;
}
function kapsamOku(f) {
    if (f.elements.tum && f.elements.tum.checked) return "*";
    return $$("input[name=kapsam]:checked", f).map((x) => x.value);
}
function sifreGoster(baslik, ad, sifre) {
    pencereAc(esc(baslik), `
        ${uyariKutu("mavi", "Şifre yalnız bir kez gösterilir. Kullanıcı ilk girişten sonra kendisi değiştirebilir.")}
        <div class="bilgi-satir"><span>Kullanıcı</span><code>${esc(ad)}</code></div>
        <div class="bilgi-satir"><span>Şifre</span><code>${esc(sifre)}</code><button class="btn kucuk" data-eylem="kopyala" data-metin="${esc(sifre)}">Kopyala</button></div>
        <div class="dugmeler"><button class="btn birincil" data-eylem="pencere-kapat">Kapat</button></div>`);
}
EYLEM["kullanici-ekle"] = () => {
    pencereAc("Yeni kullanıcı", `
        <form data-form="kullanici-ekle">
            <label class="alan">Kullanıcı adı<input name="ad" required pattern="[a-z0-9._\\-]{3,30}" autofocus autocomplete="off" spellcheck="false" placeholder="ornek.kullanici"></label>
            <label class="alan">Rol<select name="rol">
                <option value="kullanici">Kullanıcı</option><option value="yonetici">Yönetici</option>
                ${S.ben.rol === "platform" ? `<option value="platform">Platform yöneticisi</option>` : ""}</select></label>
            ${kapsamSecimi([])}
            <div class="dugmeler"><button class="btn birincil" type="submit">Ekle</button><button class="btn" type="button" data-eylem="pencere-kapat">Vazgeç</button></div>
        </form>`);
};
FORM["kullanici-ekle"] = async (f) => {
    const govde = { ad: f.elements.ad.value.trim(), rol: f.elements.rol.value, kapsam: kapsamOku(f) };
    const v = await dene(() => api("POST", "/api/kullanicilar", govde), "Kullanıcı");
    if (!v) return;
    sifreGoster(`Kullanıcı eklendi: ${v.ad}`, v.ad, v.sifre);
    ciz({ sessiz: true });
};
EYLEM["kullanici-duzenle"] = (el) => {
    const ad = el.dataset.ad;
    const kapsam = JSON.parse(el.dataset.kapsam);
    pencereAc(`Düzenle: ${esc(ad)}`, `
        <form data-form="kullanici-duzenle" data-ad="${esc(ad)}" data-rol="${esc(el.dataset.rol)}">
            <label class="alan">Rol<select name="rol">
                <option value="kullanici" ${el.dataset.rol === "kullanici" ? "selected" : ""}>Kullanıcı</option>
                <option value="yonetici" ${el.dataset.rol === "yonetici" ? "selected" : ""}>Yönetici</option>
                ${S.ben.rol === "platform" ? `<option value="platform">Platform yöneticisi</option>` : ""}</select></label>
            ${kapsamSecimi(kapsam)}
            <p class="soluk kucuk-yazi uste-az">Kaydedince kullanıcının oturumu kapanır, yeniden girer.</p>
            <div class="dugmeler"><button class="btn birincil" type="submit">Kaydet</button><button class="btn" type="button" data-eylem="pencere-kapat">Vazgeç</button></div>
        </form>`);
};
FORM["kullanici-duzenle"] = async (f) => {
    const ad = f.dataset.ad;
    const rol = f.elements.rol.value;
    if (rol !== f.dataset.rol && !(await dene(() => api("POST", `/api/kullanicilar/${encodeURIComponent(ad)}/rol`, { rol }), "Rol"))) return;
    if (rol !== "platform" && !(await dene(() => api("POST", `/api/kullanicilar/${encodeURIComponent(ad)}/kapsam`, { kapsam: kapsamOku(f) }), "Erişim"))) return;
    pencereKapat();
    bildir(`${ad} güncellendi.`);
    ciz({ sessiz: true });
};
EYLEM["kullanici-sifre"] = (el) => onayPenceresi({
    baslik: `Şifre sıfırla: ${esc(el.dataset.ad)}`, metin: "Yeni şifre üretilir ve bir kez gösterilir; kullanıcının açık oturumu kapanır.", dugme: "Sıfırla",
    async evet() {
        const v = await dene(() => api("POST", `/api/kullanicilar/${encodeURIComponent(el.dataset.ad)}/sifre`, {}), "Şifre");
        if (v) sifreGoster(`Şifre sıfırlandı: ${v.ad}`, v.ad, v.sifre); else pencereKapat();
    },
});
EYLEM["kullanici-sil"] = (el) => onayPenceresi({
    baslik: `Sil: ${esc(el.dataset.ad)}`, metin: `${esc(el.dataset.ad)} kullanıcısı silinsin mi? Oturumu hemen kapanır.`, dugme: "Sil", tehlike: true, tur: "kirmizi",
    async evet() {
        const v = await dene(() => api("POST", `/api/kullanicilar/${encodeURIComponent(el.dataset.ad)}/sil`, {}), "Silme");
        pencereKapat();
        if (v) { bildir(`${el.dataset.ad} silindi.`); ciz({ sessiz: true }); }
    },
});

/* ---------- Denetim kaydı ---------- */
const OLAY_ADI = [
    [/^GIRIS$/, "Giriş"], [/^HATALI GIRIS$/, "Hatalı giriş"], [/^CIKIS$/, "Çıkış"], [/^POST odoolar$/, "Odoo kurma"],
    [/\/deploy$/, "Deploy"], [/\/geri-al$/, "Geri alma"], [/\/production-al$/, "Production'a alma"], [/\/yedek$/, "Yedek alma"],
    [/\/geri-yukle$/, "Geri yükleme"], [/\/staging\/olustur$/, "Staging oluşturma"], [/\/staging\/yenile$/, "Staging yenileme"],
    [/\/staging\/sil$/, "Staging silme"], [/\/yedek-staging$/, "Yedeği staging'de açma"], [/\/zip$/, "Zip yükleme"],
    [/\/depo$/, "Depo bağlama"], [/\/depo\/kaldir$/, "Depo bağlantısını kaldırma"], [/\/(durdur|baslat)$/, "Durdurma / başlatma"],
    [/\/sil$/, "Odoo silme"], [/^POST bagla$/, "Mevcut Odoo'yu bağlama"], [/^INDIRDI/, "Yedek indirme"], [/^WEBHOOK/, "GitHub webhook"],
];
const olayAdi = (o) => { const e = OLAY_ADI.find(([d]) => d.test(o)); return e ? e[1] : o; };
PLATFORM.denetim = async () => {
    const v = await api("GET", "/api/denetim");
    return [`
    <div class="baslik-satiri"><div><p class="ust-etiket">Panel</p><h1>Denetim kaydı</h1>
        <p class="soluk">Paneldeki her işlem kişi, zaman ve IP ile tutulur. Son ${v.kayitlar.length} kayıt.</p></div></div>
    <div class="kart tablo-kap"><table class="tablo kartli">
        <thead><tr><th>Zaman</th><th>Kim</th><th>İşlem</th><th>Odoo</th><th>Sonuç</th><th>IP</th></tr></thead>
        <tbody>${v.kayitlar.map((k) => `<tr>
            <td data-etiket="Zaman"><span class="kirilmaz">${esc(tarihSaat(k.zaman))}</span></td>
            <td data-etiket="Kim"><code>${esc(k.kullanici)}</code></td>
            <td data-etiket="İşlem" class="ana-yazi">${esc(olayAdi(k.olay))}<small><code>${esc(k.olay)}</code></small></td>
            <td data-etiket="Odoo">${esc(k.odoo || "-")}</td>
            <td data-etiket="Sonuç">${k.kod == null ? "-" : `<span class="rozet ${k.kod < 300 ? "basarili" : "hata"}">${esc(k.kod)}</span>`}</td>
            <td data-etiket="IP"><code>${esc(k.ip || "-")}</code></td></tr>`).join("") || `<tr><td colspan="6" class="soluk">Kayıt yok.</td></tr>`}</tbody>
    </table></div>`];
};

/* ---- ekran_odoo.js ---- */
/* Odoo başına ekranlar: başlık, ortam hattı, Deploylar, İzleme, Loglar, Yedekler, Modüller, Ayarlar */
const ODOO_SEKME = {};
const DEPLOY_DURUM = {
    tamam: ["Başarılı", "basarili", "tik"], uyari: ["Uyarı", "uyari", "uyari"], hata: ["Hata", "hata", "hata"],
    durdu: ["Durdu", "hata", "uyari"], calisiyor: ["Çalışıyor", "islem", "don"], atlandi: ["Atlandı", "", "bilgi"],
};
const TETIK = { webhook: ["webhook", "webhook"], elle: ["elle", "el"], geri: ["geri alma", "geri"], zip: ["zip", "yukle"] };
const YEDEK_ETIKET = {
    GECE: "Gece", ELLE: "Elle", "DEPLOY-ONCESI": "Deploy öncesi", "YENILEME-ONCESI": "Yenileme öncesi",
    "GERI-YUKLEME-ONCESI": "Geri yükleme öncesi", "GERI-ALMA-ONCESI": "Geri alma öncesi", "SILINMEDEN-ONCE": "Silinmeden önce",
};
const ortamAdi = (ad) => (ad === "production" ? "Production" : "Staging");
const panelOrtami = (ort) => ort && ort.yonetim === "panel";

async function odooEkrani(R) {
    const od = await ajan.al(`odoolar/${encodeURIComponent(R.odoo)}`);
    const ortamAd = R.ortam === "staging" && od.ortamlar.staging ? "staging" : "production";
    const ort = od.ortamlar[ortamAd];
    if (!ort) throw new ApiHata(404, "Bu Odoo'nun production ortamı yok.");
    const ondeIstek = od.depo && od.ortamlar.staging && od.ortamlar.staging.commit
        ? ajan.al(`odoolar/${od.id}/onde`).then((v) => v.commitler).catch(() => []) : Promise.resolve([]);
    const [[icerik, sonra], onde] = await Promise.all([ODOO_SEKME[R.sekme](od, ortamAd, ort), ondeIstek]);
    return [odooKabuk(od, ortamAd, R.sekme, icerik, onde), sonra];
}

function odooKabuk(od, ortamAd, sekme, icerik, onde) {
    const ort = od.ortamlar[ortamAd];
    const sekmeler = ODOO_SEKMELER.filter(sekmeAcik);
    return `<div class="ort-${ortamAd}">
        ${tekOdoo() ? `<p class="ust-etiket">Odoo kurulumu</p>` : `<div class="kirinti"><a href="#/odoolar">Odoo'lar</a> / ${esc(od.firma)}</div>`}
        <div class="odoo-baslik">
            <div><h1>${esc(od.firma)}</h1>
                <div class="odoo-alt"><span class="rozet surum">${esc(SERI_ADI(od.seri))}</span>${ort.mesgul ? `<span class="rozet islem">${ikon("don", 11, 'class="donen"')}İşlem sürüyor</span>` : rozetDurum(ort.durum)}
                    ${od.tur === "bagli" ? `<span class="etiket">${ikon("ara", 11)}bağlandı: ${esc(KAYNAK_ADI[od.kaynak] || od.kaynak)}</span>` : ""}
                    <code>${esc(alanAdi(ort.adres))}</code><span>db: <code>${esc(ort.db_adi)}</code></span></div></div>
            <div class="dugmeler" style="margin:0">
                ${od.depo ? `<a class="btn" href="https://github.com/${esc(od.depo.ad)}" target="_blank" rel="noopener noreferrer" aria-label="GitHub'da aç" title="GitHub'da aç">${ikon("github", 16)}</a>` : ""}
                ${od.tur === "panel" && ortamAd === "production" && yetkili("kur") ? `<button class="btn" data-eylem="giris-bilgisi" data-odoo="${esc(od.id)}">Giriş bilgisi</button>` : ""}
                ${ort.adres ? `<a class="btn birincil" href="${esc(ort.adres)}" target="_blank" rel="noopener noreferrer">Odoo'yu aç ${ikon("dis", 14)}</a>` : ""}
            </div>
        </div>
        ${hatCiz(od, ortamAd, onde)}
        ${ortamNotu(od, ortamAd, ort)}
        <nav class="sekmeler" aria-label="Bu Odoo">
            ${sekmeler.map((s) => `<a class="sekme ${sekme === s.ad ? "etkin" : ""}" href="${odooRota(od.id, ortamAd, s.ad)}">${ikon(s.ikon, 15)}${esc(s.baslik)}</a>`).join("")}
        </nav>
        <div id="sekme-icerik">${icerik}</div>
    </div>`;
}

/* ---------- ortam hattı ---------- */
function hatKart(od, ortamAd, secili) {
    const ort = od.ortamlar[ortamAd];
    if (!ort) {
        return `<div class="hat-ortam hat-yok ort-staging">
            <div class="hat-ad">Staging yok</div>
            <div class="hat-alt">Production verisinin nötrleştirilmiş kopyasında deneme alanı.</div>
            ${yetkili("stagingYenile") ? `<div style="margin-top:.25rem"><button class="btn kucuk" data-eylem="staging-olustur" data-odoo="${esc(od.id)}">${ikon("artik", 13)}Staging oluştur</button></div>` : ""}
        </div>`;
    }
    const dal = od.depo && od.depo.dallar ? od.depo.dallar[ortamAd] : null;
    const kod = dal ? `${dal} @ ${kisa(ort.commit)}` : od.tur === "bagli" && ortamAd === "production" ? `bağlı kurulum (${KAYNAK_ADI[od.kaynak] || od.kaynak})` : ort.commit ? `@ ${kisa(ort.commit)}` : "Depo bağlı değil";
    const vk = ort.veri_kaynak;
    const alt = ortamAd === "staging"
        ? (vk ? `Veri ${goreli(vk.tarih)} ${vk.tur === "yedek" ? "yedekten açıldı" : "production'dan kopyalandı"}` : "Veri kopyalanmadı")
        : (ort.son_deploy_tarih ? `Son deploy ${goreli(ort.son_deploy_tarih)}` : od.tur === "bagli" ? "Panel deploy etmez" : "Henüz deploy yok");
    return `<a class="hat-ortam ort-${ortamAd} ${secili ? "secili" : ""}" href="${odooRota(od.id, ortamAd, R.sekme || "deploylar")}" ${secili ? 'aria-current="true"' : ""}>
        <span class="hat-ad"><i class="nokta ${ort.durum === "running" ? "calisiyor" : "durdu"}"></i>${ortamAdi(ortamAd)}
            ${ort.mesgul ? `<span class="rozet islem">${ikon("don", 11, 'class="donen"')}işlem</span>` : ""}</span>
        <span class="hat-kod">${esc(kod)}</span>
        <span class="hat-alt">${esc(alt)}</span>
    </a>`;
}
function hatGecis(od, onde) {
    const s = od.ortamlar.staging;
    const ok = `<span class="hat-ok"><i></i>${ikon("ok", 16)}</span>`;
    if (!s) return `<div class="hat-gecis">${ok}</div>`;
    if (!od.depo) return `<div class="hat-gecis">${ok}<span>Depo bağlı değil</span></div>`;
    if (onde.length) {
        return `<div class="hat-gecis"><span><strong>${onde.length} commit</strong> önde</span>${ok}
            ${yetkili("deploy") ? `<button class="btn birincil kucuk" data-eylem="production-al" data-odoo="${esc(od.id)}" data-sayi="${onde.length}">Production'a al</button>` : ""}</div>`;
    }
    return `<div class="hat-gecis"><span>${s.commit ? "Önde commit yok" : "Staging'de deploy yok"}</span>${ok}</div>`;
}
function hatCiz(od, secili, onde) {
    return `<section class="hat" aria-label="Ortam hattı">
        ${hatKart(od, "staging", secili === "staging")}
        ${hatGecis(od, onde)}
        ${hatKart(od, "production", secili === "production")}
    </section>`;
}
function ortamNotu(od, ortamAd, ort) {
    let html = "";
    if (ort.durum !== "running" && !ort.mesgul) html += uyariKutu("gri", "Bu ortam çalışmıyor; kullanıcılar giriş yapamıyor. İzleme sekmesinden başlatılabilir.", "dur");
    if (ortamAd === "staging") {
        const n = ort.notr || {};
        html += uyariKutu("sari", `<strong>Staging:</strong> production verisinin nötrleştirilmiş kopyası. Posta sunucuları, zamanlanmış işler, e-Belge entegratörü ve webhook'lar kapalı. Burada yapılan hiçbir şey production'a geçmez.${n.tarih ? ` Son denetim ${esc(goreli(n.tarih))}: çalışan zamanlanmış iş ${esc(n.cron ?? "-")}, etkin posta sunucusu ${esc(n.posta ?? "-")}, etkin entegratör ${esc(n.entegrator ?? "-")}.` : ""}`);
    }
    return html;
}
EYLEM["staging-olustur"] = (el) => onayPenceresi({
    baslik: "Staging oluştur",
    metin: `Production'ın veritabanı ve dosya deposu kopyalanır, kopya nötrleştirilir (posta, zamanlanmış işler, e-Belge kapanır) ve <code>${esc(el.dataset.odoo)}-staging</code> adresinde açılır. Production'a dokunulmaz. Sunucuda yaklaşık 1,2 GB bellek ister.`,
    dugme: "Oluştur",
    evet: () => isBaslat(() => ajan.gonder(`odoolar/${el.dataset.odoo}/staging/olustur`), "Staging oluşturuluyor"),
});
EYLEM["production-al"] = (el) => onayPenceresi({
    baslik: "Production'a al",
    metin: `Staging'deki ${esc(el.dataset.sayi)} commit production'a geçer. GitHub App bağlıysa staging production dalına birleştirilir; sonra production deploy'u başlar (önce yedek alınır, değişen modüller güncellenir).`,
    dugme: "Production'a al",
    evet: () => isBaslat(() => ajan.gonder(`odoolar/${el.dataset.odoo}/production/production-al`), "Production'a alınıyor"),
});

/* ---------- Deploylar ---------- */
ODOO_SEKME.deploylar = async (od, ortamAd, ort) => {
    if (od.tur === "bagli" && ortamAd === "production") {
        return [bosDurum("Bağlanan kurulumda deploy yok",
            "Bu Odoo panelin dışında kurulmuş; kodu kendi yöntemiyle güncellenir. Panel izler, yedek alır ve staging açar.",
            `<a class="btn" href="${odooRota(od.id, ortamAd, "izleme")}">İzleme</a><a class="btn" href="${odooRota(od.id, ortamAd, "yedekler")}">Yedekler</a>`, "ara")];
    }
    if (!od.depo) {
        return [bosDurum("Bu Odoo henüz bir kod deposuna bağlı değil",
            od.tur === "panel" ? "Depo bağlanınca her push bir deploy olur, geçmiş burada görünür ve eski sürüme dönülebilir." : "Staging'in kodu production'dan kopyalandı.",
            od.tur === "panel" && yetkili("github") ? `<a class="btn birincil" href="${odooRota(od.id, "production", "ayarlar")}">${ikon("github", 15)}Depoyu bağla</a>` : "", "github")];
    }
    const [dv, iv] = await Promise.all([ajan.al(`odoolar/${od.id}/${ortamAd}/deploylar`), ajan.al(`isler?odoo=${encodeURIComponent(od.id)}`)]);
    const deploylar = dv.deploylar;
    const isler = iv.isler.filter((k) => !k.ortam || k.ortam === ortamAd).slice(0, 8);
    return [`<div class="iki-sutun">
        <div class="yigin">${surumKart(od, ortamAd, ort, deploylar)}${gecmisKart(od, ortamAd, ort, deploylar)}</div>
        <aside class="yan-sutun yigin">
            ${ort.bekleyen ? bekleyenKart(od, ortamAd, ort) : ""}
            ${depoKart(od, ortamAd)}
            ${islerKart(isler)}
        </aside>
    </div>`];
};
const yayindaki = (ort, deploylar) => deploylar.find((d) => d.commit === ort.commit && (d.durum === "tamam" || d.durum === "uyari"));
function surumKart(od, ortamAd, ort, deploylar) {
    const y = yayindaki(ort, deploylar);
    const yetki = yetkili("deploy");
    const dal = od.depo.dallar[ortamAd];
    const dugmeler = `
        ${yetki ? `<button class="btn ${y ? "" : "birincil"}" data-eylem="deploy" data-odoo="${esc(od.id)}" data-ortam="${ortamAd}">${ikon("yenile", 14)}${y ? "Yeniden deploy et" : "İlk deploy'u başlat"}</button>` : ""}
        ${yetki ? `<button class="btn" data-eylem="uyumluluk" data-odoo="${esc(od.id)}" data-ortam="${ortamAd}">${ikon("tik", 14)}Uyumluluk denetimi</button>` : ""}
        ${ortamAd === "staging" && yetkili("stagingYenile") ? `<button class="btn" data-eylem="staging-yenile" data-odoo="${esc(od.id)}">${ikon("yedek", 14)}Production'dan yenile</button>` : ""}
        ${y ? `<button class="btn" data-eylem="deploy-log" data-odoo="${esc(od.id)}" data-ortam="${ortamAd}" data-no="${y.no}">${ikon("log", 14)}Deploy logu</button>` : ""}`;
    if (!y) {
        return `<div class="kart surum-kart"><div class="surum-bant">${ortamAdi(ortamAd)}: yayındaki sürüm</div>
            <div class="surum-ic"><div class="surum-baslik">${ort.commit ? `Kod ${esc(kisa(ort.commit))} (production'dan kopyalandı)` : "Henüz deploy yapılmadı"}</div>
            <p class="soluk kucuk-yazi">${esc(dal)} dalının son hali çekilir, uyumluluk denetlenir${ortamAd === "production" ? ", yedek alınır" : ""} ve kurulu modüller güncellenir.</p>
            <div class="dugmeler">${dugmeler}</div></div></div>`;
    }
    return `<div class="kart surum-kart">
        <div class="surum-bant"><span>${ortamAdi(ortamAd)}: yayındaki sürüm</span><span class="sag-taraf kod">${esc(dal)} @ ${esc(kisa(y.commit))}</span></div>
        <div class="surum-ic">
            <div class="surum-baslik">${esc(y.baslik || "")}</div>
            <div class="surum-meta"><span>${esc(y.yazar || "-")}</span><span title="${esc(tarihSaat(y.bitis))}">${esc(goreli(y.bitis))}</span>
                <span class="etiket">${ikon((TETIK[y.tetik] || ["", "el"])[1], 11)}${esc((TETIK[y.tetik] || [y.tetik])[0])}</span>${y.sure != null ? `<span>${esc(y.sure)} sn</span>` : ""}</div>
            <div class="kanitlar">
                <span class="kanit">${ikon("modul", 14)}Güncellenen: <strong>${y.moduller && y.moduller.length ? esc(y.moduller.join(", ")) : "yok"}</strong></span>
                ${y.yedek ? `<span class="kanit">${ikon("yedek", 14)}Deploy öncesi yedek alındı</span>` : ""}
                <span class="kanit">${ikon("izleme", 14)}Sağlık denetimi geçti</span>
                ${y.dal_disi ? `<span class="kanit ic-sari">${ikon("uyari", 14)}Commit dalın son hali değil</span>` : ""}
            </div>
            <div class="dugmeler">${dugmeler}</div>
        </div>
    </div>`;
}
function deploySatir(d, od, ortamAd, ort, mesgul) {
    const [yazi, sinif, simge] = DEPLOY_DURUM[d.durum] || [d.durum, "", "bilgi"];
    const tetik = TETIK[d.tetik] || [d.tetik, "el"];
    const yayinda = d.commit === ort.commit && (d.durum === "tamam" || d.durum === "uyari");
    const geriAlinir = yetkili("deploy") && (d.durum === "tamam" || d.durum === "uyari") && d.onceki && d.onceki.commit && !mesgul;
    const notlar = [d.engel, d.hata && d.hata !== d.engel ? d.hata : null, d.not].filter(Boolean);
    return `<li class="satir ${yayinda ? "yayinda-satir" : ""}">
        <span class="satir-ikon ${sinif === "basarili" ? "basarili" : d.durum === "calisiyor" ? "calisiyor" : sinif}">${ikon(simge, 13, d.durum === "calisiyor" ? 'class="donen"' : "")}</span>
        <div>
            <div class="satir-baslik">${esc(d.baslik || (d.geri_alinan ? `Deploy #${d.geri_alinan} geri alındı` : "Deploy"))}</div>
            <div class="satir-meta"><span>#${esc(d.no)}</span><span>${esc(d.yazar || d.kullanici || "-")}</span><span title="${esc(tarihSaat(d.baslangic))}">${esc(saat(d.baslangic))}, ${esc(goreli(d.baslangic))}</span>
                <span class="etiket">${ikon(tetik[1], 11)}${esc(tetik[0])}</span>${d.commit ? `<span class="hash">${esc(kisa(d.commit))}</span>` : ""}
                ${d.moduller && d.moduller.length ? `<span class="modul-ad">${esc(d.moduller.join(", "))}</span>` : ""}
                ${d.sure != null ? `<span>${esc(d.sure)} sn</span>` : ""}${d.kullanici && d.yazar && d.kullanici !== d.yazar ? `<span>başlatan: ${esc(d.kullanici)}</span>` : ""}</div>
            ${notlar.map((n) => `<div class="satir-not">${esc(n)}</div>`).join("")}
            ${(d.uyarilar || []).slice(0, 3).map((u) => `<div class="satir-not" style="color:var(--sari)">${esc(u)}</div>`).join("")}
        </div>
        <div class="satir-sag">
            ${yayinda ? `<span class="rozet yayinda">Yayında</span>` : ""}
            <span class="rozet ${sinif}">${esc(yazi)}</span>
            <button class="btn bag kucuk" data-eylem="deploy-log" data-odoo="${esc(od.id)}" data-ortam="${ortamAd}" data-no="${d.no}">Log</button>
            ${geriAlinir ? `<button class="btn kucuk" data-eylem="geri-al" data-odoo="${esc(od.id)}" data-ortam="${ortamAd}" data-no="${d.no}" data-onceki="${esc(kisa(d.onceki.commit))}" data-yedek="${d.yedek ? "1" : ""}" title="Bu deploy'dan önceki sürüme döner">${ikon("geri", 13)}Geri al</button>` : ""}
        </div>
    </li>`;
}
function gecmisKart(od, ortamAd, ort, deploylar) {
    if (!deploylar.length) return "";
    const mesgul = ort.mesgul;
    const gruplar = [];
    deploylar.forEach((d) => {
        const g = gunEtiketi(ms(d.baslangic));
        const son = gruplar[gruplar.length - 1];
        if (son && son.g === g) son.liste.push(d); else gruplar.push({ g, liste: [d] });
    });
    return `<section>
        <div class="gecmis-baslik"><h2>Deploy geçmişi</h2><span class="soluk kucuk-yazi">son ${deploylar.length} kayıt</span></div>
        <div class="kart"><ul>${gruplar.map((g) => `<li><div class="gun-baslik">${esc(g.g)}</div><ul>${g.liste.map((d) => deploySatir(d, od, ortamAd, ort, mesgul)).join("")}</ul></li>`).join("")}</ul></div>
    </section>`;
}
function bekleyenKart(od, ortamAd, ort) {
    const b = ort.bekleyen;
    return `<div class="kart kart-ic" style="border-color:var(--ort)">
        <div class="kart-baslik"><h3>Depoda yeni commit</h3></div>
        <ul class="commit-liste"><li><span class="hash">${esc(kisa(b.commit))}</span><span class="baslik">${esc(b.baslik || "")}</span></li></ul>
        <p class="soluk kucuk-yazi">${esc(b.yazar || "")} · ${esc(goreli(b.tarih))}. Bu ortam elle güncellenir.</p>
        ${yetkili("deploy") ? `<div class="dugmeler"><button class="btn birincil" data-eylem="deploy" data-odoo="${esc(od.id)}" data-ortam="${ortamAd}" data-commit="${esc(b.commit)}">Şimdi güncelle</button></div>` : ""}
    </div>`;
}
const BAGLANTI_ADI = { app: "GitHub App", anahtar: "Deploy key (salt okunur)", acik: "Herkese açık depo" };
function depoKart(od, ortamAd) {
    const d = od.depo;
    const kip = d.kip[ortamAd];
    return `<div class="kart kart-ic">
        <div class="kart-baslik"><h3 style="display:flex;gap:.4rem;align-items:center">${ikon("github", 16)}Kod deposu</h3>${yetkili("github") && od.tur === "panel" ? `<a class="btn kucuk" href="${odooRota(od.id, ortamAd, "ayarlar")}">Ayarlar</a>` : ""}</div>
        <div class="bilgi-satir"><span>Depo</span><a href="https://github.com/${esc(d.ad)}" target="_blank" rel="noopener noreferrer"><code>${esc(d.ad)}</code></a></div>
        <div class="bilgi-satir"><span>Dal</span><code>${esc(d.dallar[ortamAd] || "-")}</code></div>
        <div class="bilgi-satir"><span>Bağlantı</span><span class="deger">${esc(BAGLANTI_ADI[d.baglanti] || d.baglanti)}</span></div>
        <div class="bilgi-satir"><span>Güncelleme</span><span class="deger">${kip === "webhook" ? `${ikon("webhook", 13)} Otomatik: push gelince deploy` : `${ikon("el", 13)} Elle: panelden başlatılır`}</span></div>
    </div>`;
}
function islerKart(isler) {
    if (!isler.length) return "";
    return `<div class="kart kart-ic">
        <div class="kart-baslik"><h3>Son işler</h3></div>
        <ul class="denetim-liste">${isler.map((k) => {
        const [yazi, sinif] = IS_DURUM[k.durum] || [k.durum, ""];
        return `<li style="align-items:flex-start"><span class="rozet ${sinif}" style="flex:none">${k.durum === "calisiyor" ? ikon("don", 11, 'class="donen"') : ""}${esc(yazi)}</span>
            <span style="min-width:0;display:grid"><button class="btn bag kucuk" style="text-align:left;justify-content:flex-start;padding-left:0" data-eylem="is-ac" data-is="${esc(k.id)}"><span class="tasma-kes">${esc(k.aciklama || k.tur)}</span></button>
            <span class="soluk kucuk-yazi">${esc(goreli(k.baslangic || k.olusturma))}${k.kullanici ? ` · ${esc(k.kullanici)}` : ""}</span></span></li>`;
    }).join("")}</ul>
    </div>`;
}
EYLEM.deploy = (el) => {
    const commit = el.dataset.commit;
    const ortam = el.dataset.ortam;
    onayPenceresi({
        baslik: `${ortamAdi(ortam)} deploy`,
        metin: `${commit ? `<span class="hash">${esc(kisa(commit))}</span> commit'i` : "Dalın son hali"} ${ortamAdi(ortam).toLowerCase()} ortamına deploy edilecek.
            ${ortam === "production" ? "Önce yedek alınır. Odoo güncelleme süresince kısa bir süre kapalı kalır." : ""} Uyumluluk denetimi geçmezse hiçbir şeye dokunulmaz.`,
        dugme: "Deploy et",
        evet: () => isBaslat(() => ajan.gonder(`odoolar/${el.dataset.odoo}/${ortam}/deploy`, commit ? { commit } : {}), `${ortamAdi(ortam)} deploy`),
    });
};
EYLEM["staging-yenile"] = (el) => onayPenceresi({
    baslik: "Staging'i production'dan yenile",
    metin: "Staging'in şimdiki verisi yedeklenir, sonra production'ın verisiyle değiştirilir ve nötrleştirilir. Staging'de girilen veri kaybolur; kodu değişmez.",
    dugme: "Yenile",
    evet: () => isBaslat(() => ajan.gonder(`odoolar/${el.dataset.odoo}/staging/yenile`), "Staging yenileniyor"),
});
EYLEM["deploy-log"] = (el) => dene(async () => {
    const d = await ajan.al(`odoolar/${el.dataset.odoo}/${el.dataset.ortam}/deploylar/${el.dataset.no}`);
    const [yazi, sinif] = DEPLOY_DURUM[d.durum] || [d.durum, ""];
    pencereAc(`Deploy #${esc(d.no)}: ${esc(ortamAdi(d.ortam))}`, `
        <p class="kucuk-yazi" style="display:flex;gap:.5rem;flex-wrap:wrap;align-items:center"><span class="rozet ${sinif}">${esc(yazi)}</span>
            ${d.commit ? `<span class="hash">${esc(kisa(d.commit))}</span>` : ""}<span>${esc(d.baslik || "")}</span></p>
        <div class="bilgi-satir"><span>Başlangıç</span><span class="deger">${esc(tarihSaat(d.baslangic))}${d.sure != null ? ` (${esc(d.sure)} sn)` : ""}</span></div>
        <div class="bilgi-satir"><span>Başlatan</span><span class="deger">${esc(d.kullanici || "-")} · ${esc((TETIK[d.tetik] || [d.tetik])[0])}</span></div>
        <div class="bilgi-satir"><span>Güncellenen</span><span class="deger">${esc((d.moduller || []).join(", ") || "yok")}</span></div>
        ${d.yeni_moduller && d.yeni_moduller.length ? `<div class="bilgi-satir"><span>Kurulmayan yeni modüller</span><span class="deger">${esc(d.yeni_moduller.join(", "))}</span></div>` : ""}
        ${d.paketler && d.paketler.length ? `<div class="bilgi-satir"><span>Python paketleri</span><span class="deger">${esc(d.paketler.join(", "))}</span></div>` : ""}
        ${d.yedek ? `<div class="bilgi-satir"><span>Deploy öncesi yedek</span><code class="kucuk-yazi">${esc(d.yedek)}</code></div>` : ""}
        ${[d.engel, d.hata, d.not].filter(Boolean).map((n) => uyariKutu("kirmizi", esc(n))).join("")}
        ${(d.engeller || []).length ? `<ul class="denetim-liste uste-az">${d.engeller.map((e) => `<li>${ikon("hata", 14, 'class="ic-kirmizi"')}<span><code>${esc(e.modul)}</code>: ${esc(e.neden)}</span></li>`).join("")}</ul>` : ""}
        ${(d.uyarilar || []).length ? `<ul class="denetim-liste uste-az">${d.uyarilar.map((u) => `<li>${ikon("uyari", 14, 'class="ic-sari"')}<span>${esc(u)}</span></li>`).join("")}</ul>` : ""}
        <pre class="kayit uste-az">${(d.cikti || "Kayıt yok.").split("\n").map(logSatiriHtml).join("")}</pre>
        <div class="dugmeler"><button class="btn birincil" data-eylem="pencere-kapat">Kapat</button></div>`, { genis: true });
    const k = $("#pencere-govde .kayit");
    k.scrollTop = k.scrollHeight;
}, "Deploy kaydı");
EYLEM["geri-al"] = (el) => {
    const { odoo, ortam, no, onceki, yedek } = el.dataset;
    const g = pencereAc(`Deploy #${esc(no)} geri alınıyor`, `
        <p>Bu deploy'dan önceki sürüme (<span class="hash">${esc(onceki)}</span>) dönülür. Nasıl?</p>
        <label class="secenek"><input type="radio" name="kip" value="kod" checked><span><strong>Yalnız kod</strong><small>Önceki commit yeniden deploy edilir; değişen modüller eski kodla güncellenir. Veri yerinde kalır.${ortam === "production" ? " Önce yedek alınır." : ""}</small></span></label>
        <label class="secenek ${yedek ? "" : "gizli"}"><input type="radio" name="kip" value="kod-veri" ${yedek ? "" : "disabled"}><span><strong>Kod + veri</strong><small>Deploy öncesi yedek geri yüklenir; deploy'dan sonra girilen veri kaybolur. Şimdiki hal ayrıca yedeklenir.</small></span></label>
        <div class="dugmeler"><button class="btn birincil" id="geri-devam">Devam</button><button class="btn" data-eylem="pencere-kapat">Vazgeç</button></div>`);
    $("#geri-devam", g).addEventListener("click", () => {
        const kip = $("input[name=kip]:checked", g).value;
        const gonder = () => isBaslat(() => ajan.gonder(`odoolar/${odoo}/${ortam}/geri-al`, { no: Number(no), kip }), `Deploy #${no} geri alınıyor`);
        if (kip === "kod") { gonder(); return; }
        const od = bulOdoo(odoo);
        const adres = od && od.ortamlar[ortam] ? alanAdi(od.ortamlar[ortam].adres) : "";
        adresOnayi({ baslik: "Kod ve veri geri alınıyor", metin: "Deploy'dan sonra girilen bütün veri kaybolur. Şimdiki halin yedeği alınır.", beklenen: adres, dugme: "Geri al", evet: gonder });
    });
};
EYLEM.uyumluluk = (el) => isBaslat(() => ajan.gonder(`odoolar/${el.dataset.odoo}/${el.dataset.ortam}/uyumluluk`), "Uyumluluk denetimi", {
    kapanis(k) {
        const r = k.sonuc || {};
        if (k.durum !== "tamam" || !r.moduller) return "";
        const satirlar = Object.entries(r.moduller).map(([ad, m]) => `<tr><td><code>${esc(ad)}</code></td><td><code>${esc(m.surum)}</code></td>
            <td><span class="rozet ${m.durum === "uygun" ? "basarili" : m.durum === "engel" ? "hata" : "uyari"}">${esc({ uygun: "Uygun", engel: "Engel", uyari: "Uyarı" }[m.durum])}</span></td>
            <td class="kucuk-yazi">${esc((m.notlar || []).join("; ") || (m.kurulu ? "kurulu" : "kurulu değil"))}</td></tr>`).join("");
        $("#is-govde").insertAdjacentHTML("beforeend", `<h4 class="uste">${r.gecti ? "Deploy'u durduracak sorun yok." : "Bu commit deploy edilirse deploy durur."} <span class="soluk kucuk-yazi">commit ${esc(kisa(r.commit))}</span></h4>
            <div class="tablo-kap"><table class="tablo"><thead><tr><th>Modül</th><th>Sürüm</th><th>Sonuç</th><th>Not</th></tr></thead><tbody>${satirlar || `<tr><td colspan="4" class="soluk">Depoda modül yok.</td></tr>`}</tbody></table></div>`);
        return "";
    },
});

/* ---------- İzleme ---------- */
ODOO_SEKME.izleme = async (od, ortamAd) => {
    const d = await ajan.al(`odoolar/${od.id}/${ortamAd}/durum`);
    const k = d.kaynak || {};
    const sinir = panelOrtami(d) ? 2048 : null;
    const oran = sinir && k.bellek_mb ? (k.bellek_mb / sinir) * 100 : null;
    const islemIzni = yetkili("durdur") && (panelOrtami(d) || od.islemler_acik);
    const calisiyor = d.durum === "running";
    return [`
    <div class="filtre-satir"><span class="soluk kucuk-yazi">Anlık değerler, konteynerin kendisinden.</span><span class="bosluk"></span>
        <button class="btn kucuk" data-eylem="yeniden-ciz">${ikon("yenile", 13)}Yenile</button></div>
    <div class="gosterge-izgara">
        <div class="kart gosterge"><div class="gosterge-ust"><span class="gosterge-ad">Durum</span></div><div class="gosterge-deger" style="font-size:1rem">${rozetDurum(d.durum)}</div>
            <div class="gosterge-alt"><code>${esc(d.konteyner)}</code></div></div>
        <div class="kart gosterge"><div class="gosterge-ust"><span class="gosterge-ad">Bellek</span>${oran >= 85 ? `<span class="rozet uyari">Yüksek</span>` : ""}</div>
            <div class="gosterge-deger">${k.bellek_mb != null ? esc(boyutMb(k.bellek_mb)) : "-"}</div>${oran != null ? olcer(oran, oran >= 85 ? "sari" : "") : ""}
            <div class="gosterge-alt">${sinir ? `Sınır ${esc(boyutMb(sinir))}` : "Sınırı kurulumun kendi ayarında"}</div></div>
        <div class="kart gosterge"><div class="gosterge-ust"><span class="gosterge-ad">İşlemci</span></div>
            <div class="gosterge-deger">${k.cpu != null ? `%${esc(sayi(k.cpu))}` : "-"}</div><div class="gosterge-alt">Ölçüm anındaki kullanım</div></div>
        <div class="kart gosterge"><div class="gosterge-ust"><span class="gosterge-ad">Kod</span></div>
            <div class="gosterge-deger" style="font-size:1rem">${d.commit ? `<span class="hash">${esc(kisa(d.commit))}</span>` : "-"}</div>
            <div class="gosterge-alt tasma-kes" title="${esc(d.imaj)}">${esc(d.imaj || "")}</div></div>
    </div>
    ${islemIzni ? `<div class="kart kart-ic" style="margin-bottom:1rem"><div class="anahtar-satir"><div>${calisiyor ? "Ortamı durdur" : "Ortamı başlat"}<small>${calisiyor ? "Kullanıcılar giriş yapamaz; veri yerinde kalır." : "Konteyner açılır ve giriş sayfası denetlenir."}</small></div>
        <button class="btn ${calisiyor ? "tehlike-cizgi" : "birincil"}" data-eylem="${calisiyor ? "durdur" : "baslat"}" data-odoo="${esc(od.id)}" data-ortam="${ortamAd}">${ikon(calisiyor ? "dur" : "el", 14)}${calisiyor ? "Durdur" : "Başlat"}</button></div></div>`
        : od.tur === "bagli" && !od.islemler_acik ? uyariKutu("gri", "Bağlanan kurulumda durdurma ve başlatma kapalı. Ayarlar sekmesinden izin verilebilir.") : ""}
    ${ortamAd === "staging" && d.notr ? `<div class="kart kart-ic"><h3>Nötrleştirme denetimi</h3>
        <div class="bilgi-satir"><span>Son denetim</span><span class="deger">${esc(tarihSaat(d.notr.tarih))}</span></div>
        <div class="bilgi-satir"><span>Çalışan zamanlanmış iş</span><span class="deger">${esc(d.notr.cron)}</span></div>
        <div class="bilgi-satir"><span>Etkin posta sunucusu</span><span class="deger">${esc(d.notr.posta)}</span></div>
        <div class="bilgi-satir"><span>Etkin e-Belge entegratörü</span><span class="deger">${esc(d.notr.entegrator ?? "tablo yok")}</span></div></div>` : ""}`];
};
for (const islem of ["durdur", "baslat"]) {
    EYLEM[islem] = (el) => {
        const calistir = () => isBaslat(() => ajan.gonder(`odoolar/${el.dataset.odoo}/${el.dataset.ortam}/${islem}`), `${ortamAdi(el.dataset.ortam)} ${islem === "durdur" ? "durduruluyor" : "başlatılıyor"}`);
        if (islem === "baslat") { calistir(); return; }
        onayPenceresi({ baslik: "Ortamı durdur", metin: "Kullanıcılar giriş yapamaz. Veri yerinde kalır; sonra başlatılabilir.", dugme: "Durdur", tehlike: true, tur: "kirmizi", evet: calistir });
    };
}

/* ---------- Loglar ---------- */
const LOG = { satir: "300", seviye: "hepsi", ara: "", satirlar: [] };
ODOO_SEKME.loglar = async (od, ortamAd) => {
    const v = await ajan.al(`odoolar/${od.id}/${ortamAd}/loglar?satir=${LOG.satir}`);
    LOG.satirlar = v.satirlar;
    return [`<div class="filtre-satir">
        <label class="alan" style="margin:0;flex:0 1 140px">Seviye<select data-degis="log-seviye">
            ${[["hepsi", "Tümü"], ["uyari", "Uyarı ve hata"], ["hata", "Yalnız hata"]].map(([k, a]) => `<option value="${k}" ${LOG.seviye === k ? "selected" : ""}>${a}</option>`).join("")}</select></label>
        <label class="alan" style="margin:0;flex:0 1 110px">Satır<select data-degis="log-satir">${["300", "1000", "3000"].map((n) => `<option ${LOG.satir === n ? "selected" : ""}>${n}</option>`).join("")}</select></label>
        <label class="alan" style="margin:0;flex:1 1 180px">Ara<input id="log-ara" value="${esc(LOG.ara)}" placeholder="Metin ya da modül adı" autocomplete="off"></label>
        <button class="btn" style="align-self:flex-end" data-eylem="yeniden-ciz">${ikon("yenile", 14)}Yenile</button>
    </div>
    <pre class="kayit uzun" id="log-gor" tabindex="0" aria-label="Kayıt satırları"></pre>
    <p class="soluk kucuk-yazi uste-az" id="log-ozet"></p>`, () => {
        logCiz();
        const ara = $("#log-ara");
        ara.addEventListener("input", () => { LOG.ara = ara.value; logCiz(); });
    }];
};
function logCiz() {
    const kap = $("#log-gor");
    if (!kap) return;
    const ara = LOG.ara.toLowerCase();
    const sec = LOG.satirlar.filter((s) => {
        if (LOG.seviye === "hata" && !/ (ERROR|CRITICAL) /.test(s)) return false;
        if (LOG.seviye === "uyari" && !/ (WARNING|ERROR|CRITICAL) /.test(s)) return false;
        return !ara || s.toLowerCase().includes(ara);
    });
    kap.innerHTML = sec.map(logSatiriHtml).join("") || `<span class="k-soluk">Eşleşen satır yok.</span>`;
    kap.scrollTop = kap.scrollHeight;
    $("#log-ozet").textContent = `${sec.length} / ${LOG.satirlar.length} satır gösteriliyor.`;
}
DEGIS["log-seviye"] = (el) => { LOG.seviye = el.value; logCiz(); };
DEGIS["log-satir"] = (el) => { LOG.satir = el.value; ciz(); };

/* ---------- Yedekler ---------- */
ODOO_SEKME.yedekler = async (od, ortamAd, ort) => {
    const v = await ajan.al(`odoolar/${od.id}/${ortamAd}/yedekler`);
    const geriYukle = yetkili("geriYukle") && panelOrtami(ort);
    return [`<div class="baslik-satiri">
        <div><h2>Yedekler</h2><p class="soluk">Her yedek veritabanı ve dosya deposunu içerir. Gece yedeği 04:20'de alınır (son 7); deploy, yenileme ve geri yükleme öncesinde otomatik yedek alınır. Silinmeden önce alınan yedek hiç silinmez.</p></div>
        <div class="dugmeler" style="margin:0"><button class="btn birincil" data-eylem="yedek-al" data-odoo="${esc(od.id)}" data-ortam="${ortamAd}">${ikon("artik", 14)}Yedek al</button></div></div>
    ${!panelOrtami(ort) ? uyariKutu("gri", "Bağlanan kurulumun yedeği panelin kendi klasöründe tutulur; kurulumun kendi yedeklerine dokunulmaz. Panelden bu kuruluma geri yükleme kapalı; yedeği staging'de açabilirsiniz.") : ""}
    <div class="kart tablo-kap uste-az"><table class="tablo kartli">
        <thead><tr><th>Tarih</th><th>Tür</th><th>Kod</th><th>Boyut</th><th class="sag">İşlemler</th></tr></thead>
        <tbody>${v.yedekler.length ? v.yedekler.map((y) => `<tr>
            <td class="ana-yazi">${esc(tarihSaat(y.tarih))}<small>${esc(goreli(y.tarih))}</small></td>
            <td data-etiket="Tür"><span class="rozet ${y.etiket === "GECE" ? "" : y.etiket === "SILINMEDEN-ONCE" ? "uyari" : "islem"}">${esc(YEDEK_ETIKET[y.etiket] || y.etiket)}</span></td>
            <td data-etiket="Kod">${y.commit ? `<span class="hash">${esc(kisa(y.commit))}</span>` : `<span class="soluk">-</span>`}</td>
            <td data-etiket="Boyut" class="kirilmaz">${esc(boyutBayt(y.boyut))}</td>
            <td class="sag"><div class="islemler">
                <a class="btn kucuk" href="/api/ajan/odoolar/${encodeURIComponent(od.id)}/${ortamAd}/yedekler/${encodeURIComponent(y.dosya)}" download>${ikon("indir", 13)}İndir</a>
                ${ortamAd === "production" && yetkili("stagingYenile") ? `<button class="btn kucuk" data-eylem="yedek-staging" data-odoo="${esc(od.id)}" data-dosya="${esc(y.dosya)}" title="Production'a dokunmadan bu yedeği nötrleştirilmiş staging'de açar">Staging'de aç</button>` : ""}
                ${geriYukle ? `<button class="btn kucuk" data-eylem="yedek-geri" data-odoo="${esc(od.id)}" data-ortam="${ortamAd}" data-dosya="${esc(y.dosya)}" data-adres="${esc(alanAdi(ort.adres))}">Geri yükle</button>` : ""}
            </div></td></tr>`).join("") : `<tr><td colspan="5" class="soluk">Henüz yedek yok.</td></tr>`}</tbody>
    </table></div>`];
};
EYLEM["yedek-al"] = (el) => isBaslat(() => ajan.gonder(`odoolar/${el.dataset.odoo}/${el.dataset.ortam}/yedek`), `${ortamAdi(el.dataset.ortam)} yedeği`);
EYLEM["yedek-staging"] = (el) => onayPenceresi({
    baslik: "Yedeği staging'de aç",
    metin: `<code>${esc(el.dataset.dosya)}</code> staging'e yüklenir ve nötrleştirilir. Staging yoksa oluşturulur; varsa şimdiki verisi önce yedeklenir. Production'a dokunulmaz.`,
    dugme: "Staging'de aç",
    evet: () => isBaslat(() => ajan.gonder(`odoolar/${el.dataset.odoo}/yedek-staging`, { dosya: el.dataset.dosya }), "Yedek staging'de açılıyor"),
});
EYLEM["yedek-geri"] = (el) => adresOnayi({
    baslik: "Yedekten geri yükle",
    metin: `<code>${esc(el.dataset.dosya)}</code> bu ortamın üzerine yüklenir; şimdiki veri kaybolur. Önce şimdiki halin yedeği alınır.`,
    beklenen: el.dataset.adres, dugme: "Geri yükle",
    evet: (onay) => isBaslat(() => ajan.gonder(`odoolar/${el.dataset.odoo}/${el.dataset.ortam}/geri-yukle`, { dosya: el.dataset.dosya, onay }), "Geri yükleniyor"),
});

/* ---------- Modüller ---------- */
ODOO_SEKME.moduller = async (od, ortamAd, ort) => {
    const v = await ajan.al(`odoolar/${od.id}/${ortamAd}/moduller`);
    const zipOrtam = od.depo && od.ortamlar.staging && od.depo.dallar.staging ? "staging" : "production";
    const zipDal = od.depo ? od.depo.dallar[zipOrtam] : null;
    const prler = od.zip_pr && od.zip_pr.length ? await ajan.al(`odoolar/${od.id}/zip-pr`).then((x) => x.pr).catch(() => od.zip_pr.slice(0, 5)) : [];
    return [`<div class="baslik-satiri"><div><h2>Modüller</h2>
        <p class="soluk">Bu Odoo'ya özel modüller (depodan ya da ek klasörden). Veritabanında toplam ${esc(v.kurulu_sayisi)} modül kurulu; kurmak ve kaldırmak Odoo'daki Uygulamalar ekranından yapılır.</p></div>
        ${od.depo && yetkili("deploy") && panelOrtami(ort) ? `<button class="btn" data-eylem="uyumluluk" data-odoo="${esc(od.id)}" data-ortam="${ortamAd}">${ikon("tik", 14)}Uyumluluk denetimi</button>` : ""}</div>
    ${od.depo ? uyariKutu("mavi", `Bu Odoo <code>${esc(od.depo.ad)}</code> deposuna bağlı. Zip ile yüklenen modül sunucuya doğrudan konmaz: depoya commit edilir, sonra her zamanki deploy yolundan gelir.`, "github") : ""}
    <div class="kart tablo-kap uste-az" style="margin-bottom:1rem"><table class="tablo kartli">
        <thead><tr><th>Modül</th><th>Sürüm</th><th>Odoo</th><th>Kaynak</th></tr></thead>
        <tbody>${v.moduller.length ? v.moduller.map((m) => `<tr>
            <td class="ana-yazi">${esc(m.baslik)}<small><code>${esc(m.ad)}</code></small></td>
            <td data-etiket="Sürüm"><code>${esc(m.surum)}</code>${m.kurulu && m.kurulu_surum && m.kurulu_surum !== m.surum ? `<small class="ic-sari">veritabanında ${esc(m.kurulu_surum)}</small>` : ""}</td>
            <td data-etiket="Odoo"><span class="rozet ${m.kurulu ? "calisiyor" : ""}">${m.kurulamaz ? "Kurulamaz" : m.kurulu ? "Kurulu" : "Kurulmadı"}</span></td>
            <td data-etiket="Kaynak"><span class="etiket">${m.kaynak === "depo" ? `${ikon("github", 11)}depo` : `${ikon("yukle", 11)}ek klasör`}</span></td></tr>`).join("")
            : `<tr><td colspan="4" class="soluk">Bu Odoo'ya özel modül yok${od.depo && !ort.commit ? " (henüz deploy yapılmadı)" : ""}.</td></tr>`}</tbody>
    </table></div>
    ${prler.length ? `<div class="kart kart-ic" style="margin-bottom:1rem"><h3>Zip'ten açılan PR'lar</h3>
        <ul class="denetim-liste">${prler.map((p) => `<li>${ikon("pr", 14)}<span><a href="${esc(p.adres)}" target="_blank" rel="noopener noreferrer">PR #${esc(p.no)}</a> · <code>${esc((p.moduller || []).join(", "))}</code> → <code>${esc(p.hedef)}</code>
            <span class="rozet ${p.birlesti ? "basarili" : p.durum === "closed" ? "" : "islem"}">${p.birlesti ? "Birleşti" : p.durum === "closed" ? "Kapandı" : p.durum === "open" ? "Açık" : "?"}</span></span></li>`).join("")}</ul></div>` : ""}
    ${od.depo && od.tur === "panel" && yetkili("modul") ? zipKart(od, zipOrtam, zipDal) : ""}`];
};
function zipKart(od, ortam, dal) {
    if (od.depo.baglanti !== "app") {
        return `<div class="kart kart-ic"><h3>Modül yükle (depoya)</h3>${uyariKutu("gri", "Depo deploy key ya da kimliksiz bağlı; panel depoya yazamaz. Zip yüklemek için depoyu GitHub App ile bağlayın.")}</div>`;
    }
    return `<form class="kart kart-ic" data-form="zip" data-odoo="${esc(od.id)}" data-ortam="${ortam}">
        <h3>Modül yükle (depoya)</h3>
        <p class="soluk kucuk-yazi">Zip açılır ve denetlenir (yol, sembolik bağlantı, gizli anahtar, uyumluluk), modül depoya commit edilir. Hedef dal: <code>${esc(dal)}</code> (${ortamAdi(ortam).toLowerCase()}).</p>
        ${uyariKutu("sari", "Yüklenen kod bu Odoo'da çalışır ve verisine erişir. Yalnız güvendiğiniz kaynaktan yükleyin.")}
        <label class="alan">Modül dosyası (.zip, en çok 60 MB)<input type="file" name="dosya" accept=".zip" required></label>
        <label class="secenek"><input type="radio" name="hedef" value="dal" checked><span><strong><code>${esc(dal)}</code> dalına doğrudan commit</strong><small>${od.depo.kip[ortam] === "webhook" ? "Deploy hemen başlar." : "Ortam elle güncellendiği için commit bekleyen olarak görünür."}</small></span></label>
        <label class="secenek"><input type="radio" name="hedef" value="pr"><span><strong>Yeni dal + PR</strong><small>GitHub'da gözden geçirilip birleştirilince deploy olur.</small></span></label>
        <label class="alan">Commit mesajı<input name="mesaj" maxlength="200" placeholder="[ADD] modul_adi: kısa açıklama" autocomplete="off"></label>
        <div class="dugmeler"><button class="btn birincil" type="submit">${ikon("yukle", 14)}Depoya gönder</button></div>
    </form>`;
}
FORM.zip = async (f) => {
    const dosya = f.elements.dosya.files[0];
    if (!dosya) return;
    if (!/\.zip$/i.test(dosya.name)) { bildir("Yalnız .zip dosyası yüklenebilir.", true); return; }
    if (dosya.size > 60 * 1048576) { bildir("Dosya 60 MB'tan büyük.", true); return; }
    const veri = await dosya.arrayBuffer();
    const q = new URLSearchParams({ dosya: dosya.name, hedef: f.elements.hedef.value, mesaj: f.elements.mesaj.value.trim() });
    await isBaslat(() => api("POST", `/api/ajan/odoolar/${f.dataset.odoo}/${f.dataset.ortam}/zip?${q}`, undefined, { ham: veri, tur: "application/zip" }), `Zip depoya: ${dosya.name}`, {
        kapanis(k) {
            const s = k.sonuc || {};
            if (s.pr) return `<a class="btn birincil" href="${esc(s.pr.adres)}" target="_blank" rel="noopener noreferrer">PR #${esc(s.pr.no)}'yi aç</a>`;
            if (s.degisiklik === false) return `<span class="soluk kucuk-yazi">Depodaki modülle aynı; commit gerekmedi.</span>`;
            return (s.deploylar || []).filter((d) => d.is).map((d) => `<button class="btn birincil" data-eylem="is-ac" data-is="${esc(d.is)}">${esc(ortamAdi(d.ortam))} deploy'unu izle</button>`).join("");
        },
    });
    f.reset();
};

/* ---------- Ayarlar ---------- */
ODOO_SEKME.ayarlar = async (od, ortamAd) => {
    const st = od.ortamlar.staging;
    const pr = od.ortamlar.production;
    const bolumler = [];
    if (od.tur === "bagli") bolumler.push(bagliBolum(od));
    if (od.tur === "panel" && yetkili("github")) bolumler.push(depoBolum(od));
    if (st && yetkili("stagingYenile")) {
        bolumler.push(`<section class="kart kart-ic ort-staging">
            <h2 style="margin-bottom:.35rem">Staging</h2>
            <div class="anahtar-satir"><div>Veriyi production'dan yenile<small>Staging'in verisi yedeklenir, production'ın verisi kopyalanıp nötrleştirilir. Kod değişmez.</small></div>
                <button class="btn kucuk" data-eylem="staging-yenile" data-odoo="${esc(od.id)}">Yenile</button></div>
            <div class="anahtar-satir"><div>Staging'i kaldır<small>Veritabanı, dosya deposu ve konteyner silinir; bellek boşalır. Production'a dokunulmaz.</small></div>
                <button class="btn kucuk tehlike-cizgi" data-eylem="staging-sil" data-odoo="${esc(od.id)}" data-adres="${esc(alanAdi(st.adres))}">Kaldır</button></div>
        </section>`);
    }
    if (od.tur === "panel" && yetkili("sil")) {
        bolumler.push(`<section class="kart kart-ic" style="border-color:var(--kirmizi)">
            <h2 style="color:var(--kirmizi)">Bu Odoo'yu sil</h2>
            <p class="soluk kucuk-yazi uste-az">Staging'iyle birlikte bütün verisi silinir ve adresi çalışmaz. Silmeden önce son bir yedek alınır ve sunucuda saklanır.</p>
            <div class="dugmeler"><button class="btn tehlike" data-eylem="odoo-sil" data-odoo="${esc(od.id)}" data-adres="${esc(alanAdi(pr.adres))}">Kalıcı olarak sil</button></div>
        </section>`);
    }
    return [`<div class="yigin" style="max-width:920px">${bolumler.join("") || bosDurum("Ayar yok", "Bu Odoo için değiştirebileceğiniz ayar yok.")}</div>`, () => depoFormuBagla(od)];
};
function bagliBolum(od) {
    const yetki = yetkili("bagla") && tumKapsam();
    return `<section class="kart kart-ic">
        <h2 style="margin-bottom:.35rem">Bağlanan kurulum</h2>
        ${uyariKutu("gri", `Bu Odoo panel dışında kurulmuş ve sonradan bağlanmış (${esc(KAYNAK_ADI[od.kaynak] || od.kaynak)}). Panel izler, yedekler ve staging açar; kurulum biçimine ve compose dosyasına dokunmaz.`, "ara")}
        <div class="bilgi-satir"><span>Konteyner</span><code>${esc(od.ortamlar.production.konteyner)}</code></div>
        <div class="bilgi-satir"><span>Bağlanma</span><span class="deger">${esc(tarihSaat(od.olusturma))}${od.olusturan ? ` · ${esc(od.olusturan)}` : ""}</span></div>
        <div class="anahtar-satir"><div>Panelden durdurma ve başlatma<small>Açıksa İzleme sekmesinden konteyner durdurulup başlatılabilir (docker stop/start).</small></div>
            <label class="anahtar"><input type="checkbox" data-degis="islemler-izni" data-odoo="${esc(od.id)}" ${od.islemler_acik ? "checked" : ""} ${yetki ? "" : "disabled"} aria-label="Durdurma ve başlatma izni"><span></span></label></div>
        ${yetki ? `<div class="anahtar-satir"><div>Bağlantıyı kaldır<small>Panel bu kurulumu bırakır; kurulum çalışmaya devam eder. Panelin aldığı yedekler kalır.</small></div>
            <button class="btn kucuk tehlike-cizgi" data-eylem="baglanti-kaldir" data-odoo="${esc(od.id)}">Kaldır</button></div>` : ""}
    </section>`;
}
DEGIS["islemler-izni"] = async (el) => {
    const v = await dene(() => ajan.gonder(`odoolar/${el.dataset.odoo}/islemler`, { acik: el.checked }), "İzin");
    if (v) bildir(el.checked ? "Durdurma ve başlatma açıldı." : "Durdurma ve başlatma kapatıldı."); else el.checked = !el.checked;
};
EYLEM["baglanti-kaldir"] = (el) => onayPenceresi({
    baslik: "Bağlantıyı kaldır", metin: "Panel bu kurulumu bırakır. Kurulum çalışmaya devam eder; staging varsa önce silinmeli.", dugme: "Kaldır", tehlike: true, tur: "kirmizi",
    async evet() {
        const v = await dene(() => ajan.gonder(`odoolar/${el.dataset.odoo}/baglantiyi-kaldir`), "Bağlantı");
        pencereKapat();
        if (v) { bildir("Bağlantı kaldırıldı."); S.odoolar = null; git("#/odoolar"); }
    },
});
function depoBolum(od) {
    const d = od.depo;
    const appYok = S.saglik && !S.saglik.app;
    const bilgi = d ? `
        <div class="bilgi-satir"><span>Depo</span><a href="https://github.com/${esc(d.ad)}" target="_blank" rel="noopener noreferrer"><code>${esc(d.ad)}</code></a></div>
        <div class="bilgi-satir"><span>Bağlantı</span><span class="deger">${esc(BAGLANTI_ADI[d.baglanti] || d.baglanti)}</span></div>
        ${Object.entries(d.dallar).map(([o, dal]) => `<div class="bilgi-satir"><span>${ortamAdi(o)} dalı</span><span class="deger"><code>${esc(dal)}</code> · ${d.kip[o] === "webhook" ? "otomatik" : "elle"}</span></div>`).join("")}
        <div class="dugmeler"><button class="btn" data-eylem="depo-form-ac">Değiştir</button><button class="btn tehlike-cizgi" data-eylem="depo-kaldir" data-odoo="${esc(od.id)}">Bağlantıyı kaldır</button></div>` : "";
    return `<section class="kart kart-ic">
        <div class="kart-baslik"><h2 style="display:flex;gap:.4rem;align-items:center">${ikon("github", 17)}Kod deposu</h2>${d ? `<span class="rozet calisiyor">Bağlı</span>` : `<span class="rozet">Bağlı değil</span>`}</div>
        ${bilgi}
        <form data-form="depo" data-odoo="${esc(od.id)}" class="${d ? "gizli" : ""}" id="depo-form">
            ${d ? "" : `<p class="soluk kucuk-yazi">Bağlanınca modüller depodan gelir; her deploy commit'e sabitlenir, geçmişe yazılır ve geri alınabilir. Kod deposun köküne konmuş modüllerden oluşmalı.</p>`}
            <div class="form-izgara">
                <label class="alan">Depo (sahip/depo)<input name="ad" required value="${esc(d ? d.ad : "")}" placeholder="vekosis/ornek-addons" spellcheck="false" autocomplete="off"></label>
                <label class="alan">Bağlantı<select name="baglanti">
                    ${["app", "anahtar", "acik"].map((b) => `<option value="${b}" ${(d ? d.baglanti : "app") === b ? "selected" : ""}>${esc(BAGLANTI_ADI[b])}</option>`).join("")}</select></label>
                <label class="alan">Production dalı<input name="dal_production" required value="${esc(d ? d.dallar.production : "main")}" spellcheck="false"></label>
                <label class="alan">Staging dalı (isteğe bağlı)<input name="dal_staging" value="${esc(d && d.dallar.staging ? d.dallar.staging : "")}" placeholder="staging" spellcheck="false"></label>
            </div>
            <div class="form-izgara">
                <label class="alan">Production güncellemesi<select name="kip_production">
                    <option value="elle" ${!d || d.kip.production === "elle" ? "selected" : ""}>Elle (yeni commit bekler)</option>
                    <option value="webhook" ${d && d.kip.production === "webhook" ? "selected" : ""}>Otomatik (push gelince)</option></select></label>
                <label class="alan">Staging güncellemesi<select name="kip_staging">
                    <option value="webhook" ${!d || d.kip.staging !== "elle" ? "selected" : ""}>Otomatik (push gelince)</option>
                    <option value="elle" ${d && d.kip.staging === "elle" ? "selected" : ""}>Elle</option></select></label>
            </div>
            <div id="depo-ipucu"></div>
            <div class="dugmeler"><button class="btn birincil" type="submit">${d ? "Kaydet" : "Bağla"}</button>
                <button class="btn ${d ? "" : "gizli"}" type="button" data-eylem="depo-form-kapat">Vazgeç</button></div>
        </form>
        ${appYok ? `<p class="soluk kucuk-yazi uste-az">Sunucuda GitHub App bilgisi tanımlı değil; App ile bağlı depoda deploy ve zip yüklemesi çalışmaz.</p>` : ""}
    </section>`;
}
function depoFormuBagla(od) {
    const f = $("#depo-form");
    if (!f) return;
    const ipucu = () => {
        const b = f.elements.baglanti.value;
        $("#depo-ipucu").innerHTML = b === "app"
            ? `<p class="soluk kucuk-yazi">GitHub App bu depoya kurulu olmalı. Okuma ve yazma (zip yüklemesi, PR, production'a almada birleştirme) App jetonuyla yapılır.</p>`
            : b === "anahtar"
                ? `<p class="soluk kucuk-yazi">Panel salt okunur bir deploy key üretir; açık anahtarı GitHub'da depo Ayarlar > Deploy keys'e ekleyin. Zip yüklemesi ve PR bu bağlantıda yok.</p>
                   <button class="btn kucuk" type="button" data-eylem="deploy-key" data-odoo="${esc(od.id)}">${ikon("anahtar", 13)}Deploy key üret</button><div id="deploy-key"></div>`
                : `<p class="soluk kucuk-yazi">Herkese açık depo kimliksiz okunur. Zip yüklemesi ve PR yok.</p>`;
    };
    f.elements.baglanti.addEventListener("change", ipucu);
    ipucu();
}
EYLEM["depo-form-ac"] = () => { $("#depo-form").classList.remove("gizli"); };
EYLEM["depo-form-kapat"] = () => { $("#depo-form").classList.add("gizli"); };
EYLEM["deploy-key"] = async (el) => {
    const f = $("#depo-form");
    const ad = f.elements.ad.value.trim();
    if (!ad) { bildir("Önce depo adını yazın.", true); return; }
    const v = await dene(() => ajan.gonder(`odoolar/${el.dataset.odoo}/depo/anahtar`, { ad }), "Deploy key");
    if (!v) return;
    $("#deploy-key").innerHTML = `<div class="uste-az"><pre class="kayit" style="white-space:pre-wrap;word-break:break-all">${esc(v.acik_anahtar)}</pre>
        <button class="btn kucuk" type="button" data-eylem="kopyala" data-metin="${esc(v.acik_anahtar)}">Kopyala</button>
        <a class="btn kucuk" href="https://github.com/${esc(ad)}/settings/keys/new" target="_blank" rel="noopener noreferrer">GitHub'da ekle ${ikon("dis", 12)}</a></div>`;
};
FORM.depo = async (f) => {
    const e = f.elements;
    const govde = { ad: e.ad.value.trim(), baglanti: e.baglanti.value, dallar: { production: e.dal_production.value.trim() }, kip: { production: e.kip_production.value } };
    if (e.dal_staging.value.trim()) { govde.dallar.staging = e.dal_staging.value.trim(); govde.kip.staging = e.kip_staging.value; }
    const v = await dene(() => ajan.gonder(`odoolar/${f.dataset.odoo}/depo`, govde), "Depo");
    if (!v) return;
    bildir("Depo bağlandı. İlk deploy Deploylar sekmesinden başlatılır.");
    git(odooRota(f.dataset.odoo, "production", "deploylar"));
};
EYLEM["depo-kaldir"] = (el) => onayPenceresi({
    baslik: "Depo bağlantısını kaldır", metin: "Yayındaki kod ve deploy geçmişi kalır; yeni push'lar gelmez ve deploy yapılamaz.", dugme: "Kaldır", tehlike: true, tur: "kirmizi",
    async evet() {
        const v = await dene(() => ajan.gonder(`odoolar/${el.dataset.odoo}/depo/kaldir`), "Depo");
        pencereKapat();
        if (v) { bildir("Depo bağlantısı kaldırıldı."); ciz({ sessiz: true }); }
    },
});
EYLEM["staging-sil"] = (el) => adresOnayi({
    baslik: "Staging'i kaldır", metin: "Staging'in veritabanı, dosya deposu ve konteyneri silinir. Production'a dokunulmaz.",
    beklenen: el.dataset.adres, dugme: "Kaldır",
    evet: (onay) => isBaslat(() => ajan.gonder(`odoolar/${el.dataset.odoo}/staging/sil`, { onay }), "Staging kaldırılıyor", {
        bitince: (k) => { if (k.durum === "tamam") git(odooRota(el.dataset.odoo, "production", "ayarlar")); },
    }),
});
EYLEM["odoo-sil"] = (el) => adresOnayi({
    baslik: "Odoo'yu sil", metin: "Bu Odoo staging'iyle birlikte silinir; adresi çalışmaz. Silmeden önce son bir yedek alınır ve saklanır.",
    beklenen: el.dataset.adres, dugme: "Kalıcı olarak sil",
    evet: (onay) => isBaslat(() => ajan.gonder(`odoolar/${el.dataset.odoo}/sil`, { onay }), "Odoo siliniyor", {
        bitince: async (k) => { if (k.durum === "tamam") { S.odoolar = null; git("#/odoolar"); } },
    }),
});

/* ---- basla.js ---- */
/* Açılış: tema, oturum denetimi */
(async () => {
    S.tema = depo.al("tema") || (window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    document.documentElement.dataset.theme = S.tema;
    document.body.classList.add("oneriler-gizli");
    try {
        await benYukle();
    } catch {
        girisCiz();
        return;
    }
    S.saglik = await ajan.al("saglik").catch(() => null);
    await dene(odoolariYukle, "Odoo listesi");
    R = rotaCoz();
    ciz();
})();
