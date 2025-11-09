# 🌿 Hệ Thống Phát Hiện Bệnh Cây

## � Mô tả dự án

Hệ thống phát hiện và phân loại cây bị bệnh sử dụng AI (YOLOv5 TFLite) trên Raspberry Pi 4.

**2 Classes:**
- **Class 0 (Đỏ)**: Cây bị bệnh 🔴
- **Class 1 (Xanh)**: Cây bình thường 🟢

## � Cấu trúc dự án

- `app.py` - Flask web server chính
- `detect_stream.py` - Module xử lý video stream và detection
- `detect.py` - Code detect standalone (chạy riêng)
- `detect_web.html` - Giao diện web detection
- `map.html` - Giao diện GPS map
- `classes.txt` - 2 classes: Benh, Binh_thuong
- `model.tflite` - Model AI đã train

## 🎯 Chức năng

### 1. Xem Camera (No Detection) 📹
- Stream video trực tiếp từ camera
- Không chạy AI model
- FPS cao, độ trễ thấp
- Tiết kiệm CPU

### 2. Detection Mode 🌿
- Phát hiện và phân loại cây real-time
- Vẽ bounding boxes màu:
  - **Đỏ**: Cây bị bệnh
  - **Xanh lá**: Cây bình thường
- Thống kê chi tiết:
  - FPS hiển thị
  - Số cây phát hiện
  - Số cây bị bệnh
  - Số cây bình thường
  - Thời gian inference (ms)

## 🚀 Cách chạy

### Bước 1: Cài đặt thư viện
```bash
pip install flask opencv-python numpy tflite-runtime
```

### Bước 2: Chạy Flask server
```bash
python app.py
```

### Bước 3: Truy cập web
- **Trang chủ (GPS Map)**: http://localhost:5000/
- **Trang Detection**: http://localhost:5000/detection
- Hoặc click nút **"🎯 Detection"** trong Control Panel

## 📱 Hướng dẫn sử dụng

### Bước 1: Bật camera
1. Click nút **"📹 Xem camera"**
2. Camera khởi động và stream video
3. Nút chuyển sang **"⏹️ Tắt camera"** (màu đỏ)

### Bước 2: Bật detection
1. Click nút **"🎯 Detect"**
2. Model AI bắt đầu phân tích
3. Bounding boxes xuất hiện:
   - **Đỏ**: Cây bị bệnh
   - **Xanh**: Cây bình thường
4. Thống kê hiển thị real-time

### Bước 3: Xem kết quả
- **Bảng thống kê** hiển thị:
  - FPS
  - Tổng số cây
  - Số cây bệnh (đỏ)
  - Số cây khỏe (xanh)
  - Thời gian xử lý

### Bước 4: Tắt
1. Click **"⏹️ Dừng Detect"** - Tắt detection, camera vẫn chạy
2. Click **"⏹️ Tắt camera"** - Tắt hoàn toàn
3. Click **"⬅️ Trở về"** - Quay về GPS Map

## 🎨 Màu sắc bounding boxes

```
🔴 Đỏ (BGR: 0, 0, 255)     → Class 0: Cây bị bệnh
🟢 Xanh lá (BGR: 0, 255, 0) → Class 1: Cây bình thường
```

## ⚙️ Tùy chỉnh

### Điều chỉnh độ nhạy detection
Trong `detect_stream.py`:
```python
CONF_THRESH = 0.3   # Giảm xuống 0.2 để phát hiện nhiều hơn
NMS_THRESH = 0.45   # Điều chỉnh NMS threshold
```

### Thay đổi input size
```python
INPUT_SIZE = 480  # Giảm xuống 320 nếu muốn FPS cao hơn
```

### Thay đổi skip frames
```python
SKIP_FRAMES = 2  # Tăng lên 3 để FPS cao hơn, giảm xuống 1 để chính xác hơn
```

## 📊 API Endpoints

### Detection APIs
- `GET /video_feed` - Video stream (MJPEG)
- `POST /camera_start` - Khởi động camera
- `POST /camera_stop` - Tắt camera
- `POST /start_detection` - Bật detection
- `POST /stop_detection` - Tắt detection
- `GET /detection_stats` - Lấy thống kê (JSON)

**Response của `/detection_stats`:**
```json
{
  "fps": 18.5,
  "plants_detected": 5,
  "disease_count": 2,
  "healthy_count": 3,
  "inference_time": 185
}
```

## 🔧 Troubleshooting

### Camera không khởi động
```bash
# Kiểm tra camera
ls /dev/video*

# Test camera
python -c "import cv2; print(cv2.VideoCapture(0).read())"
```

### FPS thấp
1. Giảm `INPUT_SIZE` xuống 320
2. Tăng `SKIP_FRAMES` lên 3
3. Giảm JPEG quality xuống 70

### Model báo lỗi
- Kiểm tra file `model.tflite` tồn tại
- Đảm bảo model được train với 2 classes
- Output shape phải có dimension cuối = 7 (x,y,w,h,obj_conf,class0,class1)

## � Hiệu suất kỳ vọng (Raspberry Pi 4)

- **FPS camera only**: 25-30 FPS
- **FPS detection mode**: 15-20 FPS
- **Inference time**: 150-250ms (tùy INPUT_SIZE)
- **Độ chính xác**: Tùy model training

## � Tính năng đã tối ưu

✅ Camera buffer = 1 (giảm độ trễ)  
✅ Skip frame processing (tăng FPS)  
✅ FPS counter chính xác  
✅ Multi-threading inference  
✅ Separate camera/detection mode  
✅ Real-time stats tracking  
✅ Auto cleanup  
✅ Color-coded bounding boxes  
✅ Classification counting (bệnh/khỏe)

## 📝 Ghi chú quan trọng

- Model phải được train với **2 classes**: Benh (0) và Binh_thuong (1)
- Input size phải khớp với lúc training (480x480)
- Confidence threshold có thể điều chỉnh tùy môi trường
- Bounding box màu đỏ = Bệnh, màu xanh = Bình thường

Chúc bạn phát hiện bệnh cây thành công! 🌿🚀

