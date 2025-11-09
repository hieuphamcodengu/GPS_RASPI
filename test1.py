import serial
import threading
import math
import re
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
import numpy as np
import time

# ==== CONFIG ====
PORT = "COM22"        # ⚙️ chỉnh đúng cổng của bạn
BAUD = 115200
DIST_LIMIT = 4000     # mm
POINT_MERGE_TOL = 80  # mm - nếu điểm mới gần < 80mm thì coi là cùng điểm
MAX_MEMORY = 3000     # số điểm tối đa giữ lại

# ==== DỮ LIỆU ====
points_map = {}  # key = (x, y), value = (last_seen_cycle)
cycle_id = 0
lock = threading.Lock()
num_pattern = re.compile(r"^\s*\d+\s+[\d\.]+\s+[\d\.]+\s*$")

# ==== ĐỌC SERIAL ====
def read_serial():
    global cycle_id, points_map
    ser = serial.Serial(PORT, BAUD, timeout=0.1)
    print(f"[INFO] Connected to {PORT} @ {BAUD}")

    while True:
        try:
            line = ser.readline().decode(errors="ignore").strip()
            if not line:
                continue

            # Khi có dòng báo "Scan completed"
            if "Scan completed" in line:
                with lock:
                    cycle_id += 1
                continue

            # Bỏ dòng lỗi
            if "LiDAR error" in line:
                continue

            # Lọc đúng dòng dữ liệu
            if not num_pattern.match(line):
                continue

            _, dist, ang = line.split()
            dist, ang = float(dist), float(ang)
            if dist <= 0 or dist > DIST_LIMIT:
                continue

            # Tính toạ độ (x,y)
            rad = math.radians(ang)
            x = dist * math.sin(rad)
            y = dist * math.cos(rad)

            with lock:
                # Tìm điểm gần nhất trong map (nếu có)
                found = None
                for (px, py) in points_map.keys():
                    if abs(px - x) < POINT_MERGE_TOL and abs(py - y) < POINT_MERGE_TOL:
                        found = (px, py)
                        break

                if found:
                    # cập nhật chu kỳ nhìn thấy
                    points_map[found] = cycle_id
                else:
                    points_map[(x, y)] = cycle_id

                # nếu quá nhiều điểm thì xoá bớt
                if len(points_map) > MAX_MEMORY:
                    oldest = sorted(points_map.items(), key=lambda kv: kv[1])[:len(points_map)//10]
                    for k, _ in oldest:
                        del points_map[k]

        except Exception as e:
            print("[ERR]", e)
            break


# ==== VẼ MAP ====
def terrain_viewer():
    fig, ax = plt.subplots(figsize=(6,6))
    ax.set_facecolor("black")
    ax.set_title("ESP32 LiDAR – Dynamic 2D Terrain Map", color="lime")
    ax.set_xlabel("X (mm)")
    ax.set_ylabel("Y (mm)")
    ax.set_xlim(-DIST_LIMIT, DIST_LIMIT)
    ax.set_ylim(-DIST_LIMIT, DIST_LIMIT)
    ax.set_aspect("equal")

    ax.scatter(0, 0, s=40, c='red', marker='x', label="ESP32 LiDAR")
    ax.legend(facecolor="black", edgecolor="lime", labelcolor="white")

    scatter_obj = None

    def update(_):
        nonlocal scatter_obj
        with lock:
            # xoá điểm cũ (hết hạn 2 chu kỳ)
            expired = [k for k, v in points_map.items() if v < cycle_id - 4]
            for k in expired:
                del points_map[k]

            if not points_map:
                return scatter_obj,

            xs, ys = zip(*points_map.keys())

        # vẽ lại các điểm
        if scatter_obj:
            scatter_obj.remove()
        scatter_obj = ax.scatter(xs, ys, s=6, c='lime', alpha=0.8)
        return scatter_obj,

    ani = FuncAnimation(fig, update, interval=120, blit=False, cache_frame_data=False)
    plt.show()


# ==== MAIN ====
if __name__ == "__main__":
    threading.Thread(target=read_serial, daemon=True).start()
    terrain_viewer()
