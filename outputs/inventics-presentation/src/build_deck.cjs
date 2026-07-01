const fs = require("node:fs");
const path = require("node:path");

const RUNTIME_NODE_MODULES =
  "C:/Users/david/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules";
const PptxGenJS = require(path.join(RUNTIME_NODE_MODULES, "pptxgenjs"));
const sharp = require(path.join(RUNTIME_NODE_MODULES, "sharp"));

const ROOT = path.resolve(__dirname, "..");
const OUTPUT_DIR = path.join(ROOT, "output");
const PREVIEW_DIR = path.join(ROOT, "preview");
const PPTX_PATH = path.join(OUTPUT_DIR, "Inventics_Pitch_Deck.pptx");
const CONTACT_SHEET_PATH = path.join(PREVIEW_DIR, "contact-sheet.png");
const MANIFEST_PATH = path.join(ROOT, "manifest.json");

const PPT_W = 13.333;
const PPT_H = 7.5;
const PREVIEW_W = 1600;
const PREVIEW_H = 900;

const COLORS = {
  navy: "0E1B2E",
  navySoft: "15314D",
  ink: "15263D",
  slate: "5E7086",
  line: "D8E3EC",
  light: "F7FAFC",
  mint: "DFF8F0",
  aqua: "68E2D3",
  teal: "12B8AE",
  tealDeep: "0A8F88",
  coral: "FF8A65",
  gold: "F3B83A",
  goldSoft: "FFE6A8",
  white: "FFFFFF",
  rose: "FFD9CB",
  sky: "BEE9FF",
};

const DARK_THEME = {
  bg: COLORS.navy,
  title: COLORS.white,
  body: "DCE8F3",
  accent: COLORS.aqua,
  accent2: COLORS.coral,
  rule: "2C4663",
};

const LIGHT_THEME = {
  bg: COLORS.light,
  title: COLORS.ink,
  body: COLORS.slate,
  accent: COLORS.teal,
  accent2: COLORS.navySoft,
  rule: COLORS.line,
};

const slidesData = [
  {
    id: 1,
    type: "cover",
    theme: "dark",
    title: "Inventics",
    subtitle: "Mănușă inteligentă care transformă gesturile în text",
    notes: [
      "În România există un număr semnificativ de persoane cu deficiențe de auz.",
      "Comunicarea cu restul societății este adesea limitată.",
    ],
    solution: "Soluția: un dispozitiv portabil care transformă limbajul semnelor în text.",
  },
  {
    id: 2,
    type: "problem",
    theme: "light",
    title: "Problema",
    environments: ["școli", "spitale", "instituții"],
    points: ["Dependență de interpret", "Izolare socială"],
  },
  {
    id: 3,
    type: "award",
    theme: "dark",
    title: "Validare internațională",
    event: "Abu Dhabi International Invention Exhibition",
    result: "Locul 1",
    proof: ["inovația", "utilitatea", "potențialul global"],
  },
  {
    id: 4,
    type: "context",
    theme: "light",
    title: "Context",
    existing: ["aplicații AI", "sisteme video"],
    issues: ["sensibile la lumină", "costuri mari: 2000-3000 lei"],
  },
  {
    id: 5,
    type: "product",
    theme: "dark",
    title: "Produsul",
    productName: "Mănușă inteligentă",
    feature: "Transformă gesturile în text",
    accuracy: "87%",
  },
  {
    id: 6,
    type: "flow",
    theme: "light",
    title: "Cum funcționează",
    steps: ["Gest", "Senzori", "Procesare", "Text afișat"],
  },
  {
    id: 7,
    type: "advantages",
    theme: "dark",
    title: "Avantaje",
    items: ["Nu depinde de cameră", "Portabil", "Stabil", "Ușor de folosit"],
  },
  {
    id: 8,
    type: "competition",
    theme: "dark",
    title: "Concurența",
    competitor: "BrightSign Glove",
    price: "500 EUR, aproximativ 2500 lei",
    issues: ["cost ridicat", "dependență de cameră"],
  },
  {
    id: 9,
    type: "barCompare",
    theme: "light",
    title: "Avantaj competitiv",
    prices: [
      { label: "Inventics", value: 1875, color: COLORS.teal },
      { label: "BrightSign", value: 2500, color: COLORS.navySoft },
    ],
    productionCost: 1100,
    profit: 775,
    message: "Cu 25% mai mic și mai accesibil pentru școli.",
  },
  {
    id: 10,
    type: "market",
    theme: "dark",
    title: "Piața țintă",
    audiences: [
      "Persoane cu deficiențe de auz",
      "Elevi și studenți",
      "Școli",
      "ONG-uri",
      "Instituții",
    ],
  },
  {
    id: 11,
    type: "marketing",
    theme: "light",
    title: "Strategie marketing",
    partners: ["asociații persoanelor cu deficiențe de auz", "universități", "aeroporturi"],
    activities: ["workshop-uri", "demonstrații", "evenimente"],
  },
  {
    id: 12,
    type: "promotion",
    theme: "dark",
    title: "Promovare",
    channels: ["Social media", "Website", "Prezentări live"],
    contests: ["ISEF (SUA)", "iENA (Germania)", "WICO (Indonezia)"],
  },
  {
    id: 13,
    type: "costs",
    theme: "light",
    title: "Producție",
    costs: [
      { label: "Senzori", value: 400, color: COLORS.teal },
      { label: "PCB + componente", value: 300, color: COLORS.navySoft },
      { label: "Carcasă 3D", value: 200, color: COLORS.coral },
      { label: "Alte costuri", value: 200, color: COLORS.gold },
    ],
    total: 1100,
  },
  {
    id: 14,
    type: "team",
    theme: "dark",
    title: "Echipa",
    roles: ["Coordonator", "Hardware", "Software", "Design", "Marketing"],
  },
  {
    id: 15,
    type: "impact",
    theme: "light",
    title: "Impact",
    items: ["Crește incluziunea", "Reduce discriminarea", "Ajută educația"],
  },
  {
    id: 16,
    type: "roadmap",
    theme: "dark",
    title: "Viitor",
    milestones: [
      "Reducere cost sub 1500 lei",
      "Creștere acuratețe peste 95%",
      "Lansare internațională",
    ],
  },
  {
    id: 17,
    type: "closing",
    theme: "dark",
    title: "Comunicarea devine accesibilă.",
    subtitle: "Un gest transformat în cuvânt.",
  },
];

function ensureDirs() {
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });
  fs.mkdirSync(PREVIEW_DIR, { recursive: true });
}

function themeFor(slide) {
  return slide.theme === "dark" ? DARK_THEME : LIGHT_THEME;
}

function hex(color) {
  return color.startsWith("#") ? color.slice(1) : color;
}

function pxToIn(px) {
  return (px / PREVIEW_W) * PPT_W;
}

function pyToIn(px) {
  return (px / PREVIEW_H) * PPT_H;
}

function escapeXml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

function wrapText(text, maxChars) {
  const words = String(text).split(/\s+/).filter(Boolean);
  const lines = [];
  let current = "";
  for (const word of words) {
    const next = current ? `${current} ${word}` : word;
    if (next.length <= maxChars) {
      current = next;
      continue;
    }
    if (current) {
      lines.push(current);
      current = word;
    } else {
      lines.push(word);
    }
  }
  if (current) lines.push(current);
  return lines;
}

function lineSvg(x1, y1, x2, y2, color, width, opacity = 1) {
  return `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${color}" stroke-width="${width}" stroke-opacity="${opacity}" stroke-linecap="round" />`;
}

function rectSvg(x, y, w, h, fill, radius = 0, opacity = 1, stroke = null, strokeWidth = 0) {
  const strokePart =
    stroke && strokeWidth
      ? ` stroke="${stroke}" stroke-width="${strokeWidth}" stroke-opacity="${opacity}"`
      : "";
  return `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${radius}" ry="${radius}" fill="${fill}" fill-opacity="${opacity}"${strokePart} />`;
}

function circleSvg(cx, cy, r, fill, opacity = 1, stroke = null, strokeWidth = 0) {
  const strokePart =
    stroke && strokeWidth
      ? ` stroke="${stroke}" stroke-width="${strokeWidth}" stroke-opacity="${opacity}"`
      : "";
  return `<circle cx="${cx}" cy="${cy}" r="${r}" fill="${fill}" fill-opacity="${opacity}"${strokePart} />`;
}

function svgTextBlock(lines, x, y, options) {
  const {
    size,
    color,
    weight = 400,
    lineHeight = 1.22,
    anchor = "start",
    family = "Aptos, 'Segoe UI', Arial, sans-serif",
    opacity = 1,
    uppercase = false,
  } = options;
  const safeLines = lines.map((line) => (uppercase ? String(line).toUpperCase() : String(line)));
  const tspans = safeLines
    .map((line, index) => {
      const dy = index === 0 ? 0 : size * lineHeight;
      return `<tspan x="${x}" dy="${index === 0 ? 0 : dy}">${escapeXml(line)}</tspan>`;
    })
    .join("");
  return `<text x="${x}" y="${y}" font-size="${size}" font-weight="${weight}" font-family="${family}" fill="${color}" fill-opacity="${opacity}" text-anchor="${anchor}">${tspans}</text>`;
}

function addBackground(slide, theme) {
  slide.background = { color: hex(theme.bg) };
  slide.addShape(slide.ShapeType.rect, {
    x: 0,
    y: 0,
    w: PPT_W,
    h: PPT_H,
    line: { color: hex(theme.bg), transparency: 100 },
    fill: { color: hex(theme.bg) },
  });
}

