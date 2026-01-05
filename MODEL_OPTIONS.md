# Stable Diffusion Model Options

## Recommended: Stable Diffusion 1.5

**Model ID:** `runwayml/stable-diffusion-v1-5`

✅ **Advantages:**
- No authentication required (public model)
- Widely tested and stable
- Faster than SD 2.x (smaller model)
- Lower memory requirements
- Better compatibility

**Performance:**
- Model size: ~4GB
- Generation time (M1 Mac): 20-30 seconds per image
- Generation time (NVIDIA RTX 3080): 3-5 seconds per image
- Memory usage: ~4GB VRAM (with fp16)

**This is now the default model in config.yaml**

## Alternative: Stable Diffusion 2.1

**Model ID:** `stabilityai/stable-diffusion-2-1`

⚠️ **May require HuggingFace token**

✅ **Advantages:**
- Slightly better image quality
- Better at following complex prompts
- Higher resolution support

❌ **Disadvantages:**
- Larger model (~5GB)
- Slower generation
- May require HuggingFace authentication
- Higher memory requirements

**Performance:**
- Model size: ~5GB
- Generation time (M1 Mac): 30-40 seconds per image
- Generation time (NVIDIA RTX 3080): 5-8 seconds per image
- Memory usage: ~6GB VRAM (with fp16)

**To use SD 2.1:**

1. Get a HuggingFace token:
   - Go to https://huggingface.co/settings/tokens
   - Create a new token (read access is enough)

2. Update your `.env`:
   ```env
   SD_MODEL_ID=stabilityai/stable-diffusion-2-1
   HUGGINGFACE_TOKEN=hf_...your_token_here
   ```

3. Restart the server

## Other Options

### Stable Diffusion 1.4
**Model ID:** `CompVis/stable-diffusion-v1-4`

- Older version, less capable than 1.5
- Not recommended unless you have specific compatibility needs

### Stable Diffusion XL (SDXL)
**Model ID:** `stabilityai/stable-diffusion-xl-base-1.0`

❌ **Not recommended for this use case**
- Much larger model (~12GB)
- Much slower (2-3x)
- Requires more VRAM
- Overkill for YouTube Shorts (1080x1920)

### DreamShaper (Community Fine-tune)
**Model ID:** `Lykon/DreamShaper`

- Community fine-tuned version
- Good for artistic/stylized images
- May require different prompting style

## Model Selection Guide

### For Speed (Recommended):
```yaml
image_generation:
  model_id: "runwayml/stable-diffusion-v1-5"
  num_inference_steps: 20  # Faster
```

### For Quality:
```yaml
image_generation:
  model_id: "stabilityai/stable-diffusion-2-1"  # Requires HF token
  num_inference_steps: 30
```

### For Low Memory (CPU or low VRAM):
```yaml
image_generation:
  model_id: "runwayml/stable-diffusion-v1-5"
  num_inference_steps: 15  # Even faster
```

Then in `.env`:
```env
SD_USE_FP16=true  # Save memory
SD_DEVICE=cpu     # If GPU runs out of memory
```

## Troubleshooting Model Downloads

### Error: "Cannot load model... not cached locally"

**Solution 1 - Use SD 1.5 (Recommended):**
```env
SD_MODEL_ID=runwayml/stable-diffusion-v1-5
```

**Solution 2 - Add HuggingFace token:**
```env
HUGGINGFACE_TOKEN=hf_your_token_here
```

**Solution 3 - Pre-download the model:**
```bash
conda activate shorts
python -c "from diffusers import StableDiffusionPipeline; StableDiffusionPipeline.from_pretrained('runwayml/stable-diffusion-v1-5', cache_dir='./models')"
```

### Error: "Out of memory"

**Solution 1 - Enable optimizations:**
Already enabled in the code:
- fp16 precision
- Attention slicing
- VAE slicing

**Solution 2 - Reduce inference steps:**
```yaml
num_inference_steps: 15  # Instead of 30
```

**Solution 3 - Use CPU (slower but no memory limit):**
```env
SD_DEVICE=cpu
```

### Error: "Connection timeout" during download

The model is large (4-5GB). Solutions:
1. **Wait longer** - First download can take 10-30 minutes
2. **Check internet** - Ensure stable connection
3. **Use mobile hotspot** - If corporate network blocks it
4. **Pre-download** - Download model separately:

```bash
# Download SD 1.5
wget https://huggingface.co/runwayml/stable-diffusion-v1-5/resolve/main/v1-5-pruned-emaonly.safetensors

# Or use git-lfs
git lfs install
git clone https://huggingface.co/runwayml/stable-diffusion-v1-5 ./models/stable-diffusion-v1-5
```

## Performance Comparison

**Test: Generate 5 images (1080x1920, 30 steps)**

| Device | SD 1.5 | SD 2.1 | SDXL |
|--------|--------|--------|------|
| M1 Mac (MPS) | 2-3 min | 3-4 min | 10-15 min |
| RTX 3080 (CUDA) | 15-25 sec | 25-40 sec | 2-3 min |
| CPU (i7) | 15-25 min | 20-30 min | 60+ min |

**Recommendation:** Use **SD 1.5** for the best balance of speed and quality.

## Current Configuration

Your system is now configured to use:

```yaml
# config.yaml
image_generation:
  model_id: "runwayml/stable-diffusion-v1-5"  # ✅ No auth required
  num_inference_steps: 30
  guidance_scale: 7.5
```

```env
# .env
SD_MODEL_ID=runwayml/stable-diffusion-v1-5  # ✅ Updated
SD_DEVICE=mps  # Or cuda/cpu
SD_USE_FP16=true
HUGGINGFACE_TOKEN=  # Not required for SD 1.5
```

## Testing Your Model

Test if the model loads correctly:

```bash
conda activate shorts
python -c "from app.services.image_generator import ImageGenerator; from app.core.config import get_config; img_gen = ImageGenerator(get_config()); img_gen.load_model(); print('✅ Model loaded successfully')"
```

Expected output:
```
Loading Stable Diffusion model: runwayml/stable-diffusion-v1-5
Downloading... (first time only)
✅ Model loaded successfully
```

First download will take 5-15 minutes depending on your internet speed.
