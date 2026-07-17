import json
import os
import platform
import re
from typing import List, Optional, Set

from .config import Config
from .detect import RootLayout, detect_layout
from .snap import list_snapshots, snapshot_lv_name
from .util import RpError, run, run_out, which

BOOM_MARKER = "root-protection"
STATE_DIR = "/var/lib/root-protection"
ENTRY_MAP = os.path.join(STATE_DIR, "boom-entries.json")
PROFILE_FILE = os.path.join(STATE_DIR, "boom-profile-id")
LIBEXEC = "/usr/libexec/root-protection"
ENSURE_PROFILE = os.path.join(LIBEXEC, "ensure-boom-profile")
CREATE_ENTRY = os.path.join(LIBEXEC, "boom-create-entry")


def _boom(*args: str, check: bool = True) -> str:
    if not which("boom"):
        raise RpError("boom not installed")
    return run_out(["boom", *args], check=check)


def _load_map() -> dict:
    if not os.path.exists(ENTRY_MAP):
        return {}
    with open(ENTRY_MAP, encoding="utf-8") as f:
        return json.load(f)


def _save_map(data: dict) -> None:
    os.makedirs(STATE_DIR, mode=0o755, exist_ok=True)
    tmp = ENTRY_MAP + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, ENTRY_MAP)


def ensure_profile() -> str:
    if not which("boom"):
        raise RpError("boom not installed")
    script = ENSURE_PROFILE
    # allow running from source tree before install
    if not os.path.exists(script):
        here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        alt = os.path.join(here, "hooks", "dnf5", "ensure-boom-profile")
        if os.path.exists(alt):
            script = alt
        else:
            raise RpError(f"missing {ENSURE_PROFILE}, run: make install")
    out = run_out(["bash", script], check=True)
    pid = out.strip().splitlines()[-1].strip()
    if not pid:
        raise RpError("ensure-boom-profile returned empty profile id")
    os.makedirs(STATE_DIR, mode=0o755, exist_ok=True)
    with open(PROFILE_FILE, "w", encoding="utf-8") as f:
        f.write(pid + "\n")
    return pid


def entry_title(number: int, description: str = "") -> str:
    # avoid # in titles (shell/log noise). keep it boring and unique.
    desc = (description or "").strip().replace("#", "")
    if desc:
        short = desc[:40]
        return f"{BOOM_MARKER} snap {number} - {short}"
    return f"{BOOM_MARKER} snap {number}"


def _find_boot_ids_by_title_prefix(prefix: str) -> List[str]:
    ids = []
    try:
        out = _boom("list")
    except RpError:
        return ids
    for line in out.splitlines():
        if prefix not in line:
            continue
        m = re.search(r"\b([0-9a-f]{7,})\b", line)
        if m:
            ids.append(m.group(1))
    return ids


def sync_entry_for_snapshot(
    cfg: Config,
    number: int,
    layout: Optional[RootLayout] = None,
    description: str = "",
) -> None:
    if layout is None:
        layout = detect_layout()
    if not layout.vg or not layout.lv:
        raise RpError("cannot sync boot entry without root LV")

    profile = ensure_profile()
    if not description:
        for s in list_snapshots(cfg, layout):
            if s.number == number:
                description = s.description
                break

    title = entry_title(number, description)
    script = CREATE_ENTRY
    if not os.path.exists(script):
        here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        alt = os.path.join(here, "hooks", "dnf5", "boom-create-entry")
        if os.path.exists(alt):
            script = alt
        else:
            raise RpError(f"missing {CREATE_ENTRY}, run: make install")

    delete_entry_for_snapshot(cfg, number, only_map=False)
    out = run_out(
        ["bash", script, str(number), layout.vg, layout.lv, title],
        check=True,
    )
    boot_id = ""
    m = re.search(r"(?:Boot ID|boot_id)\s*[:=]?\s*([0-9a-f]+)", out, re.I)
    if m:
        boot_id = m.group(1)
    else:
        ids = _find_boot_ids_by_title_prefix(f"{BOOM_MARKER} snap {number}")
        boot_id = ids[-1] if ids else ""

    lv = f"{layout.vg}/{snapshot_lv_name(layout.lv, number)}"
    amap = _load_map()
    amap[str(number)] = {
        "boot_id": boot_id,
        "lv": lv,
        "title": title,
        "profile": profile,
    }
    _save_map(amap)


def delete_entry_for_snapshot(cfg: Config, number: int, only_map: bool = False) -> None:
    amap = _load_map()
    key = str(number)
    info = amap.pop(key, None)
    if info and info.get("boot_id") and not only_map:
        try:
            _boom("delete", info["boot_id"])
        except RpError:
            for bid in _find_boot_ids_by_title_prefix(f"{BOOM_MARKER} snap {number}"):
                try:
                    _boom("delete", bid)
                except RpError:
                    pass
    elif not only_map:
        for bid in _find_boot_ids_by_title_prefix(f"{BOOM_MARKER} snap {number}"):
            try:
                _boom("delete", bid)
            except RpError:
                pass
    _save_map(amap)


def sync_all_boot_entries(cfg: Config, layout: Optional[RootLayout] = None) -> int:
    if layout is None:
        layout = detect_layout()
    ensure_profile()
    snaps = list_snapshots(cfg, layout)
    wanted: Set[int] = {s.number for s in snaps}
    amap = _load_map()
    for key in list(amap.keys()):
        try:
            num = int(key)
        except ValueError:
            continue
        if num not in wanted:
            delete_entry_for_snapshot(cfg, num)
    count = 0
    for s in snaps:
        if str(s.number) not in _load_map():
            sync_entry_for_snapshot(cfg, s.number, layout=layout, description=s.description)
            count += 1
    return count


def rollback_boot(cfg: Config, number: int, layout: Optional[RootLayout] = None) -> str:
    if layout is None:
        layout = detect_layout()
    sync_entry_for_snapshot(cfg, number, layout=layout)
    lv = f"{layout.vg}/{snapshot_lv_name(layout.lv, number)}"
    return (
        f"boot entry ready for snapshot #{number} ({lv}).\n"
        "reboot, open GRUB, pick the root-protection entry for that snapshot.\n"
        "this is temporary until you merge. see: root-protection rollback --merge"
    )


def rollback_merge(cfg: Config, number: int, layout: Optional[RootLayout] = None) -> str:
    if layout is None:
        layout = detect_layout()
    if not which("lvconvert"):
        raise RpError("lvconvert missing")
    lv = f"{layout.vg}/{snapshot_lv_name(layout.lv, number)}"
    try:
        run(["lvchange", "-ay", lv], check=False)
    except RpError:
        pass
    run(["lvconvert", "--merge", lv], check=True)
    return (
        f"merge scheduled for {lv}.\n"
        "reboot now to finish. after merge that snapshot LV is gone.\n"
        "run: root-protection sync-boot && root-protection cleanup"
    )
