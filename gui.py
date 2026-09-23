#!/opt/anaconda3/bin/python3
import cv2
import face_recognition
import numpy as np
import os
import shutil
import subprocess
from datetime import date, datetime
import xlrd
from xlutils.copy import copy as xl_copy
from xlwt import Workbook
import tkinter as tk
from tkinter import messagebox, simpledialog, filedialog, ttk

from gallery_manager import GalleryManager, REPORT_EXCEL_FILE, GALLERY_DIR

KNOWN_FACES_DIR = "known_faces"
UNKNOWN_FACES_DIR = "unknown_faces"
OUTPUT_VIDEOS_DIR = "output_videos"
ATTENDANCE_EXCEL_FILE = "attendance_excel.xls"


def load_known_faces(known_faces_dir=KNOWN_FACES_DIR):
    """
    Dynamically loads and encodes all face images found in the known_faces directory.
    Image filename (without extension) is treated as the person's name.
    """
    known_face_encodings = []
    known_face_names = []

    if not os.path.exists(known_faces_dir):
        os.makedirs(known_faces_dir, exist_ok=True)
        return known_face_encodings, known_face_names

    valid_extensions = ('.png', '.jpg', '.jpeg', '.webp', '.bmp')
    for file in sorted(os.listdir(known_faces_dir)):
        if file.lower().endswith(valid_extensions):
            name = os.path.splitext(file)[0].replace('_', ' ').title()
            path = os.path.join(known_faces_dir, file)
            try:
                image = face_recognition.load_image_file(path)
                encodings = face_recognition.face_encodings(image)
                if len(encodings) > 0:
                    known_face_encodings.append(encodings[0])
                    known_face_names.append(name)
            except Exception as e:
                print(f"Error processing '{file}': {e}")

    return known_face_encodings, known_face_names


