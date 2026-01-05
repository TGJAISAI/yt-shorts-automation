# YouTube Shorts Automation Pipeline

Automated end-to-end video generation and upload pipeline for YouTube Shorts. Generates AI education videos using OpenAI GPT for scripts, Stable Diffusion for images, gTTS for narration, and automatically uploads to YouTube.

## Features

- **AI-Powered Script Generation**: Uses OpenAI GPT to create engaging "AI explained simply" video scripts
- **Local Image Generation**: Stable Diffusion 2.1 generates vertical (1080x1920) images locally
- **Text-to-Speech**: gTTS generates natural-sounding narration
- **Automated Video Rendering**: MoviePy assembles images and audio into vertical YouTube Shorts
- **Automated Uploads**: Uploads to YouTube every 8 hours (3 videos per day)
- **FastAPI REST API**: Manual triggers and monitoring endpoints
- **Comprehensive Logging**: Structured JSON logging for debugging
- **Error Handling**: Retry logic with exponential backoff

## Architecture

```
OpenAI GPT → Stable Diffusion → gTTS → MoviePy → YouTube API
(Script)     (Images)           (Audio) (Video)   (Upload)
```

## Requirements

- Python 3.10+
- OpenAI API key
- YouTube Data API v3 credentials
- Sufficient disk space for video storage
- GPU recommended for Stable Diffusion (works on CPU but slower)

## Installation

### 1. Clone the Repository

```bash
cd /Users/jaisai/Dev/yt-shorts-automation
```

### 2. Create Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Set Up Environment Variables

Copy the example environment file:

```bash
cp .env.example .env
```

Edit `.env` and add your API keys:

```env
# OpenAI API Key
OPENAI_API_KEY=sk-...

# YouTube API Credentials
YOUTUBE_CLIENT_ID=your_client_id
YOUTUBE_CLIENT_SECRET=your_client_secret
YOUTUBE_REFRESH_TOKEN=your_refresh_token

# Stable Diffusion Settings
SD_DEVICE=mps  # Use 'cuda' for NVIDIA GPU, 'mps' for Apple Silicon, 'cpu' for CPU
SD_USE_FP16=true

# Paths
DATA_DIR=/Users/jaisai/Dev/yt-shorts-automation/data
MODELS_DIR=/Users/jaisai/Dev/yt-shorts-automation/models
```

### 5. Configure YouTube API

#### Step-by-step YouTube API Setup:

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project
3. Enable "YouTube Data API v3"
4. Create OAuth 2.0 credentials:
   - Application type: Desktop app
   - Download credentials JSON
5. Get refresh token:
   ```bash
   python -c "from google_auth_oauthlib.flow import InstalledAppFlow; flow = InstalledAppFlow.from_client_secrets_file('client_secrets.json', ['https://www.googleapis.com/auth/youtube.upload']); credentials = flow.run_local_server(port=8080); print('Refresh Token:', credentials.refresh_token)"
   ```
6. Add the credentials to `.env`

## Configuration

Edit `config.yaml` to customize:

- Script generation parameters (word count, target duration)
- Image generation settings (model, inference steps, style)
- Video rendering options (fps, codec, transitions)
- YouTube upload settings (privacy, category, tags)
- Scheduling interval

## Usage

### Start the Server

```bash
python main.py
```

The server will start on `http://localhost:8000`

### API Endpoints

#### Generate Video (Synchronous)

```bash
curl -X POST http://localhost:8000/api/v1/generate \
  -H "Content-Type: application/json" \
  -d '{"topic": "What is Neural Network?"}'
```

#### Generate Video (Asynchronous)

```bash
curl -X POST http://localhost:8000/api/v1/generate/async \
  -H "Content-Type: application/json" \
  -d '{"topic": null}'
```

#### Check Status

```bash
curl http://localhost:8000/api/v1/status
```

#### List Recent Videos

```bash
curl http://localhost:8000/api/v1/videos?limit=10
```

#### List Recent Uploads

```bash
curl http://localhost:8000/api/v1/uploads?limit=10
```

#### Start Scheduler

```bash
curl -X POST http://localhost:8000/api/v1/scheduler/start
```

#### Stop Scheduler

```bash
curl -X POST http://localhost:8000/api/v1/scheduler/stop
```

#### Health Check

```bash
curl http://localhost:8000/api/v1/health
```

### Interactive API Documentation

Visit `http://localhost:8000/docs` for Swagger UI documentation.

## Automated Scheduling

The application automatically generates and uploads videos every 8 hours (configurable in `.env`).

To enable/disable:
```env
SCHEDULE_ENABLED=true
SCHEDULE_INTERVAL_HOURS=8
```

## File Structure

