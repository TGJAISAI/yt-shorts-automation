#!/usr/bin/env python
"""Quick test to verify configuration loads correctly."""

import sys

try:
    print("Testing configuration loading...")
    from app.core.config import get_config

    config = get_config()
    print(f"✓ Config loaded successfully")
    print(f"  - Model ID: {config.image_generation.model_id}")
    print(f"  - Device: {config.settings.sd_device}")
    print(f"  - FP16: {config.settings.sd_use_fp16}")
    print(f"  - HuggingFace token: {'Set' if config.settings.huggingface_token else 'Not set'}")
    print(f"  - Data dir: {config.settings.data_dir}")
    print(f"  - Models dir: {config.settings.models_dir}")

    print("\nTesting image generator initialization...")
    from app.services.image_generator import ImageGenerator

    img_gen = ImageGenerator(config)
    print(f"✓ ImageGenerator initialized")
    print(f"  - Device: {img_gen.device}")
    print(f"  - Model ID: {img_gen.image_config.model_id}")

    print("\n✅ All tests passed!")
    sys.exit(0)

except Exception as e:
    print(f"\n❌ Test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
