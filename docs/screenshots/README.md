# 실행 화면

Windows에서 Streamlit을 실행하고 Chrome 브라우저로 진단 제출, 맞춤형 문제 풀이, 힌트 확인, 결과 및 로그 화면으로 이동한 기록입니다. 화면의 학습 코드는 캡처 전용 테스트 데이터입니다. 온라인 호출 화면은 로컬 모의 API를 사용합니다.

| 파일 | 화면 |
|---|---|
| [01-diagnostic.png](01-diagnostic.png) | 10문항 기초 진단평가 |
| [02-practice.png](02-practice.png) | 진단 후 분수 뺄셈 맞춤형 문제 |
| [03-hint-mock-api.png](03-hint-mock-api.png) | 오답 이후의 힌트, 검색 출처, 모의 API 표시 |
| [04-results.png](04-results.png) | 정오답, 힌트 수, 숙달도, 다음 추천 |
| [05-agent-log.png](05-agent-log.png) | 모의 API 호출을 통해 실행한 등록 도구와 결과 |

모의 API 환경을 재현하려면 저장소 루트에서 PowerShell 창 두 개를 엽니다. 첫 창에서 다음 명령을 실행합니다.

```powershell
.\.venv\Scripts\python.exe tests/mock_api.py
```

둘째 창에서 테스트용 환경 변수를 지정하고 앱을 실행합니다.

```powershell
$env:OPENAI_API_KEY = "mock-only"
$env:OPENAI_BASE_URL = "http://127.0.0.1:8765/v1"
$env:OPENAI_MODEL = "local-fixture"
$env:BRIDGE_MOCK_API = "1"
$env:BRIDGE_DB_PATH = "data/demo.sqlite3"
.\.venv\Scripts\python.exe -m streamlit run app.py
```
