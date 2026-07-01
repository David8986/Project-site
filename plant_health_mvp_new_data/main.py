"""Command-line entry point for the plant-health multispectral MVP."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from .anomaly_detection import SpotDetectionConfig, detect_suspicious_spots, spot_result_to_report
from .adapters.registry import adapter_for_path
from .core.alignment_preview import export_alignment_preview_artifacts
from .band_extraction import apply_target_bands
from .band_profiles import get_profile
from .indices import build_indices_report, save_indices_csv, save_indices_report, summarize_main_indices
from .loader import load_sample, load_wavelength_csv, save_mock_dataset
from .models.sample import SpectralSample
from .outputs import (
    ensure_output_dir,
    save_average_bands_csv,
    save_band_images,
    save_mapping_csv,
    save_mask_image,
    save_report,
    save_spot_outputs,
    save_summary_csv,
    save_spectrum_plot,
)
from .spectrum import compute_average_spectrum
from .vegetation import apply_vegetation_mask
from .wavelength_mapping import inspect_wavelengths, map_target_wavelengths, summarize_mapping


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for the local MVP pipeline."""

    parser = argparse.ArgumentParser(
        description=(
            "Run the plant-health multispectral MVP: load data, map target "
            "bands, extract usable bands, build a vegetation mask, and save a report."
        )
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help=(
            "Optional extracted ENVI sample directory, RGB image, .npz, .npy, .csv, .txt, "
            "mixed-import .json spec, or .tar.gz sample. If omitted, a mock cube is used."
        ),
    )
    parser.add_argument(
        "--archive-sample",
        type=str,
        default=None,
        help="Optional substring selecting one sample folder/member inside a .tar.gz archive.",
    )
    parser.add_argument(
        "--wavelengths",
        type=Path,
        default=None,
        help="Optional wavelength CSV used when the sample does not contain wavelengths.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("plant_health_mvp_new_data") / "runs" / "latest",
        help="Directory where band images, mask, plot, and JSON report are written.",
    )
    parser.add_argument(
        "--save-mock-dataset",
        action="store_true",
        help="Also write a reusable mock_sample.npz and wavelengths.csv into plant_health_mvp_new_data/data/mock.",
    )
    parser.add_argument("--exact-tolerance", type=float, default=1.0, help="Exact-match tolerance in nm.")
    parser.add_argument("--nearest-tolerance", type=float, default=15.0, help="Nearest-band tolerance in nm.")
    parser.add_argument(
        "--interpolation-max-gap",
        type=float,
        default=80.0,
        help="Maximum bracket gap in nm for interpolated target bands.",
    )
    parser.add_argument(
        "--prefer-interpolation",
        action="store_true",
        help="Use interpolation before nearest matches after exact matches.",
    )
    parser.add_argument(
        "--band-profile",
        type=str,
        default="profile_7band_default",
        help="Target band profile name.",
    )
    parser.add_argument("--ndvi-threshold", type=float, default=0.2, help="NDVI threshold for 850/680 masks.")
    parser.add_argument(
        "--fallback-percentile",
        type=float,
        default=70.0,
        help="Percentile threshold for fallback vegetation masks.",
    )
    parser.add_argument(
        "--no-mask-cleanup",
        action="store_true",
        help="Disable simple morphology cleanup for the vegetation mask.",
    )
    parser.add_argument("--spot-threshold", type=float, default=0.55, help="Suspicious spot score threshold.")
    parser.add_argument("--spot-min-area", type=int, default=20, help="Minimum suspicious spot area in pixels.")
    parser.add_argument("--spot-texture-window", type=int, default=5, help="Texture window size for spot scoring.")
    return parser.parse_args(argv)


def _load_wavelengths_if_available(path: Path | None) -> np.ndarray:
    """Load a wavelength CSV when provided, returning an empty array otherwise."""

    if path is None:
        return np.asarray([], dtype=float)
    return load_wavelength_csv(path)


