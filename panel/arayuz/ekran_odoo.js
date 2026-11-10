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
