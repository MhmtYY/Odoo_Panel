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
        return [bosDurum(yetkili("kur") ? "Henüz platform yok" : "Erişebildiğiniz platform yok",
            yetkili("kur") ? "Yeni bir Odoo kurun ya da sunucuda çalışan bir Odoo'yu panele bağlayın." : "Hesabınıza atanmış platform yok. Panel yöneticisiyle görüşün.",
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
        <div><p class="ust-etiket">Panel</p><h1>Platformlar</h1>
            <p class="soluk">${l.length} Odoo, ${calisan} çalışıyor. Ortamların kullandığı bellek ${esc(boyutMb(toplam))}${S.bosBellek != null ? `, sunucuda boş ${esc(boyutMb(S.bosBellek))}` : ""}.</p></div>
        <div class="dugmeler" style="margin:0">${dugmeler}</div>
    </div>
    ${dikkat.length ? `<div class="dikkat-listesi">${dikkat.map((d) => `<a class="dikkat" href="${d.hedef}" style="color:inherit;text-decoration:none">${ikon(d.ikon, 16, `class="${d.sinif}" style="margin-top:.15rem"`)}<span><strong>${esc(d.baslik)}</strong><small>${esc(d.alt)}</small></span></a>`).join("")}</div>` : ""}
    <div class="kart tablo-kap">
        <table class="tablo kartli">
            <thead><tr><th>Platform</th><th>Sürüm</th><th>Production</th><th>Staging</th><th>Kod deposu</th><th>Bellek</th><th class="sag">İşlemler</th></tr></thead>
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
            <a class="btn" href="${odooRota(govde.id)}" data-eylem="pencere-kapat-git">Platforma git</a>` : ""),
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
        <p class="soluk">Kullanıcı yalnız erişimi verilen platformları görür. Rol neyi yapabileceğini belirler.</p></div>
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
    ["Mevcut Odoo'yu bağlama (bütün platformlara erişimi olan)", 1, 1, 0],
];
function kapsamSecimi(secili) {
    const tum = secili === "*";
    const liste = (S.odoolar || []).map((o) => `<label class="onay-satir"><input type="checkbox" name="kapsam" value="${esc(o.id)}" ${tum || (Array.isArray(secili) && secili.includes(o.id)) ? "checked" : ""}> ${esc(o.firma)} <code class="kucuk-yazi">${esc(o.id)}</code></label>`).join("");
    return `<fieldset class="uste-az" style="border:0;padding:0;margin:0"><legend class="kucuk-yazi">Erişebileceği platformlar</legend>
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
    [/\/sil$/, "Platform silme"], [/^POST bagla$/, "Mevcut Odoo'yu bağlama"], [/^INDIRDI/, "Yedek indirme"], [/^WEBHOOK/, "GitHub webhook"],
    [/\/islemler$/, "Durdurma / başlatma iznini değiştirme"], [/\/deploy-anahtari$/, "Deploy anahtarı üretme"],
    [/^KENDI SIFRESINI DEGISTIRDI$/, "Kendi şifresini değiştirme"], [/^SIFRE SIFIRLADI/, "Şifre sıfırlama"],
    [/^KULLANICI/, "Kullanıcı işlemi"], [/^MCP/, "Ajan (MCP) işlemi"], [/^JETON/, "Erişim jetonu"], [/^ASISTAN/, "Asistan"],
];
const olayAdi = (o) => { const e = OLAY_ADI.find(([d]) => d.test(o)); return e ? e[1] : o; };
const SONUC_ADI = {
    200: "Tamam", 201: "Tamam", 202: "Başladı", 400: "Geçersiz istek", 401: "Oturum yok", 403: "Yetki yok",
    404: "Bulunamadı", 409: "Çakışma", 413: "Çok büyük", 500: "Hata", 502: "Ajana ulaşılamadı", 504: "Zaman aşımı",
};
const IS_SONUC = { tamam: ["Tamamlandı", "basarili"], hata: ["Başarısız", "hata"], calisiyor: ["Sürüyor", "islem"], bekliyor: ["Sırada", "islem"], atlandi: ["Atlandı", ""] };
function denetimSonuc(k) {
    if (k.kod == null) return "-";
    const kod = `<small class="soluk kirilmaz">HTTP ${esc(k.kod)}</small>`;
    if (k.is && k.is_durum && IS_SONUC[k.is_durum]) {
        const [ad, sinif] = IS_SONUC[k.is_durum];
        return `<span class="rozet ${sinif}">${esc(ad)}</span> ${kod}`;
    }
    return `<span class="rozet ${k.kod < 300 ? "basarili" : "hata"}">${esc(SONUC_ADI[k.kod] || "Hata")}</span> ${kod}`;
}
EYLEM["denetim-is"] = (el) => isIzle({ id: el.dataset.is, durum: "bekliyor" }, el.dataset.baslik);
PLATFORM.denetim = async () => {
    const v = await api("GET", "/api/denetim");
    return [`
    <div class="baslik-satiri"><div><p class="ust-etiket">Panel</p><h1>Denetim kaydı</h1>
        <p class="soluk">Paneldeki her işlem kişi, zaman ve IP ile tutulur. Son ${v.kayitlar.length} kayıt.</p></div></div>
    <div class="kart tablo-kap"><table class="tablo kartli">
        <thead><tr><th>Zaman</th><th>Kim</th><th>İşlem</th><th>Platform</th><th>Sonuç</th><th>IP</th></tr></thead>
        <tbody>${v.kayitlar.map((k) => `<tr>
            <td data-etiket="Zaman"><span class="kirilmaz">${esc(tarihSaat(k.zaman))}</span></td>
            <td data-etiket="Kim"><code>${esc(k.kullanici)}</code></td>
            <td data-etiket="İşlem" class="ana-yazi">${esc(olayAdi(k.olay))}<small><code>${esc(k.olay)}</code></small>
                ${k.hata || k.is_hata ? `<span class="denetim-hata">${ikon("uyari", 13)} ${esc(k.hata || k.is_hata)}</span>` : ""}
                ${k.is ? `<button class="btn-baglanti kucuk-yazi" data-eylem="denetim-is" data-is="${esc(k.is)}" data-baslik="${esc(olayAdi(k.olay))}">İşin adımlarını göster</button>` : ""}</td>
            <td data-etiket="Platform">${esc(k.odoo || "-")}</td>
            <td data-etiket="Sonuç">${denetimSonuc(k)}</td>
            <td data-etiket="IP"><code>${esc(k.ip || "-")}</code></td></tr>`).join("") || `<tr><td colspan="6" class="soluk">Kayıt yok.</td></tr>`}</tbody>
    </table></div>`];
};