function addDarkDecor(slide) {
  slide.addShape(slide.ShapeType.rect, {
    x: 9.35,
    y: -0.4,
    w: 4.6,
    h: 8.5,
    rotate: 10,
    line: { color: COLORS.teal, transparency: 100 },
    fill: { color: COLORS.tealDeep, transparency: 76 },
  });
  slide.addShape(slide.ShapeType.ellipse, {
    x: 9.75,
    y: 0.65,
    w: 2.4,
    h: 2.4,
    line: { color: COLORS.aqua, transparency: 55, width: 2.25 },
    fill: { color: COLORS.navy, transparency: 100 },
  });
  slide.addShape(slide.ShapeType.ellipse, {
    x: 10.35,
    y: 1.25,
    w: 1.2,
    h: 1.2,
    line: { color: COLORS.aqua, transparency: 100 },
    fill: { color: COLORS.aqua, transparency: 8 },
  });
  slide.addShape(slide.ShapeType.line, {
    x: 10.65,
    y: 2.45,
    w: 1.5,
    h: 1.15,
    line: { color: COLORS.aqua, transparency: 55, width: 2 },
  });
  slide.addShape(slide.ShapeType.line, {
    x: 11.8,
    y: 1.45,
    w: -0.85,
    h: 2.25,
    line: { color: COLORS.coral, transparency: 65, width: 1.5 },
  });
  slide.addShape(slide.ShapeType.ellipse, {
    x: 11.78,
    y: 3.52,
    w: 0.28,
    h: 0.28,
    line: { color: COLORS.coral, transparency: 100 },
    fill: { color: COLORS.coral, transparency: 0 },
  });
}

function addLightDecor(slide) {
  slide.addShape(slide.ShapeType.rect, {
    x: 10.35,
    y: -0.35,
    w: 4.2,
    h: 3.2,
    rotate: -9,
    line: { color: COLORS.mint, transparency: 100 },
    fill: { color: COLORS.mint, transparency: 6 },
  });
  slide.addShape(slide.ShapeType.line, {
    x: 0.85,
    y: 6.88,
    w: 11.45,
    h: 0,
    line: { color: COLORS.line, transparency: 0, width: 1 },
  });
}

function addShell(slide, slideInfo) {
  const theme = themeFor(slideInfo);
  addBackground(slide, theme);
  if (slideInfo.theme === "dark") addDarkDecor(slide);
  if (slideInfo.theme === "light") addLightDecor(slide);
  if (slideInfo.type !== "cover" && slideInfo.type !== "closing") {
    slide.addText(slideInfo.title, {
      x: 0.88,
      y: 0.62,
      w: 6.2,
      h: 0.55,
      margin: 0,
      color: hex(theme.title),
      fontFace: "Aptos Display",
      fontSize: 24,
      bold: true,
    });
    slide.addText(`0${slideInfo.id}`.slice(-2), {
      x: 12.08,
      y: 6.88,
      w: 0.62,
      h: 0.2,
      margin: 0,
      align: "right",
      color: slideInfo.theme === "dark" ? "9CB4CC" : "7D8CA0",
      fontFace: "Aptos",
      fontSize: 10,
      bold: true,
    });
    slide.addText("Inventics", {
      x: 11.1,
      y: 0.66,
      w: 1.35,
      h: 0.18,
      margin: 0,
      align: "right",
      color: slideInfo.theme === "dark" ? "8EDFD5" : "14968F",
      fontFace: "Aptos",
      fontSize: 9,
      bold: true,
    });
  }
}

function addDotBullet(slide, x, y, text, theme, width = 4.6, size = 18) {
  slide.addShape(slide.ShapeType.ellipse, {
    x,
    y: y + 0.08,
    w: 0.1,
    h: 0.1,
    line: { color: hex(theme.accent), transparency: 100 },
    fill: { color: hex(theme.accent) },
  });
  slide.addText(text, {
    x: x + 0.2,
    y,
    w: width,
    h: 0.36,
    margin: 0,
    color: hex(theme.body),
    fontFace: "Aptos",
    fontSize: size,
  });
}

function addPill(slide, x, y, w, text, fillColor, textColor) {
  slide.addShape(slide.ShapeType.roundRect, {
    x,
    y,
    w,
    h: 0.42,
    rectRadius: 0.08,
    line: { color: fillColor, transparency: 100 },
    fill: { color: fillColor, transparency: 0 },
  });
  slide.addText(text, {
    x,
    y: y + 0.05,
    w,
    h: 0.2,
    margin: 0,
    align: "center",
    color: textColor,
    fontFace: "Aptos",
    fontSize: 11,
    bold: true,
  });
}

function addMetricChip(slide, x, y, w, value, label, theme, fillColor = null) {
  const bg = fillColor || hex(theme.accent);
  const textColor = bg === COLORS.gold ? "6F4A00" : "FFFFFF";
  slide.addShape(slide.ShapeType.roundRect, {
    x,
    y,
    w,
    h: 0.9,
    rectRadius: 0.08,
    line: { color: bg, transparency: 100 },
    fill: { color: bg, transparency: 0 },
  });
  slide.addText(String(value), {
    x: x + 0.12,
    y: y + 0.16,
    w: w - 0.24,
    h: 0.3,
    margin: 0,
    color: textColor,
    fontFace: "Aptos Display",
    fontSize: 24,
    bold: true,
  });
  slide.addText(label, {
    x: x + 0.12,
    y: y + 0.56,
    w: w - 0.24,
    h: 0.14,
    margin: 0,
    color: textColor,
    fontFace: "Aptos",
    fontSize: 10,
    bold: false,
  });
}

function renderCover(slide, data) {
  const theme = themeFor(data);
  addShell(slide, data);
  slide.addText("Pitch de impact social și tehnologic", {
    x: 0.92,
    y: 0.82,
    w: 3.6,
    h: 0.18,
    margin: 0,
    color: "8EDFD5",
    fontFace: "Aptos",
    fontSize: 10,
    bold: true,
  });
  slide.addText(data.title, {
    x: 0.9,
    y: 1.3,
    w: 5.6,
    h: 0.92,
    margin: 0,
    color: hex(theme.title),
    fontFace: "Aptos Display",
    fontSize: 31,
    bold: true,
  });
  slide.addText(data.subtitle, {
    x: 0.94,
    y: 2.36,
    w: 5.25,
    h: 0.9,
    margin: 0,
    color: hex(theme.body),
    fontFace: "Aptos",
    fontSize: 19,
    breakLine: false,
  });
  slide.addShape(slide.ShapeType.line, {
    x: 0.95,
    y: 3.4,
    w: 1.4,
    h: 0,
    line: { color: COLORS.aqua, width: 2.5 },
  });
  addDotBullet(slide, 0.95, 3.75, data.notes[0], theme, 4.95, 16);
  addDotBullet(slide, 0.95, 4.35, data.notes[1], theme, 4.95, 16);
  slide.addText(data.solution, {
    x: 0.94,
    y: 5.35,
    w: 5.4,
    h: 0.7,
    margin: 0,
    color: "FFFFFF",
    fontFace: "Aptos",
    fontSize: 17,
    bold: true,
  });
  slide.addShape(slide.ShapeType.ellipse, {
    x: 9.75,
    y: 1.15,
    w: 2.45,
    h: 2.45,
    line: { color: COLORS.aqua, transparency: 70, width: 1.75 },
    fill: { color: COLORS.navy, transparency: 100 },
  });
  slide.addShape(slide.ShapeType.ellipse, {
    x: 10.74,
    y: 2.14,
    w: 0.48,
    h: 0.48,
    line: { color: COLORS.aqua, transparency: 100 },
    fill: { color: COLORS.aqua, transparency: 0 },
  });
  slide.addShape(slide.ShapeType.ellipse, {
    x: 11.82,
    y: 3.1,
    w: 0.36,
    h: 0.36,
    line: { color: COLORS.coral, transparency: 100 },
    fill: { color: COLORS.coral, transparency: 0 },
  });
  slide.addShape(slide.ShapeType.line, {
    x: 11.01,
    y: 2.56,
    w: 1.08,
    h: 0.72,
    line: { color: COLORS.aqua, transparency: 55, width: 2 },
  });
  slide.addShape(slide.ShapeType.line, {
    x: 10.94,
    y: 2.52,
    w: -0.9,
    h: 1.68,
    line: { color: COLORS.aqua, transparency: 55, width: 2 },
  });
  slide.addShape(slide.ShapeType.line, {
    x: 10.12,
    y: 4.1,
    w: 1.55,
    h: 0.82,
    line: { color: COLORS.coral, transparency: 70, width: 1.5 },
  });
  slide.addText("Inventics", {
    x: 11.08,
    y: 6.88,
    w: 1.25,
    h: 0.16,
    margin: 0,
    align: "right",
    color: "8EDFD5",
    fontFace: "Aptos",
    fontSize: 9,
    bold: true,
  });
}

