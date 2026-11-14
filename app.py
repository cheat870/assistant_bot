"""
Telegram Smart Assistant Bot - Gradio Web Dashboard for Hugging Face Spaces (24/7 Hosting)
Runs the Telegram Bot in a supervised background process and serves a status UI on port 7860.
"""
import os
import sys
import time
import subprocess
import threading
import gradio as gr

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

bot_process = None

def start_bot():
    global bot_process
    print("🚀 Starting Telegram Assistant Bot in background...")
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    # Ensure health server port inside bot doesn't conflict with Gradio (7860)
    env["PORT"] = "8080"
    
    cmd = [sys.executable, os.path.join(PROJECT_ROOT, "main.py")]
    bot_process = subprocess.Popen(
        cmd,
        cwd=PROJECT_ROOT,
        env=env,
        stdout=sys.stdout,
        stderr=sys.stderr
    )

def bot_supervisor():
    """Background supervisor to keep the bot process alive 24/7."""
    time.sleep(2)
    while True:
        global bot_process
        if bot_process is None or bot_process.poll() is not None:
            print("⚠️ Bot process is not running. Starting/Restarting...")
            try:
                start_bot()
            except Exception as e:
                print(f"❌ Error starting bot: {e}")
        time.sleep(10)

# Start supervisor thread
supervisor_thread = threading.Thread(target=bot_supervisor, daemon=True)
supervisor_thread.start()

def get_status():
    global bot_process
    if bot_process and bot_process.poll() is None:
        return "🟢 Online (Running 24/7)"
    return "🟡 Initializing..."

# Build modern Gradio Dashboard
with gr.Blocks(title="Telegram Smart Assistant Bot 🇰🇭", theme=gr.themes.Soft()) as demo:
    gr.Markdown(
        """
        # 🇰🇭 Telegram Smart Assistant Bot (Hub 4.0 Pro Ultimate)
        ### 🤖 Bot is actively running 24/7 on Hugging Face Spaces!
        
        - **Bot Username:** [@Researchmap_bot](https://t.me/Researchmap_bot)
        - **Channel Storage:** [@Song182](https://t.me/Song182)
        - **Uptime Status:** 🟢 Active 24/7
        """
    )
    
    with gr.Row():
        status_box = gr.Textbox(value=get_status, label="Service Status", interactive=False)
        refresh_btn = gr.Button("🔄 Refresh Status")
        refresh_btn.click(fn=get_status, outputs=status_box)

    gr.Markdown(
        """
        ---
        ### 🎵 Featured Commands:
        - `/song <song_name>` - Download MP3 320kbps & Auto-archive to @Song182
        - `/pdf` - Chat with PDF & Auto-Summarize documents
        - `/enhance` - AI Image Enhancer & 4x Super-Resolution
        - `/budget` - Income & Expense Tracker in USD/KHR
        - `/check` - Khmer Spellchecker (Chuon Nath Dictionary)
        
        👉 **[Click Here to Open Bot in Telegram](https://t.me/Researchmap_bot)**
        """
    )

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860)
