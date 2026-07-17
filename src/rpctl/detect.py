import os
import re
from dataclasses import dataclass, field
from typing import List, Optional

from .util import RpError, parse_kv_lines, run_out, which


@dataclass
class RootLayout:
    fstype: str = ""
    source: str = ""
    vg: str = ""
    lv: str = ""
    thin: bool = False
    pool: str = ""
    boot_source: str = ""
    boot_on_thin: bool = False
    snapper: bool = False
    boom: bool = False
    issues: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues

    @property
    def root_lv_path(self) -> str:
        if self.vg and self.lv:
            return f"{self.vg}/{self.lv}"
        return ""


def _findmnt(target: str) -> dict:
    if not which("findmnt"):
        raise RpError("findmnt not found (util-linux)")
    out = run_out(
        ["findmnt", "-n", "-o", "FSTYPE,SOURCE,UUID", "-T", target],
        check=True,
    )
    parts = out.split()
    if len(parts) < 2:
        raise RpError(f"cannot resolve mount for {target}")
    return {
        "fstype": parts[0],
        "source": parts[1],
        "uuid": parts[2] if len(parts) > 2 else "",
    }


def _parse_dm_name(source: str) -> Optional[tuple]:
    # /dev/mapper/vg-lv  or  /dev/vg/lv  or  /dev/dm-N
    source = source.strip()
    m = re.match(r"^/dev/([^/]+)/([^/]+)$", source)
    if m and m.group(1) not in ("mapper", "disk", "block"):
        return m.group(1), m.group(2)

    if source.startswith("/dev/mapper/"):
        name = source[len("/dev/mapper/") :]
        # LVM escapes - as --
        # split on single - that is not part of --
        parts = []
        buf = ""
        i = 0
        while i < len(name):
            if name[i : i + 2] == "--":
                buf += "-"
                i += 2
            elif name[i] == "-":
                parts.append(buf)
                buf = ""
                i += 1
            else:
                buf += name[i]
                i += 1
        parts.append(buf)
        if len(parts) >= 2:
            return parts[0], "-".join(parts[1:])
    return None


def _lvs_report(vg: str, lv: str) -> dict:
    if not which("lvs"):
        raise RpError("lvs not found (lvm2)")
    if os.geteuid() != 0:
        raise RpError("LVM query needs root (rerun doctor as root)")
    out = run_out(
        [
            "lvs",
            "-o",
            "lv_name,vg_name,lv_attr,pool_lv,lv_role,segtype",
            "--noheadings",
            "--separator",
            "|",
            f"{vg}/{lv}",
        ],
        check=True,
    )
    line = out.splitlines()[0].strip()
    cols = [c.strip() for c in line.split("|")]
    while len(cols) < 6:
        cols.append("")
    return {
        "lv": cols[0],
        "vg": cols[1],
        "attr": cols[2],
        "pool": cols[3],
        "role": cols[4],
        "segtype": cols[5],
    }


def _is_thin(info: dict) -> bool:
    seg = info.get("segtype", "")
    attr = info.get("attr", "")
    # thin volume attr usually has 'V' volume type thin, pool has 't'
    if seg in ("thin", "thin-pool"):
        return seg == "thin" or bool(info.get("pool"))
    if info.get("pool"):
        return True
    # attr[0] volume type: V = virtual (thin)
    if attr and attr[0] == "V":
        return True
    return False


def _resolve_source_to_lv(source: str) -> Optional[tuple]:
    parsed = _parse_dm_name(source)
    if parsed:
        return parsed
    # follow /dev/dm-N via dmsetup
    if which("dmsetup") and (source.startswith("/dev/dm-") or os.path.exists(source)):
        try:
            name = run_out(["dmsetup", "info", "-C", "--noheadings", "-o", "name", source])
            if name:
                return _parse_dm_name(f"/dev/mapper/{name}")
        except RpError:
            return None
    return None


def detect_layout() -> RootLayout:
    layout = RootLayout()
    layout.snapper = which("snapper") is not None
    layout.boom = which("boom") is not None

    if not layout.snapper:
        layout.issues.append("snapper is not installed")
    if not layout.boom:
        layout.issues.append("boom is not installed (package boom-boot)")
    if not which("lvs"):
        layout.issues.append("lvm2 tools missing (lvs)")

    try:
        root = _findmnt("/")
    except RpError as e:
        layout.issues.append(str(e))
        return layout

    layout.fstype = root["fstype"]
    layout.source = root["source"]

    if layout.fstype != "ext4":
        layout.issues.append(f"root fstype is {layout.fstype}, need ext4")

    names = _resolve_source_to_lv(layout.source)
    if not names:
        layout.issues.append(f"root is not an LVM LV ({layout.source})")
        return layout

    layout.vg, layout.lv = names
    try:
        info = _lvs_report(layout.vg, layout.lv)
    except RpError as e:
        layout.issues.append(f"cannot query root LV: {e}")
        return layout

    layout.pool = info.get("pool", "")
    layout.thin = _is_thin(info)
    if not layout.thin:
        layout.issues.append(
            f"{layout.vg}/{layout.lv} is not a thin LV. "
            "root-protection needs a thin-provisioned root"
        )

    # /boot must not sit on the same thin root LV (or preferably not on thin pool)
    try:
        boot = _findmnt("/boot")
        layout.boot_source = boot["source"]
        boot_names = _resolve_source_to_lv(boot["source"])
        if boot_names:
            bvg, blv = boot_names
            if bvg == layout.vg and blv == layout.lv:
                layout.issues.append("/boot is on the root LV. keep /boot separate")
            else:
                try:
                    binfo = _lvs_report(bvg, blv)
                    if _is_thin(binfo) and binfo.get("pool") == layout.pool and layout.pool:
                        layout.boot_on_thin = True
                        layout.warnings.append(
                            "/boot is on a thin LV in the same pool. "
                            "prefer thick /boot so kernels survive pool pressure"
                        )
                except RpError:
                    pass
        # if /boot is a plain partition, thats fine
    except RpError:
        layout.warnings.append("/boot not found as its own mount. ESP-only setups need care")

    # separate /home recommended
    try:
        home = _findmnt("/home")
        if home["source"] == layout.source:
            layout.warnings.append("/home is on root. snaps will include home data")
    except RpError:
        layout.warnings.append("/home is not a separate mount")

    return layout


def doctor_text(layout: RootLayout | None = None) -> str:
    if layout is None:
        layout = detect_layout()
    lines = ["root-protection doctor", "======================", ""]
    lines.append(f"root fstype : {layout.fstype or '?'}")
    lines.append(f"root source : {layout.source or '?'}")
    if layout.vg:
        lines.append(f"root LV     : {layout.vg}/{layout.lv}")
        lines.append(f"thin        : {'yes' if layout.thin else 'no'}")
        if layout.pool:
            lines.append(f"thin pool   : {layout.vg}/{layout.pool}")
    lines.append(f"boot source : {layout.boot_source or '?'}")
    lines.append(f"snapper     : {'found' if layout.snapper else 'MISSING'}")
    lines.append(f"boom        : {'found' if layout.boom else 'MISSING'}")
    lines.append("")
    if layout.ok:
        lines.append("RESULT: OK (layout can run root-protection)")
    else:
        lines.append("RESULT: FAIL")
        for i in layout.issues:
            lines.append(f"  - {i}")
    if layout.warnings:
        lines.append("")
        lines.append("warnings:")
        for w in layout.warnings:
            lines.append(f"  - {w}")
    return "\n".join(lines)


def read_os_release() -> dict:
    path = "/etc/os-release"
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return parse_kv_lines(f.read())
