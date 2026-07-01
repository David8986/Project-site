from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_APP = ROOT / "outputs" / "real_leaf_analysis"
SOURCE_COMPARISON = ROOT / "outputs" / "inside_outside_comparison"
OUTPUT = ROOT / "outputs" / "leaf_analysis_app_new_data"


GRAPH_INFO = [
    (
        "01_mean_normalized_spectra_inside_vs_outside.png",
        "Forma spectrului normalizata",
        "Arata daca forma curbei se pastreaza intre afara si cutie. Curbele nu sunt identice, dar urmaresc aceleasi zone mari ale spectrului.",
    ),
    (
        "02_inside_outside_similarity_heatmap.png",
        "Harta de similaritate",
        "Valorile mai apropiate de 1 inseamna forme mai asemanatoare. Mediana generala este 0.56, deci exista o legatura clara, dar mediul schimba mult semnalul.",
    ),
    (
        "03_similarity_by_filter_and_condition.png",
        "Similaritate pe filtru",
        "Compara fiecare filtru si starea frunzei. Camera poate fi verificata mai bine acolo unde perechile au similaritate mai mare.",
    ),
    (
        "04_raw_signal_area_inside_vs_outside.png",
        "Puterea semnalului",
        "Afara semnalul total este de aproximativ 138 ori mai mare decat in cutie. Asta explica de ce datele brute nu trebuie comparate direct fara normalizare.",
    ),
    (
        "05_noise_roughness_inside_vs_outside.png",
        "Zgomot si rugozitate",
        "Cutia are semnal mai slab si curbe mai instabile. Pentru aplicatie este mai bine sa folosesti forma normalizata si raporturi, nu valoarea bruta singura.",
    ),
    (
        "06_camera_files_by_environment.png",
        "Poze gasite pe mediu",
        "In datele actuale exista poze doar pentru masuratorile din cutie. Afara exista spectre, dar nu si JPG-uri pentru comparatie camera-camera.",
    ),
]


def read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def round_float(value: str | float | int | None, digits: int = 3) -> str:
    if value in (None, ""):
        return ""
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return str(value)


def copy_assets() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "assets" / "graphs").mkdir(parents=True, exist_ok=True)
    (OUTPUT / "data").mkdir(parents=True, exist_ok=True)
    (OUTPUT / "source_app_copy").mkdir(parents=True, exist_ok=True)

    for graph_name, _, _ in GRAPH_INFO:
        shutil.copy2(SOURCE_COMPARISON / "graphs" / graph_name, OUTPUT / "assets" / "graphs" / graph_name)

    for data_file in [
        "inside_outside_summary.json",
        "inside_outside_spectrum_pairs.csv",
        "inside_outside_spectrum_environment_features.csv",
        "camera_environment_inventory.csv",
    ]:
        shutil.copy2(SOURCE_COMPARISON / data_file, OUTPUT / "data" / data_file)

    for old_app_file in SOURCE_APP.glob("*"):
        if old_app_file.is_file():
            shutil.copy2(old_app_file, OUTPUT / "source_app_copy" / old_app_file.name)


def build_rows(rows: list[dict[str, str]], limit: int = 12) -> str:
    shown = rows[:limit]
    cells = []
    for row in shown:
        cells.append(
            "<tr>"
            f"<td>{row.get('condition', '')}</td>"
            f"<td>{row.get('filter_label', '')}</td>"
            f"<td>{round_float(row.get('shape_similarity_pearson_r'), 3)}</td>"
            f"<td>{round_float(row.get('outside_to_inside_area_ratio'), 1)}x</td>"
            f"<td>{round_float(row.get('centroid_shift_outside_minus_inside_nm'), 1)} nm</td>"
            f"<td>{row.get('outside_sample', '')}</td>"
            f"<td>{row.get('inside_sample', '')}</td>"
            "</tr>"
        )
    return "\n".join(cells)


