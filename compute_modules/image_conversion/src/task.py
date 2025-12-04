"""Image Conversion compute module - simple Pillow-based implementation."""

import logging
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from PIL import Image

# Support both package imports and direct script imports
try:
    from .base import ComputeModule
except ImportError:
    # Fallback for when imported as a module directly (not as a package)
    from base import ComputeModule

logger = logging.getLogger(__name__)


class ImageConversionModule(ComputeModule):
    """Convert image formats using Pillow."""

    @property
    def supported_task_types(self) -> List[str]:
        return ["image_conversion"]

    async def process(
        self,
        job_id: str,
        input_files: List[Path],
        metadata: Dict[str, Any],
        progress_callback: Optional[Callable[[int], None]] = None,
    ) -> Dict[str, Any]:
        """
        Convert image format.

        Metadata:
        {
            "output_format": str (e.g., "PNG", "JPEG", default "PNG"),
            "quality": int (1-100, default 95, only for JPEG),
        }
        """
        try:
            # Validate input
            if len(input_files) != 1:
                return {
                    "status": "error",
                    "error": f"image_conversion requires exactly 1 input file, got {len(input_files)}",
                    "output_files": [],
                    "task_output": {},
                }

            if progress_callback:
                progress_callback(10)

            # Get input file
            input_file = input_files[0]
            if not input_file.exists():
                return {
                    "status": "error",
                    "error": f"Input file not found: {input_file}",
                    "output_files": [],
                    "task_output": {},
                }

            # Load image
            image = Image.open(input_file)
            original_format = image.format
            original_size = image.size

            if progress_callback:
                progress_callback(30)

            # Get conversion parameters
            output_format = metadata.get("output_format", "PNG").upper()
            quality = metadata.get("quality", 95)

            # Validate format
            valid_formats = ["JPEG", "JPG", "PNG", "BMP", "GIF", "TIFF"]
            if output_format not in valid_formats:
                return {
                    "status": "error",
                    "error": f"Unsupported output format: {output_format}. Supported: {', '.join(valid_formats)}",
                    "output_files": [],
                    "task_output": {},
                }

            # Normalize format
            if output_format == "JPG":
                output_format = "JPEG"

            if progress_callback:
                progress_callback(50)

            # Convert RGBA to RGB if saving as JPEG
            if output_format == "JPEG" and image.mode in ("RGBA", "LA", "P"):
                rgb_image = Image.new("RGB", image.size, (255, 255, 255))
                if image.mode == "RGBA":
                    rgb_image.paste(image, mask=image.split()[-1])
                elif image.mode == "LA":
                    rgb_image.paste(image, mask=image.split()[-1])
                else:  # P mode
                    rgb_image.paste(image)
                image = rgb_image

            if progress_callback:
                progress_callback(70)

            # Save output file
            output_dir = input_file.parent.parent / "output"
            output_dir.mkdir(parents=True, exist_ok=True)

            # Determine file extension
            ext = output_format.lower()
            if ext == "jpeg":
                ext = "jpg"

            output_file = output_dir / f"converted.{ext}"

            # Save with appropriate options
            save_kwargs = {}
            if output_format == "JPEG":
                save_kwargs["quality"] = quality
            elif output_format == "PNG":
                save_kwargs["compress_level"] = 9

            image.save(output_file, format=output_format, **save_kwargs)

            if progress_callback:
                progress_callback(90)

            # Get output file size
            output_size = output_file.stat().st_size

            if progress_callback:
                progress_callback(100)

            return {
                "status": "ok",
                "output_files": [
                    {
                        "file_id": "converted_image",
                        "filename": f"converted.{ext}",
                        "metadata": {
                            "original_format": original_format,
                            "output_format": output_format,
                            "quality": quality if output_format == "JPEG" else None,
                            "original_size_bytes": input_file.stat().st_size,
                            "output_size_bytes": output_size,
                            "dimensions": original_size,
                        }
                    }
                ],
                "task_output": {
                    "success": True,
                    "original_format": original_format,
                    "output_format": output_format,
                    "quality": quality if output_format == "JPEG" else None,
                },
            }

        except Exception as e:
            logger.exception(f"Error in image_conversion: {e}")
            return {
                "status": "error",
                "error": str(e),
                "output_files": [],
                "task_output": {},
            }


__all__ = ["ImageConversionModule"]
