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

async def download(status, remote_path, local_path, remote_name='remote', rclone_config_path=None):
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
    global process

    # Build the rclone command
    rclone_download_command = [
        'rclone',
        '--config',
        rclone_config_path,
        'copy',
        f'{remote_name}:{remote_path}',
        local_path,
        '--progress'
    ]

    last_text = None

    try:
        # Run the rclone command
        process = subprocess.Popen(rclone_download_command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        # Log output in real time
        for line in process.stdout:
            line = line.strip()
            datam = refindall("Transferred:.*ETA.*", line)
            if datam is not None:
                if len(datam) > 0:
                    progress = datam[0].replace("Transferred:", "").strip().split(",")
                    percentage = progress[1].strip("% ")
                    dwdata = progress[0].strip().split('/')
                    eta = progress[3].strip().replace('ETA', '').strip()
                    text = f'**Download**: {dwdata[0].strip()} of {dwdata[1].strip()}\n**Speed**: {progress[2]} | **ETA**: {eta}'

                    if text != last_text:
                        await status.edit_text(text)
                        last_text = text

                    await asyncio.sleep(3)
        if process is not None:
          process.wait()

          if process.returncode == 0:
            await status.edit_text("Download completed successfully.")
          else:
            await status.edit_text(f"rclone command failed with return code {process.returncode}")
        else:
          await status.delete()
    except subprocess.CalledProcessError as e:
        logger.error(f"Error: {e}")
    finally:
      process = None

async def merge(status, local_path, output_filename, custom_title, audio_select):
    """
    Merge video files in a local directory using ffmpeg.

    Parameters:
    - local_path (str): The local directory containing video files.
    - output_filename (str): The name of the merged output file (default is 'merged_video.mp4').

    Returns:
    - str: The path of the merged video file.
    """
    global process

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
        '-metadata:s:a:0', f'title={custom_title}',
        '-c', 'copy',
        '-map', '0:v',  # Copy video stream
        '-map', f'{audio_select}',
        '-map', '0:s',
        output_file_path
    ]

    last_text = None

    try:
        # Run the ffmpeg command and capture the output
        process = subprocess.Popen(ffmpeg_command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        
        # Log output in real time
        for line in process.stdout:
            if process is None: # Check if the process has been cancelled
              break
            line = line.strip()

            # Parse the ffmpeg progress output
            frame_match = re.search(r'frame=\s*(\d+)', line)
            fps_match = re.search(r'fps=\s*(\d+\.?\d*)', line)
            size_match = re.search(r'size=\s*([\d\.]+(?:kB|MB|GB))', line)
            time_match = re.search(r'time=(\d{2}:\d{2}:\d{2}\.\d{2})', line)
            bitrate_match = re.search(r'bitrate=\s*([\d\.]+kbits/s)', line)
            speed_match = re.search(r'speed=\s*([\d\.]+x)', line)

            if frame_match and fps_match and size_match and time_match and bitrate_match and speed_match:
                frame = int(frame_match.group(1))
                fps = float(fps_match.group(1))
                size = convert_size_to_mb(size_match.group(1))
                time_str = time_match.group(1)
                bitrate = bitrate_match.group(1)
                speed_str = speed_match.group(1)

                text = (f'**Frame**: {frame} | **FPS**: {fps} | **Size**: {size:.2f} MB | '
                        f'**Time**: {time_str} | **Bitrate**: {bitrate} | **Speed**: {speed_str}')

                if text != last_text:
                    await status.edit_text(text)
                    last_text = text

                await asyncio.sleep(3)


        if process is not None:  # Ensure process is still running before waiting
            process.wait()

            if process.returncode == 0:
              await status.edit_text(f"Merge completed successfully `{output_file_path}`")
            else:
              await status.edit_text(f"ffmpeg command failed with return code {process.returncode}")
        else:
           await status.delete
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Error: {e}")
        return None
    finally:
        # Remove the input.txt file after merging
        os.remove(input_txt_path)
        process = None  # Clear the process reference in the end
        
async def extract(status, input_file, output_file, audio_stream, stream_select, mode_select):
    """
    Extract a specific audio stream from a video file.

    Parameters:
    - input_file (str): The path to the input video file.
    - output_file (str): The path to the output audio file.
    - audio_stream (str): Stream specifier for the audio stream to extract.

    Returns:
    - str: The path of the extracted audio file.
    """
    global process

    ffmpeg_command = [
        'ffmpeg',
        '-loglevel', 'error',
        '-i', input_file,
        '-map', audio_stream,
        f'{stream_select}', f'{mode_select}', # Copy the codec '-c:a' for audio & '-c:v' & '-c:s' for video & subs respectivly
        output_file
    ]
    last_text = None
    try:
        # Run the ffmpeg command and capture the output
        process = subprocess.Popen(ffmpeg_command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        
        # Log output in real time
        for line in process.stdout:
            if process is None: # Check if the process has been cancelled
              break
            line = line.strip()

            # Parse the ffmpeg progress output
            frame_match = re.search(r'frame=\s*(\d+)', line)
            fps_match = re.search(r'fps=\s*(\d+\.?\d*)', line)
            size_match = re.search(r'size=\s*([\d\.]+(?:kB|MB|GB))', line)
            time_match = re.search(r'time=(\d{2}:\d{2}:\d{2}\.\d{2})', line)
            bitrate_match = re.search(r'bitrate=\s*([\d\.]+kbits/s)', line)
            speed_match = re.search(r'speed=\s*([\d\.]+x)', line)

            if frame_match and fps_match and size_match and time_match and bitrate_match and speed_match:
                frame = int(frame_match.group(1))
                fps = float(fps_match.group(1))
                size = convert_size_to_mb(size_match.group(1))
                time_str = time_match.group(1)
                bitrate = bitrate_match.group(1)
                speed_str = speed_match.group(1)

                text = (f'**Frame**: {frame} | **FPS**: {fps} | **Size**: {size:.2f} MB | '
                        f'**Time**: {time_str} | **Bitrate**: {bitrate} | **Speed**: {speed_str}')

                if text != last_text:
                    await status.edit_text(text)
                    last_text = text

                await asyncio.sleep(3)


        if process is not None:  # Ensure process is still running before waiting
            process.wait()

            if process.returncode == 0:
              await status.edit_text(f"extract completed successfully `{output_file}`")
            else:
              await status.edit_text(f"ffmpeg command failed with return code {process.returncode}")
        else:
           await status.delete()

    except subprocess.CalledProcessError as e:
        logger.error(f"Error: {e}")
        return None
    finally:
       process = None

# Example usage:
# input_file = '/path/to/input_video.mp4'
# output_file = '/path/to/output_audio.mp3'
# audio_stream = 'a:0'  # Change this to the desired audio stream specifier
# extract_audio_stream(input_file, output_file, audio_stream)

async def merge_avs(status, video_file, local_path, audio_file, subtitle_file, output_filename, custom_title):
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
    global process

    output_file_path = os.path.join(local_path, output_filename)
    file_title = await remove_unwanted(output_filename)

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
        '-metadata', f'title={file_title}',
        '-metadata:s:v:0', f'title={custom_title}',
        '-metadata:s:a:0', f'title={custom_title}',
        output_file_path
    ]
    last_text = None
    try:
        # Run the ffmpeg command and capture the output
        process = subprocess.Popen(ffmpeg_command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        
        # Log output in real time
        for line in process.stdout:
            if process is None: # Check if the process has been cancelled
              break
            line = line.strip()

            # Parse the ffmpeg progress output
            frame_match = re.search(r'frame=\s*(\d+)', line)
            fps_match = re.search(r'fps=\s*(\d+\.?\d*)', line)
            size_match = re.search(r'size=\s*([\d\.]+(?:kB|MB|GB))', line)
            time_match = re.search(r'time=(\d{2}:\d{2}:\d{2}\.\d{2})', line)
            bitrate_match = re.search(r'bitrate=\s*([\d\.]+kbits/s)', line)
            speed_match = re.search(r'speed=\s*([\d\.]+x)', line)

            if frame_match and fps_match and size_match and time_match and bitrate_match and speed_match:
                frame = int(frame_match.group(1))
                fps = float(fps_match.group(1))
                size = convert_size_to_mb(size_match.group(1))
                time_str = time_match.group(1)
                bitrate = bitrate_match.group(1)
                speed_str = speed_match.group(1)

                text = (f'**Frame**: {frame} | **FPS**: {fps} | **Size**: {size:.2f} MB | '
                        f'**Time**: {time_str} | **Bitrate**: {bitrate} | **Speed**: {speed_str}')

                if text != last_text:
                    await status.edit_text(text)
                    last_text = text

                await asyncio.sleep(3)


        if process is not None:  # Ensure process is still running before waiting
            process.wait()

            if process.returncode == 0:
              await status.edit_text(f"Video, audio, and subtitle merged successfully `{output_file_path}`")
            else:
              await status.edit_text(f"ffmpeg command failed with return code {process.returncode}")
        else:
           await status.delete()

    except subprocess.CalledProcessError as e:
        logger.error(f"Error: {e}")
        return None
    finally:
       process = None

# Example usage:
# video_path = '/path/to/video.mp4'
# audio_path = '/path/to/audio.mp3'
# subtitle_path = '/path/to/subtitle.srt'
# output_path = '/path/to/output.mp4'
# merge_video_audio_subtitle(video_path, audio_path, subtitle_path, output_path)

async def merge_audio(status, video_file, local_path, audio_file, subtitle_select, output_filename, custom_title):
    """
    Merge video, audio, and subtitle files into a single output file using ffmpeg.

    Parameters:
    - video_file (str): Path to the input video file.
    - audio_file (str): Path to the input audio file.
    - output_file (str): Path to the output merged file.

    Returns:
    - str: The path of the merged file.
    """
    global process

    output_file_path = os.path.join(local_path, output_filename)
    file_title = await remove_unwanted(output_filename)

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
        '-metadata', f'title={file_title}',
        '-metadata:s:a:0', f'title={custom_title}',
        '-metadata:s:a:1', 'language=hin',  # Set language metadata for the second input audio stream
        '-disposition:a:0', 'none',  # Set the first input audio stream as not default
        '-disposition:a:1', 'default',  
        output_file_path
    ]
    last_text = None
    try:
        # Run the ffmpeg command and capture the output
        process = subprocess.Popen(ffmpeg_command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        
        # Log output in real time
        for line in process.stdout:
            if process is None: # Check if the process has been cancelled
              break
            line = line.strip()

            # Parse the ffmpeg progress output
            frame_match = re.search(r'frame=\s*(\d+)', line)
            fps_match = re.search(r'fps=\s*(\d+\.?\d*)', line)
            size_match = re.search(r'size=\s*([\d\.]+(?:kB|MB|GB))', line)
            time_match = re.search(r'time=(\d{2}:\d{2}:\d{2}\.\d{2})', line)
            bitrate_match = re.search(r'bitrate=\s*([\d\.]+kbits/s)', line)
            speed_match = re.search(r'speed=\s*([\d\.]+x)', line)

            if frame_match and fps_match and size_match and time_match and bitrate_match and speed_match:
                frame = int(frame_match.group(1))
                fps = float(fps_match.group(1))
                size = convert_size_to_mb(size_match.group(1))
                time_str = time_match.group(1)
                bitrate = bitrate_match.group(1)
                speed_str = speed_match.group(1)

                text = (f'**Frame**: {frame} | **FPS**: {fps} | **Size**: {size:.2f} MB | '
                        f'**Time**: {time_str} | **Bitrate**: {bitrate} | **Speed**: {speed_str}')

                if text != last_text:
                    await status.edit_text(text)
                    last_text = text

                await asyncio.sleep(3)


        if process is not None:  # Ensure process is still running before waiting
            process.wait()

            if process.returncode == 0:
              await status.edit_text(f"Video, audio merged successfully `{output_file_path}`")
            else:
              await status.edit_text(f"ffmpeg command failed with return code {process.returncode}")
        else:
           await status.delete()
    except subprocess.CalledProcessError as e:
        logger.error(f"Error: {e}")
        return None
    finally:
       process = None

# Example usage:
# video_path = '/path/to/video.mp4'
# audio_path = '/path/to/audio.mp3'
# output_path = '/path/to/output.mp4'
# merge_video_audio_subtitle(video_path, audio_path, output_path)

async def encode(status, local_path, input_file_name, output_file_name, custom_title):
    """
    Encode a video file to HEVC x265 720p using ffmpeg.

    Parameters:
    - input_file (str): The path to the input video file.
    - output_file (str): The path to the output encoded video file.

    Returns:
    - str: The path of the encoded video file.
    """
    input_file_path = os.path.join(local_path, input_file_name)
    output_file_path = os.path.join(local_path, output_file_name)
    file_title = await remove_unwanted(output_file_name)



    ffmpeg_command = [
        'ffmpeg',
        '-i', input_file_path,
        '-c:v', 'libx265',
        '-preset', 'medium',
        '-crf', '22',
        '-vf', 'scale=-1:720',
        '-metadata', f'title={file_title}',
        '-metadata:s:v:0', f'title={custom_title}',
        '-c:a', 'aac',
        '-b:a', '128k',
        output_file_path
    ]
    last_text = None
    try:
        # Run the ffmpeg command and capture the output
        process = subprocess.Popen(ffmpeg_command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        
        # Log output in real time
        for line in process.stdout:
            if process is None: # Check if the process has been cancelled
              break
            line = line.strip()

            # Parse the ffmpeg progress output
            frame_match = re.search(r'frame=\s*(\d+)', line)
            fps_match = re.search(r'fps=\s*(\d+\.?\d*)', line)
            size_match = re.search(r'size=\s*([\d\.]+(?:kB|MB|GB))', line)
            time_match = re.search(r'time=(\d{2}:\d{2}:\d{2}\.\d{2})', line)
            bitrate_match = re.search(r'bitrate=\s*([\d\.]+kbits/s)', line)
            speed_match = re.search(r'speed=\s*([\d\.]+x)', line)

            if frame_match and fps_match and size_match and time_match and bitrate_match and speed_match:
                frame = int(frame_match.group(1))
                fps = float(fps_match.group(1))
                size = convert_size_to_mb(size_match.group(1))
                time_str = time_match.group(1)
                bitrate = bitrate_match.group(1)
                speed_str = speed_match.group(1)

                text = (f'**Frame**: {frame} | **FPS**: {fps} | **Size**: {size:.2f} MB | '
                        f'**Time**: {time_str} | **Bitrate**: {bitrate} | **Speed**: {speed_str}')

                if text != last_text:
                    await status.edit_text(text)
                    last_text = text

                await asyncio.sleep(3)


        if process is not None:  # Ensure process is still running before waiting
            process.wait()

            if process.returncode == 0:
              await status.edit_text(f"Encoding completed successfully `{output_file_path}`")
            else:
              await status.edit_text(f"ffmpeg command failed with return code {process.returncode}")
        else:
           await status.delete()

    except subprocess.CalledProcessError as e:
        logger.error(f"Error: {e}")
        return None


async def upload(status, local_file, remote_path, remote_name='remote', rclone_config_path=None):
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
    global process

    # Build the rclone command for uploading
    rclone_upload_command = [
        'rclone',
        '--config',
        rclone_config_path,
        'copy',
        local_file,
        f'{remote_name}:{remote_path}',
        '--progress'
    ]
    last_text = None
    try:
        # Run the rclone command
        process = subprocess.Popen(rclone_upload_command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        # Log output in real time
        for line in process.stdout:
          line = line.strip()
          datam = refindall("Transferred:.*ETA.*", line)
          if datam is not None:
            if len(datam) > 0:
              progress = datam[0].replace("Transferred:", "").strip().split(",")
              percentage= progress[1].strip("% ")
              dwdata = progress[0].strip().split('/')
              eta = progress[3].strip().replace('ETA', '').strip()
              text =f'**Upload**: {dwdata[0].strip()} of {dwdata[1].strip()}\n**Speed**: {progress[2]} | **ETA**: {eta}"'

              if text != last_text:
                await status.edit_text(text)
                last_text = text

                await asyncio.sleep(3)

        if process is not None:
          process.wait()

          if process.returncode == 0:
            await status.edit_text("Upload completed successfully.")
          else:
            await status.edit_text(f"rclone command failed with return code {process.returncode}")
        else:
          await status.delete()
    except subprocess.CalledProcessError as e:
        logger.error(f"Error: {e}")
    finally:
      process = None

async def remove_unwanted(caption):
    try:
        # Remove .mkv and .mp4 extensions if present
        cleaned_caption = re.sub(r'\.mkv|\.mp4|\.webm', '', caption)
        return cleaned_caption
    except Exception as e:
        logger.error(e)
        return None

def cancel_download():
    global process
    if process is not None:
        process.terminate()
        process = None
        return "Download cancelled."
    else:
        return "No active download to cancel."

def convert_size_to_mb(size_str):
    """Convert size string (e.g., 63488kB) to MB."""
    if 'kB' in size_str:
        size_in_kb = float(size_str.replace('kB', ''))
        return size_in_kb / 1024
    elif 'MB' in size_str:
        return float(size_str.replace('MB', ''))
    elif 'GB' in size_str:
        size_in_gb = float(size_str.replace('GB', ''))
        return size_in_gb * 1024
    return 0.0
