"""Resolve the directory used for mutable JSON data."""

from __future__ import annotations

import os


def data_directory(base_dir: str) -> str:
    """Use Railway's mounted persistent volume when available, local data otherwise."""
    volume_path = os.getenv("RAILWAY_VOLUME_MOUNT_PATH", "").strip()
    if volume_path:
        return volume_path
    return os.path.join(base_dir, "data")
