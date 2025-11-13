from flask import Flask, render_template_string, request, Response, jsonify
import threading
import time
import json
import os
import serial
from Read_Serial import SerialData, start_serial_thread, execute_route_commands
from config import (FLASK_HOST, FLASK_PORT, GOOGLE_MAPS_API_KEY, LIDAR_PORT, LIDAR_BAUDRATE,
                    LIDAR_OBSTACLE_DISTANCE, LIDAR_DETECTION_ANGLE_MIN, LIDAR_DETECTION_ANGLE_MAX,
                    SERIAL_PORT_CONTROL, SERIAL_BAUD_CONTROL)
import detect_stream
import Read_lidar
import config

# Tạo Flask app
app = Flask(__name__)

# =====================================================
# Runtime Settings - Có thể thay đổi mà không cần restart
# =====================================================
runtime_settings = {
    "TIME_PER_METER_SEC": config.TIME_PER_METER_SEC,
    "LIDAR_MAX_POINTS": config.LIDAR_MAX_POINTS,
    "LIDAR_DOT_LIFETIME": config.LIDAR_DOT_LIFETIME,
    "LIDAR_OBSTACLE_DISTANCE": config.LIDAR_OBSTACLE_DISTANCE,
    "LIDAR_DETECTION_ANGLE_MIN": config.LIDAR_DETECTION_ANGLE_MIN,
    "LIDAR_DETECTION_ANGLE_MAX": config.LIDAR_DETECTION_ANGLE_MAX
}
settings_lock = threading.Lock()

# Load settings từ file JSON nếu tồn tại
def load_settings_from_json():
    """Load settings từ settings.json"""
    global runtime_settings
    try:
        if os.path.exists("settings.json"):
            with open("settings.json", "r", encoding="utf-8") as f:
                loaded = json.load(f)
                with settings_lock:
                    runtime_settings.update(loaded)
                print(f"[Settings] Loaded from settings.json: {runtime_settings}")
        else:
            print("[Settings] No settings.json found, using config.py defaults")
    except Exception as e:
        print(f"[Settings] Error loading settings.json: {e}")

def save_settings_to_json():
    """Lưu settings vào settings.json"""
    try:
        with settings_lock:
            with open("settings.json", "w", encoding="utf-8") as f:
                json.dump(runtime_settings, f, indent=4)
        print(f"[Settings] Saved to settings.json: {runtime_settings}")
        return True
    except Exception as e:
        print(f"[Settings] Error saving settings.json: {e}")
        return False

def get_setting(key):
    """Lấy giá trị setting (thread-safe)"""
    with settings_lock:
        return runtime_settings.get(key)

def update_setting(key, value):
    """Cập nhật setting (thread-safe)"""
    with settings_lock:
        runtime_settings[key] = value

# Load settings khi khởi động
load_settings_from_json()

# Tạo đối tượng lưu dữ liệu GPS
shared_data = SerialData()

# Bắt đầu luồng đọc Serial nền
t = threading.Thread(target=start_serial_thread, args=(shared_data,), daemon=True)
t.start()

