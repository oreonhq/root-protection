import os
import copy
from typing import Any, Dict

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore

from .util import RpError, ensure_dir

DEFAULT_CONFIG_PATH = "/etc/root-protection/config.toml"
DEFAULTS: Dict[str, Any] = {
    "general": {
        "enabled": False,
        "snapper_config": "root",
        "boot_sync": True,
        "boot_snapshot": False,
    },
    "retention": {
        "number_limit": 10,
        "number_limit_important": 5,
        "timeline_limit_hourly": 0,
        "timeline_limit_daily": 7,
        "timeline_limit_weekly": 2,
        "timeline_limit_monthly": 1,
        "timeline_limit_yearly": 0,
        "empty_pre_post_cleanup": True,
    },
    "health": {
        "warn_data_percent": 70,
        "crit_data_percent": 85,
        "warn_meta_percent": 70,
        "crit_meta_percent": 85,
        "refuse_create_on_crit": True,
        "wall_on_crit": True,
    },
    "guard": {
        "enabled": True,
        "interactive_only": True,
        "require_confirm": True,
        "allow_force_env": True,
        "log_path": "/var/log/root-protection/guard.log",
    },
    "dnf": {
        "pre_post_snapshots": True,
        "sync_boot_after": True,
    },
}


def _deep_merge(base: dict, overlay: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in overlay.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _toml_escape(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, str):
        return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'
    raise TypeError(type(v))


def dump_toml(cfg: dict) -> str:
    lines = ["# root-protection config", ""]
    for section, values in cfg.items():
        lines.append(f"[{section}]")
        for k, v in values.items():
            lines.append(f"{k} = {_toml_escape(v)}")
        lines.append("")
    return "\n".join(lines)


class Config:
    def __init__(self, path: str = DEFAULT_CONFIG_PATH, data: dict | None = None):
        self.path = path
        self.data = data if data is not None else copy.deepcopy(DEFAULTS)

    @classmethod
    def load(cls, path: str = DEFAULT_CONFIG_PATH) -> "Config":
        if not os.path.exists(path):
            return cls(path=path)
        with open(path, "rb") as f:
            parsed = tomllib.load(f)
        return cls(path=path, data=_deep_merge(DEFAULTS, parsed))

    def save(self) -> None:
        ensure_dir(os.path.dirname(self.path))
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(dump_toml(self.data))
        os.chmod(self.path, 0o644)

    def get(self, section: str, key: str, default: Any = None) -> Any:
        return self.data.get(section, {}).get(key, default)

    def set(self, section: str, key: str, value: Any) -> None:
        if section not in self.data:
            self.data[section] = {}
        self.data[section][key] = value

    @property
    def enabled(self) -> bool:
        return bool(self.get("general", "enabled", False))

    @property
    def snapper_config(self) -> str:
        return str(self.get("general", "snapper_config", "root"))


def require_enabled(cfg: Config) -> None:
    if not cfg.enabled:
        raise RpError("root-protection is disabled. run: root-protection enable")
