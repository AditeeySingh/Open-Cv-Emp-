import os
import pickle
import cv2
import numpy as np
import xlrd
from xlutils.copy import copy as xl_copy
from xlwt import Workbook, easyxf

GALLERY_DIR = "gallery"
GALLERY_DATA_FILE = os.path.join(GALLERY_DIR, "gallery_data.pkl")
REPORT_EXCEL_FILE = "cross_video_matches.xls"


class GalleryManager:
    """
    Manages dynamic face discovery, persistent embeddings gallery,
    and cross-video re-identification tracking.
    """
    def __init__(self, gallery_dir=GALLERY_DIR):
        self.gallery_dir = gallery_dir
        self.data_file = os.path.join(gallery_dir, "gallery_data.pkl")
        self.people = []  # List of person dicts
        self.next_id_counter = 1
        self.last_log_sec = {}  # (person_id, video_name) -> last logged second
        self.load()

    def load(self):
        os.makedirs(self.gallery_dir, exist_ok=True)
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, "rb") as f:
                    data = pickle.load(f)
                    self.people = data.get("people", [])
                    self.next_id_counter = data.get("next_id_counter", len(self.people) + 1)
                print(f"[Gallery] Loaded {len(self.people)} people from gallery.")
            except Exception as e:
                print(f"[Gallery] Error loading existing gallery data: {e}")
                self.people = []
                self.next_id_counter = 1
        else:
            self.people = []
            self.next_id_counter = 1

    def save(self):
        os.makedirs(self.gallery_dir, exist_ok=True)
        with open(self.data_file, "wb") as f:
            pickle.dump({
                "people": self.people,
                "next_id_counter": self.next_id_counter
            }, f)

    def reset_gallery(self):
        """Clears all registered identities from the gallery."""
        self.people = []
        self.next_id_counter = 1
        self.last_log_sec = {}
        if os.path.exists(self.gallery_dir):
            for fname in os.listdir(self.gallery_dir):
                fpath = os.path.join(self.gallery_dir, fname)
                if os.path.isfile(fpath):
                    try:
                        os.remove(fpath)
                    except Exception:
                        pass
        self.save()
        print("[Gallery] Gallery reset successfully.")

    def match_or_register(self, face_encoding, face_crop, video_name, timestamp_str, current_sec, threshold=0.52):
        """
        Compares face_encoding against all registered gallery identities.
        Returns:
            person_id (str): e.g. "Person_001"
            is_new (bool): True if this identity was created just now
            matched_from_prev_video (str or None): Name of original video if this is a cross-video match
        """
        best_match_person = None
        best_distance = float("inf")

        # Compare against all embeddings for each registered person
        for person in self.people:
            embeddings = person["embeddings"]
            distances = [np.linalg.norm(e - face_encoding) for e in embeddings]
            min_dist = min(distances) if distances else float("inf")
            if min_dist < best_distance:
                best_distance = min_dist
                best_match_person = person

        # Check if match is within threshold
        if best_match_person is not None and best_distance < threshold:
            person_id = best_match_person["id"]
            first_video = best_match_person.get("first_seen_video", "")

            # Add diverse embedding if we have < 5 embeddings and distance is informative (> 0.25)
            if len(best_match_person["embeddings"]) < 5 and best_distance > 0.25:
                best_match_person["embeddings"].append(face_encoding)

            # Record detection in this video
            if video_name not in best_match_person["video_detections"]:
                best_match_person["video_detections"][video_name] = []

            # Debounce logging within same video (at most once every 4 seconds)
            debounce_key = (person_id, video_name)
            last_sec = self.last_log_sec.get(debounce_key, -100.0)
            if (current_sec - last_sec) >= 4.0:
                self.last_log_sec[debounce_key] = current_sec
                best_match_person["video_detections"][video_name].append(timestamp_str)

            matched_from_prev = first_video if first_video != video_name else None
            return person_id, False, matched_from_prev

        # No match found -> Register new person
        person_id = f"Person_{self.next_id_counter:03d}"
        self.next_id_counter += 1

        # Save thumbnail crop
        thumbnail_filename = f"{person_id}.jpg"
        thumbnail_path = os.path.join(self.gallery_dir, thumbnail_filename)
        if face_crop is not None and face_crop.size > 0:
            cv2.imwrite(thumbnail_path, face_crop)

        new_person = {
            "id": person_id,
            "embeddings": [face_encoding],
            "thumbnail_path": thumbnail_path,
            "first_seen_video": video_name,
            "video_detections": {
                video_name: [timestamp_str]
            }
        }
        self.people.append(new_person)
        self.last_log_sec[(person_id, video_name)] = current_sec
        self.save()

        return person_id, True, None

    def export_excel_report(self, excel_path=REPORT_EXCEL_FILE):
        """
        Exports a comprehensive cross-video matching report to Excel.
        """
        wb = Workbook()
        sheet = wb.add_sheet("Cross_Video_Matches")

        # Header style
        header_xf = easyxf('font: bold on, color white; pattern: pattern solid, fore_colour blue; align: horiz center')
        highlight_xf = easyxf('pattern: pattern solid, fore_colour light_green; align: horiz center; font: bold on')
        regular_xf = easyxf('align: horiz center')
        align_left_xf = easyxf('align: horiz left')

        # Collect all unique video names
        all_videos = set()
        for person in self.people:
            all_videos.update(person.get("video_detections", {}).keys())
        sorted_videos = sorted(list(all_videos))

        # Write header
        headers = ["Person ID", "Thumbnail Image", "First Seen In", "Total Videos Seen", "Cross-Video Match?"]
        for v in sorted_videos:
            headers.append(f"Timestamps in {v}")

        for col_idx, h in enumerate(headers):
            sheet.write(0, col_idx, h, header_xf)

        # Write data rows
        for row_idx, person in enumerate(self.people, start=1):
            pid = person["id"]
            thumb = person.get("thumbnail_path", "")
            first_v = person.get("first_seen_video", "")
            detections = person.get("video_detections", {})
            num_videos = len(detections)
            is_cross_match = "YES" if num_videos > 1 else "NO"
            row_style = highlight_xf if num_videos > 1 else regular_xf

            sheet.write(row_idx, 0, pid, row_style)
            sheet.write(row_idx, 1, thumb, align_left_xf)
            sheet.write(row_idx, 2, first_v, regular_xf)
            sheet.write(row_idx, 3, num_videos, regular_xf)
            sheet.write(row_idx, 4, is_cross_match, row_style)

            for v_idx, v in enumerate(sorted_videos):
                ts_list = detections.get(v, [])
                ts_str = ", ".join(ts_list) if ts_list else "—"
                sheet.write(row_idx, 5 + v_idx, ts_str, align_left_xf)

        wb.save(excel_path)
        print(f"[Gallery] Cross-video report saved to {excel_path}")
        return excel_path
