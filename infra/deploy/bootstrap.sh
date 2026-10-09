#!/usr/bin/env bash
# One-time preparation of a fresh Ubuntu VM (tested layout: Timeweb Cloud, Ubuntu 22.04/24.04).
# Run as root ONCE, from your computer:
#
#   scp infra/deploy/bootstrap.sh root@<VM_IP>:/root/
#   ssh root@<VM_IP> 'bash /root/bootstrap.sh "<contents of deploy_key.pub>"'
#
# It installs Docker with Compose, configures a Docker Hub mirror (Docker Hub throttles Russian IPs),
# creates the unprivileged `deploy` user that GitHub Actions logs in as, creates /opt/kainem,
# and opens only ports 22, 80 and 443. It does not touch sshd settings.
set -euo pipefail

PUBKEY="${1:?usage: bootstrap.sh '<ssh public key for the deploy user>'}"
DEPLOY_USER="${DEPLOY_USER:-deploy}"
DEPLOY_PATH="${DEPLOY_PATH:-/opt/kainem}"

[ "$(id -u)" -eq 0 ] || { echo "run as root" >&2; exit 1; }

echo "==> Packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
# Ubuntu's own Docker packages: reachable from Russian networks, unlike download.docker.com at times.
apt-get install -y -q ca-certificates curl rsync ufw docker.io docker-compose-v2 docker-buildx

echo "==> Docker daemon: registry mirrors and log rotation"
mkdir -p /etc/docker
if [ ! -f /etc/docker/daemon.json ]; then
  cat > /etc/docker/daemon.json <<'JSON'
{
  "registry-mirrors": ["https://dockerhub.timeweb.cloud", "https://mirror.gcr.io"],
  "log-driver": "json-file",
  "log-opts": { "max-size": "20m", "max-file": "5" }
}
JSON
else
  echo "/etc/docker/daemon.json exists; leaving it alone"
fi
systemctl enable --now docker
systemctl restart docker

echo "==> Deploy user $DEPLOY_USER"
if ! id "$DEPLOY_USER" > /dev/null 2>&1; then
  useradd --create-home --shell /bin/bash "$DEPLOY_USER"
fi
usermod -aG docker "$DEPLOY_USER"
install -d -m 700 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "/home/$DEPLOY_USER/.ssh"
touch "/home/$DEPLOY_USER/.ssh/authorized_keys"
grep -qxF "$PUBKEY" "/home/$DEPLOY_USER/.ssh/authorized_keys" || echo "$PUBKEY" >> "/home/$DEPLOY_USER/.ssh/authorized_keys"
chmod 600 "/home/$DEPLOY_USER/.ssh/authorized_keys"
chown -R "$DEPLOY_USER:$DEPLOY_USER" "/home/$DEPLOY_USER/.ssh"

echo "==> Application directory $DEPLOY_PATH"
install -d -m 750 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "$DEPLOY_PATH"

echo "==> Firewall: 22, 80, 443 only"
ufw allow OpenSSH > /dev/null
ufw allow 80/tcp > /dev/null
ufw allow 443/tcp > /dev/null
ufw --force enable > /dev/null
ufw status

echo "==> Checks"
docker compose version
sudo -u "$DEPLOY_USER" docker info > /dev/null && echo "$DEPLOY_USER can use docker"

cat <<EOF

Done. Next (docs/deployment.md §5):
  1. Point your domain's A record at this VM's IP.
  2. In GitHub → Settings → Environments → production, set:
       variable DEPLOY_HOST   = $(hostname -I | awk '{print $1}')
       variable DEPLOY_USER   = $DEPLOY_USER        (optional, this is the default)
       variable DEPLOY_PATH   = $DEPLOY_PATH   (optional, this is the default)
       variable DEPLOY_KNOWN_HOSTS = output of: ssh-keyscan $(hostname -I | awk '{print $1}')
       secret   DEPLOY_SSH_KEY = the private key matching the public key you passed in
       secret   PROD_ENV_FILE  = contents of infra/.env.prod (template: infra/.env.prod.example)
  3. Run the "Deploy" workflow (Actions → Deploy → Run workflow).
EOF
