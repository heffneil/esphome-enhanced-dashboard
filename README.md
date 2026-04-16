# ESPHome Enhanced Dashboard

A drop-in replacement for the stock ESPHome dashboard. Compact dark-themed table view with search, sortable columns, device tagging, archiving, a sliding side panel for every device action, and in-page modals for logs, compile, validate, and YAML editing.

The original ESPHome dashboard is preserved and available at `/classic`.

**Current base:** ESPHome 2026.4

> Pull request tracking upstream adoption: [esphome/esphome#15704](https://github.com/esphome/esphome/pull/15704)

## Features

- **Compact sortable table** — Status, Name, IP Address, Platform, ESPHome Version, Comment, Tags, Config File
- **Live search** across name, friendly name, comment, IP, and config filename
- **Device tags** with a quick-filter pill bar (OR logic across multiple tags)
- **Mark Inactive** — dims a device, sorts it to the bottom, and stops polling it
- **Archive** section with one-click restore
- **Sliding side panel** with every per-device action: Update, Install (Upload OTA), Install (Compile + Upload), Install to Specific Address, Edit, Validate, Compile, Logs, Visit, Show API Key, Clean Build, Clean MQTT, Mark Inactive, Archive
- **In-page modal** for command output — streaming ANSI-colored logs with DOWNLOAD LOGS button
- **Embedded Ace editor** for YAML editing with syntax highlighting, Ctrl+S save, unsaved-changes warning
- **Install to Specific Address** — upload firmware to an arbitrary IP/hostname with a confirmation dialog
- **Inter webfont** for a clean modern look

## Install

### Option 1: Docker image (recommended)

The easiest way. Just swap your image name — no volume mounts, no file copying, everything is baked in.

**Docker Compose:**

```yaml
services:
  esphome:
    image: heffneil/esphome-enhanced-dashboard:latest
    container_name: esphome
    restart: unless-stopped
    ports:
      - "6052:6052"
    volumes:
      - /path/to/your/config:/config
      - /etc/localtime:/etc/localtime:ro
```

Then:

```bash
docker compose up -d
```

**Docker run:**

```bash
docker run -d \
  --name esphome \
  -p 6052:6052 \
  -v /path/to/your/config:/config \
  --restart unless-stopped \
  heffneil/esphome-enhanced-dashboard:latest
```

Replace `/path/to/your/config` with the directory containing your ESPHome YAML files. That's it.

### Option 2: Volume mount overrides

If you prefer to keep the official ESPHome image and overlay just the dashboard files:

```bash
git clone https://github.com/heffneil/esphome-enhanced-dashboard.git /opt/esphome-dashboard
```

**Docker Compose:**

```yaml
services:
  esphome:
    image: esphome/esphome
    container_name: esphome
    restart: unless-stopped
    ports:
      - "6052:6052"
    volumes:
      - /path/to/your/config:/config
      - /etc/localtime:/etc/localtime:ro
      # Enhanced dashboard overrides
      - /opt/esphome-dashboard/overrides/models.py:/esphome/esphome/dashboard/models.py
      - /opt/esphome-dashboard/overrides/const.py:/esphome/esphome/dashboard/const.py
      - /opt/esphome-dashboard/overrides/web_server.py:/esphome/esphome/dashboard/web_server.py
      - /opt/esphome-dashboard/overrides/core.py:/esphome/esphome/dashboard/core.py
      - /opt/esphome-dashboard/overrides/status/ping.py:/esphome/esphome/dashboard/status/ping.py
      - /opt/esphome-dashboard/overrides/templates:/esphome/esphome/dashboard/templates
```

**Docker run:**

```bash
docker run -d \
  --name esphome \
  -p 6052:6052 \
  --restart unless-stopped \
  -v /path/to/your/config:/config \
  -v /opt/esphome-dashboard/overrides/models.py:/esphome/esphome/dashboard/models.py \
  -v /opt/esphome-dashboard/overrides/const.py:/esphome/esphome/dashboard/const.py \
  -v /opt/esphome-dashboard/overrides/web_server.py:/esphome/esphome/dashboard/web_server.py \
  -v /opt/esphome-dashboard/overrides/core.py:/esphome/esphome/dashboard/core.py \
  -v /opt/esphome-dashboard/overrides/status/ping.py:/esphome/esphome/dashboard/status/ping.py \
  -v /opt/esphome-dashboard/overrides/templates:/esphome/esphome/dashboard/templates \
  esphome/esphome
```

### Option 3: Build from source

```bash
git clone https://github.com/heffneil/esphome-enhanced-dashboard.git
cd esphome-enhanced-dashboard
docker build -t esphome-enhanced-dashboard .
```

Then use `esphome-enhanced-dashboard` as your image name. You can pin the ESPHome version:

```bash
docker build --build-arg BASE_VERSION=2026.2.0 -t esphome-enhanced-dashboard .
```

## Upgrading

**Docker image (Option 1):**

```bash
docker pull heffneil/esphome-enhanced-dashboard:latest
docker compose down && docker compose up -d
# or: docker stop esphome && docker rm esphome && docker run ...
```

**Volume mounts (Option 2):**

```bash
cd /opt/esphome-dashboard
git pull
docker restart esphome
```

**Build from source (Option 3):**

```bash
cd esphome-enhanced-dashboard
git pull
docker build -t esphome-enhanced-dashboard .
docker compose down && docker compose up -d
```

## Reverting

**Docker image:** Change your image back to `esphome/esphome` and restart.

**Volume mounts:** Remove the override volume lines from your compose/run command and restart.

## How it works

The ESPHome Python package is installed inside the container at `/esphome/esphome/`. Our image (or volume mounts) replaces these dashboard files:

| File | What it does |
|---|---|
| `web_server.py` | Routes `/` to the new template, adds `/classic` for the original, adds `/device-tags` and `/toggle-inactive` endpoints |
| `core.py` | Adds device tag and inactive device storage (JSON files in your config dir) |
| `models.py` | Adds `tags`, `inactive`, and `archived` fields to the device API response |
| `const.py` | Adds `entry_archived` / `entry_unarchived` WebSocket events |
| `status/ping.py` | Skips polling inactive devices |
| `templates/index.template.html` | The entire new dashboard UI (self-contained, no build step) |

Everything else — PlatformIO, compile toolchains, OTA, mDNS, API auth, Home Assistant ingress — is unchanged from upstream ESPHome.

## Storage

- **Tags** stored at `<config>/.esphome/device-tags.json`
- **Inactive devices** stored at `<config>/.esphome/inactive-devices.json`
- **Archived configs** move to `<config>/archive/` (unchanged from stock ESPHome)

All data lives in your config volume and survives container recreation.

## Troubleshooting

**Dashboard still looks like the stock one**
- Hard refresh: `Ctrl+Shift+R` (or `Cmd+Shift+R` on Mac)
- Verify the template exists inside the container:
  ```bash
  docker exec esphome ls /esphome/esphome/dashboard/templates/
  ```

**Compile fails with `xtensa-lx106-elf-g++: not found`**

Unrelated to the dashboard — PlatformIO toolchains download on first compile. Add a named volume to persist them:

```bash
-v esphome-platformio:/root/.platformio
```

**WebSocket keeps reconnecting**

Usually a reverse proxy issue. For nginx, ensure:
```nginx
proxy_http_version 1.1;
proxy_set_header Upgrade $http_upgrade;
proxy_set_header Connection "upgrade";
```

## License

Same license as upstream ESPHome. See [LICENSE](https://github.com/esphome/esphome/blob/dev/LICENSE).

## Upstream

Tracks [PR esphome/esphome#15704](https://github.com/esphome/esphome/pull/15704). If accepted upstream, this repo becomes unnecessary — just use the official image.
