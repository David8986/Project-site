"""Compatibility launcher for the dedicated viewer app.

Use ``plant_health_mvp.viewer_app.main`` for exploration and
``plant_health_mvp.analysis_app.main`` for processing.
"""

from __future__ import annotations

from .viewer_app.main import launch


def main() -> int:
    """Run the viewer entry point for backward compatibility."""

    return launch()


if __name__ == "__main__":
    raise SystemExit(main())
