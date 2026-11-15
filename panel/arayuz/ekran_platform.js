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
const SABLON_TUR = { veri: "Veriyle", moduller: "Yalnız modüller" };
EYLEM["yeni-odoo"] = async () => {
    pencereAc("Yeni Odoo kur", `<p class="soluk">${ikon("don", 14, 'class="donen"')} Seçenekler alınıyor...</p>`);
    const belirtec = pencereSayac;
    const s = await dene(() => ajan.al("kurulum-secenekleri"), "Kurulum seçenekleri");
    if (belirtec !== pencereSayac) return;
    const sablon = s && s.sablon;
    const imajlar = (s && s.imajlar) || [];
    const sablonlar = ((s && s.sablonlar) || []).filter((x) => x.imaj_var);
    const imajSecenekleri = imajlar.map((x, i) => `<option value="${esc(x.imaj)}" data-tur="${esc(x.tur)}" ${i === 0 ? "selected" : ""}>${esc(x.ad)}</option>`).join("")
        + (sablon ? `<option value="${esc(sablon.imaj)}" ${imajlar.length ? "" : "selected"}>Vekosis modül seti (test platformu imajı)</option>` : "")
        + `<option value="diger" ${imajlar.length || sablon ? "" : "selected"}>Diğer imaj (elle yazılır)</option>`;
    pencereAc("Yeni Odoo kur", `
        <form data-form="yeni-odoo">
            <div class="form-izgara">
                <label class="alan">Ad (adresin ilk parçası)<input name="id" required pattern="[a-z][a-z0-9\\-]{1,20}[a-z0-9]" maxlength="22" autocomplete="off" spellcheck="false" autofocus placeholder="ornekfirma"></label>
                <label class="alan">Firma adı<input name="firma" maxlength="120" autocomplete="off" placeholder="Örnek Firma A.Ş."></label>
            </div>
            <p class="kucuk-yazi soluk uste-az">Adres: <code id="yeni-adres">ad.${esc(S.saglik ? S.saglik.alan : "panel.vekosis.com")}</code>. Küçük harfle başlar; küçük harf, rakam ve tire.</p>
            <h4 class="uste">Başlangıç</h4>
            <label class="secenek"><input type="radio" name="baslangic" value="bos" checked><span><strong>Boş Odoo</strong><small>Yalnız temel modül ve Türkçe. Modüller sonra depodan ya da Uygulamalar ekranından gelir.</small></span></label>
            <label class="secenek ${sablonlar.length ? "" : "gizli"}"><input type="radio" name="baslangic" value="panel-sablon" ${sablonlar.length ? "" : "disabled"}><span><strong>Şablondan</strong><small>Bir platformdan alınmış şablonun kodu, imajı ve verisi ya da modülleriyle.</small></span></label>
            <label class="secenek ${sablon ? "" : "gizli"}"><input type="radio" name="baslangic" value="sablon" ${sablon ? "" : "disabled"}><span><strong>Test platformunun tam şablonu</strong><small>Bütün modüller kurulu ve ayarlı${sablon ? ` (<code>${esc(sablon.ad)}</code>)` : ""}.</small></span></label>
            <label class="onay-satir uste-az gizli" id="ornek-satir"><input type="checkbox" name="ornek" checked> Kurgusal örnek veriyle gelsin (müşteri Ayarlar'dan silebilir)</label>
            <div id="imaj-alani" class="uste">
                <label class="alan">Odoo sürümü<select name="imaj_sec">${imajSecenekleri}</select></label>
                <label class="alan uste-az gizli" id="imaj-elle">İmaj<input name="imaj" spellcheck="false" autocomplete="off" placeholder="vekosis/test20:20261108-1"></label>
                <div id="imaj-uyari" class="uste-az"></div>
            </div>
            <div id="sablon-alani" class="uste gizli">
                <label class="alan">Şablon<select name="sablon">${sablonlar.map((x) => `<option value="${esc(x.ad)}">${esc(x.baslik)} · ${esc(SABLON_TUR[x.tur] || x.tur)} · Odoo ${esc(x.seri || "-")}</option>`).join("")}</select></label>
                <div id="sablon-bilgi" class="uste-az"></div>
            </div>
            <p class="soluk kucuk-yazi uste-az">Kurulumda yönetici şifresi üretilir ve bir kez gösterilir; sonradan "Giriş bilgisi" ile görülür.</p>
            <div class="dugmeler"><button class="btn birincil" type="submit">Kur</button><button class="btn" type="button" data-eylem="pencere-kapat">Vazgeç</button></div>
        </form>`);
    const f = $("#pencere-govde form");
    const alan = S.saglik ? S.saglik.alan : "panel.vekosis.com";
    f.elements.id.addEventListener("input", () => { $("#yeni-adres").textContent = `${f.elements.id.value || "ad"}.${alan}`; });
    const guncelle = () => {
        const bas = f.elements.baslangic.value;
        const elle = f.elements.imaj_sec.value === "diger";
        $("#imaj-alani").classList.toggle("gizli", bas !== "bos");
        $("#sablon-alani").classList.toggle("gizli", bas !== "panel-sablon");
        $("#ornek-satir").classList.toggle("gizli", bas !== "sablon");
        $("#imaj-elle").classList.toggle("gizli", !elle);
        f.elements.imaj.required = bas === "bos" && elle;
        const secili = f.elements.imaj_sec.selectedOptions[0];
        $("#imaj-uyari").innerHTML = secili && secili.dataset.tur === "enterprise"
            ? uyariKutu("sari", "Enterprise sürümü için müşterinin Odoo Enterprise aboneliği gerekir. Abonelik kodu girilmezse veritabanı deneme süresi sonunda kilitlenir.") : "";
        const sb = sablonlar.find((x) => x.ad === f.elements.sablon.value);
        $("#sablon-bilgi").innerHTML = sb ? `<p class="soluk kucuk-yazi">Kaynak: ${esc(sb.kaynak_firma || sb.kaynak_odoo)} (${esc(ortamAdi(sb.kaynak_ortam))}) · ${esc(sb.modul_sayisi)} modül${sb.aciklama ? ` · ${esc(sb.aciklama)}` : ""}</p>
            ${sb.tur === "veri" ? uyariKutu("sari", "Şablonun verisi yeni platforma kopyalanır. Yönetici dışındaki kullanıcılar pasif gelir.") : ""}` : "";
    };
    f.addEventListener("change", guncelle);
    guncelle();
};
FORM["yeni-odoo"] = async (f) => {
    const baslangic = f.elements.baslangic.value;
    const secilen = f.elements.imaj_sec.value;
    const govde = { id: f.elements.id.value.trim(), firma: f.elements.firma.value.trim(), baslangic, ornek: f.elements.ornek.checked };
    if (baslangic === "panel-sablon") govde.sablon = f.elements.sablon.value;
    if (baslangic === "bos") govde.imaj = secilen === "diger" ? f.elements.imaj.value.trim() : secilen;
    await isBaslat(() => ajan.gonder("odoolar", govde), `Kuruluyor: ${govde.id}`, {
        kapanis: (k) => (k.durum === "tamam" ? `<button class="btn birincil" data-eylem="giris-bilgisi" data-odoo="${esc(govde.id)}">Giriş bilgisini göster</button>
            <a class="btn" href="${odooRota(govde.id)}" data-eylem="pencere-kapat-git">Platforma git</a>` : ""),
    });
};

