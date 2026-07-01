const fs = require("fs");
const path = require("path");
const Module = require("module");

const nodeModules = "C:\\Users\\david\\.cache\\codex-runtimes\\codex-primary-runtime\\dependencies\\node\\node_modules";
const pnpmModules = path.join(nodeModules, ".pnpm");
Module.globalPaths.push(nodeModules);

const pptxgen = require(path.join(pnpmModules, "pptxgenjs@4.0.1", "node_modules", "pptxgenjs"));
const sharp = require(path.join(pnpmModules, "sharp@0.34.5", "node_modules", "sharp"));

const OUT_DIR = "C:\\Users\\david\\OneDrive\\Desktop\\SpectraLeaf poster";
const GRAPH_DIR = "C:\\Users\\david\\OneDrive\\Desktop\\Spectral Leaf graphs for document\\graphs";
const MEDIA_DIR = "C:\\Users\\david\\OneDrive\\Desktop\\Archive\\Projects\\CodeX\\outputs\\poster_extract\\media";
const PPTX_OUT = path.join(OUT_DIR, "SpectraLeaf_poster_7x10.pptx");
const PNG_OUT = path.join(OUT_DIR, "SpectraLeaf_poster_7x10_preview.png");

const assets = {
  validation: path.join(GRAPH_DIR, "figure_1_set_1_camera_vs_spectrometer_overlay.png"),
  set1: path.join(GRAPH_DIR, "figure_2_set_1_health_comparison_side_by_side.png"),
  set2: path.join(GRAPH_DIR, "figure_2_set_2_health_comparison_side_by_side.png"),
  mechanism: path.join(MEDIA_DIR, "image4.png"),
  camera: path.join(MEDIA_DIR, "image6.png"),
  app: path.join(MEDIA_DIR, "image11.png"),
};

const W = 14;
const H = 20;
const PX_W = 2100;
const PX_H = 3000;
const PPTX_TEXT_SCALE = 1.18;
const SVG_TEXT_SCALE = 1.18;

const C = {
  bg: "EAF2F4",
  header: "0F5D73",
  headerDark: "0A4F63",
  bar: "10647A",
  panel: "FFFFFF",
  pale: "F5FAFB",
  ink: "18323A",
  muted: "48636B",
  line: "B8D0D6",
  blue: "1F77B4",
  orange: "FF7F0E",
  green: "23865A",
};

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true });
}

function checkAssets() {
  for (const file of Object.values(assets)) {
    if (!fs.existsSync(file)) throw new Error(`Missing asset: ${file}`);
  }
}

function addText(slide, text, x, y, w, h, opts = {}) {
  slide.addText(text, {
    x, y, w, h,
    fontFace: opts.fontFace || "Aptos",
    fontSize: (opts.size || 8.5) * (opts.noScale ? 1 : PPTX_TEXT_SCALE),
    bold: Boolean(opts.bold),
    italic: Boolean(opts.italic),
    color: opts.color || C.ink,
    align: opts.align || "left",
    valign: opts.valign || "top",
    margin: opts.margin ?? 0.025,
    fit: "shrink",
    breakLine: false,
    paraSpaceAfterPt: opts.paraSpaceAfterPt ?? 1,
  });
}

function addSection(slide, title, x, y, w, h) {
  slide.addShape("rect", {
    x, y, w, h,
    fill: { color: C.panel },
    line: { color: C.line, width: 0.8 },
  });
  slide.addShape("rect", {
    x, y, w, h: 0.3,
    fill: { color: C.bar },
    line: { color: C.bar },
  });
  addText(slide, title, x + 0.1, y + 0.05, w - 0.2, 0.16, {
    size: 7.9,
    bold: true,
    color: "FFFFFF",
    align: "center",
    margin: 0,
  });
}

function addBullets(slide, lines, x, y, w, h, opts = {}) {
  addText(slide, lines.map((line) => `• ${line}`).join("\n"), x, y, w, h, {
    size: opts.size || 6.9,
    color: opts.color || C.ink,
    margin: 0.02,
  });
}

function addMetric(slide, value, label, x, y, w, color) {
  slide.addShape("rect", {
    x, y, w, h: 0.54,
    fill: { color: C.pale },
    line: { color: C.line, width: 0.7 },
  });
  addText(slide, value, x + 0.08, y + 0.1, 1.08, 0.26, {
    size: 13.3,
    bold: true,
    color,
    margin: 0,
  });
  addText(slide, label, x + 1.19, y + 0.1, w - 1.28, 0.27, {
    size: 5.8,
    bold: true,
    color: C.ink,
    margin: 0,
  });
}

