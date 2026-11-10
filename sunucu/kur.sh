#!/usr/bin/env bash
# Odoo Yönetim Paneli kurulumu ve güncellemesi. Tekrar çalıştırmak güvenlidir: var olan ayar, kullanıcı ve
# ortamlara dokunmaz, yalnız kodu ve hizmetleri yeniler.
#   1/7 ön denetim
#   2/7 kod          -> /opt/odoo-panel/surumler/<sürüm>; /opt/odoo-panel/kod bu sürümü gösterir
#   3/7 ayarlar      -> /opt/odoo-panel/ayar: ajan.env, ajan anahtarı, webhook sırrı, github.com host anahtarı
#   4/7 ajan         -> systemd odoo-panel-ajan (vtest ağ geçidi:8098) + gece yedeği zamanlayıcısı (04:20)
#   5/7 panel        -> pnl-panel konteyneri (root yetkisi yok, salt okunur dosya sistemi)
#   6/7 Caddy        -> /opt/edge/etc/panel.caddy + Caddyfile'a tek "import" satırı. Önce yedek ve doğrulama;
#                       erp.vekosis.com, test.vekosis.com ve musteri.test.vekosis.com önceki gibi yanıt vermezse
#                       eski Caddyfile geri konur. DNS'te panel.vekosis.com yoksa bu adım atlanır.
#   7/7 ilk kullanıcı ve son denetim
# Eski test paneli (vtest-panel, vtest-ajan), test ortamları ve ERP yeniden başlatılmaz.
# Geri dönüş: bash /opt/odoo-panel/kod/sunucu/kaldir.sh
# Kullanım : bash /opt/odoo-panel/paket/<sürüm>/odoo-panel/sunucu/kur.sh
set -euo pipefail

P=$(cd "$(dirname "$0")/.." && pwd)
# ODOO_PANEL_KOK / ODOO_PANEL_KENAR yalnız yerel sınama içindir; sunucuda tanımlanmaz
K=${ODOO_PANEL_KOK:-/opt/odoo-panel}
SUNUCU_ADI=ubuntu-16gb-hel1-1
AG=vtest
PORT=8098
ALAN=panel.vekosis.com
KENAR=${ODOO_PANEL_KENAR:-/opt/edge}
SYSTEMD=${ODOO_PANEL_SYSTEMD:-/etc/systemd/system}
GITHUB_ED25519="SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU"
SURUM=$(tr -c 'a-z0-9._\n-' '-' < "$P/SURUM" 2>/dev/null | head -1 || true)
[ -n "$SURUM" ] || SURUM=yerel-$(date +%Y%m%d%H%M%S)
ZAMAN=$(date +%Y%m%d%H%M%S)
PANEL_IMAJ="pnl/panel:$SURUM"

adim() { echo; echo "=== $1 ($(date '+%H:%M:%S'))"; }
hata() { echo "HATA: $*" >&2; exit 1; }
ajan_cagir() { (cd "$K/kod" && set -a && . "$K/ayar/ajan.env" && set +a && python3 -m ajan "$@"); }
# Adresin HTTPS yanıt kodu (sunucunun kendisinden, Caddy üzerinden)
https_kod() { curl -s -o /dev/null -w '%{http_code}' --max-time 20 --resolve "$1:443:127.0.0.1" "https://$1$2" || true; }
dns_bu_sunucu() {
    local ip
    ip=$(getent ahostsv4 "$1" 2>/dev/null | awk 'NR==1 {print $1}')
    [ -n "$ip" ] && hostname -I | tr ' ' '\n' | grep -qx "$ip"
}

adim "1/7 Ön denetim (sürüm $SURUM)"
[ "$(hostname)" = "$SUNUCU_ADI" ] || hata "yanlış makine: $(hostname) (bu betik yalnız $SUNUCU_ADI için)"
[ "$(id -u)" = "0" ] || hata "root olarak çalıştırın"
for KOMUT in docker python3 openssl ssh-keygen ssh-keyscan curl git getent; do
    command -v "$KOMUT" >/dev/null 2>&1 || hata "$KOMUT bulunamadı"
done
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' || hata "Python 3.12 ya da yenisi gerekli"
docker compose version >/dev/null 2>&1 || hata "docker compose eklentisi yok"
docker network inspect "$AG" >/dev/null 2>&1 || hata "$AG ağı yok (test platformu kurulu mu?)"
for KONTEYNER in vtest-postgres edge-caddy; do
    [ "$(docker inspect -f '{{.State.Running}}' "$KONTEYNER" 2>/dev/null || true)" = "true" ] || hata "$KONTEYNER çalışmıyor"
