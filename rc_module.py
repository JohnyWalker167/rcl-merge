import re
from re import findall as refindall
import os
import asyncio
import logging
import subprocess
from logging.handlers import RotatingFileHandler

# Configure the logging module
LOG_FILE_NAME = "mergebot.txt"

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s - %(levelname)s] - %(name)s - %(message)s",
    datefmt='%d-%b-%y %H:%M:%S',
    handlers=[
        RotatingFileHandler(
            LOG_FILE_NAME,
            maxBytes=50000000,
            backupCount=10
        ),
        logging.StreamHandler()
    ]
)
logging.getLogger("pyrogram").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# Global process variable for cancellation
process = None

async def execute_command(command, status, progress_label):
    global process
    last_text = None
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        while True:
            line = await process.stdout.readline()
            if not line:
                break

            line = line.strip()

            # Parse the ffmpeg progress output
            frame_match = re.search(r'frame=\s*(\d+)', line)
            fps_match = re.search(r'fps=\s*(\d+\.?\d*)', line)
            size_match = re.search(r'size=\s*([\d\.]+(?:kB|MB|GB))', line)
            time_match = re.search(r'time=(\d{2}:\d{2}:\d{2}\.\d{2})', line)
            bitrate_match = re.search(r'bitrate=\s*([\d\.]+kbits/s)', line)
            speed_match = re.search(r'speed=\s*([\d\.]+x)', line)

            # Extract matched groups
            frame = frame_match.group(1) if frame_match else 'N/A'
            fps = fps_match.group(1) if fps_match else 'N/A'
            size = size_match.group(1) if size_match else 'N/A'
            time = time_match.group(1) if time_match else 'N/A'
            bitrate = bitrate_match.group(1) if bitrate_match else 'N/A'
            speed = speed_match.group(1) if speed_match else 'N/A'

            text = (f'**{progress_label}**:\n'
                    f'**Frame**: {frame}\n'
                    f'**FPS**: {fps}\n'
                    f'**Size**: {size}\n'
                    f'**Time**: {time}\n'
                    f'**Bitrate**: {bitrate}\n'
                    f'**Speed**: {speed}')

            if text != last_text:
                await status.edit_text(text)
                await asyncio.sleep(3)
                last_text = text

        await process.wait()
        if process.returncode != 0:
            await status.edit_text(f"Command failed with return code {process.returncode}")
        else:
            await status.delete()
    except Exception as e:
        logger.error(f"Error: {e}")
    finally:
        process = None

async def download(status, remote_path, local_path, remote_name='remote', rclone_config_path=None):
    rclone_download_command = [
        'rclone', '--config', rclone_config_path, 'copy',
        f'{remote_name}:{remote_path}', local_path, '--progress'
    ]
    await execute_command(rclone_download_command, status, "Downloading")
    return local_path if os.path.isdir(local_path) else os.path.join(local_path, os.listdir(local_path)[0])

async def merge(status, local_path, output_filename, custom_title, audio_select):
    if not os.path.exists(local_path):
        logger.error(f"The local path '{local_path}' does not exist.")
        return

    video_files = [f for f in os.listdir(local_path) if f.lower().endswith(('.mp4', '.mkv', '.avi', '.mov'))]
    if not video_files:
        logger.error("No video files found in the specified local path.")
        return

    video_files.sort()
    input_txt_path = os.path.join(local_path, 'input.txt')
    with open(input_txt_path, 'w') as input_txt:
        input_txt.writelines([f"file '{os.path.join(local_path, file)}'\n" for file in video_files])

    output_file_path = os.path.join(local_path, output_filename)
    file_title = await remove_unwanted(output_filename)
    ffmpeg_command = [
        'ffmpeg', '-loglevel', 'error', '-stats', '-f', 'concat', '-safe', '0',
        '-i', input_txt_path, '-metadata', f'title={file_title}', '-metadata:s:v:0', f'title={custom_title}',
        '-metadata:s:a:0', f'title={custom_title}', '-c', 'copy', '-map', '0:v', '-map', audio_select, '-map', '0:s',
        output_file_path
    ]
    await execute_command(ffmpeg_command, status, "Merging")
    os.remove(input_txt_path)
    return output_file_path
    
async def changeindex(status, local_path, input_file_name, output_file_name, custom_title, audio_select):
    input_file_path = os.path.join(local_path, input_file_name)
    output_file_path = os.path.join(local_path, output_file_name)
    file_title = await remove_unwanted(output_file_name)
    ffmpeg_command = [
        'ffmpeg', '-i', input_file_path, '-metadata', f'title={file_title}', '-metadata:s:v:0', f'title={custom_title}',
        '-metadata:s:a:0', f'title={custom_title}', '-metadata:s:s:0', f'title={custom_title}', '-c', 'copy', '-map', '0:v',
        '-map', audio_select, '-map', '0:s', output_file_path
    ]
    await execute_command(ffmpeg_command, status, "Changing index")
    return output_file_path

async def softmux(status, local_path, input_file_name, output_file_name, custom_title, audio_select, subtitle_file_name):
    input_file_path = os.path.join(local_path, input_file_name)
    subtitle_file_path = os.path.join(local_path, subtitle_file_name)
    output_file_path = os.path.join(local_path, output_file_name)
    file_title = await remove_unwanted(output_file_name)
    ffmpeg_command = [
        'ffmpeg', '-i', input_file_path, '-i', subtitle_file_path, '-metadata', f'title={file_title}',
        '-metadata:s:v:0', f'title={custom_title}', '-metadata:s:a:0', f'title={custom_title}', '-metadata:s:s:0', f'title={custom_title}',
        '-c:v', 'copy', '-c:a', 'copy', '-c:s', 'mov_text', '-map', '0:v', '-map', audio_select, '-map', '1', output_file_path
    ]
    await execute_command(ffmpeg_command, status, "Softmuxing")
    return output_file_path

async def upload(status, local_file, remote_path, remote_name='remote', rclone_config_path=None):
    rclone_upload_command = [
        'rclone', '--config', rclone_config_path, 'copy', local_file,
        f'{remote_name}:{remote_path}', '--progress'
    ]
    await execute_command(rclone_upload_command, status, "Uploading")

async def remove_unwanted(caption):
    try:
        return re.sub(r'\.(mkv|mp4|webm)', '', caption)
    except Exception as e:
        logger.error(e)
        return None

def cancel_download():
    global process
    if process:
        process.terminate()
        process = None
        return "Download cancelled."
    return "No active download to cancel."

def convert_size_to_mb(size_str):
    size_value, size_unit = re.findall(r'([\d\.]+)([kB|MB|GB])', size_str)[0]
    size_value = float(size_value)
    if size_unit == 'kB':
        return size_value / 1024
    elif size_unit == 'MB':
        return size_value
    elif size_unit == 'GB':
        return size_value * 1024
    return 0.0
