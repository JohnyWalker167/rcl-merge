import os
from shutil import rmtree
import time
from datetime import datetime
import subprocess
from pyrogram import filters, Client
from pyromod import listen
from urllib.parse import urlparse, parse_qs, unquote
from rc_module import download, merge, upload, logger, LOG_FILE_NAME, cancel_download, changeindex, softmux
from dotenv import load_dotenv
from pyrogram.errors import FloodWait

load_dotenv()

# Set the default local path
DEFAULT_LOCAL_PATH = '/downloads'

# Set the rclone configuration file path
RCLONE_CONFIG_PATH = os.environ.get("RCLONE_CONFIG_PATH", "/path/to/rclone.conf")

# Initialize Pyrogram client
api_id = int(os.environ.get("API_ID", 0))  # Replace 0 with your actual API ID
api_hash = os.environ.get("API_HASH", "")   # Replace "" with your actual API Hash
bot_token = os.environ.get("BOT_TOKEN", "")  # Replace "" with your actual Bot Token

app = Client("my_bot", api_id=api_id, api_hash=api_hash, bot_token=bot_token)

# Initialize start time
BotTimes = type("BotTimes", (object,), {"task_start": datetime.now()})

def extract_filename(url):
    parsed_url = urlparse(url)
    query_params = parse_qs(parsed_url.query)
    
    # Assume the file parameter contains the filename
    if 'file' in query_params:
        filename = os.path.basename(unquote(query_params['file'][0]))
    else:
        filename = 'downloaded_file'  # Default if no filename is found

    print(f"Extracted filename: {filename}")
    return filename

async def main():
    await app.run()

async def delete_all(dir):
    try:
        rmtree(dir)
    except Exception as e:
        logger.error(f"Error clearing files in {DEFAULT_LOCAL_PATH}: {e}")
        pass
    return

@app.on_message(filters.command("start"))
async def start_command(client, message):
    await message.reply_text("Welcome! This bot can perform rclone operations and video merging. Use /help for commands.")

@app.on_message(filters.command("clear"))
async def clear_command(client, message):
    # Clear all files in the DEFAULT_LOCAL_PATH
    await delete_all(DEFAULT_LOCAL_PATH)
    await message.reply_text(f"All files in {DEFAULT_LOCAL_PATH} cleared successfully.")

@app.on_message(filters.command("download"))
async def download_command(client, message):
    user_id = message.from_user.id
    # Ask for the rclone remote name
    await message.reply_text("Enter the rclone remote name:")
    remote_name = (await app.listen(message.chat.id)).text

    # Ask for the remote path to download from
    await message.reply_text("Enter the remote path to download from (default: `Work/SSHEMW/Merge`):")
    remote_path = (await app.listen(message.chat.id)).text

    status = await message.reply_text("Downloading..")

    # Download from rclone cloud
    downloaded_path = await download(status, remote_path, DEFAULT_LOCAL_PATH, remote_name, rclone_config_path=RCLONE_CONFIG_PATH)
    await app.send_message(user_id, text=f"Download Completed {downloaded_path}") 
    

@app.on_message(filters.command("merge"))
async def merge_command(client, message):
    user_id = message.from_user.id
    # Ask for the local path containing video files to merge
    await message.reply_text("Enter the local path containing video files to merge:")
    merge_local_path = (await app.listen(message.chat.id)).text

    # Ask for the name of the merged video file
    await message.reply_text("Enter the name for the merged video file (e.g., merged_video`.mkv`):")
    output_filename = (await app.listen(message.chat.id)).text

    await message.reply_text("Enter the title for the merged video file (e.g., `REPACKED BY @thetgflix`):")
    custom_title = (await app.listen(message.chat.id)).text

    await message.reply_text("Enter the audio arg for the merged video file (e.g., `0:a` # Copy all audio streams, `0:a:1` # Copy the second audio stream (add more if needed)):")
    audio_select = (await app.listen(message.chat.id)).text

    status = await message.reply_text(f"Merging...")

    # Merge videos using ffmpeg and get the merged file path
    merge_path = await merge(status, merge_local_path, output_filename, custom_title, audio_select)

    await app.send_message(user_id, text=f"Merge Completed `{merge_path}`") 

