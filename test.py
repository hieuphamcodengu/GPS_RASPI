import tkinter as tk
from tkinter import ttk, messagebox
import serial
import serial.tools.list_ports
import threading
import math
import re
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
import numpy as np
import time

# ==== GLOBAL ====
ser = None
connected = False
angles, distances, timestamps = [], [], []
lock = threading.Lock()
num_pattern = re.compile(r"^\s*[\d\.]+\s+[\d\.]+\s*$")
dot_lifetime = 1.0  # Thời gian hiển thị điểm (giây) - có thể điều chỉnh

show_serial = True
show_debug = True
stop_radar = threading.Event()

# ==== LOG ====
def gui_log(msg, prefix="[DEBUG] "):
    if show_debug:
        try:
            serial_text.insert(tk.END, prefix + msg + "\n")
            serial_text.see(tk.END)
            if int(serial_text.index('end-1c').split('.')[0]) > 400:
                serial_text.delete("1.0", "100.0")
        except:
            pass

def debug(msg):
    gui_log(msg, "[DEBUG] ")

# ==== SERIAL ====
def read_serial():
    global connected, ser, angles, distances, timestamps
    while connected:
        try:
            line = ser.readline().decode(errors="ignore").strip()
            if not line:
                continue
            if show_serial:
                serial_text.insert(tk.END, line + "\n")
                serial_text.see(tk.END)
                if int(serial_text.index('end-1c').split('.')[0]) > 400:
                    serial_text.delete("1.0", "100.0")

            if not num_pattern.match(line):
                continue

            parts = line.split()
            if len(parts) == 2:
                dist, ang = parts
                dist, ang = float(dist), float(ang)
                if dist > 0:
                    ang_rad = math.radians(ang)
                    with lock:
                        angles.append(ang_rad)
                        distances.append(dist)
                        timestamps.append(time.time())
                        if len(angles) > 1000:
                            angles[:] = angles[-1000:]
                            distances[:] = distances[-1000:]
                            timestamps[:] = timestamps[-1000:]
                    debug(f"Parsed: dist={dist}, ang={ang}, total={len(angles)}")
        except Exception as e:
            debug(f"Serial error: {e}")
    debug("Serial thread stopped.")

# ==== CỬA SỔ RADAR ====
def radar_window():
    stop_radar.clear()
    fig = plt.figure("ESP32 LIDAR Viewer", figsize=(6,6))
    ax = fig.add_subplot(111, polar=True)
    ax.set_theta_zero_location('N')
    ax.set_theta_direction(-1)
    ax.set_rmax(4000)
    ax.grid(True)

    points, = ax.plot([], [], 'go', markersize=4)
    text = ax.text(0.05, 1.05, "", transform=ax.transAxes)

    def update(_):
        with lock:
            current_time = time.time()
            all_angles = list(angles)
            all_distances = list(distances)
            all_timestamps = list(timestamps)

            # Lọc các điểm còn hợp lệ theo thời gian
            valid_indices = [i for i, ts in enumerate(all_timestamps) if current_time - ts < dot_lifetime]
            
            if valid_indices:
                a = np.array([all_angles[i] for i in valid_indices])
                d = np.array([all_distances[i] for i in valid_indices])
            else:
                a = np.array([])
                d = np.array([])

            if len(d) > 0:
                max_r = min(max(d) * 1.1, 4000)
                points.set_data(a, d)
            else:
                max_r = 4000
                points.set_data([], [])
                
            ax.set_rmax(max_r)
            text.set_text(f"{len(a)} điểm | lifetime: {dot_lifetime}s")
            
        return points, text

    ani = FuncAnimation(fig, update, interval=60, blit=False)
    plt.show(block=True)
    stop_radar.set()

# ==== KẾT NỐI SERIAL ====
def connect_serial():
    global ser, connected
    port, baud = com_var.get(), baud_var.get()
    try:
        ser = serial.Serial(port, baud, timeout=0.1)
        connected = True
        threading.Thread(target=read_serial, daemon=True).start()
        status_var.set(f"✅ Kết nối {port} @ {baud}")
        debug(f"Connected to {port} @ {baud}")
    except Exception as e:
        messagebox.showerror("Lỗi", str(e))
        connected = False

