#!/opt/anaconda3/bin/python3
import os
import time
import cv2
import numpy as np
import webbrowser
import threading
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_file, send_from_directory
from werkzeug.utils import secure_filename
import face_recognition

from gallery_manager import GalleryManager, REPORT_EXCEL_FILE, GALLERY_DIR

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max video upload
app.config['UPLOAD_FOLDER'] = os.path.abspath('uploads')
app.config['OUTPUT_FOLDER'] = os.path.abspath('output_videos')
app.config['GALLERY_FOLDER'] = os.path.abspath(GALLERY_DIR)
app.config['KNOWN_FACES_FOLDER'] = os.path.abspath('known_faces')

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['OUTPUT_FOLDER'], exist_ok=True)
os.makedirs(app.config['GALLERY_FOLDER'], exist_ok=True)
os.makedirs(app.config['KNOWN_FACES_FOLDER'], exist_ok=True)

# Thread-safe dictionary tracking real-time background jobs
active_jobs = {}
jobs_lock = threading.Lock()


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/gallery_thumb/<filename>')
def serve_gallery_thumb(filename):
    return send_from_directory(app.config['GALLERY_FOLDER'], filename)


@app.route('/download_video/<filename>')
def serve_annotated_video(filename):
    return send_from_directory(app.config['OUTPUT_FOLDER'], filename, as_attachment=True)


@app.route('/download_report')
def download_report():
    gm = GalleryManager(app.config['GALLERY_FOLDER'])
    report_path = gm.export_excel_report(REPORT_EXCEL_FILE)
    if os.path.exists(report_path):
        return send_file(os.path.abspath(report_path), as_attachment=True, download_name="cross_video_matches.xls")
    return jsonify({"error": "Report not found"}), 404


@app.route('/api/gallery', methods=['GET'])
def get_gallery():
    gm = GalleryManager(app.config['GALLERY_FOLDER'])
    people_data = []
    for p in gm.people:
        thumb_name = os.path.basename(p.get("thumbnail_path", ""))
        people_data.append({
            "id": p["id"],
            "thumbnail_url": f"/gallery_thumb/{thumb_name}" if thumb_name else None,
            "first_seen_video": p.get("first_seen_video", ""),
            "video_detections": p.get("video_detections", {}),
            "total_videos": len(p.get("video_detections", {})),
            "is_cross_match": len(p.get("video_detections", {})) > 1
        })
    return jsonify({
        "people": people_data,
        "total_count": len(people_data),
        "cross_matches_count": sum(1 for p in people_data if p["is_cross_match"])
    })


@app.route('/api/reset_gallery', methods=['POST'])
def reset_gallery():
    gm = GalleryManager(app.config['GALLERY_FOLDER'])
    gm.reset_gallery()
    return jsonify({"success": True, "message": "Gallery has been reset."})