@app.on_message(filters.command("changeindex"))
async def changeindex_command(client, message):
    user_id = message.from_user.id
    await message.reply_text("Enter the file_name of the video (e.g., encode.mp4)")
    input_file_name = (await app.listen(message.chat.id)).text

    await message.reply_text("Enter the file_name of the video (e.g., merged_output.mp4)")
    output_file_name = (await app.listen(message.chat.id)).text

    await message.reply_text("Enter the title for the merged video file (e.g., `REPACKED BY @thetgflix`):")
    custom_title = (await app.listen(message.chat.id)).text

    await message.reply_text("Enter the audio arg for the merged video file (e.g., `0:a` # Copy all audio streams, `0:a:1` # Copy the second audio stream (add more if needed)):")
    audio_select = (await app.listen(message.chat.id)).text

    status = await message.reply_text(f"changing...")

    change_index_path = await changeindex(status, DEFAULT_LOCAL_PATH, input_file_name, output_file_name, custom_title, audio_select)
    await app.send_message(user_id, text=f"Index Change Completed `{change_index_path}`") 

@app.on_message(filters.command("softmux"))
async def softmux_command(client, message):
    user_id = message.from_user.id
    await message.reply_text("Enter the file_name of the video (e.g., encode.mp4)")
    input_file_name = (await app.listen(message.chat.id)).text

    await message.reply_text("Enter the file_name of the video (e.g., merged_output.mp4)")
    output_file_name = (await app.listen(message.chat.id)).text

    await message.reply_text("Enter the file_name of the subtitle (e.g., `2_English.srt`)")
    subtitle_file_name = (await app.listen(message.chat.id)).text

    await message.reply_text("Enter the title for the merged video file (e.g., `REPACKED BY @thetgflix`):")
    custom_title = (await app.listen(message.chat.id)).text

    await message.reply_text("Enter the audio arg for the merged video file (e.g., `0:a` # Copy all audio streams, `0:a:1` # Copy the second audio stream (add more if needed)):")
    audio_select = (await app.listen(message.chat.id)).text

    status = await message.reply_text(f"changing...")

    softmux_path = await softmux(status, DEFAULT_LOCAL_PATH, input_file_name, output_file_name, custom_title, audio_select, subtitle_file_name)
    await app.send_message(user_id, text=f"Softmux Completed `{softmux_path}`") 

@app.on_message(filters.command("upload"))
async def upload_command(client, message):
    user_id = message.from_user.id
    # Ask for the local path of the merged video file
    await message.reply_text("Enter the local path of the merged video file:")
    local_merged_video = (await app.listen(message.chat.id)).text

    # Ask for the rclone remote name for upload
    await message.reply_text("Enter the rclone remote name for upload:")
    remote_upload_name = (await app.listen(message.chat.id)).text

    # Ask for the remote path to upload to
    await message.reply_text("Enter the remote path to upload to:")
    remote_upload_path = (await app.listen(message.chat.id)).text

    status = await message.reply_text("Uploading...")

    # Upload merged video to rclone cloud
    await upload(status, local_merged_video, remote_upload_path, remote_upload_name, rclone_config_path=RCLONE_CONFIG_PATH)
    await app.send_message(user_id, text="Upload Completed.") 
    
@app.on_message(filters.command("log"))
async def log_command(client, message):
    user_id = message.from_user.id

    # Send the log file
    try:
        await app.send_document(user_id, document=LOG_FILE_NAME, caption="Bot Log File")
    except Exception as e:
        await app.send_message(user_id, f"Failed to send log file. Error: {str(e)}")

@app.on_message(filters.text)
async def handle_download(client, message):
    if message.text.startswith("http://") or message.text.startswith("https://"):
        download_url = message.text
        filename = extract_filename(download_url)

        progress_msg = await message.reply_text("Starting download...")

        command = [
            "aria2c",
            "--continue=true",
            "--max-connection-per-server=4",
            "--split=4",
            "--summary-interval=1",
            "--console-log-level=notice",
            "--dir=" + DEFAULT_LOCAL_PATH,  
            "--out=" + filename,
            download_url
        ]

        BotTimes.task_start = datetime.now()
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        process.communicate()  # Wait for the process to complete

    await progress_msg.edit_text(f'Downloaded ✅ `{filename}` at {datetime.now().strftime("%H:%M:%S")}')

@app.on_message(filters.command("cancel"))
async def cancel_command(client, message):
  msg = cancel_download()
  await message.reply_text(msg)
       
if __name__ == "__main__":
    
    try:
        app.run()
    except FloodWait as e:
        # Handle FloodWait exception
        logger.error(f"FloodWait exception. Waiting for {e.value} seconds.")
        time.sleep(e.value)
        # Retry running the app after waiting
        app.run()
