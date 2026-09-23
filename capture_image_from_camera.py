import cv2
import os

KNOWN_FACES_DIR = "known_faces"
os.makedirs(KNOWN_FACES_DIR, exist_ok=True)

cam_port = 0
cam = cv2.VideoCapture(cam_port)

if not cam.isOpened():
    print(f"Error: Unable to open camera on port {cam_port}")
    exit(1)

inp = input('Enter person name to enroll: ').strip()
if not inp:
    print("Invalid name. Exiting.")
    cam.release()
    exit(1)

safe_name = inp.replace(' ', '_').lower()
save_path = os.path.join(KNOWN_FACES_DIR, f"{safe_name}.png")

print("Press 's' or 'Space' to capture photo, or 'q' to cancel.")

while True:
    result, image = cam.read()
    if not result:
        print("No image detected from camera. Retrying...")
        continue

    # Show live preview
    preview = image.copy()
    cv2.putText(preview, f"Enrolling: {inp}", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
    cv2.putText(preview, "Press 's' to Save | 'q' to Quit", (20, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    cv2.imshow("Capture Face", preview)

    key = cv2.waitKey(1) & 0xFF
    if key in (ord('s'), 32):  # 's' or Space
        cv2.imwrite(save_path, image)
        print(f"Face image saved to: {save_path}")
        break
    elif key == ord('q'):
        print("Capture cancelled.")
        break

cam.release()
cv2.destroyAllWindows()