def build_environment_rows(rows: list[dict[str, str]]) -> str:
    cells = []
    for row in rows:
        cells.append(
            "<tr>"
            f"<td>{row.get('environment', '')}</td>"
            f"<td>{row.get('condition', '')}</td>"
            f"<td>{row.get('filter_label', '')}</td>"
            f"<td>{round_float(row.get('full_area'), 0)}</td>"
            f"<td>{round_float(row.get('full_peak'), 0)}</td>"
            f"<td>{round_float(row.get('noise_index_residual_over_mean'), 3)}</td>"
            f"<td>{round_float(row.get('roughness_index_mean_abs_diff'), 3)}</td>"
            "</tr>"
        )
    return "\n".join(cells)


def build_graphs() -> str:
    items = []
    for file_name, title, text in GRAPH_INFO:
        items.append(
            f"""
            <article class="graph-card" data-graph="{file_name}">
              <button class="graph-button" type="button" aria-label="Open {title}">
                <img src="assets/graphs/{file_name}" alt="{title}">
              </button>
              <div class="graph-copy">
                <h3>{title}</h3>
                <p>{text}</p>
              </div>
            </article>
            """
        )
    return "\n".join(items)


def build_html() -> str:
    summary = read_json(SOURCE_COMPARISON / "inside_outside_summary.json")
    pairs = read_csv(SOURCE_COMPARISON / "inside_outside_spectrum_pairs.csv")
    env_rows = read_csv(SOURCE_COMPARISON / "inside_outside_spectrum_environment_features.csv")
    camera_rows = read_csv(SOURCE_COMPARISON / "camera_environment_inventory.csv")

    healthy = summary["by_condition"]["healthy"]
    unhealthy = summary["by_condition"]["unhealthy"]
    env_summary = summary["environment_spectrum_summary"]
    camera_count = summary["camera_image_counts_by_environment"].get("in cutie", 0)

    camera_table = "\n".join(
        f"<tr><td>{row['environment']}</td><td>{row['condition']}</td><td>{row['image_count']}</td></tr>"
        for row in camera_rows
    )

    data_payload = json.dumps(
        {
            "summary": summary,
            "pair_count": len(pairs),
            "environment_feature_count": len(env_rows),
        },
        ensure_ascii=False,
        indent=2,
    )

    return f"""<!doctype html>
<html lang="ro">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Analiza frunze - date noi</title>
  <style>
    :root {{
      --bg: #f5f6f2;
      --ink: #17211b;
      --muted: #5f6b62;
      --line: #d9ded5;
      --panel: #ffffff;
      --green: #23734a;
      --blue: #295f8f;
      --amber: #b26922;
      --red: #a64536;
      --soft-green: #e3f1e8;
      --soft-blue: #e5eef8;
      --soft-amber: #f7ead9;
      --shadow: 0 10px 26px rgba(23, 33, 27, 0.08);
    }}
    * {{ box-sizing: border-box; }}
    html {{ overflow-x: hidden; }}
    body {{
      margin: 0;
      font-family: Inter, Segoe UI, Arial, sans-serif;
      background: var(--bg);
      color: var(--ink);
      letter-spacing: 0;
      overflow-x: hidden;
    }}
    header {{
      background: #ffffff;
      border-bottom: 1px solid var(--line);
    }}
    .hero {{
      max-width: 1280px;
      width: 100%;
      margin: 0 auto;
      padding: 28px 32px 22px;
      display: grid;
      grid-template-columns: minmax(0, 1fr) 360px;
      gap: 28px;
      align-items: end;
    }}
    h1 {{
      margin: 0 0 10px;
      font-size: 30px;
      line-height: 1.15;
      font-weight: 780;
      overflow-wrap: anywhere;
    }}
    h2 {{
      margin: 0 0 12px;
      font-size: 19px;
      line-height: 1.25;
    }}
    h3 {{
      margin: 0 0 8px;
      font-size: 15px;
      line-height: 1.25;
    }}
    p {{
      margin: 0;
      color: var(--muted);
      line-height: 1.5;
      font-size: 14px;
      overflow-wrap: anywhere;
    }}
    main {{
      max-width: 1280px;
      width: 100%;
      margin: 0 auto;
      padding: 24px 32px 44px;
    }}
    .summary-note {{
      display: grid;
      gap: 10px;
      padding: 16px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fbfcf9;
    }}
    .summary-note strong {{
      color: var(--ink);
      font-size: 13px;
    }}
    .kpi-grid {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 14px;
      margin-bottom: 20px;
    }}
    .kpi {{
      min-height: 126px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 15px;
      box-shadow: 0 1px 2px rgba(23, 33, 27, 0.05);
    }}
    .kpi-label {{
      color: var(--muted);
      font-size: 12px;
      font-weight: 720;
      text-transform: uppercase;
    }}
    .kpi-value {{
      margin-top: 8px;
      font-size: 30px;
      line-height: 1;
      font-weight: 780;
    }}
    .kpi-note {{
      margin-top: 10px;
      font-size: 12px;
    }}
    .tabs {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin: 0 0 18px;
    }}
    .tab {{
      min-height: 38px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #ffffff;
      color: var(--ink);
      padding: 8px 12px;
      font-size: 13px;
      font-weight: 750;
      cursor: pointer;
    }}
    .tab.active {{
      background: #173324;
      color: #ffffff;
      border-color: #173324;
    }}
    section[data-panel] {{ display: none; }}
    section[data-panel].active {{ display: block; }}
    .band {{
      margin-bottom: 20px;
      padding: 18px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: 0 1px 2px rgba(23, 33, 27, 0.05);
    }}
    .split {{
      display: grid;
      grid-template-columns: minmax(0, 0.9fr) minmax(0, 1.1fr);
      gap: 16px;
      align-items: start;
    }}
    .result-list {{
      display: grid;
      gap: 10px;
      margin-top: 14px;
    }}
    .result {{
      display: grid;
      grid-template-columns: 120px 1fr;
      gap: 12px;
      padding: 11px 0;
      border-top: 1px solid #e6eae3;
    }}
    .result:first-child {{ border-top: 0; padding-top: 0; }}
    .result b {{ font-size: 13px; }}
    .pill-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 12px;
    }}
    .pill {{
      display: inline-flex;
      align-items: center;
      min-height: 26px;
      border-radius: 999px;
      padding: 4px 9px;
      font-size: 12px;
      font-weight: 760;
    }}
    .good {{ background: var(--soft-green); color: #1f663f; }}
    .info {{ background: var(--soft-blue); color: #225780; }}
    .warn {{ background: var(--soft-amber); color: #854b15; }}
    .bad {{ background: #f4dfdc; color: #873329; }}
    .graph-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 16px;
    }}
    .graph-card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
      box-shadow: 0 1px 2px rgba(23, 33, 27, 0.05);
    }}
    .graph-button {{
      display: block;
      width: 100%;
      padding: 0;
      border: 0;
      background: #ffffff;
      cursor: zoom-in;
    }}
    .graph-card img {{
      display: block;
      width: 100%;
      aspect-ratio: 16 / 10;
      object-fit: contain;
      background: #ffffff;
    }}
    .graph-copy {{
      padding: 14px;
      border-top: 1px solid var(--line);
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
      background: #ffffff;
    }}
    th, td {{
      padding: 9px 8px;
      border-bottom: 1px solid #e4e8e0;
      text-align: left;
      vertical-align: top;
    }}
    th {{
      color: var(--muted);
      font-size: 12px;
      font-weight: 760;
    }}
    .table-wrap {{
      width: 100%;
      overflow-x: auto;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #ffffff;
    }}
    .data-links {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
      margin-top: 14px;
    }}
    .data-link {{
      display: block;
      min-height: 76px;
      padding: 12px;
      color: var(--ink);
      text-decoration: none;
      background: #ffffff;
      border: 1px solid var(--line);
      border-radius: 8px;
    }}
    .data-link span {{
      display: block;
      margin-top: 7px;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.35;
    }}
    .modal {{
      position: fixed;
      inset: 0;
      display: none;
      align-items: center;
      justify-content: center;
      padding: 28px;
      background: rgba(12, 17, 14, 0.78);
      z-index: 20;
    }}
    .modal.open {{ display: flex; }}
    .modal-inner {{
      width: min(1180px, 100%);
      max-height: 92vh;
      background: #ffffff;
      border-radius: 8px;
      overflow: auto;
      box-shadow: var(--shadow);
    }}
    .modal-top {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: center;
      padding: 12px 14px;
      border-bottom: 1px solid var(--line);
    }}
    .close {{
      width: 34px;
      height: 34px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #ffffff;
      color: var(--ink);
      font-size: 20px;
      line-height: 1;
      cursor: pointer;
    }}
    .modal img {{
      display: block;
      width: 100%;
      background: #ffffff;
    }}
    pre {{
      white-space: pre-wrap;
      word-break: break-word;
      padding: 14px;
      background: #eef1eb;
      border-radius: 8px;
      color: #233029;
      font-size: 12px;
      line-height: 1.45;
    }}
    @media (max-width: 980px) {{
      .hero, main {{ padding-left: 18px; padding-right: 18px; }}
      .hero, .split, .kpi-grid, .graph-grid, .data-links {{
        grid-template-columns: 1fr;
      }}
      .result {{ grid-template-columns: 1fr; gap: 4px; }}
    }}
    @media (max-width: 600px) {{
      .hero, main {{ padding-left: 16px; padding-right: 16px; }}
      .hero > *, main > * {{ min-width: 0; max-width: 100%; }}
      .hero h1, .hero p, .summary-note {{ max-width: min(340px, calc(100vw - 32px)); }}
      h1 {{ font-size: 25px; line-height: 1.18; }}
      h2 {{ font-size: 17px; }}
      .hero {{ gap: 18px; }}
      .summary-note {{ padding: 14px; }}
      .kpi {{ min-height: 118px; }}
      .tab {{ flex: 1 1 calc(50% - 8px); }}
      .modal {{ padding: 12px; }}
    }}
  </style>
</head>
<body>
  <header>
    <div class="hero">
      <div>
        <h1>Analiza camera + spectrometru cu datele noi</h1>
        <p>Copie adaptata a aplicatiei de analiza. Foloseste masuratorile reale pentru comparatia afara / in cutie si include graficele generate din intregul spectru.</p>
        <div class="pill-row">
          <span class="pill good">spectre reale</span>
          <span class="pill info">27 perechi comparate</span>
          <span class="pill warn">poze afara lipsesc</span>
        </div>
      </div>
      <aside class="summary-note">
        <strong>Concluzia scurta</strong>
        <p>Forma curbelor ramane partial asemanatoare intre afara si cutie, dar intensitatea bruta se schimba foarte mult. Pentru aplicatie, camera trebuie comparata cu spectrometrul prin valori normalizate, rapoarte si tendinte pe filtre, nu prin intensitatea bruta directa.</p>
      </aside>
    </div>
  </header>

  <main>
    <div class="kpi-grid" aria-label="Rezumat numeric">
      <div class="kpi"><div class="kpi-label">Perechi afara / cutie</div><div class="kpi-value">{summary['matched_inside_outside_spectrum_pairs']}</div><p class="kpi-note">spectre potrivite dupa stare si filtru</p></div>
      <div class="kpi"><div class="kpi-label">Similaritate mediana</div><div class="kpi-value">{round_float(summary['overall_median_shape_similarity_r'], 2)}</div><p class="kpi-note">corelatia formei curbei, dupa normalizare</p></div>
      <div class="kpi"><div class="kpi-label">Semnal afara / cutie</div><div class="kpi-value">{round_float(summary['overall_median_outside_to_inside_area_ratio'], 1)}x</div><p class="kpi-note">intensitatea totala este mult mai mare afara</p></div>
      <div class="kpi"><div class="kpi-label">Poze in date</div><div class="kpi-value">{camera_count}</div><p class="kpi-note">toate sunt din cutie in setul gasit</p></div>
    </div>

    <nav class="tabs" aria-label="Sectiuni aplicatie">
      <button class="tab active" type="button" data-tab="overview">Rezumat</button>
      <button class="tab" type="button" data-tab="graphs">Grafice</button>
      <button class="tab" type="button" data-tab="tables">Tabele</button>
      <button class="tab" type="button" data-tab="files">Fisiere</button>
    </nav>

    <section class="active" data-panel="overview">
      <div class="band split">
        <div>
          <h2>Ce demonstreaza datele</h2>
          <p>Masuratorile arata ca sistemul din cutie poate pastra informatia de forma a spectrului, dar la o intensitate mult mai mica. Asta sustine ideea ca imaginile camerei pot fi folosite ca dovada de concept daca sunt calibrate si comparate cu spectrometrul prin aceleasi filtre.</p>
          <div class="result-list">
            <div class="result"><b>Frunze sanatoase</b><p>{healthy['matched_pairs']} perechi, similaritate mediana {round_float(healthy['median_shape_similarity_r'], 2)}, semnal afara/cutie {round_float(healthy['median_outside_to_inside_area_ratio'], 1)}x.</p></div>
            <div class="result"><b>Frunze nesanatoase</b><p>{unhealthy['matched_pairs']} perechi, similaritate mediana {round_float(unhealthy['median_shape_similarity_r'], 2)}, semnal afara/cutie {round_float(unhealthy['median_outside_to_inside_area_ratio'], 1)}x.</p></div>
            <div class="result"><b>Zgomot</b><p>Mediana zgomotului este {round_float(env_summary['afara']['median_noise_index'], 3)} afara si {round_float(env_summary['in cutie']['median_noise_index'], 3)} in cutie.</p></div>
          </div>
        </div>
        <div class="table-wrap">
          <table>
            <thead><tr><th>Mediu</th><th>Spectre</th><th>Arie mediana</th><th>Zgomot median</th><th>Rugozitate</th></tr></thead>
            <tbody>
              <tr><td>afara</td><td>{env_summary['afara']['sample_spectra']}</td><td>{round_float(env_summary['afara']['median_full_area'], 0)}</td><td>{round_float(env_summary['afara']['median_noise_index'], 3)}</td><td>{round_float(env_summary['afara']['median_roughness_index'], 3)}</td></tr>
              <tr><td>in cutie</td><td>{env_summary['in cutie']['sample_spectra']}</td><td>{round_float(env_summary['in cutie']['median_full_area'], 0)}</td><td>{round_float(env_summary['in cutie']['median_noise_index'], 3)}</td><td>{round_float(env_summary['in cutie']['median_roughness_index'], 3)}</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </section>

    <section data-panel="graphs">
      <div class="graph-grid">
        {build_graphs()}
      </div>
    </section>

    <section data-panel="tables">
      <div class="band">
        <h2>Primele perechi spectru afara / spectru in cutie</h2>
        <div class="table-wrap">
          <table>
            <thead><tr><th>Stare</th><th>Filtru</th><th>Similaritate r</th><th>Raport arie</th><th>Deplasare centru</th><th>Proba afara</th><th>Proba in cutie</th></tr></thead>
            <tbody>{build_rows(pairs, 14)}</tbody>
          </table>
        </div>
      </div>
      <div class="band">
        <h2>Inventar poze gasite</h2>
        <div class="table-wrap">
          <table>
            <thead><tr><th>Mediu</th><th>Stare</th><th>Numar imagini</th></tr></thead>
            <tbody>{camera_table}</tbody>
          </table>
        </div>
      </div>
      <div class="band">
        <h2>Mostre de caracteristici spectrale</h2>
        <div class="table-wrap">
          <table>
            <thead><tr><th>Mediu</th><th>Stare</th><th>Filtru</th><th>Arie</th><th>Varf</th><th>Zgomot</th><th>Rugozitate</th></tr></thead>
            <tbody>{build_environment_rows(env_rows[:16])}</tbody>
          </table>
        </div>
      </div>
    </section>

    <section data-panel="files">
      <div class="band">
        <h2>Datele copiate in aplicatie</h2>
        <p>Aceste fisiere sunt in folderul copiei, deci dashboardul poate fi mutat impreuna cu folderul lui.</p>
        <div class="data-links">
          <a class="data-link" href="data/inside_outside_summary.json">Rezumat JSON<span>numerele principale folosite in partea de sus</span></a>
          <a class="data-link" href="data/inside_outside_spectrum_pairs.csv">Perechi CSV<span>toate perechile afara / cutie comparate</span></a>
          <a class="data-link" href="data/inside_outside_spectrum_environment_features.csv">Caracteristici CSV<span>arie, varf, zgomot si rugozitate pe fiecare spectru</span></a>
          <a class="data-link" href="source_app_copy/real_leaf_analysis_dashboard.html">Copia app vechi<span>dashboardul original pastrat separat</span></a>
        </div>
      </div>
      <div class="band">
        <h2>Payload intern</h2>
        <pre id="payload"></pre>
      </div>
    </section>
  </main>

  <div class="modal" id="modal" role="dialog" aria-modal="true" aria-label="Grafic marit">
    <div class="modal-inner">
      <div class="modal-top">
        <h3 id="modalTitle">Grafic</h3>
        <button class="close" type="button" aria-label="Close">&times;</button>
      </div>
      <img id="modalImage" alt="">
    </div>
  </div>

  <script>
    const PAYLOAD = {data_payload};
    document.getElementById("payload").textContent = JSON.stringify(PAYLOAD, null, 2);

    const tabs = [...document.querySelectorAll(".tab")];
    const panels = [...document.querySelectorAll("[data-panel]")];
    function activateTab(name, updateHash = false) {{
      const selected = tabs.find((item) => item.dataset.tab === name) || tabs[0];
      tabs.forEach((item) => item.classList.toggle("active", item === selected));
      panels.forEach((panel) => panel.classList.toggle("active", panel.dataset.panel === selected.dataset.tab));
      if (updateHash) history.replaceState(null, "", "#" + selected.dataset.tab);
    }}
    tabs.forEach((tab) => {{
      tab.addEventListener("click", () => activateTab(tab.dataset.tab, true));
    }});
    activateTab(location.hash.replace("#", "") || "overview");

    const modal = document.getElementById("modal");
    const modalImage = document.getElementById("modalImage");
    const modalTitle = document.getElementById("modalTitle");
    document.querySelectorAll(".graph-card").forEach((card) => {{
      card.querySelector("button").addEventListener("click", () => {{
        const image = card.querySelector("img");
        modalImage.src = image.src;
        modalImage.alt = image.alt;
        modalTitle.textContent = card.querySelector("h3").textContent;
        modal.classList.add("open");
      }});
    }});
    document.querySelector(".close").addEventListener("click", () => modal.classList.remove("open"));
    modal.addEventListener("click", (event) => {{
      if (event.target === modal) modal.classList.remove("open");
    }});
    window.addEventListener("keydown", (event) => {{
      if (event.key === "Escape") modal.classList.remove("open");
    }});
  </script>
</body>
</html>
"""


def main() -> None:
    copy_assets()
    html = build_html()
    (OUTPUT / "index.html").write_text(html, encoding="utf-8")
    (OUTPUT / "inside_outside_analysis_dashboard.html").write_text(html, encoding="utf-8")
    print(OUTPUT)


if __name__ == "__main__":
    main()
