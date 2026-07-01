const fs = require("fs");
const path = require("path");
const Module = require("module");

const nodeModules = "C:\\Users\\david\\.cache\\codex-runtimes\\codex-primary-runtime\\dependencies\\node\\node_modules";
Module.globalPaths.push(nodeModules);

const pptxgen = require(path.join(nodeModules, "pptxgenjs"));
const sharp = require(path.join(nodeModules, "sharp"));

const OUT_DIR = "C:\\Users\\david\\OneDrive\\Desktop\\SpectraLeaf poster";
const GRAPH_DIR = "C:\\Users\\david\\OneDrive\\Desktop\\Spectral Leaf graphs for document\\graphs";
const MEDIA_DIR = "C:\\Users\\david\\OneDrive\\Desktop\\Archive\\Projects\\CodeX\\outputs\\poster_extract\\media";
const PPTX_OUT = path.join(OUT_DIR, "SpectraLeaf_scientific_poster.pptx");
const PNG_OUT = path.join(OUT_DIR, "SpectraLeaf_scientific_poster_preview.png");

const assets = {
  validation: path.join(GRAPH_DIR, "figure_1_set_1_camera_vs_spectrometer_overlay.png"),
  set1: path.join(GRAPH_DIR, "figure_2_set_1_health_comparison_side_by_side.png"),
  set2: path.join(GRAPH_DIR, "figure_2_set_2_health_comparison_side_by_side.png"),
  mechanism: path.join(MEDIA_DIR, "image4.png"),
  camera: path.join(MEDIA_DIR, "image6.png"),
  overlay: path.join(MEDIA_DIR, "image11.png"),
};

const W = 33.11;
const H = 23.39;
const C = {
  bg: "F7FAF5",
  ink: "1C2B24",
  muted: "52645C",
  faint: "E5EEE6",
  green: "2B7A4B",
  orange: "FF7F0E",
  blue: "1F77B4",
  paleOrange: "FFF0DF",
  paleBlue: "E9F4FC",
  white: "FFFFFF",
};

function ensureDir(p) {
  fs.mkdirSync(p, { recursive: true });
}

function addPanel(slide, x, y, w, h, opts = {}) {
  slide.addShape(pptx.ShapeType.roundRect, {
    x, y, w, h,
    rectRadius: 0.12,
    fill: { color: opts.fill || C.white, transparency: opts.transparency || 0 },
    line: { color: opts.line || C.faint, transparency: 0, width: opts.width || 1.0 },
  });
}

function addText(slide, txt, x, y, w, h, opts = {}) {
  slide.addText(txt, {
    x, y, w, h,
    fontFace: opts.fontFace || "Aptos",
    fontSize: opts.size || 20,
    color: opts.color || C.ink,
    bold: opts.bold || false,
    italic: opts.italic || false,
    margin: opts.margin || 0,
    breakLine: false,
    valign: opts.valign || "top",
    fit: "shrink",
    align: opts.align || "left",
  });
}

async function imageFit(imgPath, x, y, w, h) {
  const meta = await sharp(imgPath).metadata();
  const ar = meta.width / meta.height;
  const boxAr = w / h;
  let iw = w, ih = h, ix = x, iy = y;
  if (ar > boxAr) {
    iw = w;
    ih = w / ar;
    iy = y + (h - ih) / 2;
  } else {
    ih = h;
    iw = h * ar;
    ix = x + (w - iw) / 2;
  }
  return { x: ix, y: iy, w: iw, h: ih };
}

async function addImageContain(slide, imgPath, x, y, w, h) {
  const fit = await imageFit(imgPath, x, y, w, h);
  slide.addImage({ path: imgPath, ...fit });
}

function addSectionTitle(slide, title, x, y, w, accent = C.green) {
  slide.addShape(pptx.ShapeType.rect, { x, y: y + 0.1, w: 0.12, h: 0.34, fill: { color: accent }, line: { color: accent } });
  addText(slide, title, x + 0.25, y, w - 0.25, 0.5, { size: 18, bold: true, color: C.ink });
}

function addBullets(slide, lines, x, y, w, h, opts = {}) {
  addText(slide, lines.map((l) => `• ${l}`).join("\n"), x, y, w, h, {
    size: opts.size || 14.5,
    color: opts.color || C.muted,
    margin: 0,
  });
}

