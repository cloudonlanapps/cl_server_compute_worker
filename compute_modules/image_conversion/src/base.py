"""Base interface for all compute modules."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Callable, Optional, Dict, Any


class ComputeModule(ABC):
    """Base class for all compute modules."""

    @property
    @abstractmethod
    def supported_task_types(self) -> List[str]:
        """
        Return list of task types this module supports.

        Returns:
            List of task type strings (e.g., ["image_resize", "image_conversion"])
        """
        pass

    @abstractmethod
    async def process(
        self,
        job_id: str,
        input_files: List[Path],
        metadata: Dict[str, Any],
        progress_callback: Optional[Callable[[int], None]] = None,
    ) -> Dict[str, Any]:
        """
        Process a compute job.

        Args:
            job_id: Unique job identifier
            input_files: List of paths to input files
            metadata: Task-specific metadata/configuration from caller
            progress_callback: Optional callback to report progress (0-100)

        Returns:
            Dictionary with:
            {
                "status": "ok" or "error",
                "output_files": [{file_id: str, metadata: dict}, ...],
                "task_output": {...},  # Task-specific results
                "error": Optional error message
            }
        """
        pass


__all__ = ["ComputeModule"]
