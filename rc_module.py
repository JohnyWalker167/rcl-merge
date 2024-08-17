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
    downloaded_path = None
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
                    dwdata = progress[0].strip().split('/')
                    eta = progress[3].strip().replace('ETA', '').strip()
                    text = f'**Downloading**:\n {dwdata[0].strip()} of {dwdata[1].strip()}\n**Speed**: {progress[2]} | **ETA**: {eta}'

                    if text != last_text:
                        await status.edit_text(text)
                        await asyncio.sleep(3)
                        last_text = text
                        
        if process is not None:
          process.wait()

          if process.returncode == 0:
              # Determine the downloaded path
              if os.path.isdir(local_path):
                  downloaded_path = local_path
              else:
                  downloaded_files = os.listdir(local_path)
                  if len(downloaded_files) == 1:
                      downloaded_path = os.path.join(local_path, downloaded_files[0])
                  else:
                      downloaded_path = local_path  
              await status.delete()
          else:
            await status.edit_text(f"rclone command failed with return code {process.returncode}")
        else:
          await status.delete()
    except subprocess.CalledProcessError as e:
        logger.error(f"Error: {e}")
    finally:
      process = None
    return downloaded_path

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

                text = (f'**Merging**:\n**Frame**: {frame} | **FPS**: {fps} | **Size**: {size:.2f} MB | '
                        f'**Time**: {time_str} | **Bitrate**: {bitrate} | **Speed**: {speed_str}')

                if text != last_text:
                    await status.edit_text(text)
                    await asyncio.sleep(3)
                    last_text = text
                    
        if process is not None:  # Ensure process is still running before waiting
            process.wait()

            if process.returncode == 0:
              await status.delete()
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
        return output_file_path
        

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

async def changeindex(status, local_path, input_file_name, output_file_name, custom_title, audio_select):
   
    input_file_path = os.path.join(local_path, input_file_name)
    output_file_path = os.path.join(local_path, output_file_name)
    file_title = await remove_unwanted(output_file_name)

    ffmpeg_command = [
        'ffmpeg',
        '-i', input_file_path,
        '-metadata', f'title={file_title}',
        '-metadata:s:v:0', f'title={custom_title}',
        '-metadata:s:a:0', f'title={custom_title}',
        '-metadata:s:s:0', f'title={custom_title}',
        '-c', 'copy',
        '-map', '0:v',  # Copy video stream
        '-map', f'{audio_select}', # Copy audio stream
        '-map', '0:s', # Copy sub stream
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
              await status.edit_text(f"Change Index successfully `{output_file_path}`")
            else:
              await status.edit_text(f"ffmpeg command failed with return code {process.returncode}")
        else:
           await status.delete
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Error: {e}")
        return None
    finally:
        process = None  # Clear the process reference in the end

async def softmux(status, local_path, input_file_name, output_file_name, custom_title, audio_select, subtitle_file_name):
   
    input_file_path = os.path.join(local_path, input_file_name)
    subtitle_file_path = os.path.join(local_path, subtitle_file_name)
    output_file_path = os.path.join(local_path, output_file_name)
    file_title = await remove_unwanted(output_file_name)

    ffmpeg_command = [
        'ffmpeg',
        '-i', input_file_path,
        '-i', subtitle_file_path,  # Include the SRT subtitle file
        '-metadata', f'title={file_title}',
        '-metadata:s:v:0', f'title={custom_title}',
        '-metadata:s:a:0', f'title={custom_title}',
        '-metadata:s:s:0', f'title={custom_title}',
        '-c:v', 'copy',  # Copy video stream
        '-c:a', 'copy',  # Copy audio stream
        '-c:s', 'mov_text',  # Use mov_text codec for the subtitle
        '-map', '0:v',  # Map the video stream
        '-map', f'{audio_select}',  # Map the selected audio stream
        '-map', '0:s',  # Map the original subtitle stream (if any)
        '-map', '1',  # Map the new subtitle file
        output_file_path
    ]

    last_text = None

    try:
        # Run the ffmpeg command and capture the output
        process = subprocess.Popen(ffmpeg_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        # Log output in real-time
        for line in process.stdout:
            if process is None:  # Check if the process has been cancelled
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

        # Capture any errors from stderr
        stderr_output = process.stderr.read()

        if process is not None:  # Ensure process is still running before waiting
            process.wait()

            if process.returncode == 0:
                await status.edit_text(f"Change Index successfully `{output_file_path}`")
            else:
                error_message = f"ffmpeg command failed with return code {process.returncode}. Error details: {stderr_output}"
                await status.edit_text(error_message)
        else:
            await status.delete()

    except subprocess.CalledProcessError as e:
        logger.error(f"Error: {e}")
        return None
    finally:
        process = None  # Clear the process reference in the end
        
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
              dwdata = progress[0].strip().split('/')
              eta = progress[3].strip().replace('ETA', '').strip()
              text =f'**Uploaded**:\n {dwdata[0].strip()} of {dwdata[1].strip()}\n**Speed**: {progress[2]} | **ETA**: {eta}"'

              if text != last_text:
                await status.edit_text(text)
                await asyncio.sleep(3)
                last_text = text
                
        if process is not None:
          process.wait()

          if process.returncode == 0:
            await status.delete()
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
