"""
Image Processor Compute Module.
Handles both image conversion and image resizing.
"""

import logging
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable
from PIL import Image

# Support both package imports and direct script imports
try:
    from cl_server_shared import ComputeModule, run_compute_job, ComputeJobParams, ImageResizeParams, ImageConversionParams
except ImportError:
    # Fallback for when imported as a module directly (not as a package)
    # This might fail if cl_server_shared is not in path, but that's expected
    raise

logger = logging.getLogger(__name__)


class ImageProcessorModule(ComputeModule):
    """Compute module for image processing tasks."""

    @property
    def supported_task_types(self) -> List[str]:
        return ["image_resize", "image_conversion"]

    async def process(
        self,
        job_id: str,
        task_type: str,
        params: ComputeJobParams,
        progress_callback: Optional[Callable[[int], None]] = None,
    ) -> Dict[str, Any]:
        """Process image job based on task type."""
        logger.info(f"Processing job {job_id} (type: {task_type})")
        
        if task_type == "image_resize":
            if not isinstance(params, ImageResizeParams):
                return {"status": "error", "error": "Invalid params for image_resize"}
            return await self._process_resize(job_id, params, progress_callback)
        elif task_type == "image_conversion":
            if not isinstance(params, ImageConversionParams):
                return {"status": "error", "error": "Invalid params for image_conversion"}
            return await self._process_conversion(job_id, params, progress_callback)
        else:
            return {"status": "error", "error": f"Unsupported task type: {task_type}"}

    async def _process_resize(
        self,
        job_id: str,
        params: ImageResizeParams,
        progress_callback: Optional[Callable[[int], None]] = None,
    ) -> Dict[str, Any]:
        """Resize images."""
        try:
            total_files = len(params.input_paths)

            for i, (input_path_str, output_path_str) in enumerate(zip(params.input_paths, params.output_paths)):
                input_path = Path(input_path_str)
                output_path = Path(output_path_str)
                
                try:
                    # Ensure output directory exists
                    output_path.parent.mkdir(parents=True, exist_ok=True)

                    with Image.open(input_path) as img:
                        # Resize
                        resized_img = img.resize((params.width, params.height))
                        
                        # Save
                        resized_img.save(output_path)
                        
                except Exception as e:
                    logger.error(f"Failed to resize {input_path}: {e}")
                
                if progress_callback:
                    progress_callback(int((i + 1) / total_files * 100))
                
                # Simulate some work
                await asyncio.sleep(0.1)

            return {
                "status": "ok",
                "task_output": {"processed_count": total_files}
            }

        except Exception as e:
            logger.exception(f"Resize failed: {e}")
            return {"status": "error", "error": str(e)}

    async def _process_conversion(
        self,
        job_id: str,
        params: ImageConversionParams,
        progress_callback: Optional[Callable[[int], None]] = None,
    ) -> Dict[str, Any]:
        """Convert images to target format."""
        try:
            target_format = params.format.upper()
            total_files = len(params.input_paths)

            for i, (input_path_str, output_path_str) in enumerate(zip(params.input_paths, params.output_paths)):
                input_path = Path(input_path_str)
                output_path = Path(output_path_str)

                try:
                    # Ensure output directory exists
                    output_path.parent.mkdir(parents=True, exist_ok=True)

                    with Image.open(input_path) as img:
                        # Convert to RGB if saving as JPEG
                        if target_format == "JPEG" and img.mode in ("RGBA", "P"):
                            img = img.convert("RGB")
                        
                        # Save
                        img.save(output_path, format=target_format, quality=params.quality)
                        
                except Exception as e:
                    logger.error(f"Failed to convert {input_path}: {e}")
                
                if progress_callback:
                    progress_callback(int((i + 1) / total_files * 100))
                
                # Simulate some work
                await asyncio.sleep(0.1)

            return {
                "status": "ok",
                "task_output": {"processed_count": total_files}
            }

        except Exception as e:
            logger.exception(f"Conversion failed: {e}")
            return {"status": "error", "error": str(e)}


def main():
    module = ImageProcessorModule()
    run_compute_job(module)


if __name__ == "__main__":
    main()