# Background thread để tự động kiểm tra LIDAR và cập nhật obstacle status
def lidar_monitor_thread(shared_data):
    """Thread liên tục kiểm tra LIDAR data và cập nhật obstacle status"""
    print("[LIDAR Monitor] Background thread started")
    last_config_print = 0  # Để in config mỗi 10 giây
    
    while True:
        try:
            # Lấy dữ liệu LIDAR hiện tại
            points = Read_lidar.lidar_data.get_current_points()
            
            # Đọc config động từ runtime_settings
            angle_min = get_setting("LIDAR_DETECTION_ANGLE_MIN")
            angle_max = get_setting("LIDAR_DETECTION_ANGLE_MAX")
            obstacle_dist = get_setting("LIDAR_OBSTACLE_DISTANCE")
            
            # In config mỗi 10 giây để debug
            current_time = time.time()
            if current_time - last_config_print > 10:
                print(f"[LIDAR Monitor] Current config: Distance={obstacle_dist}mm, Angle=[{angle_min}° to {angle_max}°]")
                last_config_print = current_time
            
            # Tính khoảng cách gần nhất trong vùng được cấu hình
            min_distance = float('inf')
            has_obstacle = False
            
            for point in points:
                angle = point["angle"]
                distance = point["distance"]
                
                # Kiểm tra góc trong vùng phát hiện (xử lý cả góc âm)
                is_in_zone = False
                
                if angle_min < 0 and angle_max > 0:
                    # Trường hợp góc qua 0° (ví dụ: -20° đến 20°)
                    # Chấp nhận góc trong khoảng [-20, 20] hoặc [340, 360] và [0, 20]
                    if (angle >= angle_min and angle <= angle_max) or \
                       (angle >= (360 + angle_min) and angle <= 360) or \
                       (angle >= 0 and angle <= angle_max):
                        is_in_zone = True
                else:
                    # Trường hợp bình thường (ví dụ: 30° đến 60°)
                    if angle >= angle_min and angle <= angle_max:
                        is_in_zone = True
                
                # Chỉ xét các điểm trong vùng được cấu hình
                if is_in_zone:
                    if distance < min_distance:
                        min_distance = distance
                    if distance < obstacle_dist:
                        has_obstacle = True
            
            # Cập nhật vào shared_data
            if has_obstacle:
                shared_data.set_lidar_obstacle(True, min_distance)
                print(f"[LIDAR Monitor] ⚠️ OBSTACLE: {min_distance:.0f}mm < {obstacle_dist}mm in zone [{angle_min}° to {angle_max}°]")
            else:
                shared_data.set_lidar_obstacle(False, min_distance if min_distance != float('inf') else 9999)
            
            time.sleep(0.1)  # Kiểm tra mỗi 100ms
            
        except Exception as e:
            print(f"[LIDAR Monitor] Error: {e}")
            time.sleep(0.5)

# Khởi động LIDAR monitor thread
lidar_monitor = threading.Thread(target=lidar_monitor_thread, args=(shared_data,), daemon=True)
lidar_monitor.start()

def lidar_emergency_monitor_thread(shared_data):
    """
    Thread liên tục gửi tín hiệu về Arduino:
    - 'S' nếu phát hiện vật cản < ngưỡng
    - 'N' nếu không có vật cản (normal)
    Arduino sẽ tự quyết định xử lý như thế nào.
    """
    print("[LIDAR Emergency Monitor] Starting continuous monitoring...")
    
    try:
        with serial.Serial(SERIAL_PORT_CONTROL, SERIAL_BAUD_CONTROL, timeout=1) as ser:
            print(f"[LIDAR Emergency Monitor] Connected to {SERIAL_PORT_CONTROL}")
            last_state = None  # Track để chỉ log khi thay đổi
            
            while True:
                try:
                    lidar_status = shared_data.get_lidar_obstacle()
                    
                    if lidar_status["detected"]:
                        # Có vật cản → gửi 'S'
                        ser.write(b'S')
                        if last_state != 'S':
                            print(f"[LIDAR Emergency Monitor] 🚨 OBSTACLE DETECTED at {lidar_status['min_distance']:.0f}mm → Sending 'S'")
                            last_state = 'S'
                    else:
                        # Không có vật cản → gửi 'N'
                        ser.write(b'N')
                        if last_state != 'N':
                            print(f"[LIDAR Emergency Monitor] ✅ Path clear → Sending 'N'")
                            last_state = 'N'
                    
                    time.sleep(0.1)  # Gửi mỗi 100ms
                    
                except Exception as e:
                    print(f"[LIDAR Emergency Monitor] Error in loop: {e}")
                    time.sleep(0.5)
                    
    except Exception as e:
        print(f"[LIDAR Emergency Monitor] Failed to open serial port: {e}")

# Khởi động LIDAR emergency monitor thread
emergency_monitor = threading.Thread(target=lidar_emergency_monitor_thread, args=(shared_data,), daemon=True)
emergency_monitor.start()
print("[LIDAR Emergency Monitor] Thread started - Continuous S/N monitoring ENABLED")

# Đọc file HTML từ map.html
with open("map.html", "r", encoding="utf-8") as f:
    html_template = f.read()

# Đọc file HTML từ detect_web.html
with open("detect_web.html", "r", encoding="utf-8") as f:
    detect_html_template = f.read()

# Đọc file HTML từ lidar_web.html
with open("lidar_web.html", "r", encoding="utf-8") as f:
    lidar_html_template = f.read()

