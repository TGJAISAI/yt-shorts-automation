"""Script generation service using OpenAI GPT."""

import json
import logging
from typing import Dict, Any
from openai import OpenAI

from app.core.config import Config
from app.core.exceptions import ScriptGenerationError, APIError, RateLimitError
from app.utils.retry import retry_with_backoff

logger = logging.getLogger(__name__)


class ScriptGenerator:
    """Generates video scripts using OpenAI GPT."""

    def __init__(self, config: Config):
        """Initialize script generator.

        Args:
            config: Application configuration.
        """
        self.config = config
        self.client = OpenAI(api_key=config.settings.openai_api_key)
        self.script_config = config.script_generation

    def _build_system_prompt(self) -> str:
        """Build the system prompt for GPT.

        Returns:
            System prompt string.
        """
        return f"""You are an expert content creator specializing in {self.script_config.niche}.
Your task is to create engaging, educational YouTube Shorts scripts that are:
- Clear and easy to understand
- Visually descriptive for video generation
- {self.script_config.target_duration_seconds} seconds long when spoken
- Suitable for vertical video format (1080x1920)
- Engaging and informative

Generate scripts with {self.script_config.num_scenes} scenes, where each scene has:
1. A detailed description for video generation
2. Voiceover text that's concise and engaging

The total voiceover should be {self.script_config.min_word_count}-{self.script_config.max_word_count} words.

CRITICAL JSON FORMATTING RULES:
- Return ONLY valid JSON, no markdown code blocks
- Use double quotes for all strings
- Escape special characters: use \\" for quotes, \\n for newlines
- No trailing commas
- Keep strings on single lines where possible"""

    def _build_user_prompt(self, topic: str = None) -> str:
        """Build the user prompt for GPT.

        Args:
            topic: Optional specific topic to cover. If None, GPT will choose.

        Returns:
            User prompt string.
        """
        base_instructions = f"""
Return ONLY a valid JSON object (no markdown, no code blocks) with this exact structure:
{{
    "title": "Engaging title for the video (max 100 chars)",
    "description": "Video description with key points (max 500 chars)",
    "tags": ["tag1", "tag2", "tag3"],
    "scenes": [
        {{
            "scene_id": 1,
            "description": "Detailed description for video generation (what should be shown)",
            "voiceover": "Clear, concise narration for this scene",
            "duration": 10
        }}
    ]
}}

Ensure:
- Exactly {self.script_config.num_scenes} scenes
- Total voiceover is {self.script_config.min_word_count}-{self.script_config.max_word_count} words
- Scene descriptions are detailed for AI video generation
- Duration adds up to approximately {self.script_config.target_duration_seconds} seconds
- All text is on single lines (no line breaks within strings)
"""

        if topic:
            return f"""Create a YouTube Shorts script about: {topic}

The script should be in the niche: {self.script_config.niche}

{base_instructions}"""
        else:
            return f"""Create a YouTube Shorts script about an interesting topic in: {self.script_config.niche}

Choose a specific topic that would be engaging and educational.

{base_instructions}"""

    @retry_with_backoff(
        max_attempts=3,
        base_delay=2.0,
        exceptions=(APIError, RateLimitError)
    )
    def generate_script(self, topic: str = None) -> Dict[str, Any]:
        """Generate a video script using OpenAI GPT.

        Args:
            topic: Optional specific topic. If None, GPT chooses.

        Returns:
            Dictionary containing script data with title, description, tags, and scenes.

        Raises:
            ScriptGenerationError: If script generation fails.
        """
        try:
            logger.info(f"Generating script for topic: {topic or 'auto-selected'}")

            system_prompt = self._build_system_prompt()
            user_prompt = self._build_user_prompt(topic)

            response = self.client.chat.completions.create(
                model=self.script_config.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=self.script_config.max_tokens,
                temperature=self.script_config.temperature,
                response_format={"type": "json_object"}
            )

            # Extract and parse response
            content = response.choices[0].message.content
            if not content:
                raise ScriptGenerationError("GPT returned empty response")

            logger.debug(f"Raw GPT response: {content[:200]}...")

            # Parse JSON
            script_data = json.loads(content)

            # Validate script structure
            self._validate_script(script_data)

            logger.info(f"Successfully generated script: {script_data['title']}")
            return script_data

        except json.JSONDecodeError as e:
            raise ScriptGenerationError(f"Failed to parse GPT response as JSON: {str(e)}")

        except Exception as e:
            if "rate_limit" in str(e).lower():
                raise RateLimitError("OpenAI API rate limit exceeded")
            elif "api_key" in str(e).lower() or "auth" in str(e).lower():
                raise ScriptGenerationError(f"Authentication error: {str(e)}")
            else:
                raise ScriptGenerationError(f"Script generation failed: {str(e)}")

    def _validate_script(self, script_data: Dict[str, Any]):
        """Validate script structure and content.

        Args:
            script_data: Script data to validate.

        Raises:
            ScriptGenerationError: If validation fails.
        """
        required_fields = ["title", "description", "tags", "scenes"]
        for field in required_fields:
            if field not in script_data:
                raise ScriptGenerationError(f"Missing required field: {field}")

        # Validate scenes
        scenes = script_data.get("scenes", [])
        if len(scenes) != self.script_config.num_scenes:
            logger.warning(
                f"Expected {self.script_config.num_scenes} scenes, got {len(scenes)}. "
                "Proceeding anyway."
            )

        if not scenes:
            raise ScriptGenerationError("Script has no scenes")

        # Validate each scene
        for i, scene in enumerate(scenes):
            required_scene_fields = ["scene_id", "description", "voiceover", "duration"]
            for field in required_scene_fields:
                if field not in scene:
                    raise ScriptGenerationError(f"Scene {i+1} missing field: {field}")

        # Validate word count
        total_words = sum(len(scene["voiceover"].split()) for scene in scenes)
        if total_words > self.script_config.max_word_count * 1.2:
            logger.warning(
                f"Script has {total_words} words, which may exceed target duration. "
                f"Recommended: {self.script_config.min_word_count}-{self.script_config.max_word_count} words"
            )
