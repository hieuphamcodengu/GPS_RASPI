from flask import Flask, render_template_string, request, Response, jsonify
import threading
from Read_Serial import SerialData, start_serial_thread, execute_route_commands
from config import FLASK_HOST, FLASK_PORT, GOOGLE_MAPS_API_KEY
import detect_stream

# Tạo Flask app
app = Flask(__name__)

# Tạo đối tượng lưu dữ liệu GPS
shared_data = SerialData()

# Bắt đầu luồng đọc Serial nền
t = threading.Thread(target=start_serial_thread, args=(shared_data,), daemon=True)
t.start()

# Đọc file HTML từ map.html
with open("map.html", "r", encoding="utf-8") as f:
    html_template = f.read()

# Đọc file HTML từ detect_web.html
with open("detect_web.html", "r", encoding="utf-8") as f:
    detect_html_template = f.read()

@app.route("/")
def index():
    # render_template_string để chèn API key động vào file ngoài
    return render_template_string(html_template, GOOGLE_MAPS_API_KEY=GOOGLE_MAPS_API_KEY)

@app.route("/detection")
def detection_page():
    # Trang detection
    return render_template_string(detect_html_template)

@app.route("/getGpsData")
def get_gps_data():
    snap = shared_data.snapshot()
    return f"{snap.get('lat', 0.0)},{snap.get('lon', 0.0)}"

@app.route("/postData", methods=["POST"])
def post_data():
    dis = request.form.get("dis", "")
    dir_ = request.form.get("dir", "")
    dir_val = request.form.get("dir_value", "")
    print(f"[POST] dis={dis}")
    print(f"[POST] dir={dir_}")
    print(f"[POST] dir_value={dir_val}")
    return Response("Data received", mimetype="text/plain")

@app.route("/getYaw")
def get_yaw():
    yaw = shared_data.snapshot().get("yaw", 0.0)
    return f"{yaw:.2f}"

# Route bắt đầu thực thi lệnh điều khiển
@app.route("/startRoute", methods=["POST"])
def start_route():
    dis = request.form.get("dis", "")
    dir_ = request.form.get("dir", "")
    dir_val = request.form.get("dir_value", "")
    # Chuyển thành list số
    dis_list = [float(x) for x in dis.split(",") if x]
    dir_list = [int(x) for x in dir_.split(",") if x]
    dir_value_list = [float(x) for x in dir_val.split(",") if x]
    print(f"[START ROUTE] dis={dis_list}")
    print(f"[START ROUTE] dir={dir_list}")
    print(f"[START ROUTE] dir_value={dir_value_list}")
    threading.Thread(target=execute_route_commands, args=(shared_data, dis_list, dir_list, dir_value_list), daemon=True).start()
    return Response("Route started", mimetype="text/plain")

@app.route("/pauseRoute", methods=["POST"])
def pause_route():
    """Tạm dừng route"""
    shared_data.set_route_state(paused=True)
    print("[PAUSE ROUTE] Route paused")
    return Response("Route paused", mimetype="text/plain")

@app.route("/resumeRoute", methods=["POST"])
def resume_route():
    """Tiếp tục route sau khi tạm dừng"""
    shared_data.set_route_state(paused=False)
    print("[RESUME ROUTE] Route resumed")
    return Response("Route resumed", mimetype="text/plain")

@app.route("/stopRoute", methods=["POST"])
def stop_route():
    """Dừng hẳn route"""
    shared_data.set_route_state(stopped=True, running=False, paused=False)
    print("[STOP ROUTE] Route stopped")
    return Response("Route stopped", mimetype="text/plain")

@app.route("/getRouteStatus")
def get_route_status():
    """Lấy trạng thái route hiện tại"""
    status = shared_data.get_route_state()
    return jsonify(status)

# ===================== DETECTION ROUTES =====================
@app.route("/video_feed")
def video_feed():
    """Video streaming route"""
    if not detect_stream.init_camera():
        return Response("Camera not available", status=503)
    return Response(detect_stream.generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route("/start_detection", methods=["POST"])
def start_detection():
    """Enable object detection"""
    detect_stream.set_detection_enabled(True)
    return Response("Detection started", mimetype="text/plain")

@app.route("/stop_detection", methods=["POST"])
def stop_detection():
    """Disable object detection"""
    detect_stream.set_detection_enabled(False)
    return Response("Detection stopped", mimetype="text/plain")

@app.route("/detection_stats")
def detection_stats():
    """Get detection statistics"""
    stats = detect_stream.get_stats()
    return jsonify(stats)

@app.route("/camera_start", methods=["POST"])
def camera_start():
    """Start camera"""
    if detect_stream.init_camera():
        return Response("Camera started", mimetype="text/plain")
    return Response("Camera failed to start", status=500)

@app.route("/camera_stop", methods=["POST"])
def camera_stop():
    """Stop camera"""
    detect_stream.release_camera()
    detect_stream.set_detection_enabled(False)
    return Response("Camera stopped", mimetype="text/plain")

if __name__ == "__main__":
    app.run(host=FLASK_HOST, port=FLASK_PORT, debug=False)