# Đọc file HTML từ config_web.html
with open("config_web.html", "r", encoding="utf-8") as f:
    config_html_template = f.read()

@app.route("/")
def index():
    # render_template_string để chèn API key động vào file ngoài
    return render_template_string(html_template, GOOGLE_MAPS_API_KEY=GOOGLE_MAPS_API_KEY)

@app.route("/config")
def config_page():
    # Trang cấu hình
    return render_template_string(config_html_template)

@app.route("/detection")
def detection_page():
    # Trang detection
    return render_template_string(detect_html_template)

@app.route("/lidar")
def lidar_page():
    # Trang LIDAR - Tự động bắt đầu LIDAR
    # Nếu chưa chạy thì khởi động
    if not Read_lidar.connected:
        Read_lidar.start_lidar_thread(LIDAR_PORT, LIDAR_BAUDRATE)
    return render_template_string(lidar_html_template)

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

# ===================== LIDAR ROUTES =====================
@app.route("/startLidar", methods=["POST"])
def start_lidar():
    """Bắt đầu đọc LIDAR"""
    # Sử dụng config từ file config.py
    success = Read_lidar.start_lidar_thread(LIDAR_PORT, LIDAR_BAUDRATE)
    if success:
        return Response(f"LIDAR started on {LIDAR_PORT} @ {LIDAR_BAUDRATE}", mimetype="text/plain")
    else:
        return Response("LIDAR already running", mimetype="text/plain")

@app.route("/stopLidar", methods=["POST"])
def stop_lidar():
    """Dừng đọc LIDAR"""
    Read_lidar.stop_lidar()
    return Response("LIDAR stopped", mimetype="text/plain")

@app.route("/getLidarData")
def get_lidar_data():
    """Lấy dữ liệu LIDAR hiện tại"""
    points = Read_lidar.lidar_data.get_current_points()
    return jsonify({
        'points': points,
        'connected': Read_lidar.connected
    })

@app.route("/clearLidarData", methods=["POST"])
def clear_lidar_data():
    """Xóa tất cả dữ liệu LIDAR"""
    Read_lidar.lidar_data.clear_all()
    return Response("LIDAR data cleared", mimetype="text/plain")

@app.route("/updateLidarObstacle", methods=["POST"])
def update_lidar_obstacle():
    """Cập nhật trạng thái vật cản từ LIDAR"""
    detected = request.form.get("detected", "false").lower() == "true"
    min_distance = float(request.form.get("min_distance", "9999"))
    
    # Log để debug
    if detected:
        print(f"[LIDAR] ⚠️ OBSTACLE DETECTED: {min_distance:.0f}mm")
    
    # Cập nhật vào shared_data để execute_route_commands có thể check
    shared_data.set_lidar_obstacle(detected, min_distance)
    
    return Response(f"LIDAR obstacle updated: {detected}, {min_distance}mm", mimetype="text/plain")

@app.route("/getLidarObstacleStatus")
def get_lidar_obstacle_status():
    """Lấy trạng thái vật cản hiện tại (để debug)"""
    status = shared_data.get_lidar_obstacle()
    return jsonify(status)

@app.route("/getConfig")
def get_config():
    """Lấy các giá trị cấu hình hiện tại từ runtime_settings"""
    with settings_lock:
        return jsonify(runtime_settings)