```
yt-shorts-automation/
├── app/
│   ├── api/              # FastAPI routes and schemas
│   ├── core/             # Configuration, logging, exceptions
│   ├── services/         # Script, image, audio, video, upload services
│   ├── pipeline/         # Orchestrator and validators
│   └── utils/            # File manager, retry logic
├── data/
│   ├── outputs/          # Generated content
│   │   ├── scripts/
│   │   ├── images/
│   │   ├── audio/
│   │   └── videos/
│   ├── prompts/          # Prompt templates
│   └── metadata/         # Upload history
├── logs/                 # Application logs
├── models/               # Stable Diffusion model cache
├── main.py               # FastAPI application
├── scheduler.py          # APScheduler configuration
├── config.yaml           # Application configuration
└── requirements.txt      # Python dependencies
```

## Pipeline Flow

1. **Script Generation** (OpenAI GPT)
   - Generates title, description, and 5 scenes
   - Each scene has image prompt and voiceover
   - Target: 45-50 seconds of narration

2. **Image Generation** (Stable Diffusion)
   - Generates 1080x1920 vertical images
   - One image per scene
   - Optimized with fp16 and attention slicing

3. **Audio Generation** (gTTS)
   - Converts voiceover text to speech
   - Validates duration < 60s
   - Saves as MP3

4. **Video Rendering** (MoviePy)
   - Combines images and audio
   - Adds transitions and title overlay
   - Exports as vertical MP4 (1080x1920)

5. **YouTube Upload**
   - Uploads with metadata
   - Auto-detected as Short (vertical + <60s)
   - Logs video ID and URL

## Troubleshooting

### Out of Memory (OOM) Errors

If Stable Diffusion runs out of memory:

1. Enable fp16 in `.env`: `SD_USE_FP16=true`
2. Reduce inference steps in `config.yaml`: `num_inference_steps: 20`
3. Use SD 1.5 instead of 2.1: `SD_MODEL_ID=runwayml/stable-diffusion-v1-5`
4. Fall back to CPU: `SD_DEVICE=cpu`

### YouTube API Quota Exceeded

- Default quota: 10,000 units/day
- Upload cost: ~1,600 units
- Max uploads/day: ~6 videos
- Request quota increase from Google

### Video Duration Exceeds 60s

- Reduce `max_word_count` in `config.yaml`
- Decrease `target_duration_seconds`
- Script will auto-regenerate if too long

### Audio Quality Issues

- gTTS is free but basic quality
- For better quality, switch to:
  - Coqui TTS (local, high quality)
  - Edge TTS (Microsoft, free)
  - ElevenLabs (paid, best quality)

## Performance Optimization

### Image Generation Speed

- **GPU**: Use CUDA (NVIDIA) or MPS (Apple Silicon)
- **Reduce steps**: 20-25 instead of 50
- **Use SD 1.5**: Faster than SD 2.1
- **Enable attention slicing**: Already enabled

### Video Rendering Speed

- **Use medium preset**: Faster than slow
- **Reduce FPS**: 24 instead of 30
- **Lower bitrate**: 5000k instead of 8000k

## Monitoring

### Logs

Logs are stored in `logs/app.log` with rotation (10MB max, 5 backups).

View logs:
```bash
tail -f logs/app.log
```

### Disk Usage

Check disk usage via API:
```bash
curl http://localhost:8000/api/v1/status
```

Cleanup old files:
```bash
curl -X POST http://localhost:8000/api/v1/cleanup?keep_days=30
```

## Production Deployment

### Using systemd (Linux)

Create `/etc/systemd/system/yt-shorts.service`:

```ini
[Unit]
Description=YouTube Shorts Automation
After=network.target

[Service]
Type=simple
User=your_user
WorkingDirectory=/path/to/yt-shorts-automation
Environment="PATH=/path/to/venv/bin"
ExecStart=/path/to/venv/bin/python main.py
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable yt-shorts
sudo systemctl start yt-shorts
sudo systemctl status yt-shorts
```

### Using Docker (Optional)

Create `Dockerfile`:

```dockerfile
FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["python", "main.py"]
```

Build and run:
```bash
docker build -t yt-shorts-automation .
docker run -d -p 8000:8000 --env-file .env yt-shorts-automation
```

## License

MIT License - See LICENSE file for details

## Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## Support

For issues and questions:
- GitHub Issues: [Create an issue](https://github.com/yourusername/yt-shorts-automation/issues)
- Documentation: See `/docs` endpoint when server is running

## Acknowledgments

- OpenAI for GPT API
- Stability AI for Stable Diffusion
- Google for YouTube Data API and gTTS
- FastAPI, MoviePy, and all open-source contributors

# yt-shorts-automation