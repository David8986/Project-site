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
const PPTX_OUT = path.join(OUT_DIR, "SpectraLeaf_conference_poster.pptx");
const PNG_OUT = path.join(OUT_DIR, "SpectraLeaf_conference_poster_preview.png");

const assets = {
  validation: path.join(GRAPH_DIR, "figure_1_set_1_camera_vs_spectrometer_overlay.png"),
  set1: path.join(GRAPH_DIR, "figure_2_set_1_health_comparison_side_by_side.png"),
  set2: path.join(GRAPH_DIR, "figure_2_set_2_health_comparison_side_by_side.png"),
  mechanism: path.join(MEDIA_DIR, "image4.png"),
  camera: path.join(MEDIA_DIR, "image6.png"),
  app: path.join(MEDIA_DIR, "image11.png"),
};

const W = 33.11;
const H = 23.39;
const PX_W = 4967;
const PX_H = 3508;

const C = {
  bg: "EAF2F4",
  header: "0F5D73",
  header2: "0A4F63",
  bar: "10647A",
  ink: "18323A",
  muted: "49636B",
  line: "B9D0D6",
  panel: "FFFFFF",
  pale: "F6FAFB",
  blue: "1F77B4",
  orange: "FF7F0E",
  green: "23925F",
  red: "D62728",
};

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true });
}

function safeExists(file) {
  if (!fs.existsSync(file)) throw new Error(`Missing asset: ${file}`);
}

function addText(slide, text, x, y, w, h, opts = {}) {
  slide.addText(text, {
    x, y, w, h,
    fontFace: opts.fontFace || "Aptos",
    fontSize: opts.size || 12,
    color: opts.color || C.ink,
    bold: Boolean(opts.bold),
    italic: Boolean(opts.italic),
    align: opts.align || "left",
    valign: opts.valign || "top",
    margin: opts.margin ?? 0.04,
    fit: "shrink",
    breakLine: false,
    paraSpaceAfterPt: opts.paraSpaceAfterPt ?? 2,
    breakLine: false,
  });
}

function addPanel(slide, x, y, w, h) {
  slide.addShape("rect", {
    x, y, w, h,
    fill: { color: C.panel },
    line: { color: C.line, width: 1.0 },
  });
}

function addSection(slide, title, x, y, w, h) {
  addPanel(slide, x, y, w, h);
  slide.addShape("rect", {
    x, y, w, h: 0.38,
    fill: { color: C.bar },
    line: { color: C.bar },
  });
  addText(slide, title, x + 0.14, y + 0.07, w - 0.28, 0.22, {
    size: 10.5,
    bold: true,
    color: "FFFFFF",
    align: "center",
    margin: 0,
  });
}