function renderProblem(slide, data) {
  const theme = themeFor(data);
  addShell(slide, data);
  slide.addText("Unde se vede cel mai clar ruptura de comunicare", {
    x: 0.9,
    y: 1.35,
    w: 4.7,
    h: 0.35,
    margin: 0,
    color: "14968F",
    fontFace: "Aptos",
    fontSize: 12,
    bold: true,
  });
  addPill(slide, 7.75, 1.32, 1.1, data.environments[0], "DFF8F0", "0F756E");
  addPill(slide, 8.95, 1.32, 1.15, data.environments[1], "DDEAFE", "15314D");
  addPill(slide, 10.2, 1.32, 1.45, data.environments[2], "FFE4DA", "91492B");
  slide.addText(data.points[0], {
    x: 0.92,
    y: 2.6,
    w: 5.4,
    h: 0.65,
    margin: 0,
    color: hex(theme.title),
    fontFace: "Aptos Display",
    fontSize: 26,
    bold: true,
  });
  slide.addText(data.points[1], {
    x: 0.92,
    y: 3.45,
    w: 4.8,
    h: 0.54,
    margin: 0,
    color: "5B6D82",
    fontFace: "Aptos Display",
    fontSize: 22,
    bold: true,
  });
  slide.addText(
    "Fără un instrument direct, accesul la informație și la servicii depinde de prezența unui intermediar.",
    {
      x: 0.94,
      y: 4.45,
      w: 4.7,
      h: 0.95,
      margin: 0,
      color: hex(theme.body),
      fontFace: "Aptos",
      fontSize: 16,
    },
  );
  slide.addShape(slide.ShapeType.ellipse, {
    x: 8.3,
    y: 2.15,
    w: 2.35,
    h: 2.35,
    line: { color: COLORS.teal, transparency: 0, width: 1.75 },
    fill: { color: COLORS.mint, transparency: 0 },
  });
  slide.addShape(slide.ShapeType.line, {
    x: 7.18,
    y: 2.92,
    w: 1.18,
    h: 0.25,
    line: { color: COLORS.teal, transparency: 0, width: 2.5 },
  });
  slide.addShape(slide.ShapeType.line, {
    x: 10.66,
    y: 3.02,
    w: 1.25,
    h: 0.42,
    line: { color: COLORS.coral, transparency: 0, width: 2.5 },
  });
  slide.addText("comunicare\nfragmentată", {
    x: 8.7,
    y: 2.73,
    w: 1.55,
    h: 0.6,
    margin: 0,
    align: "center",
    color: "15314D",
    fontFace: "Aptos Display",
    fontSize: 16,
    bold: true,
  });
  slide.addText("mediator uman", {
    x: 6.4,
    y: 2.62,
    w: 1.1,
    h: 0.2,
    margin: 0,
    color: "14968F",
    fontFace: "Aptos",
    fontSize: 11,
    bold: true,
  });
  slide.addText("utilizator final", {
    x: 11.1,
    y: 3.32,
    w: 1.2,
    h: 0.2,
    margin: 0,
    color: "B45B36",
    fontFace: "Aptos",
    fontSize: 11,
    bold: true,
  });
}

function renderAward(slide, data) {
  const theme = themeFor(data);
  addShell(slide, data);
  slide.addText(data.event, {
    x: 0.9,
    y: 1.5,
    w: 4.9,
    h: 0.95,
    margin: 0,
    color: hex(theme.title),
    fontFace: "Aptos Display",
    fontSize: 24,
    bold: true,
  });
  slide.addText("Rezultat internațional care confirmă relevanța soluției", {
    x: 0.92,
    y: 2.62,
    w: 4.8,
    h: 0.45,
    margin: 0,
    color: hex(theme.body),
    fontFace: "Aptos",
    fontSize: 15,
  });
  slide.addShape(slide.ShapeType.ellipse, {
    x: 7.68,
    y: 1.4,
    w: 3.05,
    h: 3.05,
    line: { color: COLORS.gold, transparency: 0, width: 3 },
    fill: { color: COLORS.goldSoft, transparency: 0 },
  });
  slide.addText("#1", {
    x: 8.35,
    y: 2.05,
    w: 1.7,
    h: 0.7,
    margin: 0,
    align: "center",
    color: "8A5A00",
    fontFace: "Aptos Display",
    fontSize: 34,
    bold: true,
  });
  slide.addText(data.result, {
    x: 8.05,
    y: 2.95,
    w: 2.3,
    h: 0.3,
    margin: 0,
    align: "center",
    color: "8A5A00",
    fontFace: "Aptos",
    fontSize: 16,
    bold: true,
  });
  addPill(slide, 0.95, 4.25, 1.3, data.proof[0], "183954", "FFFFFF");
  addPill(slide, 2.38, 4.25, 1.22, data.proof[1], "14968F", "FFFFFF");
  addPill(slide, 3.73, 4.25, 1.7, data.proof[2], "C46D43", "FFFFFF");
  slide.addText("Premiul arată că produsul are valoare practică și poate scala dincolo de contextul local.", {
    x: 0.94,
    y: 5.08,
    w: 5.2,
    h: 0.9,
    margin: 0,
    color: hex(theme.body),
    fontFace: "Aptos",
    fontSize: 16,
  });
}

function renderContext(slide, data) {
  const theme = themeFor(data);
  addShell(slide, data);
  slide.addText("Soluții existente", {
    x: 0.92,
    y: 1.55,
    w: 2.8,
    h: 0.3,
    margin: 0,
    color: "14968F",
    fontFace: "Aptos",
    fontSize: 13,
    bold: true,
  });
  addDotBullet(slide, 0.95, 2.0, data.existing[0], theme, 3.0, 19);
  addDotBullet(slide, 0.95, 2.6, data.existing[1], theme, 3.0, 19);
  slide.addShape(slide.ShapeType.line, {
    x: 6.62,
    y: 1.6,
    w: 0,
    h: 4.2,
    line: { color: COLORS.line, width: 1.25 },
  });
  slide.addText("Limite ale alternativelor", {
    x: 7.15,
    y: 1.55,
    w: 3.5,
    h: 0.3,
    margin: 0,
    color: "15314D",
    fontFace: "Aptos",
    fontSize: 13,
    bold: true,
  });
  addDotBullet(slide, 7.18, 2.0, data.issues[0], theme, 4.0, 19);
  addDotBullet(slide, 7.18, 2.65, data.issues[1], theme, 4.4, 19);
  addMetricChip(slide, 7.18, 3.78, 2.4, "2000-3000", "interval frecvent de cost (lei)", LIGHT_THEME, COLORS.navySoft);
  slide.addText(
    "Inventics urmărește o abordare mai robustă și mai accesibilă, fără dependență de condițiile de filmare.",
    {
      x: 0.95,
      y: 5.15,
      w: 5.35,
      h: 0.76,
      margin: 0,
      color: hex(theme.body),
      fontFace: "Aptos",
      fontSize: 16,
    },
  );
}

function renderProduct(slide, data) {
  const theme = themeFor(data);
  addShell(slide, data);
  slide.addText(data.productName, {
    x: 0.92,
    y: 1.6,
    w: 4.7,
    h: 0.6,
    margin: 0,
    color: hex(theme.title),
    fontFace: "Aptos Display",
    fontSize: 28,
    bold: true,
  });
  slide.addText(data.feature, {
    x: 0.95,
    y: 2.48,
    w: 4.7,
    h: 0.55,
    margin: 0,
    color: hex(theme.body),
    fontFace: "Aptos",
    fontSize: 18,
  });
  addPill(slide, 0.95, 3.45, 1.7, "fără cameră", "183954", "FFFFFF");
  addPill(slide, 2.8, 3.45, 1.5, "portabil", "14968F", "FFFFFF");
  addPill(slide, 4.45, 3.45, 1.25, "direct", "C46D43", "FFFFFF");
  slide.addText("Acuratețe estimată", {
    x: 8.0,
    y: 1.7,
    w: 2.1,
    h: 0.22,
    margin: 0,
    color: "8EDFD5",
    fontFace: "Aptos",
    fontSize: 11,
    bold: true,
  });
  slide.addText(data.accuracy, {
    x: 7.92,
    y: 2.08,
    w: 3.2,
    h: 1.0,
    margin: 0,
    color: "FFFFFF",
    fontFace: "Aptos Display",
    fontSize: 44,
    bold: true,
  });
  slide.addText(
    "Conceptul central: un lanț simplu, purtabil și intuitiv care convertește gestul într-un mesaj lizibil.",
    {
      x: 7.96,
      y: 3.48,
      w: 3.9,
      h: 1.0,
      margin: 0,
      color: hex(theme.body),
      fontFace: "Aptos",
      fontSize: 16,
    },
  );
}

function renderFlow(slide, data) {
  addShell(slide, data);
  const xs = [0.95, 4.15, 7.35, 10.55];
  const colors = [COLORS.mint, "DDEAFE", "FFE4DA", "FFF0C5"];
  const textColors = ["0A6B65", "183954", "9B4B2B", "8A5A00"];
  data.steps.forEach((step, index) => {
    slide.addShape(slide.ShapeType.roundRect, {
      x: xs[index],
      y: 2.6,
      w: 2.15,
      h: 1.15,
      rectRadius: 0.08,
      line: { color: colors[index], transparency: 100 },
      fill: { color: colors[index], transparency: 0 },
    });
    slide.addText(step, {
      x: xs[index] + 0.16,
      y: 2.98,
      w: 1.83,
      h: 0.32,
      margin: 0,
      align: "center",
      color: textColors[index],
      fontFace: "Aptos Display",
      fontSize: 18,
      bold: true,
    });
    if (index < data.steps.length - 1) {
      slide.addShape(slide.ShapeType.chevron, {
        x: xs[index] + 2.32,
        y: 2.92,
        w: 0.48,
        h: 0.46,
        line: { color: COLORS.line, transparency: 100 },
        fill: { color: COLORS.teal, transparency: 12 },
      });
    }
  });
  slide.addText(
    "Fluxul este gândit pentru răspuns rapid: mișcarea este captată, interpretată și afișată aproape instant.",
    {
      x: 0.95,
      y: 4.6,
      w: 5.5,
      h: 0.7,
      margin: 0,
      color: COLORS.slate,
      fontFace: "Aptos",
      fontSize: 16,
    },
  );
}

