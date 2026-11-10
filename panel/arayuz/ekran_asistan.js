/* Asistan sekmesi (platform ortamı başına sohbet) ve Ajan bağlantıları ekranı (MCP, jetonlar, asistan ayarı) */

/* ---------- güvenli markdown: önce kaçırılır, sonra yalnız birkaç biçim ---------- */
function mdHtml(metin) {
    const satirIci = (s) => esc(s).replace(/`([^`]+)`/g, "<code>$1</code>").replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    return String(metin || "").split("```").map((parca, i) => {
        if (i % 2 === 1) return `<pre class="kayit">${esc(parca.replace(/^[A-Za-z0-9_+-]*\n/, ""))}</pre>`;
        return parca.trim().split(/\n{2,}/).filter(Boolean).map((blok) => {
            const satirlar = blok.split("\n");
            if (satirlar.every((s) => /^\s*[-*] /.test(s))) return `<ul>${satirlar.map((s) => `<li>${satirIci(s.replace(/^\s*[-*] /, ""))}</li>`).join("")}</ul>`;
            if (satirlar.every((s) => /^\s*\d+[.)] /.test(s))) return `<ol>${satirlar.map((s) => `<li>${satirIci(s.replace(/^\s*\d+[.)] /, ""))}</li>`).join("")}</ol>`;
            const baslik = satirlar.length === 1 && blok.match(/^#{1,4} (.*)$/);
            if (baslik) return `<p><strong>${satirIci(baslik[1])}</strong></p>`;
            return `<p>${satirlar.map(satirIci).join("<br>")}</p>`;
        }).join("");
    }).join("");
}

