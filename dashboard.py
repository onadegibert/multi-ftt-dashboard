from flask import Flask, render_template, request, url_for, send_file
import os
from pathlib import Path
from werkzeug.utils import safe_join

app = Flask(__name__)

# Assume your sessions.txt and other paths are properly set up
tmux_sessions = ["../" + session for session in open('sessions.txt', 'r').read().splitlines()]
logs_path = "/scratch/project_462000088/members/degibert/data/logs/"

def check_process_status(process_path):
    if process_path.is_dir():
        return "Directory", get_files_in_directory(process_path)
    else:
        try:
            with open(process_path, "r") as file:
                last_line = file.readlines()[-1]
                if "error" in last_line.lower():
                    return "Failed", last_line
                else:
                    return "Completed", None
        except Exception as e:
            return "Empty", str(e)

def get_files_in_directory(directory_path):
    files_status = []
    for item in Path(directory_path).iterdir():
        if item.is_dir():
            continue
        status, error = check_process_status(item)
        files_status.append({"name": item.name, "status": status, "error": error, "path": str(item)})
    return files_status

def get_session_data():
    processes = []
    sessions = {}
    for tmux_session in tmux_sessions:
        processes = sorted(Path(tmux_session).iterdir(), key=os.path.getmtime)
        for process in processes:
            if os.stat(process).st_size == 0:
                print(process, ": removed from log because it is empty")
                processes.remove(process)
            if process.stem.endswith('log'): #This will get rid of GPU performance
                processes.remove(process)
        sessions[tmux_session] = processes
    return sessions

@app.route('/image/<path:filename>')
def custom_static(filename):
    base_path = '/scratch/project_462000088/members/degibert/data/logs/images'
    # Ensure the path is safe to prevent path traversal attacks
    safe_path = safe_join(base_path, filename)
    if not os.path.exists(safe_path):
        abort(404)  # Not found if the path doesn't exist
    return send_file(safe_path, mimetype='image/png')

@app.route("/training_curves")
def training_curves():
    session_images = {}
    for session in tmux_sessions:
        session_name = session.replace("../dec23/","").replace("../dev23/","").replace("/","_")
        image_name = f"{session_name}.png"
        # Use the custom route to create a URL for the image
        session_images[session_name] = url_for('custom_static', filename=image_name)
    return render_template("training_curves.html", session_images=session_images)

@app.route("/gpu_performance")
def gpu_performance():
    # Placeholder for GPU performance section
    return "to do"

@app.route("/dashboard")
def dashboard():
    sessions = get_session_data()
    process_data = {}

    for session in sessions:
        process_list = []
        for process in sessions[session]:
            status, error = check_process_status(process)
            process_list.append({"process": process.stem, "status": status, "error": error, "path": str(process)})
        process_data[session.replace("../dec23/","").replace("../dev23/","")] = process_list

    return render_template("dashboard.html", process_data=process_data)


@app.route('/<path:filename>')
def logs(filename):
    full_path = os.path.join(logs_path,filename)

    try:
        with open(full_path, "r") as file:
            content = file.read()
        return content, 200, {'Content-Type': 'text/plain; charset=utf-8'}
    except Exception as e:
        return f"Error reading file: {e}", 400


if __name__ == "__main__":
    app.run(debug=True)