def _load_pipeline_sample(
    input_path: Path | None,
    wavelength_csv: Path | None,
    archive_sample: str | None = None,
) -> SpectralSample:
    """Load the source sample, using a mock sample when no usable input exists."""

    csv_wavelengths = _load_wavelengths_if_available(wavelength_csv)
    if input_path is None:
        adapter = adapter_for_path(None, wavelength_csv)
        adapter_sample = adapter.load_sample()
        sample = adapter_sample.to_spectral_sample(use_reflectance=True)
        sample.metadata.setdefault("loader_notes", []).append(
            "No input sample was supplied; generated mock image data through the mock adapter."
        )
    elif input_path.is_dir() or input_path.name.lower().endswith((".tar.gz", ".tgz", ".tar")):
        adapter = adapter_for_path(input_path, wavelength_csv)
        adapter_sample = adapter.load_sample(archive_sample)
        sample = adapter_sample.to_spectral_sample(use_reflectance=True)
    else:
        sample = load_sample(input_path, wavelength_csv, archive_sample=archive_sample)
    if wavelength_csv is not None:
        sample.metadata["wavelength_csv_path"] = str(wavelength_csv)
        sample.metadata["wavelength_csv_count"] = int(csv_wavelengths.size)
        if csv_wavelengths.size == 0:
            sample.metadata.setdefault("loader_notes", []).append(
                "Provided wavelength CSV was empty or contained no numeric values."
            )
    sample.metadata.setdefault(
        "source_data_kind",
        "mock_synthetic_data" if sample.metadata.get("mock_flag") else "real_sample_data",
    )
    return sample


def _print_json_block(title: str, payload: dict[str, Any]) -> None:
    """Print a compact, readable JSON block to stdout."""

    print(f"\n{title}")
    print(json.dumps(payload, indent=2, sort_keys=True))


