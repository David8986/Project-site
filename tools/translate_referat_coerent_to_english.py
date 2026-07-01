"""Translate the coherent Romanian referat DOCX to English while preserving images."""

from __future__ import annotations

from pathlib import Path

from docx import Document


SOURCE = Path(r"C:\Users\david\OneDrive\Desktop\referat (2) - revizuit coerent.docx")
OUTPUT = Path(r"C:\Users\david\OneDrive\Desktop\referat (2) - revizuit coerent - English.docx")


PARAGRAPH_TRANSLATIONS = {
    0: "90SpectraLeaf",
    1: "-",
    2: "NIR-based multispectral optical system for early detection of plant stress",
    4: "I. Purpose of the project",
    5: (
        "The purpose of this project is to develop an accessible, low-cost multispectral system capable of helping "
        "identify plant stress early by analyzing how plants reflect light in the visible and near-infrared range, "
        "especially in the NIR region. The project starts from the idea that many plant problems, such as water "
        "stress, nutritional deficiencies, or early forms of physiological degradation, can produce changes in the "
        "spectral response before the symptoms become clearly visible to the naked eye."
    ),
    6: (
        "By building this system, the project aims to create a more accessible alternative to existing commercial "
        "multispectral solutions, which are often expensive and difficult to use in educational contexts or small-scale "
        "research. The project combines optics, electronics, image acquisition, and digital analysis, with the final "
        "goal of building an experimental application capable of highlighting relevant differences between healthy "
        "plants and stressed or diseased plants using selected spectral bands and a modular hardware architecture."
    ),
    8: "II. Physical principles of the project",
    9: "Spectral dependence of photosynthesis.",
    10: (
        "In the emission spectrum of solar radiation, the maximum energy values of total radiation (direct and diffuse) "
        "in cloud-free conditions correspond mainly to the green and blue-green regions. Experimental research has "
        "shown that, for most terrestrial plants, photosynthesis is more intense in the red and indigo-violet regions "
        "of the solar spectrum. The figure shown above represents the spectral curve of photosynthesis and demonstrates "
        "the spectral dependence of energy absorption by plastid pigments (chlorophyll a and chlorophyll b). Therefore, "
        "the two high-efficiency peaks of photosynthesis correspond to wavelengths between 400 nm and 700 nm. The "
        "violet-indigo region is probably convenient from an energetic point of view for supporting the photochemical "
        "reactions. On the other hand, orange-red radiation predominates in sunlight during the evening before sunset. "
        "At those hours, the photosynthetic apparatus of plants still works intensely due to other physical factors: "
        "the ambient temperature remains high, the leaves of many plants are positioned almost perpendicular to the "
        "incoming solar rays, and those rays are efficient for photosynthesis."
    ),
    11: (
        "Of course, the influence of light energy on plant growth and development is accompanied by other physical "
        "processes as well: reflection, diffusion, and the transport of this energy inside the leaf. Even so, the graph "
        "of yield as a function of wavelength generally follows the graph of pigment photosynthetic activity. "
        "Experimental studies also show that biomass growth and development stages are stimulated by radiation in the "
        "yellow-green range (500-600 nm). This is explained by the complexity of photosynthesis and by the particular "
        "way in which light is absorbed at the leaf surface."
    ),
    12: (
        "It has been demonstrated that ultraviolet radiation reduces electron transport in photosynthesis cycles and "
        "inhibits photosynthetic reactions even in the early stages of photosynthesis. In addition to reducing the "
        "intensity of photosynthesis, it has a depressing effect on growth, development, and flowering. At high UV "
        "fluxes, plants lose a large part of this information because a normal camera mixes the spectrum into only "
        "three broad channels. SpectraLeaf aims to separate light selectively into narrow bands so that each photograph "
        "becomes a measurement closer to the biological properties of the plant."
    ),
    15: (
        "The action of infrared and ultraviolet radiation on photosynthesis was also studied. It was found that the "
        "effect of infrared radiation in the 730-1200 nm range is determined by its weak absorption by plants (only a "
        "few percent), as shown in the graph on the left, where after the region around 700 nm there is a strong light "
        "reflection peak between 700 and 1400 nm."
    ),
    18: (
        "Using the principle of light reflection and absorption at different wavelengths, images can be captured in "
        "these spectral regions, and by analyzing their brightness, several physical indices can be calculated. These "
        "indices are useful for the early identification of plant diseases:"
    ),
    20: (
        "1. NDVI - standard index for vegetation health (biomass and vigor)\n"
        "Formula: NDVI = (NIR - Red) / (NIR + Red).\n"
        "[-1; 0] = water / non-vegetated surfaces\n"
        "[0; 0.2] = bare soil / very weak vegetation\n"
        "[0.2; 0.5] = moderate vegetation\n"
        "[0.5; 1] = healthy, dense vegetation"
    ),
    21: (
        "NDVI is used to evaluate the general condition of vegetation, especially for estimating vigor, density, and "
        "vegetation cover. It is a basic indicator in agricultural monitoring and remote sensing, used to identify "
        "healthy areas compared with areas affected by stress or lack of vegetation."
    ),
    23: (
        "2. NDRE - index sensitive to chlorophyll content (stress and advanced growth stages)\n"
        "Formula: NDRE = (NIR - RedEdge) / (NIR + RedEdge)\n"
        "[-1; 0] = non-vegetation / severe stress\n"
        "[0; 0.2] = weak vegetation\n"
        "[0.2; 1] = healthy vegetation"
    ),
    24: (
        "NDRE is used to evaluate vegetation health in advanced growth stages and is more effective than NDVI in dense "
        "crops. It is used for early detection of physiological stress and variations in chlorophyll content when the "
        "vegetation is mature."
    ),
    26: (
        "3. GNDVI - green-based index that highlights chlorophyll\n"
        "Formula: GNDVI = (NIR - Green) / (NIR + Green)\n"
        "[-1; 0] = non-vegetation\n"
        "[0; 0.3] = weak vegetation\n"
        "[0.3; 1] = healthy vegetation"
    ),
    27: (
        "GNDVI is used to monitor photosynthetic activity and plant nutritional status, having increased sensitivity "
        "to chlorophyll variation. It is frequently used in precision agriculture to evaluate subtle differences in "
        "crop condition."
    ),
    30: (
        "4. CIre - chlorophyll index (red-edge)\n"
        "Formula: CIre = (NIR / RedEdge) - 1\n"
        "[-1; 0] = stress / lack of chlorophyll\n"
        "[0; 1] = moderate chlorophyll\n"
        "[1; +infinity] = high chlorophyll"
    ),
    31: (
        "CIre is used to estimate chlorophyll content and evaluate the physiological condition of plants. It is an "
        "important indicator for the early identification of nutritional deficiencies and stress, before visible "
        "symptoms appear."
    ),
    33: (
        "5. NDWI - vegetation moisture index (Gao)\n"
        "Formula: NDWI = (NIR - SWIR) / (NIR + SWIR)\n"
        "[-1; 0] = dry vegetation\n"
        "[0; 0.2] = moderate moisture\n"
        "[0.2; 1] = well-hydrated vegetation"
    ),
    34: (
        "NDWI is used to evaluate the water content of vegetation and to monitor water stress. It is applied in "
        "drought analysis and in determining the hydration level of crops."
    ),
    37: "III. Method of obtaining the experimental data",
    38: (
        "The system designed for the image acquisition stage is an optical assembly in which we planned to use a "
        "rotating mechanism with 7 spectral filters. Its working principle consists of placing each filter in front of "
        "the lens one after another, so that the same scene is recorded in several wavelength bands. The major "
        "advantage of this solution is that it allows multispectral imaging using a single sensor, reducing cost and "
        "complexity compared with systems based on several cameras. At the same time, this approach introduces specific "
        "challenges, such as the need to align images captured successively, the influence of scene movement, and the "
        "reduction of available light after filtering."
    ),
    43: (
        "For obtaining the images, we used an OV9281 Global Shutter Camera Module, for which the housing with the 7 "
        "filters was modeled, and a modified phone camera sensor used in earlier experiments. From the phone camera we "
        "removed the IR-cut filter, which normally blocks infrared radiation."
    ),
    51: (
        "In the image on the left is the phone camera sensor with the IR-cut filter, and on the right is the image "
        "after the filter was removed."
    ),
    58: "Image at 680 nm                                      image at 850 nm",
    60: (
        "For data processing, we built a program that processes the data automatically. Using different algorithms, it "
        "finds the exact vegetation surface from several images, builds a mask, measures the brightness of the pixels "
        "inside that mask, and calculates multiple indices presented at the beginning of the paper, such as NDVI, NDWI, "
        "and GNDVI. An example of the direct program result is shown below:"
    ),
    61: "IV. Experimental data",
    62: (
        "Using the interface of the program we built, we can analyze in detail the 7 images of a leaf captured at "
        "different wavelengths. The images used in one of our tests are shown in the table below:"
    ),
    64: (
        "Using these images, the program identifies the vegetation area and creates a selected region of interest, from "
        "which it calculates the mean pixel intensity and several indices used to determine the analysis results. It "
        "then creates a graph and an image map where areas with low, medium, or high risk of plant problems can be "
        "identified."
    ),
    65: (
        "To strengthen the scientific basis of the project, the intensity graph of the photographed leaf shows a strong "
        "similarity to a representative graph presented in Section II of the paper, together with a graph showing the "
        "values of the important indices:"
    ),
    66: (
        "In addition to identifying the vegetation area, the program uses an algorithm that observes strong increases "
        "and decreases in pixel light intensity and marks them as \"suspicious areas\". Of course, because the mask may "
        "sometimes include a"
    ),
    67: (
        "part of the background, false alarms may also appear, but they are easy to identify. This result is shown "
        "below by the white outlined perimeters:"
    ),
    69: "V. Conclusion of the measurements and of the project",
    70: (
        "The conclusion of the project is that plant problems can be measured and identified successfully using an "
        "inexpensive camera compared with most other options, while also giving the user the freedom to perform their "
        "own vegetation measurements. In addition, the rotating system that changes the spectrum visible to the camera "
        "is an advantage, because it avoids the need for other expensive equipment or many separate cameras, while also "
        "maintaining control over the exact wavelengths measured individually."
    ),
    71: (
        "The program written by us, after analyzing the 7 images, can overlay them when small deviations occur during "
        "photo capture. By calculating all indices and creating representative graphs and overlays on the images to "
        "highlight problematic areas, it gives the user another level of control over the collected data and over their "
        "own interpretation in case of errors, however rare, during data collection and processing."
    ),
    73: "VI. Bibliography",
    90: (
        "An important objective is the calculation of vegetation indices. The best-known one is NDVI, which compares "
        "reflectance in red with reflectance in near-infrared. NDVI remains useful, but it can saturate in very dense or "
        "very vigorous crops, where real differences between plants become difficult to observe. For this reason, the "
        "project should also include indices based on the red-edge region, such as NDRE, which preserves better "
        "sensitivity to chlorophyll variations. Because of this, the proposed band set for SpectraLeaf is essential: "
        "blue (approximately 475 nm), green (560 nm), red (668 nm), red-edge (717 or 730 nm), and near-infrared "
        "(842 or 860 nm)."
    ),
    92: (
        "This configuration is close to the bands used in mature commercial systems, while remaining realistic enough "
        "for an accessible prototype."
    ),
    95: "III. Project objectives",
    96: (
        "The general objective of the project is to develop and justify a low-cost multispectral system capable of "
        "contributing to the monitoring of plant health by analyzing how plants reflect electromagnetic radiation in "
        "different spectral bands, with emphasis on the visible, red-edge, and near-infrared regions. In this context, "
        "the project aims both to experimentally validate the basic idea and to design a technical solution that can "
        "later be extended into a more precise, robust, and useful system for real applications. More precisely, we "
        "have five main objectives:"
    ),
    97: (
        "The first objective is to study reflectance differences between healthy plants and plants under stress, based "
        "on the observation that physiological changes caused by lack of water, nutritional deficiencies, tissue "
        "damage, or other environmental factors influence how vegetation absorbs and reflects light. This objective "
        "aims to identify the spectral regions where the contrast between plant states is strong enough to be used in "
        "an early detection system."
    ),
    98: (
        "The second objective is the practical validation of the concept using a modified phone camera as the initial "
        "experimental platform. Because the project does not yet have the final dedicated camera, this stage is meant "
        "to demonstrate that relevant differences between vegetation and other surfaces, as well as between plants in "
        "different states, can be observed and analyzed even in a preliminary phase. This approach allows the idea to "
        "be tested under real conditions, with accessible resources, and provides an experimental basis for later "
        "development."
    ),
    99: (
        "The third objective is to design an optical acquisition system based on a rotating mechanism with 7 spectral "
        "filters. The central idea is for the same scene to be captured successively in several wavelength bands, so "
        "that a multispectral representation can be obtained using a single sensor and a relatively simple mechanical "
        "assembly. This objective includes choosing the relevant spectral bands, designing the mechanical architecture "
        "of the filter holder, analyzing how the filters should be positioned above the lens, and anticipating "
        "difficulties related to image alignment or light losses."
    ),
    100: (
        "The fourth objective is to evaluate the advantages and limitations of a low-cost solution in relation to "
        "commercial multispectral systems already available on the market. In this sense, the project aims to show "
        "what an accessible solution can offer in terms of cost, flexibility, and modularity, but also where "
        "compromises appear regarding spectral precision, acquisition stability, or processing complexity. This "
        "comparison is important for positioning the project realistically and for arguing its usefulness as an "
        "educational, experimental, or small-scale research alternative."
    ),
    101: (
        "The fifth objective is to prepare a technical basis for the later development of the project toward automatic "
        "image processing and classification assisted by machine-learning algorithms. Even though the current stage "
        "focuses mainly on concept, optical acquisition, and experimental validation, the project is designed so that "
        "the data obtained can later be used to train models capable of recognizing patterns associated with different "
        "forms of plant stress. In this way, the system does not remain only a capture device, but becomes the "
        "foundation of a broader platform for intelligent plant-health analysis."
    ),
    102: "IV. Problem identified for solving and current state of the field",
    103: (
        "The main problem from which this project starts is that plant stress is often detected too late when the "
        "evaluation is based only on direct visual observation. In many situations, plants begin to undergo internal "
        "physiological changes before their leaves clearly change color, before their surfaces show obvious signs of "
        "degradation, or before the symptoms can be easily recognized by a human observer. Because of this, intervention "
        "often takes place only after the problem has already appeared, and the impact on plant development or "
        "productivity can become significant."
    ),
    104: (
        "In agriculture, horticulture, and environmental monitoring, early identification of stress is important because "
        "it allows faster and better-targeted action. A plant affected by water, nutritional, or thermal stress can show "
        "subtle changes in its spectral reflectance long before these changes are visible in a normal RGB image. This "
        "means that simple visual analysis is not always sufficient for a correct and early evaluation of vegetation "
        "condition, especially over larger areas or in contexts where objective and repeatable comparisons are needed."
    ),
    105: (
        "At present, one known direction in vegetation analysis is based on multispectral imaging and on the use of "
        "spectral bands that are sensitive to physiological changes in plants. Among these, the NIR and red-edge "
        "regions are considered especially useful because they provide relevant information about the internal "
        "structure of the leaf, chlorophyll content, and variations associated with the general condition of vegetation. "
        "This is why these spectral regions are frequently used in crop-condition evaluation, in the calculation of "
        "vegetation indices, and in the detection of differences between healthy and affected plants."
    ),
    106: (
        "However, commercial systems capable of performing such analyses are usually expensive and difficult to access "
        "for students, educational activities, small laboratories, or people who want to experiment without investing "
        "large amounts of money. Professional multispectral equipment often includes specialized sensors, dedicated "
        "optics, proprietary software, and complex acquisition platforms. These make the systems efficient, but not very "
        "suitable for school projects or independent prototyping. This situation creates a clear gap between what is "
        "theoretically possible and what is practically accessible for a project developed in a pre-university context."
    ),
    107: (
        "This need provides the justification for the present project. A more accessible alternative is necessary, one "
        "capable of demonstrating the operating principle of multispectral analysis without depending on expensive "
        "infrastructure. The project proposes exactly this direction: a low-cost experimental solution built around a "
        "simplified optical and mechanical concept, allowing relevant spectral differences in vegetation to be observed "
        "and creating a bridge between the theory of multispectral imaging and its practical application in a realistic "
        "educational and technical context."
    ),
    109: (
        "Therefore, the identified problem is not only technical, but also related to accessibility. Efficient methods "
        "for spectral analysis of vegetation already exist, but they are not accessible enough for everyone who could "
        "benefit from them for educational, experimental, or local use. The project aims to respond to this problem by "
        "developing a more accessible solution that is still scientifically justified and capable of highlighting the "
        "potential of using NIR and red-edge bands for early monitoring of plant condition."
    ),
    111: (
        "The graph above represents the reflectance of several objects of interest at different wavelengths. Three "
        "lines can be observed, each representing:\n"
        "\t- the continuous line represents the visibility of healthy plants, which increases strongly after passing "
        "the Red Edge region, around the NIR range;"
    ),
    112: (
        "- the dashed line represents the visibility of unhealthy plants, which is significantly lower compared with "
        "healthy plants;"
    ),
    113: (
        "- the dotted, almost horizontal line represents soil, which remains almost constant throughout most of the "
        "graph."
    ),
    114: (
        "6. Methods used, description of the systems created or used, demonstrations, sizing, organization of the "
        "studies, and other elements related to the team's activity"
    ),
    116: (
        "The methodology of the project was built to combine theoretical documentation, comparative analysis of "
        "existing solutions, preliminary experimental testing, and the design of our own technical system. The general "
        "approach was applied-experimental, typical for projects that aim to solve a practical problem through a "
        "combination of knowledge from optics, electronics, image analysis, and plant-environment monitoring. This "
        "methodological choice is also consistent with the nature of the project, which aims to create a concrete "
        "monitoring solution, not only a theoretical analysis."
    ),
    117: (
        "The first method used was documentary research. Information was analyzed regarding the spectral response of "
        "vegetation, the relationship between plant health and reflectance in different spectral bands, and the role of "
        "the NIR and red-edge regions in analyzing the physiological condition of leaves. This study served to justify "
        "the choice of bands of interest and to support the orientation of the project toward multispectral imaging. In "
        "addition, the documentation also included the analysis of existing commercial or experimental systems in order "
        "to understand which characteristics are essential and what compromises appear when cost reduction is pursued."
    ),
    120: (
        "The system used in the initial experimental stage is therefore a modified phone camera used as a validation "
        "platform. The role of this system is to check whether differences between plant and non-plant surfaces, and "
        "between plants in different states, can be highlighted through a capture system that is also sensitive in the "
        "near-infrared region. This system is not presented as the final version of the project, but as an intermediate "
        "exploration tool, useful for confirming feasibility and guiding later development. In this way, the "
        "experimental part remains realistic and well connected to the current stage of the project."
    ),
    121: (
        "The system designed for the next stage is an optical assembly based on a rotating mechanism with 7 spectral "
        "filters. Its operating principle consists of positioning each filter successively in front of the lens so that "
        "the same scene is recorded in several wavelength bands. The major advantage of this solution is that it allows "
        "multispectral imaging using a single sensor, reducing cost and complexity compared with systems based on "
        "multiple cameras. At the same time, this approach introduces specific challenges, such as the need to align "
        "images captured successively, the influence of scene movement, and the decrease in available light after "
        "filtering."
    ),
    122: (
        "From a mechanical point of view, the design of the filter assembly took into account the size of the available "
        "filters and the size of the optical area of the lens. The compatibility between small filters and the lens was "
        "analyzed, as well as the need to place the filters as close as possible to the optical system in order to "
        "reduce field losses and vignetting. It was also considered that each filter must be positioned with sufficient "
        "precision to avoid alignment deviations between captures and to preserve acquisition repeatability. These "
        "sizing considerations were treated not only as construction details, but as important elements for the final "
        "quality of the data."
    ),
    123: (
        "Regarding demonstrations and tests, the project methodology is based on visual and analytical comparison "
        "between images taken under different conditions. The purpose is to observe whether vegetation behaves "
        "differently depending on the selected spectral band and whether these differences can become useful for "
        "evaluating plant condition. At the current stage, the demonstration is preliminary and mainly aims to confirm "
        "the existence of significant contrast, not to obtain a fully automated agronomic diagnosis. This limitation is "
        "accepted and is normal for a project under development."
    ),
    124: (
        "The organization of the study was based on a logical sequence of activities. First, the problem was defined "
        "and the theoretical documentation was completed. Then, possible technical solutions were analyzed and the "
        "initial testing platform was selected. After this, the concept of the filter-based system was developed and "
        "the main optical and mechanical constraints were identified. In parallel, the experimental observations to be "
        "followed were formulated, and the development directions for the next stages were established. This "
        "organization shows that the project was built methodically, through successive steps, and not as a simple "
        "collection of separate ideas."
    ),
    125: (
        "Another important element of the methodology is that the project was designed from the beginning as an "
        "extendable system. The data and observations obtained in the current stage are not the final goal, but the "
        "foundation for later development. In a future stage, the multispectral images obtained through successive "
        "filtering could be corrected, aligned, and processed automatically, then used to extract indicators or train "
        "classification models. Thus, the current methodology is not isolated, but prepares the transition toward a "
        "more advanced platform in which the hardware and software parts work together."
    ),
    126: (
        "Through the set of methods used, the project aims to maintain a balance between technical realism and "
        "scientific ambition. On one hand, accessible resources and an imperfect initial platform are used, making the "
        "project practically achievable. On the other hand, the choice of spectral bands, the logic of the optical "
        "system, and the orientation toward plant-condition analysis keep the project relevant from a scientific and "
        "applied point of view. This combination of accessibility, practical testing, and theoretical grounding is one "
        "of the defining characteristics of the project."
    ),
    128: "V. Stages completed",
    129: (
        "The development of the project was organized into several successive stages so that the initial idea could be "
        "gradually transformed into a justified technical concept and a realistic experimental direction. The first "
        "stage consisted of identifying the problem to be addressed: the difficulty of early detection of plant stress "
        "through simple visual observation. In this phase, the practical relevance of the topic was analyzed and it was "
        "established that an optical system capable of using information from the near-infrared region could represent "
        "a promising solution for highlighting differences that are not easily visible in the visible spectrum."
    ),
    130: (
        "The second stage involved theoretical documentation on how plants interact with electromagnetic radiation. In "
        "this stage, essential concepts related to light absorption and reflectance, the behavior of vegetation in the "
        "visible bands, the red-edge region, and the NIR domain were studied, as well as the usefulness of these "
        "spectral regions in analyzing the physiological condition of plants. During the same phase, examples of "
        "multispectral applications in agriculture were analyzed and the general principles of professional systems "
        "were compared with the possibilities of a prototype built with more limited resources."
    ),
    131: (
        "The third stage was dedicated to exploring possible technical solutions for image acquisition. Several sensor "
        "and capture-platform options were analyzed, with emphasis on the advantages and limitations of each. In the "
        "absence of a dedicated multispectral camera, a modified phone camera was chosen as an initial experimental "
        "solution because it allows preliminary investigation of vegetation response in the near-infrared region. The "
        "purpose of this stage was not to obtain a perfect spectral measurement, but to verify the feasibility of the "
        "idea and obtain a first level of practical validation."
    ),
    132: (
        "The fourth stage consisted of defining the general architecture of the proposed system. In this phase, the idea "
        "of using a rotating mechanism with 7 spectral filters was formulated, with the filters positioned successively "
        "in front of the camera so that the same scene could be recorded in several wavelength bands. This solution was "
        "chosen because of the desire to build a modular and flexible system that does not require the simultaneous use "
        "of several cameras and that can be extended later. In parallel, the optical and mechanical constraints of such "
        "an assembly were analyzed, including filter size, lens diameter, proximity to the objective, and possible "
        "effects such as vignetting or loss of light."
    ),
    133: (
        "The fifth stage focused on preliminary testing and on structuring the experimental direction. In this stage, "
        "the types of scenes and plant subjects that could provide useful contrast between plant and non-plant surfaces, "
        "as well as between plants in different states, were identified. Even though the final system is not yet fully "
        "implemented, this stage made it possible to establish a working method and define initial experimental "
        "observations that will form the basis for future comparisons."
    ),
    134: (
        "The sixth stage was oriented toward integrating all project components into a coherent vision. Thus, the "
        "theoretical documentation, initial testing with the modified camera, analysis of the limitations of this "
        "solution, and design of the rotating-filter system were brought together into a single concept: a low-cost "
        "multispectral system for monitoring plant condition. This stage was important because it transformed the "
        "project from a general idea into a justified technical proposal, with clear objectives, development stages, "
        "and real possibilities for extension."
    ),
    135: (
        "In its current form, the project is at an intermediate stage between concept validation and the development of "
        "a more advanced implementation. This is an advantage from a research perspective, because it makes it possible "
        "to highlight both the steps already completed and the future development directions. In addition, this staged "
        "structure demonstrates that the project was not conceived as a finished product from a single attempt, but as "
        "an applied research process based on documentation, analysis, testing, and progressive optimization."
    ),
    136: "VI. Experimental validation of the system through spectrometric comparison",
    137: (
        "For practical verification of the prototype, the spectrometric measurements taken outdoors were compared with "
        "the measurements taken inside the testing box. The comparison was made using pairs with the same leaf "
        "condition and the same spectral filter, using the entire measured spectrum and not only a few isolated points."
    ),
    138: (
        "The purpose of this stage is not for the raw values to be identical, because the illumination and measurement "
        "geometry are different. What matters is whether the shape of the spectral response and the trends between "
        "filters are preserved well enough for the camera-based optical system to be calibrated and used as an "
        "accessible multispectral analysis solution."
    ),
    139: (
        "The camera photographs are used at this stage for the series taken inside the box, while the outdoor "
        "measurements act as a spectrometric reference. Therefore, the comparison below mainly follows the change "
        "produced by the measurement environment, in order to establish which corrections must be applied before the "
        "camera results can be compared directly with outdoor measurements."
    ),
    140: (
        "The table summarizes the main results of the comparison. The Pearson r coefficient describes the similarity "
        "of the curve shapes after normalization, and the signal ratio shows the difference between the raw intensity "
        "recorded outdoors and the intensity obtained inside the box."
    ),
    142: "Figure 1. Comparison of the normalized spectral shapes",
    144: (
        "In this representation, the spectra measured outdoors and inside the box are normalized so that the comparison "
        "is not dominated by the difference in light intensity. It can be observed that the measurement environment "
        "changes the exact shape of the curve, especially in the visible region, but preserves the same general trend: "
        "decreases and increases in the response occur in nearby spectral regions. This supports the idea that the "
        "camera system can track real variations in spectral response, provided that proper calibration is used."
    ),
    145: "Figure 2. Similarity by filter and leaf condition",
    147: (
        "The graph shows how close the spectral shape measured inside the box is to the spectrum measured outdoors, for "
        "each filter and for the two leaf categories. The Pearson r coefficient is higher when the curve shapes match "
        "better. The most useful values for validating the prototype appear especially in the red-edge and NIR regions, "
        "where some filters preserve a moderate or good similarity. Lower values show that certain wavelengths are more "
        "sensitive to illumination and to the geometry of the setup."
    ),
    148: "Figure 3. Difference between raw intensity measured outdoors and inside the box",
    150: (
        "This graph compares the total area of the spectral signal, meaning the raw energy recorded over the entire "
        "spectrum. The signal obtained outdoors is hundreds of times stronger than the signal obtained inside the box, "
        "with a median ratio of approximately 137.8. For this reason, raw values cannot be compared directly as if "
        "they came from the same working environment. Scientific interpretation must use normalization, ratios between "
        "bands, and comparison of curve shapes."
    ),
    151: "Figure 4. Noise and roughness of the spectral curves",
    153: (
        "The figure compares curve stability using two indicators: the relative noise of the signal and roughness, "
        "meaning rapid variations from one spectral point to the next. Inside the box, the signal is weaker, and small "
        "variations become more visible after processing. However, this does not invalidate the method; instead, it "
        "shows that the system needs controlled exposure, calibration, and repeated measurements. For the multispectral "
        "camera, these results indicate where the internal illumination must be improved."
    ),
    154: "Figure 5. Similarity map for the spectral pairs",
    156: (
        "The similarity map shows each outdoor-inside-box measurement pair. Green colors indicate pairs with better "
        "similarity in spectral shape, while yellow-red colors show pairs where the measurement environment changed the "
        "response more strongly. The overall median of approximately r = 0.56 does not mean that the system is "
        "identical to the spectrometer under all conditions, but that there is a measurable and useful relationship "
        "between the two types of acquisition. This relationship can be used as a basis for calibrating the application."
    ),
    157: "Interpretation of the experimental results",
    158: (
        "The results show that the measurements inside the box and the outdoor measurements are not identical, but they "
        "preserve a measurable connection. The median similarity of approximately r = 0.56 indicates a moderate "
        "similarity of spectral shape, which is important for a low-cost prototype in the validation stage. The largest "
        "difference is the raw signal intensity, because natural outdoor light is much stronger than the illumination "
        "inside the box."
    ),
    159: (
        "Therefore, the system should not be evaluated only through raw brightness values, but through normalized "
        "comparisons, ratios between bands, and the relative behavior of the curves. This conclusion is consistent with "
        "the objective of the project: building an accessible multispectral camera that can approximate useful "
        "information about plant condition and can be improved through calibration, controlled illumination, and "
        "repeated measurements."
    ),
}


