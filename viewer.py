"""Compatibility launcher for the plant-health hyperspectral explorer."""

from __future__ import annotations

from plant_health_mvp.gui.main_window import launch_gui


def main() -> int:
    """Run the adapter-driven hyperspectral inspection GUI."""

    return launch_gui()


if __name__ == "__main__":
    raise SystemExit(main())
