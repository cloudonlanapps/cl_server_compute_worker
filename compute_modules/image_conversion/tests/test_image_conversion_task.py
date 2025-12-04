"""Tests for image_conversion module."""

import pytest
from pathlib import Path
from task import ImageConversionModule


@pytest.fixture
def module():
    """Create ImageConversionModule instance."""
    return ImageConversionModule()


@pytest.fixture
def sample_jpeg(tmp_path):
    """Create a sample JPEG image for testing."""
    from PIL import Image
    
    img_path = tmp_path / "test_image.jpg"
    img = Image.new('RGB', (800, 600), color='blue')
    img.save(img_path, 'JPEG')
    return img_path


@pytest.fixture
def sample_png_with_alpha(tmp_path):
    """Create a sample PNG image with alpha channel."""
    from PIL import Image
    
    img_path = tmp_path / "test_image.png"
    img = Image.new('RGBA', (800, 600), color=(255, 0, 0, 128))
    img.save(img_path, 'PNG')
    return img_path


def test_module_supported_tasks(module):
    """Test that module supports image_conversion task."""
    assert "image_conversion" in module.supported_task_types


@pytest.mark.asyncio
async def test_jpeg_to_png(module, sample_jpeg, tmp_path):
    """Test converting JPEG to PNG."""
    metadata = {
        "output_format": "PNG"
    }
    
    result = await module.process(
        job_id="test-job-1",
        input_files=[sample_jpeg],
        metadata=metadata
    )
    
    assert result["status"] == "ok"
    assert result["task_output"]["success"] is True
    assert result["task_output"]["output_format"] == "PNG"
    assert len(result["output_files"]) == 1
    assert result["output_files"][0]["filename"] == "converted.png"


@pytest.mark.asyncio
async def test_png_to_jpeg_with_alpha(module, sample_png_with_alpha, tmp_path):
    """Test converting PNG with alpha to JPEG (should convert RGBA to RGB)."""
    metadata = {
        "output_format": "JPEG",
        "quality": 90
    }
    
    result = await module.process(
        job_id="test-job-2",
        input_files=[sample_png_with_alpha],
        metadata=metadata
    )
    
    assert result["status"] == "ok"
    assert result["task_output"]["output_format"] == "JPEG"
    assert result["task_output"]["quality"] == 90
    assert result["output_files"][0]["filename"] == "converted.jpg"


@pytest.mark.asyncio
async def test_invalid_format(module, sample_jpeg):
    """Test error handling for unsupported format."""
    metadata = {
        "output_format": "INVALID"
    }
    
    result = await module.process(
        job_id="test-job-3",
        input_files=[sample_jpeg],
        metadata=metadata
    )
    
    assert result["status"] == "error"
    assert "Unsupported output format" in result["error"]


@pytest.mark.asyncio
async def test_default_format(module, sample_jpeg):
    """Test default output format (PNG)."""
    result = await module.process(
        job_id="test-job-4",
        input_files=[sample_jpeg],
        metadata={}
    )
    
    assert result["status"] == "ok"
    assert result["task_output"]["output_format"] == "PNG"


@pytest.mark.asyncio
async def test_missing_input_file(module):
    """Test error handling for missing input file."""
    result = await module.process(
        job_id="test-job-5",
        input_files=[],
        metadata={}
    )
    
    assert result["status"] == "error"
    assert "exactly 1 input file" in result["error"]