def run_cross_video_matching(video_path, save_video=False):
    """
    Runs dynamic face discovery and re-identification on a video file.
    Matches faces against the persistent GalleryManager gallery, assigns
    new IDs to new individuals, and flags matches from prior videos.
    """
    if not os.path.exists(video_path):
        messagebox.showerror("Error", f"Video file not found: {video_path}")
        return

    os.makedirs(OUTPUT_VIDEOS_DIR, exist_ok=True)
    gm = GalleryManager(GALLERY_DIR)
    video_name = os.path.basename(video_path)

    video_capture = cv2.VideoCapture(video_path)
    if not video_capture.isOpened():
        messagebox.showerror("Error", f"Cannot open video: {video_path}")
        return

    fps = video_capture.get(cv2.CAP_PROP_FPS)
    if not fps or fps <= 0 or np.isnan(fps):
        fps = 25.0
    frame_width = int(video_capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(video_capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(video_capture.get(cv2.CAP_PROP_FRAME_COUNT))

    video_writer = None
    if save_video:
        output_filename = f"reid_{os.path.splitext(video_name)[0]}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
        output_path = os.path.join(OUTPUT_VIDEOS_DIR, output_filename)
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        video_writer = cv2.VideoWriter(output_path, fourcc, fps, (frame_width, frame_height))
        print(f"Recording cross-video Re-ID output to: {output_path}")

    process_this_frame = True
    frame_index = 0
    delay_ms = max(1, int(1000 / fps))
    paused = False

    face_locations = []
    face_display_data = []

    print(f"\n[Cross-Video Re-ID] Processing '{video_name}'...")
    print("Controls: 'Space' to Pause/Resume | 'q' to Finish & Save")

    try:
        while True:
            if not paused:
                ret, frame = video_capture.read()
                if not ret:
                    print("Reached end of video.")
                    break

                frame_index += 1
                pos_msec = video_capture.get(cv2.CAP_PROP_POS_MSEC)
                current_sec = pos_msec / 1000.0 if pos_msec > 0 else (frame_index / fps)
                minutes = int(current_sec // 60)
                secs = int(current_sec % 60)
                timestamp_str = f"{minutes:02d}:{secs:02d}"

                small_frame = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
                rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)

                if process_this_frame:
                    face_locations = face_recognition.face_locations(rgb_small_frame)
                    face_encodings = face_recognition.face_encodings(rgb_small_frame, face_locations)

                    face_display_data = []
                    for face_encoding, (s_top, s_right, s_bottom, s_left) in zip(face_encodings, face_locations):
                        # Calculate high-res bounding box for crop
                        top, right, bottom, left = s_top * 4, s_right * 4, s_bottom * 4, s_left * 4
                        h, w = frame.shape[:2]
                        crop_top, crop_bottom = max(0, top), min(h, bottom)
                        crop_left, crop_right = max(0, left), min(w, right)
                        face_crop = frame[crop_top:crop_bottom, crop_left:crop_right]

                        person_id, is_new, matched_from = gm.match_or_register(
                            face_encoding=face_encoding,
                            face_crop=face_crop,
                            video_name=video_name,
                            timestamp_str=timestamp_str,
                            current_sec=current_sec,
                            threshold=0.52
                        )

                        if matched_from:
                            label = f"{person_id} (Match: {matched_from})"
                            color = (0, 255, 255)  # Bright Yellow/Cyan for cross-video match
                        elif is_new:
                            label = f"{person_id} [New]"
                            color = (0, 255, 0)  # Green for new discovery
                        else:
                            label = f"{person_id}"
                            color = (0, 220, 100)

                        face_display_data.append((top, right, bottom, left, label, color))

                process_this_frame = not process_this_frame

                # Draw bounding boxes and labels
                for (top, right, bottom, left, label, color) in face_display_data:
                    cv2.rectangle(frame, (left, top), (right, bottom), color, 2)
                    cv2.rectangle(frame, (left, bottom - 28), (right, bottom), color, cv2.FILLED)
                    cv2.putText(frame, label, (left + 5, bottom - 7), cv2.FONT_HERSHEY_DUPLEX, 0.6, (0, 0, 0), 1)

                # Draw HUD
                hud_text = f"[{video_name}] Time: {timestamp_str}"
                if total_frames > 0:
                    hud_text += f" | Frame: {frame_index}/{total_frames}"
                cv2.putText(frame, hud_text, (15, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
                cv2.putText(frame, f"Gallery Size: {len(gm.people)} IDs", (15, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 2)

                if video_writer is not None:
                    video_writer.write(frame)

                cv2.imshow("Cross-Video Face Discovery & Re-ID", frame)

            key = cv2.waitKey(delay_ms) & 0xFF
            if key == ord('q'):
                print("User stopped processing.")
                break
            elif key == ord(' '):
                paused = not paused
                print("Paused" if paused else "Resumed")

    finally:
        video_capture.release()
        if video_writer is not None:
            video_writer.release()
            print("Annotated output video saved.")
        cv2.destroyAllWindows()
        gm.save()
        report_path = gm.export_excel_report(REPORT_EXCEL_FILE)
        messagebox.showinfo(
            "Video Processed",
            f"Completed processing '{video_name}'.\n\n"
            f"Total People in Gallery: {len(gm.people)}\n"
            f"Cross-Video Match Report updated in:\n'{report_path}'"
        )


def run_enrolled_attendance(source, session_name, save_video=False, is_video_file=False):
    """
    Standard attendance mode matching against manually enrolled photos in known_faces/.
    """
    known_face_encodings, known_face_names = load_known_faces(KNOWN_FACES_DIR)
    if not known_face_encodings:
        proceed = messagebox.askyesno(
            "No Enrolled Faces",
            "No known face images found in 'known_faces/'. Continue anyway?"
        )
        if not proceed:
            return

    video_capture = cv2.VideoCapture(source)
    if not video_capture.isOpened():
        messagebox.showerror("Error", f"Cannot open video source: {source}")
        return

    fps = video_capture.get(cv2.CAP_PROP_FPS) or 25.0
    frame_width = int(video_capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(video_capture.get(cv2.CAP_PROP_FRAME_HEIGHT))

    video_writer = None
    if save_video and is_video_file:
        output_filename = f"attendance_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
        output_path = os.path.join(OUTPUT_VIDEOS_DIR, output_filename)
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        video_writer = cv2.VideoWriter(output_path, fourcc, fps, (frame_width, frame_height))

    # Initialize attendance excel
    wb = Workbook()
    if not os.path.exists(ATTENDANCE_EXCEL_FILE):
        sheet = wb.add_sheet(session_name)
        sheet.write(0, 0, 'Name')
        sheet.write(0, 1, 'Source')
        sheet.write(0, 2, 'Timestamp')
        sheet.write(0, 3, 'Status')
        wb.save(ATTENDANCE_EXCEL_FILE)

    rb = xlrd.open_workbook(ATTENDANCE_EXCEL_FILE, formatting_info=True)
    wb = xl_copy(rb)
    sheet_names = rb.sheet_names()
    if session_name in sheet_names:
        sheet = wb.get_sheet(sheet_names.index(session_name))
        row = rb.sheet_by_name(session_name).nrows
    else:
        sheet = wb.add_sheet(session_name)
        sheet.write(0, 0, 'Name')
        sheet.write(0, 1, 'Source')
        sheet.write(0, 2, 'Timestamp')
        sheet.write(0, 3, 'Status')
        row = 1

    last_logged_time = {}
    delay_ms = max(1, int(1000 / fps)) if is_video_file else 1
    process_this_frame = True
    frame_index = 0

    try:
        while True:
            ret, frame = video_capture.read()
            if not ret:
                break
            frame_index += 1

            current_sec = frame_index / fps
            timestamp_str = datetime.now().strftime("%H:%M:%S")

            small_frame = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
            rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)

            face_locations = face_recognition.face_locations(rgb_small_frame)
            face_encodings = face_recognition.face_encodings(rgb_small_frame, face_locations)

            face_names = []
            for face_encoding in face_encodings:
                name = "Unknown"
                if known_face_encodings:
                    distances = face_recognition.face_distance(known_face_encodings, face_encoding)
                    best_idx = np.argmin(distances)
                    if distances[best_idx] < 0.6:
                        name = known_face_names[best_idx]
                face_names.append(name)

                if name != "Unknown":
                    if name not in last_logged_time or (current_sec - last_logged_time[name]) >= 5.0:
                        last_logged_time[name] = current_sec
                        sheet.write(row, 0, name)
                        sheet.write(row, 1, str(source) if is_video_file else str(date.today()))
                        sheet.write(row, 2, timestamp_str)
                        sheet.write(row, 3, "Present")
                        wb.save(ATTENDANCE_EXCEL_FILE)
                        row += 1

            for (top, right, bottom, left), name in zip(face_locations, face_names):
                top, right, bottom, left = top * 4, right * 4, bottom * 4, left * 4
                color = (0, 255, 0) if name != "Unknown" else (0, 0, 255)
                cv2.rectangle(frame, (left, top), (right, bottom), color, 2)
                cv2.rectangle(frame, (left, bottom - 25), (right, bottom), color, cv2.FILLED)
                cv2.putText(frame, name, (left + 6, bottom - 6), cv2.FONT_HERSHEY_DUPLEX, 0.7, (255, 255, 255), 1)

            if video_writer is not None:
                video_writer.write(frame)

            cv2.imshow("Enrolled Face Attendance", frame)
            if cv2.waitKey(delay_ms) & 0xFF == ord('q'):
                break
    finally:
        video_capture.release()
        if video_writer is not None:
            video_writer.release()
        cv2.destroyAllWindows()
        wb.save(ATTENDANCE_EXCEL_FILE)
        messagebox.showinfo("Done", f"Attendance logged to '{ATTENDANCE_EXCEL_FILE}'.")


def create_gui():
    root = tk.Tk()
    root.title("Face Recognition & Cross-Video Re-Identification")
    root.geometry("560x540")
    root.resizable(False, False)

    notebook = ttk.Notebook(root)
    notebook.pack(fill="both", expand=True, padx=10, pady=10)

    # -------------------------------------------------------------
    # TAB 1: Cross-Video Face Matching (The Primary Request)
    # -------------------------------------------------------------
    tab_reid = ttk.Frame(notebook)
    notebook.add(tab_reid, text="  Cross-Video Re-ID (Video 1 ➔ Video 2)  ")

    reid_title = tk.Label(
        tab_reid,
        text="Cross-Video Face Discovery & Matching",
        font=("Helvetica", 15, "bold")
    )
    reid_title.pack(pady=(12, 4))

    reid_sub = tk.Label(
        tab_reid,
        text="Assigns IDs (Person_001, Person_002...) in Video 1 and automatically\nmatches returning faces across Video 2, Video 3, etc.",
        font=("Helvetica", 9),
        fg="#cbd5e1",
        justify="center"
    )
    reid_sub.pack(pady=(0, 10))

    gallery_info_frame = tk.LabelFrame(tab_reid, text="Current Gallery Status", padx=12, pady=8)
    gallery_info_frame.pack(fill="x", padx=15, pady=5)

    gallery_status_label = tk.Label(gallery_info_frame, text="Checking gallery...", font=("Helvetica", 10), justify="left")
    gallery_status_label.pack(anchor="w")

    def refresh_gallery_status():
        gm = GalleryManager(GALLERY_DIR)
        num_people = len(gm.people)
        cross_matches = sum(1 for p in gm.people if len(p.get("video_detections", {})) > 1)
        txt = f"• Registered People in Gallery: {num_people}\n• Cross-Video Matches Found: {cross_matches}"
        if num_people > 0:
            sample_ids = [p["id"] for p in gm.people[:6]]
            txt += f"\n• Active IDs: {', '.join(sample_ids)}{'...' if num_people > 6 else ''}"
        gallery_status_label.config(text=txt)

    save_annotated_var = tk.BooleanVar(value=True)
    chk_save = tk.Checkbutton(
        tab_reid,
        text="Save Annotated Output Video (Bounding Boxes + Match Labels)",
        variable=save_annotated_var
    )
    chk_save.pack(pady=4)

    def on_run_cross_video():
        file_path = filedialog.askopenfilename(
            title="Select Video to Process & Match",
            filetypes=[("Video Files", "*.mp4 *.avi *.mov *.mkv *.webm"), ("All Files", "*.*")]
        )
        if not file_path:
            return
        run_cross_video_matching(file_path, save_video=save_annotated_var.get())
        refresh_gallery_status()

    def on_reset_gallery():
        confirm = messagebox.askyesno(
            "Reset Gallery?",
            "This will delete all discovered identities and start fresh from Person_001.\n\nAre you sure?"
        )
        if confirm:
            gm = GalleryManager(GALLERY_DIR)
            gm.reset_gallery()
            refresh_gallery_status()
            messagebox.showinfo("Reset", "Gallery has been reset.")

    def on_open_report():
        if not os.path.exists(REPORT_EXCEL_FILE):
            messagebox.showinfo("No Report", f"Report '{REPORT_EXCEL_FILE}' has not been generated yet. Process a video first.")
            return
        if os.name == 'posix':
            subprocess.run(["open", REPORT_EXCEL_FILE])
        elif os.name == 'nt':
            os.startfile(REPORT_EXCEL_FILE)

    def on_open_gallery_folder():
        os.makedirs(GALLERY_DIR, exist_ok=True)
        if os.name == 'posix':
            subprocess.run(["open", GALLERY_DIR])
        elif os.name == 'nt':
            os.startfile(GALLERY_DIR)

    btn_process_reid = tk.Button(
        tab_reid,
        text="▶  Process Video (Match Against Gallery)",
        command=on_run_cross_video,
        bg="#e2e8f0",
        fg="#000000",
        highlightbackground="#0066cc",
        font=("Helvetica", 12, "bold"),
        height=2
    )
    btn_process_reid.pack(fill="x", padx=15, pady=(10, 4))

    action_row = tk.Frame(tab_reid)
    action_row.pack(fill="x", padx=15, pady=4)

    btn_report = tk.Button(
        action_row,
        text="📊 Open Cross-Video Report (Excel)",
        command=on_open_report,
        font=("Helvetica", 10)
    )
    btn_report.pack(side="left", expand=True, fill="x", padx=(0, 2))

    btn_folder = tk.Button(
        action_row,
        text="🖼 View Face Crops",
        command=on_open_gallery_folder,
        font=("Helvetica", 10)
    )
    btn_folder.pack(side="right", expand=True, fill="x", padx=(2, 0))

    btn_reset = tk.Button(
        tab_reid,
        text="🔄 Reset Gallery (Start Fresh from Person_001)",
        command=on_reset_gallery,
        fg="#cc0000",
        font=("Helvetica", 9)
    )
    btn_reset.pack(pady=(12, 0))

    # -------------------------------------------------------------
    # TAB 2: Pre-Enrolled Faces Attendance (Original feature)
    # -------------------------------------------------------------
    tab_att = ttk.Frame(notebook)
    notebook.add(tab_att, text="  Enrolled Faces (Webcam & Photos)  ")

    att_title = tk.Label(
        tab_att,
        text="Enrolled Face Attendance",
        font=("Helvetica", 14, "bold")
    )
    att_title.pack(pady=(15, 5))

    enrolled_info_frame = tk.LabelFrame(tab_att, text="Enrolled Faces Info", padx=10, pady=8)
    enrolled_info_frame.pack(fill="x", padx=20, pady=10)

    enrolled_label = tk.Label(enrolled_info_frame, text="Checking enrolled faces...", justify="left")
    enrolled_label.pack(anchor="w")

    def refresh_enrolled_count():
        _, names = load_known_faces(KNOWN_FACES_DIR)
        enrolled_label.config(text=f"Enrolled Photos: {len(names)} ({', '.join(names) if names else 'None'})")

    def on_start_webcam():
        run_enrolled_attendance(source=0, session_name="Webcam_Session", is_video_file=False)

    def on_add_face():
        fpath = filedialog.askopenfilename(
            title="Select Face Photo",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.webp *.bmp"), ("All", "*.*")]
        )
        if not fpath:
            return
        pname = simpledialog.askstring("Name", "Enter person's name:")
        if not pname:
            return
        dest = os.path.join(KNOWN_FACES_DIR, f"{pname.strip().replace(' ', '_').lower()}{os.path.splitext(fpath)[1]}")
        os.makedirs(KNOWN_FACES_DIR, exist_ok=True)
        shutil.copyfile(fpath, dest)
        refresh_enrolled_count()
        messagebox.showinfo("Added", f"Face photo added for {pname}!")

    btn_cam = tk.Button(
        tab_att,
        text="📷  Start Webcam Attendance",
        command=on_start_webcam,
        font=("Helvetica", 11, "bold"),
        height=2
    )
    btn_cam.pack(fill="x", padx=20, pady=10)

    btn_add_img = tk.Button(
        tab_att,
        text="➕ Enroll New Face Photo",
        command=on_add_face,
        font=("Helvetica", 10)
    )
    btn_add_img.pack(fill="x", padx=20, pady=5)

    refresh_gallery_status()
    refresh_enrolled_count()

    root.mainloop()


if __name__ == "__main__":
    create_gui()
