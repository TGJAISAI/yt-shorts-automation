#!/bin/bash

# Setup script for YouTube Shorts Automation

echo "=== YouTube Shorts Automation Setup ==="
echo

# Check if .env exists
if [ -f .env ]; then
    echo "✓ .env file already exists"
else
    echo "Creating .env file from template..."
    cp .env.example .env
    echo "✓ Created .env file"
    echo
    echo "⚠️  IMPORTANT: Edit .env and add your API keys:"
    echo "   - OPENAI_API_KEY"
    echo "   - YOUTUBE_CLIENT_ID"
    echo "   - YOUTUBE_CLIENT_SECRET"
    echo "   - YOUTUBE_REFRESH_TOKEN"
    echo
fi

# Activate conda environment
echo "Activating conda environment 'shorts'..."
source /opt/anaconda3/etc/profile.d/conda.sh
conda activate shorts

# Verify installations
echo
echo "=== Verifying Installations ==="
python -c "from diffusers import StableDiffusionPipeline; print('✓ Diffusers')" 2>/dev/null || echo "✗ Diffusers"
python -c "from openai import OpenAI; print('✓ OpenAI')" 2>/dev/null || echo "✗ OpenAI"
python -c "from gtts import gTTS; print('✓ gTTS')" 2>/dev/null || echo "✗ gTTS"
python -c "from moviepy.editor import VideoFileClip; print('✓ MoviePy')" 2>/dev/null || echo "✗ MoviePy"
python -c "from fastapi import FastAPI; print('✓ FastAPI')" 2>/dev/null || echo "✗ FastAPI"

echo
echo "=== Environment Setup Complete ==="
echo
echo "Next steps:"
echo "1. Edit .env and add your API keys"
echo "2. Run: conda activate shorts"
echo "3. Run: python main.py"
echo "4. Visit: http://localhost:8000/docs"
echo
