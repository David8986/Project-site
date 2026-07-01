# Leaf Photo / Spectrometer Analysis

## What can be analyzed now

The JPG photos can be analyzed directly. The `.ocv` files found here are OceanView ZIP/XML containers; in the checked files they contain acquisition/view settings, not exported wavelength-intensity tables. Therefore, this report analyzes the photos and prepares the association structure for the spectrometer measurements.

## Photo group summary

| Photo group | Count | Avg GCC | Avg ExG | Avg VARI | Avg saturation | Interpretation |
|---|---:|---:|---:|---:|---:|---|
| Poze normale frunza 1 | 7 | 0.333223 | -1.7e-05 | -6.8e-05 | 0.000127 | Mostly grayscale/low-saturation sequence; likely filter/IR-style captures of the first leaf. |
| Poze normale frunza 2 | 7 | 0.347846 | -0.015168 | 0.624965 | 0.216174 | Contains green, red/brown, and bright low-saturation captures; likely visible + near-IR sequence of the second leaf. |

## Proposed association

| Photo group | Leaf condition | Spectrometer folder | Confidence |
|---|---|---|---|
| Poze normale frunza 1 | green/healthy leaf | `Camera Roll\spectrometru frunza\verde frunza` | medium for folder, low for exact per-photo wavelength |
| Poze normale frunza 2 | yellow/unhealthy leaf | `Camera Roll\spectrometru frunza\fruza nesanatoasa-galben` | medium |

## Proposed per-photo filter order

This is a working association, not a substitute for lab notes. Group 2 visually supports the sequence better than group 1.

| Group | Photo | Proposed filter/light | Appearance | Confidence |
|---|---|---|---|---|
| Poze normale frunza 1 | WIN_20260515_15_03_51_Pro.jpg | 532 nm | dark grayscale/IR-like | low |
| Poze normale frunza 1 | WIN_20260515_15_04_05_Pro.jpg | 556 nm | dark grayscale/IR-like | low |
| Poze normale frunza 1 | WIN_20260515_15_04_17_Pro.jpg | full/no filter | bright grayscale/white | low |
| Poze normale frunza 1 | WIN_20260515_15_04_30_Pro.jpg | 680 nm | dark grayscale/IR-like | low |
| Poze normale frunza 1 | WIN_20260515_15_04_42_Pro.jpg | 725 nm | dark grayscale/IR-like | low |
| Poze normale frunza 1 | WIN_20260515_15_05_00_Pro.jpg | 850 nm | bright grayscale/white | low |
| Poze normale frunza 1 | WIN_20260515_15_05_08_Pro.jpg | 940 nm | dark grayscale/IR-like | low |
| Poze normale frunza 2 | WIN_20260515_15_16_17_Pro.jpg | 532 nm | red/brown | medium |
| Poze normale frunza 2 | WIN_20260515_15_16_24_Pro.jpg | 556 nm | green | medium |
| Poze normale frunza 2 | WIN_20260515_15_16_48_Pro.jpg | full/no filter | red/brown | medium |
| Poze normale frunza 2 | WIN_20260515_15_17_13_Pro.jpg | 680 nm | red/brown | medium |
| Poze normale frunza 2 | WIN_20260515_15_17_30_Pro.jpg | 725 nm | red/brown | medium |
| Poze normale frunza 2 | WIN_20260515_15_17_42_Pro.jpg | 850 nm | bright grayscale/white | medium |
| Poze normale frunza 2 | WIN_20260515_15_17_53_Pro.jpg | 940 nm | bright grayscale/white | medium |

## How to finish the spectrometer comparison

Export each OceanView measurement as CSV/TXT with wavelength and intensity columns. Then compare each photo group's averaged visible-camera metrics against the matching spectrometer intensities/reflectance at 532, 556, 680, 725, 850, and 940 nm.

Recommended comparison features:

- Camera: GCC, ExG, VARI, mean saturation, mean brightness.
- Spectrometer: intensity or reflectance at 532, 556, 680, 725, 850, 940 nm.
- Ratios: 850/680 and 725/680, because they summarize near-IR/red-edge response against red/chlorophyll-region response.