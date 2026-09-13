"""Pure os.stat-based model file verification (no Salad /download)."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

CHUNK = 64 * 1024

# Mirrors model_requirements paths (kept local so the container image is self-contained)
REQUIRED_SPECS = [
    {
        "key": "unet",
        "path": "/opt/ComfyUI/models/diffusion_models/flux-2-klein-9b-fp8.safetensors",
        "min_bytes": 8_961_408_451,
        "expected_bytes": 9_433_061_528,
        "required": True,
    },
    {
        "key": "clip",
        "path": "/opt/ComfyUI/models/text_encoders/qwen_3_8b_fp8mixed.safetensors",
        "min_bytes": 8_231_606_304,
        "expected_bytes": 8_664_848_742,
        "required": True,
    },
    {
        "key": "vae_instance",
        "path": "/opt/ComfyUI/models/vae/flux2-vae.safetensors",
        "min_bytes": 319_402_878,
        "expected_bytes": 336_213_556,
        "required": True,
    },
    {
        "key": "vae_official",
        "path": "/opt/ComfyUI/models/vae/full_encoder_small_decoder.safetensors",
        "min_bytes": 237_043_137,
        "expected_bytes": 249_519_092,
        "required": False,
    },
]


def _chunk_hashes(path: Path, size: int) -> tuple[str | None, str | None]:
    try:
        with path.open("rb") as f:
            head = f.read(CHUNK)
            if size > CHUNK:
                f.seek(max(0, size - CHUNK))
                tail = f.read(CHUNK)
            else:
                tail = head
        return (
            hashlib.sha256(head).hexdigest() if head else None,
            hashlib.sha256(tail).hexdigest() if tail else None,
        )
    except OSError:
        return None, None


def stat_one(spec: dict[str, Any], *, root: Path | None = None) -> dict[str, Any]:
    """Stat a single model file. root remaps absolute paths for tests."""
    rel = spec["path"]
    if root is not None:
        # Map /opt/ComfyUI/models/... → root / models/...
        suffix = rel.split("/models/", 1)[-1] if "/models/" in rel else rel.lstrip("/")
        path = root / suffix
    else:
        path = Path(rel)

    out: dict[str, Any] = {
        "key": spec["key"],
        "path": str(path if root is None else rel),  # report canonical container path
        "local_path": rel,
        "required": bool(spec.get("required")),
        "min_bytes": int(spec["min_bytes"]),
        "expected_bytes": int(spec["expected_bytes"]),
        "exists": False,
        "size": None,
        "readable": False,
        "size_ok": False,
        "hard_missing": False,
        "head_sha256": None,
        "tail_sha256": None,
        "error": None,
        "source": "os.stat",
    }

    try:
        if not path.exists():
            out["hard_missing"] = bool(spec.get("required"))
            out["error"] = "missing"
            return out
        if not path.is_file():
            out["exists"] = True
            out["hard_missing"] = bool(spec.get("required"))
            out["error"] = "not_a_file"
            return out

        out["exists"] = True
        st = path.stat()
        out["size"] = int(st.st_size)
        out["size_ok"] = out["size"] >= int(spec["min_bytes"])

        # readable: open + read 1 byte (or empty file OK)
        try:
            with path.open("rb") as f:
                f.read(1)
            out["readable"] = True
        except OSError as e:
            out["readable"] = False
            out["error"] = f"unreadable: {e}"
            out["hard_missing"] = bool(spec.get("required"))
            return out

        head, tail = _chunk_hashes(path, out["size"])
        out["head_sha256"] = head
        out["tail_sha256"] = tail

        if not out["size_ok"]:
            out["hard_missing"] = bool(spec.get("required"))
            out["error"] = "undersized"
        return out
    except OSError as e:
        out["error"] = str(e)[:200]
        out["hard_missing"] = bool(spec.get("required"))
        return out


def stat_all(*, root: Path | None = None, specs: list[dict] | None = None) -> dict[str, Any]:
    specs = specs or REQUIRED_SPECS
    files = [stat_one(s, root=root) for s in specs]
    required = [f for f in files if f.get("required")]
    ok = all(
        f.get("exists") and f.get("readable") and f.get("size_ok") and not f.get("hard_missing")
        for f in required
    )
    hard_keys = [f["key"] for f in required if f.get("hard_missing") or not f.get("size_ok") or not f.get("readable") or not f.get("exists")]
    return {
        "ok": ok,
        "source": "os.stat",
        "files": files,
        "hard_missing_keys": hard_keys,
        "required_ok_count": sum(1 for f in required if f.get("size_ok") and f.get("readable") and f.get("exists")),
        "required_total": len(required),
    }
