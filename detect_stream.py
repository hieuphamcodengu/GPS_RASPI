import cv2
import numpy as np
import time
from concurrent.futures import ThreadPoolExecutor
import os
import threading

# Try import TFLite runtime, fallback to TensorFlow if not available
try:
    import tflite_runtime.interpreter as tflite
    print("[INFO] Using tflite_runtime")
except ImportError:
    try:
        import tensorflow as tf
        tflite = tf.lite
        print("[INFO] Using TensorFlow Lite from tensorflow package")
    except ImportError:
        print("[WARNING] Neither tflite_runtime nor tensorflow found!")
        print("[WARNING] Detection features will be disabled")
        tflite = None

# ===================== CONFIG =====================
MODEL_PATH = "model.tflite"
INPUT_SIZE = 480        
NUM_THREADS = 4
CONF_THRESH = 0.3
NMS_THRESH = 0.45
CLASS_FILE = "classes.txt"
SKIP_FRAMES = 2

# ===================== ENV TWEAKS =====================
os.environ["OMP_NUM_THREADS"] = str(NUM_THREADS)
os.environ["OPENBLAS_NUM_THREADS"] = str(NUM_THREADS)
os.environ["NUMEXPR_NUM_THREADS"] = str(NUM_THREADS)

# ===================== LOAD CLASSES =====================
if os.path.exists(CLASS_FILE):
    with open(CLASS_FILE, "r", encoding="utf-8") as f:
        CLASS_NAMES = [c.strip() for c in f.readlines() if c.strip()]
else:
    # Fallback cho 2 classes: 0=Bệnh, 1=Bình thường
    CLASS_NAMES = ["Benh", "Binh_thuong"]

# ===================== LOAD TFLITE MODEL =====================
interpreter = None
input_details = None
output_details = None

if tflite is not None and os.path.exists(MODEL_PATH):
    try:
        print(f"Loading TFLite model: {MODEL_PATH}")
        interpreter = tflite.Interpreter(model_path=MODEL_PATH, num_threads=NUM_THREADS)
        interpreter.allocate_tensors()
        input_details = interpreter.get_input_details()
        output_details = interpreter.get_output_details()
        print("Model loaded successfully.")
    except Exception as e:
        print(f"[ERROR] Failed to load model: {e}")
        interpreter = None
elif tflite is None:
    print("[WARNING] TFLite not available - detection will be disabled")
else:
    print(f"[WARNING] Model file not found: {MODEL_PATH}")

# ===================== GLOBAL VARIABLES =====================
cap = None
detection_enabled = False
latest_frame = None
frame_lock = threading.Lock()
executor = ThreadPoolExecutor(max_workers=2)
future = None
latest_display = None
fps_display = 0.0
avg_inf_time = 0.0
object_count = 0
disease_count = 0  # Số cây bị bệnh
healthy_count = 0  # Số cây bình thường

# ===================== HELPERS =====================
def letterbox(img, new_shape=(INPUT_SIZE, INPUT_SIZE), color=(114,114,114)):
    """Resize and pad image while meeting stride-multiple constraints"""
    shape = img.shape[:2]
    if isinstance(new_shape, int):
        new_shape = (new_shape, new_shape)
    r = min(new_shape[0] / shape[0], new_shape[1] / shape[1])
    new_unpad = (int(round(shape[1] * r)), int(round(shape[0] * r)))
    dw = new_shape[1] - new_unpad[0]
    dh = new_shape[0] - new_unpad[1]
    dw /= 2
    dh /= 2

    img_resized = cv2.resize(img, new_unpad, interpolation=cv2.INTER_LINEAR)
    top, bottom = int(round(dh - 0.0001)), int(round(dh + 0.0001))
    left, right = int(round(dw - 0.0001)), int(round(dw + 0.0001))
    img_padded = cv2.copyMakeBorder(img_resized, top, bottom, left, right, cv2.BORDER_CONSTANT, value=color)
    return img_padded, r, (left, top)

