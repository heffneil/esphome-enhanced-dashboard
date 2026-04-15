# ESPHome Enhanced Dashboard

A drop-in replacement for the stock ESPHome dashboard, designed as an overlay on top of the official Docker image. Gives you a compact, dark-themed table view with search, sortable columns, device tagging, archiving, a sliding side panel for every device action, and an in-page modal for logs, compile, validate, and YAML editing.

The original ESPHome dashboard is preserved and available at `/classic`.

> Pull request tracking upstream adoption: [esphome/esphome#15704](https://github.com/esphome/esphome/pull/15704)

## Features

- **Compact sortable table** — Status, Name, IP Address, Platform, ESPHome Version, Comment, Tags, Config File
- **Live search** across name, friendly name, comment, IP, and config filename
- **Device tags** with a quick-filter pill bar (OR logic across multiple tags)
- **Archive** section with one-click restore
- **Sliding side panel** with every per-device action: Update, Install (Upload OTA), Install (Compile + Upload), Install to Specific Address, Edit, Validate, Compile, Logs, Visit, Show API Key, Clean Build, Clean MQTT, Archive
- **In-page modal** for command output — streaming ANSI-colored logs with DOWNLOAD LOGS button, no popup windows
- **Embedded Ace editor** for YAML editing with syntax highlighting, Ctrl+S save, unsaved-changes warning
- **Install to Specific Address** — upload firmware to an arbitrary IP/hostname with a confirmation dialog
- **Inter webfont** for a clean modern look

## Screenshots

> Add screenshots here once the repo is published.

## Install

You have two installation options. **Both use the official ESPHome Docker image** — we just overlay the modified dashboard files on top. This means the compile toolchains and everything else the official image provides keep working unchanged.

Download the release zip and extract it somewhere persistent on your host, for example:

```bash
mkdir -p /docker/esphome-dashboard-overrides
cd /docker/esphome-dashboard-overrides
curl -LO https://github.com/heffneil/esphome-enhanced-dashboard/releases/latest/download/overrides.zip
unzip overrides.zip
```

After extraction you should have:

```
/docker/esphome-dashboard-overrides/
├── const.py
├── core.py
├── models.py
├── web_server.py
└── templates/
    └── index.template.html
```

### Option 1: `docker run`

```bash
docker run -d \
  --name esphome \
  -p 6052:6052 \
  --restart unless-stopped \
  -v /path/to/your/config:/config \
  -v /docker/esphome-dashboard-overrides/models.py:/esphome/esphome/dashboard/models.py \
  -v /docker/esphome-dashboard-overrides/const.py:/esphome/esphome/dashboard/const.py \
  -v /docker/esphome-dashboard-overrides/web_server.py:/esphome/esphome/dashboard/web_server.py \
  -v /docker/esphome-dashboard-overrides/core.py:/esphome/esphome/dashboard/core.py \
  -v /docker/esphome-dashboard-overrides/templates:/esphome/esphome/dashboard/templates \
  ghcr.io/esphome/esphome
```

Replace `/path/to/your/config` with the directory containing your ESPHome YAML files. If you already run ESPHome in Docker, use the same config path you already have.

### Option 2: `docker compose`

Create or edit your `docker-compose.yml`:

```yaml
services:
  esphome:
    image: ghcr.io/esphome/esphome
    container_name: esphome
    restart: unless-stopped
    ports:
      - "6052:6052"
    volumes:
      - /path/to/your/config:/config
      - /etc/localtime:/etc/localtime:ro

      # Enhanced dashboard overrides
      - /docker/esphome-dashboard-overrides/models.py:/esphome/esphome/dashboard/models.py
      - /docker/esphome-dashboard-overrides/const.py:/esphome/esphome/dashboard/const.py
      - /docker/esphome-dashboard-overrides/web_server.py:/esphome/esphome/dashboard/web_server.py
      - /docker/esphome-dashboard-overrides/core.py:/esphome/esphome/dashboard/core.py
      - /docker/esphome-dashboard-overrides/templates:/esphome/esphome/dashboard/templates
```

Then start it:

```bash
docker compose up -d
```

Open the dashboard at `http://<your-host>:6052/` and you should see the new UI. The original dashboard is still accessible at `http://<your-host>:6052/classic` if you ever need it.

## Upgrading

When a new release is published, download the new `overrides.zip`, extract it over the existing directory, and restart the container:

```bash
cd /docker/esphome-dashboard-overrides
curl -LO https://github.com/heffneil/esphome-enhanced-dashboard/releases/latest/download/overrides.zip
unzip -o overrides.zip

# docker run
docker restart esphome

# docker compose
docker compose restart esphome
```

Because we mount the files in, no image rebuild is needed — a container restart is enough.

## Reverting

Remove the override volume mounts from your `docker run` command or `docker-compose.yml`, then restart. The official image's stock dashboard comes back untouched.

## How the overlay works

The ESPHome Python package is installed inside the container at `/esphome/esphome/`. We volume-mount our replacement files on top of the originals:

| Override file | Mounts over |
|---|---|
| `models.py` | `/esphome/esphome/dashboard/models.py` |
| `const.py` | `/esphome/esphome/dashboard/const.py` |
| `web_server.py` | `/esphome/esphome/dashboard/web_server.py` |
| `core.py` | `/esphome/esphome/dashboard/core.py` |
| `templates/` | `/esphome/esphome/dashboard/templates/` (new directory, holds the new UI) |

On startup, the replaced `web_server.py` points `MainRequestHandler` at `templates/index.template.html` and registers a new `ClassicDashboardHandler` at `/classic` that serves the stock template from the `esphome-dashboard` pip package.

Because the official image is untouched, everything else — PlatformIO, compile toolchains, OTA, mDNS, API auth, Home Assistant ingress — behaves exactly as it does upstream.

## Storage

Tags are stored at `/config/.esphome/.../device-tags.json` inside your config volume. They survive container recreation.

Archived configs move from `/config/` to `/config/archive/` when you archive a device (this behavior is unchanged from stock ESPHome — we only surface the archive folder in the UI).

## Troubleshooting

**Dashboard still looks like the stock one**

- Hard refresh the browser (`Cmd+Shift+R` or `Ctrl+Shift+R`)
- Confirm the container actually restarted after the overrides were added
- Inside the container, check the template is present:
  ```bash
  docker exec esphome ls -la /esphome/esphome/dashboard/templates/
  ```
  You should see `index.template.html`.

**Compile fails with `xtensa-lx106-elf-g++: not found`**

This is unrelated to the overlay — it means your PlatformIO toolchains aren't installed. First compile after a fresh install downloads them automatically; add the PlatformIO cache as a named volume so they persist:

```bash
-v esphome-platformio:/root/.platformio
```

If the toolchain download fails or lands in the wrong place, copy it into ESPHome's expected path:

```bash
docker exec -it esphome cp -r \
  /root/.platformio/packages/toolchain-xtensa \
  /config/.esphome/platformio/packages/toolchain-xtensa
```

**WebSocket keeps reconnecting / `/events` flaps**

Usually a reverse proxy that doesn't forward WebSocket upgrade headers. If you use nginx, make sure you have `proxy_http_version 1.1`, `proxy_set_header Upgrade $http_upgrade`, and `proxy_set_header Connection "upgrade"` on the location block.

## Known limitations

- The **Edit** action opens the stock dashboard's Ace-based editor in a new tab when needed (full YAML edit); inline editing is also available via the embedded Ace editor in a modal. Deep-linking directly into the classic editor is not possible because that UI is an SPA without URL routing.
- The PlatformIO toolchain download still happens on first compile, exactly as on the stock image.
- This is a dashboard overlay only — it doesn't change any device firmware behavior, config schema, or YAML handling.

## License

Same license as upstream ESPHome (see https://github.com/esphome/esphome/blob/dev/LICENSE). The override files here are derivatives of the ESPHome dashboard source, modified for UI enhancements.

## Upstream

Work here tracks [PR esphome/esphome#15704](https://github.com/esphome/esphome/pull/15704). If/when that lands, this repo will mirror whatever release number upstream stamps on it and the overlay becomes unnecessary — you can just `docker pull ghcr.io/esphome/esphome:<version>` and delete the override mounts.
