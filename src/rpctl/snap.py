import os
import re
from dataclasses import dataclass
from typing import List, Optional

from .config import Config
from .detect import RootLayout, detect_layout
from .health import assert_can_create
from .util import RpError, run, run_out, which

SNAPPER_CONFIG_DIR = "/etc/snapper/configs"
FILTERS = [
    "/.snapshots",
    "/var/tmp",
    "/var/cache",
    "/var/lib/dnf",
    "/var/lib/rpm",
    "/var/log",
    "/tmp",
    "/root/.cache",
]


@dataclass
class Snapshot:
    number: int
    type: str
    pre: str
    date: str
    user: str
    cleanup: str
    description: str
    lv: str = ""


def _snapper(*args: str, check: bool = True) -> str:
    if not which("snapper"):
        raise RpError("snapper not installed")
    return run_out(["snapper", *args], check=check)


def config_exists(name: str) -> bool:
    return os.path.exists(os.path.join(SNAPPER_CONFIG_DIR, name))


def create_snapper_config(name: str = "root", path: str = "/") -> None:
    if config_exists(name):
        return
    _snapper("-c", name, "create-config", "-f", "lvm(ext4)", path)


def apply_retention(cfg: Config) -> None:
    name = cfg.snapper_config
    r = cfg.data["retention"]
    pairs = [
        f"NUMBER_CLEANUP=yes",
        f"NUMBER_LIMIT={int(r['number_limit'])}",
        f"NUMBER_LIMIT_IMPORTANT={int(r['number_limit_important'])}",
        f"TIMELINE_CREATE=no",
        f"TIMELINE_CLEANUP=yes",
        f"TIMELINE_LIMIT_HOURLY={int(r['timeline_limit_hourly'])}",
        f"TIMELINE_LIMIT_DAILY={int(r['timeline_limit_daily'])}",
        f"TIMELINE_LIMIT_WEEKLY={int(r['timeline_limit_weekly'])}",
        f"TIMELINE_LIMIT_MONTHLY={int(r['timeline_limit_monthly'])}",
        f"TIMELINE_LIMIT_YEARLY={int(r['timeline_limit_yearly'])}",
        f"EMPTY_PRE_POST_CLEANUP={'yes' if r.get('empty_pre_post_cleanup', True) else 'no'}",
        "ALLOW_USERS=\"\"",
        "ALLOW_GROUPS=\"\"",
        "SYNC_ACL=no",
        "BACKGROUND_COMPARISON=yes",
    ]
    _snapper("-c", name, "set-config", *pairs)
    # filters file
    filt = os.path.join(SNAPPER_CONFIG_DIR, f"{name}-filters")
    # also use FILTERS in snapper 0.10+ via config; older uses /etc/snapper/filters
    filt_dir = "/etc/snapper/filters"
    os.makedirs(filt_dir, exist_ok=True)
    with open(os.path.join(filt_dir, f"{name}.txt"), "w", encoding="utf-8") as f:
        for p in FILTERS:
            f.write(p + "\n")


def snapshot_lv_name(root_lv: str, number: int) -> str:
    return f"{root_lv}-snapshot{number}"