/* ---------- Şablonlar ---------- */
PLATFORM.sablonlar = async () => {
    const v = await ajan.al("sablonlar");
    const silebilir = yetkili("sablon") && tumKapsam();
    return [`
    <div class="baslik-satiri"><div><p class="ust-etiket">Panel</p><h1>Şablonlar</h1>
        <p class="soluk">Bir platformdan alınmış kopyalar. Yeni Odoo kurarken "Şablondan" seçilir. Şablon oluşturmak için platformun Ayarlar sekmesine gidin.</p></div></div>
    ${v.sablonlar.length ? `<div class="kart tablo-kap"><table class="tablo kartli">
        <thead><tr><th>Şablon</th><th>Tür</th><th>Kaynak</th><th>Sürüm</th><th>Boyut</th><th>Tarih</th><th class="sag"></th></tr></thead>
        <tbody>${v.sablonlar.map((s) => `<tr>
            <td><span class="ana-yazi">${esc(s.baslik)}</span><small><code>${esc(s.ad)}</code>${s.aciklama ? ` · ${esc(s.aciklama)}` : ""}</small>${s.imaj_var ? "" : `<small style="color:var(--kirmizi)">İmajı sunucuda yok, kullanılamaz: <code>${esc(s.imaj)}</code></small>`}</td>
            <td data-etiket="Tür">${esc(SABLON_TUR[s.tur] || s.tur)}<small class="soluk">${esc(s.modul_sayisi)} modül</small></td>
            <td data-etiket="Kaynak">${esc(s.kaynak_firma || s.kaynak_odoo)}<small class="soluk">${esc(ortamAdi(s.kaynak_ortam))}</small></td>
            <td data-etiket="Sürüm"><span class="rozet surum">${esc(s.seri || "-")}</span></td>
            <td data-etiket="Boyut" class="kirilmaz">${esc(boyutMb(s.boyut / 1048576))}</td>
            <td data-etiket="Tarih" class="kirilmaz">${esc(tarihSaat(s.tarih))}${s.olusturan ? `<small class="soluk">${esc(s.olusturan)}</small>` : ""}</td>
            <td class="sag">${silebilir ? `<button class="btn kucuk tehlike-cizgi" data-eylem="sablon-sil" data-ad="${esc(s.ad)}" data-baslik="${esc(s.baslik)}">Sil</button>` : ""}</td></tr>`).join("")}</tbody>
    </table></div>` : bosDurum("Henüz şablon yok", "Bir platformun Ayarlar sekmesinden şablon oluşturabilirsiniz.", "", "sablon")}`];
};
EYLEM["sablon-sil"] = (el) => onayPenceresi({
    baslik: "Şablonu sil", metin: `<strong>${esc(el.dataset.baslik)}</strong> silinir. Bu şablondan kurulmuş platformlar etkilenmez.`,
    dugme: "Sil", tehlike: true, tur: "kirmizi",
    evet: async () => { const v = await dene(() => ajan.gonder(`sablonlar/${el.dataset.ad}/sil`), "Şablon"); pencereKapat(); if (v) { bildir("Şablon silindi."); ciz({ sessiz: true }); } },
});
EYLEM["sablon-olustur"] = (el) => {
    const { odoo, ortam } = el.dataset;
    pencereAc("Şablon oluştur", `
        <form data-form="sablon-olustur" data-odoo="${esc(odoo)}" data-ortam="${esc(ortam)}">
            <p class="soluk kucuk-yazi">${esc(el.dataset.firma)} (${esc(ortamAdi(ortam))}) kopyalanır. Platform çalışmaya devam eder, hiçbir şeyi değişmez.</p>
            <div class="form-izgara uste-az">
                <label class="alan">Şablon adı<input name="ad" required pattern="[a-z][a-z0-9\\-]{1,38}[a-z0-9]" maxlength="40" autocomplete="off" spellcheck="false" autofocus placeholder="imalat-temel"></label>
                <label class="alan">Başlık<input name="baslik" maxlength="80" autocomplete="off" placeholder="İmalat firması başlangıç paketi"></label>
            </div>
            <label class="alan uste-az">Açıklama<input name="aciklama" maxlength="300" autocomplete="off"></label>
            <h4 class="uste">Ne alınsın?</h4>
            <label class="secenek"><input type="radio" name="tur" value="moduller" checked><span><strong>Yalnız modüller</strong><small>Kurulu modül listesi, kod ve imaj. Yeni platform boş veritabanıyla açılıp aynı modülleri kurar; ayarlar gelmez.</small></span></label>
            <label class="secenek"><input type="radio" name="tur" value="veri"><span><strong>Veriyle</strong><small>Ayarlar, ana veriler ve belgelerle tam kopya. Posta sunucuları, e-Belge ve entegrasyon anahtarları silinir; yönetici dışındaki kullanıcılar pasif olur, şifreler silinir.</small></span></label>
            <div id="sablon-veri-uyari" class="uste-az gizli">
                ${uyariKutu("kirmizi", "Şablon platformun bütün verisini taşır (kişiler, belgeler, faturalar). Gerçek müşteri verisi olan platformdan veriyle şablon almayın: bir müşterinin verisi başka müşteriye geçmemeli.")}
                <label class="onay-satir uste-az"><input type="checkbox" name="onay"> Bu platformda gerçek müşteri verisi yok</label>
            </div>
            <div class="dugmeler"><button class="btn birincil" type="submit">Oluştur</button><button class="btn" type="button" data-eylem="pencere-kapat">Vazgeç</button></div>
        </form>`);
    const f = $("#pencere-govde form");
    f.addEventListener("change", () => {
        const veri = f.elements.tur.value === "veri";
        $("#sablon-veri-uyari").classList.toggle("gizli", !veri);
        f.elements.onay.required = veri;
    });
};
FORM["sablon-olustur"] = async (f) => {
    const govde = { ad: f.elements.ad.value.trim(), baslik: f.elements.baslik.value.trim(), aciklama: f.elements.aciklama.value.trim(),
        tur: f.elements.tur.value, onay: f.elements.onay.checked };
    await isBaslat(() => ajan.gonder(`odoolar/${f.dataset.odoo}/${f.dataset.ortam}/sablon`, govde), `Şablon: ${govde.ad}`, {
        kapanis: (k) => (k.durum === "tamam" ? `<a class="btn birincil" href="#/sablonlar" data-eylem="pencere-kapat-git">Şablonlara git</a>` : ""),
    });
};

