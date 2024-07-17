import re
import os
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

async def download(remote_path, local_path, remote_name='remote', rclone_config_path=None):
    """
    Download files from a cloud path to a local path using rclone.

    Parameters:
    - remote_path (str): The path on the cloud storage.
    - local_path (str): The local directory where files will be downloaded.
    - remote_name (str): The name of the rclone remote (default is 'remote').
    - rclone_config_path (str): The path to the rclone configuration file.

    Returns:
    - None
    """
    # Build the rclone command
    rclone_command = [
        'rclone',
        '--config',
        rclone_config_path,
        'copy',
        f'{remote_name}:{remote_path}',
        local_path
    ]

    try:
        # Run the rclone command
        subprocess.run(rclone_command, check=True)
        logger.info("Download completed successfully.")
    except subprocess.CalledProcessError as e:
        logger.error(f"Error: {e}")

async def merge(local_path, output_filename, custom_title, audio_select):
    """
    Merge video files in a local directory using ffmpeg.

    Parameters:
    - local_path (str): The local directory containing video files.
    - output_filename (str): The name of the merged output file (default is 'merged_video.mp4').

    Returns:
    - str: The path of the merged video file.
    """
    # Ensure the local path exists
    if not os.path.exists(local_path):
        logger.error(f"The local path '{local_path}' does not exist.")
        return

    # Get a list of video files in the local directory
    video_files = [f for f in os.listdir(local_path) if f.lower().endswith(('.mp4', '.mkv', '.avi', '.mov'))]
    
    if not video_files:
        logger.error("No video files found in the specified local path.")
        return
    video_files.sort()

    # Create the input.txt file
    input_txt_path = os.path.join(local_path, 'input.txt')
    with open(input_txt_path, 'w') as input_txt:
        input_txt.writelines([f"file '{os.path.join(local_path, file)}'\n" for file in video_files])


    # Build the ffmpeg command
    output_file_path = os.path.join(local_path, output_filename)
    file_title = await remove_unwanted(output_filename)
    ffmpeg_command = [
        'ffmpeg',
        '-loglevel','error','-stats',
        '-f', 'concat',
        '-safe', '0',
        '-i', input_txt_path,
        '-metadata', f'title={file_title}',
        '-metadata:s:v:0', f'title={custom_title}',
        '-c', 'copy',
        '-map', '0:v',  # Copy video stream
        '-map', f'{audio_select}',
        '-map', '0:s',
        output_file_path
    ]

    try:
        # Run the ffmpeg command and capture the output
        result = subprocess.run(ffmpeg_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        # Log the command output and error
        if result.stdout:
            logger.info(f"ffmpeg stdout: {result.stdout}")
        if result.stderr:
            logger.error(f"ffmpeg stderr: {result.stderr}")

        if result.returncode == 0:
            logger.info("Video files merged successfully.")
            return output_file_path
        else:
            logger.error(f"ffmpeg command failed with return code {result.returncode}")
            return None
    except subprocess.CalledProcessError as e:
        logger.error(f"Error: {e}")
        return None
    finally:
        # Remove the input.txt file after merging
        os.remove(input_txt_path)
        
async def extract(input_file, output_file, audio_stream, stream_select, mode_select):
    """
    Extract a specific audio stream from a video file.

    Parameters:
    - input_file (str): The path to the input video file.
    - output_file (str): The path to the output audio file.
    - audio_stream (str): Stream specifier for the audio stream to extract.

    Returns:
    - str: The path of the extracted audio file.
    """
    ffmpeg_command = [
        'ffmpeg',
        '-loglevel', 'error',
        '-i', input_file,
        '-map', audio_stream,
        f'{stream_select}', f'{mode_select}', # Copy the codec '-c:a' for audio & '-c:v' & '-c:s' for video & subs respectivly
        output_file
    ]

    try:
        subprocess.run(ffmpeg_command, check=True)
        logger.info("Stream extracted successfully.")
        return output_file
    except subprocess.CalledProcessError as e:
        logger.error(f"Error: {e}")
        return None

# Example usage:
# input_file = '/path/to/input_video.mp4'
# output_file = '/path/to/output_audio.mp3'
# audio_stream = 'a:0'  # Change this to the desired audio stream specifier
# extract_audio_stream(input_file, output_file, audio_stream)

async def merge_avs(video_file, audio_file, subtitle_file, output_file, custom_title):
    """
    Merge video, audio, and subtitle files into a single output file using ffmpeg.

    Parameters:
    - video_file (str): Path to the input video file.
    - audio_file (str): Path to the input audio file.
    - subtitle_file (str): Path to the input subtitle file.
    - output_file (str): Path to the output merged file.

    Returns:
    - str: The path of the merged file.
    """
    ffmpeg_command = [
        'ffmpeg',
        '-loglevel', 'error',
        '-i', video_file,
        '-i', audio_file,
        '-i', subtitle_file,
        '-c:v', 'copy',  # Copy video codec
        '-c:a', 'copy',  # Copy audio codec
        '-map', '0:v:0',  # Map video stream from the first input
        '-map', '1:a:0',  # Map audio stream from the second input
        '-map', '2:s:0',  # Map subtitle stream from the third input
        '-metadata', f'title={custom_title}',  # Set custom title
        output_file
    ]

    try:
        subprocess.run(ffmpeg_command, check=True)
        logger.info("Video, audio, and subtitle merged successfully.")
        return output_file
    except subprocess.CalledProcessError as e:
        logger.error(f"Error: {e}")
        return None

# Example usage:
# video_path = '/path/to/video.mp4'
# audio_path = '/path/to/audio.mp3'
# subtitle_path = '/path/to/subtitle.srt'
# output_path = '/path/to/output.mp4'
# merge_video_audio_subtitle(video_path, audio_path, subtitle_path, output_path)

async def merge_audio(video_file, audio_file, subtitle_select, output_file, custom_title):
    """
    Merge video, audio, and subtitle files into a single output file using ffmpeg.

    Parameters:
    - video_file (str): Path to the input video file.
    - audio_file (str): Path to the input audio file.
    - output_file (str): Path to the output merged file.

    Returns:
    - str: The path of the merged file.
    """
    ffmpeg_command = [
        'ffmpeg',
        '-loglevel', 'error',
        '-i', video_file,
        '-i', audio_file,
        '-c:v', 'copy',  # Copy video codec
        '-c:a', 'copy',  # Copy audio codec
        '-map', '0:v:0',  # Map video stream from the first input
        '-map', '0:a:0',  # Map audio stream from the first input
        '-map', '1:a:0',  # Map audio stream from the second input
        '-map', f'{subtitle_select}',  # Map subtitle stream from the third input
        '-metadata', f'title={custom_title}',  # Set custom title
        '-metadata:s:a:1', 'language=hin',  # Set language metadata for the second input audio stream
        '-disposition:a:0', 'none',  # Set the first input audio stream as not default
        '-disposition:a:1', 'default',  
        output_file
    ]

    try:
        subprocess.run(ffmpeg_command, check=True)
        logger.info("Video, audio merged successfully.")
        return output_file
    except subprocess.CalledProcessError as e:
        logger.error(f"Error: {e}")
        return None

# Example usage:
# video_path = '/path/to/video.mp4'
# audio_path = '/path/to/audio.mp3'
# output_path = '/path/to/output.mp4'
# merge_video_audio_subtitle(video_path, audio_path, output_path)


async def upload(local_file, remote_path, remote_name='remote', rclone_config_path=None):
    """
    Upload a local file to a specified path on a cloud storage using rclone.

    Parameters:
    - local_file (str): The local file to upload.
    - remote_path (str): The path on the cloud storage.
    - remote_name (str): The name of the rclone remote (default is 'remote').
    - rclone_config_path (str): The path to the rclone configuration file.

    Returns:
    - None
    """
    # Build the rclone command for uploading
    rclone_upload_command = [
        'rclone',
        '--config',
        rclone_config_path,
        'copy',
        local_file,
        f'{remote_name}:{remote_path}'
    ]

    try:
        # Run the rclone command for uploading
        subprocess.run(rclone_upload_command, check=True)
        logger.info("Upload completed successfully.")
    except subprocess.CalledProcessError as e:
        logger.error(f"Error: {e}")


async def remove_unwanted(caption):
    try:
        # Remove .mkv and .mp4 extensions if present
        cleaned_caption = re.sub(r'\.mkv|\.mp4|\.webm', '', caption)
        return cleaned_caption
    except Exception as e:
        logger.error(e)
        return None