done
[ -f "$KENAR/etc/Caddyfile" ] || hata "$KENAR/etc/Caddyfile yok"
for PARCA in ajan/__main__.py panel/panel.py panel/static/index.html sunucu/Caddyfile.panel; do
    [ -f "$P/$PARCA" ] || hata "pakette $PARCA yok"
done
echo "Tamam: $(docker --version | cut -d, -f1), $(python3 --version), $(git --version)"

adim "2/7 Kod"
mkdir -p "$K/surumler"
H="$K/surumler/$SURUM"
rm -rf "$H.yeni"
mkdir -p "$H.yeni"
cp -a "$P/ajan" "$P/panel" "$P/sunucu" "$H.yeni/"
cp "$P/SURUM" "$H.yeni/SURUM" 2>/dev/null || echo "$SURUM" > "$H.yeni/SURUM"
(cd "$H.yeni" && PYTHONDONTWRITEBYTECODE=1 python3 -c "import ajan.servis, ajan.sunucu, panel.yetki") \
    || hata "kod Python $(python3 --version) ile yüklenemedi"
chmod -R u=rwX,go=rX "$H.yeni"
rm -rf "$H"
mv "$H.yeni" "$H"
ONCEKI=""
[ -L "$K/kod" ] && ONCEKI=$(readlink -f "$K/kod")
[ -e "$K/kod" ] && [ ! -L "$K/kod" ] && hata "$K/kod bir klasör; bağlantı olmalı, elle bakın"
ln -sfn "$H" "$K/kod"
echo "Kod: $K/kod -> $H${ONCEKI:+ (önceki: $ONCEKI)}"

adim "3/7 Ayarlar"
for D in ayar ayar/anahtarlar odoolar depolar yedekler isler gecici onbellek silinenler panel panel/veri; do
    mkdir -p "$K/$D"
done
chmod 700 "$K/ayar" "$K/ayar/anahtarlar" "$K/yedekler" "$K/isler" "$K/gecici" "$K/silinenler"
[ -s "$K/ayar/ajan_anahtari" ] || (umask 077; openssl rand -hex 32 > "$K/ayar/ajan_anahtari")
[ -s "$K/ayar/webhook_sirri" ] || (umask 077; openssl rand -hex 32 > "$K/ayar/webhook_sirri")
chmod 600 "$K/ayar/ajan_anahtari" "$K/ayar/webhook_sirri"
GW=$(docker network inspect "$AG" -f '{{range .IPAM.Config}}{{.Gateway}}{{end}}')
SUBNET=$(docker network inspect "$AG" -f '{{range .IPAM.Config}}{{.Subnet}}{{end}}')
if [ -z "$GW" ]; then
    KOPRU="br-$(docker network inspect "$AG" -f '{{.Id}}' | cut -c1-12)"
    GW=$(ip -4 -o addr show "$KOPRU" | awk '{print $4}' | cut -d/ -f1)
fi
{ [ -n "$GW" ] && [ -n "$SUBNET" ]; } || hata "$AG ağının adresi bulunamadı"
(umask 077; cat > "$K/ayar/ajan.env" <<ENV
PANEL_KOK=$K
PANEL_ALAN=$ALAN
PANEL_AG=$AG
PANEL_PG=vtest-postgres
PANEL_KENAR_TENANTS=$KENAR/etc/tenants
PANEL_VTEST_KOK=/opt/vekosis-test
AJAN_ADRES=$GW
AJAN_PORT=$PORT
AJAN_IZINLI=pnl-panel
ENV
)
if [ ! -s "$K/ayar/known_hosts" ]; then
    GECICI=$(mktemp)
    ssh-keyscan -t ed25519 github.com 2>/dev/null > "$GECICI" || true
    PARMAK=$(ssh-keygen -lf "$GECICI" 2>/dev/null | awk '{print $2}')
    if [ "$PARMAK" = "$GITHUB_ED25519" ]; then
        install -m 644 "$GECICI" "$K/ayar/known_hosts"
        echo "github.com host anahtarı doğrulandı ($PARMAK)."
    else
        echo "UYARI: github.com host anahtarı doğrulanamadı (${PARMAK:-alınamadı}); deploy key ile bağlı depolar çekilemez."
    fi
    rm -f "$GECICI"
fi
if [ -s "$K/ayar/github_app.json" ]; then echo "GitHub App bilgisi var."; else echo "GitHub App bilgisi yok: deploy key ya da herkese açık depo kullanılabilir; zip yüklemesi ve PR için App gerekir."; fi
echo "Ajan adresi: $GW:$PORT (ağ $SUBNET)"

