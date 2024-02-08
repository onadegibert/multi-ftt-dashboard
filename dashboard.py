from flask import Flask, render_template, request, url_for, send_file
import os, glob
from pathlib import Path
from werkzeug.utils import safe_join
import pandas as pd
from datetime import datetime

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

def analyze_gpu_log(log):
    if os.path.isfile(log):
        print(log)
        # Convert the log data into a pandas DataFrame
        df = pd.read_csv(log) 
        
        multiple_jobs = df['device'].isin(["new job started"]).any()
        if multiple_jobs:
            # To remove "new job started" lines
            #df = df_og[~df_og['device'].str.contains("new job started")]
            # To keep only the last job
            last_job = df[df['device'] == "new job started"].index[-1]
            df.drop(df.index[:last_job+1], inplace=True)
        df['device'] = df['device'].str.split('\t', expand=True)[0]
        df['device'] = pd.to_datetime(df['device'], format='%Y-%m-%d_%H:%M:%S')
        
        # Calculate total run time
        run_time_seconds = (df['device'].iloc[-1] - df['device'].iloc[0]).total_seconds()

        # Calculate average GPU use
        avg_gpu_use = df['GPU use (%)'].mean()

        # Calculate total energy counter
        total_energy_counter = df['Energy counter'].sum()

        # Calculate total accumulated energy
        total_accumulated_energy = df['Accumulated Energy (uJ)'].sum()

        return run_time_seconds, avg_gpu_use, total_energy_counter, total_accumulated_energy
    else: # If the log file doesn't exist
        print(log+" doesn't exist")
        return

def add_gpu_stats(gpu_stats_list):
    total_run_time_seconds = 0
    avg_gpu_use = 0
    total_energy_counter = 0
    total_accumulated_energy = 0

    for curr_gpu_stats in gpu_stats_list:
        current_run_time, current_avg_gpu_use, current_energy_counter, current_accumulated_energy = curr_gpu_stats
        
        total_run_time_seconds += current_run_time
        avg_gpu_use += current_avg_gpu_use
        total_energy_counter += current_energy_counter
        total_accumulated_energy += current_accumulated_energy
    
    # Convert total_run_time_seconds back to hours and minutes
    total_run_time = f"{total_run_time_seconds // 3600} hours, {(total_run_time_seconds % 3600) // 60} minutes"
    
    # For avg_gpu_use, you might want to calculate the average over all entries, not just sum them
    avg_gpu_use = round(avg_gpu_use / len(gpu_stats_list) if gpu_stats_list else 0, 2)
    return total_run_time, avg_gpu_use, total_energy_counter, total_accumulated_energy

@app.route("/gpu_performance")
def gpu_performance():
    sessions_gpu_stats = {}  # Dictionary to hold GPU stats for each session
    for session in tmux_sessions:
        session_name = session.replace("../dec23/","").replace("../dev23/","").replace("/","_")
        session_gpu_stats = []  # List to hold GPU stats for each log file in the session

        # Process translate logs
        translate_gpu_stats = []
        for log in glob.glob(session+"/translate_corpus/*/*gpu"):
            filename = log.replace(session,"").replace("/translate_corpus/","").replace("/","_")
            gpu_stats = analyze_gpu_log(log)
            if gpu_stats:  # Ensure gpu_stats is not None
                translate_gpu_stats.append(gpu_stats)
        total_translate = add_gpu_stats(translate_gpu_stats)
        session_gpu_stats.append(("translate", total_translate))

        # Process score logs
        score_gpu_stats = []
        # Process .gpu logs
        for log in glob.glob(session+"/*.gpu"):
            filename = os.path.basename(log)
            gpu_stats = analyze_gpu_log(log)
            task = "score" if "score" in filename else "finetune" if "finetune" in filename else "train_opustrainer" if "opustrainer" in filename else "train_student"
            if gpu_stats:
                if task == "score":
                    score_gpu_stats.append(gpu_stats)
                else:
                    session_gpu_stats.append((task, add_gpu_stats([gpu_stats])))
        total_score = add_gpu_stats(score_gpu_stats)
        session_gpu_stats.append(("score", total_score))

        # Process eval logs
        eval_gpu_stats = []
        for log in glob.glob(session+"/eval/*gpu"):
            filename = os.path.basename(log)
            gpu_stats = analyze_gpu_log(log)
            if gpu_stats:
                eval_gpu_stats.append(gpu_stats)

        total_eval = add_gpu_stats(eval_gpu_stats)
        session_gpu_stats.append(("eval", total_eval))
        
        if session_gpu_stats:
            sessions_gpu_stats[session_name] = session_gpu_stats

    # Pass the GPU stats data to the HTML template
    return render_template('gpu_performance.html', sessions_gpu_stats=sessions_gpu_stats)

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