/* ---------- Asistan sekmesi ---------- */
const ASISTAN_ORNEK = [
    "Son 24 saatte hata ya da uyarı var mı? Nedenleri neler?",
    "En yavaş ekranlar hangileri ve neden yavaşlar?",
    "Zamanlanmış işlerde hata veren var mı?",
    "Son deploy'da ne değişti, uyarı verdi mi?",
];
ODOO_SEKME.asistan = async (od, ortamAd) => {
    const v = await api("GET", `/api/asistan/${encodeURIComponent(od.id)}/${ortamAd}`);
    const yazar = !!(od.depo && od.depo.baglanti === "app" && od.depo.dallar && od.depo.dallar.staging && yetkili("deploy"));
    const ayar = v.ayar || {};
    const kapali = !ayar.anahtar_var || !ayar.sdk;
    return [`<div class="asistan">
        <div class="kart asistan-pano">
            <div class="asistan-ust">
                <strong style="display:flex;gap:.35rem;align-items:center">${ikon("asistan", 16)}Asistan</strong>
                <span class="etiket">${esc(ortamAd)}</span>
                <span class="rozet ${yazar ? "uyari" : "calisiyor"}">${yazar ? "Staging dalına yazabilir (onayınızla)" : "Yalnız okur"}</span>
                <span class="soluk kucuk-yazi">${esc(ayar.model || "")}</span>
                <span class="bosluk"></span>
                <button class="btn kucuk" data-eylem="asistan-yeni" data-odoo="${esc(od.id)}" data-ortam="${ortamAd}">Yeni oturum</button>
            </div>
            ${!ayar.sdk ? `<div class="kart-ic">${uyariKutu("kirmizi", "Panel imajında Claude SDK'sı yok; panel güncellenince açılır.")}</div>`
                : !ayar.anahtar_var ? `<div class="kart-ic">${uyariKutu("sari", `Asistan için API anahtarı girilmemiş. Platform yöneticisi <a href="#/baglantilar">Ajan bağlantıları</a> ekranından girer.`)}</div>` : ""}
            <div class="asistan-akis" id="asistan-akis" aria-live="polite"></div>
            <div class="asistan-oneriler">${ASISTAN_ORNEK.map((s) => `<button class="oneri-yazi" data-eylem="asistan-sor" data-metin="${esc(s)}" ${kapali ? "disabled" : ""}>${esc(s)}</button>`).join("")}</div>
            <form class="asistan-giris" data-form="asistan" data-odoo="${esc(od.id)}" data-ortam="${ortamAd}">
                <textarea name="metin" rows="2" placeholder="Bu ortam hakkında sorun ya da iş verin" aria-label="Asistana mesaj" ${kapali ? "disabled" : ""} style="flex:1;resize:vertical"></textarea>
                <button class="btn birincil" type="submit" ${kapali ? "disabled" : ""}>Gönder</button>
            </form>
        </div>
        <aside class="yigin">
            <div class="kart kart-ic" id="asistan-degisiklik"></div>
            <div class="kart kart-ic">
                <h3 style="margin-bottom:.35rem">Sınırlar</h3>
                <ul class="denetim-liste">
                    <li>${ikon("tik", 14, 'class="ic-yesil"')}<span>Bu ortamın durumu, logları, izlemesi, modülleri ve çalışan kodu</span></li>
                    <li>${ikon("tik", 14, 'class="ic-yesil"')}<span>Salt okunur veritabanı sorgusu (şifre, anahtar, jeton sütunları kapalı)</span></li>
                    <li>${ikon("tik", 14, 'class="ic-yesil"')}<span>Kod değişikliği yalnız staging dalına ve sizin onayınızla</span></li>
                    <li>${ikon("hata", 14, 'class="ic-kirmizi"')}<span>Production'a yazamaz; lisanslı modülleri ve <code>odoo.conf</code> dosyasını göremez</span></li>
                </ul>
                <p class="soluk kucuk-yazi uste-az" id="asistan-kullanim"></p>
            </div>
        </aside>
    </div>`, () => asistanCiz(od.id, ortamAd, v)];
};
function asistanCiz(odooId, ortamAd, v) {
    const akis = $("#asistan-akis");
    if (!akis) return;
    const altta = akis.scrollTop + akis.clientHeight >= akis.scrollHeight - 30;
    akis.innerHTML = v.akis.length ? v.akis.map((m) => {
        if (m.tur === "ben") return `<div class="mesaj ben">${esc(m.metin)}</div>`;
        if (m.tur === "adim") return `<div class="adim-satir">${ikon("tik", 12)}<span>${esc(m.metin)}</span></div>`;
        if (m.tur === "hata") return `<div class="mesaj cevap" style="border-color:var(--kirmizi)">${ikon("uyari", 14, 'class="ic-kirmizi"')} ${esc(m.metin)}</div>`;
        return `<div class="mesaj cevap">${mdHtml(m.metin)}</div>`;
    }).join("") + (v.mesgul ? `<div class="adim-satir">${ikon("don", 12, 'class="donen"')}<span>Çalışıyor...</span></div>` : "")
        : `<div class="soluk" style="margin:auto;text-align:center;max-width:46ch">Bu ortamın loglarını, ölçümlerini, kodunu ve veritabanını okuyarak yanıtlar. Aşağıdaki örneklerden birini deneyin ya da yazın.</div>`;
    if (altta || v.mesgul) akis.scrollTop = akis.scrollHeight;
    const kapali = !v.ayar || !v.ayar.anahtar_var || !v.ayar.sdk;
    document.querySelectorAll("form[data-form=asistan] textarea, form[data-form=asistan] button, [data-eylem=asistan-sor]")
        .forEach((el) => { el.disabled = kapali || !!v.mesgul; });
    const kullanim = $("#asistan-kullanim");
    if (kullanim && v.kullanim && v.kullanim.girdi) kullanim.textContent = `Bu oturum: ${sayi(v.kullanim.girdi, 0)} girdi, ${sayi(v.kullanim.cikti, 0)} çıktı belirteci.`;
    const yan = $("#asistan-degisiklik");
    if (yan) {
        const o = v.oneri;
        yan.innerHTML = o ? `<h3>Önerilen değişiklik</h3>
            <p class="kucuk-yazi uste-az"><strong>${esc(o.mesaj || "")}</strong></p>
            ${o.dosyalar.map((d) => `<details class="uste-az"><summary class="kucuk-yazi" style="cursor:pointer"><code class="tasma-kes">${esc(d.yol)}</code>${d.icerik == null ? ` <span class="rozet hata">silinir</span>` : ""}</summary>
                ${d.icerik == null ? "" : `<pre class="kayit" style="max-height:260px">${esc(d.icerik)}</pre>`}</details>`).join("")}
            <p class="soluk kucuk-yazi uste-az">Onaylarsanız staging dalına commit atılır ve staging deploy'u başlar. Production'a dokunulmaz.</p>
            <div class="dugmeler"><button class="btn birincil kucuk" data-eylem="asistan-onay" data-evet="1" data-odoo="${esc(odooId)}" data-ortam="${ortamAd}">Commit at, staging'e gönder</button>
            <button class="btn kucuk" data-eylem="asistan-onay" data-evet="" data-odoo="${esc(odooId)}" data-ortam="${ortamAd}">Vazgeç</button></div>`
            : `<h3>Önerilen değişiklik</h3><p class="soluk kucuk-yazi uste-az">Henüz yok. Asistan kod değişikliği önerirse burada görünür ve sizin onayınızı bekler.</p>`;
    }
    if (v.mesgul) {
        const zaman = setTimeout(async () => {
            if (R.ekran !== "odoo" || R.odoo !== odooId || R.ortam !== ortamAd || R.sekme !== "asistan") return;
            const yeni = await api("GET", `/api/asistan/${encodeURIComponent(odooId)}/${ortamAd}`).catch(() => null);
            if (yeni) asistanCiz(odooId, ortamAd, yeni);
        }, 1200);
        temizleyiciler.push(() => clearTimeout(zaman));
    }
}
async function asistanGonder(odooId, ortamAd, metin) {
    const v = await dene(() => api("POST", `/api/asistan/${encodeURIComponent(odooId)}/${ortamAd}/mesaj`, { metin }), "Asistan");
    if (v) asistanCiz(odooId, ortamAd, v);
    return !!v;
}
FORM.asistan = async (f) => {
    const metin = f.elements.metin.value.trim();
    if (!metin) return;
    if (await asistanGonder(f.dataset.odoo, f.dataset.ortam, metin)) f.elements.metin.value = "";
};
EYLEM["asistan-sor"] = (el) => {
    const f = document.querySelector("form[data-form=asistan]");
    if (f) asistanGonder(f.dataset.odoo, f.dataset.ortam, el.dataset.metin);
};
EYLEM["asistan-yeni"] = async (el) => {
    const v = await dene(() => api("POST", `/api/asistan/${encodeURIComponent(el.dataset.odoo)}/${el.dataset.ortam}/yeni`, {}), "Asistan");
    if (v) asistanCiz(el.dataset.odoo, el.dataset.ortam, v);
};
EYLEM["asistan-onay"] = async (el) => {
    const evet = !!el.dataset.evet;
    const yol = `/api/asistan/${encodeURIComponent(el.dataset.odoo)}/${el.dataset.ortam}`;
    if (evet) await isBaslat(() => api("POST", `${yol}/onay`, { evet: true }), "Asistan değişikliği staging'e");
    else await dene(() => api("POST", `${yol}/onay`, { evet: false }), "Asistan");
    const v = await api("GET", yol).catch(() => null);
    if (v) asistanCiz(el.dataset.odoo, el.dataset.ortam, v);
};

