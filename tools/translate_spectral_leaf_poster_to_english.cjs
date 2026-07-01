const fs = require("fs");
const path = require("path");

const JSZip = require("C:/Users/david/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/.pnpm/pptxgenjs@4.0.1/node_modules/jszip");

const SRC = "C:/Users/david/OneDrive/Desktop/SpectraLeaf_poster_7x10.pptx";
const OUT = "C:/Users/david/OneDrive/Desktop/SpectraLeaf_poster_7x10_EN.pptx";

const translations = {
  1: "SpectraLeaf",
  2: "NIR-based multispectral optical system for detecting plant stress",
  3: "Introduction and problem",
  4: [
    "Plant stress can change reflectance before clear color changes appear in RGB photographs.",
    "In the NIR range, after about 700 nm, the signal is influenced by the leaf's internal structure, moisture and degradation.",
    "The project aims to offer a low-cost alternative to commercial multispectral systems, using a multispectral camera.",
  ].map((line) => `• ${line}`).join("\n"),
  5: "97.5%",
  6: "average shape agreement of the camera-spectrometer curves",
  7: "11.65%",
  8: "average NIR decrease observed in Set 1",
  9: "Materials, filters and principle",
  10: [
    "Spectrometer: Ocean Optics USB2000+XR1-ES, wavelength range lambda = 200-1025 nm, resolution 1.7-2.1 nm, 2048 CCD pixels.",
    "Camera: the same leaf is photographed through filters at 532, 556, 680, 725, 850 and 940 nm.",
    "For each image, the leaf is detected, then the median reflected light from the leaf is calculated for a specific spectral component inside the leaf mask.",
  ].map((line) => `• ${line}`).join("\n"),
  11: "The camera points are not a continuous spectrum, but they can show whether the general shape and NIR variation are close to the reference.",
  12: "Built system and data flow",
  13: "Experimental workflow: the leaf is measured first with the spectrometer, then photographed inside the box through the 6 filters. The application aligns the images, finds the leaf area, removes part of the background through a mask and extracts median values for each band.",
  14: "Validation: spectrometer vs camera",
  15: "The comparison overlays the continuous spectrometer curves with the points/curves obtained from the multispectral camera. For the blue curve, the correlation coefficient is r = 0.982, and for the orange curve r = 0.967. The average of these values indicates a shape agreement of about 97.5%.",
  16: "Comparison formula used in the interpretation: for each camera band, the median brightness value of the leaf is compared with the spectrometer intensity around the same wavelength. In the graphs, the spectrometer is smoothed using medians over 10 nm intervals.",
  17: "Results: healthy vs unhealthy leaves",
  18: "Interpretation, limitations and conclusion",
  19: "The correct interpretation is that SpectraLeaf validates the working principle: a camera with filters can follow the general shape of the spectrum and can highlight relevant differences in NIR. The value of 97.5% is a statistical agreement with the spectrometer for the analyzed data, not a universal diagnostic accuracy.",
  20: "Conclusion: the system is suitable as a low-cost experimental platform for multispectral analysis, and the results justify developing an application that automatically compares the camera signal with reference measurements.",
  21: "References",
  22: "[1] GoPhotonics, USB2000+XR1-ES - Ocean Optics.  [2] Ocean Optics, Legacy Spectrometers Support.  [3] SpectraLeaf experimental data: spectrometer/camera graphs, multispectral images and application outputs.",
  23: "The photos are made using our multispectral camera and then loaded into the program we built. The program creates a graph with all wavelengths, automatically calculates indices such as NDVI, GNDVI and NDRE, and then creates a visual map of the plant to show possible stress areas.",
  24: "The reasoning obtained by comparing the two methods shows that the camera-and-filter system can record light values relevant to plant health.",
  25: "In this experimental set, the absolute reflectance value of the unhealthy leaf clearly decreases in the IR/NIR range by 10.7% with the spectrometer and by 12.6% with the camera, resulting in an average decrease of about 11.65%. This is the most important case for practical validation of the system, because the camera reproduces the difference observed with the spectrometer very well.",
  26: "The statistical agreement of the camera-spectrometer curve shapes, calculated as the average of the correlation coefficients in the validation set, is about 97.5%. This value supports the idea that SpectraLeaf can be used as a promising experimental platform for determining plant health, provided that the database is expanded and additional calibration is performed.",
  27: "In its current form, the system offers an accessible method for investigating the spectral response of leaves, while the software application adds another level of interpretation by masking the vegetation area, calculating indices and visually representing risk zones. Future directions include testing a larger number of leaves, stricter lighting control, black/white reference calibration and training artificial-intelligence-assisted classification models.",
};

function xmlEscape(text) {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

function xmlDecode(text) {
  return String(text)
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&amp;/g, "&")
    .replace(/&quot;/g, '"')
    .replace(/&apos;/g, "'");
}

function firstMatch(text, patterns) {
  for (const pattern of patterns) {
    const match = text.match(pattern);
    if (match) return match[0];
  }
  return "";
}

function makeParagraphs(text, pPr, rPr) {
  const lines = String(text).split("\n");
  return lines.map((line) => {
    return `<a:p>${pPr}<a:r>${rPr}<a:t>${xmlEscape(line)}</a:t></a:r></a:p>`;
  }).join("");
}

function replaceTextBody(shapeXml, replacement) {
  return shapeXml.replace(/<p:txBody>[\s\S]*?<\/p:txBody>/, (txBody) => {
    const prefixMatch = txBody.match(/^<p:txBody>([\s\S]*?)(?=<a:p[\s>])/);
    const prefix = prefixMatch ? prefixMatch[1] : "<a:bodyPr/><a:lstStyle/>";
    const firstParagraph = firstMatch(txBody, [/<a:p[\s\S]*?<\/a:p>/]);
    const pPr = firstMatch(firstParagraph, [/<a:pPr[\s\S]*?<\/a:pPr>/, /<a:pPr[^>]*\/>/]);
    const rPr = firstMatch(firstParagraph, [/<a:rPr[\s\S]*?<\/a:rPr>/, /<a:rPr[^>]*\/>/]);
    return `<p:txBody>${prefix}${makeParagraphs(replacement, pPr, rPr)}</p:txBody>`;
  });
}

async function main() {
  if (!fs.existsSync(SRC)) {
    throw new Error(`Source PPTX not found: ${SRC}`);
  }

  const zip = await JSZip.loadAsync(fs.readFileSync(SRC));
  const slidePath = "ppt/slides/slide1.xml";
  let xml = await zip.file(slidePath).async("string");
  xml = xml.replace(/lang="ro-RO"/g, 'lang="en-US"');

  let textShapeIndex = 0;
  xml = xml.replace(/<p:sp[\s\S]*?<\/p:sp>/g, (shapeXml) => {
    const textBits = [...shapeXml.matchAll(/<a:t>([\s\S]*?)<\/a:t>/g)].map((m) => xmlDecode(m[1]));
    if (!textBits.join("").trim()) return shapeXml;
    textShapeIndex += 1;
    const replacement = translations[textShapeIndex];
    if (!replacement) return shapeXml;
    return replaceTextBody(shapeXml, replacement);
  });

  zip.file(slidePath, xml);
  const output = await zip.generateAsync({ type: "nodebuffer" });
  fs.writeFileSync(OUT, output);
  console.log(OUT);
  console.log(`Translated text shapes: ${Object.keys(translations).length}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
