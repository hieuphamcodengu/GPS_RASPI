# Serial cấu hình
SERIAL_PORT = "COM24"   # hoặc /dev/ttyACM0 nếu ESP32-C3 hiển thị vậy
SERIAL_BAUD = 115200

# Flask cấu hình
FLASK_HOST = "0.0.0.0"
FLASK_PORT = 5000    # dùng 5000 nếu không chạy sudo

# Google Maps
GOOGLE_MAPS_API_KEY = "AIzaSyCWxuTGtkD5O7cDqQYrsHZeajpPBZdKWnk"  # thay bằng key thật

# Timeout Serial
SERIAL_TIMEOUT_SEC = 1

# Thời gian trung bình xe đi hết 1 mét (giây)
TIME_PER_METER_SEC = 1  # chỉnh lại theo thực tế

# Cổng COM dùng để gửi lệnh điều khiển (khác cổng đọc ESP)
SERIAL_PORT_CONTROL = "COM6"  # chỉnh lại theo thực tế
SERIAL_BAUD_CONTROL = 115200  # baudrate cho cổng điều khiển

