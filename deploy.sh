#!/usr/bin/env bash
# 部署 / 更新 ashencrown.ya1om.com（在本机 Git Bash 里运行：bash deploy.sh）
# 首次部署会自动安装 nginx 站点配置并申请 certbot 证书；之后只同步 index.html、src/、assets/。
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
KEY="$HOME/.ssh/qqbot_ed25519"
HOST="ubuntu@43.128.44.184"
WEBROOT="/var/www/ashencrown"
DOMAIN="ashencrown.ya1om.com"
SITE="ashencrown"

cd "$HERE"
TAR="$(mktemp -t ashen-XXXX).tar.gz"
tar -czf "$TAR" index.html src assets
scp -i "$KEY" "$TAR" deploy/nginx-ashencrown.conf "$HOST:/tmp/"
ssh -i "$KEY" "$HOST" bash -s <<REMOTE
set -e
sudo mkdir -p $WEBROOT && sudo chown -R ubuntu:ubuntu $WEBROOT
rm -rf $WEBROOT/.next && mkdir -p $WEBROOT/.next
tar -xzf /tmp/$(basename "$TAR") -C $WEBROOT/.next && rm -f /tmp/$(basename "$TAR")
# 整体替换，避免玩家读到新旧混杂的文件
for d in index.html src assets; do
  rm -rf $WEBROOT/\$d.old
  if [ -e $WEBROOT/\$d ]; then mv $WEBROOT/\$d $WEBROOT/\$d.old; fi
  mv $WEBROOT/.next/\$d $WEBROOT/\$d
  rm -rf $WEBROOT/\$d.old
done
rmdir $WEBROOT/.next
if [ ! -f /etc/nginx/sites-available/$SITE ]; then
  sudo mv /tmp/nginx-ashencrown.conf /etc/nginx/sites-available/$SITE
  sudo ln -sf /etc/nginx/sites-available/$SITE /etc/nginx/sites-enabled/$SITE
  sudo nginx -t && sudo systemctl reload nginx
  sudo certbot --nginx -d $DOMAIN --non-interactive --agree-tos --register-unsafely-without-email --redirect
else
  rm -f /tmp/nginx-ashencrown.conf
fi
echo "deployed: \$(du -sh $WEBROOT | cut -f1), \$(find $WEBROOT -type f | wc -l) files"
REMOTE
rm -f "$TAR"
echo "done -> https://$DOMAIN/"