async function createPptx() {
  const pptx = new pptxgen();
  pptx.author = "SpectraLeaf";
  pptx.subject = "SpectraLeaf scientific poster";
  pptx.title = "SpectraLeaf scientific poster";
  pptx.company = "SpectraLeaf";
  pptx.lang = "ro-RO";
  pptx.layout = "LAYOUT_CUSTOM";
  pptx.defineLayout({ name: "A1_LANDSCAPE", width: W, height: H });
  pptx.layout = "A1_LANDSCAPE";
  pptx.theme = {
    headFontFace: "Aptos Display",
    bodyFontFace: "Aptos",
    lang: "ro-RO",
  };

  const slide = pptx.addSlide();
  slide.background = { color: C.bg };

  // Header
  slide.addShape(pptx.ShapeType.rect, { x: 0, y: 0, w: W, h: 2.9, fill: { color: "ECF6ED" }, line: { color: "ECF6ED" } });
  slide.addShape(pptx.ShapeType.rect, { x: 0, y: 2.82, w: W, h: 0.08, fill: { color: C.green }, line: { color: C.green } });
  addText(slide, "SpectraLeaf", 0.65, 0.35, 7.5, 0.8, { size: 42, bold: true, color: C.green, fontFace: "Aptos Display" });
  addText(slide, "Sistem optic multispectral bazat pe NIR pentru detecția timpurie a stresului vegetal", 0.68, 1.25, 18.2, 0.55, { size: 20, color: C.ink });
  addText(slide, "camera + 6 filtre optice  |  validare cu spectrometru Ocean Optics USB2000+XR1-ES", 0.68, 1.92, 18.6, 0.42, { size: 13.8, color: C.muted });
  addPanel(slide, 22.1, 0.44, 4.7, 1.7, { fill: C.paleBlue, line: "B7D7EE" });
  addText(slide, "97,5%", 22.45, 0.58, 1.8, 0.62, { size: 31, bold: true, color: C.blue });
  addText(slide, "concordanță medie\na formei curbelor", 24.18, 0.62, 2.2, 0.9, { size: 12.2, color: C.ink });
  addPanel(slide, 27.25, 0.44, 5.2, 1.7, { fill: C.paleOrange, line: "FFD0A0" });
  addText(slide, "11,65%", 27.6, 0.58, 1.9, 0.62, { size: 31, bold: true, color: C.orange });
  addText(slide, "scădere medie NIR\nîn Setul 1", 29.46, 0.62, 2.35, 0.9, { size: 12.2, color: C.ink });

  // Left method panel
  addPanel(slide, 0.65, 3.35, 8.55, 8.8, { fill: C.white });
  addSectionTitle(slide, "Scop și principiu", 1.0, 3.75, 7.8, C.green);
  addBullets(slide, [
    "Detectarea diferențelor spectrale dintre frunze sănătoase și frunze afectate.",
    "Domeniul NIR (>700 nm) este sensibil la structura internă și starea fiziologică a frunzei.",
    "Camera cu filtre produce puncte discrete care aproximează curba spectrală continuă.",
  ], 1.05, 4.35, 7.6, 1.75, { size: 13.2 });
  addSectionTitle(slide, "Achiziție experimentală", 1.0, 6.55, 7.8, C.blue);
  addText(slide, "1  spectrometru: curbă continuă λ = 200–1025 nm\n2  cameră în cutie: 532, 556, 680, 725, 850, 940 nm\n3  mască frunză + mediană pixelilor\n4  comparație cameră vs spectrometru", 1.05, 7.12, 7.55, 1.8, { size: 13.6, color: C.ink });
  addSectionTitle(slide, "Referință: USB2000+XR1-ES", 1.0, 9.4, 7.8, C.orange);
  addText(slide, "• spectrometru UV–NIR portabil\n• 2048 pixeli CCD Sony ILX511B\n• rezoluție spectrală 1,7–2,1 nm\n• integrare 1 ms – 65 s\n• USB 2.0, conector SMA 905", 1.05, 9.95, 4.25, 1.62, { size: 12.6, color: C.muted });
  addPanel(slide, 5.6, 9.85, 3.15, 1.78, { fill: "F8FAF5", line: C.faint });
  await addImageContain(slide, assets.mechanism, 5.78, 10.0, 2.8, 1.45);
  await addImageContain(slide, assets.camera, 5.75, 7.05, 2.85, 1.8);

  // Validation graph
  addPanel(slide, 9.65, 3.35, 22.8, 8.8, { fill: C.white });
  addSectionTitle(slide, "Validarea metodei: camera urmărește forma spectrometrului", 10.0, 3.75, 21.9, C.green);
  await addImageContain(slide, assets.validation, 10.0, 4.35, 21.95, 7.25);

  // Results row
  addPanel(slide, 0.65, 12.65, 15.82, 7.8, { fill: C.white });
  addSectionTitle(slide, "Set 1: diferență NIR clară", 1.0, 13.03, 15.0, C.orange);
  await addImageContain(slide, assets.set1, 0.95, 13.62, 15.18, 5.85);
  addText(slide, "În Setul 1, frunza nesănătoasă scade în NIR cu 10,7% la spectrometru și 12,6% la cameră.", 1.05, 19.58, 14.7, 0.5, { size: 12.5, color: C.ink });

  addPanel(slide, 16.78, 12.65, 15.67, 7.8, { fill: C.white });
  addSectionTitle(slide, "Set 2: diferență detectată, amplitudine diferită", 17.13, 13.03, 14.9, C.blue);
  await addImageContain(slide, assets.set2, 17.05, 13.62, 15.08, 5.85);
  addText(slide, "În Setul 2, ambele metode detectează aceeași direcție generală, dar camera comprimă amplitudinea diferenței.", 17.15, 19.58, 14.5, 0.5, { size: 12.5, color: C.ink });

  // Bottom conclusion strip
  addPanel(slide, 0.65, 20.82, 31.8, 1.95, { fill: "F0F7F1", line: "CFE3D1" });
  addText(slide, "Concluzie", 1.0, 21.1, 2.6, 0.4, { size: 18, bold: true, color: C.green });
  addText(slide, "SpectraLeaf poate evidenția diferențe relevante în domeniul NIR și urmărește foarte bine forma curbei de referință. Au fost analizate 4 frunze: două sănătoase și două nesănătoase. Rezultatele confirmă fezabilitatea sistemului, iar direcțiile următoare sunt extinderea bazei de date, controlul iluminării și calibrarea cu referințe alb/negru.", 3.55, 20.98, 21.2, 0.95, { size: 13.2, color: C.ink });
  addText(slide, "SPECTRAL LEAF", 26.1, 21.08, 4.1, 0.5, { size: 22, bold: true, color: C.green, align: "right" });
  addText(slide, "prototip educațional low-cost", 26.0, 21.68, 4.2, 0.35, { size: 10.8, color: C.muted, align: "right" });

  await pptx.writeFile({ fileName: PPTX_OUT });
}

