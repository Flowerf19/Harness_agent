# filepath: discord-bot-gemini/src/services/channel_service.py
import os
import requests
import logging

logger = logging.getLogger('discord_bot')

class ChannelService:
    def __init__(self):
        self.gemini_api_url = os.getenv('GEMINI_API_URL', 'http://localhost:11434/api/generate')

    def get_channel_info(self, channel_id):
        """Fetch channel information from the Gemini API."""
        try:
            response = requests.get(f"{self.gemini_api_url}/channels/{channel_id}")
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch channel info: {e}")
            return None

    def create_channel(self, channel_data):
        """Create a new channel using the Gemini API."""
        try:
            response = requests.post(f"{self.gemini_api_url}/channels", json=channel_data)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to create channel: {e}")
            return None

    def update_channel(self, channel_id, channel_data):
        """Update an existing channel using the Gemini API."""
        try:
            response = requests.put(f"{self.gemini_api_url}/channels/{channel_id}", json=channel_data)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to update channel: {e}")
            return None

    def delete_channel(self, channel_id):
        """Delete a channel using the Gemini API."""
        try:
            response = requests.delete(f"{self.gemini_api_url}/channels/{channel_id}")
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to delete channel: {e}")
            return None