def scale_coords(box_xywh, r, pad, orig_shape):
    """Scale boxes from letterboxed image back to original"""
    pad_x, pad_y = pad
    x_center = (box_xywh[0] - pad_x) / r
    y_center = (box_xywh[1] - pad_y) / r
    w = box_xywh[2] / r
    h = box_xywh[3] / r
    x1 = int(x_center - w / 2)
    y1 = int(y_center - h / 2)
    x2 = int(x_center + w / 2)
    y2 = int(y_center + h / 2)
    x1 = max(0, min(orig_shape[1]-1, x1))
    y1 = max(0, min(orig_shape[0]-1, y1))
    x2 = max(0, min(orig_shape[1]-1, x2))
    y2 = max(0, min(orig_shape[0]-1, y2))
    return [x1, y1, x2, y2]

def nms_boxes(boxes, scores, iou_threshold=NMS_THRESH):
    """NMS using OpenCV"""
    if len(boxes) == 0:
        return []
    rects = [[int(b[0]), int(b[1]), int(b[2]-b[0]), int(b[3]-b[1])] for b in boxes]
    indices = cv2.dnn.NMSBoxes(rects, scores, CONF_THRESH, iou_threshold)
    if len(indices) == 0:
        return []
    indices = np.array(indices).reshape(-1)
    return indices.tolist()

# ===================== INFERENCE WORKER =====================
def infer_on_image(img_bgr):
    """Run inference on image"""
    # Kiểm tra nếu không có interpreter
    if interpreter is None:
        return None, 0, (0, 0), 0.0
    
    start_time = time.time()
    
    img_padded, r, pad = letterbox(img_bgr, (INPUT_SIZE, INPUT_SIZE))
    input_tensor = img_padded.astype(np.float32) / 255.0
    input_index = input_details[0]['index']
    
    if input_details[0]['dtype'] == np.float32:
        interpreter.set_tensor(input_index, np.expand_dims(input_tensor, 0).astype(np.float32))
    else:
        interpreter.set_tensor(input_index, np.expand_dims(input_tensor, 0).astype(input_details[0]['dtype']))
    
    interpreter.invoke()
    output_data = interpreter.get_tensor(output_details[0]['index'])
    
    inference_time = time.time() - start_time
    return output_data[0], r, pad, inference_time

# ===================== POSTPROCESS =====================
def postprocess_and_draw(output, r, pad, frame):
    """Decode model output and draw bounding boxes"""
    global object_count, disease_count, healthy_count
    
    # Nếu không có output (interpreter = None)
    if output is None:
        return frame
    
    h0, w0 = frame.shape[:2]
    boxes = []
    scores = []
    class_ids = []

    for det in output:
        x, y, w, hh, obj_conf = det[0], det[1], det[2], det[3], det[4]
        class_confs = det[5:]
        class_id = int(np.argmax(class_confs))
        class_conf = float(class_confs[class_id])
        final_conf = float(obj_conf) * class_conf
        if final_conf < CONF_THRESH:
            continue

        if max(x, y, w, hh) <= 1.01:
            x_px = x * INPUT_SIZE
            y_px = y * INPUT_SIZE
            w_px = w * INPUT_SIZE
            h_px = hh * INPUT_SIZE
        else:
            x_px = x
            y_px = y
            w_px = w
            h_px = hh

        box_xywh = [x_px, y_px, w_px, h_px]
        x1, y1, x2, y2 = scale_coords(box_xywh, r, pad, (h0, w0))
        boxes.append([x1, y1, x2, y2])
        scores.append(final_conf)
        class_ids.append(class_id)

    indices = nms_boxes(boxes, scores, iou_threshold=NMS_THRESH)
    object_count = len(indices)
    
    # Đếm số lượng từng loại
    disease_count = 0
    healthy_count = 0
    
    if len(indices) == 0:
        return frame

    for i in indices:
        x1, y1, x2, y2 = boxes[i]
        cls = class_ids[i]
        label = CLASS_NAMES[cls] if cls < len(CLASS_NAMES) else f"class{cls}"
        conf = scores[i]
        
        # Đếm số lượng
        if cls == 0:
            disease_count += 1
        else:
            healthy_count += 1
        
        # Màu sắc: Đỏ nếu bệnh (class 0), Xanh lá nếu bình thường (class 1)
        if cls == 0:
            color = (0, 0, 255)  # Đỏ - Bệnh
            display_label = f"BENH {conf:.2f}"
        else:
            color = (0, 255, 0)  # Xanh lá - Bình thường
            display_label = f"BINH THUONG {conf:.2f}"
        
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 3)
        txt = display_label
        t_size = cv2.getTextSize(txt, 0, fontScale=0.7, thickness=2)[0]
        cv2.rectangle(frame, (x1, y1 - 25), (x1 + t_size[0] + 10, y1), color, -1)
        cv2.putText(frame, txt, (x1 + 5, y1 - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255,255,255), 2, cv2.LINE_AA)

    return frame

