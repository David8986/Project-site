"""Batch command-line runner for folder-based plant-health processing."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable, Sequence

from .main import run_pipeline
from .outputs import ensure_output_dir


DEFAULT_EXTENSIONS = (
    ".tar.gz",
    ".tgz",
    ".tar",
    ".npz",
    ".npy",
    ".json",
    ".jpg",
    ".jpeg",
    ".png",
    ".tif",
    ".tiff",
    ".bmp",
)
TABLE_EXTENSIONS = (".csv", ".txt")


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for batch folder processing."""

    parser = argparse.ArgumentParser(
        description="Run the plant-health pipeline on every supported sample in a folder."
    )
    parser.add_argument(
        "--input-folder",
        type=Path,
        required=True,
        help="Folder containing supported samples such as .tar.gz, .npz, or .npy files.",
    )
    parser.add_argument(
        "--wavelengths",
        type=Path,
        default=None,
        help="Optional wavelength CSV shared by all samples.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output folder. Each sample gets its own subfolder here.",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Search input-folder recursively.",
    )
    parser.add_argument(
        "--include-tables",
        action="store_true",
        help="Also process .csv and .txt spectral tables as samples.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional maximum number of samples to process.",
    )
    parser.add_argument(
        "--archive-sample",
        type=str,
        default=None,
        help="Optional substring selecting one sample folder/member inside every .tar.gz archive.",
    )
    parser.add_argument("--exact-tolerance", type=float, default=1.0)
    parser.add_argument("--nearest-tolerance", type=float, default=15.0)
    parser.add_argument("--interpolation-max-gap", type=float, default=80.0)
    parser.add_argument("--prefer-interpolation", action="store_true")
    parser.add_argument("--band-profile", type=str, default="profile_7band_default")
    parser.add_argument("--ndvi-threshold", type=float, default=0.2)
    parser.add_argument("--fallback-percentile", type=float, default=70.0)
    parser.add_argument("--no-mask-cleanup", action="store_true")
    parser.add_argument("--spot-threshold", type=float, default=0.55)
    parser.add_argument("--spot-min-area", type=int, default=20)
    parser.add_argument("--spot-texture-window", type=int, default=5)
    return parser.parse_args(argv)


def _is_supported_sample(path: Path, include_tables: bool) -> bool:
    """Return True when a path is a supported batch input sample."""

    if path.is_dir() and (path / "capture").is_dir():
        return True

    lower_name = path.name.lower()
    if lower_name.endswith(DEFAULT_EXTENSIONS):
        return True
    return include_tables and lower_name.endswith(TABLE_EXTENSIONS)


def _iter_samples(input_folder: Path, recursive: bool, include_tables: bool) -> Iterable[Path]:
    """Yield supported sample files or extracted sample directories."""

    pattern = "**/*" if recursive else "*"
    for path in sorted(input_folder.glob(pattern)):
        if _is_supported_sample(path, include_tables):
            yield path


def _sanitize_name(value: str) -> str:
    """Return a readable filesystem-safe name."""

    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")
    return safe or "sample"


def _short_path_hash(path: Path) -> str:
    """Return a short stable hash so duplicate sample names stay distinguishable."""

    return hashlib.sha1(str(path).lower().encode("utf-8")).hexdigest()[:8]


def _sample_base_name(path: Path) -> str:
    """Create a stable readable name for a sample path."""

    name = path.name
    if path.is_file():
        for suffix in (".tar.gz", ".tgz", ".tar", ".npz", ".npy", ".json", ".csv", ".txt"):
            if name.lower().endswith(suffix):
                name = name[: -len(suffix)]
                break
    return _sanitize_name(name)


def _sample_output_name(path: Path, index: int) -> str:
    """Create an output folder name that is easy to match back to the input."""

    return f"{index:03d}__{_sample_base_name(path)}__{_short_path_hash(path)}"


def _pipeline_args(
    *,
    sample_path: Path,
    output_dir: Path,
    batch_args: argparse.Namespace,
) -> argparse.Namespace:
    """Create the argument object expected by the single-sample pipeline."""

    return argparse.Namespace(
        input=sample_path,
        archive_sample=batch_args.archive_sample,
        wavelengths=batch_args.wavelengths,
        output=output_dir,
        save_mock_dataset=False,
        exact_tolerance=batch_args.exact_tolerance,
        nearest_tolerance=batch_args.nearest_tolerance,
        interpolation_max_gap=batch_args.interpolation_max_gap,
        prefer_interpolation=batch_args.prefer_interpolation,
        band_profile=batch_args.band_profile,
        ndvi_threshold=batch_args.ndvi_threshold,
        fallback_percentile=batch_args.fallback_percentile,
        no_mask_cleanup=batch_args.no_mask_cleanup,
        spot_threshold=batch_args.spot_threshold,
        spot_min_area=batch_args.spot_min_area,
        spot_texture_window=batch_args.spot_texture_window,
    )


def run_batch(args: argparse.Namespace) -> dict[str, Any]:
    """Run the single-sample pipeline for each supported file in a folder."""

    input_folder = args.input_folder
    if not input_folder.exists() or not input_folder.is_dir():
        raise NotADirectoryError(f"Input folder not found: {input_folder}")

    output_root = ensure_output_dir(args.output)
    samples = list(_iter_samples(input_folder, args.recursive, args.include_tables))
    if args.limit is not None:
        samples = samples[: max(0, int(args.limit))]

    results: list[dict[str, Any]] = []
    for index, sample_path in enumerate(samples, start=1):
        sample_output = output_root / _sample_output_name(sample_path, index)
        print(f"\nProcessing sample: {sample_path}")
        try:
            artifacts = run_pipeline(
                _pipeline_args(sample_path=sample_path, output_dir=sample_output, batch_args=args)
            )
            results.append(
                {
                    "input": str(sample_path),
                    "sample_name": _sample_base_name(sample_path),
                    "output_dir": str(sample_output),
                    "status": "ok",
                    "artifacts": artifacts,
                }
            )
        except Exception as exc:  # noqa: BLE001 - batch summary should capture per-file failure.
            results.append(
                {
                    "input": str(sample_path),
                    "sample_name": _sample_base_name(sample_path),
                    "output_dir": str(sample_output),
                    "status": "error",
                    "error": str(exc),
                }
            )
            print(f"Failed sample: {sample_path}\nReason: {exc}")

    summary = {
        "input_folder": str(input_folder),
        "output_folder": str(output_root),
        "sample_count": len(samples),
        "succeeded": sum(1 for result in results if result["status"] == "ok"),
        "failed": sum(1 for result in results if result["status"] == "error"),
        "results": results,
    }
    summary_path = output_root / "batch_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    summary_csv_path = output_root / "batch_summary.csv"
    with summary_csv_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(
            [
                "status",
                "sample_name",
                "input_path",
                "output_folder",
                "mapping_report_csv",
                "indices_report_csv",
                "error",
            ]
        )
        for result in results:
            artifacts = result.get("artifacts", {})
            writer.writerow(
                [
                    result.get("status", ""),
                    result.get("sample_name", ""),
                    result.get("input", ""),
                    result.get("output_dir", ""),
                    artifacts.get("mapping_csv_path", ""),
                    artifacts.get("indices_csv_path", ""),
                    result.get("error", ""),
                ]
            )
    print(f"\nBatch summary saved: {summary_path}")
    print(f"Batch CSV summary saved: {summary_csv_path}")
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    """Run the batch command-line application."""

    args = _parse_args(argv)
    run_batch(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
