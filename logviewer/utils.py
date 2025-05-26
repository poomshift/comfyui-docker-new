import os
import threading
import time
import zipfile
import io
import re
import html
from datetime import datetime

# Thread-safe log buffer and lock
log_buffer = []
log_lock = threading.Lock()

def get_installed_custom_nodes():
    """Get a list of installed custom nodes from start.sh"""
    custom_nodes = []
    try:
        start_sh_paths = ['/start.sh', './start.sh', '/workspace/start.sh', os.path.join(os.path.dirname(__file__), 'start.sh')]
        start_sh_content = None
        for path in start_sh_paths:
            if os.path.exists(path):
                with open(path, 'r') as file:
                    start_sh_content = file.read()
                break
        if not start_sh_content:
            print("Warning: start.sh not found in expected locations")
            return []
        pattern = r'git clone --depth=1 (https://github.com/[^/]+/([^\.]+)\.git)'
        matches = re.findall(pattern, start_sh_content)
        for match in matches:
            repo_url, repo_name = match
            repo_name_clean = repo_url.split('/')[-1].replace('.git', '')
            custom_nodes.append({
                'name': repo_name_clean,
                'path': f"/workspace/ComfyUI/custom_nodes/{repo_name_clean}",
                'version': "Installed",
                'url': repo_url
            })
    except Exception as e:
        print(f"Error parsing custom nodes from start.sh: {e}")
    return sorted(custom_nodes, key=lambda x: x['name'].lower())

def get_installed_models():
    """Get a list of installed models from models_config.json"""
    models = {}
    try:
        config_paths = [
            '/workspace/models_config.json',
            './models_config.json',
            os.path.join(os.path.dirname(__file__), 'models_config.json')
        ]
        model_config = None
        for path in config_paths:
            if os.path.exists(path):
                import json
                with open(path, 'r') as file:
                    model_config = json.load(file)
                break
        if not model_config:
            print("Warning: models_config.json not found in expected locations")
            return {}
        comfyui_models_dir = '/workspace/ComfyUI/models'
        if not os.path.exists(comfyui_models_dir):
            print(f"Note: {comfyui_models_dir} doesn't exist yet. Will show models from config only.")
        for category, urls in model_config.items():
            if urls:
                model_files = []
                for url in urls:
                    filename = url.split('/')[-1]
                    model_files.append({
                        'name': filename,
                        'path': f"/workspace/ComfyUI/models/{category}/{filename}",
                        'url': url
                    })
                if model_files:
                    model_files.sort(key=lambda x: x['name'].lower())
                    models[category] = model_files
    except Exception as e:
        print(f"Error parsing models from models_config.json: {e}")
    return dict(sorted(models.items()))

def get_current_logs():
    """Get the current logs from the buffer with Docker-style formatting"""
    with log_lock:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        header = f"<div class='log-line'><span class='log-timestamp'>{timestamp}</span><span class='log-info'>Log Viewer - Last {len(log_buffer)} lines</span></div>\n"
        if log_buffer:
            formatted_logs = []
            prev_line = None
            for line in log_buffer:
                if line != prev_line:
                    formatted_line = format_log_line(line)
                    formatted_logs.append(formatted_line)
                prev_line = line
            return header + '\n'.join(formatted_logs)
        else:
            return header + "<div class='log-line'><span class='log-info'>No logs yet.</span></div>"

def format_log_line(line):
    """Format a log line to match Docker container log style"""
    timestamp_match = re.search(r'^\[([\d\-\s:]+)\]', line)
    if timestamp_match:
        timestamp = timestamp_match.group(1)
        content = line[len(timestamp_match.group(0)):].strip()
    else:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        content = line
    css_class = 'log-info'
    if re.search(r'error|exception|fail|critical', content, re.IGNORECASE):
        css_class = 'log-error'
    elif re.search(r'warn|caution', content, re.IGNORECASE):
        css_class = 'log-warning'
    return f"<div class='log-line'><span class='log-timestamp'>{timestamp}</span><span class='{css_class}'>{html.escape(content)}</span></div>"

def tail_log_file(socketio_emit=None):
    """Continuously tail the log file and update the buffer. Optionally emit logs via socketio_emit callback."""
    log_file = os.path.join('logs', 'comfyui.log')
    if not os.path.exists(log_file):
        os.makedirs('logs', exist_ok=True)
        open(log_file, 'a').close()
    def follow(file_path):
        current_position = 0
        while True:
            try:
                with open(file_path, 'r') as file:
                    file_size = os.path.getsize(file_path)
                    if file_size < current_position:
                        current_position = 0
                    file.seek(current_position)
                    new_lines = file.readlines()
                    if new_lines:
                        current_position = file.tell()
                        for line in new_lines:
                            yield line
                    else:
                        time.sleep(0.1)
            except Exception as e:
                print(f"Error following log file: {e}")
                time.sleep(1)
    try:
        with open(log_file, 'r') as file:
            content = file.readlines()
            processed_content = []
            content = content[-500:] if len(content) > 500 else content
            prev_line = None
            for line in content:
                stripped_line = line.strip()
                if stripped_line and stripped_line != prev_line:
                    processed_content.append(stripped_line)
                prev_line = stripped_line
            with log_lock:
                log_buffer.clear()
                log_buffer.extend(processed_content)
            if socketio_emit:
                socketio_emit('logs', {'logs': get_current_logs()})
        prev_line = None
        for line in follow(log_file):
            stripped_line = line.strip()
            if stripped_line and stripped_line != prev_line:
                with log_lock:
                    log_buffer.append(stripped_line)
                    if len(log_buffer) > 500:
                        log_buffer.pop(0)
                if socketio_emit:
                    socketio_emit('new_log_line', {'line': format_log_line(stripped_line)})
            prev_line = stripped_line
    except Exception as e:
        print(f"Error tailing log file: {e}")
        time.sleep(5)

def create_output_zip():
    """Create a zip file of the ComfyUI output directory"""
    output_dir = os.path.join('/workspace', 'ComfyUI', 'output')
    memory_file = io.BytesIO()
    with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(output_dir):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, output_dir)
                zf.write(file_path, arcname)
    memory_file.seek(0)
    return memory_file 