# ===================== CAMERA FUNCTIONS =====================
def init_camera():
    """Initialize camera"""
    global cap
    if cap is None or not cap.isOpened():
        cap = cv2.VideoCapture(0)
        if cap.isOpened():
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            print("Camera initialized")
            return True
    return cap is not None and cap.isOpened()

def release_camera():
    """Release camera"""
    global cap
    if cap is not None:
        cap.release()
        cap = None
        print("Camera released")

def get_frame():
    """Get current frame with or without detection"""
    global latest_frame, latest_display, future, fps_display, avg_inf_time
    global frame_lock, detection_enabled
    
    if cap is None or not cap.isOpened():
        return None
    
    ret, frame = cap.read()
    if not ret:
        return None
    
    with frame_lock:
        latest_frame = frame.copy()
    
    if detection_enabled and interpreter is not None:
        # Detection mode - run inference
        if future is not None and future.done():
            try:
                output, r, pad, inf_time = future.result()
                latest_display = postprocess_and_draw(output, r, pad, frame.copy())
                avg_inf_time = inf_time
            except Exception as e:
                print("Error processing detection:", e)
                latest_display = frame
        
        if future is None or future.done():
            future = executor.submit(infer_on_image, frame.copy())
        
        display = latest_display if latest_display is not None else frame
        
        # Draw stats on frame
        cv2.putText(display, f"FPS: {fps_display:.1f}", (10, 30), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,0), 2)
        cv2.putText(display, f"Inference: {avg_inf_time*1000:.0f}ms", (10, 60), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,255), 2)
        cv2.putText(display, f"Cay phat hien: {object_count}", (10, 90), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255,100,255), 2)
        
        return display
    elif detection_enabled and interpreter is None:
        # Detection requested but model not available
        cv2.putText(frame, "Detection unavailable - Model not loaded", (10, 30), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,0,255), 2)
        return frame
    else:
        # Camera only mode - no detection
        cv2.putText(frame, "Camera Mode - No Detection", (10, 30), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255,255,255), 2)
        return frame

def generate_frames():
    """Generator for video streaming"""
    frame_count = 0
    fps_start_time = time.time()
    global fps_display
    
    while True:
        frame = get_frame()
        if frame is None:
            time.sleep(0.1)
            continue
        
        # Update FPS
        frame_count += 1
        current_time = time.time()
        elapsed = current_time - fps_start_time
        if elapsed >= 1.0:
            fps_display = frame_count / elapsed
            frame_count = 0
            fps_start_time = current_time
        
        # Encode frame to JPEG
        ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if not ret:
            continue
        
        frame_bytes = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        
        time.sleep(0.01)  # Small delay to prevent CPU overload

def set_detection_enabled(enabled):
    """Enable or disable detection"""
    global detection_enabled, latest_display, future, object_count, disease_count, healthy_count
    detection_enabled = enabled
    if not enabled:
        latest_display = None
        future = None
        object_count = 0
        disease_count = 0
        healthy_count = 0
    print(f"Detection {'enabled' if enabled else 'disabled'}")

def get_stats():
    """Get current detection statistics"""
    return {
        "fps": round(fps_display, 1),
        "plants_detected": object_count,  # Số cây phát hiện
        "disease_count": disease_count,    # Số cây bị bệnh
        "healthy_count": healthy_count,    # Số cây bình thường
        "inference_time": round(avg_inf_time * 1000, 0)
    }
