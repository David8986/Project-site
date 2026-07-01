"""Build an app-ready JSON file and static proof-of-concept dashboard."""

from __future__ import annotations

import csv
import json
from pathlib import Path


PROJECT_ROOT = Path(r"C:\Users\david\OneDrive\Desktop\Archive\Projects\CodeX")
ANALYSIS_DIR = PROJECT_ROOT / "outputs" / "spectrometer_photo_comparison"
POC_DIR = PROJECT_ROOT / "outputs" / "leaf_analysis_poc"


def main() -> None:
    POC_DIR.mkdir(parents=True, exist_ok=True)
    data = build_data_payload()
    json_path = POC_DIR / "leaf_poc_data.json"
    html_path = POC_DIR / "leaf_poc_dashboard.html"
    json_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    html_path.write_text(build_html(data), encoding="utf-8")
    print(html_path)
    print(json_path)


def build_data_payload() -> dict[str, object]:
    photo_rows = read_csv(ANALYSIS_DIR / "per_photo_leaf_analysis.csv")
    group_rows = read_csv(ANALYSIS_DIR / "photo_group_summary.csv")
    associations = read_csv(ANALYSIS_DIR / "photo_to_filter_association.csv")
    spectrometer_catalog = read_csv(ANALYSIS_DIR / "spectrometer_file_catalog.csv")
    settings_count = count_csv_rows(ANALYSIS_DIR / "leaf_photo_spectrometer_numeric_analysis.csv")

    groups = []
    for group in group_rows:
        saturation = number(group["avg_mean_saturation"])
        gcc = number(group["avg_gcc"])
        vari = number(group["avg_vari"])
        exg = number(group["avg_exg"])
        brightness = number(group["avg_mean_value_brightness"])
        app_class = classify_group(saturation, gcc)
        groups.append(
            {
                "photo_group": group["photo_group"],
                "photo_count": int(number(group["photo_count"])),
                "leaf_condition": "green/healthy leaf" if group["photo_group"].endswith("1") else "yellow/unhealthy leaf",
                "avg_gcc": gcc,
                "avg_exg": exg,
                "avg_vari": vari,
                "avg_saturation": saturation,
                "avg_brightness": brightness,
                "visible_color_usability_score_0_100": round(min(max(saturation / 0.35, 0), 1) * 100, 1),
                "green_dominance_score": round((gcc - (1 / 3)) * 300, 3),
                "prototype_classification": app_class,
                "recommended_use": (
                    "Use as filter/brightness response input; do not rely on RGB color indices."
                    if app_class == "filter_or_ir_like"
                    else "Use for visible-camera color features and camera-vs-spectrometer comparison."
                ),
            }
        )

    return {
        "dataset_name": "Leaf camera and OceanView spectrometer measurements",
        "status": {
            "camera_photo_metrics_available": True,
            "spectrometer_file_metadata_available": True,
            "raw_spectrometer_intensity_arrays_available": False,
            "required_next_step": "Export wavelength-intensity spectra from OceanView as CSV/TXT.",
        },
        "summary": {
            "photo_count": len(photo_rows),
            "photo_group_count": len(group_rows),
            "spectrometer_catalog_rows": len(spectrometer_catalog),
            "duplicate_ocv_files_included_in_catalog": sum(1 for row in spectrometer_catalog if row.get("duplicate_hint")),
        },
        "app_features": groups,
        "photo_rows": photo_rows,
        "photo_to_filter_association": associations,
        "spectrometer_catalog": spectrometer_catalog,
    }


def classify_group(saturation: float, gcc: float) -> str:
    if saturation < 0.05:
        return "filter_or_ir_like"
    if gcc > 0.34:
        return "visible_leaf_color_signal"
    return "mixed_or_low_confidence_visible_signal"