function renderAdvantages(slide, data) {
  addShell(slide, data);
  slide.addText("Un produs util în contexte reale, nu doar într-un demo controlat", {
    x: 0.9,
    y: 1.42,
    w: 5.5,
    h: 0.4,
    margin: 0,
    color: "9FDCD3",
    fontFace: "Aptos",
    fontSize: 13,
    bold: true,
  });
  const positions = [
    { x: 1.0, y: 2.4, w: 2.55, h: 0.95, fill: "183954" },
    { x: 3.85, y: 4.65, w: 1.8, h: 0.85, fill: "14968F" },
    { x: 7.4, y: 2.1, w: 1.65, h: 0.85, fill: "C46D43" },
    { x: 9.3, y: 4.1, w: 2.55, h: 0.95, fill: "F3B83A" },
  ];
  data.items.forEach((item, index) => {
    const pos = positions[index];
    slide.addShape(slide.ShapeType.roundRect, {
      x: pos.x,
      y: pos.y,
      w: pos.w,
      h: pos.h,
      rectRadius: 0.08,
      line: { color: pos.fill, transparency: 100 },
      fill: { color: pos.fill, transparency: 0 },
    });
    slide.addText(item, {
      x: pos.x + 0.12,
      y: pos.y + 0.24,
      w: pos.w - 0.24,
      h: 0.34,
      margin: 0,
      align: "center",
      color: index === 3 ? "6F4A00" : "FFFFFF",
      fontFace: "Aptos Display",
      fontSize: 17,
      bold: true,
    });
  });
  slide.addShape(slide.ShapeType.ellipse, {
    x: 5.75,
    y: 2.95,
    w: 1.65,
    h: 1.65,
    line: { color: COLORS.aqua, transparency: 55, width: 2 },
    fill: { color: COLORS.aqua, transparency: 88 },
  });
  slide.addText("mai multă\nautonomie", {
    x: 5.98,
    y: 3.42,
    w: 1.2,
    h: 0.52,
    margin: 0,
    align: "center",
    color: "FFFFFF",
    fontFace: "Aptos",
    fontSize: 14,
    bold: true,
  });
}

function renderCompetition(slide, data) {
  addShell(slide, data);
  slide.addText(data.competitor, {
    x: 0.95,
    y: 1.72,
    w: 4.8,
    h: 0.45,
    margin: 0,
    color: "FFFFFF",
    fontFace: "Aptos Display",
    fontSize: 26,
    bold: true,
  });
  slide.addText("Referință utilă, dar greu de adoptat la scară largă în contexte educaționale.", {
    x: 0.96,
    y: 2.38,
    w: 4.9,
    h: 0.7,
    margin: 0,
    color: "DCE8F3",
    fontFace: "Aptos",
    fontSize: 16,
  });
  addMetricChip(slide, 0.96, 3.58, 2.55, "2500 lei", "preț estimat", DARK_THEME, COLORS.coral);
  addDotBullet(slide, 7.38, 2.3, data.issues[0], DARK_THEME, 3.7, 19);
  addDotBullet(slide, 7.38, 3.05, data.issues[1], DARK_THEME, 3.7, 19);
  slide.addText("Provocarea nu este doar tehnologia, ci adoptarea ei în medii unde bugetul și simplitatea contează.", {
    x: 7.38,
    y: 4.02,
    w: 4.4,
    h: 0.95,
    margin: 0,
    color: "BFD0E1",
    fontFace: "Aptos",
    fontSize: 16,
  });
}

function renderBarCompare(slide, data) {
  addShell(slide, data);
  slide.addText(data.message, {
    x: 0.95,
    y: 1.42,
    w: 5.7,
    h: 0.34,
    margin: 0,
    color: "14968F",
    fontFace: "Aptos",
    fontSize: 13,
    bold: true,
  });
  const max = Math.max(...data.prices.map((item) => item.value));
  data.prices.forEach((item, index) => {
    const y = 2.18 + index * 1.06;
    const barW = 4.35 * (item.value / max);
    slide.addText(item.label, {
      x: 0.96,
      y: y + 0.07,
      w: 1.15,
      h: 0.22,
      margin: 0,
      color: "183954",
      fontFace: "Aptos",
      fontSize: 13,
      bold: true,
    });
    slide.addShape(slide.ShapeType.roundRect, {
      x: 2.15,
      y,
      w: barW,
      h: 0.52,
      rectRadius: 0.08,
      line: { color: item.color, transparency: 100 },
      fill: { color: item.color, transparency: 0 },
    });
    slide.addText(`${item.value} lei`, {
      x: 2.28 + barW,
      y: y + 0.06,
      w: 1.15,
      h: 0.22,
      margin: 0,
      color: "183954",
      fontFace: "Aptos",
      fontSize: 13,
      bold: true,
    });
  });
  addMetricChip(slide, 7.45, 2.05, 2.05, `${data.productionCost} lei`, "cost producție / unitate", LIGHT_THEME, COLORS.navySoft);
  addMetricChip(slide, 9.8, 2.05, 2.05, `${data.profit} lei`, "profit brut / unitate", LIGHT_THEME, COLORS.teal);
  slide.addText("Mai accesibil, mai ușor de implementat în școli, cu marjă suficientă pentru dezvoltare.", {
    x: 7.45,
    y: 3.5,
    w: 4.4,
    h: 0.9,
    margin: 0,
    color: COLORS.slate,
    fontFace: "Aptos",
    fontSize: 16,
  });
}

function renderMarket(slide, data) {
  addShell(slide, data);
  slide.addText("Cui îi aduce valoare imediată", {
    x: 0.92,
    y: 1.42,
    w: 4.5,
    h: 0.28,
    margin: 0,
    color: "9FDCD3",
    fontFace: "Aptos",
    fontSize: 13,
    bold: true,
  });
  const nodes = [
    { x: 1.0, y: 3.05, w: 2.8, fill: "183954", label: data.audiences[0] },
    { x: 4.15, y: 2.15, w: 2.25, fill: "14968F", label: data.audiences[1] },
    { x: 4.25, y: 4.4, w: 1.55, fill: "C46D43", label: data.audiences[2] },
    { x: 7.05, y: 2.35, w: 1.5, fill: "F3B83A", label: data.audiences[3] },
    { x: 9.35, y: 3.2, w: 2.0, fill: "183954", label: data.audiences[4] },
  ];
  nodes.forEach((node, index) => {
    slide.addShape(slide.ShapeType.roundRect, {
      x: node.x,
      y: node.y,
      w: node.w,
      h: 0.78,
      rectRadius: 0.08,
      line: { color: node.fill, transparency: 100 },
      fill: { color: node.fill, transparency: 0 },
    });
    slide.addText(node.label, {
      x: node.x + 0.1,
      y: node.y + 0.18,
      w: node.w - 0.2,
      h: 0.34,
      margin: 0,
      align: "center",
      color: index === 3 ? "6F4A00" : "FFFFFF",
      fontFace: "Aptos Display",
      fontSize: index === 0 ? 15 : 14,
      bold: true,
    });
  });
  slide.addShape(slide.ShapeType.line, {
    x: 3.82,
    y: 3.46,
    w: 0.58,
    h: -0.8,
    line: { color: COLORS.aqua, transparency: 50, width: 1.5 },
  });
  slide.addShape(slide.ShapeType.line, {
    x: 3.82,
    y: 3.46,
    w: 0.62,
    h: 1.28,
    line: { color: COLORS.aqua, transparency: 50, width: 1.5 },
  });
  slide.addShape(slide.ShapeType.line, {
    x: 6.38,
    y: 2.54,
    w: 0.78,
    h: 0.2,
    line: { color: COLORS.aqua, transparency: 50, width: 1.5 },
  });
  slide.addShape(slide.ShapeType.line, {
    x: 8.62,
    y: 2.72,
    w: 0.72,
    h: 0.85,
    line: { color: COLORS.coral, transparency: 55, width: 1.5 },
  });
}

function renderMarketing(slide, data) {
  addShell(slide, data);
  slide.addShape(slide.ShapeType.ellipse, {
    x: 5.48,
    y: 2.35,
    w: 2.15,
    h: 2.15,
    line: { color: COLORS.teal, transparency: 100 },
    fill: { color: COLORS.mint, transparency: 0 },
  });
  slide.addText("rețea de\nparteneri", {
    x: 5.92,
    y: 3.0,
    w: 1.25,
    h: 0.54,
    margin: 0,
    align: "center",
    color: "0A6B65",
    fontFace: "Aptos Display",
    fontSize: 16,
    bold: true,
  });
  addPill(slide, 2.0, 2.2, 2.8, data.partners[0], "DFF8F0", "0A6B65");
  addPill(slide, 8.28, 2.2, 1.8, data.partners[1], "DDEAFE", "183954");
  addPill(slide, 5.05, 4.98, 2.75, data.partners[2], "FFE4DA", "9B4B2B");
  slide.addShape(slide.ShapeType.line, {
    x: 4.78,
    y: 2.42,
    w: 0.73,
    h: 0.95,
    line: { color: COLORS.teal, transparency: 35, width: 1.5 },
  });
  slide.addShape(slide.ShapeType.line, {
    x: 7.6,
    y: 3.36,
    w: 0.65,
    h: -0.92,
    line: { color: COLORS.navySoft, transparency: 40, width: 1.5 },
  });
  slide.addShape(slide.ShapeType.line, {
    x: 6.54,
    y: 4.5,
    w: -0.06,
    h: 0.53,
    line: { color: COLORS.coral, transparency: 40, width: 1.5 },
  });
  slide.addText("Activități principale", {
    x: 0.95,
    y: 5.38,
    w: 2.6,
    h: 0.2,
    margin: 0,
    color: "15314D",
    fontFace: "Aptos",
    fontSize: 12,
    bold: true,
  });
  addPill(slide, 0.95, 5.72, 1.55, data.activities[0], "183954", "FFFFFF");
  addPill(slide, 2.65, 5.72, 1.75, data.activities[1], "14968F", "FFFFFF");
  addPill(slide, 4.55, 5.72, 1.4, data.activities[2], "C46D43", "FFFFFF");
}

