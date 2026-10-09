"""실행: python -m app"""
import logging

import uvicorn

from .config import get_settings


def main() -> None:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s %(message)s")
    # workers=1: 관리 API로 바꾼 설정이 프로세스 메모리에만 있어서, 워커가 여러 개면 일부에만 적용된다
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, workers=1)


if __name__ == "__main__":
    main()