def disconnect_serial():
    global connected, ser
    connected = False
    if ser:
        ser.close()
        ser = None
    status_var.set("🔴 Đã ngắt kết nối")
    debug("Disconnected")

def refresh_ports():
    ports = [p.device for p in serial.tools.list_ports.comports()]
    com_menu["values"] = ports
    if ports:
        com_var.set(ports[0])
    debug(f"Ports: {ports}")

# ==== GUI TKINTER ====
root = tk.Tk()
root.title("ESP32 LIDAR Serial Reader")

main = ttk.Frame(root, padding=10)
main.pack(fill=tk.BOTH, expand=True)

# COM & Baudrate
ttk.Label(main, text="Cổng COM:").grid(row=0, column=0, sticky="w")
com_var = tk.StringVar()
com_menu = ttk.Combobox(main, textvariable=com_var, width=15)
com_menu.grid(row=0, column=1, padx=5)
ttk.Button(main, text="🔄 Làm mới", command=refresh_ports).grid(row=0, column=2, padx=5)

ttk.Label(main, text="Baudrate:").grid(row=1, column=0, sticky="w")
baud_var = tk.IntVar(value=115200)
ttk.Combobox(main, textvariable=baud_var,
             values=[9600, 57600, 115200, 230400], width=15).grid(row=1, column=1, padx=5)

ttk.Button(main, text="🔗 Kết nối", command=connect_serial).grid(row=0, column=3, padx=10)
ttk.Button(main, text="❌ Ngắt kết nối", command=disconnect_serial).grid(row=1, column=3, padx=10)

# ==== Mở cửa sổ hiển thị ====
def open_radar():
    if not connected:
        messagebox.showwarning("Chưa kết nối", "Hãy kết nối trước khi mở cửa sổ hiển thị.")
        return
    threading.Thread(target=radar_window, daemon=True).start()
    debug("LIDAR viewer window started")

ttk.Button(main, text="📡 Mở cửa sổ LIDAR", command=open_radar).grid(row=2, column=3, pady=5)

status_var = tk.StringVar(value="Chưa kết nối")
ttk.Label(main, textvariable=status_var, foreground="blue").grid(row=3, column=0, columnspan=4, pady=5)

# ==== Serial log ====
serial_frame = ttk.LabelFrame(main, text="Serial Monitor & Debug", padding=5)
serial_frame.grid(row=4, column=0, columnspan=4, pady=5, sticky="nsew")

serial_text = tk.Text(serial_frame, height=15, width=55, wrap="none")
serial_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
scroll = ttk.Scrollbar(serial_frame, command=serial_text.yview)
scroll.pack(side=tk.RIGHT, fill=tk.Y)
serial_text.configure(yscrollcommand=scroll.set)

def clear_log():
    serial_text.delete("1.0", tk.END)
ttk.Button(serial_frame, text="🧹 Clear log", command=clear_log).pack(side=tk.BOTTOM, pady=3)

def toggle_serial():
    global show_serial
    show_serial = serial_var.get()

def toggle_debug():
    global show_debug
    show_debug = debug_var.get()

serial_var = tk.BooleanVar(value=True)
debug_var = tk.BooleanVar(value=True)
ttk.Checkbutton(serial_frame, text="Hiện Serial Log", variable=serial_var, command=toggle_serial).pack(side=tk.BOTTOM, anchor="w")
ttk.Checkbutton(serial_frame, text="Hiện Debug Log", variable=debug_var, command=toggle_debug).pack(side=tk.BOTTOM, anchor="w")

refresh_ports()

# Khi đóng
def on_close():
    disconnect_serial()
    stop_radar.set()
    root.destroy()

root.protocol("WM_DELETE_WINDOW", on_close)
root.mainloop()