def build_html(data: dict[str, object]) -> str:
    app_features = data["app_features"]
    photo_rows = data["photo_rows"]
    associations = data["photo_to_filter_association"]
    payload = json.dumps(data)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Leaf Analysis POC</title>
  <style>
    :root {{
      --bg: #f7f8f4;
      --ink: #17211b;
      --muted: #667168;
      --line: #d9ded5;
      --panel: #ffffff;
      --green: #287a46;
      --amber: #b66b1f;
      --red: #a43d2f;
      --blue: #315f8c;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Inter, Segoe UI, Arial, sans-serif;
      background: var(--bg);
      color: var(--ink);
      letter-spacing: 0;
    }}
    header {{
      padding: 28px 32px 18px;
      border-bottom: 1px solid var(--line);
      background: #ffffff;
    }}
    h1 {{ margin: 0 0 8px; font-size: 28px; line-height: 1.15; }}
    h2 {{ margin: 0 0 14px; font-size: 17px; }}
    p {{ margin: 0; color: var(--muted); line-height: 1.5; }}
    main {{ padding: 24px 32px 40px; max-width: 1280px; margin: 0 auto; }}
    .grid {{ display: grid; gap: 16px; }}
    .kpis {{ grid-template-columns: repeat(4, minmax(0, 1fr)); margin-bottom: 18px; }}
    .two {{ grid-template-columns: minmax(0, 1.05fr) minmax(0, .95fr); }}
    .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 18px;
      box-shadow: 0 1px 2px rgba(23, 33, 27, .05);
    }}
    .kpi .label {{ color: var(--muted); font-size: 12px; text-transform: uppercase; }}
    .kpi .value {{ font-size: 28px; font-weight: 750; margin-top: 6px; }}
    .kpi .note {{ font-size: 12px; color: var(--muted); margin-top: 6px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{ padding: 9px 8px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }}
    th {{ font-size: 12px; color: var(--muted); font-weight: 700; }}
    .pill {{ display: inline-flex; border-radius: 999px; padding: 3px 8px; font-size: 12px; font-weight: 700; }}
    .good {{ background: #dff2e5; color: #1d6d3a; }}
    .warn {{ background: #f8ead5; color: #8a4c12; }}
    .bad {{ background: #f7dddd; color: #842c24; }}
    .bar-row {{ display: grid; grid-template-columns: 150px 1fr 78px; gap: 10px; align-items: center; margin: 11px 0; }}
    .track {{ height: 12px; background: #edf0ea; border-radius: 999px; overflow: hidden; }}
    .bar {{ height: 100%; border-radius: 999px; background: var(--green); }}
    .bar.amber {{ background: var(--amber); }}
    .bar.blue {{ background: var(--blue); }}
    .controls {{ display: flex; gap: 8px; margin: 0 0 14px; flex-wrap: wrap; }}
    button {{
      border: 1px solid var(--line);
      background: #fff;
      color: var(--ink);
      border-radius: 6px;
      padding: 8px 11px;
      font-weight: 700;
      cursor: pointer;
    }}
    button.active {{ background: #193b28; color: #fff; border-color: #193b28; }}
    .image-strip {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-top: 16px; }}
    .image-strip img {{ width: 100%; border-radius: 8px; border: 1px solid var(--line); display: block; }}
    .small {{ font-size: 12px; color: var(--muted); }}
    .status {{ display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; }}
    code {{ background: #eef1eb; padding: 2px 5px; border-radius: 4px; }}
    @media (max-width: 900px) {{
      main, header {{ padding-left: 18px; padding-right: 18px; }}
      .kpis, .two, .image-strip {{ grid-template-columns: 1fr; }}
      .bar-row {{ grid-template-columns: 120px 1fr 64px; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>Leaf Camera + Spectrometer Proof of Concept</h1>
    <p>Uses the real computed numbers from your current dataset. Camera features are available now; raw spectrometer intensity curves still need CSV export from OceanView.</p>
    <div class="status">
      <span class="pill good">Camera metrics ready</span>
      <span class="pill warn">Spectrometer metadata ready</span>
      <span class="pill bad">Raw spectra missing</span>
    </div>
  </header>
  <main>
    <section class="grid kpis">
      <div class="panel kpi"><div class="label">Photos</div><div class="value">{data['summary']['photo_count']}</div><div class="note">JPG measurements analyzed</div></div>
      <div class="panel kpi"><div class="label">Photo groups</div><div class="value">{data['summary']['photo_group_count']}</div><div class="note">Two leaf/condition groups</div></div>
      <div class="panel kpi"><div class="label">Spectrometer rows</div><div class="value">{data['summary']['spectrometer_catalog_rows']}</div><div class="note">OCV catalog entries</div></div>
      <div class="panel kpi"><div class="label">Raw spectra</div><div class="value">0</div><div class="note">Need OceanView CSV export</div></div>
    </section>

    <section class="grid two">
      <div class="panel">
        <h2>App-Ready Classification</h2>
        <table>
          <thead><tr><th>Group</th><th>Condition</th><th>Saturation</th><th>GCC</th><th>Usability</th><th>Class</th></tr></thead>
          <tbody id="groupRows"></tbody>
        </table>
      </div>
      <div class="panel">
        <h2>Metric Bars</h2>
        <div id="metricBars"></div>
        <p class="small">GCC near 0.333 means neutral gray. Higher saturation means the camera image contains more usable visible color.</p>
      </div>
    </section>

    <section class="panel" style="margin-top:16px">
      <h2>Photo Group Explorer</h2>
      <div class="controls" id="groupButtons"></div>
      <div id="groupDetail"></div>
    </section>

    <section class="grid two" style="margin-top:16px">
      <div class="panel">
        <h2>How This Becomes An App Feature</h2>
        <table>
          <thead><tr><th>Input</th><th>Feature</th><th>Use in app</th></tr></thead>
          <tbody>
            <tr><td>JPG photo</td><td>GCC, ExG, VARI, saturation, brightness</td><td>Classify whether the camera image is visible-color useful or filter/IR-like.</td></tr>
            <tr><td>OCV file name/folder</td><td>condition, filter_nm, measurement type</td><td>Attach spectrometer measurements to the right leaf group.</td></tr>
            <tr><td>Future exported CSV</td><td>I532, I556, I680, I725, I850, I940</td><td>Compare camera features against spectral response and ratios like 850/680.</td></tr>
          </tbody>
        </table>
      </div>
      <div class="panel">
        <h2>Proof Rule</h2>
        <p>If <code>saturation &lt; 0.05</code>, treat the photo group as filter/IR-like. If saturation is higher and <code>GCC &gt; 0.34</code>, treat it as visible leaf color signal.</p>
        <div style="height:12px"></div>
        <p>This separates your current groups: <code>Poze normale frunza 1</code> becomes filter/IR-like, while <code>Poze normale frunza 2</code> becomes visible leaf color signal.</p>
      </div>
    </section>

    <section class="image-strip">
      <div>
        <p class="small">Original photo contact sheet</p>
        <img src="../spectrometer_photo_comparison/photo_contact_sheet.jpg" alt="Photo contact sheet" />
      </div>
      <div>
        <p class="small">Leaf masks used for numeric features</p>
        <img src="../spectrometer_photo_comparison/photo_leaf_masks.jpg" alt="Leaf mask sheet" />
      </div>
    </section>
  </main>
  <script>
    const DATA = {payload};
    const groups = DATA.app_features;
    const photos = DATA.photo_rows;
    const assoc = DATA.photo_to_filter_association;

    function fmt(v, digits = 4) {{
      const n = Number(v);
      if (!Number.isFinite(n)) return "";
      return n.toFixed(digits);
    }}
    function classPill(value) {{
      return value === "filter_or_ir_like"
        ? '<span class="pill warn">filter / IR-like</span>'
        : '<span class="pill good">visible color signal</span>';
    }}
    document.getElementById("groupRows").innerHTML = groups.map(g => `
      <tr>
        <td>${{g.photo_group}}</td>
        <td>${{g.leaf_condition}}</td>
        <td>${{fmt(g.avg_saturation, 6)}}</td>
        <td>${{fmt(g.avg_gcc, 6)}}</td>
        <td>${{g.visible_color_usability_score_0_100}} / 100</td>
        <td>${{classPill(g.prototype_classification)}}</td>
      </tr>`).join("");

    const barMetrics = [
      ["avg_saturation", "Saturation", 0.35, "amber"],
      ["avg_gcc", "GCC", 0.45, ""],
      ["avg_brightness", "Brightness", 1, "blue"]
    ];
    document.getElementById("metricBars").innerHTML = groups.flatMap(g => barMetrics.map(([key, label, max, cls]) => {{
      const width = Math.max(0, Math.min(100, Number(g[key]) / max * 100));
      return `<div class="bar-row"><div>${{g.photo_group}} ${{label}}</div><div class="track"><div class="bar ${{cls}}" style="width:${{width}}%"></div></div><div>${{fmt(g[key], 4)}}</div></div>`;
    }})).join("");

    const buttons = document.getElementById("groupButtons");
    const detail = document.getElementById("groupDetail");
    function showGroup(groupName) {{
      [...buttons.children].forEach(btn => btn.classList.toggle("active", btn.dataset.group === groupName));
      const rows = photos.filter(p => p.photo_group === groupName);
      const map = assoc.filter(a => a.photo_group === groupName);
      const g = groups.find(item => item.photo_group === groupName);
      detail.innerHTML = `
        <p><strong>${{groupName}}</strong>: ${{g.recommended_use}}</p>
        <table style="margin-top:12px">
          <thead><tr><th>Photo</th><th>Proposed filter/light</th><th>Brightness</th><th>Saturation</th><th>GCC</th><th>Appearance</th></tr></thead>
          <tbody>${{rows.map(row => {{
            const m = map.find(a => a.photo_file === row.photo_file) || {{}};
            return `<tr><td>${{row.photo_file}}</td><td>${{m.proposed_camera_filter_or_light || ""}}</td><td>${{fmt(row.mean_value_brightness, 4)}}</td><td>${{fmt(row.mean_saturation, 4)}}</td><td>${{fmt(row.gcc, 4)}}</td><td>${{row.appearance}}</td></tr>`;
          }}).join("")}}</tbody>
        </table>`;
    }}
    buttons.innerHTML = groups.map((g, i) => `<button data-group="${{g.photo_group}}" class="${{i === 0 ? "active" : ""}}">${{g.photo_group}}</button>`).join("");
    buttons.addEventListener("click", event => {{
      if (event.target.dataset.group) showGroup(event.target.dataset.group);
    }});
    showGroup(groups[0].photo_group);
  </script>
</body>
</html>
"""


def read_csv(path: Path) -> list[dict[str, object]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def count_csv_rows(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open(newline="", encoding="utf-8") as handle:
        return max(sum(1 for _ in handle) - 1, 0)


def number(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


if __name__ == "__main__":
    main()
