import json
import serial
import threading
from time import sleep
from config import SERIAL_PORT, SERIAL_BAUD, SERIAL_TIMEOUT_SEC, TIME_PER_METER_SEC, SERIAL_PORT_CONTROL, SERIAL_BAUD_CONTROL

class SerialData:
    """Bộ nhớ chia sẻ để lưu dữ liệu GPS mới nhất từ ESP32"""
    def __init__(self):
        self.latest = {"lat": 21.0278, "lon": 105.8342, "yaw": 0.0}
        self.lock = threading.Lock()
        # Thêm biến điều khiển route
        self.route_running = False
        self.route_paused = False
        self.route_stopped = False
        self.current_step = 0
        self.total_steps = 0
        self.current_action = "Chờ lệnh..."
        self.distance_remaining = 0.0

    def update(self, data: dict):
        with self.lock:
            self.latest.update(data)

    def snapshot(self):
        with self.lock:
            return dict(self.latest)
    
    def set_route_state(self, running=None, paused=None, stopped=None):
        with self.lock:
            if running is not None:
                self.route_running = running
            if paused is not None:
                self.route_paused = paused
            if stopped is not None:
                self.route_stopped = stopped
    
    def get_route_state(self):
        with self.lock:
            return {
                "running": self.route_running,
                "paused": self.route_paused,
                "stopped": self.route_stopped,
                "current_step": self.current_step,
                "total_steps": self.total_steps,
                "current_action": self.current_action,
                "distance_remaining": self.distance_remaining
            }
    
    def update_route_progress(self, step, total, action, distance_remaining=0.0):
        with self.lock:
            self.current_step = step
            self.total_steps = total
            self.current_action = action
            self.distance_remaining = distance_remaining

def start_serial_thread(shared_data: SerialData):
    """Luồng đọc dữ liệu GPS và góc quay từ ESP32"""
    while True:
        try:
            with serial.Serial(SERIAL_PORT, SERIAL_BAUD, timeout=SERIAL_TIMEOUT_SEC) as ser:
                while True:
                    line = ser.readline().decode(errors="ignore").strip()
                    if not line:
                        continue
                    # In ra giá trị thô nhận được để debug
                    # print(f"[Serial] Raw: {line}")
                    try:
                        # Dữ liệu dạng: yaw,lat,lon,speed
                        parts = line.split(",")
                        if len(parts) >= 3:
                            yaw = float(parts[0])
                            lat = float(parts[1])
                            lon = float(parts[2])
                            # Nếu lat/lon đều 0 thì bỏ qua (giữ tọa độ cũ)
                            if lat == 0.0 and lon == 0.0:
                                data = {"yaw": yaw}  # chỉ cập nhật yaw
                            else:
                                data = {"lat": lat, "lon": lon, "yaw": yaw}
                            shared_data.update(data)
                    except (ValueError, IndexError) as e:
                        print(f"[Serial] Parsing error: {e} -> '{line}'")
        except Exception as e:
            print(f"[Serial] Error: {e}. Reconnecting in 2s...")
            sleep(2)
