"""환경변수 설정. 쿠버네티스에서는 Deployment의 env로 넣는다."""
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    log_level: str = "INFO"
    host: str = "0.0.0.0"
    port: int = 8090

    # 1회 결제 한도(원). 이보다 큰 결제는 거절한다. order-api의 거절(402) 흐름을 확인할 때 쓴다
    payment_limit: int = 1_000_000


@lru_cache
def get_settings() -> Settings:
    return Settings()