function renderPromotion(slide, data) {
  addShell(slide, data);
  slide.addText("Canale proprii", {
    x: 0.94,
    y: 1.55,
    w: 2.0,
    h: 0.2,
    margin: 0,
    color: "9FDCD3",
    fontFace: "Aptos",
    fontSize: 12,
    bold: true,
  });
  addPill(slide, 0.95, 2.0, 1.55, data.channels[0], "183954", "FFFFFF");
  addPill(slide, 0.95, 2.62, 1.35, data.channels[1], "14968F", "FFFFFF");
  addPill(slide, 0.95, 3.24, 1.75, data.channels[2], "C46D43", "FFFFFF");
  slide.addText("Concursuri internaționale vizate", {
    x: 7.02,
    y: 1.55,
    w: 3.2,
    h: 0.2,
    margin: 0,
    color: "9FDCD3",
    fontFace: "Aptos",
    fontSize: 12,
    bold: true,
  });
  data.contests.forEach((contest, index) => {
    slide.addShape(slide.ShapeType.roundRect, {
      x: 7.05,
      y: 2.0 + index * 0.72,
      w: 3.95,
      h: 0.5,
      rectRadius: 0.08,
      line: { color: index === 0 ? COLORS.teal : index === 1 ? COLORS.coral : COLORS.gold, transparency: 100 },
      fill: { color: index === 0 ? COLORS.tealDeep : index === 1 ? "A65833" : "A17314", transparency: 0 },
    });
    slide.addText(contest, {
      x: 7.2,
      y: 2.16 + index * 0.72,
      w: 3.65,
      h: 0.18,
      margin: 0,
      color: index === 2 ? "FFF3D6" : "FFFFFF",
      fontFace: "Aptos Display",
      fontSize: 14,
      bold: true,
    });
  });
}

function renderCosts(slide, data) {
  addShell(slide, data);
  slide.addText("Cost estimat / unitate", {
    x: 0.95,
    y: 1.45,
    w: 2.8,
    h: 0.2,
    margin: 0,
    color: "14968F",
    fontFace: "Aptos",
    fontSize: 12,
    bold: true,
  });
  let currentX = 0.95;
  data.costs.forEach((item) => {
    const width = 4.95 * (item.value / data.total);
    slide.addShape(slide.ShapeType.rect, {
      x: currentX,
      y: 2.05,
      w: width,
      h: 0.65,
      line: { color: item.color, transparency: 100 },
      fill: { color: item.color, transparency: 0 },
    });
    currentX += width;
  });
  data.costs.forEach((item, index) => {
    slide.addShape(slide.ShapeType.roundRect, {
      x: 0.96,
      y: 3.05 + index * 0.72,
      w: 3.55,
      h: 0.48,
      rectRadius: 0.08,
      line: { color: item.color, transparency: 100 },
      fill: { color: item.color, transparency: 0 },
    });
    slide.addText(`${item.label}   ${item.value} lei`, {
      x: 1.12,
      y: 3.2 + index * 0.72,
      w: 3.15,
      h: 0.16,
      margin: 0,
      color: index === 3 ? "6F4A00" : "FFFFFF",
      fontFace: "Aptos Display",
      fontSize: 14,
      bold: true,
    });
  });
  addMetricChip(slide, 8.15, 2.62, 2.55, `${data.total} lei`, "total estimat", LIGHT_THEME, COLORS.navySoft);
  slide.addText(
    "Structura de cost susține un produs care poate fi produs, testat și îmbunătățit fără a ieși dintr-un prag realist.",
    {
      x: 7.55,
      y: 4.0,
      w: 4.2,
      h: 0.95,
      margin: 0,
      color: COLORS.slate,
      fontFace: "Aptos",
      fontSize: 16,
    },
  );
}

function renderTeam(slide, data) {
  addShell(slide, data);
  slide.addText("Echipă multidisciplinară pentru produs, prototipare și lansare", {
    x: 0.9,
    y: 1.4,
    w: 5.2,
    h: 0.3,
    margin: 0,
    color: "9FDCD3",
    fontFace: "Aptos",
    fontSize: 13,
    bold: true,
  });
  const positions = [
    { x: 5.6, y: 2.12, fill: "14968F", label: data.roles[0] },
    { x: 2.05, y: 3.15, fill: "183954", label: data.roles[1] },
    { x: 4.25, y: 4.72, fill: "C46D43", label: data.roles[2] },
    { x: 7.1, y: 4.82, fill: "F3B83A", label: data.roles[3] },
    { x: 9.35, y: 3.12, fill: "183954", label: data.roles[4] },
  ];
  positions.forEach((pos) => {
    slide.addShape(slide.ShapeType.roundRect, {
      x: pos.x,
      y: pos.y,
      w: 1.95,
      h: 0.68,
      rectRadius: 0.08,
      line: { color: pos.fill, transparency: 100 },
      fill: { color: pos.fill, transparency: 0 },
    });
    slide.addText(pos.label, {
      x: pos.x + 0.08,
      y: pos.y + 0.18,
      w: 1.8,
      h: 0.18,
      margin: 0,
      align: "center",
      color: pos.fill === "F3B83A" ? "6F4A00" : "FFFFFF",
      fontFace: "Aptos Display",
      fontSize: 14,
      bold: true,
    });
  });
  slide.addShape(slide.ShapeType.line, {
    x: 6.55,
    y: 2.8,
    w: -3.0,
    h: 0.72,
    line: { color: COLORS.aqua, transparency: 50, width: 1.5 },
  });
  slide.addShape(slide.ShapeType.line, {
    x: 6.55,
    y: 2.8,
    w: -0.85,
    h: 2.0,
    line: { color: COLORS.coral, transparency: 50, width: 1.5 },
  });
  slide.addShape(slide.ShapeType.line, {
    x: 6.55,
    y: 2.8,
    w: 1.55,
    h: 1.98,
    line: { color: COLORS.aqua, transparency: 50, width: 1.5 },
  });
  slide.addShape(slide.ShapeType.line, {
    x: 6.55,
    y: 2.8,
    w: 3.72,
    h: 0.8,
    line: { color: COLORS.coral, transparency: 50, width: 1.5 },
  });
}

function renderImpact(slide, data) {
  addShell(slide, data);
  const blocks = [
    { x: 0.95, color: COLORS.mint, textColor: "0A6B65", label: data.items[0] },
    { x: 4.53, color: "DDEAFE", textColor: "183954", label: data.items[1] },
    { x: 8.11, color: "FFE4DA", textColor: "9B4B2B", label: data.items[2] },
  ];
  blocks.forEach((block) => {
    slide.addShape(slide.ShapeType.roundRect, {
      x: block.x,
      y: 2.2,
      w: 3.0,
      h: 2.05,
      rectRadius: 0.08,
      line: { color: block.color, transparency: 100 },
      fill: { color: block.color, transparency: 0 },
    });
    slide.addText(block.label, {
      x: block.x + 0.2,
      y: 2.88,
      w: 2.6,
      h: 0.55,
      margin: 0,
      align: "center",
      color: block.textColor,
      fontFace: "Aptos Display",
      fontSize: 22,
      bold: true,
    });
  });
}

function renderRoadmap(slide, data) {
  addShell(slide, data);
  slide.addShape(slide.ShapeType.line, {
    x: 1.2,
    y: 5.4,
    w: 9.95,
    h: -2.8,
    line: { color: COLORS.aqua, width: 2.5, transparency: 0 },
  });
  const points = [
    { x: 1.65, y: 5.05, label: data.milestones[0], fill: "183954" },
    { x: 5.1, y: 4.08, label: data.milestones[1], fill: "14968F" },
    { x: 8.65, y: 3.12, label: data.milestones[2], fill: "C46D43" },
  ];
  points.forEach((point) => {
    slide.addShape(slide.ShapeType.ellipse, {
      x: point.x,
      y: point.y,
      w: 0.34,
      h: 0.34,
      line: { color: COLORS.aqua, transparency: 100 },
      fill: { color: COLORS.aqua, transparency: 0 },
    });
    slide.addShape(slide.ShapeType.roundRect, {
      x: point.x - 0.55,
      y: point.y - 0.9,
      w: 2.25,
      h: 0.65,
      rectRadius: 0.08,
      line: { color: point.fill, transparency: 100 },
      fill: { color: point.fill, transparency: 0 },
    });
    slide.addText(point.label, {
      x: point.x - 0.42,
      y: point.y - 0.7,
      w: 1.95,
      h: 0.25,
      margin: 0,
      align: "center",
      color: "FFFFFF",
      fontFace: "Aptos Display",
      fontSize: 13,
      bold: true,
    });
  });
}

