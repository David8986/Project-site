"""Open the analysis app with an existing output folder loaded."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6 import QtWidgets

from plant_health_mvp_new_data.analysis_app.main import AnalysisWindow, DARK_STYLESHEET


def main() -> int:
    input_path = sys.argv[1] if len(sys.argv) > 1 else ""
    output_path = sys.argv[2] if len(sys.argv) > 2 else str(ROOT / "plant_health_mvp_new_data" / "runs" / "analysis_export")
    app = QtWidgets.QApplication([])
    app.setStyleSheet(DARK_STYLESHEET)
    window = AnalysisWindow(input_path, "", output_path)
    window._load_outputs()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
