from flask import Flask, render_template, send_from_directory
import os
from pathlib import Path, PosixPath

app = Flask(__name__)


tmux_sessions = ["../"+session for session in open('sessions.txt','r').read().splitlines()]

steps = ["download", "data cleaning", "bicleaner", ""]


def get_session_data():
    processes = []
    sessions = {}
    for tmux_session in tmux_sessions:
        processes = sorted(Path(tmux_session).iterdir(), key=os.path.getmtime)
        for process in processes:
            # Probably there is a cleaner way of doing this, it takes too long now
            # if os.path.isdir(process):
            #     processes.remove(process)
            #     subprocesses = sorted(Path(process).iterdir(), key=os.path.getmtime)
            #     # for subprocess in subprocesses:
            #     #     if os.path.isdir(process):
            #     #         subsubprocesses = sorted(Path(process).iterdir(), key=os.path.getmtime)
            #     #         processes.extend(subsubprocesses)
            #     # else:
            #     processes.extend(subprocesses)
            # # if file is empty:
            if os.stat(process).st_size == 0:
                print(process, ": removed from log because it is empty")
                processes.remove(process)
            if process.stem.endswith('log'): #This will get rid of GPU performance
                processes.remove(process)
        sessions[tmux_session]=processes
    return sessions

def check_process_status(process_path):
    if os.path.isdir(process_path):
        return "Directory", None
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

@app.route("/")
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
    logs_path = "/scratch/project_462000088/members/degibert/data/logs/"
    full_path = os.path.join(logs_path,filename)

    try:
        with open(full_path, "r") as file:
            content = file.read()
        return content, 200, {'Content-Type': 'text/plain; charset=utf-8'}
    except Exception as e:
        return f"Error reading file: {e}", 400


if __name__ == "__main__":
    app.run(debug=True)