async function fitImage(imgPath, x, y, w, h) {
  const meta = await sharp(imgPath).metadata();
  const ar = meta.width / meta.height;
  const box = w / h;
  if (ar > box) {
    const ih = w / ar;
    return { x, y: y + (h - ih) / 2, w, h: ih };
  }
  const iw = h * ar;
  return { x: x + (w - iw) / 2, y, w: iw, h };
}

async function addImage(slide, imgPath, x, y, w, h) {
  slide.addImage({ path: imgPath, ...(await fitImage(imgPath, x, y, w, h)) });
}

function dataUri(imgPath) {
  const ext = path.extname(imgPath).slice(1).toLowerCase().replace("jpg", "jpeg");
  return `data:image/${ext};base64,${fs.readFileSync(imgPath).toString("base64")}`;
}

function esc(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function wrap(text, maxChars) {
  const words = String(text).split(/\s+/);
  const lines = [];
  let line = "";
  for (const word of words) {
    const next = line ? `${line} ${word}` : word;
    if (next.length > maxChars && line) {
      lines.push(line);
      line = word;
    } else {
      line = next;
    }
  }
  if (line) lines.push(line);
  return lines;
}

function svgText(text, x, y, size, color, opts = {}) {
  const lines = Array.isArray(text) ? text : String(text).split("\n");
  const scaledSize = size * (opts.noScale ? 1 : SVG_TEXT_SCALE);
  const weight = opts.weight || 400;
  const anchor = opts.anchor || "start";
  const lh = opts.lineHeight || 1.18;
  return `<text x="${x}" y="${y}" font-family="Aptos, Arial, sans-serif" font-size="${scaledSize}" fill="#${color}" font-weight="${weight}" text-anchor="${anchor}">${lines.map((line, i) => `<tspan x="${x}" dy="${i === 0 ? 0 : scaledSize * lh}">${esc(line)}</tspan>`).join("")}</text>`;
}

function svgWrapped(text, x, y, size, color, maxChars, opts = {}) {
  return svgText(wrap(text, maxChars), x, y, size, color, opts);
}

function svgBullets(lines, x, y, size, color, maxChars) {
  const out = [];
  for (const line of lines) {
    const wrapped = wrap(line, maxChars);
    wrapped.forEach((part, idx) => out.push(idx === 0 ? `• ${part}` : `  ${part}`));
  }
  return svgText(out, x, y, size, color, { lineHeight: 1.18 });
}

function svgPanel(x, y, w, h, title) {
  return `
    <rect x="${x}" y="${y}" width="${w}" height="${h}" fill="#${C.panel}" stroke="#${C.line}" stroke-width="1.5"/>
    <rect x="${x}" y="${y}" width="${w}" height="45" fill="#${C.bar}"/>
    ${svgText(title, x + w / 2, y + 29, 19, "FFFFFF", { weight: 800, anchor: "middle" })}
  `;
}

function svgImg(imgPath, x, y, w, h) {
  return `<image href="${dataUri(imgPath)}" x="${x}" y="${y}" width="${w}" height="${h}" preserveAspectRatio="xMidYMid meet"/>`;
}

async function createPptx() {
  const pptx = new pptxgen();
  pptx.author = "SpectraLeaf";
  pptx.subject = "SpectraLeaf 7:10 poster";
  pptx.title = "SpectraLeaf 7:10 poster";
  pptx.lang = "ro-RO";
  pptx.defineLayout({ name: "POSTER_7X10", width: W, height: H });
  pptx.layout = "POSTER_7X10";
  pptx.theme = { headFontFace: "Aptos Display", bodyFontFace: "Aptos", lang: "ro-RO" };

  const slide = pptx.addSlide();
  slide.background = { color: C.bg };
  slide.addShape("rect", { x: 0.08, y: 0.08, w: 13.84, h: 1.48, fill: { color: C.header }, line: { color: C.header } });
  addText(slide, "SpectraLeaf", 0.33, 0.28, 3.2, 0.34, { size: 21, bold: true, color: "FFFFFF", fontFace: "Aptos Display", margin: 0 });
  addText(slide, "Sistem optic multispectral bazat pe NIR pentru detecția stresului vegetal", 0.34, 0.77, 10.7, 0.23, { size: 9.5, color: "E8F6F9", margin: 0 });
  addText(slide, "Validare cu spectrometrul Ocean Optics USB2000+XR1-ES și cu o cameră în cutie cu 6 filtre optice", 0.34, 1.08, 10.95, 0.18, { size: 6.7, color: "D8EEF3", margin: 0 });
  addText(slide, "7:10 POSTER", 12.3, 0.42, 1.25, 0.18, { size: 7.5, bold: true, color: "FFFFFF", align: "right", margin: 0 });
  addText(slide, "532 / 556 / 680 / 725 / 850 / 940 nm", 10.55, 1.11, 3.0, 0.14, { size: 5.5, color: "D8EEF3", align: "right", margin: 0 });

  const x0 = 0.28;
  const gap = 0.22;
  const col = (13.44 - gap) / 2;
  const r = x0 + col + gap;

  addSection(slide, "Introducere și problemă", x0, 1.82, col, 2.25);
  addBullets(slide, [
    "Stresul vegetal poate modifica reflectanța înainte să apară schimbări clare de culoare în fotografie RGB.",
    "În domeniul NIR, după aproximativ 700 nm, semnalul este influențat de structura internă a frunzei, umiditate și degradare.",
    "Proiectul urmărește o alternativă low-cost la sistemele multispectrale comerciale, folosind o cameră și filtre optice.",
  ], x0 + 0.18, 2.28, col - 0.36, 1.12, { size: 6.45 });
  addMetric(slide, "97,5%", "concordanță medie a formei curbelor cameră–spectrometru", x0 + 0.2, 3.46, 2.98, C.blue);
  addMetric(slide, "11,65%", "scădere medie NIR observată în Setul 1", x0 + 3.35, 3.46, 2.98, C.orange);

  addSection(slide, "Materiale, filtre și principiu", r, 1.82, col, 2.25);
  addBullets(slide, [
    "Spectrometru: Ocean Optics USB2000+XR1-ES, interval λ = 200–1025 nm, rezoluție 1,7–2,1 nm, 2048 pixeli CCD.",
    "Camera: aceeași frunză este fotografiată prin filtre la 532, 556, 680, 725, 850 și 940 nm.",
    "Pentru fiecare imagine se detectează frunza, apoi se calculează mediana luminozității în masca frunzei.",
  ], r + 0.18, 2.28, col - 0.36, 1.3, { size: 6.45 });
  addText(slide, "Punctele camerei nu sunt un spectru continuu, dar pot arăta dacă forma generală și variația NIR sunt apropiate de referință.", r + 0.18, 3.63, col - 0.36, 0.24, { size: 6.05, color: C.muted, margin: 0.01 });

  addSection(slide, "Sistem construit și fluxul de date", x0, 4.3, 13.44, 2.45);
  await addImage(slide, assets.mechanism, x0 + 0.25, 4.78, 2.55, 1.35);
  await addImage(slide, assets.camera, x0 + 3.08, 4.78, 2.32, 1.35);
  await addImage(slide, assets.app, x0 + 5.58, 4.77, 2.45, 1.37);
  addText(slide, "Flux experimental: frunza este măsurată întâi cu spectrometrul, apoi fotografiată în cutie prin cele 6 filtre. Aplicația aliniază imaginile, găsește zona frunzei, elimină o parte din fundal prin mască și extrage valori mediane pentru fiecare bandă.", x0 + 8.25, 4.83, 4.8, 0.64, { size: 6.25, color: C.ink, margin: 0.01 });
  addText(slide, "Spectrometrul produce curba continuă de referință. Camera produce 6 puncte discrete; prin unirea lor se obține o aproximare a răspunsului spectral al frunzei.", x0 + 8.25, 5.65, 4.8, 0.44, { size: 6.25, color: C.ink, margin: 0.01 });

  addSection(slide, "Validare: spectrometru vs cameră", x0, 7.0, 13.44, 4.2);
  await addImage(slide, assets.validation, x0 + 0.35, 7.48, 8.4, 3.06);
  addText(slide, "Comparația suprapune curbele continue ale spectrometrului cu punctele/curbele obținute din camera multispectrală. Pentru curba albastră, coeficientul de corelație este r = 0,982, iar pentru curba portocalie r = 0,967. Media acestor valori indică o concordanță a formei de aproximativ 97,5%.", x0 + 9.0, 7.58, 4.05, 0.96, { size: 6.2, color: C.ink, margin: 0.01 });
  addText(slide, "Diferențele medii dintre cameră și spectrometru sunt 7,166% și 5,403%. Aceste valori sunt suficient de mici pentru un prototip educațional, deoarece sistemul nu trebuie să înlocuiască spectrometrul, ci să indice corect tendințele utile pentru sănătatea plantei.", x0 + 9.0, 8.72, 4.05, 1.02, { size: 6.2, color: C.ink, margin: 0.01 });
  addText(slide, "Formula de comparație folosită în interpretare: pentru fiecare bandă a camerei se compară valoarea mediană a luminozității frunzei cu intensitatea spectrometrului în jurul aceleiași lungimi de undă. În grafice, spectrometrul este netezit prin mediane pe intervale de 10 nm.", x0 + 9.0, 9.92, 4.05, 0.55, { size: 5.8, color: C.muted, margin: 0.01 });

  addSection(slide, "Rezultate: frunze sănătoase vs nesănătoase", x0, 11.45, 13.44, 4.65);
  await addImage(slide, assets.set1, x0 + 0.28, 11.9, 6.25, 3.1);
  await addImage(slide, assets.set2, x0 + 6.9, 11.9, 6.25, 3.1);
  addText(slide, "Set 1: frunza nesănătoasă are semnal NIR mai mic. Spectrometrul indică o scădere de 10,7%, iar camera o scădere de 12,6%, deci diferența dintre metode este de doar 1,9 puncte procentuale.", x0 + 0.35, 15.12, 6.0, 0.42, { size: 5.9, color: C.ink, margin: 0.01 });
  addText(slide, "Set 2: diferența este detectată, dar camera comprimă amplitudinea. Acest rezultat arată că o etichetă simplă sănătos/nesănătos nu produce mereu aceeași formă spectrală și că este nevoie de mai multe probe.", x0 + 6.95, 15.12, 6.05, 0.42, { size: 5.9, color: C.ink, margin: 0.01 });

  addSection(slide, "Interpretare, limite și concluzie", x0, 16.35, 13.44, 2.7);
  addText(slide, "Interpretarea corectă este că SpectraLeaf validează principiul de funcționare: o cameră cu filtre poate urmări forma generală a spectrului și poate evidenția diferențe relevante în NIR. Valoarea de 97,5% este o concordanță statistică față de spectrometru pentru datele analizate, nu o acuratețe universală de diagnostic.", x0 + 0.28, 16.85, 6.35, 0.64, { size: 6.25, color: C.ink, margin: 0.01 });
  addText(slide, "Au fost analizate 4 frunze: 2 sănătoase și 2 nesănătoase. Pentru rezultate finale ar fi necesare mai multe mostre, calibrare cu referințe alb/negru, control mai strict al iluminării și separarea tipurilor de stres: uscare, lipsă de apă, degradare mecanică sau variații naturale ale frunzei.", x0 + 6.9, 16.85, 6.25, 0.64, { size: 6.25, color: C.ink, margin: 0.01 });
  addText(slide, "Concluzie: sistemul este potrivit ca platformă experimentală low-cost pentru analiză multispectrală, iar rezultatele justifică dezvoltarea unei aplicații care să compare automat semnalul camerei cu măsurători de referință.", x0 + 0.28, 17.85, 12.85, 0.34, { size: 6.45, bold: true, color: C.header, margin: 0.01 });

  addSection(slide, "Referințe", x0, 19.22, 13.44, 0.52);
  addText(slide, "[1] GoPhotonics, USB2000+XR1-ES – Ocean Optics.  [2] Ocean Optics, Legacy Spectrometers Support.  [3] Date experimentale SpectraLeaf: grafice spectrometru/cameră, imagini multispectrale și ieșiri ale aplicației.", x0 + 0.22, 19.56, 12.95, 0.12, { size: 4.8, color: C.ink, margin: 0 });

  await pptx.writeFile({ fileName: PPTX_OUT });
}

async function createPreview() {
  const X = (v) => Math.round((v / W) * PX_W);
  const Y = (v) => Math.round((v / H) * PX_H);
  const SW = (v) => Math.round((v / W) * PX_W);
  const SH = (v) => Math.round((v / H) * PX_H);
  const x0 = 0.28;
  const gap = 0.22;
  const col = (13.44 - gap) / 2;
  const r = x0 + col + gap;
  const panel = (x, y, w, h, title) => svgPanel(X(x), Y(y), SW(w), SH(h), title);

  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${PX_W}" height="${PX_H}" viewBox="0 0 ${PX_W} ${PX_H}">
    <rect width="${PX_W}" height="${PX_H}" fill="#${C.bg}"/>
    <rect x="${X(0.08)}" y="${Y(0.08)}" width="${SW(13.84)}" height="${SH(1.48)}" fill="#${C.header}"/>
    ${svgText("SpectraLeaf", X(0.33), Y(0.61), 58, "FFFFFF", { weight: 800 })}
    ${svgText("Sistem optic multispectral bazat pe NIR pentru detecția stresului vegetal", X(0.34), Y(1.01), 25, "E8F6F9")}
    ${svgText("Validare cu spectrometrul Ocean Optics USB2000+XR1-ES și cu o cameră în cutie cu 6 filtre optice", X(0.34), Y(1.28), 18, "D8EEF3")}
    ${svgText("7:10 POSTER", X(13.55), Y(0.61), 20, "FFFFFF", { weight: 800, anchor: "end" })}
    ${svgText("532 / 556 / 680 / 725 / 850 / 940 nm", X(13.55), Y(1.28), 15, "D8EEF3", { anchor: "end" })}

    ${panel(x0, 1.82, col, 2.25, "Introducere și problemă")}
    ${svgBullets(["Stresul vegetal poate modifica reflectanța înainte să apară schimbări clare de culoare în fotografie RGB.", "În domeniul NIR, după aproximativ 700 nm, semnalul este influențat de structura internă a frunzei, umiditate și degradare.", "Proiectul urmărește o alternativă low-cost la sistemele multispectrale comerciale, folosind o cameră și filtre optice."], X(x0 + 0.18), Y(2.44), 17, C.ink, 62)}
    <rect x="${X(x0 + 0.2)}" y="${Y(3.46)}" width="${SW(2.98)}" height="${SH(0.54)}" fill="#${C.pale}" stroke="#${C.line}" stroke-width="1.2"/>
    ${svgText("97,5%", X(x0 + 0.28), Y(3.8), 32, C.blue, { weight: 800 })}
    ${svgText(["concordanță medie a formei", "curbelor cameră–spectrometru"], X(x0 + 1.45), Y(3.7), 13, C.ink, { weight: 800 })}
    <rect x="${X(x0 + 3.35)}" y="${Y(3.46)}" width="${SW(2.98)}" height="${SH(0.54)}" fill="#${C.pale}" stroke="#${C.line}" stroke-width="1.2"/>
    ${svgText("11,65%", X(x0 + 3.43), Y(3.8), 29, C.orange, { weight: 800 })}
    ${svgText(["scădere medie NIR", "observată în Setul 1"], X(x0 + 4.62), Y(3.7), 13, C.ink, { weight: 800 })}

    ${panel(r, 1.82, col, 2.25, "Materiale, filtre și principiu")}
    ${svgBullets(["Spectrometru: Ocean Optics USB2000+XR1-ES, interval λ = 200–1025 nm, rezoluție 1,7–2,1 nm, 2048 pixeli CCD.", "Camera: aceeași frunză este fotografiată prin filtre la 532, 556, 680, 725, 850 și 940 nm.", "Pentru fiecare imagine se detectează frunza, apoi se calculează mediana luminozității în masca frunzei."], X(r + 0.18), Y(2.44), 17, C.ink, 62)}
    ${svgWrapped("Punctele camerei nu sunt un spectru continuu, dar pot arăta dacă forma generală și variația NIR sunt apropiate de referință.", X(r + 0.18), Y(3.75), 15, C.muted, 62)}

    ${panel(x0, 4.3, 13.44, 2.45, "Sistem construit și fluxul de date")}
    ${svgImg(assets.mechanism, X(x0 + 0.25), Y(4.78), SW(2.55), SH(1.35))}
    ${svgImg(assets.camera, X(x0 + 3.08), Y(4.78), SW(2.32), SH(1.35))}
    ${svgImg(assets.app, X(x0 + 5.58), Y(4.77), SW(2.45), SH(1.37))}
    ${svgWrapped("Flux experimental: frunza este măsurată întâi cu spectrometrul, apoi fotografiată în cutie prin cele 6 filtre. Aplicația aliniază imaginile, găsește zona frunzei, elimină o parte din fundal prin mască și extrage valori mediane pentru fiecare bandă.", X(x0 + 8.25), Y(5.02), 16, C.ink, 58)}
    ${svgWrapped("Spectrometrul produce curba continuă de referință. Camera produce 6 puncte discrete; prin unirea lor se obține o aproximare a răspunsului spectral al frunzei.", X(x0 + 8.25), Y(5.86), 16, C.ink, 58)}

    ${panel(x0, 7.0, 13.44, 4.2, "Validare: spectrometru vs cameră")}
    ${svgImg(assets.validation, X(x0 + 0.35), Y(7.48), SW(8.4), SH(3.06))}
    ${svgWrapped("Comparația suprapune curbele continue ale spectrometrului cu punctele/curbele obținute din camera multispectrală. Pentru curba albastră, coeficientul de corelație este r = 0,982, iar pentru curba portocalie r = 0,967. Media indică o concordanță a formei de aproximativ 97,5%.", X(x0 + 9.0), Y(7.75), 16, C.ink, 48)}
    ${svgWrapped("Diferențele medii dintre cameră și spectrometru sunt 7,166% și 5,403%. Aceste valori sunt suficient de mici pentru un prototip educațional, deoarece sistemul nu trebuie să înlocuiască spectrometrul, ci să indice corect tendințele utile pentru sănătatea plantei.", X(x0 + 9.0), Y(9.0), 16, C.ink, 48)}
    ${svgWrapped("Formula de comparație folosită în interpretare: pentru fiecare bandă a camerei se compară valoarea mediană a luminozității frunzei cu intensitatea spectrometrului în jurul aceleiași lungimi de undă. Spectrometrul este netezit prin mediane pe intervale de 10 nm.", X(x0 + 9.0), Y(10.23), 14, C.muted, 52)}

    ${panel(x0, 11.45, 13.44, 4.65, "Rezultate: frunze sănătoase vs nesănătoase")}
    ${svgImg(assets.set1, X(x0 + 0.28), Y(11.9), SW(6.25), SH(3.1))}
    ${svgImg(assets.set2, X(x0 + 6.9), Y(11.9), SW(6.25), SH(3.1))}
    ${svgWrapped("Set 1: frunza nesănătoasă are semnal NIR mai mic. Spectrometrul indică o scădere de 10,7%, iar camera o scădere de 12,6%, deci diferența dintre metode este de doar 1,9 puncte procentuale.", X(x0 + 0.35), Y(15.34), 15, C.ink, 70)}
    ${svgWrapped("Set 2: diferența este detectată, dar camera comprimă amplitudinea. Acest rezultat arată că o etichetă simplă sănătos/nesănătos nu produce mereu aceeași formă spectrală și că este nevoie de mai multe probe.", X(x0 + 6.95), Y(15.34), 15, C.ink, 70)}

    ${panel(x0, 16.35, 13.44, 2.7, "Interpretare, limite și concluzie")}
    ${svgWrapped("Interpretarea corectă este că SpectraLeaf validează principiul de funcționare: o cameră cu filtre poate urmări forma generală a spectrului și poate evidenția diferențe relevante în NIR. Valoarea de 97,5% este o concordanță statistică față de spectrometru pentru datele analizate, nu o acuratețe universală de diagnostic.", X(x0 + 0.28), Y(17.04), 16, C.ink, 74)}
    ${svgWrapped("Au fost analizate 4 frunze: 2 sănătoase și 2 nesănătoase. Pentru rezultate finale ar fi necesare mai multe mostre, calibrare cu referințe alb/negru, control mai strict al iluminării și separarea tipurilor de stres: uscare, lipsă de apă, degradare mecanică sau variații naturale ale frunzei.", X(x0 + 6.9), Y(17.04), 16, C.ink, 74)}
    ${svgWrapped("Concluzie: sistemul este potrivit ca platformă experimentală low-cost pentru analiză multispectrală, iar rezultatele justifică dezvoltarea unei aplicații care să compare automat semnalul camerei cu măsurători de referință.", X(x0 + 0.28), Y(18.25), 17, C.header, 140, { weight: 800 })}

    ${panel(x0, 19.22, 13.44, 0.52, "Referințe")}
    ${svgText("[1] GoPhotonics, USB2000+XR1-ES – Ocean Optics.  [2] Ocean Optics, Legacy Spectrometers Support.  [3] Date experimentale SpectraLeaf: grafice spectrometru/cameră, imagini multispectrale și ieșiri ale aplicației.", X(x0 + 0.22), Y(19.67), 12, C.ink)}
  </svg>`;
  await sharp(Buffer.from(svg)).png().toFile(PNG_OUT);
}

async function main() {
  ensureDir(OUT_DIR);
  checkAssets();
  await createPptx();
  await createPreview();
  console.log(PPTX_OUT);
  console.log(PNG_OUT);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
