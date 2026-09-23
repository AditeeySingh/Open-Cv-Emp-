# Smart Face Discovery & Cross-Video Re-Identification (Web & Desktop)

A Cross-Video Face Recognition, Discovery, and Re-Identification application with an **interactive Web Interface (browser)** and desktop controls.

---

## 🌟 How It Works

1. **Process Video 1**:
   - Upload Video 1 in your browser.
   - The engine discovers all faces, assigns unique IDs (`Person_001`, `Person_002`...), stores their 128D facial embeddings, and saves clear face crops to the gallery.
2. **Process Video 2**:
   - Upload Video 2.
   - Returning individuals are identified and tagged as:
     `🎯 Person_001 (Matched from video1.mp4)`
   - Any newly discovered people are assigned `Person_003`, etc.
3. **Cross-Video Report & Annotated Video**:
   - Download `cross_video_matches.xls` with all timestamps (`MM:SS`) for each video.
   - Download the annotated output video with bounding boxes and match labels.

---

## 🚀 Running the Web Interface (Recommended)

Run either of these commands in your terminal:
```bash
./run.sh
```
or
```bash
./run_web.sh
```

This will automatically launch the server and **open your browser** at:
👉 **`http://127.0.0.1:5000`**

### Inside the Web Interface:
- **Upload & Match Tab**:
  - Drag and drop or click the dropzone to select your video (`.mp4`, `.avi`, `.mov`, `.mkv`).
  - Click the **"🚀 Process Video"** button.
  - Watch the live progress bar.
  - View detected people cards with their face photo, ID, match badges, and timestamps.
  - Download the annotated video or Excel report.
- **Discovered Gallery Tab**:
  - View all cataloged identities across all processed videos.
  - Click **"🔄 Reset Gallery"** to clear identities and start fresh from `Person_001`.

---

## 🖥️ Desktop Tkinter GUI (Alternative)

If you prefer the native desktop window:
```bash
./run.sh --gui
```
*(Fixed button contrast for macOS dark mode)*