@app.route("/saveConfigRuntime", methods=["POST"])
def save_config_runtime():
    """Lưu cấu hình vào bộ nhớ (runtime) - Áp dụng ngay, mất khi restart"""
    try:
        data = request.get_json()
        print(f"[Settings] 💾 Saving to RUNTIME (temporary): {data}")
        
        # Cập nhật runtime_settings
        update_setting("TIME_PER_METER_SEC", float(data.get("TIME_PER_METER_SEC", 1.0)))
        update_setting("LIDAR_MAX_POINTS", int(data.get("LIDAR_MAX_POINTS", 1500)))
        update_setting("LIDAR_DOT_LIFETIME", float(data.get("LIDAR_DOT_LIFETIME", 1.0)))
        update_setting("LIDAR_OBSTACLE_DISTANCE", int(data.get("LIDAR_OBSTACLE_DISTANCE", 400)))
        update_setting("LIDAR_DETECTION_ANGLE_MIN", int(data.get("LIDAR_DETECTION_ANGLE_MIN", -20)))
        update_setting("LIDAR_DETECTION_ANGLE_MAX", int(data.get("LIDAR_DETECTION_ANGLE_MAX", 20)))
        
        print(f"[Settings] ✅ Runtime settings updated:")
        print(f"  - LIDAR_OBSTACLE_DISTANCE: {get_setting('LIDAR_OBSTACLE_DISTANCE')}mm")
        print(f"  - LIDAR_DETECTION_ANGLE: [{get_setting('LIDAR_DETECTION_ANGLE_MIN')}° to {get_setting('LIDAR_DETECTION_ANGLE_MAX')}°]")
        
        return jsonify({"success": True, "message": "Cấu hình đã được lưu vào bộ nhớ (tạm thời)"})
    
    except Exception as e:
        print(f"[Settings] ❌ Error saving to runtime: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "message": str(e)})

@app.route("/saveConfigPermanent", methods=["POST"])
def save_config_permanent():
    """Lưu cấu hình vào settings.json - Vĩnh viễn, không cần restart"""
    try:
        data = request.get_json()
        print(f"[Settings] 💿 Saving to settings.json (permanent): {data}")
        
        # Cập nhật runtime_settings
        update_setting("TIME_PER_METER_SEC", float(data.get("TIME_PER_METER_SEC", 1.0)))
        update_setting("LIDAR_MAX_POINTS", int(data.get("LIDAR_MAX_POINTS", 1500)))
        update_setting("LIDAR_DOT_LIFETIME", float(data.get("LIDAR_DOT_LIFETIME", 1.0)))
        update_setting("LIDAR_OBSTACLE_DISTANCE", int(data.get("LIDAR_OBSTACLE_DISTANCE", 400)))
        update_setting("LIDAR_DETECTION_ANGLE_MIN", int(data.get("LIDAR_DETECTION_ANGLE_MIN", -20)))
        update_setting("LIDAR_DETECTION_ANGLE_MAX", int(data.get("LIDAR_DETECTION_ANGLE_MAX", 20)))
        
        # Lưu vào file JSON
        if save_settings_to_json():
            print(f"[Settings] ✅ Settings saved to settings.json permanently")
            return jsonify({"success": True, "message": "Cấu hình đã được lưu vĩnh viễn vào settings.json"})
        else:
            return jsonify({"success": False, "message": "Lỗi khi ghi file settings.json"})
    
    except Exception as e:
        print(f"[Settings] ❌ Error saving permanent: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "message": str(e)})

@app.route("/resetConfig", methods=["POST"])
def reset_config():
    """Reset về cấu hình mặc định từ config.py"""
    try:
        print("[Settings] 🔄 Resetting to default values from config.py")
        
        # Load lại giá trị mặc định từ config.py
        default_settings = {
            "TIME_PER_METER_SEC": config.TIME_PER_METER_SEC,
            "LIDAR_MAX_POINTS": config.LIDAR_MAX_POINTS,
            "LIDAR_DOT_LIFETIME": config.LIDAR_DOT_LIFETIME,
            "LIDAR_OBSTACLE_DISTANCE": config.LIDAR_OBSTACLE_DISTANCE,
            "LIDAR_DETECTION_ANGLE_MIN": config.LIDAR_DETECTION_ANGLE_MIN,
            "LIDAR_DETECTION_ANGLE_MAX": config.LIDAR_DETECTION_ANGLE_MAX
        }
        
        # Cập nhật runtime_settings
        with settings_lock:
            runtime_settings.update(default_settings)
        
        # Lưu vào settings.json
        save_settings_to_json()
        
        print("[Settings] ✅ Reset to default values successfully")
        return jsonify({"success": True, "message": "Đã reset về cấu hình mặc định từ config.py"})
    
    except Exception as e:
        print(f"[Settings] ❌ Error resetting: {e}")
        return jsonify({"success": False, "message": str(e)})

if __name__ == "__main__":
    # Tự động khởi động LIDAR khi server start
    print("[LIDAR] Auto-starting LIDAR on server startup...")
    Read_lidar.start_lidar_thread(LIDAR_PORT, LIDAR_BAUDRATE)
    
    app.run(host=FLASK_HOST, port=FLASK_PORT, debug=False)
