# payment-mock

S.E.R.O 테스트 환경의 가짜 외부 결제사. order-api의 결제 요청에 승인이나 거절로 답하고, 관리 API로 결제사 장애(오류율, 지연, 동시 처리 상한)를 재시작 없이 넣고 뺀다.

## 실행

Docker Desktop을 켜고 이 폴더에서

```powershell
docker compose up -d --build
```

* API 문서와 테스트 화면: http://127.0.0.1:8090/docs
* 로그 보기: `docker compose logs -f`
* 끄기: `docker compose down`
* 코드를 바꿨으면 `--build`를 붙여 다시 띄운다

## API

* `POST /payments`: 결제. 본문은 `{"order_id": "...", "amount": 25000}`
  * 설정한 지연(기본 0.8초) 뒤에 답한다
  * 승인: 200, `status`는 `APPROVED`, `payment_id`가 붙는다
  * 거절: 200, `status`는 `DECLINED`, `reason`은 `LIMIT_EXCEEDED` (금액이 `PAYMENT_LIMIT`보다 클 때)
  * 오류: 오류율만큼 `error_status`(기본 503)로 답한다
* `GET /admin/config`: 지금 장애 설정, 처리 중인 결제 수(`in_flight`), 상한 때문에 기다리는 결제 수(`waiting`)
* `POST /admin/config`: 장애 설정을 통째로 바꾼다. 보내지 않은 항목은 기본값이 된다
  * `error_rate`: 0~1, 기본 0
  * `error_status`: 500~599, 기본 503
  * `latency_ms`: 0~60000, 기본 800
  * `max_concurrency`: 1 이상, 기본 null(상한 없음). 넘친 요청은 거절하지 않고 기다린다
  * 본문 없이 보내거나 `{}`를 보내면 기본값으로 돌아간다
* `GET /healthz`: 프로세스가 응답하는지

PowerShell에서 설정 바꾸기와 되돌리기

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8090/admin/config -ContentType "application/json" -Body '{"error_rate": 0.2, "error_status": 503}'
```

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8090/admin/config
```

## 환경변수

* `PAYMENT_LIMIT`: 1회 결제 한도(원), 기본 `1000000`
* `LOG_LEVEL`, `HOST`, `PORT`: 기본 `INFO`, `0.0.0.0`, `8090`

## 지켜야 할 것

* 설정은 프로세스 메모리에만 있다. 워커 1개, 레플리카 1개로 돌린다 (여러 개면 관리 API가 그중 하나에만 적용된다)
* 다시 시작하면 설정은 기본값으로 돌아간다
* 관리 API는 시나리오 러너만 부른다. 쿠버네티스에서는 pg-external 네임스페이스에 두고 Ingress로 열지 않는다
* 계측과 로그 수집은 하지 않는다. 에이전트는 order-api 쪽에 나타난 결제 오류와 지연만 보고 원인을 짚어야 한다

## 장애 시나리오와의 관계

* S11 결제사 5xx: `error_rate`, `error_status`
* S12 결제사 지연: `latency_ms` (예: 3000)
* S13 결제사 연결 불가: 설정이 아니라 레플리카 0으로
* S27 재시도 폭주: `max_concurrency`와 짧은 지연 상승