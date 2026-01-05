# Troubleshooting Guide

## Quick Start Checklist

✅ **All fixes have been applied!** The following issues have been resolved:

1. ✅ Diffusers import error (huggingface_hub version conflict)
2. ✅ JSON parsing error (GPT unterminated strings)
3. ✅ Config attribute error (wrong config structure access)

## Verifying the Fixes

Run the configuration test:

```bash
conda activate shorts
python test_config.py
```

Expected output:
```
✓ Config loaded successfully
✓ ImageGenerator initialized
✅ All tests passed!
```

## Starting the Server

```bash
# Activate the conda environment
conda activate shorts

# Start the server
python main.py
```

Expected output:
```
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

## Testing Video Generation

Once the server is running:

```bash
# In another terminal
curl -X POST http://localhost:8000/api/v1/generate \
  -H "Content-Type: application/json" \
  -d '{"topic": "What is Machine Learning?"}'
```

## Common Issues & Solutions

### Issue: "OPENAI_API_KEY is required"

**Solution:** Make sure you have a `.env` file with your API key:

```bash
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY
```

### Issue: "YOUTUBE_CLIENT_ID is required"

**Solution:** Add your YouTube API credentials to `.env`:

```env
YOUTUBE_CLIENT_ID=your_client_id
YOUTUBE_CLIENT_SECRET=your_client_secret
YOUTUBE_REFRESH_TOKEN=your_refresh_token
```

See README.md for instructions on how to get these credentials.

### Issue: Pydantic warning about "model_id"

**Warning:**
```
Field "model_id" has conflict with protected namespace "model_"
```

**Impact:** This is just a warning from Pydantic 2.x and doesn't affect functionality. Can be safely ignored.

**Solution (optional):** You can suppress it by adding to the config classes:
```python
model_config = ConfigDict(protected_namespaces=())
```

### Issue: Out of Memory during image generation

**Symptoms:**
```
torch.cuda.OutOfMemoryError
# or
RuntimeError: MPS backend out of memory
```

**Solutions:**

1. **Enable fp16 (if not already):**
   ```env
   SD_USE_FP16=true
   ```

2. **Reduce inference steps in config.yaml:**
   ```yaml
   image_generation:
     num_inference_steps: 20  # Instead of 30
   ```

3. **Use a smaller model:**
   ```env
   SD_MODEL_ID=runwayml/stable-diffusion-v1-5
   ```

4. **Fall back to CPU (slower but no memory limits):**
   ```env
   SD_DEVICE=cpu
   ```

### Issue: Stable Diffusion model download fails

**Error:**
```
OSError: Can't load config for 'stabilityai/stable-diffusion-2-1'
```

**Solutions:**

1. **Check internet connection** - First download is ~5GB

2. **Set HuggingFace token (if using gated models):**
   ```env
   HUGGINGFACE_TOKEN=your_token_here
   ```

3. **Use a different model:**
   ```env
   SD_MODEL_ID=runwayml/stable-diffusion-v1-5
   ```

### Issue: gTTS fails with rate limiting

**Error:**
```
gTTS.tts.gTTSError: Failed to retrieve audio
```

**Solutions:**

1. **Add delay between requests** (already implemented in retry logic)

2. **Wait a few minutes and try again**

3. **Switch to alternative TTS** (requires code modification):
   - pyttsx3 (offline, lower quality)
   - Edge TTS (Microsoft, good quality)
   - Coqui TTS (local, high quality, GPU recommended)

### Issue: MoviePy rendering is slow

**Symptoms:** Video rendering takes >5 minutes

**Solutions:**

1. **Check codec settings in config.yaml:**
   ```yaml
   video_rendering:
     preset: "medium"  # or "fast" for faster rendering
   ```

2. **Reduce FPS:**
   ```yaml
   video_rendering:
     fps: 24  # Instead of 30
   ```

3. **Reduce bitrate:**
   ```yaml
   video_rendering:
     bitrate: "5000k"  # Instead of "8000k"
   ```

### Issue: YouTube upload quota exceeded

**Error:**
```
QuotaExceededError: YouTube API quota exceeded
```

**Facts:**
- Default quota: 10,000 units/day
- Each upload: ~1,600 units
- Max uploads: ~6 per day with default quota

**Solutions:**

1. **Request quota increase:**
   - Go to Google Cloud Console
   - Navigate to YouTube Data API v3
   - Request quota increase (explain use case)

2. **Reduce upload frequency:**
   ```env
   SCHEDULE_INTERVAL_HOURS=12  # Instead of 8 (2 videos/day)
   ```

3. **Monitor quota usage:**
   ```bash
   curl http://localhost:8000/api/v1/status | jq '.quota_info'
   ```

### Issue: Video duration exceeds 60 seconds

**Error:**
```
DurationExceededError: Audio duration 62.3s exceeds maximum 59s
```

**Solutions:**

1. **Reduce word count in config.yaml:**
   ```yaml
   script_generation:
     max_word_count: 130  # Instead of 150
     target_duration_seconds: 45  # Instead of 50
   ```

2. **Use fewer scenes:**
   ```yaml
   script_generation:
     num_scenes: 4  # Instead of 5
   ```

3. **The pipeline will automatically retry** with adjusted settings

## Monitoring

### Check Pipeline Status

```bash
curl http://localhost:8000/api/v1/status
```

Returns:
- Disk usage
- Recent jobs
- Recent uploads
- Quota information
- Model status

### View Logs

```bash
# Real-time logs
tail -f logs/app.log