TABLE_CELL_TRANSLATIONS = {
    "Lungimea de una a fotografiei": "Image wavelength",
    "Fotografia": "Photo",
    "Indicator": "Indicator",
    "Valoare": "Value",
    "Interpretare": "Interpretation",
    "Perechi spectrale comparate": "Compared spectral pairs",
    "27": "27",
    "măsurători afară corelate cu măsurători în cutie": "outdoor measurements correlated with measurements inside the box",
    "Similaritate mediană totală": "Overall median similarity",
    "r = 0,56": "r = 0.56",
    "asemănare moderată a formei spectrale": "moderate similarity of spectral shape",
    "Similaritate frunze sănătoase": "Similarity for healthy leaves",
    "r = 0,57": "r = 0.57",
    "rezultat apropiat de media generală": "result close to the overall average",
    "Similaritate frunze nesănătoase": "Similarity for unhealthy leaves",
    "r = 0,53": "r = 0.53",
    "asemănare moderată, cu variații mai mari": "moderate similarity, with larger variations",
    "Raport median al semnalului": "Median signal ratio",
    "137,8x": "137.8x",
    "semnalul brut este mult mai puternic afară": "the raw signal is much stronger outdoors",
}


def has_drawing(run) -> bool:
    return bool(run._r.xpath('.//*[local-name()="drawing"]')) or bool(run._r.xpath('.//*[local-name()="pict"]'))


def replace_paragraph_text(paragraph, text: str) -> None:
    text_runs = [run for run in paragraph.runs if not has_drawing(run)]
    if not text_runs:
        paragraph.add_run(text)
        return
    text_runs[0].text = text
    for run in text_runs[1:]:
        run.text = ""


def replace_cell_text(cell, text: str) -> None:
    """Replace textual content in a cell while preserving any images in later paragraphs."""

    if not cell.paragraphs:
        cell.add_paragraph(text)
        return
    replace_paragraph_text(cell.paragraphs[0], text)
    for paragraph in cell.paragraphs[1:]:
        for run in paragraph.runs:
            if not has_drawing(run):
                run.text = ""


def translate_document() -> Path:
    document = Document(SOURCE)

    for index, text in PARAGRAPH_TRANSLATIONS.items():
        if index >= len(document.paragraphs):
            raise IndexError(f"Paragraph index {index} missing")
        replace_paragraph_text(document.paragraphs[index], text)

    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                text = cell.text.strip()
                if text in TABLE_CELL_TRANSLATIONS:
                    replace_cell_text(cell, TABLE_CELL_TRANSLATIONS[text])

    document.save(OUTPUT)
    return OUTPUT


if __name__ == "__main__":
    print(translate_document())
