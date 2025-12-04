"""Image Resize compute module - simple Pillow-based implementation."""

import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from PIL import Image

from .base import ComputeModule

logger = logging.getLogger(__name__)


class ImageResizeModule(ComputeModule):
    """Resize images to specified dimensions using Pillow."""

    @property
    def supported_task_types(self) -> List[str]:
        return ["image_resize"]

    async def process(
        self,
        job_id: str,
        input_files: List[Path],
        metadata: Dict[str, Any],
        progress_callback: Optional[Callable[[int], None]] = None,
    ) -> Dict[str, Any]:
        """
        Resize image(s) to specified dimensions.

        Metadata:
        {
            "width": int (default 256),
            "height": int (default 256),
            "preserve_aspect": bool (default True),
        }
        """
        try:
            # Validate input
            if len(input_files) != 1:
                return {
                    "status": "error",
                    "error": f"image_resize requires exactly 1 input file, got {len(input_files)}",
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
            original_size = image.size

            if progress_callback:
                progress_callback(30)

            # Get resize parameters
            width = metadata.get("width", 256)
            height = metadata.get("height", 256)
            preserve_aspect = metadata.get("preserve_aspect", True)

            # Validate dimensions
            if width <= 0 or height <= 0:
                return {
                    "status": "error",
                    "error": f"Invalid dimensions: width={width}, height={height}",
                    "output_files": [],
                    "task_output": {},
                }

            # Resize image
            if preserve_aspect:
                image.thumbnail((width, height), Image.Resampling.LANCZOS)
            else:
                image = image.resize((width, height), Image.Resampling.LANCZOS)

            if progress_callback:
                progress_callback(70)

            # Save output file
            output_dir = input_file.parent.parent / "output"
            output_dir.mkdir(parents=True, exist_ok=True)
            output_file = output_dir / "resized.jpg"

            image.save(output_file, quality=95)

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
                        "file_id": "resized_image",
                        "filename": "resized.jpg",
                        "metadata": {
                            "original_width": original_size[0],
                            "original_height": original_size[1],
                            "resized_width": image.width,
                            "resized_height": image.height,
                            "original_size_bytes": input_file.stat().st_size,
                            "output_size_bytes": output_size,
                            "preserve_aspect": preserve_aspect,
                        }
                    }
                ],
                "task_output": {
                    "success": True,
                    "original_dimensions": original_size,
                    "resized_dimensions": (image.width, image.height),
                },
            }

        except Exception as e:
            logger.exception(f"Error in image_resize: {e}")
            return {
                "status": "error",
                "error": str(e),
                "output_files": [],
                "task_output": {},
            }


__all__ = ["ImageResizeModule"]
