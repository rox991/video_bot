import os
import telebot
import yt_dlp
import tempfile
from flask import Flask, request
from openai import OpenAI

# Environment Variables
BOT_TOKEN = os.environ.get("BOT_TOKEN")
HF_TOKEN = os.environ.get("HF_TOKEN")

# Bot and Flask setup
bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# HuggingFace OpenAI-compatible client
hf_client = OpenAI(
    base_url="https://router.huggingface.co/v1",
    api_key=HF_TOKEN,
)


def ask_ai(prompt: str) -> str:
    """Send a prompt to DeepSeek via HuggingFace router."""
    try:
        chat_completion = hf_client.chat.completions.create(
            model="deepseek-ai/DeepSeek-R1:novita",
            messages=[{"role": "user", "content": prompt}],
        )
        return chat_completion.choices[0].message.content
    except Exception as e:
        return f"AI Error: {str(e)}"


def download_video(url: str, output_dir: str) -> str:
    """Download video from URL using yt-dlp and return file path."""
    ydl_opts = {
        "outtmpl": os.path.join(output_dir, "%(title)s.%(ext)s"),
        "format": "best[filesize<50M]/best",          # Telegram limit ~50MB
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        return filename


# ── Handlers ──────────────────────────────────────────────────────────────────

@bot.message_handler(commands=["start", "help"])
def send_welcome(message):
    bot.reply_to(
        message,
        "👋 *Welcome!* Here's what I can do:\n\n"
        "🎥 *Download a video* – just send me any video URL\n"
        "🤖 *Ask AI* – use /ask <your question> to chat with DeepSeek R1\n\n"
        "Supported sites: YouTube, Instagram, Twitter/X, TikTok, Facebook, and 1000+ more.",
        parse_mode="Markdown",
    )


@bot.message_handler(commands=["ask"])
def handle_ask(message):
    prompt = message.text.replace("/ask", "", 1).strip()
    if not prompt:
        bot.reply_to(message, "Please provide a question. Example:\n`/ask What is the capital of France?`", parse_mode="Markdown")
        return
    thinking_msg = bot.reply_to(message, "🤔 Thinking...")
    response = ask_ai(prompt)
    bot.edit_message_text(
        chat_id=message.chat.id,
        message_id=thinking_msg.message_id,
        text=f"🤖 *DeepSeek R1:*\n\n{response}",
        parse_mode="Markdown",
    )


@bot.message_handler(func=lambda msg: msg.text and (
    msg.text.startswith("http://") or msg.text.startswith("https://")
))
def handle_video_url(message):
    url = message.text.strip()
    status_msg = bot.reply_to(message, "⏳ Downloading your video, please wait...")

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=status_msg.message_id,
                text="📥 Fetching video info and downloading...",
            )
            filepath = download_video(url, tmpdir)

            file_size = os.path.getsize(filepath)
            if file_size > 50 * 1024 * 1024:
                bot.edit_message_text(
                    chat_id=message.chat.id,
                    message_id=status_msg.message_id,
                    text="❌ Video is larger than 50 MB. Telegram doesn't allow files this big. Try a shorter clip.",
                )
                return

            bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=status_msg.message_id,
                text="📤 Uploading to Telegram...",
            )
            with open(filepath, "rb") as video_file:
                bot.send_video(
                    message.chat.id,
                    video_file,
                    caption="✅ Here's your video!",
                    supports_streaming=True,
                )
            bot.delete_message(message.chat.id, status_msg.message_id)

    except yt_dlp.utils.DownloadError as e:
        bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=status_msg.message_id,
            text=f"❌ Download failed:\n`{str(e)}`",
            parse_mode="Markdown",
        )
    except Exception as e:
        bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=status_msg.message_id,
            text=f"⚠️ Unexpected error:\n`{str(e)}`",
            parse_mode="Markdown",
        )


@bot.message_handler(func=lambda msg: True)
def handle_unknown(message):
    bot.reply_to(
        message,
        "🤷 I didn't understand that.\n"
        "Send a video URL to download, or use /ask <question> to chat with AI.\n"
        "Type /help for more info.",
    )


# ── Flask Webhook ──────────────────────────────────────────────────────────────

@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    json_str = request.get_data(as_text=True)
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return "OK", 200


@app.route("/")
def index():
    return "Bot is running!", 200


# ── Entry Point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Set webhook on startup (Render provides RENDER_EXTERNAL_URL automatically)
    render_url = os.environ.get("RENDER_EXTERNAL_URL")
    if render_url:
        webhook_url = f"{render_url}/{BOT_TOKEN}"
        bot.remove_webhook()
        bot.set_webhook(url=webhook_url)
        print(f"Webhook set to: {webhook_url}")
    else:
        # Local development: use polling instead
        print("No RENDER_EXTERNAL_URL found – starting polling mode.")
        bot.remove_webhook()
        bot.infinity_polling()

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
