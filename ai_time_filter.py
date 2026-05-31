import os
import json
import time
import re
import threading
import google.generativeai as genai
from typing import List, Dict

_ai_lock = threading.Lock()

def get_ai_time_filter(places_info: List[Dict]) -> Dict[str, dict]:
    """
    Nhận danh sách địa điểm (kèm mô tả), gọi Gemini để phân loại vào morning, afternoon, evening.
    """
    if not places_info:
        return {}
        
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return {} # Fallback
        
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-3.1-flash-lite')
    
    prompt = f"""
Là chuyên gia du lịch địa phương. Hãy giúp tôi phân tích các địa điểm dưới đây:
1. Phân loại vào 3 buổi: "morning" (sáng), "afternoon" (chiều), "evening" (tối) tuỳ thuộc vào việc khách du lịch thường đi đến đó hoặc ăn món đó vào lúc nào là hợp lý nhất.
Nguyên tắc:
- morning: Bún, phở, bánh mì, hủ tiếu, cafe sáng, đền, chùa, lăng tẩm, leo núi, công viên, chợ sáng.
- afternoon: Bảo tàng, khu vui chơi trong nhà, chè, kem, ăn vặt, mua sắm, dạo biển chiều.
- evening: Nhà hàng, quán ăn chính (sushi, lẩu, nướng, hải sản), phố đi bộ, chợ đêm, bar, pub, cảnh đêm.

2. Dự đoán mức giá (estimated_price): Ước tính chi phí trung bình (ví dụ: "Miễn phí", "30.000đ - 50.000đ", "100.000đ - 250.000đ", "Từ 500.000đ").

Danh sách địa điểm (bao gồm Tên và Mô tả):
{json.dumps(places_info, ensure_ascii=False)}

Hãy trả về kết quả JSON OBJECT nguyên bản, trong đó Key là TÊN CHÍNH XÁC của địa điểm (không được đổi tên).
Value là một object gồm 2 trường: "best_time" (morning/afternoon/evening) và "estimated_price" (chuỗi mức giá).
Ví dụ:
{{
  "Nhà hàng Nhật Bản Shinosushi": {{"best_time": "evening", "estimated_price": "200.000đ - 500.000đ"}},
  "Đường đi bộ Nguyễn Đình Chiểu": {{"best_time": "evening", "estimated_price": "Miễn phí"}}
}}
"""
    with _ai_lock:
        for attempt in range(2):
            try:
                print(f"[AI Time Filter] 🚀 Đang gọi Gemini 3.1 xử lý {len(places_info)} địa điểm...")
                response = model.generate_content(
                    prompt,
                    generation_config={"response_mime_type": "application/json"}
                )
                
                text = response.text
                json_match = re.search(r'\{[\s\S]*\}', text)
                if json_match:
                    result = json.loads(json_match.group(0))
                    print(f"[AI Time Filter] ✅ AI xử lý thành công {len(places_info)} địa điểm!")
                    return result
            except Exception as e:
                err_str = str(e)
                if "429" in err_str:
                    print(f"[AI Time Filter] Hết hạn mức Gemini (429). Hủy gọi AI để dùng Fallback ngay lập tức nhằm tiết kiệm thời gian.")
                    break # Abort immediately on 429
                
                print(f"[AI Time Filter] Lỗi khi gọi Gemini: {e}. Thử lại (Attempt {attempt+1}/2)...")
                time.sleep(2)
                
        return {}
