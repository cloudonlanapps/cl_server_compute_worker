# Image Conversion Compute Module

A standalone compute module for converting images between different formats using Pillow.

## Features

- Convert between image formats (JPEG, PNG, BMP, GIF, TIFF)
- Automatic RGBA to RGB conversion for JPEG
- Quality control for JPEG output
- Compression control for PNG output
- Isolated virtual environment

## Dependencies

- `pillow>=10.0.0` - Image processing
- `sqlalchemy>=2.0.0` - Database access
- `paho-mqtt>=1.6.0` - Event broadcasting

## Installation

The module is automatically set up by the worker when first discovered:

```bash
# Worker creates venv and installs dependencies
python -m venv .venv
.venv/bin/pip install -e .
```

## Task Type

**`image_conversion`**

## Input Metadata

```json
{
  "output_format": "PNG",  // Target format: JPEG, PNG, BMP, GIF, TIFF (default: PNG)
  "quality": 95            // JPEG quality 1-100 (default: 95, JPEG only)
}
```

## Output

```json
{
  "status": "ok",
  "output_files": [{
    "file_id": "converted_image",
    "filename": "converted.png",
    "metadata": {
      "original_format": "JPEG",
      "output_format": "PNG",
      "quality": null,
      "original_size_bytes": 524288,
      "output_size_bytes": 345678,
      "dimensions": [1920, 1080]
    }
  }],
  "task_output": {
    "success": true,
    "original_format": "JPEG",
    "output_format": "PNG",
    "quality": null
  }
}
```

## Supported Formats

- **JPEG/JPG** - Lossy compression, quality control
- **PNG** - Lossless compression
- **BMP** - Uncompressed bitmap
- **GIF** - Lossless, supports animation
- **TIFF** - Lossless, high quality

## Module Structure

```
image_conversion/
├── task.py         # ImageConversionModule implementation
├── base.py         # ComputeModule base class
├── runner.py       # Subprocess runner
├── shared.py       # Shared utilities (models, config, broadcaster)
├── pyproject.toml  # Dependencies
└── README.md       # This file
```

## Testing

```bash
# Run module tests
pytest tests/
```

## Usage

This module is automatically discovered and executed by the worker. You don't run it directly.

To create a job that uses this module:

```bash
curl -X POST http://localhost:8001/job/image_conversion \
  -F "upload_files=@image.jpg" \
  -F "external_files=[{\"metadata\": {\"output_format\": \"PNG\"}}]" \
  -F "priority=5"
```
