#!/usr/bin/env bash
#
# ESPHome Enhanced Dashboard — Proxmox VE LXC installer
#
# Creates a Debian 12 LXC, installs Docker, and runs the
# heffneil/esphome-enhanced-dashboard image with a persistent config volume
# and named PlatformIO cache.
#
# Run on the Proxmox HOST (not inside an existing LXC):
#
#   bash -c "$(curl -fsSL https://raw.githubusercontent.com/heffneil/esphome-enhanced-dashboard/main/script/install-proxmox.sh)"
#
# Set any of these env vars to skip prompts:
#   CT_ID, CT_HOSTNAME, CT_DISK_GB, CT_RAM_MB, CT_CORES, CT_BRIDGE,
#   CT_IP, CT_GATEWAY, CT_STORAGE, CT_PASSWORD, CT_TEMPLATE,
#   IMAGE_TAG (default: latest)

set -euo pipefail

# ---------- pretty output ---------------------------------------------------
GREEN=$'\033[0;32m'; YELLOW=$'\033[1;33m'; RED=$'\033[0;31m'; CYAN=$'\033[0;36m'; NC=$'\033[0m'
say()   { printf "${GREEN}==>${NC} %s\n" "$*"; }
warn()  { printf "${YELLOW}==>${NC} %s\n" "$*"; }
fatal() { printf "${RED}!! %s${NC}\n" "$*" >&2; exit 1; }
ask()   { local q="$1" def="${2-}" ans; read -r -p "$(printf "${CYAN}?${NC} %s%s: " "$q" "${def:+ [$def]}")" ans; printf "%s" "${ans:-$def}"; }

# ---------- preflight -------------------------------------------------------
[[ $EUID -eq 0 ]] || fatal "Must run as root on the Proxmox host."
command -v pct >/dev/null 2>&1 || fatal "'pct' not found. Run this on a Proxmox VE host."
command -v pveam >/dev/null 2>&1 || fatal "'pveam' not found. This isn't a Proxmox VE host."

say "ESPHome Enhanced Dashboard — Proxmox LXC installer"

# ---------- defaults & inputs ----------------------------------------------
NEXT_ID="$(pvesh get /cluster/nextid)"
CT_ID="${CT_ID:-$(ask "Container ID" "$NEXT_ID")}"
CT_HOSTNAME="${CT_HOSTNAME:-$(ask "Hostname" "esphome-enhanced")}"
CT_DISK_GB="${CT_DISK_GB:-$(ask "Disk size (GB)" "16")}"
CT_RAM_MB="${CT_RAM_MB:-$(ask "RAM (MB)" "2048")}"
CT_CORES="${CT_CORES:-$(ask "CPU cores" "2")}"
CT_BRIDGE="${CT_BRIDGE:-$(ask "Network bridge" "vmbr0")}"
CT_IP="${CT_IP:-$(ask "IPv4 (CIDR or 'dhcp')" "dhcp")}"
CT_GATEWAY="${CT_GATEWAY:-}"
if [[ "$CT_IP" != "dhcp" && -z "$CT_GATEWAY" ]]; then
  CT_GATEWAY="$(ask "Gateway IP" "")"
fi
CT_STORAGE="${CT_STORAGE:-$(ask "Storage" "local-lvm")}"
CT_PASSWORD="${CT_PASSWORD:-$(ask "Root password" "esphome")}"
IMAGE_TAG="${IMAGE_TAG:-$(ask "Docker image tag" "latest")}"

# ---------- ensure Debian 12 template is available --------------------------
TEMPLATE_NAME="${CT_TEMPLATE:-debian-12-standard_12.7-1_amd64.tar.zst}"
TEMPLATE_VOLID=""
if pveam list "$CT_STORAGE" 2>/dev/null | grep -q "$TEMPLATE_NAME"; then
  TEMPLATE_VOLID="$CT_STORAGE:vztmpl/$TEMPLATE_NAME"
else
  # Try to find any Debian 12 template on common storages
  for s in local "$CT_STORAGE"; do
    found="$(pveam list "$s" 2>/dev/null | awk '/debian-12-standard/ {print $1; exit}')"
    if [[ -n "$found" ]]; then TEMPLATE_VOLID="$found"; break; fi
  done