def list_snapshots(cfg: Config, layout: Optional[RootLayout] = None) -> List[Snapshot]:
    name = cfg.snapper_config
    if not config_exists(name):
        return []
    if layout is None:
        layout = detect_layout()

    # prefer json when available
    try:
        import json

        out = _snapper("-c", name, "--jsonout", "list")
        data = json.loads(out)
        rows = data if isinstance(data, list) else data.get("snapshots") or data.get(name) or []
        snaps: List[Snapshot] = []
        for row in rows:
            num = int(row.get("number") or row.get("#") or 0)
            if num == 0:
                continue
            lv = ""
            if layout.lv:
                lv = f"{layout.vg}/{snapshot_lv_name(layout.lv, num)}"
            snaps.append(
                Snapshot(
                    number=num,
                    type=str(row.get("type", "")),
                    pre=str(row.get("pre-number") or row.get("pre_number") or row.get("pre") or ""),
                    date=str(row.get("date", "")),
                    user=str(row.get("user", "")),
                    cleanup=str(row.get("cleanup", "")),
                    description=str(row.get("description", "")),
                    lv=lv,
                )
            )
        if snaps:
            return snaps
    except Exception:
        pass

    # Oreon/newer snapper uses pre-number, not pre
    try:
        out = _snapper(
            "-c",
            name,
            "--csvout",
            "list",
            "--columns",
            "number,type,pre-number,date,user,cleanup,description",
        )
    except RpError:
        out = _snapper(
            "-c",
            name,
            "--csvout",
            "list",
            "--columns",
            "number,type,date,user,cleanup,description",
        )
        snaps = []
        for line in out.splitlines():
            line = line.strip()
            if not line or line.startswith("number,"):
                continue
            parts = line.split(",", 5)
            if len(parts) < 6:
                continue
            try:
                num = int(parts[0])
            except ValueError:
                continue
            if num == 0:
                continue
            lv = ""
            if layout.lv:
                lv = f"{layout.vg}/{snapshot_lv_name(layout.lv, num)}"
            snaps.append(
                Snapshot(
                    number=num,
                    type=parts[1],
                    pre="",
                    date=parts[2],
                    user=parts[3],
                    cleanup=parts[4],
                    description=parts[5],
                    lv=lv,
                )
            )
        return snaps

    snaps = []
    for line in out.splitlines():
        line = line.strip()
        if not line or line.startswith("number,"):
            continue
        parts = line.split(",", 6)
        if len(parts) < 7:
            continue
        try:
            num = int(parts[0])
        except ValueError:
            continue
        if num == 0:
            continue
        lv = ""
        if layout.lv:
            lv = f"{layout.vg}/{snapshot_lv_name(layout.lv, num)}"
        snaps.append(
            Snapshot(
                number=num,
                type=parts[1],
                pre=parts[2],
                date=parts[3],
                user=parts[4],
                cleanup=parts[5],
                description=parts[6],
                lv=lv,
            )
        )
    return snaps


def create_snapshot(
    cfg: Config,
    description: str = "",
    cleanup: str = "number",
    stype: str = "single",
    pre_number: Optional[int] = None,
    important: bool = False,
    sync_boot: bool = True,
    layout: Optional[RootLayout] = None,
) -> int:
    if layout is None:
        layout = detect_layout()
    if not layout.ok:
        raise RpError("layout not ok: " + "; ".join(layout.issues))
    assert_can_create(cfg.data["health"], layout)

    name = cfg.snapper_config
    if not config_exists(name):
        raise RpError(f"snapper config '{name}' missing. run enable first")

    args = ["-c", name, "create", "-t", stype, "--cleanup", cleanup, "-p"]
    if description:
        args.extend(["-d", description])
    if important:
        args.extend(["-u", "important=yes"])
    if stype == "post":
        if pre_number is None:
            raise RpError("post snapshot needs pre_number")
        args.extend(["--pre-number", str(pre_number)])

    out = _snapper(*args)
    m = re.search(r"(\d+)", out)
    if not m:
        raise RpError(f"could not parse snapshot number from: {out}")
    number = int(m.group(1))

    if sync_boot and cfg.get("general", "boot_sync", True):
        from .boot import sync_entry_for_snapshot

        sync_entry_for_snapshot(cfg, number, layout=layout)

    return number


def delete_snapshot(cfg: Config, number: int, sync_boot: bool = True) -> None:
    name = cfg.snapper_config
    if sync_boot and cfg.get("general", "boot_sync", True):
        from .boot import delete_entry_for_snapshot

        delete_entry_for_snapshot(cfg, number)
    _snapper("-c", name, "delete", str(number))


def cleanup(cfg: Config) -> None:
    name = cfg.snapper_config
    for algo in ("number", "timeline", "empty-pre-post"):
        try:
            _snapper("-c", name, "cleanup", algo)
        except RpError:
            pass
    if cfg.get("general", "boot_sync", True):
        from .boot import sync_all_boot_entries

        sync_all_boot_entries(cfg)