adim "4/7 Ajan hizmeti"
install -m 644 "$H/sunucu/odoo-panel-ajan.service" "$SYSTEMD/odoo-panel-ajan.service"
install -m 644 "$H/sunucu/odoo-panel-gece-yedek.service" "$SYSTEMD/odoo-panel-gece-yedek.service"
install -m 644 "$H/sunucu/odoo-panel-gece-yedek.timer" "$SYSTEMD/odoo-panel-gece-yedek.timer"
systemctl daemon-reload
systemctl enable odoo-panel-ajan >/dev/null 2>&1
systemctl restart odoo-panel-ajan
if command -v ufw >/dev/null 2>&1 && ufw status | grep -q "Status: active"; then
    ufw allow from "$SUBNET" to "$GW" port "$PORT" proto tcp comment "Odoo Yonetim Paneli ajani - yalniz Docker ici" >/dev/null
fi
HAZIR=0
for _ in $(seq 1 15); do
    if ajan_cagir saglik >/dev/null 2>&1; then HAZIR=1; break; fi
    sleep 1
done
if [ "$HAZIR" != "1" ]; then
    journalctl -u odoo-panel-ajan -n 30 --no-pager
    hata "ajan yanıt vermedi"
fi
systemctl enable --now odoo-panel-gece-yedek.timer >/dev/null 2>&1
echo "Ajan çalışıyor; sonraki gece yedeği: $(systemctl show odoo-panel-gece-yedek.timer -p NextElapseUSecRealtime --value)"

adim "5/7 Panel konteyneri"
chown 10001:10001 "$K/panel/veri"
chmod 700 "$K/panel/veri"
(umask 077; printf 'AJAN_URL=http://%s:%s\nAJAN_ANAHTAR=%s\n' "$GW" "$PORT" "$(cat "$K/ayar/ajan_anahtari")" > "$K/panel/panel.env")
if ! docker build -t "$PANEL_IMAJ" "$H/panel" > "$K/panel/imaj-$ZAMAN.log" 2>&1; then
    tail -20 "$K/panel/imaj-$ZAMAN.log"
    hata "panel imajı oluşturulamadı (kayıt: $K/panel/imaj-$ZAMAN.log)"
fi
cat > "$K/panel/compose.yml" <<YML
# Odoo Yönetim Paneli web konteyneri ($K/kod/sunucu/kur.sh üretir)
name: pnl-panel
services:
  panel:
    image: $PANEL_IMAJ
    container_name: pnl-panel
    restart: unless-stopped
    env_file: $K/panel/panel.env
    volumes:
      - $K/panel/veri:/veri
    read_only: true
    tmpfs: [/tmp]
    cap_drop: [ALL]
    security_opt: [no-new-privileges:true]
    mem_limit: 256m
    networks: [$AG]
networks:
  $AG:
    external: true
YML
docker compose -f "$K/panel/compose.yml" up -d --force-recreate 2>&1 | tail -1
HAZIR=0
for _ in $(seq 1 20); do
    if docker exec pnl-panel python -c "import urllib.request;urllib.request.urlopen('http://localhost:8080/')" >/dev/null 2>&1; then HAZIR=1; break; fi
    sleep 1
done
[ "$HAZIR" = "1" ] || { docker logs --tail 20 pnl-panel; hata "panel açılmadı"; }
docker exec pnl-panel python -c "import os,json,urllib.request as u;r=u.Request(os.environ['AJAN_URL']+'/saglik',headers={'X-Ajan-Anahtar':os.environ['AJAN_ANAHTAR']});d=json.load(u.urlopen(r,timeout=10));print('Panel -> ajan:',d['durum'],d['surum'],d['alan'])" \
    || hata "panel ajana ulaşamıyor"

adim "6/7 Caddy"
if ! dns_bu_sunucu "$ALAN"; then
    echo "ATLANDI: DNS'te $ALAN bu sunucuyu göstermiyor. DNS'e 'panel' ve '*.panel' A kayıtlarını ekleyip kur.sh'i tekrar çalıştırın."
    CADDY=atlandi