fi

if [[ -z "$TEMPLATE_VOLID" ]]; then
  say "Downloading Debian 12 LXC template..."
  pveam update >/dev/null
  AVAIL="$(pveam available --section system | awk '/debian-12-standard/ {print $2}' | sort | tail -1)"
  [[ -n "$AVAIL" ]] || fatal "No Debian 12 template available from pveam."
  pveam download local "$AVAIL"
  TEMPLATE_VOLID="local:vztmpl/$AVAIL"
fi
say "Using template $TEMPLATE_VOLID"

# ---------- create the LXC --------------------------------------------------
NET_OPT="name=eth0,bridge=$CT_BRIDGE,ip=$CT_IP"
[[ "$CT_IP" != "dhcp" ]] && NET_OPT="$NET_OPT,gw=$CT_GATEWAY"

say "Creating LXC $CT_ID ($CT_HOSTNAME)..."
pct create "$CT_ID" "$TEMPLATE_VOLID" \
  --hostname "$CT_HOSTNAME" \
  --cores "$CT_CORES" \
  --memory "$CT_RAM_MB" \
  --rootfs "$CT_STORAGE:$CT_DISK_GB" \
  --net0 "$NET_OPT" \
  --password "$CT_PASSWORD" \
  --features nesting=1 \
  --unprivileged 1 \
  --onboot 1 \
  --start 0

say "Starting LXC..."
pct start "$CT_ID"
sleep 5

# ---------- wait for network ------------------------------------------------
say "Waiting for network..."
tries=0
until pct exec "$CT_ID" -- bash -c "ping -c1 -W2 deb.debian.org >/dev/null 2>&1"; do
  ((tries++))
  if (( tries > 30 )); then fatal "Network never came up inside the LXC."; fi
  sleep 2
done

# ---------- install Docker inside the LXC -----------------------------------
say "Installing Docker inside the LXC..."
pct exec "$CT_ID" -- bash -lc '
  set -e
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq curl ca-certificates gnupg
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/debian/gpg \
    | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg
  . /etc/os-release
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian $VERSION_CODENAME stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -qq
  apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin
  systemctl enable --now docker
'

# ---------- create config dir, compose file, and launch ---------------------
say "Bringing up esphome-enhanced-dashboard:$IMAGE_TAG ..."
pct exec "$CT_ID" -- bash -lc "
  set -e
  mkdir -p /opt/esphome-enhanced/config
  cat > /opt/esphome-enhanced/docker-compose.yml <<'EOF'
services:
  esphome:
    image: heffneil/esphome-enhanced-dashboard:${IMAGE_TAG}
    container_name: esphome
    restart: unless-stopped
    network_mode: host
    privileged: true
    environment:
      - TZ=\$(cat /etc/timezone 2>/dev/null || echo Etc/UTC)
    volumes:
      - /opt/esphome-enhanced/config:/config
      - /etc/localtime:/etc/localtime:ro
      - esphome-platformio:/root/.platformio

volumes:
  esphome-platformio:
EOF
  cd /opt/esphome-enhanced
  docker compose pull
  docker compose up -d
"

# ---------- print access URL ------------------------------------------------
IP_ADDR="$(pct exec "$CT_ID" -- bash -c "hostname -I | awk '{print \$1}'")"
echo
say "Done."
echo
echo "  Container:  ID $CT_ID — '$CT_HOSTNAME'"
echo "  Dashboard:  http://${IP_ADDR}:6052/"
echo "  Configs:    /opt/esphome-enhanced/config (inside the LXC)"
echo
echo "Useful commands (run on the Proxmox host):"
echo "  pct enter $CT_ID                              # shell into the LXC"
echo "  pct exec  $CT_ID -- docker compose -f /opt/esphome-enhanced/docker-compose.yml logs -f"
echo "  pct stop  $CT_ID                              # stop the LXC"
echo "  pct destroy $CT_ID                            # remove (caution: data loss)"
echo
say "Updating to a newer dashboard release later:"
echo "  pct exec $CT_ID -- bash -lc 'cd /opt/esphome-enhanced && docker compose pull && docker compose up -d'"
