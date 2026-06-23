from __future__ import annotations

from pathlib import Path
import yaml


def load_config(path: str | Path = "config.yaml") -> dict:
    cfg_path = Path(path)
    with cfg_path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    base = cfg_path.parent.resolve()
    cfg["_base_dir"] = base
    cfg["data_root"] = (base / cfg["data_root"]).resolve()
    cfg["output_dir"] = (base / cfg.get("output_dir", "outputs")).resolve()
    return cfg


def ensure_output_dirs(cfg: dict) -> None:
    out = Path(cfg["output_dir"])
    for sub in ["tables", "figures", "cache/lob_daily"]:
        (out / sub).mkdir(parents=True, exist_ok=True)
