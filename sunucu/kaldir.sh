#!/usr/bin/env bash
# Odoo Yönetim Paneli'ni durdurur ve Caddy'den çıkarır (geri dönüş).
# Veriye dokunmaz: /opt/odoo-panel (ayarlar, ortam kayıtları, yedekler) yerinde kalır. Panelin açtığı ortam
# konteynerleri (pnl-<ad>) DURDURULMAZ; adresleri Caddy'den çıktığı için dışarıdan erişilemez olur.
# Yeniden kurmak için kur.sh tekrar çalıştırılır.
# Kullanım: bash /opt/odoo-panel/kod/sunucu/kaldir.sh
set -euo pipefail

# ODOO_PANEL_KOK / ODOO_PANEL_KENAR yalnız yerel sınama içindir; sunucuda tanımlanmaz
K=${ODOO_PANEL_KOK:-/opt/odoo-panel}
KENAR=${ODOO_PANEL_KENAR:-/opt/edge}
SUNUCU_ADI=ubuntu-16gb-hel1-1
SATIR="import /etc/caddy/panel.caddy"
ZAMAN=$(date +%Y%m%d%H%M%S)

[ "$(hostname)" = "$SUNUCU_ADI" ] || { echo "HATA: yanlış makine: $(hostname)"; exit 1; }
[ "$(id -u)" = "0" ] || { echo "HATA: root olarak çalıştırın"; exit 1; }

echo "=== 1/3 Caddy"
if grep -qx "$SATIR" "$KENAR/etc/Caddyfile"; then
    cp "$KENAR/etc/Caddyfile" "$KENAR/Caddyfile.$ZAMAN.bak"
    YENI=$(mktemp)
    grep -vx "$SATIR" "$KENAR/etc/Caddyfile" | grep -v '^# Odoo Yönetim Paneli (panel.vekosis.com' > "$YENI"
    install -m 644 "$YENI" "$KENAR/etc/Caddyfile"
    rm -f "$YENI"
    docker exec edge-caddy caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile
    echo "Caddyfile'dan panel satırı çıkarıldı (yedek $KENAR/Caddyfile.$ZAMAN.bak); panel.caddy dosyası duruyor."
else
    echo "Caddyfile'da panel satırı yok."
fi

echo "=== 2/3 Panel konteyneri"
if [ -f "$K/panel/compose.yml" ]; then
    docker compose -f "$K/panel/compose.yml" down 2>&1 | tail -1
else
    echo "Panel compose dosyası yok."
fi

echo "=== 3/3 Ajan"
systemctl disable --now odoo-panel-gece-yedek.timer >/dev/null 2>&1 || true
systemctl disable --now odoo-panel-ajan >/dev/null 2>&1 || true
echo "Ajan ve gece yedeği durduruldu."
echo
echo "Panel durdu. Çalışmaya devam eden ortamlar: $(docker ps --filter name=^pnl- --format '{{.Names}}' | paste -sd, -)"
echo "Veri: $K (silinmedi)."
