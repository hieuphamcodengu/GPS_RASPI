# Serial cấu hình
SERIAL_PORT = "COM24"   # hoặc /dev/ttyACM0 nếu ESP32-C3 hiển thị vậy
SERIAL_BAUD = 115200
# Cổng COM dùng để gửi lệnh điều khiển (khác cổng đọc ESP)
SERIAL_PORT_CONTROL = "COM6"  # chỉnh lại theo thực tế
SERIAL_BAUD_CONTROL = 115200  # baudrate cho cổng điều khiển

# # Serial cấu hình
# SERIAL_PORT = "/dev/ttyACM0"   # hoặc /dev/ttyACM0 nếu ESP32-C3 hiển thị vậy
# SERIAL_BAUD = 115200
# # Cổng COM dùng để gửi lệnh điều khiển (khác cổng đọc ESP)
# SERIAL_PORT_CONTROL = "/dev/ttyUSB0"  # chỉnh lại theo thực tế
# SERIAL_BAUD_CONTROL = 115200  # baudrate cho cổng điều khiển



# Flask cấu hình
FLASK_HOST = "0.0.0.0"
FLASK_PORT = 5000    # dùng 5000 nếu không chạy sudo

# Google Maps
GOOGLE_MAPS_API_KEY = "AIzaSyCWxuTGtkD5O7cDqQYrsHZeajpPBZdKWnk"  # thay bằng key thật

# Timeout Serial
SERIAL_TIMEOUT_SEC = 1

# Thời gian trung bình xe đi hết 1 mét (giây)
TIME_PER_METER_SEC = 1.0  # chỉnh lại theo thực tế

# =====================================================
# LIDAR Configuration
# =====================================================
# Cấu hình Serial cho LIDAR
LIDAR_PORT = "COM25"           # Cổng COM kết nối LIDAR
LIDAR_BAUDRATE = 115200       # Tốc độ baudrate

# Cấu hình hiển thị LIDAR
LIDAR_MAX_POINTS = 1500       # Số điểm tối đa lưu trữ
LIDAR_DOT_LIFETIME = 1.0      # Thời gian hiển thị điểm (giây)

# Cấu hình phát hiện vật cản
LIDAR_OBSTACLE_DISTANCE = 400  # Khoảng cách phát hiện vật cản (mm)
LIDAR_DETECTION_ANGLE_MIN = -20  # Góc phát hiện tối thiểu (độ)
LIDAR_DETECTION_ANGLE_MAX = 20   # Góc phát hiện tối đa (độ)