function addBullets(slide, lines, x, y, w, h, opts = {}) {
  const bulletText = lines.map((line) => `• ${line}`).join("\n");
  addText(slide, bulletText, x, y, w, h, {
    size: opts.size || 9.3,
    color: opts.color || C.ink,
    margin: 0.03,
    paraSpaceAfterPt: 1,
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
  const fit = await fitImage(imgPath, x, y, w, h);
  slide.addImage({ path: imgPath, ...fit });
}

function addMetric(slide, label, value, note, x, y, w, color) {
  slide.addShape("rect", {
    x, y, w, h: 0.95,
    fill: { color: "F4FAFC" },
    line: { color: C.line, width: 0.8 },
  });
  addText(slide, value, x + 0.12, y + 0.14, 1.55, 0.35, {
    size: 18,
    bold: true,
    color,
    margin: 0,
  });
  addText(slide, label, x + 1.72, y + 0.12, w - 1.86, 0.24, {
    size: 7.8,
    bold: true,
    color: C.ink,
    margin: 0,
  });
  addText(slide, note, x + 1.72, y + 0.43, w - 1.86, 0.32, {
    size: 7.5,
    color: C.muted,
    margin: 0,
  });
}

function imgDataUri(imgPath) {
  const ext = path.extname(imgPath).slice(1).toLowerCase().replace("jpg", "jpeg");
  return `data:image/${ext};base64,${fs.readFileSync(imgPath).toString("base64")}`;
}

function esc(text) {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function wrapLines(text, maxChars) {
  const words = String(text).split(/\s+/);
  const out = [];
  let line = "";
  for (const word of words) {
    const next = line ? `${line} ${word}` : word;
    if (next.length > maxChars && line) {
      out.push(line);
      line = word;
    } else {
      line = next;
    }
  }
  if (line) out.push(line);
  return out;
}

function svgText(text, x, y, size, color, opts = {}) {
  const lines = Array.isArray(text) ? text : String(text).split("\n");
  const weight = opts.weight || 400;
  const anchor = opts.anchor || "start";
  const lh = opts.lineHeight || 1.22;
  const family = opts.family || "Aptos, Arial, sans-serif";
  return `<text x="${x}" y="${y}" font-family="${family}" font-size="${size}" fill="#${color}" font-weight="${weight}" text-anchor="${anchor}">${lines.map((line, i) => `<tspan x="${x}" dy="${i === 0 ? 0 : size * lh}">${esc(line)}</tspan>`).join("")}</text>`;
}

function svgWrapped(text, x, y, size, color, maxChars, opts = {}) {
  return svgText(wrapLines(text, maxChars), x, y, size, color, opts);
}

function svgBullets(lines, x, y, size, color, maxChars) {
  const all = [];
  for (const line of lines) {
    const wrapped = wrapLines(line, maxChars);
    wrapped.forEach((part, idx) => all.push(idx === 0 ? `• ${part}` : `  ${part}`));
  }
  return svgText(all, x, y, size, color, { lineHeight: 1.22 });
}

function svgPanel(x, y, w, h, title) {
  return `
    <rect x="${x}" y="${y}" width="${w}" height="${h}" fill="#${C.panel}" stroke="#${C.line}" stroke-width="2"/>
    <rect x="${x}" y="${y}" width="${w}" height="57" fill="#${C.bar}"/>
    ${svgText(title, x + w / 2, y + 37, 27, "FFFFFF", { weight: 800, anchor: "middle" })}
  `;
}

function svgImg(imgPath, x, y, w, h) {
  return `<image href="${imgDataUri(imgPath)}" x="${x}" y="${y}" width="${w}" height="${h}" preserveAspectRatio="xMidYMid meet"/>`;
}

async function createPptx() {
  Object.values(assets).forEach(safeExists);
  const pptx = new pptxgen();
  pptx.author = "SpectraLeaf";
  pptx.subject = "Poster științific SpectraLeaf";
  pptx.title = "SpectraLeaf conference poster";
  pptx.company = "SpectraLeaf";
  pptx.lang = "ro-RO";
  pptx.defineLayout({ name: "A1_LANDSCAPE", width: W, height: H });
  pptx.layout = "A1_LANDSCAPE";
  pptx.theme = {
    headFontFace: "Aptos Display",
    bodyFontFace: "Aptos",
    lang: "ro-RO",
  };

  const slide = pptx.addSlide();
  slide.background = { color: C.bg };

  slide.addShape("rect", { x: 0.14, y: 0.12, w: 32.83, h: 1.72, fill: { color: C.header }, line: { color: C.header } });
  addText(slide, "SpectraLeaf: Sistem optic multispectral bazat pe NIR pentru detecția stresului vegetal", 0.55, 0.34, 25.7, 0.48, {
    size: 25,
    bold: true,
    color: "FFFFFF",
    fontFace: "Aptos Display",
    margin: 0,
  });
  addText(slide, "Validarea unui sistem low-cost cu cameră și filtre optice prin comparație cu spectrometrul Ocean Optics USB2000+XR1-ES", 0.57, 0.93, 24.8, 0.28, {
    size: 11.2,
    color: "E8F6F9",
    margin: 0,
  });
  addText(slide, "SPECTRAL LEAF", 28.3, 0.48, 3.6, 0.34, { size: 14.5, bold: true, color: "FFFFFF", align: "right", margin: 0 });
  addText(slide, "camera + 6 filtre: 532 / 556 / 680 / 725 / 850 / 940 nm", 24.7, 1.07, 7.15, 0.24, { size: 8.6, color: "D6EEF3", align: "right", margin: 0 });

  const l = 0.38;
  const gap = 0.28;
  const colW = (W - 2 * l - 2 * gap) / 3;
  const c1 = l;
  const c2 = l + colW + gap;
  const c3 = l + 2 * (colW + gap);
  const y0 = 2.12;

  addSection(slide, "Introducere", c1, y0, colW, 3.85);
  addBullets(slide, [
    "Multe tipuri de stres vegetal modifică reflectanța înainte ca simptomele să fie vizibile în RGB.",
    "În zona red-edge și NIR, răspunsul frunzei este legat de structura internă, apă și degradare fiziologică.",
    "Scopul proiectului este un sistem multispectral accesibil, potrivit pentru laborator educațional.",
  ], c1 + 0.25, y0 + 0.62, colW - 0.5, 1.7, { size: 8.9 });
  addMetric(slide, "concordanță medie a formei curbelor", "97,5%", "cameră vs spectrometru", c1 + 0.25, y0 + 2.58, 4.9, C.blue);
  addMetric(slide, "scădere NIR în Setul 1", "11,65%", "media estimărilor cameră/spectrometru", c1 + 5.35, y0 + 2.58, 5.0, C.orange);

  addSection(slide, "Întrebarea de cercetare", c1, 6.22, colW, 2.45);
  addText(slide, "Poate o cameră cu șase filtre optice să reproducă suficient de bine informația spectrală relevantă măsurată de un spectrometru, astfel încât să diferențieze frunze sănătoase de frunze afectate?", c1 + 0.32, 6.9, colW - 0.64, 0.9, {
    size: 11.2,
    bold: true,
    color: C.ink,
    margin: 0.03,
  });
  addText(slide, "Ipoteză: forma curbei obținute din cele 6 puncte ale camerei trebuie să urmeze curba continuă a spectrometrului, mai ales peste 700 nm.", c1 + 0.32, 7.84, colW - 0.64, 0.45, { size: 8.3, color: C.muted, margin: 0.03 });

  addSection(slide, "Sistem optic și aplicație", c1, 8.93, colW, 6.08);
  await addImage(slide, assets.mechanism, c1 + 0.28, 9.53, 4.7, 2.45);
  await addImage(slide, assets.camera, c1 + 5.22, 9.53, 4.95, 2.45);
  addBullets(slide, [
    "Filtrele sunt poziționate succesiv în fața camerei pentru aceeași frunză.",
    "Aplicația detectează zona frunzei, calculează medianele pixelilor și compară benzile.",
    "Pentru validare, spectrometrul este tratat ca referință experimentală.",
  ], c1 + 0.28, 12.22, colW - 0.56, 1.18, { size: 8.4 });
  await addImage(slide, assets.app, c1 + 0.55, 13.43, colW - 1.1, 1.25);

  addSection(slide, "Materiale și metode", c2, y0, colW, 4.7);
  addBullets(slide, [
    "Spectrometru Ocean Optics USB2000+XR1-ES: λ = 200–1025 nm, rezoluție 1,7–2,1 nm, detector CCD liniar Sony ILX511B, 2048 pixeli.",
    "Sistem cameră: cutie de măsurare, iluminare controlată, filtre optice la 532, 556, 680, 725, 850 și 940 nm.",
    "Datele spectrometrului sunt reprezentate de la aproximativ 300 nm pentru a evita zona foarte zgomotoasă.",
    "Comparația se face pe forma curbei și pe media semnalului în NIR, peste 700 nm.",
  ], c2 + 0.27, y0 + 0.65, colW - 0.54, 2.25, { size: 8.45 });
  addText(slide, "Flux de lucru", c2 + 0.3, y0 + 3.16, 2.2, 0.28, { size: 10.2, bold: true, color: C.header, margin: 0 });
  addText(slide, "frunză → spectrometru → cameră cu filtre → mască frunză → mediane → grafice comparative", c2 + 2.38, y0 + 3.16, colW - 2.7, 0.3, { size: 8.4, color: C.ink, margin: 0 });

  addSection(slide, "Validare: spectrometru vs cameră", c2, 7.08, colW, 7.93);
  await addImage(slide, assets.validation, c2 + 0.28, 7.72, colW - 0.56, 5.55);
  addText(slide, "Coeficienții r = 0,982 și r = 0,967 arată că sistemul cu cameră urmărește foarte bine forma spectrului de referință. Diferențele medii rămân reduse pentru un prototip low-cost: 7,166% și 5,403%.", c2 + 0.34, 13.48, colW - 0.68, 0.62, { size: 8.35, color: C.ink });

  addSection(slide, "Rezultate principale", c3, y0, colW, 4.9);
  addText(slide, "Diferențele dintre frunzele sănătoase și nesănătoase apar cel mai clar în domeniul NIR. Camera reproduce bine tendința generală, dar poate comprima amplitudinea diferenței față de spectrometru.", c3 + 0.3, y0 + 0.72, colW - 0.6, 0.95, { size: 9.0, color: C.ink, margin: 0.03 });
  addMetric(slide, "Set 1 spectrometru", "10,7%", "frunza nesănătoasă mai joasă peste 700 nm", c3 + 0.3, y0 + 2.05, 4.85, C.blue);
  addMetric(slide, "Set 1 cameră", "12,6%", "frunza nesănătoasă mai joasă peste 700 nm", c3 + 5.33, y0 + 2.05, 4.85, C.orange);
  addMetric(slide, "Set 2 spectrometru", "11,1%", "diferență detectată în sens invers", c3 + 0.3, y0 + 3.18, 4.85, C.blue);
  addMetric(slide, "Set 2 cameră", "1,4%", "aceeași direcție, amplitudine comprimată", c3 + 5.33, y0 + 3.18, 4.85, C.orange);

  addSection(slide, "Discuție", c3, 7.3, colW, 3.15);
  addBullets(slide, [
    "Rezultatul nu este o acuratețe universală de diagnostic, ci o validare experimentală a concordanței cameră–spectrometru.",
    "Eticheta „nesănătos” poate include cauze diferite: apă, degradare mecanică, uscare, textură sau poziționare.",
    "Următorul pas este calibrarea cu referințe alb/negru și extinderea setului de frunze.",
  ], c3 + 0.28, 7.93, colW - 0.56, 1.65, { size: 8.15 });

  addSection(slide, "Concluzii", c3, 10.72, colW, 4.29);
  addBullets(slide, [
    "SpectraLeaf poate evidenția diferențe relevante în NIR cu un ansamblu optic mult mai ieftin decât un sistem multispectral comercial.",
    "Forma curbei obținute cu camera are o concordanță medie de aproximativ 97,5% față de spectrometru.",
    "Au fost analizate 4 frunze: 2 sănătoase și 2 nesănătoase; rezultatele susțin fezabilitatea, nu încă un diagnostic final.",
  ], c3 + 0.28, 11.32, colW - 0.56, 1.55, { size: 8.35 });
  addText(slide, "Direcții viitoare: mai multe mostre, iluminare mai stabilă, corecție cu referințe, antrenarea unui model de clasificare.", c3 + 0.3, 13.52, colW - 0.6, 0.4, { size: 8.1, color: C.muted, margin: 0.02 });

  addSection(slide, "Seturi experimentale: sănătos vs nesănătos", c1, 15.32, 21.88, 6.72);
  await addImage(slide, assets.set1, c1 + 0.28, 15.92, 10.45, 4.95);
  await addImage(slide, assets.set2, c1 + 11.05, 15.92, 10.45, 4.95);
  addText(slide, "Set 1: camera confirmă scăderea NIR a frunzei nesănătoase aproape la același procent ca spectrometrul.", c1 + 0.4, 21.1, 9.8, 0.34, { size: 8.0, color: C.ink, margin: 0 });
  addText(slide, "Set 2: diferența există, dar camera o comprimă; acest lucru indică necesitatea unui set de date mai mare.", c1 + 11.25, 21.1, 9.8, 0.34, { size: 8.0, color: C.ink, margin: 0 });

  addSection(slide, "Referințe", c3, 15.32, colW, 4.78);
  addText(slide, "[1] GoPhotonics, USB2000+XR1-ES – Ocean Optics, fișă tehnică.\n[2] Ocean Optics, Legacy Spectrometers Support.\n[3] Date experimentale SpectraLeaf: imagini multispectrale, grafice spectrometru/cameră și ieșiri ale aplicației.\n[4] Literatură generală privind NDVI, NDRE, GNDVI, CIre și reflectanța vegetației în NIR.", c3 + 0.28, 15.95, colW - 0.56, 2.2, { size: 7.6, color: C.ink, margin: 0.02 });
  slide.addShape("rect", { x: c3 + 0.28, y: 18.5, w: colW - 0.56, h: 1.18, fill: { color: "F4FAFC" }, line: { color: C.line } });
  addText(slide, "Mesaj-cheie", c3 + 0.48, 18.68, 1.7, 0.24, { size: 8.7, bold: true, color: C.header, margin: 0 });
  addText(slide, "Sistemul construit nu înlocuiește spectrometrul, dar reproduce suficient de bine semnalele relevante pentru a justifica o platformă multispectrală educațională.", c3 + 2.15, 18.63, colW - 2.55, 0.44, { size: 7.7, color: C.ink, margin: 0 });

  slide.addShape("rect", { x: 0.14, y: 22.45, w: 32.83, h: 0.28, fill: { color: C.header2 }, line: { color: C.header2 } });
  addText(slide, "SpectraLeaf | poster generat din lucrarea științifică și graficele experimentale", 0.45, 22.52, 20, 0.18, { size: 6.8, color: "FFFFFF", margin: 0 });
  addText(slide, "λ = 200–1025 nm spectrometru | 532–940 nm cameră", 25.0, 22.52, 7.45, 0.18, { size: 6.8, color: "FFFFFF", align: "right", margin: 0 });

  await pptx.writeFile({ fileName: PPTX_OUT });
}

async function createPreviewPng() {
  const X = (v) => Math.round((v / W) * PX_W);
  const Y = (v) => Math.round((v / H) * PX_H);
  const SW = (v) => Math.round((v / W) * PX_W);
  const SH = (v) => Math.round((v / H) * PX_H);
  const colW = (W - 2 * 0.38 - 2 * 0.28) / 3;
  const c1 = 0.38;
  const c2 = 0.38 + colW + 0.28;
  const c3 = 0.38 + 2 * (colW + 0.28);
  const p = (x, y, w, h, title) => svgPanel(X(x), Y(y), SW(w), SH(h), title);

  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${PX_W}" height="${PX_H}" viewBox="0 0 ${PX_W} ${PX_H}">
    <rect width="${PX_W}" height="${PX_H}" fill="#${C.bg}"/>
    <rect x="${X(0.14)}" y="${Y(0.12)}" width="${SW(32.83)}" height="${SH(1.72)}" fill="#${C.header}"/>
    ${svgText("SpectraLeaf: Sistem optic multispectral bazat pe NIR pentru detecția stresului vegetal", X(0.55), Y(0.75), 52, "FFFFFF", { weight: 800 })}
    ${svgText("Validarea unui sistem low-cost cu cameră și filtre optice prin comparație cu spectrometrul Ocean Optics USB2000+XR1-ES", X(0.57), Y(1.18), 26, "E8F6F9")}
    ${svgText("SPECTRAL LEAF", X(31.9), Y(0.78), 33, "FFFFFF", { weight: 800, anchor: "end" })}
    ${svgText("camera + 6 filtre: 532 / 556 / 680 / 725 / 850 / 940 nm", X(31.9), Y(1.28), 20, "D6EEF3", { anchor: "end" })}

    ${p(c1, 2.12, colW, 3.85, "Introducere")}
    ${svgBullets(["Multe tipuri de stres vegetal modifică reflectanța înainte ca simptomele să fie vizibile în RGB.", "În red-edge și NIR, răspunsul frunzei este legat de structura internă, apă și degradare fiziologică.", "Scopul proiectului este un sistem multispectral accesibil, potrivit pentru laborator educațional."], X(c1 + 0.25), Y(2.95), 19, C.ink, 58)}
    <rect x="${X(c1 + 0.25)}" y="${Y(4.7)}" width="${SW(4.9)}" height="${SH(0.95)}" fill="#F4FAFC" stroke="#${C.line}" stroke-width="1.5"/>
    ${svgText("97,5%", X(c1 + 0.37), Y(5.17), 45, C.blue, { weight: 800 })}
    ${svgText(["concordanță medie", "cameră vs spectrometru"], X(c1 + 1.93), Y(5.0), 18, C.ink, { weight: 700 })}
    <rect x="${X(c1 + 5.35)}" y="${Y(4.7)}" width="${SW(5.0)}" height="${SH(0.95)}" fill="#F4FAFC" stroke="#${C.line}" stroke-width="1.5"/>
    ${svgText("11,65%", X(c1 + 5.47), Y(5.17), 41, C.orange, { weight: 800 })}
    ${svgText(["scădere NIR", "în Setul 1"], X(c1 + 7.12), Y(5.0), 18, C.ink, { weight: 700 })}

    ${p(c1, 6.22, colW, 2.45, "Întrebarea de cercetare")}
    ${svgWrapped("Poate o cameră cu șase filtre optice să reproducă suficient de bine informația spectrală relevantă măsurată de un spectrometru, astfel încât să diferențieze frunze sănătoase de frunze afectate?", X(c1 + 0.32), Y(7.02), 25, C.ink, 74, { weight: 800 })}
    ${svgWrapped("Ipoteză: forma curbei obținute din cele 6 puncte ale camerei trebuie să urmeze curba continuă a spectrometrului, mai ales peste 700 nm.", X(c1 + 0.32), Y(8.1), 18, C.muted, 90)}

    ${p(c1, 8.93, colW, 6.08, "Sistem optic și aplicație")}
    ${svgImg(assets.mechanism, X(c1 + 0.28), Y(9.53), SW(4.7), SH(2.45))}
    ${svgImg(assets.camera, X(c1 + 5.22), Y(9.53), SW(4.95), SH(2.45))}
    ${svgBullets(["Filtrele sunt poziționate succesiv în fața camerei pentru aceeași frunză.", "Aplicația detectează zona frunzei, calculează medianele pixelilor și compară benzile.", "Spectrometrul este tratat ca referință experimentală."], X(c1 + 0.28), Y(12.45), 18, C.ink, 82)}
    ${svgImg(assets.app, X(c1 + 0.55), Y(13.43), SW(colW - 1.1), SH(1.25))}

    ${p(c2, 2.12, colW, 4.7, "Materiale și metode")}
    ${svgBullets(["Spectrometru Ocean Optics USB2000+XR1-ES: λ = 200–1025 nm, rezoluție 1,7–2,1 nm, detector CCD liniar Sony ILX511B, 2048 pixeli.", "Sistem cameră: cutie de măsurare, iluminare controlată, filtre optice la 532, 556, 680, 725, 850 și 940 nm.", "Datele spectrometrului sunt reprezentate de la aproximativ 300 nm pentru a evita zona foarte zgomotoasă.", "Comparația se face pe forma curbei și pe media semnalului în NIR, peste 700 nm."], X(c2 + 0.27), Y(2.93), 18, C.ink, 83)}
    ${svgText("Flux de lucru", X(c2 + 0.3), Y(5.5), 23, C.header, { weight: 800 })}
    ${svgText("frunză → spectrometru → cameră cu filtre → mască frunză → mediane → grafice comparative", X(c2 + 2.38), Y(5.5), 18, C.ink)}

    ${p(c2, 7.08, colW, 7.93, "Validare: spectrometru vs cameră")}
    ${svgImg(assets.validation, X(c2 + 0.28), Y(7.72), SW(colW - 0.56), SH(5.55))}
    ${svgWrapped("Coeficienții r = 0,982 și r = 0,967 arată că sistemul cu cameră urmărește foarte bine forma spectrului de referință. Diferențele medii rămân reduse pentru un prototip low-cost: 7,166% și 5,403%.", X(c2 + 0.34), Y(13.92), 18, C.ink, 90)}

    ${p(c3, 2.12, colW, 4.9, "Rezultate principale")}
    ${svgWrapped("Diferențele dintre frunzele sănătoase și nesănătoase apar cel mai clar în domeniul NIR. Camera reproduce bine tendința generală, dar poate comprima amplitudinea diferenței față de spectrometru.", X(c3 + 0.3), Y(2.97), 20, C.ink, 82)}
    ${svgText("10,7%", X(c3 + 0.42), Y(4.66), 42, C.blue, { weight: 800 })}
    ${svgText("12,6%", X(c3 + 5.45), Y(4.66), 42, C.orange, { weight: 800 })}
    ${svgText("Set 1 spectrometru", X(c3 + 2.0), Y(4.45), 18, C.ink, { weight: 700 })}
    ${svgText("Set 1 cameră", X(c3 + 7.02), Y(4.45), 18, C.ink, { weight: 700 })}
    ${svgText("11,1%", X(c3 + 0.42), Y(5.78), 42, C.blue, { weight: 800 })}
    ${svgText("1,4%", X(c3 + 5.45), Y(5.78), 42, C.orange, { weight: 800 })}
    ${svgText("Set 2 spectrometru", X(c3 + 2.0), Y(5.58), 18, C.ink, { weight: 700 })}
    ${svgText("Set 2 cameră", X(c3 + 7.02), Y(5.58), 18, C.ink, { weight: 700 })}

    ${p(c3, 7.3, colW, 3.15, "Discuție")}
    ${svgBullets(["Rezultatul nu este o acuratețe universală de diagnostic, ci o validare experimentală a concordanței cameră–spectrometru.", "Eticheta „nesănătos” poate include cauze diferite: apă, degradare mecanică, uscare, textură sau poziționare.", "Următorul pas este calibrarea cu referințe alb/negru și extinderea setului de frunze."], X(c3 + 0.28), Y(8.1), 18, C.ink, 82)}

    ${p(c3, 10.72, colW, 4.29, "Concluzii")}
    ${svgBullets(["SpectraLeaf poate evidenția diferențe relevante în NIR cu un ansamblu optic mult mai ieftin decât un sistem multispectral comercial.", "Forma curbei obținute cu camera are o concordanță medie de aproximativ 97,5% față de spectrometru.", "Au fost analizate 4 frunze: 2 sănătoase și 2 nesănătoase; rezultatele susțin fezabilitatea, nu încă un diagnostic final."], X(c3 + 0.28), Y(11.5), 18, C.ink, 82)}
    ${svgWrapped("Direcții viitoare: mai multe mostre, iluminare mai stabilă, corecție cu referințe, antrenarea unui model de clasificare.", X(c3 + 0.3), Y(14.0), 17, C.muted, 84)}

    ${p(c1, 15.32, 21.88, 6.72, "Seturi experimentale: sănătos vs nesănătos")}
    ${svgImg(assets.set1, X(c1 + 0.28), Y(15.92), SW(10.45), SH(4.95))}
    ${svgImg(assets.set2, X(c1 + 11.05), Y(15.92), SW(10.45), SH(4.95))}
    ${svgWrapped("Set 1: camera confirmă scăderea NIR a frunzei nesănătoase aproape la același procent ca spectrometrul.", X(c1 + 0.4), Y(21.42), 17, C.ink, 70)}
    ${svgWrapped("Set 2: diferența există, dar camera o comprimă; acest lucru indică necesitatea unui set de date mai mare.", X(c1 + 11.25), Y(21.42), 17, C.ink, 70)}

    ${p(c3, 15.32, colW, 4.78, "Referințe")}
    ${svgText(["[1] GoPhotonics, USB2000+XR1-ES – Ocean Optics, fișă tehnică.", "[2] Ocean Optics, Legacy Spectrometers Support.", "[3] Date experimentale SpectraLeaf: imagini, grafice și ieșiri ale aplicației.", "[4] Literatură generală privind NDVI, NDRE, GNDVI, CIre și reflectanța vegetației în NIR."], X(c3 + 0.28), Y(16.15), 17, C.ink)}
    <rect x="${X(c3 + 0.28)}" y="${Y(18.5)}" width="${SW(colW - 0.56)}" height="${SH(1.18)}" fill="#F4FAFC" stroke="#${C.line}" stroke-width="1.5"/>
    ${svgText("Mesaj-cheie", X(c3 + 0.48), Y(18.9), 19, C.header, { weight: 800 })}
    ${svgWrapped("Sistemul construit nu înlocuiește spectrometrul, dar reproduce suficient de bine semnalele relevante pentru a justifica o platformă multispectrală educațională.", X(c3 + 2.15), Y(18.85), 17, C.ink, 62)}

    <rect x="${X(0.14)}" y="${Y(22.45)}" width="${SW(32.83)}" height="${SH(0.28)}" fill="#${C.header2}"/>
    ${svgText("SpectraLeaf | poster generat din lucrarea științifică și graficele experimentale", X(0.45), Y(22.66), 16, "FFFFFF")}
    ${svgText("λ = 200–1025 nm spectrometru | 532–940 nm cameră", X(32.45), Y(22.66), 16, "FFFFFF", { anchor: "end" })}
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