function renderClosing(slide, data) {
  const theme = themeFor(data);
  addShell(slide, data);
  slide.addText("Inventics", {
    x: 0.95,
    y: 1.0,
    w: 1.8,
    h: 0.2,
    margin: 0,
    color: "8EDFD5",
    fontFace: "Aptos",
    fontSize: 10,
    bold: true,
  });
  slide.addText(data.title, {
    x: 1.0,
    y: 2.2,
    w: 7.0,
    h: 0.9,
    margin: 0,
    color: hex(theme.title),
    fontFace: "Aptos Display",
    fontSize: 30,
    bold: true,
  });
  slide.addText(data.subtitle, {
    x: 1.02,
    y: 3.45,
    w: 5.7,
    h: 0.45,
    margin: 0,
    color: hex(theme.body),
    fontFace: "Aptos",
    fontSize: 20,
    italic: true,
  });
  slide.addShape(slide.ShapeType.line, {
    x: 1.03,
    y: 4.22,
    w: 1.55,
    h: 0,
    line: { color: COLORS.aqua, width: 2.5 },
  });
}

function buildPresentation() {
  const pptx = new PptxGenJS();
  pptx.layout = "LAYOUT_WIDE";
  pptx.author = "OpenAI Codex";
  pptx.company = "Inventics";
  pptx.subject = "Inventics pitch deck";
  pptx.title = "Inventics Pitch Deck";
  pptx.lang = "ro-RO";
  pptx.theme = {
    headFontFace: "Aptos Display",
    bodyFontFace: "Aptos",
    lang: "ro-RO",
  };

  slidesData.forEach((slideInfo) => {
    const slide = pptx.addSlide();
    slide.ShapeType = pptx.ShapeType;
    switch (slideInfo.type) {
      case "cover":
        renderCover(slide, slideInfo);
        break;
      case "problem":
        renderProblem(slide, slideInfo);
        break;
      case "award":
        renderAward(slide, slideInfo);
        break;
      case "context":
        renderContext(slide, slideInfo);
        break;
      case "product":
        renderProduct(slide, slideInfo);
        break;
      case "flow":
        renderFlow(slide, slideInfo);
        break;
      case "advantages":
        renderAdvantages(slide, slideInfo);
        break;
      case "competition":
        renderCompetition(slide, slideInfo);
        break;
      case "barCompare":
        renderBarCompare(slide, slideInfo);
        break;
      case "market":
        renderMarket(slide, slideInfo);
        break;
      case "marketing":
        renderMarketing(slide, slideInfo);
        break;
      case "promotion":
        renderPromotion(slide, slideInfo);
        break;
      case "costs":
        renderCosts(slide, slideInfo);
        break;
      case "team":
        renderTeam(slide, slideInfo);
        break;
      case "impact":
        renderImpact(slide, slideInfo);
        break;
      case "roadmap":
        renderRoadmap(slide, slideInfo);
        break;
      case "closing":
        renderClosing(slide, slideInfo);
        break;
      default:
        throw new Error(`Unknown slide type: ${slideInfo.type}`);
    }
  });
  return pptx;
}

function svgFrame(theme, body) {
  const defs = `
    <defs>
      <linearGradient id="heroGradient" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" stop-color="${theme.bg === COLORS.navy ? "#0E1B2E" : "#F7FAFC"}" />
        <stop offset="100%" stop-color="${theme.bg === COLORS.navy ? "#15314D" : "#EEF4F8"}" />
      </linearGradient>
    </defs>
  `;
  return `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="${PREVIEW_W}" height="${PREVIEW_H}" viewBox="0 0 ${PREVIEW_W} ${PREVIEW_H}">
${defs}
<rect x="0" y="0" width="${PREVIEW_W}" height="${PREVIEW_H}" fill="url(#heroGradient)" />
${body}
</svg>`;
}

function svgShell(slideInfo) {
  const theme = themeFor(slideInfo);
  const isDark = slideInfo.theme === "dark";
  let body = "";
  if (isDark) {
    body += rectSvg(1180, -50, 360, 1000, "#0A8F88", 0, 0.2);
    body += circleSvg(1320, 210, 145, "none", 1, "#68E2D3", 4);
    body += circleSvg(1380, 275, 36, "#68E2D3", 0.95);
    body += lineSvg(1410, 305, 1520, 380, "#68E2D3", 4, 0.55);
    body += lineSvg(1415, 298, 1320, 460, "#68E2D3", 4, 0.55);
  } else {
    body += rectSvg(1240, -40, 330, 240, "#DFF8F0", 0, 0.4);
    body += lineSvg(110, 828, 1480, 828, "#D8E3EC", 2, 1);
  }
  if (slideInfo.type !== "cover" && slideInfo.type !== "closing") {
    body += svgTextBlock([slideInfo.title], 105, 120, {
      size: 46,
      color: slideInfo.theme === "dark" ? "#FFFFFF" : "#15263D",
      weight: 700,
      family: "Aptos Display, 'Segoe UI', Arial, sans-serif",
    });
    body += svgTextBlock([`0${slideInfo.id}`.slice(-2)], 1490, 840, {
      size: 18,
      color: slideInfo.theme === "dark" ? "#9CB4CC" : "#7D8CA0",
      weight: 700,
      anchor: "end",
    });
    body += svgTextBlock(["Inventics"], 1470, 88, {
      size: 16,
      color: slideInfo.theme === "dark" ? "#8EDFD5" : "#14968F",
      weight: 700,
      anchor: "end",
    });
  }
  return { theme, body };
}

