"""Cấu hình tập trung, đọc từ biến môi trường / .env."""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str = "sqlite:///./stock.db"

    # Data source
    data_source: str = "demo"          # "demo" | "vnstock"
    vnstock_source: str = "VCI"
    # Danh mục theo dõi khi dùng vnstock (community edition bị giới hạn rate/limit,
    # nên không quét toàn bộ ~1600 mã). Chuỗi phân tách bằng dấu phẩy.
    vnstock_watchlist: str = (            # mặc định VN30
        "ACB,BCM,BID,BVH,CTG,FPT,GAS,GVR,HDB,HPG,MBB,MSN,MWG,PLX,POW,SAB,"
        "SHB,SSB,SSI,STB,TCB,TPB,VCB,VHM,VIB,VIC,VJC,VNM,VPB,VRE")

    # Telegram
    telegram_token: str = ""
    telegram_chat_id: str = ""

    # LLM — hỗ trợ OpenAI (ChatGPT) hoặc Anthropic (Claude).
    # Tự chọn: có openai_api_key → OpenAI; else có anthropic_api_key → Claude; else quy tắc.
    # Ép cứng bằng llm_provider = "openai" | "anthropic" nếu muốn.
    llm_provider: str = ""              # "" = tự nhận diện theo key
    openai_api_key: str = ""
    openai_model: str = "gpt-5"
    # Chỉ áp dụng cho model suy luận (gpt-5*, o-series): low | medium | high
    # low = rẻ & nhanh, high = suy luận sâu & đắt. Để trống = dùng mặc định của OpenAI.
    openai_reasoning_effort: str = "medium"
    anthropic_api_key: str = ""
    llm_model: str = "claude-sonnet-5"

    # Alert thresholds
    alert_min_score: float = 75.0
    alert_volume_zscore: float = 2.0

    # AI chọn lọc cổ phiếu nên đầu tư (curation) — chỉ gửi Telegram danh sách này
    curate_top_n: int = 15                 # số ứng viên điểm cao đưa cho AI xét
    curate_min_score: float = 58.0         # ngưỡng điểm tối thiểu để lọt vòng xét
    push_individual_alerts: bool = False   # True = vẫn gửi cảnh báo lẻ như cũ (mặc định tắt)

    # Bộ quét tín hiệu MUA theo Nadaraya-Watson trên toàn thị trường (chạy ~9h30, gửi ~10h)
    nw_min_liquidity: float = 5_000_000_000.0   # GTGD tối thiểu/phiên (~5 tỷ) — mã đủ thanh khoản
    nw_min_price: float = 3_000.0               # loại cổ phiếu thị giá quá thấp
    nw_scan_max: int = 250                      # số mã phân tích sâu (giới hạn rate-limit)
    nw_top_n: int = 10                          # số mã gửi Telegram
    nw_require_uptrend: bool = True             # lọc: giá > MA200 (xu hướng tăng)
    nw_require_inflow: bool = True              # lọc: CMF20 > 0 (dòng tiền đang vào)
    # Bắt buộc PHẢI có tín hiệu BUY của NW mới lọt danh sách?
    # Mặc định TẮT: backtest cho thấy gate theo NW BUY làm KÉM ĐI có ý nghĩa thống kê
    # (alpha −2.9%, t=−2.4 ở 20 phiên khi kết hợp với lọc chất lượng). NW chỉ dùng làm bối cảnh.
    nw_require_buy_signal: bool = False

    # Bộ quét cổ phiếu penny (đầu cơ, rủi ro rất cao)
    penny_price_max: float = 10_000.0      # giá <= ngưỡng này coi là penny (VND)
    penny_min_liquidity: float = 1_000_000_000.0  # GTGD tối thiểu/phiên (~1 tỷ) để còn giao dịch được
    penny_scan_top: int = 20               # số ứng viên phân tích sâu ở tầng 2
    penny_min_upside: float = 60.0         # ngưỡng điểm tiềm năng để cảnh báo

    # Quét tin tức kinh tế (chạy 9h & 14h) → AI phân tích ảnh hưởng giá cổ phiếu
    news_scan_limit: int = 40              # số bài mới nhất phân tích mỗi lần chạy
    news_batch_size: int = 12              # số bài/1 lệnh gọi LLM (tiết kiệm chi phí)

    dashboard_base_url: str = "http://localhost:8000"

    # Celery / Redis
    redis_url: str = "redis://localhost:6379/0"

    # Scoring weights (tổng = 1.0). Có thể override qua API.
    w_fundamental: float = 0.18
    w_growth: float = 0.15
    w_health: float = 0.12
    w_valuation: float = 0.10
    w_technical: float = 0.20
    w_moneyflow: float = 0.13
    w_news: float = 0.05
    w_risk: float = 0.07
    weights_version: str = "v1"

    @property
    def weights(self) -> dict[str, float]:
        return {
            "fundamental": self.w_fundamental,
            "growth": self.w_growth,
            "health": self.w_health,
            "valuation": self.w_valuation,
            "technical": self.w_technical,
            "moneyflow": self.w_moneyflow,
            "news": self.w_news,
            "risk": self.w_risk,
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
