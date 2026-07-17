import os
import shutil

from .boot import ensure_profile, sync_all_boot_entries
from .config import Config, DEFAULT_CONFIG_PATH
from .detect import detect_layout, doctor_text
from .snap import apply_retention, config_exists, create_snapper_config
from .util import RpError, ensure_dir, run, run_out, which


UNIT_TIMER = "root-protection-snapshot.timer"
HEALTH_TIMER = "root-protection-health.timer"
RESTORE_GRUB = "/usr/libexec/root-protection/restore-grub-default"


def _systemctl(*args: str) -> None:
    if not which("systemctl"):
        return
    run(["systemctl", *args], check=False)


def _grub_default(action: str) -> str:
    script = RESTORE_GRUB
    if not os.path.exists(script):
        here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        alt = os.path.join(here, "hooks", "dnf5", "restore-grub-default")
        if os.path.exists(alt):
            script = alt
        else:
            return ""
    try:
        return run_out(["bash", script, action], check=False)
    except RpError:
        return ""


def enable(cfg: Config) -> str:
    layout = detect_layout()
    if not layout.ok:
        raise RpError(
            "cannot enable, layout check failed:\n"
            + doctor_text(layout)
            + "\n\nfix: put / on LVM thin ext4 with /boot outside the thin root LV"
        )

    if not os.path.exists(cfg.path):
        src = "/usr/share/root-protection/config.toml"
        ensure_dir(os.path.dirname(cfg.path))
        if os.path.exists(src):
            shutil.copy2(src, cfg.path)
            cfg = Config.load(cfg.path)
        else:
            cfg.save()

    create_snapper_config(cfg.snapper_config, "/")
    apply_retention(cfg)
    try:
        profile = ensure_profile()
    except RpError as e:
        raise RpError(f"boom OS profile setup failed: {e}") from e

    live = _grub_default("save")

    from .snap import create_snapshot, list_snapshots

    existing = list_snapshots(cfg, layout)
    enable_snaps = [s for s in existing if "root-protection enable" in (s.description or "")]
    if enable_snaps:
        num = enable_snaps[-1].number
        sync_all_boot_entries(cfg, layout)
    else:
        num = create_snapshot(
            cfg,
            description="root-protection enable",
            cleanup="number",
            important=True,
            layout=layout,
        )
        sync_all_boot_entries(cfg, layout)

    restored = _grub_default("restore")

    cfg.set("general", "enabled", True)
    cfg.save()
    _systemctl("enable", "--now", UNIT_TIMER)
    _systemctl("enable", "--now", HEALTH_TIMER)

    return (
        f"enabled. snapper config '{cfg.snapper_config}', "
        f"boom profile {profile}, initial snapshot #{num}, timers on.\n"
        f"grub default kept on live OS ({restored or live or '?'}).\n"
        "daily snaps + dnf pre/post are active when packages are installed."
    )


def disable(cfg: Config, keep_snapshots: bool = True) -> str:
    cfg.set("general", "enabled", False)
    cfg.save()
    _systemctl("disable", "--now", UNIT_TIMER)
    _systemctl("disable", "--now", HEALTH_TIMER)
    msg = "disabled. timers stopped."
    if keep_snapshots:
        msg += " existing snapshots kept."
    return msg


def status_text(cfg: Config) -> str:
    layout = detect_layout()
    from .health import check_health
    from .snap import list_snapshots

    lines = ["root-protection status", "----------------------"]
    lines.append(f"enabled     : {cfg.enabled}")
    lines.append(f"config      : {cfg.path}")
    lines.append(f"snapper cfg : {cfg.snapper_config} ({'yes' if config_exists(cfg.snapper_config) else 'no'})")
    lines.append(f"layout ok   : {layout.ok}")
    if layout.vg:
        lines.append(f"root LV     : {layout.vg}/{layout.lv} (thin={layout.thin})")
    h = None
    if layout.thin and layout.pool:
        try:
            h = check_health(
                layout,
                warn_data=cfg.get("health", "warn_data_percent", 70),
                crit_data=cfg.get("health", "crit_data_percent", 85),
                warn_meta=cfg.get("health", "warn_meta_percent", 70),
                crit_meta=cfg.get("health", "crit_meta_percent", 85),
            )
        except RpError as e:
            lines.append(f"pool health : error ({e})")
    if h:
        lines.append(f"pool health : {h.level} ({h.message})")
    snaps = []
    try:
        if cfg.enabled or config_exists(cfg.snapper_config):
            snaps = list_snapshots(cfg, layout)
    except RpError:
        snaps = []
    lines.append(f"snapshots   : {len(snaps)}")
    if snaps:
        last = snaps[-1]
        lines.append(f"latest      : #{last.number} {last.date} {last.description}")
    if layout.issues:
        lines.append("issues:")
        for i in layout.issues:
            lines.append(f"  - {i}")
    if layout.warnings:
        lines.append("warnings:")
        for w in layout.warnings:
            lines.append(f"  - {w}")
    return "\n".join(lines)