/* ---------- Yedekleme ---------- */
const PERIYOT_ADI = { 0: "Kapalı", 6: "6 saatte bir", 12: "12 saatte bir", 24: "Günde bir", 48: "2 günde bir", 168: "Haftada bir" };
function planSaatleri(p) {
    if (!p.periyot_saat) return "";
    const adim = Math.min(p.periyot_saat, 24);
    const saatler = [];
    for (let h = 0; h < 24; h += adim) saatler.push((p.saat + h) % 24);
    return saatler.sort((a, b) => a - b).map((h) => `${iki(h)}:20`).join(", ");
}
function planMetni(p) {
    if (!p.periyot_saat) return `Otomatik yedek kapalı; var olan otomatik yedekler ${p.saklama_gun} gün saklanır.`;
    const ek = p.periyot_saat === 48 ? " (iki günde bir)" : p.periyot_saat === 168 ? " (ilk yedekten başlayarak 7 günde bir)" : "";
    return `${PERIYOT_ADI[p.periyot_saat]}, saat ${planSaatleri(p)}${ek}; ${p.saklama_gun} gün saklanır.`;
}
function planAlanlari(p) {
    return `<div class="form-izgara">
        <label class="alan">Sıklık<select name="periyot_saat">${Object.entries(PERIYOT_ADI).map(([d, ad]) => `<option value="${d}" ${Number(d) === p.periyot_saat ? "selected" : ""}>${esc(ad)}</option>`).join("")}</select></label>
        <label class="alan">Saat<select name="saat">${Array.from({ length: 24 }, (_, h) => `<option value="${h}" ${h === p.saat ? "selected" : ""}>${iki(h)}:20</option>`).join("")}</select></label>
        <label class="alan">Kaç gün saklansın<input name="saklama_gun" type="number" min="1" max="365" required value="${esc(p.saklama_gun)}"></label>
    </div>`;
}
const planGovdesi = (f) => ({ periyot_saat: Number(f.elements.periyot_saat.value), saat: Number(f.elements.saat.value), saklama_gun: Number(f.elements.saklama_gun.value) });
function sonYedekMetni(o) {
    if (!o) return "-";
    return `${o.son ? `Son: ${esc(goreli(o.son))}` : "Henüz otomatik yedek yok"}${o.sonraki ? ` · Sonraki: ${esc(tarihSaat(o.sonraki))}` : ""}`;
}
PLATFORM.yedekleme = async () => {
    const v = await ajan.al("yedek-plani");
    const genelDuzenler = yetkili("yedekPlani") && tumKapsam();
    return [`
    <div class="baslik-satiri"><div><p class="ust-etiket">Panel</p><h1>Yedekleme</h1>
        <p class="soluk">Otomatik yedeklerin sıklığı ve kaç gün saklanacağı. Genel plan bütün platformlara uygulanır; bir platformda ayrıca değiştirilirse o platformun planı geçerli olur. Elle, deploy öncesi ve silinmeden önce alınan yedekler bu plandan bağımsızdır.</p></div></div>
    <section class="kart kart-ic">
        <div class="kart-baslik"><h2>Genel plan</h2></div>
        ${genelDuzenler ? `<form data-form="yedek-plani-genel">${planAlanlari(v.genel)}
            <p class="soluk kucuk-yazi uste-az">Saklama süresini aşan otomatik yedekler silinir; her ortamın en yeni otomatik yedeği her zaman kalır.</p>
            <div class="dugmeler"><button class="btn birincil" type="submit">Kaydet</button></div></form>`
            : `<p>${esc(planMetni(v.genel))}</p>`}
    </section>
    <div class="kart tablo-kap uste"><table class="tablo kartli">
        <thead><tr><th>Platform</th><th>Plan</th><th>Production</th><th>Staging</th><th class="sag"></th></tr></thead>
        <tbody>${v.platformlar.map((p) => `<tr>
            <td class="ana-yazi">${esc(p.firma || p.id)}<small><code>${esc(p.id)}</code></small></td>
            <td data-etiket="Plan"><span class="rozet ${p.ozel ? "islem" : ""}">${p.ozel ? "Bu platforma özel" : "Genel plan"}</span><small>${esc(planMetni(p.gecerli))}</small></td>
            <td data-etiket="Production" class="kucuk-yazi">${sonYedekMetni(p.ortamlar.production)}</td>
            <td data-etiket="Staging" class="kucuk-yazi">${p.ortamlar.staging ? sonYedekMetni(p.ortamlar.staging) : `<span class="soluk">Yok</span>`}</td>
            <td class="sag"><a class="btn kucuk" href="${odooRota(p.id, "production", "yedekler")}">Yedekler</a></td></tr>`).join("")
            || `<tr><td colspan="5" class="soluk">Platform yok.</td></tr>`}</tbody>
    </table></div>`];
};
FORM["yedek-plani-genel"] = async (f) => {
    const v = await dene(() => ajan.gonder("yedek-plani", planGovdesi(f)), "Yedek planı");
    if (v) { bildir("Genel yedek planı kaydedildi."); ciz({ sessiz: true }); }
};

/* ---------- pencereden sayfaya ---------- */
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
    [/yedek-plani$/, "Yedek planını değiştirme"], [/\/sablon$/, "Şablon oluşturma"], [/^POST sablonlar\//, "Şablon silme"],
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
