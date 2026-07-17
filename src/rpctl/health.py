from dataclasses import dataclass
from typing import Optional, Tuple

from .detect import RootLayout, detect_layout
from .util import RpError, run_out, which


@dataclass
class PoolHealth:
    vg: str = ""
    pool: str = ""
    data_percent: float = 0.0
    meta_percent: float = 0.0
    level: str = "ok"  # ok|warn|crit
    message: str = ""


def _pool_percents(vg: str, pool: str) -> Tuple[float, float]:
    if not which("lvs"):
        raise RpError("lvs not found")
    out = run_out(
        [
            "lvs",
            "-o",
            "data_percent,metadata_percent",
            "--noheadings",
            "--nosuffix",
            "--units",
            "b",
            f"{vg}/{pool}",
        ],
        check=True,
    )
    parts = out.split()
    if len(parts) < 2:
        # some lvm versions put both on one line with spaces
        raise RpError(f"cannot read thin pool usage for {vg}/{pool}")
    try:
        return float(parts[0]), float(parts[1])
    except ValueError as e:
        raise RpError(f"bad pool percent output: {out}") from e


def check_health(
    layout: Optional[RootLayout] = None,
    warn_data: float = 70,
    crit_data: float = 85,
    warn_meta: float = 70,
    crit_meta: float = 85,
) -> PoolHealth:
    if layout is None:
        layout = detect_layout()
    h = PoolHealth(vg=layout.vg, pool=layout.pool)
    if not layout.thin or not layout.pool:
        h.level = "crit"
        h.message = "no thin pool for root"
        return h
    data, meta = _pool_percents(layout.vg, layout.pool)
    h.data_percent = data
    h.meta_percent = meta
    h.message = (
        f"thin pool {layout.vg}/{layout.pool} "
        f"data={data:.1f}% meta={meta:.1f}%"
    )
    if data >= crit_data or meta >= crit_meta:
        h.level = "crit"
    elif data >= warn_data or meta >= warn_meta:
        h.level = "warn"
    else:
        h.level = "ok"
    return h


def assert_can_create(cfg_health: dict, layout: Optional[RootLayout] = None) -> PoolHealth:
    h = check_health(
        layout,
        warn_data=float(cfg_health.get("warn_data_percent", 70)),
        crit_data=float(cfg_health.get("crit_data_percent", 85)),
        warn_meta=float(cfg_health.get("warn_meta_percent", 70)),
        crit_meta=float(cfg_health.get("crit_meta_percent", 85)),
    )
    if h.level == "crit" and cfg_health.get("refuse_create_on_crit", True):
        raise RpError(
            f"refusing new snapshot, thin pool critical ({h.message}). "
            "free space or raise health.crit_* in config"
        )
    return h