/* ---------- Ajan bağlantıları ---------- */
const BAGLANTI_TUR = { kisisel: "Kişisel jeton", oauth: "OAuth bağlantısı" };
const zamanMs = (sn) => (sn ? sn * 1000 : null);
PLATFORM.baglantilar = async () => {
    const v = await api("GET", "/api/baglantilar");
    const a = v.asistan || {};
    const adres = v.mcp_adresi;
    const codex = `[mcp_servers.odoo_panel]\nurl = "${adres}"\nbearer_token_env_var = "ODOO_PANEL_JETON"`;
    return [`
    <div class="baslik-satiri"><div><p class="ust-etiket">Panel</p><h1>Ajan bağlantıları</h1>
        <p class="soluk">Claude Desktop, claude.ai ve Codex gibi ajanlar panele MCP ile bağlanır. Ajan sizin rolünüz ve erişebildiğiniz platformlarla çalışır; production'a yazamaz, kod değişikliği yalnız staging dalına gider. Her çağrı denetim kaydına yazılır.</p></div></div>
    <div class="yigin" style="max-width:960px">
        <div class="kart kart-ic">
            <h3>Bağlantı adresi</h3>
            <div class="filtre-satir uste-az"><code style="font-size:.95rem">${esc(adres)}</code>
                <button class="btn kucuk" data-eylem="kopyala" data-metin="${esc(adres)}">${ikon("kopya", 13)}Kopyala</button></div>
        </div>
        <div class="izgara-2">
            <div class="kart kart-ic"><h3>Claude Desktop / claude.ai</h3>
                <ol class="kucuk-yazi" style="padding-left:1.1rem;line-height:1.7">
                    <li>Ayarlar &gt; Bağlayıcılar (Connectors) &gt; <strong>Özel bağlayıcı ekle</strong>.</li>
                    <li>Ad: <code>Odoo Yönetim Paneli</code>, adres: yukarıdaki bağlantı adresi.</li>
                    <li><strong>Bağlan</strong>'a basın; panelin onay ekranı açılır. Panel kullanıcı adınızla girip <strong>İzin ver</strong> deyin.</li>
                </ol>
                <p class="soluk kucuk-yazi uste-az">Team ve Enterprise hesaplarında bağlayıcıyı kuruluş yöneticisi ekler; herkes kendi panel hesabıyla onaylar.</p></div>
            <div class="kart kart-ic"><h3>Codex</h3>
                <p class="kucuk-yazi">Aşağıdan kişisel jeton üretin, jetonu <code>ODOO_PANEL_JETON</code> ortam değişkenine koyun ve <code>~/.codex/config.toml</code> dosyasına ekleyin:</p>
                <pre class="kayit uste-az">${esc(codex)}</pre>
                <button class="btn kucuk uste-az" data-eylem="kopyala" data-metin="${esc(codex)}">${ikon("kopya", 13)}Kopyala</button></div>
        </div>
        <form class="kart kart-ic" data-form="jeton-uret">
            <h3>Kişisel jeton üret</h3>
            <p class="soluk kucuk-yazi">Jeton bir kez gösterilir; diskte yalnız özeti tutulur. Bir jeton tek bir ajan ya da bilgisayar için kullanılmalı.</p>
            <div class="form-izgara uste-az">
                <label class="alan">Ad<input name="ad" maxlength="60" required placeholder="ör. Codex, ofis dizüstü" autocomplete="off"></label>
                <label class="alan">Geçerlilik<select name="sure"><option value="30">30 gün</option><option value="90" selected>90 gün</option><option value="365">1 yıl</option><option value="">Süresiz</option></select></label>
            </div>
            <div class="dugmeler"><button class="btn birincil" type="submit">${ikon("anahtar", 14)}Jeton üret</button></div>
        </form>
        <div class="kart tablo-kap"><div class="kart-ic" style="padding-bottom:.25rem"><h3>Bağlantılarım</h3></div>
            <table class="tablo kartli"><thead><tr><th>Ad</th><th>Tür</th><th>Oluşturma</th><th>Son kullanım</th><th>Bitiş</th><th class="sag"></th></tr></thead>
            <tbody>${v.baglantilar.map((b) => `<tr>
                <td class="ana-yazi">${esc(b.ad || "-")}</td><td data-etiket="Tür">${esc(BAGLANTI_TUR[b.tur] || b.tur)}</td>
                <td data-etiket="Oluşturma" class="kirilmaz">${esc(tarihSaat(zamanMs(b.olusturma)))}</td>
                <td data-etiket="Son kullanım" class="kirilmaz">${b.son_kullanim ? esc(goreli(zamanMs(b.son_kullanim))) : "-"}</td>
                <td data-etiket="Bitiş" class="kirilmaz">${b.bitis ? esc(tarihSaat(zamanMs(b.bitis))) : b.tur === "oauth" ? "yenilendikçe" : "süresiz"}</td>
                <td class="sag"><button class="btn kucuk tehlike-cizgi" data-eylem="baglanti-kaldir" data-id="${esc(b.id)}" data-ad="${esc(b.ad || "")}">Kaldır</button></td></tr>`).join("")
                || `<tr><td colspan="6" class="soluk">Henüz bağlantı yok.</td></tr>`}</tbody></table></div>
        <div class="kart kart-ic"><h3>Ajanın kullanabileceği araçlar</h3>
            <p class="soluk kucuk-yazi">Rolünüze göre. Yazan araçları ajan istemcisi çalıştırmadan önce size sorar.</p>
            <div class="filtre-satir uste-az" style="flex-wrap:wrap">${v.araclar.map((x) => `<span class="etiket" title="${esc(x.ad)}">${x.yazar ? ikon("uyari", 11) : ikon("tik", 11)}${esc(x.baslik)}</span>`).join("")}</div></div>
        ${v.asistan_ayar_yetkisi ? `<form class="kart kart-ic" data-form="asistan-ayar">
            <h3>Panel asistanı</h3>
            <p class="soluk kucuk-yazi">Platform sayfalarındaki Asistan sekmesi Claude API ile çalışır; kullanım Anthropic hesabınıza faturalanır. Anahtar sunucuda saklanır, tarayıcıya gönderilmez.</p>
            ${a.sdk ? "" : uyariKutu("kirmizi", "Panel imajında Claude SDK'sı yok; panel güncellenmeli.")}
            <div class="form-izgara uste-az">
                <label class="alan">API anahtarı<input name="anahtar" type="password" autocomplete="off" placeholder="${a.anahtar_var ? `kayıtlı (…${esc(a.anahtar_son)}); değiştirmek için yazın` : "sk-ant-..."}"></label>
                <label class="alan">Model<select name="model">${Object.entries(a.modeller || {}).map(([k, ad]) => `<option value="${esc(k)}" ${a.model === k ? "selected" : ""}>${esc(ad)}</option>`).join("")}</select></label>
                <label class="alan">Effort<select name="effort">${(a.effortlar || []).map((e) => `<option ${a.effort === e ? "selected" : ""}>${esc(e)}</option>`).join("")}</select></label>
            </div>
            <div class="dugmeler"><button class="btn birincil" type="submit">Kaydet</button>
                ${a.anahtar_var ? `<button class="btn tehlike-cizgi" type="button" data-eylem="asistan-anahtar-sil">Anahtarı sil</button>` : ""}</div>
        </form>` : ""}
    </div>`];
};
FORM["jeton-uret"] = async (f) => {
    const sure = f.elements.sure.value;
    const v = await dene(() => api("POST", "/api/baglantilar", { ad: f.elements.ad.value.trim(), sure_gun: sure ? Number(sure) : null }), "Jeton");
    if (!v) return;
    pencereAc("Kişisel jeton", `${uyariKutu("sari", "Jeton yalnız şimdi gösteriliyor. Kopyalayıp güvenli yere koyun; kaybederseniz kaldırıp yenisini üretin.")}
        <pre class="kayit uste-az" style="white-space:pre-wrap;overflow-wrap:anywhere">${esc(v.jeton)}</pre>
        <p class="kucuk-yazi uste-az">PowerShell: <code>setx ODOO_PANEL_JETON "…"</code> · bash: <code>export ODOO_PANEL_JETON=…</code></p>
        <div class="dugmeler"><button class="btn birincil" data-eylem="kopyala" data-metin="${esc(v.jeton)}">${ikon("kopya", 14)}Kopyala</button>
        <button class="btn" data-eylem="is-kapat">Kapat</button></div>`);
};
FORM["asistan-ayar"] = async (f) => {
    const govde = { model: f.elements.model.value, effort: f.elements.effort.value };
    if (f.elements.anahtar.value.trim()) govde.anahtar = f.elements.anahtar.value.trim();
    const v = await dene(() => api("POST", "/api/baglantilar/asistan-ayar", govde), "Asistan ayarı");
    if (v) { bildir("Asistan ayarı kaydedildi."); ciz({ sessiz: true }); }
};
EYLEM["asistan-anahtar-sil"] = () => onayPenceresi({
    baslik: "API anahtarını sil", metin: "Panel asistanı anahtar yeniden girilene kadar çalışmaz. MCP bağlantıları etkilenmez.",
    dugme: "Sil", tehlike: true, tur: "kirmizi",
    evet: async () => { const v = await dene(() => api("POST", "/api/baglantilar/asistan-ayar", { anahtar: "" }), "Asistan ayarı"); pencereKapat(); if (v) ciz({ sessiz: true }); },
});
EYLEM["baglanti-kaldir"] = (el) => onayPenceresi({
    baslik: "Bağlantıyı kaldır", metin: `<strong>${esc(el.dataset.ad || "Bu bağlantı")}</strong> artık panele erişemez.`,
    dugme: "Kaldır", tehlike: true, tur: "kirmizi",
    evet: async () => { const v = await dene(() => api("POST", `/api/baglantilar/${el.dataset.id}/sil`, {}), "Bağlantı"); pencereKapat(); if (v) { bildir("Bağlantı kaldırıldı."); ciz({ sessiz: true }); } },
});