# Search for errors
grep ERROR logs/app.log

# View JSON logs
cat logs/app.log | jq 'select(.level=="ERROR")'
```

### List Generated Videos

```bash
curl http://localhost:8000/api/v1/videos?limit=10
```

### Check Scheduler Status

```bash
curl http://localhost:8000/api/v1/scheduler/status
```

## Performance Benchmarks

Expected timings on M1 Mac (MPS device):

1. **Script Generation:** 5-10 seconds
2. **Image Generation:** 2-4 minutes (5 images @ 30 steps)
3. **Audio Generation:** 5 seconds
4. **Video Rendering:** 30-60 seconds
5. **YouTube Upload:** 30-60 seconds

**Total:** 4-6 minutes per video

On NVIDIA GPU (CUDA):
- Image generation: 1-2 minutes
- **Total:** 2-3 minutes per video

On CPU:
- Image generation: 15-30 minutes
- **Total:** 17-32 minutes per video

## Getting Help

If you encounter issues not covered here:

1. **Check the logs:**
   ```bash
   tail -50 logs/app.log
   ```

2. **Check if services are accessible:**
   ```bash
   # Test OpenAI
   curl https://api.openai.com/v1/models \
     -H "Authorization: Bearer $OPENAI_API_KEY"

   # Test YouTube API
   curl -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
     https://www.googleapis.com/youtube/v3/channels?part=snippet&mine=true
   ```

3. **Review failed GPT responses:**
   ```bash
   cat /tmp/failed_gpt_response.txt
   ```

4. **Check environment variables:**
   ```bash
   conda activate shorts
   python -c "from app.core.config import get_config; c = get_config(); print(c.settings)"
   ```

5. **Verify all packages are installed:**
   ```bash
   ./setup_env.sh
   ```

## Success Indicators

When everything is working correctly:

- ✅ Server starts without errors
- ✅ `/api/v1/health` returns `{"status": "healthy"}`
- ✅ `/api/v1/status` shows model loaded
- ✅ `/api/v1/generate` completes successfully
- ✅ Video appears on YouTube
- ✅ Scheduler runs automatically every 8 hours
- ✅ Logs show "Pipeline completed successfully"

## Clean Start

If you need to reset everything:

```bash
# Stop the server (Ctrl+C)

# Clean up generated files (optional)
rm -rf data/outputs/*
rm -rf logs/*

# Keep models cache to avoid re-downloading
# rm -rf models/*  # Only if you want to re-download

# Restart
conda activate shorts
python main.py
```
