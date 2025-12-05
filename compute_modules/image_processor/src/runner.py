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
    from cl_server_shared import ComputeModule, run_compute_job
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
        input_files: List[Path],
        metadata: Dict[str, Any],
        progress_callback: Optional[Callable[[int], None]] = None,
    ) -> Dict[str, Any]:
        """Process image job based on task type."""
        logger.info(f"Processing job {job_id} (type: {task_type})")
        
        if task_type == "image_resize":
            return await self._process_resize(job_id, input_files, metadata, progress_callback)
        elif task_type == "image_conversion":
            return await self._process_conversion(job_id, input_files, metadata, progress_callback)
        else:
            return {"status": "error", "error": f"Unsupported task type: {task_type}"}

    async def _process_resize(
        self,
        job_id: str,
        input_files: List[Path],
        metadata: Dict[str, Any],
        progress_callback: Optional[Callable[[int], None]] = None,
    ) -> Dict[str, Any]:
        """Resize images."""
        try:
            width = metadata.get("width")
            height = metadata.get("height")
            
            if not width or not height:
                return {"status": "error", "error": "Missing width or height in metadata"}

            output_files = []
            total_files = len(input_files)

            for i, input_path in enumerate(input_files):
                try:
                    with Image.open(input_path) as img:
                        # Resize
                        resized_img = img.resize((width, height))
                        
                        # Save
                        output_filename = f"resized_{input_path.name}"
                        output_path = input_path.parent / output_filename
                        resized_img.save(output_path)
                        
                        output_files.append({
                            "file_id": output_filename,
                            "metadata": {
                                "original_path": str(input_path),
                                "width": width,
                                "height": height
                            }
                        })
                except Exception as e:
                    logger.error(f"Failed to resize {input_path}: {e}")
                    # Continue with other files or fail? For now, let's continue but log error
                
                if progress_callback:
                    progress_callback(int((i + 1) / total_files * 100))
                
                # Simulate some work
                await asyncio.sleep(0.1)

            return {
                "status": "ok",
                "output_files": output_files,
                "task_output": {"processed_count": len(output_files)}
            }

        except Exception as e:
            logger.exception(f"Resize failed: {e}")
            return {"status": "error", "error": str(e)}

    async def _process_conversion(
        self,
        job_id: str,
        input_files: List[Path],
        metadata: Dict[str, Any],
        progress_callback: Optional[Callable[[int], None]] = None,
    ) -> Dict[str, Any]:
        """Convert images to target format."""
        try:
            target_format = metadata.get("format", "JPEG").upper()
            
            output_files = []
            total_files = len(input_files)

            for i, input_path in enumerate(input_files):
                try:
                    with Image.open(input_path) as img:
                        # Convert to RGB if saving as JPEG
                        if target_format == "JPEG" and img.mode in ("RGBA", "P"):
                            img = img.convert("RGB")
                        
                        # Save
                        output_filename = f"converted_{input_path.stem}.{target_format.lower()}"
                        output_path = input_path.parent / output_filename
                        img.save(output_path, format=target_format)
                        
                        output_files.append({
                            "file_id": output_filename,
                            "metadata": {
                                "original_path": str(input_path),
                                "format": target_format
                            }
                        })
                except Exception as e:
                    logger.error(f"Failed to convert {input_path}: {e}")
                
                if progress_callback:
                    progress_callback(int((i + 1) / total_files * 100))
                
                # Simulate some work
                await asyncio.sleep(0.1)

            return {
                "status": "ok",
                "output_files": output_files,
                "task_output": {"processed_count": len(output_files)}
            }

        except Exception as e:
            logger.exception(f"Conversion failed: {e}")
            return {"status": "error", "error": str(e)}


def main():
    module = ImageProcessorModule()
    run_compute_job(module)


if __name__ == "__main__":
    main()