function esc(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function imgDataUri(imgPath) {
  const ext = path.extname(imgPath).slice(1).toLowerCase().replace("jpg", "jpeg");
  const data = fs.readFileSync(imgPath).toString("base64");
  return `data:image/${ext};base64,${data}`;
}

function imageSvg(imgPath, x, y, w, h) {
  return `<image href="${imgDataUri(imgPath)}" x="${x}" y="${y}" width="${w}" height="${h}" preserveAspectRatio="xMidYMid meet"/>`;
}

function textSvg(lines, x, y, size, color, weight = 400, lineH = 1.25, anchor = "start") {
  const arr = Array.isArray(lines) ? lines : String(lines).split("\n");
  return `<text x="${x}" y="${y}" font-family="Aptos, Arial, sans-serif" font-size="${size}" fill="#${color}" font-weight="${weight}" text-anchor="${anchor}">${arr.map((line, i) => `<tspan x="${x}" dy="${i === 0 ? 0 : size * lineH}">${esc(line)}</tspan>`).join("")}</text>`;
}

function panelSvg(x, y, w, h, fill = C.white, stroke = C.faint) {
  return `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="20" fill="#${fill}" stroke="#${stroke}" stroke-width="2"/>`;
}

async function createPreviewPng() {
  const pw = 4967;
  const ph = 3508;
  const sx = pw / W;
  const sy = ph / H;
  const X = (v) => Math.round(v * sx);
  const Y = (v) => Math.round(v * sy);
  const S = (v) => Math.round(v * sx);
  const T = (v) => Math.round(v * sy);
  let svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${pw}" height="${ph}" viewBox="0 0 ${pw} ${ph}">
    <rect width="${pw}" height="${ph}" fill="#${C.bg}"/>
    <rect x="0" y="0" width="${pw}" height="${Y(2.9)}" fill="#ECF6ED"/>
    <rect x="0" y="${Y(2.82)}" width="${pw}" height="${Y(0.08)}" fill="#${C.green}"/>
    ${textSvg("SpectraLeaf", X(0.65), Y(0.95), 118, C.green, 800, 1.15)}
    ${textSvg("Sistem optic multispectral bazat pe NIR pentru detecția timpurie a stresului vegetal", X(0.68), Y(1.72), 48, C.ink, 400)}
    ${textSvg("camera + 6 filtre optice  |  validare cu spectrometru Ocean Optics USB2000+XR1-ES", X(0.68), Y(2.22), 32, C.muted, 400)}
    ${panelSvg(X(22.1), Y(0.44), S(4.7), T(1.7), C.paleBlue, "B7D7EE")}
    ${textSvg("97,5%", X(22.45), Y(1.08), 78, C.blue, 800)}
    ${textSvg(["concordanță medie", "a formei curbelor"], X(24.18), Y(0.95), 31, C.ink, 500)}
    ${panelSvg(X(27.25), Y(0.44), S(5.2), T(1.7), C.paleOrange, "FFD0A0")}
    ${textSvg("11,65%", X(27.6), Y(1.08), 78, C.orange, 800)}
    ${textSvg(["scădere medie NIR", "în Setul 1"], X(29.46), Y(0.95), 31, C.ink, 500)}
    ${panelSvg(X(0.65), Y(3.35), S(8.55), T(8.8))}
    ${textSvg("Scop și principiu", X(1.0), Y(4.1), 38, C.ink, 800)}
    ${textSvg(["• Detectarea diferențelor spectrale între frunze sănătoase și afectate.", "• NIR (>700 nm) este sensibil la structura internă a frunzei.", "• Camera cu filtre aproximează curba spectrală prin 6 puncte."], X(1.05), Y(4.8), 31, C.muted, 400)}
    ${textSvg("Achiziție experimentală", X(1.0), Y(7.0), 38, C.ink, 800)}
    ${textSvg(["1  spectrometru: curbă continuă λ = 200–1025 nm", "2  cameră în cutie: 532, 556, 680, 725, 850, 940 nm", "3  mască frunză + mediană pixelilor", "4  comparație cameră vs spectrometru"], X(1.05), Y(7.62), 31, C.ink, 400)}
    ${textSvg("Referință: USB2000+XR1-ES", X(1.0), Y(9.82), 37, C.ink, 800)}
    ${textSvg(["• spectrometru UV–NIR portabil", "• 2048 pixeli CCD Sony ILX511B", "• rezoluție spectrală 1,7–2,1 nm", "• integrare 1 ms – 65 s", "• USB 2.0, conector SMA 905"], X(1.05), Y(10.45), 27, C.muted, 400)}
    ${imageSvg(assets.mechanism, X(5.78), Y(10.0), S(2.8), T(1.45))}
    ${imageSvg(assets.camera, X(5.75), Y(7.05), S(2.85), T(1.8))}
    ${panelSvg(X(9.65), Y(3.35), S(22.8), T(8.8))}
    ${textSvg("Validarea metodei: camera urmărește forma spectrometrului", X(10.0), Y(4.1), 38, C.ink, 800)}
    ${imageSvg(assets.validation, X(10.0), Y(4.35), S(21.95), T(7.25))}
    ${panelSvg(X(0.65), Y(12.65), S(15.82), T(7.8))}
    ${textSvg("Set 1: diferență NIR clară", X(1.0), Y(13.38), 38, C.ink, 800)}
    ${imageSvg(assets.set1, X(0.95), Y(13.62), S(15.18), T(5.85))}
    ${textSvg("Frunza nesănătoasă scade în NIR cu 10,7% la spectrometru și 12,6% la cameră.", X(1.05), Y(20.02), 28, C.ink, 400)}
    ${panelSvg(X(16.78), Y(12.65), S(15.67), T(7.8))}
    ${textSvg("Set 2: diferență detectată, amplitudine diferită", X(17.13), Y(13.38), 38, C.ink, 800)}
    ${imageSvg(assets.set2, X(17.05), Y(13.62), S(15.08), T(5.85))}
    ${textSvg("Ambele metode detectează direcția generală, dar camera comprimă amplitudinea diferenței.", X(17.15), Y(20.02), 28, C.ink, 400)}
    ${panelSvg(X(0.65), Y(20.82), S(31.8), T(1.95), "F0F7F1", "CFE3D1")}
    ${textSvg("Concluzie", X(1.0), Y(21.45), 41, C.green, 800)}
    ${textSvg("SpectraLeaf poate evidenția diferențe relevante în domeniul NIR și urmărește foarte bine forma curbei de referință. Au fost analizate 4 frunze: două sănătoase și două nesănătoase. Rezultatele confirmă fezabilitatea sistemului, iar direcțiile următoare sunt extinderea bazei de date, controlul iluminării și calibrarea cu referințe alb/negru.", X(3.55), Y(21.32), 31, C.ink, 400)}
    ${textSvg("SPECTRAL LEAF", X(30.2), Y(21.5), 50, C.green, 800, 1.15, "end")}
    ${textSvg("prototip educațional low-cost", X(30.2), Y(22.05), 25, C.muted, 400, 1.15, "end")}
  </svg>`;

  await sharp(Buffer.from(svg)).png().toFile(PNG_OUT);
}

async function main() {
  ensureDir(OUT_DIR);
  await createPptx();
  await createPreviewPng();
  console.log(PPTX_OUT);
  console.log(PNG_OUT);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
