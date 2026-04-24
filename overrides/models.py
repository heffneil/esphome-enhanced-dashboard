"""Data models and builders for the dashboard."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from esphome.zeroconf import DiscoveredImport

    from .core import ESPHomeDashboard
    from .entries import DashboardEntry

_LOGGER = logging.getLogger(__name__)

_KNOWN_PLATFORMS = frozenset({
    "esp32", "esp8266", "bk72xx", "rtl87xx", "rp2040", "host",
})

_SUBST_REF_RE = re.compile(r'\$\{(\w+)\}|\$(\w+)')
_ESPHOME_FIELDS = frozenset({"name", "friendly_name", "comment"})


def _resolve_substitutions(value, substitutions: dict) -> str:
    """Replace ${var} and $var references using the substitutions dict."""
    if not isinstance(value, str):
        return value

    def replace(m):
        var_name = m.group(1) or m.group(2)
        return str(substitutions.get(var_name, m.group(0)))

    return _SUBST_REF_RE.sub(replace, value)


def _try_load_with_esphome(config_path: Path):
    """Try ESPHome's loader — works when it does, returns None otherwise."""
    try:
        from esphome import yaml_util
        data = yaml_util.load_yaml(config_path)
        if isinstance(data, dict):
            return data
    except Exception as exc:  # pylint: disable=broad-except
        _LOGGER.debug("load_yaml failed for %s: %r", config_path, exc)
    return None


def _parse_manually(config_path: Path) -> dict:
    """Line-by-line fallback when ESPHome's loader fails (e.g. broken !include path).

    Tracks section context and only picks direct children (same indent as the
    first indented line of the section), so project.name under esphome: is
    not mistaken for esphome.name.
    """
    try:
        lines = config_path.read_text(encoding="utf-8").splitlines()
    except Exception:  # pylint: disable=broad-except
        return {}

    data: dict = {}
    current_section: str | None = None
    section_indent: int = 0
    current_block: dict | None = None

    for line in lines:
        content = line.strip()
        if not content or content.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())

        if indent == 0:
            key = content.split(":", 1)[0].strip()
            if ":" in content:
                if key in _KNOWN_PLATFORMS and "target_platform" not in data:
                    data["target_platform"] = key
                if key in ("substitutions", "esphome"):
                    current_section = key
                    current_block = {}
                    data[key] = current_block
                    section_indent = 0
                else:
                    current_section = None
                    current_block = None
            else:
                current_section = None
                current_block = None
            continue

        if current_block is None:
            continue

        if section_indent == 0:
            section_indent = indent
        if indent != section_indent:
            continue

        m = re.match(r'^([\w-]+)\s*:\s*(.*)', content)
        if not m:
            continue
        key = m.group(1)
        val = m.group(2).strip().strip("\"'")
        val = re.sub(r'\s+#\s.*$', '', val).strip()
        if val:
            current_block[key] = val

    return data


def _merge_packages(data: dict) -> dict:
    """Merge ESPHome `packages:` entries into the root config.

    yaml_util.load_yaml already resolves !include inline, so packages are
    dicts by the time we see them. ESPHome semantics: packages fill in
    defaults, the root config overrides them. So we start with packages
    and layer the root dict on top.
    """
    packages = data.get("packages")
    if not isinstance(packages, dict):
        return data

    merged: dict = {}
    for pkg_data in packages.values():
        if isinstance(pkg_data, dict):
            _deep_merge(merged, pkg_data)

    root_without_packages = {k: v for k, v in data.items() if k != "packages"}
    _deep_merge(merged, root_without_packages)
    return merged


def _deep_merge(target: dict, source: dict) -> None:
    """Recursively merge source into target; source values win on conflict."""
    for key, val in source.items():
        if key in target and isinstance(target[key], dict) and isinstance(val, dict):
            _deep_merge(target[key], val)
        else:
            target[key] = val


def _info_from_yaml(config_path: Path) -> dict:
    """Extract platform / name / friendly_name / comment from a YAML config.

    Uses ESPHome's yaml_util.load_yaml (handles !secret, !include, !lambda),
    merges packages into the root so values defined in included files are
    picked up, then resolves ${var} substitution references. Falls back to
    a line-by-line parser only if the loader raises.
    """
    data = _try_load_with_esphome(config_path)
    if data is not None:
        data = _merge_packages(data)
    else:
        data = _parse_manually(config_path)

    if not isinstance(data, dict):
        return {}

    result: dict[str, str] = {}

    platform = data.get("target_platform")
    if platform:
        result["target_platform"] = platform
    else:
        for key in data:
            if key in _KNOWN_PLATFORMS:
                result["target_platform"] = key
                break

    substitutions = data.get("substitutions") or {}
    if not isinstance(substitutions, dict):
        substitutions = {}

    esphome = data.get("esphome") or {}
    if isinstance(esphome, dict):
        for field in _ESPHOME_FIELDS:
            raw = esphome.get(field)
            if raw is None:
                continue
            resolved = _resolve_substitutions(raw, substitutions)
            if isinstance(resolved, str) and not _SUBST_REF_RE.search(resolved):
                result[field] = resolved.strip()

    _LOGGER.debug("YAML info for %s: %s", config_path, result)
    return result


