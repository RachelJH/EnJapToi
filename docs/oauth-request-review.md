# 치지직 인증 코드 교환 요청 대조

## 확인한 공식 근거

- [Authorization](https://chzzk.gitbook.io/chzzk/chzzk-api/authorization): 브라우저 인증 요청과 토큰 발급/갱신.
- [API 공통 규격](https://chzzk.gitbook.io/chzzk/chzzk-api/tips): Open API 도메인과 Content-Type, 일반 인증 유형.

아래는 확인한 문서에 근거한 비교이며, 실제 계정으로 성공한 요청 기록은 아닙니다.

| 항목 | 공식 문서 | 현재 요청 | 결과 |
|---|---|---|---|
| 토큰 URL | 공통 도메인 `https://openapi.chzzk.naver.com` + `/auth/v1/token` | `https://openapi.chzzk.naver.com/auth/v1/token` | 일치 |
| 메서드 | POST | POST | 일치 |
| Content-Type | application/json | application/json | 일치 |
| 본문 | Request Body에 필드 나열 | UTF-8 JSON body | 일치 |
| grantType | authorization_code | authorization_code | 일치 |
| clientId / clientSecret | JSON 본문에 나열 | 둘 다 JSON 본문으로 전달 | 일치, 단 기존 출처 혼합 버그 수정 |
| code / state | JSON 본문에 나열 | 콜백 code, 검증한 원래 state 전달 | 일치 |
| redirectUri | 브라우저 인증 요청의 필수 파라미터이며 등록 URL과 동일해야 함 | 브라우저 요청에 고정 콜백 URL 사용 | 일치 |

토큰 발급 문서에는 별도의 Required 열이 없으며 본문에 위 5개 필드를 나열합니다. 현재 코드는 모두 보냅니다. redirectUri는 인증 시작 요청에 명시돼 있지만 토큰 발급 본문 목록에는 없습니다. 일반 OAuth의 redirect_uri, scope 등을 근거 없이 추가하지 않았습니다.

공통 문서의 Client 인증 헤더(Client-Id/Client-Secret)는 Client 인증 API 규격입니다. 토큰 발급 문서는 클라이언트 정보를 JSON 본문으로 나열하고 별도 헤더의 필수 여부를 명시하지 않습니다. 이 헤더 누락이 401의 원인이라고 단정할 근거가 없어 요청 형식을 임의로 바꾸지 않았습니다. 토큰 발급 전 Access Token이 없으므로 임의 Bearer 헤더도 추가하지 않았습니다.

## 코드에서 확인해 수정한 문제

기존 credentials()는 Client ID와 Secret을 각각 `환경변수 값 or 파일 값`으로 골랐습니다. 환경변수 한쪽과 파일의 다른 쪽이 섞일 수 있어, 환경변수의 앱 A ID + 파일의 앱 B Secret이 한 요청으로 전송될 수 있었습니다.

이제 환경변수를 사용한다면 **비어 있지 않은 두 값이 모두 있어야** 합니다. 한쪽만 설정됐거나 비어 있으면 CLIENT_CONFIG_PAIR 오류로 요청 전에 중단합니다. 환경변수가 모두 없으면 파일의 한 쌍을 사용합니다. 환경변수의 완전한 한 쌍이 파일보다 우선한다는 기존 동작은 유지합니다. 값은 출력하지 않습니다.

이 버그는 코드와 모의 테스트로 확인했지만, 사용자가 겪은 401의 실제 원인이라고 확정하지 않습니다. 두 환경변수가 모두 오래된 값으로 설정됐다면 파일을 확인해도 환경변수 쌍이 우선합니다. 앱 설정을 다시 바꾸기 전에 사용 중인 입력 출처부터 확인해야 합니다.

## 비밀값 없이 파일만 사용해 확인하기 (Windows)

다음 명령은 현재 PowerShell의 두 환경변수를 제거할 뿐 값을 출력하지 않습니다. 실행 중인 Paper/수신기를 정상 종료한 상태에서 수행하세요.

```powershell
Remove-Item Env:CHZZK_CLIENT_ID, Env:CHZZK_CLIENT_SECRET -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe bridge/oauth.py login --config bridge\.local\client.json
```

이미 받은 인증 코드나 실패한 인증 URL을 재사용하지 말고 새 로그인 흐름을 사용합니다. 실제 로그인 실행은 이 조사에서 수행하지 않았습니다. API의 HTTP 상태만으로 서버의 상세 거부 이유, 문서와 실서버 사이 차이, 클라이언트 유효성 등을 확정할 수 없습니다. 원본 응답이나 인증 코드를 로그에 추가해 확인하지 않습니다.

## 추가 검증

- 실제 localhost 콜백에서 특수문자/UTF-8 인증 코드를 파싱한 뒤 모의 토큰 API로 직렬화해 URL·메서드·Content-Type·5개 필드·state 일치와 단일 호출 확인.
- 갱신 요청의 URL·POST·JSON과 grantType/clientId/clientSecret/refreshToken 4개 필드 확인.
- 환경변수 한쪽만 설정한 경우 파일과 혼합하지 않고 차단, 완전한 환경변수 쌍과 파일 쌍의 기존 우선순위 확인.
- TLS 검증·리디렉션 차단·state 검증·단일 콜백·재시도 금지·민감정보 미출력 회귀 테스트 유지.