function previewForSlide(slideInfo) {
  const { theme, body: shell } = svgShell(slideInfo);
  let body = shell;
  const titleColor = slideInfo.theme === "dark" ? "#FFFFFF" : "#15263D";
  const bodyColor = slideInfo.theme === "dark" ? "#DCE8F3" : "#5E7086";

  switch (slideInfo.type) {
    case "cover":
      body += svgTextBlock(["Pitch de impact social și tehnologic"], 110, 104, {
        size: 16,
        color: "#8EDFD5",
        weight: 700,
      });
      body += svgTextBlock([slideInfo.title], 110, 210, {
        size: 82,
        color: titleColor,
        weight: 700,
        family: "Aptos Display, 'Segoe UI', Arial, sans-serif",
      });
      body += svgTextBlock(wrapText(slideInfo.subtitle, 32), 110, 312, {
        size: 34,
        color: bodyColor,
        weight: 400,
      });
      body += lineSvg(110, 414, 270, 414, "#68E2D3", 5, 1);
      body += svgTextBlock(wrapText(slideInfo.notes[0], 42), 145, 476, {
        size: 28,
        color: bodyColor,
        weight: 400,
      });
      body += svgTextBlock(wrapText(slideInfo.notes[1], 42), 145, 556, {
        size: 28,
        color: bodyColor,
        weight: 400,
      });
      body += circleSvg(115, 463, 7, "#68E2D3");
      body += circleSvg(115, 543, 7, "#68E2D3");
      body += svgTextBlock(wrapText(slideInfo.solution, 44), 110, 664, {
        size: 30,
        color: "#FFFFFF",
        weight: 700,
      });
      break;
    case "problem":
      body += svgTextBlock(["Unde se vede cel mai clar ruptura de comunicare"], 110, 190, {
        size: 20,
        color: "#14968F",
        weight: 700,
      });
      [
        { x: 935, label: slideInfo.environments[0], fill: "#DFF8F0", color: "#0F756E" },
        { x: 1085, label: slideInfo.environments[1], fill: "#DDEAFE", color: "#15314D" },
        { x: 1238, label: slideInfo.environments[2], fill: "#FFE4DA", color: "#91492B" },
      ].forEach((pill, index) => {
        body += rectSvg(pill.x, 140, index === 2 ? 180 : 135, 46, pill.fill, 18);
        body += svgTextBlock([pill.label], pill.x + (index === 2 ? 90 : 67), 170, {
          size: 18,
          color: pill.color,
          weight: 700,
          anchor: "middle",
        });
      });
      body += svgTextBlock([slideInfo.points[0]], 110, 330, {
        size: 56,
        color: "#15263D",
        weight: 700,
      });
      body += svgTextBlock([slideInfo.points[1]], 110, 420, {
        size: 46,
        color: "#5B6D82",
        weight: 700,
      });
      body += svgTextBlock(
        wrapText(
          "Fără un instrument direct, accesul la informație și la servicii depinde de prezența unui intermediar.",
          54,
        ),
        110,
        555,
        { size: 28, color: "#5E7086", weight: 400 },
      );
      body += circleSvg(1120, 340, 140, "#DFF8F0", 1, "#12B8AE", 4);
      body += lineSvg(960, 350, 1115, 365, "#12B8AE", 5);
      body += lineSvg(1260, 365, 1445, 400, "#FF8A65", 5);
      body += svgTextBlock(["comunicare", "fragmentată"], 1120, 350, {
        size: 28,
        color: "#15314D",
        weight: 700,
        anchor: "middle",
      });
      break;
    case "award":
      body += svgTextBlock(wrapText(slideInfo.event, 28), 110, 250, {
        size: 54,
        color: titleColor,
        weight: 700,
      });
      body += svgTextBlock(["Rezultat internațional care confirmă relevanța soluției"], 110, 405, {
        size: 26,
        color: bodyColor,
        weight: 400,
      });
      body += circleSvg(1105, 310, 182, "#FFE6A8", 1, "#F3B83A", 7);
      body += svgTextBlock(["#1"], 1105, 305, {
        size: 88,
        color: "#8A5A00",
        weight: 700,
        anchor: "middle",
      });
      body += svgTextBlock([slideInfo.result], 1105, 376, {
        size: 32,
        color: "#8A5A00",
        weight: 700,
        anchor: "middle",
      });
      [
        { x: 110, label: slideInfo.proof[0], fill: "#183954" },
        { x: 340, label: slideInfo.proof[1], fill: "#14968F" },
        { x: 560, label: slideInfo.proof[2], fill: "#C46D43" },
      ].forEach((pill) => {
        body += rectSvg(pill.x, 510, pill.label.length > 10 ? 190 : 150, 48, `#${pill.fill}`, 18);
        body += svgTextBlock([pill.label], pill.x + (pill.label.length > 10 ? 95 : 75), 541, {
          size: 18,
          color: "#FFFFFF",
          weight: 700,
          anchor: "middle",
        });
      });
      break;
    case "context":
      body += svgTextBlock(["Soluții existente"], 110, 220, {
        size: 24,
        color: "#14968F",
        weight: 700,
      });
      slideInfo.existing.forEach((item, index) => {
        body += circleSvg(120, 284 + index * 78, 6, "#12B8AE");
        body += svgTextBlock([item], 145, 294 + index * 78, {
          size: 34,
          color: "#15263D",
          weight: 500,
        });
      });
      body += lineSvg(800, 190, 800, 690, "#D8E3EC", 2);
      body += svgTextBlock(["Limite ale alternativelor"], 860, 220, {
        size: 24,
        color: "#15314D",
        weight: 700,
      });
      slideInfo.issues.forEach((item, index) => {
        body += circleSvg(870, 284 + index * 84, 6, "#12B8AE");
        body += svgTextBlock(wrapText(item, 24), 895, 294 + index * 84, {
          size: 34,
          color: "#15263D",
          weight: 500,
        });
      });
      body += rectSvg(860, 480, 300, 125, "#15314D", 24);
      body += svgTextBlock(["2000-3000"], 895, 545, {
        size: 42,
        color: "#FFFFFF",
        weight: 700,
      });
      body += svgTextBlock(["interval frecvent de cost (lei)"], 895, 585, {
        size: 16,
        color: "#FFFFFF",
        weight: 400,
      });
      break;
    case "product":
      body += svgTextBlock([slideInfo.productName], 110, 250, {
        size: 58,
        color: titleColor,
        weight: 700,
      });
      body += svgTextBlock([slideInfo.feature], 110, 360, {
        size: 34,
        color: bodyColor,
        weight: 400,
      });
      [
        { x: 110, label: "fără cameră", fill: "#183954" },
        { x: 330, label: "portabil", fill: "#14968F" },
        { x: 520, label: "direct", fill: "#C46D43" },
      ].forEach((pill) => {
        body += rectSvg(pill.x, 418, pill.label === "fără cameră" ? 190 : 150, 48, `#${pill.fill}`, 18);
        body += svgTextBlock([pill.label], pill.x + (pill.label === "fără cameră" ? 95 : 75), 450, {
          size: 18,
          color: "#FFFFFF",
          weight: 700,
          anchor: "middle",
        });
      });
      body += svgTextBlock(["Acuratețe estimată"], 960, 238, {
        size: 18,
        color: "#8EDFD5",
        weight: 700,
      });
      body += svgTextBlock([slideInfo.accuracy], 956, 390, {
        size: 120,
        color: "#FFFFFF",
        weight: 700,
      });
      body += svgTextBlock(
        wrapText(
          "Conceptul central: un lanț simplu, purtabil și intuitiv care convertește gestul într-un mesaj lizibil.",
          30,
        ),
        955,
        510,
        { size: 27, color: bodyColor, weight: 400 },
      );
      break;
    case "flow":
      slideInfo.steps.forEach((step, index) => {
        const x = 120 + index * 380;
        const colors = ["#DFF8F0", "#DDEAFE", "#FFE4DA", "#FFF0C5"];
        const textColors = ["#0A6B65", "#183954", "#9B4B2B", "#8A5A00"];
        body += rectSvg(x, 330, 260, 120, colors[index], 24);
        body += svgTextBlock([step], x + 130, 395, {
          size: 34,
          color: textColors[index],
          weight: 700,
          anchor: "middle",
        });
        if (index < slideInfo.steps.length - 1) {
          body += `<polygon points="${x + 295},380 ${x + 340},350 ${x + 340},410" fill="#12B8AE" fill-opacity="0.2" />`;
        }
      });
      body += svgTextBlock(
        wrapText(
          "Fluxul este gândit pentru răspuns rapid: mișcarea este captată, interpretată și afișată aproape instant.",
          60,
        ),
        110,
        605,
        { size: 28, color: "#5E7086", weight: 400 },
      );
      break;
    case "advantages":
      [
        { x: 120, y: 310, w: 300, h: 110, fill: "#183954", label: slideInfo.items[0] },
        { x: 470, y: 610, w: 210, h: 95, fill: "#14968F", label: slideInfo.items[1] },
        { x: 900, y: 270, w: 190, h: 95, fill: "#C46D43", label: slideInfo.items[2] },
        { x: 1120, y: 560, w: 320, h: 110, fill: "#F3B83A", label: slideInfo.items[3], color: "#6F4A00" },
      ].forEach((box) => {
        body += rectSvg(box.x, box.y, box.w, box.h, box.fill, 24);
        body += svgTextBlock(wrapText(box.label, box.w > 240 ? 20 : 10), box.x + box.w / 2, box.y + 62, {
          size: box.w > 240 ? 28 : 30,
          color: box.color || "#FFFFFF",
          weight: 700,
          anchor: "middle",
        });
      });
      body += circleSvg(780, 460, 120, "#68E2D3", 0.16, "#68E2D3", 4);
      body += svgTextBlock(["mai multă", "autonomie"], 780, 450, {
        size: 26,
        color: "#FFFFFF",
        weight: 700,
        anchor: "middle",
      });
      break;
    case "competition":
      body += svgTextBlock([slideInfo.competitor], 110, 265, {
        size: 58,
        color: titleColor,
        weight: 700,
      });
      body += svgTextBlock(
        wrapText(
          "Referință utilă, dar greu de adoptat la scară largă în contexte educaționale.",
          38,
        ),
        110,
        368,
        { size: 28, color: bodyColor, weight: 400 },
      );
      body += rectSvg(110, 500, 320, 125, "#FF8A65", 24);
      body += svgTextBlock(["2500 lei"], 150, 570, {
        size: 48,
        color: "#FFFFFF",
        weight: 700,
      });
      body += svgTextBlock(["preț estimat"], 150, 610, {
        size: 18,
        color: "#FFFFFF",
        weight: 400,
      });
      slideInfo.issues.forEach((item, index) => {
        body += circleSvg(920, 332 + index * 105, 6, "#68E2D3");
        body += svgTextBlock([item], 945, 344 + index * 105, {
          size: 34,
          color: "#FFFFFF",
          weight: 500,
        });
      });
      break;
    case "barCompare": {
      body += svgTextBlock([slideInfo.message], 110, 188, {
        size: 20,
        color: "#14968F",
        weight: 700,
      });
      const max = Math.max(...slideInfo.prices.map((item) => item.value));
      slideInfo.prices.forEach((item, index) => {
        const y = 275 + index * 110;
        const w = 540 * (item.value / max);
        body += svgTextBlock([item.label], 110, y + 18, {
          size: 22,
          color: "#183954",
          weight: 700,
        });
        body += rectSvg(255, y, w, 48, `#${item.color}`, 18);
        body += svgTextBlock([`${item.value} lei`], 285 + w, y + 18, {
          size: 22,
          color: "#183954",
          weight: 700,
        });
      });
      body += rectSvg(900, 260, 250, 120, "#15314D", 24);
      body += rectSvg(1180, 260, 250, 120, "#12B8AE", 24);
      body += svgTextBlock([`${slideInfo.productionCost} lei`], 935, 325, {
        size: 38,
        color: "#FFFFFF",
        weight: 700,
      });
      body += svgTextBlock(["cost producție / unitate"], 935, 364, {
        size: 16,
        color: "#FFFFFF",
        weight: 400,
      });
      body += svgTextBlock([`${slideInfo.profit} lei`], 1215, 325, {
        size: 38,
        color: "#FFFFFF",
        weight: 700,
      });
      body += svgTextBlock(["profit brut / unitate"], 1215, 364, {
        size: 16,
        color: "#FFFFFF",
        weight: 400,
      });
      body += svgTextBlock(
        wrapText(
          "Mai accesibil, mai ușor de implementat în școli, cu marjă suficientă pentru dezvoltare.",
          30,
        ),
        900,
        520,
        { size: 27, color: "#5E7086", weight: 400 },
      );
      break;
    }
    case "market":
      [
        { x: 110, y: 410, w: 340, fill: "#183954", label: slideInfo.audiences[0] },
        { x: 500, y: 270, w: 270, fill: "#14968F", label: slideInfo.audiences[1] },
        { x: 520, y: 610, w: 190, fill: "#C46D43", label: slideInfo.audiences[2] },
        { x: 870, y: 300, w: 175, fill: "#F3B83A", label: slideInfo.audiences[3], color: "#6F4A00" },
        { x: 1160, y: 430, w: 250, fill: "#183954", label: slideInfo.audiences[4] },
      ].forEach((node) => {
        body += rectSvg(node.x, node.y, node.w, 88, node.fill, 24);
        body += svgTextBlock(wrapText(node.label, node.w > 250 ? 22 : 14), node.x + node.w / 2, node.y + 50, {
          size: node.w > 250 ? 24 : 26,
          color: node.color || "#FFFFFF",
          weight: 700,
          anchor: "middle",
        });
      });
      break;
    case "marketing":
      body += circleSvg(800, 420, 132, "#DFF8F0", 1, "#12B8AE", 4);
      body += svgTextBlock(["rețea de", "parteneri"], 800, 400, {
        size: 30,
        color: "#0A6B65",
        weight: 700,
        anchor: "middle",
      });
      [
        { x: 250, y: 260, w: 380, fill: "#DFF8F0", color: "#0A6B65", label: slideInfo.partners[0] },
        { x: 1020, y: 260, w: 240, fill: "#DDEAFE", color: "#183954", label: slideInfo.partners[1] },
        { x: 690, y: 650, w: 330, fill: "#FFE4DA", color: "#9B4B2B", label: slideInfo.partners[2] },
      ].forEach((pill) => {
        body += rectSvg(pill.x, pill.y, pill.w, 48, pill.fill, 18);
        body += svgTextBlock([pill.label], pill.x + pill.w / 2, pill.y + 31, {
          size: 18,
          color: pill.color,
          weight: 700,
          anchor: "middle",
        });
      });
      slideInfo.activities.forEach((item, index) => {
        const fills = ["#183954", "#14968F", "#C46D43"];
        body += rectSvg(110 + index * 220, 745, index === 2 ? 160 : 190, 48, fills[index], 18);
        body += svgTextBlock([item], 110 + index * 220 + (index === 2 ? 80 : 95), 776, {
          size: 18,
          color: "#FFFFFF",
          weight: 700,
          anchor: "middle",
        });
      });
      break;
    case "promotion":
      body += svgTextBlock(["Canale proprii"], 110, 220, {
        size: 20,
        color: "#9FDCD3",
        weight: 700,
      });
      [
        { y: 270, label: slideInfo.channels[0], fill: "#183954", w: 210 },
        { y: 350, label: slideInfo.channels[1], fill: "#14968F", w: 180 },
        { y: 430, label: slideInfo.channels[2], fill: "#C46D43", w: 235 },
      ].forEach((pill) => {
        body += rectSvg(110, pill.y, pill.w, 48, pill.fill, 18);
        body += svgTextBlock([pill.label], 110 + pill.w / 2, pill.y + 31, {
          size: 18,
          color: "#FFFFFF",
          weight: 700,
          anchor: "middle",
        });
      });
      body += svgTextBlock(["Concursuri internaționale vizate"], 865, 220, {
        size: 20,
        color: "#9FDCD3",
        weight: 700,
      });
      slideInfo.contests.forEach((item, index) => {
        const fills = ["#0A8F88", "#A65833", "#A17314"];
        const textColor = index === 2 ? "#FFF3D6" : "#FFFFFF";
        body += rectSvg(865, 270 + index * 82, 500, 56, fills[index], 20);
        body += svgTextBlock([item], 900, 306 + index * 82, {
          size: 24,
          color: textColor,
          weight: 700,
        });
      });
      break;
    case "costs": {
      body += svgTextBlock(["Cost estimat / unitate"], 110, 190, {
        size: 20,
        color: "#14968F",
        weight: 700,
      });
      let cursor = 110;
      slideInfo.costs.forEach((item) => {
        const w = 630 * (item.value / slideInfo.total);
        body += rectSvg(cursor, 245, w, 54, `#${item.color}`, 0);
        cursor += w;
      });
      slideInfo.costs.forEach((item, index) => {
        body += rectSvg(110, 360 + index * 82, 460, 54, `#${item.color}`, 20);
        body += svgTextBlock([`${item.label}   ${item.value} lei`], 145, 395 + index * 82, {
          size: 23,
          color: item.color === COLORS.gold ? "#6F4A00" : "#FFFFFF",
          weight: 700,
        });
      });
      body += rectSvg(985, 320, 300, 125, "#15314D", 24);
      body += svgTextBlock([`${slideInfo.total} lei`], 1025, 385, {
        size: 48,
        color: "#FFFFFF",
        weight: 700,
      });
      body += svgTextBlock(["total estimat"], 1025, 425, {
        size: 18,
        color: "#FFFFFF",
        weight: 400,
      });
      break;
    }
    case "team":
      [
        { x: 690, y: 260, label: slideInfo.roles[0], fill: "#14968F" },
        { x: 255, y: 385, label: slideInfo.roles[1], fill: "#183954" },
        { x: 520, y: 645, label: slideInfo.roles[2], fill: "#C46D43" },
        { x: 865, y: 660, label: slideInfo.roles[3], fill: "#F3B83A", color: "#6F4A00" },
        { x: 1140, y: 380, label: slideInfo.roles[4], fill: "#183954" },
      ].forEach((box) => {
        body += rectSvg(box.x, box.y, 235, 76, box.fill, 20);
        body += svgTextBlock([box.label], box.x + 117.5, box.y + 47, {
          size: 22,
          color: box.color || "#FFFFFF",
          weight: 700,
          anchor: "middle",
        });
      });
      break;
    case "impact":
      [
        { x: 110, fill: "#DFF8F0", color: "#0A6B65", label: slideInfo.items[0] },
        { x: 565, fill: "#DDEAFE", color: "#183954", label: slideInfo.items[1] },
        { x: 1020, fill: "#FFE4DA", color: "#9B4B2B", label: slideInfo.items[2] },
      ].forEach((box) => {
        body += rectSvg(box.x, 310, 370, 245, box.fill, 24);
        body += svgTextBlock(wrapText(box.label, 18), box.x + 185, 430, {
          size: 38,
          color: box.color,
          weight: 700,
          anchor: "middle",
        });
      });
      break;
    case "roadmap":
      body += lineSvg(150, 650, 1350, 310, "#68E2D3", 5, 1);
      [
        { x: 205, y: 606, label: slideInfo.milestones[0], fill: "#183954" },
        { x: 640, y: 486, label: slideInfo.milestones[1], fill: "#14968F" },
        { x: 1080, y: 360, label: slideInfo.milestones[2], fill: "#C46D43" },
      ].forEach((point) => {
        body += circleSvg(point.x, point.y, 12, "#68E2D3");
        body += rectSvg(point.x - 70, point.y - 105, 290, 74, point.fill, 20);
        body += svgTextBlock(wrapText(point.label, 21), point.x + 75, point.y - 58, {
          size: 20,
          color: "#FFFFFF",
          weight: 700,
          anchor: "middle",
        });
      });
      break;
    case "closing":
      body += svgTextBlock(["Inventics"], 110, 106, {
        size: 16,
        color: "#8EDFD5",
        weight: 700,
      });
      body += svgTextBlock(wrapText(slideInfo.title, 24), 110, 335, {
        size: 80,
        color: titleColor,
        weight: 700,
        family: "Aptos Display, 'Segoe UI', Arial, sans-serif",
      });
      body += svgTextBlock([slideInfo.subtitle], 110, 500, {
        size: 34,
        color: bodyColor,
        weight: 400,
      });
      body += lineSvg(110, 560, 280, 560, "#68E2D3", 5, 1);
      break;
    default:
      throw new Error(`Missing preview renderer for ${slideInfo.type}`);
  }

  return svgFrame(theme, body);
}