def execute_route_commands(shared_data: SerialData, dis_list, dir_list, dir_value_list):
    """
    Thực thi tuần tự các lệnh điều khiển xe dựa trên các mảng dis, dir, dir_value.
    dis_list: [quãng đường di chuyển]
    dir_list: [hướng rẽ: -1 trái, 1 phải, 0 đi thẳng/dừng]
    dir_value_list: [góc quay (độ)]
    """
    try:
        print("[Serial] === Route execution started ===")
        shared_data.set_route_state(running=True, paused=False, stopped=False)
        shared_data.update_route_progress(0, len(dis_list), "Bắt đầu hành trình...")
        
        with serial.Serial(SERIAL_PORT_CONTROL, SERIAL_BAUD_CONTROL, timeout=SERIAL_TIMEOUT_SEC) as ser:
            for i in range(len(dis_list)):
                # Kiểm tra nếu bị dừng
                if shared_data.get_route_state()["stopped"]:
                    print("[Serial] Route stopped by user")
                    ser.write(b'S')  # Gửi lệnh dừng
                    shared_data.update_route_progress(i, len(dis_list), "Đã dừng")
                    break
                
                distance = float(dis_list[i])
                direction = int(dir_list[i])
                angle = float(dir_value_list[i])

                print(f"[Serial] Step {i+1}/{len(dis_list)}: dis={distance:.2f}, dir={direction}, angle={angle:.2f}")

                # Bước 1: Đi tiến - gửi 'T' liên tục
                shared_data.update_route_progress(i+1, len(dis_list), f"Đi thẳng", distance)
                ser.write(b'T')
                print(f"[Serial] Send: T (forward {distance:.2f}m)")
                total_time = TIME_PER_METER_SEC * distance
                elapsed = 0
                interval = 0.1  # gửi lệnh mỗi 0.1s
                
                while elapsed < total_time:
                    # Kiểm tra pause
                    while shared_data.get_route_state()["paused"]:
                        ser.write(b'S')  # Dừng xe
                        shared_data.update_route_progress(i+1, len(dis_list), "Đang tạm dừng...", distance * (1 - elapsed/total_time))
                        sleep(0.1)
                    
                    # Kiểm tra stop
                    if shared_data.get_route_state()["stopped"]:
                        ser.write(b'S')
                        shared_data.update_route_progress(i+1, len(dis_list), "Đã dừng")
                        print("[Serial] Route stopped during movement")
                        return
                    
                    ser.write(b'T')
                    remaining_distance = distance * (1 - elapsed/total_time)
                    shared_data.update_route_progress(i+1, len(dis_list), f"Đi thẳng", remaining_distance)
                    sleep(interval)
                    elapsed += interval
                
                shared_data.update_route_progress(i+1, len(dis_list), f"Đã đi xong {distance:.2f}m", 0)
                
                # Bước 2: Kiểm tra xem có cần quay không
                if direction != 0:
                    # Kiểm tra stop trước khi quay
                    if shared_data.get_route_state()["stopped"]:
                        ser.write(b'S')
                        shared_data.update_route_progress(i+1, len(dis_list), "Đã dừng")
                        return
                    
                    turn_direction = "trái" if direction == -1 else "phải"
                    shared_data.update_route_progress(i+1, len(dis_list), f"Quay {turn_direction} {angle:.2f}°")
                    
                    # Quay trái/phải - gửi 'L' hoặc 'R' liên tục
                    cmd = b'L' if direction == -1 else b'R'
                    print(f"[Serial] Send: {cmd.decode()} (turn {angle:.2f}°)")
                    
                    # Đọc giá trị yaw hiện tại
                    start_yaw = shared_data.snapshot().get("yaw", 0.0)
                    target_yaw = start_yaw + angle if direction == -1 else start_yaw - angle
                    
                    # Xử lý góc quay tròn
                    if target_yaw < 0:
                        target_yaw += 360
                    elif target_yaw >= 360:
                        target_yaw -= 360
                    
                    print(f"[Serial] Start yaw: {start_yaw:.2f}°, Target yaw: {target_yaw:.2f}°, Need to turn: {angle:.2f}°")
                    
                    while True:
                        # Kiểm tra pause
                        while shared_data.get_route_state()["paused"]:
                            ser.write(b'S')
                            shared_data.update_route_progress(i+1, len(dis_list), "Đang tạm dừng...")
                            sleep(0.1)
                        
                        # Kiểm tra stop
                        if shared_data.get_route_state()["stopped"]:
                            ser.write(b'S')
                            shared_data.update_route_progress(i+1, len(dis_list), "Đã dừng")
                            return
                        
                        current_yaw = shared_data.snapshot().get("yaw", 0.0)
                        
                        # Tính góc đã quay được
                        if direction == -1:  # Quay trái (yaw tăng)
                            diff = current_yaw - start_yaw
                        else:  # Quay phải (yaw giảm)
                            diff = start_yaw - current_yaw
                        
                        # Đảm bảo diff >= 0 (bỏ qua nhiễu âm)
                        if diff < 0:
                            diff = 0
                        
                        remaining_angle = angle - diff
                        shared_data.update_route_progress(i+1, len(dis_list), f"Quay {turn_direction} (còn {remaining_angle:.1f}°)")
                        
                        print(f"[Serial] Start: {start_yaw:.2f}°, Current: {current_yaw:.2f}°, Target: {target_yaw:.2f}°, Turned: {diff:.2f}°/{angle:.2f}°")
                        
                        if diff >= angle:
                            print(f"[Serial] Done turn {angle:.2f}° (yaw={current_yaw:.2f})")
                            shared_data.update_route_progress(i+1, len(dis_list), f"Đã quay xong {angle:.2f}°")
                            break
                        
                        ser.write(cmd)  # gửi lệnh quay liên tục
                        sleep(0.05)
                else:
                    print(f"[Serial] No turn needed (final destination or straight path)")
            
            # Kết thúc hành trình
            ser.write(b'S')  # Dừng xe
            shared_data.set_route_state(running=False)
            shared_data.update_route_progress(len(dis_list), len(dis_list), "Hoàn thành hành trình!")
            print("[Serial] === Route execution finished ===")
            
    except Exception as e:
        print(f"[Serial] Route execution error: {e}")
        shared_data.set_route_state(running=False, stopped=True)
        shared_data.update_route_progress(0, 0, f"Lỗi: {str(e)}")
