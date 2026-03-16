import os
import logging
import tempfile
from typing import Optional
import telebot
from telebot.types import Message
import yt_dlp
import requests
from flask import Flask, request
import threading

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Get environment variables
BOT_TOKEN = os.environ.get('BOT_TOKEN')
HF_TOKEN = os.environ.get('HF_TOKEN')

if not BOT_TOKEN:
    logger.error("BOT_TOKEN environment variable not set!")
    exit(1)

# Initialize bot
bot = telebot.TeleBot(BOT_TOKEN)

# Flask app for keeping the service alive on Render
app = Flask(__name__)

# Download options for yt-dlp
DOWNLOAD_OPTIONS = {
    'format': 'best[ext=mp4]/best',  # Prefer mp4 format
    'outtmpl': tempfile.gettempdir() + '/%(title)s.%(ext)s',
    'quiet': True,
    'no_warnings': True,
    'extract_flat': False,
}

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message: Message):
    """Send welcome message when /start or /help is issued"""
    welcome_text = (
        "👋 Welcome to Video Downloader Bot!\n\n"
        "Send me any video link (YouTube, Twitter, Instagram, Facebook, TikTok, etc.) "
        "and I'll download it for you and send it back as a video file.\n\n"
        "Just paste the link and I'll do the rest! 🎥"
    )
    bot.reply_to(message, welcome_text)

@bot.message_handler(func=lambda message: True)
def handle_message(message: Message):
    """Handle all text messages (assumed to be links)"""
    url = message.text.strip()
    
    # Basic URL validation
    if not url.startswith(('http://', 'https://')):
        bot.reply_to(message, "❌ Please send a valid URL starting with http:// or https://")
        return
    
    # Send processing message
    processing_msg = bot.reply_to(message, "⏳ Processing your video... This may take a moment.")
    
    try:
        # Download the video
        video_path = download_video(url)
        
        if video_path and os.path.exists(video_path):
            # Send the video
            with open(video_path, 'rb') as video_file:
                bot.send_video(
                    message.chat.id,
                    video_file,
                    caption="✅ Here's your video!",
                    supports_streaming=True
                )
            
            # Clean up the file
            os.remove(video_path)
            
            # Delete processing message
            bot.delete_message(message.chat.id, processing_msg.message_id)
        else:
            bot.edit_message_text(
                "❌ Failed to download video. Make sure the link is valid and the video is accessible.",
                message.chat.id,
                processing_msg.message_id
            )
            
    except Exception as e:
        logger.error(f"Error downloading video: {str(e)}")
        bot.edit_message_text(
            f"❌ An error occurred: {str(e)[:100]}",
            message.chat.id,
            processing_msg.message_id
        )

def download_video(url: str) -> Optional[str]:
    """Download video from URL and return the file path"""
    try:
        with yt_dlp.YoutubeDL(DOWNLOAD_OPTIONS) as ydl:
            # Extract info and download
            info = ydl.extract_info(url, download=True)
            
            # Get the downloaded file path
            if 'entries' in info:  # Playlist
                video = info['entries'][0]
            else:  # Single video
                video = info
            
            # Construct the filename
            filename = ydl.prepare_filename(video)
            
            # Check if file exists (adjust extension if needed)
            if os.path.exists(filename):
                return filename
            
            # Try with mp4 extension if the original didn't work
            base, _ = os.path.splitext(filename)
            mp4_filename = base + '.mp4'
            if os.path.exists(mp4_filename):
                return mp4_filename
            
            return None
            
    except Exception as e:
        logger.error(f"Download error: {str(e)}")
        raise e

# Optional: You can use the HF_TOKEN for additional features if needed
def hf_api_example():
    """Example function showing how to use HF_TOKEN if you need AI features later"""
    if HF_TOKEN:
        try:
            headers = {"Authorization": f"Bearer {HF_TOKEN}"}
            # You can add Hugging Face API calls here if needed
            pass
        except Exception as e:
            logger.error(f"HF API error: {str(e)}")

@app.route('/')
def home():
    return "Video Downloader Bot is running!"

@app.route('/health')
def health():
    return "OK", 200

def start_bot():
    """Start the bot in a separate thread"""
    logger.info("Starting bot...")
    try:
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
    except Exception as e:
        logger.error(f"Bot polling error: {str(e)}")

if __name__ == '__main__':
    # Start bot in a separate thread
    bot_thread = threading.Thread(target=start_bot, daemon=True)
    bot_thread.start()
    
    # Run Flask app (for Render's web service)
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