class ImportableDeviceDict(TypedDict):
    """Dictionary representation of an importable device."""

    name: str
    friendly_name: str | None
    package_import_url: str
    project_name: str
    project_version: str
    network: str
    ignored: bool


class ConfiguredDeviceDict(TypedDict, total=False):
    """Dictionary representation of a configured device."""

    name: str
    friendly_name: str | None
    configuration: str
    loaded_integrations: list[str] | None
    deployed_version: str | None
    current_version: str | None
    path: str
    comment: str | None
    address: str | None
    web_port: int | None
    target_platform: str | None
    tags: list[str]
    inactive: bool


class ArchivedDeviceDict(TypedDict, total=False):
    """Dictionary representation of an archived device."""

    name: str
    friendly_name: str | None
    configuration: str
    comment: str | None
    address: str | None
    target_platform: str | None
    tags: list[str]


class DeviceListResponse(TypedDict):
    """Response for device list API."""

    configured: list[ConfiguredDeviceDict]
    importable: list[ImportableDeviceDict]
    archived: list[ArchivedDeviceDict]


def build_importable_device_dict(
    dashboard: ESPHomeDashboard, discovered: DiscoveredImport
) -> ImportableDeviceDict:
    """Build the importable device dictionary."""
    return ImportableDeviceDict(
        name=discovered.device_name,
        friendly_name=discovered.friendly_name,
        package_import_url=discovered.package_import_url,
        project_name=discovered.project_name,
        project_version=discovered.project_version,
        network=discovered.network,
        ignored=discovered.device_name in dashboard.ignored_devices,
    )


def build_archived_device_list(
    tags: dict[str, list[str]] | None = None,
) -> list[ArchivedDeviceDict]:
    """Scan the archive directory and build a list of archived devices."""
    from esphome.storage_json import StorageJSON, archive_storage_path, ext_storage_path

    if tags is None:
        tags = {}

    try:
        archive_path = archive_storage_path()
        if not archive_path.is_dir():
            return []
    except Exception:  # pylint: disable=broad-except
        return []

    archived: list[ArchivedDeviceDict] = []
    for path in sorted(archive_path.iterdir()):
        if path.suffix not in (".yaml", ".yml"):
            continue
        filename = path.name
        storage = StorageJSON.load(ext_storage_path(filename))
        if storage is not None:
            archived.append(
                ArchivedDeviceDict(
                    name=storage.name,
                    friendly_name=storage.friendly_name,
                    configuration=filename,
                    comment=storage.comment,
                    address=storage.address,
                    target_platform=storage.target_platform,
                    tags=tags.get(filename, []),
                )
            )
        else:
            yaml_info = _info_from_yaml(path)
            name = yaml_info.get("friendly_name") or Path(filename).stem.replace("-", " ").replace("_", " ")
            archived.append(
                ArchivedDeviceDict(
                    name=name,
                    friendly_name=yaml_info.get("friendly_name"),
                    configuration=filename,
                    comment=yaml_info.get("comment"),
                    address=None,
                    target_platform=yaml_info.get("target_platform"),
                    tags=tags.get(filename, []),
                )
            )
    return archived


def build_device_list_response(
    dashboard: ESPHomeDashboard, entries: list[DashboardEntry]
) -> DeviceListResponse:
    """Build the device list response data."""
    configured_names = {entry.name for entry in entries}
    try:
        tags = dashboard.device_tags
    except Exception:  # pylint: disable=broad-except
        tags = {}
    try:
        inactive = dashboard.inactive_devices
    except Exception:  # pylint: disable=broad-except
        inactive = set()
    configured = []
    for entry in entries:
        d = dict(entry.to_dict())
        d["tags"] = tags.get(entry.filename, [])
        d["inactive"] = entry.filename in inactive
        stem = Path(entry.filename).stem
        try:
            config_path = Path(dashboard.settings.rel_path(entry.filename))
            if config_path.exists():
                yaml_info = _info_from_yaml(config_path)
                # Name + friendly_name from entry.to_dict() default to the
                # filename stem; always prefer YAML when present, and
                # replace a stem-equal friendly_name too.
                if "name" in yaml_info:
                    d["name"] = yaml_info["name"]
                if "friendly_name" in yaml_info and (
                    not d.get("friendly_name") or d.get("friendly_name") == stem
                ):
                    d["friendly_name"] = yaml_info["friendly_name"]
                for key in ("target_platform", "comment"):
                    if not d.get(key) and yaml_info.get(key):
                        d[key] = yaml_info[key]
        except Exception:  # pylint: disable=broad-except
            pass
        configured.append(d)
    try:
        archived = build_archived_device_list(tags)
    except Exception:  # pylint: disable=broad-except
        _LOGGER.exception("Failed to build archived device list")
        archived = []
    return DeviceListResponse(
        configured=configured,
        importable=[
            build_importable_device_dict(dashboard, res)
            for res in dashboard.import_result.values()
            if res.device_name not in configured_names
        ],
        archived=archived,
    )
