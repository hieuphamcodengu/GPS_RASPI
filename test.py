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
angles, distances = [], []
lock = threading.Lock()
num_pattern = re.compile(r"^\s*\d+\s+[\d\.]+\s+[\d\.]+\s*$")

show_serial = True
show_debug = True
stop_radar = threading.Event()
scan_mode = "dot"   # "dot" hoặc "sweep"

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
    global connected, ser, angles, distances
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
            if len(parts) == 3:
                _, dist, ang = parts
                dist, ang = float(dist), float(ang)
                if dist > 0:
                    with lock:
                        angles.append(math.radians(ang))
                        distances.append(dist)
                        if len(angles) > 1000:
                            angles[:] = angles[-1000:]
                            distances[:] = distances[-1000:]
                    debug(f"Parsed: dist={dist}, ang={ang}, total={len(angles)}")
        except Exception as e:
            debug(f"Serial error: {e}")
    debug("Serial thread stopped.")

# ==== CỬA SỔ RADAR ====
def radar_window():
    stop_radar.clear()
    fig = plt.figure("ESP32 LIDAR Radar Viewer", figsize=(6,6))
    ax = fig.add_subplot(111, polar=True)
    ax.set_theta_zero_location('N')
    ax.set_theta_direction(-1)
    ax.set_rmax(4000)
    ax.grid(True)

    points, = ax.plot([], [], 'go', markersize=3)
    beam_line, = ax.plot([], [], 'lime', lw=2)
    text = ax.text(0.05, 1.05, "", transform=ax.transAxes)
    fade_memory = []
    fade_scatters = []  # lưu các scatter đang vẽ để xóa an toàn

    def update(_):
        global scan_mode
        with lock:
            if not angles:
                return points, beam_line, text

            a = np.array(angles)
            d = np.array(distances)
            max_r = min(max(d) * 1.1, 4000)
            ax.set_rmax(max_r)

            # Xóa các scatter cũ an toàn
            for scat in fade_scatters:
                scat.remove()
            fade_scatters.clear()

            if scan_mode == "dot":
                # Chế độ chấm
                points.set_data(a, d)
                beam_line.set_data([], [])
                fade_memory.clear()

            else:
                # Chế độ radar xoay
                t = time.time() % 5  # 5s cho 1 vòng
                sweep_angle = (t / 5) * 2 * np.pi
                beam_line.set_data([sweep_angle, sweep_angle], [0, max_r])

                # Lưu vùng quét mờ dần
                fade_memory.append((a, d, time.time()))
                # Xoá vùng cũ quá 1s
                fade_memory[:] = [(x, y, ts) for x, y, ts in fade_memory if time.time() - ts < 1.0]

                for x, y, ts in fade_memory:
                    alpha = 1.0 - (time.time() - ts)
                    s = ax.scatter(x, y, c='lime', s=8, alpha=max(alpha, 0))
                    fade_scatters.append(s)

            text.set_text(f"{len(a)} pts | mode: {scan_mode}")
        return points, beam_line, text

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
root.title("ESP32 LIDAR Serial Reader (Chế độ quét)")

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

# ==== Chọn chế độ quét ====
ttk.Label(main, text="Chế độ quét:").grid(row=2, column=0, sticky="w")
scan_mode_var = tk.StringVar(value="dot")
ttk.Radiobutton(main, text="Kiểu chấm", variable=scan_mode_var, value="dot").grid(row=2, column=1, sticky="w")
ttk.Radiobutton(main, text="Kiểu radar (vệt xoay)", variable=scan_mode_var, value="sweep").grid(row=2, column=2, sticky="w")

def update_mode():
    global scan_mode
    scan_mode = scan_mode_var.get()
    debug(f"Chuyển chế độ sang: {scan_mode}")

ttk.Button(main, text="Áp dụng chế độ", command=update_mode).grid(row=2, column=3, padx=10)

# ==== Mở radar window ====
def open_radar():
    if not connected:
        messagebox.showwarning("Chưa kết nối", "Hãy kết nối trước khi mở radar.")
        return
    threading.Thread(target=radar_window, daemon=True).start()
    debug("Radar window started")

ttk.Button(main, text="📡 Mở cửa sổ Radar", command=open_radar).grid(row=3, column=3, pady=5)

status_var = tk.StringVar(value="Chưa kết nối")
ttk.Label(main, textvariable=status_var, foreground="blue").grid(row=4, column=0, columnspan=4, pady=5)

# ==== Serial log ====
serial_frame = ttk.LabelFrame(main, text="Serial Monitor & Debug", padding=5)
serial_frame.grid(row=5, column=0, columnspan=4, pady=5, sticky="nsew")

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
