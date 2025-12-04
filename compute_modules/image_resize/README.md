# Image Resize Compute Module

A standalone compute module for resizing images using Pillow.

## Features

- Resize images to specified dimensions
- Preserve aspect ratio option
- Support for various image formats (JPEG, PNG, BMP, etc.)
- Progress reporting via callback
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

**`image_resize`**

## Input Metadata

```json
{
  "width": 256,           // Target width (default: 256)
  "height": 256,          // Target height (default: 256)
  "preserve_aspect": true // Preserve aspect ratio (default: true)
}
```

## Output

```json
{
  "status": "ok",
  "output_files": [{
    "file_id": "resized_image",
    "filename": "resized.jpg",
    "metadata": {
      "original_width": 1920,
      "original_height": 1080,
      "resized_width": 256,
      "resized_height": 144,
      "original_size_bytes": 524288,
      "output_size_bytes": 12345,
      "preserve_aspect": true
    }
  }],
  "task_output": {
    "success": true,
    "original_dimensions": [1920, 1080],
    "resized_dimensions": [256, 144]
  }
}
```

## Module Structure

```
image_resize/
├── task.py         # ImageResizeModule implementation
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
curl -X POST http://localhost:8001/job/image_resize \
  -F "upload_files=@image.jpg" \
  -F "priority=5"
```