async function writePreviews() {
  const outputFiles = [];
  for (const slideInfo of slidesData) {
    const svg = previewForSlide(slideInfo);
    const pngPath = path.join(PREVIEW_DIR, `slide-${String(slideInfo.id).padStart(2, "0")}.png`);
    await sharp(Buffer.from(svg)).png().toFile(pngPath);
    outputFiles.push(pngPath);
  }
  await writeContactSheet(outputFiles);
  return outputFiles;
}

async function writeContactSheet(files) {
  const cols = 4;
  const thumbW = 400;
  const thumbH = 225;
  const gap = 20;
  const rows = Math.ceil(files.length / cols);
  const width = cols * thumbW + (cols - 1) * gap;
  const height = rows * thumbH + (rows - 1) * gap;
  const composites = [];
  for (let index = 0; index < files.length; index += 1) {
    const col = index % cols;
    const row = Math.floor(index / cols);
    const buffer = await sharp(files[index]).resize(thumbW, thumbH).png().toBuffer();
    composites.push({
      input: buffer,
      left: col * (thumbW + gap),
      top: row * (thumbH + gap),
    });
  }
  await sharp({
    create: {
      width,
      height,
      channels: 4,
      background: "#0B1322",
    },
  })
    .composite(composites)
    .png()
    .toFile(CONTACT_SHEET_PATH);
}

async function main() {
  ensureDirs();
  const pptx = buildPresentation();
  await pptx.writeFile({ fileName: PPTX_PATH });
  const previewFiles = await writePreviews();
  const manifest = {
    created_at: new Date().toISOString(),
    slide_count: slidesData.length,
    pptx: PPTX_PATH,
    previews: previewFiles,
    contact_sheet: CONTACT_SHEET_PATH,
  };
  fs.writeFileSync(MANIFEST_PATH, `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
  console.log(JSON.stringify(manifest, null, 2));
}

main().catch((error) => {
  console.error(error && error.stack ? error.stack : String(error));
  process.exit(1);
});
