import os
from shutil import rmtree
import time
from pyrogram import filters, Client
from pyromod import listen
from rc_module import download, merge, extract, merge_avs, merge_audio, upload, logger, LOG_FILE_NAME, cancel_download, encode
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

@app.on_message(filters.command("help"))
async def help_command(client, message):
    help_text = (
        "Available commands:\n"
        "/download - Download files from rclone cloud storage\n"
        "/merge - Merge video files\n"
        "/upload - Upload merged video to rclone cloud storage\n"
        "/help - Show this help message"
    )
    await message.reply_text(help_text)

@app.on_message(filters.command("clear"))
async def clear_command(client, message):
    # Clear all files in the DEFAULT_LOCAL_PATH
    await delete_all(DEFAULT_LOCAL_PATH)
    await message.reply_text(f"All files in {DEFAULT_LOCAL_PATH} cleared successfully.")

@app.on_message(filters.command("download"))
async def download_command(client, message):
    # Ask for the rclone remote name
    await message.reply_text("Enter the rclone remote name:")
    remote_name = (await app.listen(message.chat.id)).text

    # Ask for the remote path to download from
    await message.reply_text("Enter the remote path to download from (default: `Work/SSHEMW/Merge`):")
    remote_path = (await app.listen(message.chat.id)).text

    status = await message.reply_text("Downloading..")

    # Download from rclone cloud
    status = await download(status, remote_path, DEFAULT_LOCAL_PATH, remote_name, rclone_config_path=RCLONE_CONFIG_PATH)


@app.on_message(filters.command("merge"))
async def merge_command(client, message):
    # Ask for the local path containing video files to merge
    await message.reply_text("Enter the local path containing video files to merge:")
    merge_local_path = (await app.listen(message.chat.id)).text

    # Ask for the name of the merged video file
    await message.reply_text("Enter the name for the merged video file (e.g., merged_video`.mkv`):")
    output_filename = (await app.listen(message.chat.id)).text

    await message.reply_text("Enter the title for the merged video file (e.g., `@hevcripsofficial`):")
    custom_title = (await app.listen(message.chat.id)).text

    await message.reply_text("Enter the audio arg for the merged video file (e.g., `0:a` # Copy all audio streams, `0:a:1` # Copy the second audio stream (add more if needed)):")
    audio_select = (await app.listen(message.chat.id)).text

    status = await message.reply_text(f"Merging...")

    # Merge videos using ffmpeg and get the merged file path
    await merge(status, merge_local_path, output_filename, custom_title, audio_select)

@app.on_message(filters.command("extract"))
async def extract_command(client, message):
    # Ask for the local path of the video file to extract audio from
    await message.reply_text("Enter the local path of the video file to extract audio from:")
    input_file = (await app.listen(message.chat.id)).text

    # Ask for the output path of the extracted audio file
    await message.reply_text("Enter the local path to save the extracted audio file:")
    output_file = (await app.listen(message.chat.id)).text

    # Ask for the audio stream specifier to extract
    await message.reply_text("Enter the audio stream specifier to extract (e.g., `0:a:1`):")
    audio_stream = (await app.listen(message.chat.id)).text

    # Ask for the audio stream specifier to extract
    await message.reply_text("Enter the stream specifier for codec (e.g., `-c:a` for audio):")
    stream_select = (await app.listen(message.chat.id)).text

    
    # Ask for the audio stream specifier to extract
    await message.reply_text("Enter the stream specifier for codec (e.g., `copy` or `aac` for audio):")
    mode_select = (await app.listen(message.chat.id)).text

    status = message.reply_text("Error extracting audio stream.")

    # Extract the specific audio stream
    await extract(status, input_file, output_file, audio_stream, stream_select, mode_select)

@app.on_message(filters.command("mergeavs"))
async def merge_avs_command(client, message):
    # Ask for the local path containing video files to merge
    await message.reply_text("Enter the local path containing video files to merge:")
    merge_local_path = (await app.listen(message.chat.id)).text

    # Ask for the local paths of the video, audio, and subtitle files
    await message.reply_text("Enter the local path of the video file:")
    video_path = (await app.listen(message.chat.id)).text

    await message.reply_text("Enter the local path of the audio file:")
    audio_path = (await app.listen(message.chat.id)).text

    await message.reply_text("Enter the local path of the subtitle file:")
    subtitle_path = (await app.listen(message.chat.id)).text

    # Ask for the name of the merged output file
    await message.reply_text("Enter the name for the merged output file (e.g., merged_output.mp4):")
    output_filename = (await app.listen(message.chat.id)).text

    # Ask for the custom title for the video
    await message.reply_text("Enter the custom title for the merged video:")
    custom_title = (await app.listen(message.chat.id)).text

    status = await message.reply_text("Error merging video, audio, and subtitle.")

    # Merge video, audio, and subtitle using the defined function
    await merge_avs(status, video_path, DEFAULT_LOCAL_PATH, audio_path, subtitle_path, output_filename, custom_title)

@app.on_message(filters.command("mergea"))
async def merge_avs_command(client, message):
    # Ask for the local paths of the video, audio, and subtitle files
    await message.reply_text("Enter the local path of the video file:")
    video_path = (await app.listen(message.chat.id)).text

    await message.reply_text("Enter the local path of the audio file:")
    audio_path = (await app.listen(message.chat.id)).text

    # Ask for the name of the merged output file
    await message.reply_text("Enter the name for the merged output file (e.g., merged_output.mp4):")
    output_filename = (await app.listen(message.chat.id)).text

    # Ask for the custom title for the video
    await message.reply_text("Enter the custom title for the merged video:")
    custom_title = (await app.listen(message.chat.id)).text

    # Ask for the custom title for the video
    await message.reply_text("Enter the subtitle title for the merged video: (eg. `0:s:0`)")
    subtitle_select = (await app.listen(message.chat.id)).text

    status = await message.reply_text("Merging")

    # Merge video, audio, and subtitle using the defined function
    await merge_audio(status, video_path, DEFAULT_LOCAL_PATH, audio_path, subtitle_select, output_filename, custom_title)

@app.on_message(filters.command("encode"))
async def encode_command(client, message):
    # Ask for the file_name of video
    await message.reply_text("Enter the file_name of the video (e.g., encode.mp4)")
    input_file_name = (await app.listen(message.chat.id)).text

    # Ask for the custom file_name for the encode output
    await message.reply_text("Enter the file_name of the video (e.g., merged_output.mp4)")
    output_file_name = (await app.listen(message.chat.id)).text

    # Ask for the custom title for the video
    await message.reply_text("Enter the custom title for the encoded video:")
    custom_title = (await app.listen(message.chat.id)).text

    status = await message.reply_text("Encoding...") 

    await encode(status, DEFAULT_LOCAL_PATH, input_file_name, output_file_name, custom_title)

@app.on_message(filters.command("upload"))
async def upload_command(client, message):
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

@app.on_message(filters.command("log"))
async def log_command(client, message):
    user_id = message.from_user.id

    # Send the log file
    try:
        await app.send_document(user_id, document=LOG_FILE_NAME, caption="Bot Log File")
    except Exception as e:
        await app.send_message(user_id, f"Failed to send log file. Error: {str(e)}")

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