else
    if ! dns_bu_sunucu "dns-denetimi.$ALAN"; then
        echo "UYARI: *.$ALAN DNS kaydı yok; panel açılır ama panelin kuracağı ortamların adresi çalışmaz."
    fi
    declare -A ONCE
    SITELER=("erp.vekosis.com /web/login" "test.vekosis.com /" "musteri.test.vekosis.com /web/login")
    for S in "${SITELER[@]}"; do set -- $S; ONCE[$1]=$(https_kod "$1" "$2"); done
    KAYNAK="$H/sunucu/Caddyfile.panel"
    SATIR="import /etc/caddy/panel.caddy"
    DENEME=$(mktemp -d)
    cp -a "$KENAR/etc/." "$DENEME/"
    install -m 644 "$KAYNAK" "$DENEME/panel.caddy"
    if ! grep -qx "$SATIR" "$DENEME/Caddyfile"; then
        printf '\n# Odoo Yönetim Paneli (panel.vekosis.com ve *.panel.vekosis.com); /opt/odoo-panel/kod/sunucu/kur.sh ekler\n%s\n' "$SATIR" >> "$DENEME/Caddyfile"
    fi
    CADDY_IMAJ=$(docker inspect -f '{{.Config.Image}}' edge-caddy)
    if ! docker run --rm -v "$DENEME:/etc/caddy:ro" "$CADDY_IMAJ" caddy validate --config /etc/caddy/Caddyfile \
            --adapter caddyfile > "$K/panel/caddy-dogrula-$ZAMAN.log" 2>&1; then
        tail -15 "$K/panel/caddy-dogrula-$ZAMAN.log"
        rm -rf "$DENEME"
        hata "yeni Caddy yapılandırması geçersiz; Caddy'ye dokunulmadı"
    fi
    cp "$KENAR/etc/Caddyfile" "$KENAR/Caddyfile.$ZAMAN.bak"
    [ -f "$KENAR/etc/panel.caddy" ] && cp "$KENAR/etc/panel.caddy" "$KENAR/panel.caddy.$ZAMAN.bak"
    install -m 644 "$DENEME/panel.caddy" "$KENAR/etc/panel.caddy"
    install -m 644 "$DENEME/Caddyfile" "$KENAR/etc/Caddyfile"
    rm -rf "$DENEME"
    docker exec edge-caddy caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile
    sleep 3
    BOZUK=""
    for S in "${SITELER[@]}"; do
        set -- $S
        SONRA=$(https_kod "$1" "$2")
        echo "$1: önce ${ONCE[$1]}, sonra $SONRA"
        if [ "${ONCE[$1]}" = "200" ] && [ "$SONRA" != "200" ]; then BOZUK="$BOZUK $1"; fi
    done
    if [ -n "$BOZUK" ]; then
        echo "Bozulan adres:$BOZUK - eski Caddyfile geri konuyor."
        cp "$KENAR/Caddyfile.$ZAMAN.bak" "$KENAR/etc/Caddyfile"
        if [ -f "$KENAR/panel.caddy.$ZAMAN.bak" ]; then cp "$KENAR/panel.caddy.$ZAMAN.bak" "$KENAR/etc/panel.caddy"; else rm -f "$KENAR/etc/panel.caddy"; fi
        docker exec edge-caddy caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile
        hata "Caddy değişikliği geri alındı; panel konteyneri ve ajan çalışıyor ama dışarıdan erişilemez"
    fi
    echo "Caddy yeniden yüklendi; yedek $KENAR/Caddyfile.$ZAMAN.bak"
    CADDY=tamam
fi

adim "7/7 İlk kullanıcı ve son denetim"
if [ ! -s "$K/panel/veri/kullanicilar.json" ]; then
    (umask 077; docker exec pnl-panel python -m panel kullanici-ekle vekosis > "$K/panel/ILK-KULLANICI.txt")
    echo "İlk kullanıcı: vekosis (platform yöneticisi). Şifre: cat $K/panel/ILK-KULLANICI.txt"
else
    echo "Panel kullanıcıları: $(docker exec pnl-panel python -m panel kullanicilar | awk '{print $1}' | paste -sd, -)"
fi
echo "Çalışan pnl- konteynerleri: $(docker ps --filter name=^pnl- --format '{{.Names}}' | paste -sd, -)"
if [ "$CADDY" = "tamam" ]; then
    PANEL_KOD=000
    for _ in $(seq 1 12); do
        PANEL_KOD=$(https_kod "$ALAN" "/")
        [ "$PANEL_KOD" = "200" ] && break
        sleep 5
    done
    echo "https://$ALAN: $PANEL_KOD"
    [ "$PANEL_KOD" = "200" ] || echo "Not: sertifika birkaç dakika içinde alınır; sonra 'docker restart edge-caddy' gerekmez, Caddy kendisi yeniden dener."
fi
echo
echo "=== ODOO YÖNETİM PANELİ KURULDU: sürüm $SURUM ==="
echo "Adres          : https://$ALAN"
echo "Webhook sırrı  : $K/ayar/webhook_sirri (GitHub > depo > Settings > Webhooks; adres https://$ALAN/webhook/github, application/json)"
echo "Geri dönüş     : bash $K/kod/sunucu/kaldir.sh"
