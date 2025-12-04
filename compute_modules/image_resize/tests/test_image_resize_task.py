"""Tests for image_resize module."""

import pytest
from pathlib import Path
from task import ImageResizeModule


@pytest.fixture
def module():
    """Create ImageResizeModule instance."""
    return ImageResizeModule()


@pytest.fixture
def sample_image(tmp_path):
    """Create a sample image for testing."""
    from PIL import Image
    
    img_path = tmp_path / "test_image.jpg"
    img = Image.new('RGB', (800, 600), color='red')
    img.save(img_path)
    return img_path


def test_module_supported_tasks(module):
    """Test that module supports image_resize task."""
    assert "image_resize" in module.supported_task_types


@pytest.mark.asyncio
async def test_resize_with_aspect_ratio(module, sample_image, tmp_path):
    """Test resizing with aspect ratio preserved."""
    metadata = {
        "width": 400,
        "height": 400,
        "preserve_aspect": True
    }
    
    result = await module.process(
        job_id="test-job-1",
        input_files=[sample_image],
        metadata=metadata
    )
    
    assert result["status"] == "ok"
    assert result["task_output"]["success"] is True
    assert len(result["output_files"]) == 1
    
    # Check dimensions - should preserve aspect ratio
    output_meta = result["output_files"][0]["metadata"]
    assert output_meta["resized_width"] == 400
    assert output_meta["resized_height"] == 300  # 800x600 -> 400x300


@pytest.mark.asyncio
async def test_resize_without_aspect_ratio(module, sample_image, tmp_path):
    """Test resizing without preserving aspect ratio."""
    metadata = {
        "width": 400,
        "height": 400,
        "preserve_aspect": False
    }
    
    result = await module.process(
        job_id="test-job-2",
        input_files=[sample_image],
        metadata=metadata
    )
    
    assert result["status"] == "ok"
    output_meta = result["output_files"][0]["metadata"]
    assert output_meta["resized_width"] == 400
    assert output_meta["resized_height"] == 400


@pytest.mark.asyncio
async def test_invalid_dimensions(module, sample_image):
    """Test error handling for invalid dimensions."""
    metadata = {
        "width": -100,
        "height": 200
    }
    
    result = await module.process(
        job_id="test-job-3",
        input_files=[sample_image],
        metadata=metadata
    )
    
    assert result["status"] == "error"
    assert "Invalid dimensions" in result["error"]


@pytest.mark.asyncio
async def test_missing_input_file(module):
    """Test error handling for missing input file."""
    result = await module.process(
        job_id="test-job-4",
        input_files=[],
        metadata={}
    )
    
    assert result["status"] == "error"
    assert "exactly 1 input file" in result["error"]