def process_video_worker(job_id, video_path, filename, save_annotated):
    """
    Background worker that runs frame-by-frame face recognition
    and updates active_jobs[job_id] with real-time progress.
    """
    start_time = time.time()
    try:
        gm = GalleryManager(app.config['GALLERY_FOLDER'])

        video_capture = cv2.VideoCapture(video_path)
        if not video_capture.isOpened():
            with jobs_lock:
                active_jobs[job_id] = {"status": "error", "error": "Could not open video file."}
            return

        fps = video_capture.get(cv2.CAP_PROP_FPS)
        if not fps or fps <= 0 or np.isnan(fps):
            fps = 25.0
        frame_width = int(video_capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        frame_height = int(video_capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_frames = int(video_capture.get(cv2.CAP_PROP_FRAME_COUNT))
        if total_frames <= 0:
            total_frames = 1

        annotated_filename = None
        video_writer = None
        if save_annotated:
            annotated_filename = f"reid_{os.path.splitext(filename)[0]}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
            annotated_path = os.path.join(app.config['OUTPUT_FOLDER'], annotated_filename)
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            video_writer = cv2.VideoWriter(annotated_path, fourcc, fps, (frame_width, frame_height))

        frame_index = 0
        process_this_frame = True
        detected_in_run = {}
        last_progress_update = 0

        while True:
            ret, frame = video_capture.read()
            if not ret:
                break

            frame_index += 1
            pos_msec = video_capture.get(cv2.CAP_PROP_POS_MSEC)
            current_sec = pos_msec / 1000.0 if pos_msec > 0 else (frame_index / fps)
            minutes = int(current_sec // 60)
            secs = int(current_sec % 60)
            timestamp_str = f"{minutes:02d}:{secs:02d}"

            face_locations = []
            face_display = []

            # Scale frame for speed
            small_frame = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
            rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)

            if process_this_frame:
                face_locations = face_recognition.face_locations(rgb_small_frame)
                face_encodings = face_recognition.face_encodings(rgb_small_frame, face_locations)

                for face_encoding, (s_top, s_right, s_bottom, s_left) in zip(face_encodings, face_locations):
                    top, right, bottom, left = s_top * 4, s_right * 4, s_bottom * 4, s_left * 4
                    h, w = frame.shape[:2]
                    face_crop = frame[max(0, top):min(h, bottom), max(0, left):min(w, right)]

                    person_id, is_new, matched_from = gm.match_or_register(
                        face_encoding=face_encoding,
                        face_crop=face_crop,
                        video_name=filename,
                        timestamp_str=timestamp_str,
                        current_sec=current_sec,
                        threshold=0.52
                    )

                    thumb_file = f"{person_id}.jpg"
                    if person_id not in detected_in_run:
                        detected_in_run[person_id] = {
                            "id": person_id,
                            "is_new": is_new,
                            "matched_from": matched_from,
                            "thumbnail_url": f"/gallery_thumb/{thumb_file}",
                            "timestamps": []
                        }

                    if timestamp_str not in detected_in_run[person_id]["timestamps"]:
                        if len(detected_in_run[person_id]["timestamps"]) < 10:
                            detected_in_run[person_id]["timestamps"].append(timestamp_str)

                    if matched_from:
                        lbl = f"{person_id} (Match: {matched_from})"
                        clr = (0, 255, 255)
                    elif is_new:
                        lbl = f"{person_id} [New]"
                        clr = (0, 255, 0)
                    else:
                        lbl = f"{person_id}"
                        clr = (0, 200, 100)
                    face_display.append((top, right, bottom, left, lbl, clr))

            process_this_frame = not process_this_frame

            if video_writer is not None:
                for (t, r, b, l, lbl, clr) in face_display:
                    cv2.rectangle(frame, (l, t), (r, b), clr, 2)
                    cv2.rectangle(frame, (l, b - 26), (r, b), clr, cv2.FILLED)
                    cv2.putText(frame, lbl, (l + 4, b - 6), cv2.FONT_HERSHEY_DUPLEX, 0.6, (0, 0, 0), 1)

                hud = f"[{filename}] {timestamp_str} | Frame {frame_index}/{total_frames}"
                cv2.putText(frame, hud, (15, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
                video_writer.write(frame)

            # Update real-time progress every 3 frames or 0.15s
            now = time.time()
            if now - last_progress_update > 0.15 or frame_index == total_frames:
                last_progress_update = now
                pct = min(99, int((frame_index / total_frames) * 100))
                elapsed = max(0.1, now - start_time)
                proc_fps = round(frame_index / elapsed, 1)
                match_count = sum(1 for p in detected_in_run.values() if p["matched_from"] is not None)

                with jobs_lock:
                    active_jobs[job_id] = {
                        "status": "processing",
                        "current_frame": frame_index,
                        "total_frames": total_frames,
                        "percent": pct,
                        "current_time": timestamp_str,
                        "proc_fps": proc_fps,
                        "detected_count": len(detected_in_run),
                        "match_count": match_count
                    }

        video_capture.release()
        if video_writer is not None:
            video_writer.release()
        gm.save()
        gm.export_excel_report(REPORT_EXCEL_FILE)

        detected_list = list(detected_in_run.values())
        new_count = sum(1 for p in detected_list if p["is_new"])
        match_count = sum(1 for p in detected_list if p["matched_from"] is not None)

        with jobs_lock:
            active_jobs[job_id] = {
                "status": "completed",
                "percent": 100,
                "result": {
                    "success": True,
                    "video_name": filename,
                    "total_frames": frame_index,
                    "duration_seconds": round(frame_index / fps, 1),
                    "detected_people": detected_list,
                    "new_identities_count": new_count,
                    "cross_matches_count": match_count,
                    "annotated_video_url": f"/download_video/{annotated_filename}" if annotated_filename else None,
                    "report_url": "/download_report",
                    "gallery_total_people": len(gm.people)
                }
            }

    except Exception as e:
        print(f"Error processing video job {job_id}: {e}")
        with jobs_lock:
            active_jobs[job_id] = {"status": "error", "error": str(e)}


@app.route('/api/process_video', methods=['POST'])
def start_process_video():
    if 'video' not in request.files:
        return jsonify({"success": False, "error": "No video file provided"}), 400

    video_file = request.files['video']
    if not video_file or not video_file.filename:
        return jsonify({"success": False, "error": "Empty filename"}), 400

    filename = secure_filename(video_file.filename)
    if not filename:
        filename = f"video_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"

    save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    video_file.save(save_path)

    save_annotated = request.form.get('save_annotated', 'true').lower() == 'true'

    job_id = f"job_{int(time.time() * 1000)}"
    with jobs_lock:
        active_jobs[job_id] = {
            "status": "starting",
            "percent": 0,
            "current_frame": 0,
            "total_frames": 0,
            "detected_count": 0,
            "match_count": 0
        }

    # Start asynchronous processing worker
    worker_thread = threading.Thread(
        target=process_video_worker,
        args=(job_id, save_path, filename, save_annotated),
        daemon=True
    )
    worker_thread.start()

    return jsonify({"success": True, "job_id": job_id})


@app.route('/api/progress/<job_id>', methods=['GET'])
def get_job_progress(job_id):
    with jobs_lock:
        job = active_jobs.get(job_id)
        if not job:
            return jsonify({"status": "not_found"}), 404
        return jsonify(job)


def find_available_port(start_port=5000, max_attempts=10):
    import socket
    for port in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('127.0.0.1', port)) != 0:
                return port
    return start_port


if __name__ == '__main__':
    port = find_available_port(5000)
    url = f"http://127.0.0.1:{port}"
    threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    print("\n========================================================")
    print("🚀 Face Recognition & Cross-Video Re-ID Web App Starting!")
    print(f"📍 URL: {url}")
    print("========================================================\n")
    app.run(host='127.0.0.1', port=port, debug=False)