def run_pipeline(args: argparse.Namespace) -> dict[str, Any]:
    """Run the full MVP pipeline and return saved artifact paths."""

    output_dir = ensure_output_dir(args.output)
    sample = _load_pipeline_sample(args.input, args.wavelengths, args.archive_sample)
    profile_name = (
        "profile_rgb_image"
        if sample.metadata.get("rgb_only") and args.band_profile == "profile_7band_default"
        else args.band_profile
    )
    band_profile = get_profile(profile_name)

    wavelength_inspection = inspect_wavelengths(sample.available_wavelengths)
    mappings = map_target_wavelengths(
        sample.available_wavelengths,
        target_wavelengths=band_profile.wavelengths_nm,
        exact_tolerance_nm=args.exact_tolerance,
        nearest_tolerance_nm=args.nearest_tolerance,
        interpolation_max_gap_nm=args.interpolation_max_gap,
        prefer_interpolation=args.prefer_interpolation,
    )
    mapping_summary = summarize_mapping(mappings)

    sample.metadata["wavelength_inspection"] = wavelength_inspection
    sample.metadata["mapping_summary"] = mapping_summary
    sample.metadata["target_wavelengths_nm"] = list(band_profile.wavelengths_nm)
    sample.metadata["band_profile"] = band_profile.name

    apply_target_bands(sample, mappings)
    is_real_sample = not bool(sample.metadata.get("mock_flag"))
    if is_real_sample:
        apply_vegetation_mask(
            sample,
            ndvi_threshold=args.ndvi_threshold,
            fallback_percentile=args.fallback_percentile,
            cleanup=not args.no_mask_cleanup,
        )
        average_spectrum, spectrum_metadata = compute_average_spectrum(sample)
        spot_result = detect_suspicious_spots(
            sample,
            config=SpotDetectionConfig(
                score_threshold=args.spot_threshold,
                min_area_px=args.spot_min_area,
                texture_window=args.spot_texture_window,
            ),
        )
        spot_report = spot_result_to_report(spot_result)
        sample.metadata["spot_detection"] = spot_report
    else:
        average_spectrum = {}
        spectrum_metadata = {
            "vegetation_pixel_count": 0,
            "mask_used": False,
            "mask_strategy": "skipped_for_synthetic_data",
            "note": (
                "Vegetation masking and average spectrum were skipped because no real "
                "hyperspectral sample was loaded."
            ),
        }
        sample.metadata["vegetation_mask"] = {
            "method": "skipped_for_synthetic_data",
            "reason": "A wavelength CSV alone does not contain image intensities.",
        }
        spot_result = None
        spot_report = {
            "spot_count": 0,
            "reason": "skipped for synthetic data",
            "spots": [],
        }

    band_images = save_band_images(sample, output_dir)
    mask_image = save_mask_image(sample.mask, output_dir)
    spot_output_paths = save_spot_outputs(spot_result, output_dir)
    alignment_preview_paths = export_alignment_preview_artifacts(sample, output_dir)
    spectrum_plot = save_spectrum_plot(average_spectrum, output_dir)
    indices_report = build_indices_report(sample, average_spectrum, spectrum_metadata)
    indices_report_path = save_indices_report(sample, output_dir, average_spectrum, spectrum_metadata)
    indices_csv_path = save_indices_csv(sample, output_dir, average_spectrum, spectrum_metadata)
    report_path = save_report(
        sample,
        output_dir,
        average_spectrum,
        spectrum_metadata,
        indices_report=indices_report,
        spot_report=spot_report,
        extra_metadata={
            "cli": {
                "input": None if args.input is None else str(args.input),
                "wavelengths": None if args.wavelengths is None else str(args.wavelengths),
                "archive_sample": args.archive_sample,
                "output": str(output_dir),
                "prefer_interpolation": bool(args.prefer_interpolation),
            }
        },
    )
    summary_csv_path = save_summary_csv(sample, output_dir, spectrum_metadata)
    average_bands_csv_path = save_average_bands_csv(output_dir, average_spectrum)
    mapping_csv_path = save_mapping_csv(sample, output_dir, average_spectrum)
    camera_calibration_csv_path = output_dir / "camera_calibration.csv"

    mock_dataset_paths: tuple[Path, Path] | None = None
    if args.save_mock_dataset:
        mock_dataset_paths = save_mock_dataset(Path("plant_health_mvp_new_data") / "data" / "mock")

    artifacts: dict[str, Any] = {
        "output_dir": str(output_dir),
        "band_images": band_images,
        "mask_image": mask_image,
        "spot_outputs": spot_output_paths,
        "alignment_preview": alignment_preview_paths,
        "spectrum_plot": spectrum_plot,
        "report_path": str(report_path),
        "summary_csv_path": str(summary_csv_path),
        "average_bands_csv_path": str(average_bands_csv_path),
        "mapping_csv_path": str(mapping_csv_path),
        "camera_calibration_csv_path": (
            str(camera_calibration_csv_path) if camera_calibration_csv_path.exists() else None
        ),
        "indices_report_path": str(indices_report_path),
        "indices_csv_path": str(indices_csv_path),
        "mock_dataset": None
        if mock_dataset_paths is None
        else {
            "sample": str(mock_dataset_paths[0]),
            "wavelengths": str(mock_dataset_paths[1]),
        },
    }

    _print_json_block("Wavelength Inspection", wavelength_inspection)
    _print_json_block("Target Band Mapping", mapping_summary)
    if is_real_sample:
        _print_json_block("Average Spectrum Over Vegetation", average_spectrum)
        _print_json_block("Spectral Indices Summary", summarize_main_indices(indices_report))
        _print_json_block("Suspicious Spot Summary", {"spot_count": spot_report.get("spot_count", 0)})
    else:
        _print_json_block("Synthetic Run Notice", {"vegetation_and_spectrum": "skipped"})
    _print_json_block("Saved Outputs", artifacts)
    return artifacts


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line application."""

    args = _parse_args(argv)
    run_pipeline(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
