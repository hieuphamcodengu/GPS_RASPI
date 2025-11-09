# 🚀 Hướng Dẫn Sử Dụng Detection Web

## 📋 Cấu trúc dự án

- `app.py` - Flask web server chính
- `detect_stream.py` - Module xử lý video stream và detection
- `detect.py` - Code detect gốc (standalone)
- `detect_web.html` - Giao diện web detection
- `map.html` - Giao diện GPS map
- `classes.txt` - Danh sách tên các class

## 🎯 Chức năng

### 1. Xem Camera (No Detection)
- Chỉ stream video trực tiếp từ camera
- Không chạy AI model
- FPS cao, độ trễ thấp

### 2. Detection Mode
- Phát hiện và phân loại vật thể real-time
- Vẽ bounding boxes
- Hiển thị thống kê: FPS, số vật phát hiện, thời gian inference

## 🚀 Cách chạy

### Bước 1: Cài đặt thư viện (nếu chưa có)
```bash
pip install flask opencv-python numpy tflite-runtime
```

### Bước 2: Chạy Flask server
```bash
python app.py
```

### Bước 3: Truy cập web
- Trang chủ (GPS Map): http://localhost:5000/
- Trang Detection: http://localhost:5000/detection
- Hoặc click nút "🎯 Detection" trong Control Panel

## 📱 Sử dụng giao diện Detection

1. **Nhấn "📹 Xem camera"**
   - Camera khởi động
   - Video stream hiển thị (chưa có detection)
   - Nút chuyển sang màu đỏ "⏹️ Tắt camera"

2. **Nhấn "🎯 Detect"**
   - Bật detection
   - Model AI bắt đầu phân tích
   - Bounding boxes xuất hiện
   - Thống kê được cập nhật real-time

3. **Nhấn "⏹️ Dừng Detect"**
   - Tắt detection
   - Quay về chế độ xem camera thường

4. **Nhấn "⏹️ Tắt camera"**
   - Tắt camera hoàn toàn
   - Giải phóng tài nguyên

5. **Nhấn "⬅️ Trở về"**
   - Quay về trang GPS Map

## ⚙️ Tùy chỉnh

### Thay đổi độ nhạy detection
Trong `detect_stream.py`:
```python
CONF_THRESH = 0.3  # Giảm xuống 0.2 để phát hiện nhiều hơn
NMS_THRESH = 0.45  # Giảm để loại bỏ ít boxes hơn
```

### Thay đổi input size (tăng độ chính xác nhưng giảm FPS)
```python
INPUT_SIZE = 480  # Tăng lên 640 nếu Pi4 đủ mạnh
```

### Thay đổi skip frames (tăng FPS hiển thị)
```python
SKIP_FRAMES = 2  # Tăng lên 3 để FPS cao hơn
```

## 📊 API Endpoints

### Detection APIs
- `GET /video_feed` - Video stream (MJPEG)
- `POST /camera_start` - Khởi động camera
- `POST /camera_stop` - Tắt camera
- `POST /start_detection` - Bật detection
- `POST /stop_detection` - Tắt detection
- `GET /detection_stats` - Lấy thống kê (JSON)

### GPS APIs (từ trước)
- `GET /getGpsData` - Lấy tọa độ GPS
- `GET /getYaw` - Lấy góc yaw
- `POST /postData` - Gửi dữ liệu route
- `POST /startRoute` - Bắt đầu di chuyển

## 🔧 Troubleshooting

### Camera không khởi động
```bash
# Kiểm tra camera có hoạt động không
ls /dev/video*

# Test camera
python -c "import cv2; print(cv2.VideoCapture(0).read())"
```

### FPS thấp
1. Giảm `INPUT_SIZE` xuống 320 hoặc 416
2. Tăng `SKIP_FRAMES` lên 3
3. Giảm chất lượng JPEG trong `detect_stream.py`:
   ```python
   cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
   ```

### Model không load được
- Kiểm tra file `model.tflite` tồn tại
- Kiểm tra đã cài `tflite-runtime`
- Thử chạy `detect.py` standalone để test model

## 📝 Notes

- Camera chỉ mở khi nhấn nút "Xem camera"
- Detection chỉ chạy khi đã bật camera
- Tự động cleanup khi thoát trang
- Stats cập nhật mỗi 0.5 giây
- Video quality: JPEG 85%

## 🎨 Tính năng đã tối ưu

✅ Camera buffer size = 1 (giảm độ trễ)
✅ Skip frame processing (tăng FPS hiển thị)
✅ FPS counter chính xác
✅ Multi-threading inference
✅ Separate camera mode và detection mode
✅ Real-time stats update
✅ Auto cleanup on page exit

Chúc bạn thành công! 🚀
