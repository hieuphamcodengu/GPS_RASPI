import serial
import serial.tools.list_ports
import threading
import math
import re
import time
from config import LIDAR_MAX_POINTS, LIDAR_DOT_LIFETIME

class LidarData:
    """Class lưu trữ dữ liệu LIDAR"""
    def __init__(self):
        self.lock = threading.Lock()
        self.angles = []  # Danh sách góc (radian)
        self.distances = []  # Danh sách khoảng cách (mm)
        self.timestamps = []  # Danh sách thời gian
        self.max_points = LIDAR_MAX_POINTS
        self.dot_lifetime = LIDAR_DOT_LIFETIME
        
    def add_point(self, angle_deg, distance_mm):
        """Thêm 1 điểm LIDAR mới"""
        with self.lock:
            angle_rad = math.radians(angle_deg)
            current_time = time.time()
            
            self.angles.append(angle_rad)
            self.distances.append(distance_mm)
            self.timestamps.append(current_time)
            
            # Giới hạn số điểm
            if len(self.angles) > self.max_points:
                self.angles.pop(0)
                self.distances.pop(0)
                self.timestamps.pop(0)
    
    def get_current_points(self):
        """Lấy các điểm còn hợp lệ (trong khoảng thời gian dot_lifetime)"""
        with self.lock:
            current_time = time.time()
            valid_points = []
            
            for i in range(len(self.angles)):
                if current_time - self.timestamps[i] < self.dot_lifetime:
                    valid_points.append({
                        'angle': math.degrees(self.angles[i]),  # Chuyển về độ để gửi lên web
                        'distance': self.distances[i],
                        'age': current_time - self.timestamps[i]
                    })
            
            return valid_points
    
    def clear_all(self):
        """Xóa tất cả dữ liệu"""
        with self.lock:
            self.angles.clear()
            self.distances.clear()
            self.timestamps.clear()

# Global instance
lidar_data = LidarData()
ser = None
connected = False
num_pattern = re.compile(r"^\s*[\d\.]+\s+[\d\.]+\s*$")

def read_lidar_serial(port, baudrate):
    """Hàm đọc dữ liệu từ LIDAR qua Serial"""
    global ser, connected
    
    try:
        ser = serial.Serial(port, baudrate, timeout=0.1)
        connected = True
        print(f"[LIDAR] Connected to {port} @ {baudrate}")
        
        while connected:
            try:
                line = ser.readline().decode(errors="ignore").strip()
                if not line:
                    continue
                
                # Kiểm tra pattern: "khoảng_cách góc"
                if not num_pattern.match(line):
                    continue
                
                parts = line.split()
                if len(parts) == 2:
                    dist, ang = parts
                    dist, ang = float(dist), float(ang)
                    if dist > 0:
                        lidar_data.add_point(ang, dist)
                        # print(f"[LIDAR] angle={ang}°, distance={dist}mm")
                        
            except Exception as e:
                print(f"[LIDAR] Read error: {e}")
                
    except Exception as e:
        print(f"[LIDAR] Connection error: {e}")
        connected = False
    finally:
        if ser:
            ser.close()
        connected = False
        print("[LIDAR] Serial connection closed")

def start_lidar_thread(port="COM3", baudrate=115200):
    """Bắt đầu luồng đọc LIDAR"""
    global connected
    if not connected:
        t = threading.Thread(target=read_lidar_serial, args=(port, baudrate), daemon=True)
        t.start()
        print(f"[LIDAR] Thread started on {port}")
        return True
    return False

def stop_lidar():
    """Dừng đọc LIDAR"""
    global connected, ser
    connected = False
    if ser:
        ser.close()
    print("[LIDAR] Stopped")

def get_available_ports():
    """Lấy danh sách cổng COM khả dụng"""
    ports = [p.device for p in serial.tools.list_ports.comports()]
    return ports

# Test code
if __name__ == "__main__":
    print("Available COM ports:", get_available_ports())
    
    # Thử kết nối
    port = input("Enter COM port (e.g., COM3): ").strip()
    baudrate = int(input("Enter baudrate (default 115200): ").strip() or "115200")
    
    start_lidar_thread(port, baudrate)
    
    try:
        while True:
            time.sleep(2)
            points = lidar_data.get_current_points()
            print(f"[DEBUG] Current points: {len(points)}")
            if points:
                print(f"[DEBUG] Sample point: {points[0]}")
    except KeyboardInterrupt:
        print("\nStopping...")
        stop_lidar()
