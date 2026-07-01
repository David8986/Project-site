"""In-app glossary and plain-English explanations for the analysis app."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from PySide6 import QtCore, QtWidgets


CARD_STYLE = """
QGroupBox {
    background: #2b2b2b;
    border: 1px solid #777777;
    margin-top: 8px;
    padding: 6px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 6px;
    padding: 0 2px;
    color: #eeeeee;
    font-weight: bold;
}
QLineEdit {
    background: #2b2b2b;
    color: #eeeeee;
    border: 1px solid #777777;
    padding: 3px;
}
QTabWidget::pane {
    border: 1px solid #777777;
}
QTabBar::tab {
    background: #2b2b2b;
    border: 1px solid #777777;
    padding: 4px 8px;
}
QTabBar::tab:selected {
    background: #444444;
}
QLabel {
    color: #eeeeee;
}
"""

SECTION_NAME_MAP = {
    "Quick Start": "Pornire rapida",
    "Input and Import": "Intrare si import",
    "Alignment": "Aliniere",
    "Vegetation and Masks": "Vegetatie si masti",
    "Suspicious Regions": "Regiuni suspecte",
    "Measurements and Analysis": "Masuratori si analiza",
    "Indices": "Indici",
    "Reports and Outputs": "Rapoarte si iesiri",
}


@dataclass(frozen=True, slots=True)
class TermDefinition:
    """One structured glossary term."""

    section: str
    term: str
    short: str
    used_for: str
    formula: str = "n/a"
    higher_lower: str = "n/a"
    caution: str = "n/a"


def _value(path: Mapping[str, Any], *keys: str, default: Any = None) -> Any:
    """Return a nested mapping value."""

    current: Any = path
    for key in keys:
        if not isinstance(current, Mapping):
            return default
        current = current.get(key)
    return default if current is None else current


def _fmt(value: Any) -> str:
    """Format a live value for display."""

    if value in (None, ""):
        return "indisponibil"
    if isinstance(value, float):
        return f"{value:.4g}"
    return str(value)


def _term_html(term: TermDefinition) -> str:
    """Format a glossary term using the required field structure."""

    return (
        f"<b>Termen:</b> {term.term}"
        f"<br><b>Pe scurt:</b> {term.short}"
        f"<br><b>Folosit pentru:</b> {term.used_for}"
        f"<br><b>Formula/regula:</b> {term.formula}"
        f"<br><b>Semnificatie valori mari/mici:</b> {term.higher_lower}"
        f"<br><b>Limite/atentie:</b> {term.caution}"
    )


class GlossaryWidget(QtWidgets.QWidget):
    """Searchable, tabbed explanation view for controls, outputs, and terms."""

    SECTION_ORDER = (
        "Pornire rapida",
        "Intrare si import",
        "Aliniere",
        "Vegetatie si masti",
        "Regiuni suspecte",
        "Masuratori si analiza",
        "Indici",
        "Rapoarte si iesiri",
    )

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._text_labels: list[QtWidgets.QLabel] = []
        self._term_cards: list[tuple[QtWidgets.QGroupBox, str]] = []

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        content = QtWidgets.QWidget()
        content.setStyleSheet(CARD_STYLE)
        layout = QtWidgets.QVBoxLayout(content)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)
        root.addWidget(content)

        title = QtWidgets.QLabel("Glosar / Explicarea termenilor")
        title.setStyleSheet("font-size: 16pt; font-weight: 700; color: #eef5f7;")
        layout.addWidget(title)

        intro = QtWidgets.QLabel(
            "Referinta in limbaj simplu pentru pipeline-ul determinist curent. "
            "Foloseste taburile sau caseta de cautare ca sa gasesti controale, termeni, formule si semnificatia iesirilor."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("color: #b7c0c6;")
        layout.addWidget(intro)
        self._text_labels.append(intro)

        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText("Cauta termeni, praguri, formule, iesiri...")
        self.search.textChanged.connect(self._apply_filter)
        layout.addWidget(self.search)

        self.tabs = QtWidgets.QTabWidget()
        layout.addWidget(self.tabs, 1)

        self._section_layouts: dict[str, QtWidgets.QVBoxLayout] = {}
        self._build_sections()
        self._populate_terms()

    def set_live_values(
        self,
        *,
        ndvi_threshold: float,
        spot_threshold: float,
        spot_min_area: int,
        texture_window: int,
    ) -> None:
        """Update the live control-value summary."""

        radius = max(1, int(texture_window) // 2)
        footprint = (2 * radius) + 1
        self.live_values_label.setText(
            "<b>Termen:</b> Valorile curente ale controalelor"
            "<br><b>Pe scurt:</b> Valorile exacte ale pragurilor si controalelor setate acum in aplicatia de analiza."
            "<br><b>Folosit pentru:</b> Verificarea valorilor care vor fi aplicate la urmatoarea rulare."
            "<br><b>Formula/regula:</b> "
            f"<code>NDVI &gt; {_fmt(float(ndvi_threshold))}</code>; "
            f"<code>score_map &gt;= {_fmt(float(spot_threshold))}</code>; "
            f"<code>area_px &gt;= {int(spot_min_area)}</code>; "
            f"<code>texture footprint = {footprint}x{footprint}</code>; local standard deviation."
            "<br><b>Semnificatie valori mari/mici:</b> Un prag mai mare pentru spoturi si o arie minima mai mare sunt mai stricte. "
            "Un prag NDVI mai mic poate include vegetatie mai slaba sau stresata."
            "<br><b>Limite/atentie:</b> Acestea sunt controale deterministe, nu setari de diagnostic al bolii."
        )

    def set_report(self, report: Mapping[str, Any] | None) -> None:
        """Update loaded-report context without recomputing analysis."""

        if not report:
            self.report_context_label.setText(
                "<b>Termen:</b> Contextul esantionului incarcat"
                "<br><b>Pe scurt:</b> Nu este incarcat inca niciun raport de analiza."
                "<br><b>Folosit pentru:</b> Afisarea sursei, mastii, maparii si disponibilitatii indicilor pentru esantionul curent."
                "<br><b>Formula/regula:</b> indisponibil"
                "<br><b>Semnificatie valori mari/mici:</b> indisponibil"
                "<br><b>Limite/atentie:</b> Ruleaza analiza sau reincarca un folder de iesire pentru a popula aceasta sectiune."
            )
            return

        source = _value(report, "source", default={})
        vegetation = _value(report, "vegetation", "mask", default={})
        alignment = _value(source, "alignment", default={})
        mapping = _value(report, "target_band_mapping", default={})
        status_counts: dict[str, int] = {}
        if isinstance(mapping, Mapping):
            for item in mapping.values():
                if not isinstance(item, Mapping):
                    continue
                status = str(item.get("status", "unknown"))
                status_counts[status] = status_counts.get(status, 0) + 1
        status_text = ", ".join(f"{key}: {value}" for key, value in sorted(status_counts.items())) or "n/a"
        availability = _value(report, "whole_leaf", "index_availability", default={})
        available_indices = _value(availability, "available_indices", default=[])
        unavailable_indices = _value(availability, "unavailable_indices", default=[])
        available_text = ", ".join(available_indices) if isinstance(available_indices, list) else _fmt(available_indices)
        unavailable_text = ", ".join(unavailable_indices) if isinstance(unavailable_indices, list) else _fmt(unavailable_indices)
        self.report_context_label.setText(
            "<b>Termen:</b> Contextul esantionului incarcat"
            f"<br><b>Pe scurt:</b> Esantion {_fmt(_value(source, 'sample_id'))}; "
            f"{_fmt(_value(source, 'source_data_kind'))}; "
            f"tip date analiza {_fmt(_value(source, 'analysis_data_kind'))}."
            f"<br><b>Folosit pentru:</b> Pixeli de vegetatie {_fmt(_value(source, 'vegetation_pixels'))}; "
            f"metoda masca {_fmt(_value(vegetation, 'method'))}; "
            f"aliniere {_fmt(_value(alignment, 'status'))} prin {_fmt(_value(alignment, 'mode'))}."
            f"<br><b>Formula/regula:</b> Statusuri mapare benzi tinta: {status_text}."
            f"<br><b>Semnificatie valori mari/mici:</b> Indici disponibili pe roluri: {_fmt(available_text)}. "
            f"Indisponibili: {_fmt(unavailable_text)}."
            f"<br><b>Limite/atentie:</b> Calibrare aplicata: {_fmt(_value(source, 'calibration_applied'))}. "
            "Verifica avertismentele din raport pentru aliniere cu incredere scazuta, intensitate bruta sau benzi lipsa."
        )

    def contents_text(self) -> str:
        """Return a test-friendly text dump of the glossary."""

        return "\n".join(label.text() for label in self._text_labels)

    def _build_sections(self) -> None:
        """Create scrollable section tabs."""

        for section in self.SECTION_ORDER:
            scroll = QtWidgets.QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)

            page = QtWidgets.QWidget()
            page_layout = QtWidgets.QVBoxLayout(page)
            page_layout.setContentsMargins(10, 10, 10, 10)
            page_layout.setSpacing(8)
            page_layout.addStretch(1)
            scroll.setWidget(page)
            self.tabs.addTab(scroll, section)
            self._section_layouts[section] = page_layout

    def _section_key(self, section: str) -> str:
        """Map legacy English section names to the Romanian tab names."""

        return SECTION_NAME_MAP.get(section, section)

    def _add_card(self, section: str, title: str, widget: QtWidgets.QWidget, filter_text: str) -> None:
        """Add a card to a section tab."""

        card = QtWidgets.QGroupBox(title)
        card_layout = QtWidgets.QVBoxLayout(card)
        card_layout.addWidget(widget)
        layout = self._section_layouts[self._section_key(section)]
        layout.insertWidget(max(0, layout.count() - 1), card)
        self._term_cards.append((card, filter_text.casefold()))

    def _add_term(self, term: TermDefinition) -> None:
        """Add one structured term card."""

        label = QtWidgets.QLabel(_term_html(term))
        label.setTextFormat(QtCore.Qt.TextFormat.RichText)
        label.setWordWrap(True)
        label.setStyleSheet("color: #dce7ec;")
        self._text_labels.append(label)
        filter_text = " ".join(
            [
                term.section,
                self._section_key(term.section),
                term.term,
                term.short,
                term.used_for,
                term.formula,
                term.higher_lower,
                term.caution,
            ]
        )
        self._add_card(term.section, term.term, label, filter_text)

    def _apply_filter(self, text: str) -> None:
        """Show only cards matching the current search text."""

        query = text.strip().casefold()
        for card, filter_text in self._term_cards:
            card.setVisible(not query or query in filter_text)

    def _populate_terms(self) -> None:
        """Populate the tabbed glossary."""

        self.live_values_label = QtWidgets.QLabel()
        self.live_values_label.setTextFormat(QtCore.Qt.TextFormat.RichText)
        self.live_values_label.setWordWrap(True)
        self._text_labels.append(self.live_values_label)
        self._add_card("Pornire rapida", "Valorile curente ale controalelor", self.live_values_label, "valori curente praguri controale")

        self.report_context_label = QtWidgets.QLabel()
        self.report_context_label.setTextFormat(QtCore.Qt.TextFormat.RichText)
        self.report_context_label.setWordWrap(True)
        self._text_labels.append(self.report_context_label)
        self._add_card("Pornire rapida", "Contextul esantionului incarcat", self.report_context_label, "context esantion incarcat raport sursa")
        self.set_report({})

        for term in _terms():
            self._add_term(term)


def _terms() -> list[TermDefinition]:
    """Return the structured glossary terms."""

    terms = [
        TermDefinition(
            "Quick Start",
            "Analysis workflow",
            "The normal order of operations for the Analysis app.",
            "Load or import a sample, optionally align mixed images, run masking, compute indices, detect suspicious regions, then inspect/export reports.",
            "Load input -> map bands/roles -> align if mixed -> vegetation mask -> score map -> connected regions -> reports.",
            "More available bands and better alignment usually make analysis more meaningful.",
            "This workflow is deterministic candidate finding, not AI diagnosis.",
        ),
        TermDefinition(
            "Quick Start",
            "What is safe to trust first",
            "The app is strongest at showing what data exists and what calculations were possible.",
            "Checking mapping, missing bands, calibration status, alignment status, mask method, and warnings before interpreting values.",
            "Read Summary, Glossary, JSON Report, and warnings.",
            "Higher confidence comes from calibrated, aligned, narrowband data.",
            "RGB-derived values and resize-only alignment should be treated as exploratory.",
        ),
        TermDefinition(
            "Input and Import",
            "Mixed image bundle",
            "A JSON spec that combines RGB images and grayscale band images into one sample.",
            "Cases like one RGB photo plus one NIR 850 nm image.",
            "RGB expands to RED/GREEN/BLUE; grayscale rows use manually assigned role and wavelength.",
            "More correctly assigned roles allow more indices.",
            "Wrong wavelength/role assignments create wrong downstream results.",
        ),
        TermDefinition(
            "Input and Import",
            "RGB image",
            "A normal color image with red, green, and blue channels.",
            "Visual background, RGB-like masking, and NDVI-like calculations if a separate NIR band exists.",
            "R -> approx 650 nm, G -> approx 556 nm, B -> approx 532 nm.",
            "RGB is useful for shape/color context.",
            "RGB channels are broad display channels, not calibrated narrow spectral bands.",
        ),
        TermDefinition(
            "Input and Import",
            "Grayscale band image",
            "A single-channel image that the user assigns to one role/wavelength.",
            "Adding NIR, red-edge, water-band, or custom bands from separate captures.",
            "Example: role NIR, wavelength 850 nm.",
            "Correct assignment enables role-aware indices.",
            "If the image is not registered to RGB, per-pixel index maps can be misleading.",
        ),
        TermDefinition(
            "Input and Import",
            "Band role",
            "A semantic name for what a band is used as.",
            "Generalizing analysis across datasets with different exact wavelengths.",
            "RED prefers 680 then 650; GREEN prefers 556 then 532; RED_EDGE 725; NIR 850; WATER_BAND 940.",
            "Available roles increase available analysis.",
            "Fallback roles may be approximate and are reported with caveats.",
        ),
        TermDefinition(
            "Input and Import",
            "Band mapping",
            "Connecting requested target wavelengths to actual source wavelengths.",
            "Extracting or marking target bands before analysis.",
            "Statuses: exact: source wavelength is within exact tolerance; nearest: closest source band is used; interpolated: estimated from surrounding bands; missing: no usable band.",
            "Exact is strongest; missing disables dependent indices.",
            "Nearest/interpolated mappings are useful but less direct than exact source bands.",
        ),
        TermDefinition(
            "Input and Import",
            "Raw intensity vs reflectance",
            "Raw intensity is original sensor/image value; reflectance is calibrated using references.",
            "Knowing whether values are comparable across captures.",
            "<code>reflectance = (raw - dark) / (white - dark)</code>.",
            "Reflectance is generally more comparable than raw intensity.",
            "JPEG/PNG RGB and most manual mixed images are raw/mixed-image intensity unless a calibrated adapter provides reflectance.",
        ),
        TermDefinition(
            "Alignment",
            "Alignment mode",
            "The method used to register mixed images before analysis.",
            "Making RGB, NIR, red-edge, and other separate images line up in the same frame.",
            "Options: none, resize only, automatic ECC, automatic feature/edge, automatic contour/mask.",
            "Automatic modes can correct shifts/warps; resize only only changes dimensions.",
            "Registration can fail or fall back; always check report alignment status and warnings.",
        ),
        TermDefinition(
            "Alignment",
            "Reference image",
            "The image that all other mixed inputs are transformed into.",
            "Keeping the final aligned stack in one coordinate system.",
            "Transform maps moving image -> reference image.",
            "A clear, sharp image with full leaf/scene coverage is usually better.",
            "If the reference is cropped or distorted, all aligned outputs inherit that frame.",
        ),
        TermDefinition(
            "Alignment",
            "Translation",
            "A transform that moves an image left/right/up/down only.",
            "Correcting simple camera shifts between captures.",
            "<code>x' = x + dx</code>, <code>y' = y + dy</code>.",
            "Simple and stable when images differ only by position.",
            "Cannot fix rotation, scale, shear, perspective, or parallax.",
        ),
        TermDefinition(
            "Alignment",
            "Euclidean",
            "A rigid transform: translation plus rotation.",
            "Aligning images where the camera rotated slightly but scale stayed mostly the same.",
            "Rotation + translation, with distances mostly preserved.",
            "More flexible than translation; safer than affine when only rotation/shift is expected.",
            "Cannot correct scale changes, shear, or perspective.",
        ),
        TermDefinition(
            "Alignment",
            "Affine",
            "A transform that handles translation, rotation, scale, and shear.",
            "Default automatic alignment model for modest viewpoint/scale differences.",
            "2x3 matrix applied globally to the full image.",
            "More flexible than Euclidean.",
            "Can overfit if features are poor; does not model full perspective depth/parallax.",
        ),
        TermDefinition(
            "Alignment",
            "Homography",
            "A perspective transform for planar scenes.",
            "Stronger registration when the scene behaves like a flat plane.",
            "3x3 projective matrix.",
            "Most flexible global option.",
            "Can distort leaves badly if the scene is not planar or feature matches are weak.",
        ),
        TermDefinition(
            "Alignment",
            "Automatic ECC",
            "Image registration that optimizes global image similarity.",
            "Aligning images with similar silhouettes or intensity patterns.",
            "OpenCV ECC alignment using selected transform model.",
            "Higher confidence means better similarity optimization.",
            "Different modalities such as RGB vs NIR can be harder; fallback may occur.",
        ),
        TermDefinition(
            "Alignment",
            "Automatic feature/edge",
            "Feature matching on edge-enhanced images.",
            "Aligning images with visible corners, veins, leaf edges, or texture.",
            "ORB features + RANSAC transform estimation.",
            "More inliers/confidence is better.",
            "Smooth leaves or low texture may produce too few reliable matches.",
        ),
        TermDefinition(
            "Alignment",
            "Automatic contour/mask",
            "Alignment from broad foreground shape.",
            "Fallback when features are weak but the leaf/plant silhouette is visible.",
            "Foreground mask moments estimate translation/rotation/scale.",
            "Works best when one dominant foreground object exists.",
            "Multiple plants or messy backgrounds can confuse the contour.",
        ),
        TermDefinition(
            "Alignment",
            "Resize only",
            "Changes image size to match the reference without content registration.",
            "Emergency fallback when images differ only by dimensions or automatic alignment fails.",
            "Resize moving image to reference shape.",
            "Fast but low confidence.",
            "Does not correct shifts, rotation, scale, perspective, or parallax.",
        ),
        TermDefinition(
            "Vegetation and Masks",
            "Vegetation mask",
            "The pixels treated as plant/leaf area for later analysis.",
            "Limiting averages and suspicious-region detection to vegetation-like pixels.",
            "Preferred: <code>NDVI &gt; threshold</code>; fallbacks use NDVI-like, RGB excess green, or percentile threshold.",
            "More mask pixels means more tissue included; fewer means stricter leaf selection.",
            "A strict mask can exclude damaged/low-NIR tissue; inspect the mask overlay.",
        ),
        TermDefinition(
            "Vegetation and Masks",
            "NDVI mask threshold",
            "The cutoff used to decide which pixels are vegetation when NIR and red are available.",
            "Building the common vegetation mask before averages and suspicious-region analysis.",
            "<code>NDVI = (850 - 680) / (850 + 680 + eps)</code>; mask rule <code>NDVI &gt; threshold</code>. If 680 is missing but 650 and 850 exist: <code>(850 - 650) / (850 + 650 + eps)</code>.",
            "Higher threshold is stricter. Lower threshold includes weaker/stressed vegetation.",
            "RGB+NIR fallback is NDVI-like, not true narrowband NDVI.",
        ),
        TermDefinition(
            "Vegetation and Masks",
            "RGB excess green mask",
            "An RGB-only vegetation fallback based on green dominance.",
            "Making a rough mask when NIR is unavailable.",
            "<code>(2 * GREEN) - RED - BLUE</code>, then percentile threshold.",
            "Higher green excess is more leaf-like in many RGB photos.",
            "Sensitive to lighting, shadows, background color, and camera white balance.",
        ),
        TermDefinition(
            "Vegetation and Masks",
            "Common vegetation mask",
            "One shared mask used after alignment for all downstream metrics.",
            "Keeping whole-leaf spectra, spot detection, and overlays consistent.",
            "Computed after mixed images are aligned into the reference frame.",
            "Better alignment means the common mask matches all bands better.",
            "Misalignment causes band values to be sampled from wrong pixels.",
        ),
        TermDefinition(
            "Vegetation and Masks",
            "Suspicious mask",
            "Binary mask of pixels above the suspiciousness score threshold.",
            "Visualizing and labeling candidate affected regions.",
            "<code>suspicious_mask = score_map &gt;= spot_threshold</code> inside vegetation mask.",
            "More pixels pass when the threshold is lower.",
            "It is a candidate mask, not a disease mask.",
        ),
        TermDefinition(
            "Suspicious Regions",
            "Suspicious regions",
            "Connected components in the suspicious mask.",
            "Finding local affected-area candidates instead of relying only on whole-leaf averages.",
            "Threshold score map -> morphology cleanup -> connected components -> min-area filter.",
            "Larger/more intense regions rank higher.",
            "Regions are deterministic candidates, not AI classifications.",
        ),
        TermDefinition(
            "Suspicious Regions",
            "Spot threshold",
            "The cutoff applied to the combined suspiciousness score map.",
            "Controlling strictness of candidate detection.",
            "<code>score_map = clip(weighted_average(anomaly_maps), 0, 1) * vegetation_mask</code>; <code>suspicious_mask = score_map &gt;= threshold</code>.",
            "Higher threshold = stricter/fewer detections. Lower threshold = more detections.",
            "It is not NDVI directly and not a disease probability.",
        ),
        TermDefinition(
            "Suspicious Regions",
            "Spot min area",
            "Minimum connected-component size in pixels.",
            "Removing tiny speckles/noise after thresholding.",
            "<code>area_px &gt;= min_area_px</code>.",
            "Higher value removes more small regions. Lower value keeps smaller candidates.",
            "Too high can remove real small lesions; too low can keep noise/veins.",
        ),
        TermDefinition(
            "Suspicious Regions",
            "Texture window",
            "Neighborhood size used for local variation maps.",
            "Detecting local roughness/variance in red, red-edge, and NIR roles using local standard deviation.",
            "Local standard deviation over a square footprint; current live value shows actual footprint.",
            "Larger windows smooth details; smaller windows react to speckles and veins.",
            "Texture can highlight veins/noise as well as symptoms.",
        ),
        TermDefinition(
            "Suspicious Regions",
            "Contour outlines",
            "Clean boundary lines around suspicious candidate masks.",
            "Default affected-area visualization that keeps the leaf visible.",
            "Contours are drawn from the suspicious mask; OpenCV anti-aliased lines when available.",
            "Selected region is highlighted more strongly.",
            "Contours show candidate boundaries, not certainty.",
        ),
        TermDefinition(
            "Suspicious Regions",
            "Bounding boxes",
            "Rectangles around connected suspicious regions.",
            "Quickly locating and selecting candidate regions.",
            "Box from component min/max x/y coordinates.",
            "Boxes are easier to see than exact masks.",
            "They can look cluttered, so they are optional and off by default.",
        ),
        TermDefinition(
            "Measurements and Analysis",
            "ROI",
            "Region Of Interest: selected pixels summarized together.",
            "Comparing whole leaf, suspicious regions, and manually selected areas.",
            "ROI values are averages over selected pixels.",
            "Larger ROI averages are more stable; small ROI can show local detail.",
            "ROI meaning depends on selection quality and alignment/mask quality.",
        ),
        TermDefinition(
            "Measurements and Analysis",
            "Histogram",
            "A distribution of display pixel values for the current background image.",
            "Checking brightness, contrast, clipping, and dynamic range.",
            "Counts pixels per value bin, usually 0..255 display-normalized values.",
            "Wider histogram means more contrast/spread.",
            "Current histogram is display-oriented, not calibrated reflectance statistics.",
        ),
        TermDefinition(
            "Measurements and Analysis",
            "Mean",
            "Average value over pixels or a selected region.",
            "Summarizing band, index, ROI, or display values.",
            "<code>sum(values) / count(values)</code>.",
            "Higher/lower depends on the band or index being measured.",
            "Mean can hide localized spots, which is why suspicious-region detection exists.",
        ),
        TermDefinition(
            "Measurements and Analysis",
            "Standard deviation",
            "How spread out values are around the mean.",
            "Texture, histogram stats, and anomaly z-scores.",
            "Square root of average squared deviation from the mean.",
            "Higher std means more variation/texture/noise.",
            "High variation may be biology, veins, shadows, or sensor noise.",
        ),
        TermDefinition(
            "Measurements and Analysis",
            "Severity score",
            "A deterministic ranking score for suspicious regions.",
            "Sorting candidate spots by area and suspiciousness.",
            "<code>mean_suspiciousness_score * log1p(area_px)</code>.",
            "Higher score ranks earlier.",
            "Not a diagnosis and not comparable across datasets without validation.",
        ),
    ]

    index_terms = [
        ("NDVI", "Vegetation contrast using NIR and red.", "(NIR - RED) / (NIR + RED)", "NIR 850; RED 680, or RGB-red 650 for NDVI-like fallback.", "Higher often means stronger NIR/red vegetation contrast.", "RGB+NIR output is labeled NDVI-like, not true narrowband NDVI."),
        ("NDRE", "Red-edge vegetation contrast.", "(NIR - RED_EDGE) / (NIR + RED_EDGE)", "NIR 850 and RED_EDGE 725.", "Higher often means stronger red-edge contrast.", "Unavailable without red-edge."),
        ("SR_RED", "Simple ratio of NIR to red.", "NIR / RED", "NIR 850 and RED 680.", "Higher means NIR is larger relative to red.", "Sensitive to raw intensity scale if not calibrated."),
        ("SR_RE", "Simple ratio of NIR to red-edge.", "NIR / RED_EDGE", "NIR 850 and RED_EDGE 725.", "Higher means NIR is larger relative to red-edge.", "Unavailable without red-edge."),
        ("GNDVI", "Vegetation contrast using NIR and green.", "(NIR - GREEN) / (NIR + GREEN)", "NIR 850 and GREEN 556.", "Higher means stronger NIR/green contrast.", "Green from RGB is approximate if using a normal photo."),
        ("GRI", "Green ratio index used here as NIR over green.", "NIR / GREEN", "NIR 850 and GREEN 556.", "Higher means more NIR relative to green.", "Raw intensity and lighting can affect it."),
        ("CI_RE", "Chlorophyll index red-edge proxy.", "(NIR / RED_EDGE) - 1", "NIR 850 and RED_EDGE 725.", "Higher can indicate stronger NIR/red-edge separation.", "Proxy only; not calibrated chlorophyll measurement."),
        ("RE_RED_DIFF", "Difference between red-edge and red.", "RED_EDGE - RED", "RED_EDGE 725 and RED 680.", "Higher means red-edge is above red.", "Unavailable without red-edge and red."),
        ("RE_SLOPE", "Simple red-edge slope proxy.", "(RED_EDGE - RED) / (725 - 680)", "725 and 680.", "Higher means steeper red-edge lift.", "Only a coarse two-band slope."),
        ("NDWI_850_940", "Water-sensitive normalized difference proxy.", "(NIR - WATER_BAND) / (NIR + WATER_BAND)", "NIR 850 and WATER_BAND 940.", "Higher/lower depends on water-band response and calibration.", "Unavailable without 940; not a complete water-status model."),
        ("WATER_RATIO", "Ratio of water band to NIR.", "WATER_BAND / NIR", "940 and 850.", "Higher means 940 is larger relative to NIR.", "Sensitive to calibration and lighting."),
        ("GRND", "Green-red normalized difference.", "(GREEN - RED) / (GREEN + RED)", "GREEN 556 and RED 680.", "Higher means green exceeds red more strongly.", "RGB green/red are broad approximate channels."),
        ("RED_GREEN_RATIO", "Ratio of red to green.", "RED / GREEN", "RED 680 and GREEN 556.", "Higher means red is larger relative to green.", "Can be affected by lighting and camera color processing."),
        ("NIR_RED_DIFF", "Difference between NIR and red.", "NIR - RED", "850 and 680.", "Higher means NIR exceeds red more.", "Raw difference depends on intensity scale."),
        ("NIR_RED_SUM", "Sum of NIR and red.", "NIR + RED", "850 and 680.", "Higher means combined brightness/reflectance is higher.", "Not normalized; scale-sensitive."),
        ("NIR_RE_DIFF", "Difference between NIR and red-edge.", "NIR - RED_EDGE", "850 and 725.", "Higher means NIR exceeds red-edge more.", "Unavailable without red-edge."),
        ("NIR_RE_SUM", "Sum of NIR and red-edge.", "NIR + RED_EDGE", "850 and 725.", "Higher means combined brightness/reflectance is higher.", "Not normalized; scale-sensitive."),
    ]
    for name, short, formula, used_for, higher_lower, caution in index_terms:
        terms.append(
            TermDefinition(
                "Indices",
                name,
                short,
                used_for,
                f"<code>{formula}</code>",
                higher_lower,
                caution,
            )
        )

    terms.extend(
        [
            TermDefinition(
                "Reports and Outputs",
                "JSON report",
                "The complete structured machine-readable report.",
                "Downstream analysis, debugging, and preserving full metadata.",
                "Saved as <code>mapping_report.json</code> and <code>indices_report.json</code>.",
                "More complete than CSV.",
                "Harder to read manually than the readable report.",
            ),
            TermDefinition(
                "Reports and Outputs",
                "Readable report",
                "Human-friendly rendering of the JSON report.",
                "Quick inspection inside the app.",
                "Built from the structured JSON report.",
                "n/a",
                "Short labels are deterministic summaries, not diagnosis.",
            ),
            TermDefinition(
                "Reports and Outputs",
                "CSV exports",
                "Spreadsheet-friendly outputs.",
                "Opening band mapping, average bands, indices, summary, and spots in Excel/Sheets.",
                "One table per output type.",
                "Easier to scan than JSON.",
                "CSV flattens nested details; use JSON for full metadata.",
            ),
            TermDefinition(
                "Reports and Outputs",
                "Band images",
                "Display-normalized PNGs for extracted target bands.",
                "Visual checking/debugging of extracted layers.",
                "Saved under <code>bands/band_*.png</code>.",
                "Brighter PNG means brighter display-normalized value.",
                "PNG normalization is display-only; scientific arrays are kept separately.",
            ),
            TermDefinition(
                "Reports and Outputs",
                "Overlay exports",
                "Saved visualization images from the overlay tab.",
                "Sharing or reviewing outline/fill/heatmap/vegetation visualizations.",
                "Export current view or all overlay modes.",
                "n/a",
                "They are visual summaries, not new scientific measurements.",
            ),
            TermDefinition(
                "Reports and Outputs",
                "Warnings",
                "Report caveats about missing data, low-confidence alignment, raw intensity, or unavailable roles.",
                "Preventing over-interpretation.",
                "Collected from loaders, mapping, calibration, alignment, masks, and detectors.",
                "More warnings mean more caution is needed.",
                "Warnings do not always mean the run failed; they say what to verify.",
            ),
        ]
    )
    return terms


__all__ = ["GlossaryWidget"]
