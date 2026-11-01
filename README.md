# 엔잡퇴 v0.1 — Paper 플러그인 소스 + 로컬 후원 시뮬레이터

**상태: Java 25 빌드·Paper 26.3 빌드 230 서버 통합 검증 완료·게임 내 효과 미검증 개발 초안. 공식 치지직 OAuth·실시간 후원 수신기를 포함하며, 실제 계정·후원 및 금액 대응은 추가 검증이 필요합니다.**

대상: Windows / Java 25 / 사용자 제공 Paper 26.3 / 방송인 `Yirue`.

## 포함된 것
- Paper 플러그인 Java 소스, Maven 설정, `plugin.yml`, `config.yml`
- 로컬 HTTP 이벤트 수신기 (`127.0.0.1:18765`, 비밀 토큰 인증)
- 10개 게임 이벤트 및 운영 명령어 `/ejt pause`, `/ejt resume`, `/ejt status`, `/ejt reload`, `/ejt test <event>`
- 이벤트 대기열, 이벤트 ID 중복 방지용 상태 파일, 오프라인 대기, 3초 간격 처리
- Python 표준 라이브러리 기반 **모의 후원** 송신기

## 빌드 (친구 Windows PC)
1. Java 25와 Maven 3.9+ 설치. `java -version`, `mvn -version` 확인.
2. `paper-plugin` 폴더에서 `mvn clean package` 실행.
3. `target/enjaptoi-0.1.0.jar` 파일을 Paper 서버의 `plugins` 폴더로 복사하고 서버 재시작.
4. 서버 콘솔에서 `version` 명령으로 Paper 버전을 확인. API 의존성은 공식 저장소의 `26.3.build.230-stable`로 고정했습니다. 운영 대상인 Paper 26.3 빌드 230과 대응합니다. `plugin.yml`의 `api-version: '26.3'`과 실제 서버 로딩도 확인하세요.
5. 서버 시작 후 `plugins/EnJapToi/bridge-token.txt`가 자동 생성되는지 확인. 이 파일은 타인에게 공유하지 마세요.
6. 콘솔에서 `ejt status`, 게임에서 OP 권한으로 `/ejt test bread` 테스트. 방송인 Yirue가 접속해 있어야 효과 적용.

## 로컬 후원 테스트
Python 3.10+ 설치 후, **서버가 실행 중인 친구 PC**에서 다음을 실행합니다. 경로는 실제 서버 경로로 변경하세요.

```powershell
python bridge\bridge.py --amount 1000 --message "!밥" --token-file "C:\\MinecraftServer\\plugins\\EnJapToi\\bridge-token.txt"
python bridge\bridge.py --amount 5000 --message "!랜덤즉사" --token-file "C:\\MinecraftServer\\plugins\\EnJapToi\\bridge-token.txt" --id sample1
```

두 번째 명령을 같은 `--id sample1`로 반복하면 중복으로 인식되어야 합니다.

## 클라우드 빌드 검증
- Java 25 / Maven 3.9.11에서 `paper-plugin` 디렉터리의 `mvn -B -U -s /workspace/setup/maven-settings.xml package` 성공. 클라우드에서는 먼저 `source /workspace/setup/activate.sh`를 실행합니다. 일반 개발 환경은 해당 프록시 설정 없이 `mvn -B -U package`를 사용합니다.
- Paper 26.1 이후 Maven 버전 표기([공식 문서](https://docs.papermc.io/paper/dev/project-setup/))를 따르며, 가변 범위 `[26.3.build,)` 대신 검증한 `26.3.build.230-stable`을 고정해 사용합니다. 저장소는 `https://repo.papermc.io/repository/maven-public/`, Java 타깃은 25입니다.
- 산출물: `paper-plugin/target/enjaptoi-0.1.0.jar`. JAR 무결성, 플러그인 클래스·설정 포함, Java 25 바이트코드를 확인했습니다.
- Python 송신기의 명령어 10개, 선택 규칙 4개, 임시 HTTP 모의 수신기로의 CLI 전송을 검증했습니다. 이 모의 수신기 검증과 별도로, Paper 26.3 빌드 230에서 실제 브리지 전송도 확인했습니다.
- Java 저장/HTTP/강제 종료 복구 자동 테스트 16개가 통과했습니다. Paper 26.3 빌드 230 / API 230에서 플러그인 활성화, `ejt status`, 토큰 생성, `!밥` 후원의 `queued` 응답, 동일 ID의 `duplicate` 응답, 플레이어 0명 상태의 대기열 저장 및 정상 재시작 후 보존을 검증했습니다. 실제 플레이어가 접속하지 않아 게임 효과는 미검증입니다.

## 명령어 규칙
- 1000: `!버프`, `!이동`, `!밥`, `!다곡`; 메시지에 명령어가 없으면 4종 균등 룰렛.
- 2000: `!몹`, `!디버프` (명령어 필수).
- 5000: `!삭제`, `!랜덤즉사`, `!지상` (명령어 필수).
- 30000: 메시지 무관 즉사.
- 메시지의 공백으로 분리된 정확한 명령어만 인식하며 여러 명령어가 있으면 첫 번째를 사용.

## 반드시 해결해야 할 항목
1. **실제 치지직 계정·후원 미검증.** 공식 세션 수신기를 추가했지만 금액 대응과 실제 Scope 승인·후원 수신은 실행 PC에서 검증해야 합니다. 공식 후원 고유 ID와 누락분 재생 명세가 없어 완전한 중복·누락 방지를 보장하지 않습니다. `bridge.py`는 계속 로컬 시뮬레이터입니다.
2. **실제 게임 효과 미검증.** Paper 26.3 빌드 230에서 서버 통합 검증을 완료했으며, 플레이어가 접속한 상태의 게임 효과와 비정상 종료 시 복구는 별도 테스트가 필요합니다.
3. SQLite로 수신 기록과 실행 의도를 저장합니다. 강제 종료 시 불확실한 RUNNING은 UNCERTAIN으로 보류하며 자동 재실행하지 않습니다. 게임 효과와 월드 저장은 DB와 원자적이지 않아 정확히 한 번 실행은 보장하지 않습니다. [저장·복구 절차](docs/paper-event-durability.md)를 확인하세요.
4. SQLite의 처리 ID 기록은 자동 삭제하지 않으므로 운영 전 보존·백업 정책이 필요합니다.
5. 순간이동의 안전 판정은 단순 블록 판정이며 월드 보더, 청크 로드, 엔드 공허, 네더 지붕 및 위험 지형을 포함한 실서버 검증 필요.
6. `/ejt test`는 즉시 실행하며 테스트 시에도 인벤토리 삭제/즉사 가능. 운영 서버에서 위험 이벤트 테스트 금지.
7. 모의 후원 시 `--id`를 생략하면 새 ID가 생성됨. 실제 후원 연결 시 안정적인 고유 ID가 필수.
8. 방송 종료 후 모든 이벤트를 실행하는 정책은 의도된 것이나, 접속 직후 대량 실행을 대비한 관리자 일시정지 기능 테스트 필요.

## 안전 및 보안
- HTTP 수신기는 **localhost에만 바인딩**. 외부 포트 포워딩하지 마세요.
- 치지직 클라이언트 비밀키/토큰을 채팅이나 저장소에 올리지 마세요.
- 테스트 전 월드/인벤토리 백업을 만드세요.

## 업데이트
기본 설정은 `plugins/EnJapToi/config.yml`에서 바꿀 수 있습니다. `ejt reload`는 설정을 다시 읽지만 HTTP 바인딩 주소/포트 변경에는 재시작이 필요합니다. Minecraft/Paper 버전 변경 시 빌드 및 기능 검증을 다시 해야 합니다.


## 치지직 OAuth 인증 (친구 Windows PC)

`oauth.py`는 **로그인·토큰 발급·갱신만** 처리합니다. 최초 인증을 마치면 아래 설정에 따라 Paper가 수신기를 자동 실행·종료합니다. Paper 26.3 빌드 230과 Java 25, 기존 게임 규칙에는 변화가 없습니다. 인증 단계에서는 Paper 서버를 켜지 않아도 됩니다.

### 1. 준비

1. Python 3.10 이상을 설치하고 설치 화면의 **Add python.exe to PATH**를 선택합니다. PowerShell에서 `python --version`을 확인합니다. 추가 Python 패키지는 필요 없습니다.
2. 최신 저장소를 내려받아 압축을 풀거나 Git으로 받습니다. PowerShell에서 `cd "C:\실제경로\EnJapToi"`처럼 `README.md`가 있는 폴더로 이동합니다.
3. 치지직 개발자 센터의 `enjaptoi` 앱에 로그인 리디렉션 주소가 정확히 `http://127.0.0.1:18766/callback`인지 확인합니다. `localhost`로 바꾸거나 포트를 바꾸지 마세요. 앱에 `후원 조회`와 등록한 유저 조회 권한을 준비합니다. 공식 User 문서의 명칭은 **유저 정보 조회**이며, 실제 승인 화면도 확인하세요.
4. 앱의 **Client ID와 Client Secret**을 준비합니다. 앱 이름/ID인 `enjaptoi`를 Client ID 대신 사용하지 마세요. 이 값을 채팅·GitHub·스크린샷에 올리지 마세요.

### 2. 현재 PowerShell에만 클라이언트 정보 설정

아래 명령은 값을 명령줄에 직접 적지 않고 입력받습니다. Client Secret 입력은 화면에 표시되지 않습니다. PowerShell 창을 닫으면 환경변수도 사라집니다. `setx`로 영구 저장할 필요가 없습니다.

```powershell
$env:CHZZK_CLIENT_ID = Read-Host "개발자 센터의 Client ID"
$env:CHZZK_CLIENT_SECRET = [System.Net.NetworkCredential]::new("", (Read-Host "Client Secret" -AsSecureString)).Password
```

환경변수 대신 설정 파일을 사용하려면 Git에서 제외된 `bridge\.local\client.json`을 만들고 `clientId`, `clientSecret` 문자열 키를 넣을 수 있습니다. `--config bridge\.local\client.json`을 `login` 또는 `refresh` 뒤에 붙이세요. 이 JSON은 **평문**이므로 Windows 파일 보안에서 본인 계정만 접근하도록 제한하고 공유·백업에서 제외하세요. 환경변수의 Client ID와 Secret이 둘 다 설정됐으면 파일보다 우선합니다. 한쪽만 있거나 비어 있으면 `CLIENT_CONFIG_PAIR`로 중단하며 파일 값과 섞지 않습니다. 파일만 사용할 때에는 두 환경변수를 모두 제거하세요. 일반 추적 파일에 비밀값을 넣지 마세요.

### 3. 방송인 계정으로 로그인

```powershell
python bridge/oauth.py login
```

- 실행 PC에서 `127.0.0.1:18766`만 수신하고 `/callback`을 처리합니다. 외부 포트 포워딩이나 공용 서버는 필요 없습니다.
- 기본 브라우저가 열리면 **실제 방송인인 친구의 치지직 계정**인지 확인하고 앱과 권한을 승인합니다. 다른 계정으로 로그인돼 있다면 승인하지 말고 계정을 바꾸세요.
- 개발자 센터에서 등록된 권한과 치지직 승인 화면을 사용합니다. 공식 인증 요청 명세에 없는 `scope`나 PKCE 파라미터는 임의로 추가하지 않습니다.
- 5분 안에 인증하면 브라우저에 저장 완료 안내가 표시됩니다. 탭을 닫고 PowerShell의 완료 메시지를 확인합니다.
- 인증 실패·취소·잘못된 state·중복 요청을 처리하며, 인증 코드와 토큰은 출력하지 않습니다.

토큰은 `bridge\.local\tokens.dat`에 저장합니다. Windows에서는 **현재 사용자 DPAPI로 암호화**하므로 같은 Windows 사용자 계정에서 사용하세요. 다른 PC나 계정에 복사하지 마세요. 임시 파일에 암호화한 뒤 원자적으로 교체하고 동시 로그인·갱신을 잠금으로 제한합니다. 관리자나 본인 계정으로 실행되는 악성 프로그램까지 방어하는 저장소는 아닙니다. Linux 테스트 환경에서는 소유자 전용 디렉터리/파일(0700/0600)로 저장하며 암호화하지 않습니다. `.local`은 Git에서 제외됩니다.

### 4. 상태 확인과 갱신

```powershell
python bridge/oauth.py status
python bridge/oauth.py refresh
```

`status`는 토큰을 노출하지 않고 로컬 저장과 만료 임박 여부만 확인합니다. **방송인 계정·권한·서버 측 유효성을 확인하는 API 호출은 하지 않습니다.** 공식 문서상 Access Token은 1일, Refresh Token은 30일이며 갱신 토큰은 일회용입니다. `refresh`는 현재 환경변수/설정 파일로 새 토큰을 요청하고 새 Refresh Token까지 함께 교체 저장합니다. 미래 수신기에서 사용할 `refresh_tokens()`는 만료 60초 전부터 갱신할 수 있도록 구현했지만, 아래 수신기는 이 함수를 재사용해 만료 전 갱신과 새 세션 연결을 처리합니다. OAuth 도구 단독 실행은 상시 갱신하지 않습니다.

갱신 중 통신이나 저장에 실패했다면 기존 Refresh Token이 이미 사용됐을 수 있습니다. 반복 재시도하지 말고 `login`으로 다시 인증하세요. 새 인증 정보를 저장한 뒤 이전 저장 파일로 되돌리지 마세요.

작업 후 현재 PowerShell의 클라이언트 정보를 지우려면:

```powershell
Remove-Item Env:CHZZK_CLIENT_ID, Env:CHZZK_CLIENT_SECRET -ErrorAction SilentlyContinue
```

### 오류 해결·보안

- **18766 포트 사용 중:** 다른 OAuth 도구를 종료하고 다시 시도합니다. 등록된 콜백 포트는 임의로 변경하지 않습니다.
- **대기 시간 만료·state 오류:** 같은 실행에서 열린 브라우저 탭으로 인증해야 합니다. 이전 탭을 닫고 `login`을 새로 실행합니다.
- **인증 거부·토큰 응답 오류:** Client ID/Secret, 앱 상태, 등록된 권한과 콜백 주소를 확인한 뒤 다시 로그인합니다. 원본 오류 응답·인증 URL·브라우저 주소를 공개하지 마세요.
- **OAuth 잠금:** 잠금 파일은 남아 있어도 정상입니다. OS 잠금을 사용하므로 프로세스 종료 시 해제됩니다. 실행 중 잠금 파일을 삭제하지 마세요. 토큰 갱신 도중 강제 종료됐다면 토큰 사용 여부가 불명확할 수 있어 재로그인이 필요할 수 있습니다.
- **Windows 복호화 실패:** 같은 Windows 사용자에서 실행했는지 확인하고, 필요하면 다시 로그인합니다. 평문 저장으로 우회하지 않습니다.
- 콜백 접근 로그, 요청·응답 본문, 인증 코드, 토큰과 후원자 정보는 기록하지 않습니다. 지원 요청 시에는 화면의 일반 오류 메시지만 공유하세요. 토큰 폴더와 클라이언트 파일을 Git에 강제로 추가하지 마세요.
- 공식 API는 HTTPS 및 TLS 검증을 유지하고 토큰 요청의 HTTP 리디렉션을 따라가지 않습니다. 네트워크 제한이 있다면 브라우저 인증에 `chzzk.naver.com`, 토큰 API에 `openapi.chzzk.naver.com` 접근이 필요합니다. 로그인 중 추가 브라우저 인증 도메인은 실제 흐름에서 확인해야 합니다.

### 공식 근거와 검증 범위

- [Authorization](https://chzzk.gitbook.io/chzzk/chzzk-api/authorization): 인증 요청, `state`, 토큰 발급·갱신, 일회용 Refresh Token.
- [API 공통 안내](https://chzzk.gitbook.io/chzzk/chzzk-api/tips): 공식 API 도메인·인증 규격.
- [Session](https://chzzk.gitbook.io/chzzk/chzzk-api/session): 후원 조회 권한. 실시간 수신기는 아래 절차를 따릅니다.
- [User](https://chzzk.gitbook.io/chzzk/chzzk-api/user): 유저 정보 조회 권한. 수신기는 `/open/v1/users/me`로 설정한 방송인 채널과 인증 계정이 같은지 확인합니다.

모의 검증은 `python -m unittest discover -s tests -v`로 실행합니다. 테스트는 고정된 localhost 콜백 포트를 사용하므로 OAuth 작업과 동시에 실행하지 마세요. 외부 계정·API에는 연결하지 않고 브라우저와 토큰 API를 대체합니다. Windows에서는 같은 테스트가 DPAPI 저장 왕복도 검사하며, Linux에서는 해당 검사를 건너뜁니다. 실제 계정 승인, 실제 토큰 발급·갱신, 권한 승인 결과 및 Windows 브라우저/DPAPI 동작은 실행 PC에서 추가 검증해야 합니다.


## 공식 치지직 실시간 후원 수신 (Windows PC 한 대)

친구 PC에서 **기존 Paper 서버 실행 파일 하나만** 실행합니다. 처음 한 번 아래 설정과 OAuth 인증을 마치면 별도의 수신기 창을 열거나 닫지 않습니다. 브라우저 OAuth와 서버는 같은 Windows 사용자 계정을 사용합니다. Paper는 기존처럼 Java 25 / 빌드 230으로 실행하며 게임 규칙은 바꾸지 않습니다. 실제 계정·후원을 사용한 검증은 아직 수행하지 않았습니다.

### 설치와 로그인

저장소 루트에서 다음 명령을 실행합니다. 가상환경 활성화 스크립트나 PowerShell 실행 정책 변경은 필요 없습니다.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r bridge/requirements.txt
```

위 OAuth 절차처럼 `CHZZK_CLIENT_ID`, `CHZZK_CLIENT_SECRET`을 현재 창에 입력한 후, 같은 가상환경으로 인증합니다.

```powershell
.\.venv\Scripts\python.exe bridge/oauth.py login
```

이미 같은 계정에서 인증한 `bridge\.local\tokens.dat`가 있으면 재사용합니다. 앱의 `후원 조회`와 공식 문서상 `유저 정보 조회` 권한이 필요합니다. 사용자 Scope 승인을 바꿨다면 다시 로그인하세요. 본인의 방송 채널 ID도 확인해 둡니다. 채널 ID는 닉네임이나 Minecraft 이름 `Yirue`가 아니라 치지직 채널 식별자입니다. [User API](https://chzzk.gitbook.io/chzzk/chzzk-api/user)에 공식 조회 규격이 있습니다. 수신기는 제공한 ID와 `/open/v1/users/me`가 다르면 중단합니다.

### 금액 대응을 먼저 결정하세요

공식 후원 메시지의 `payAmount`는 **원 단위 문자열**입니다. 기존 게임 규칙의 치즈 금액과 같다고 자동 가정하지 않습니다. 기본 매핑을 제공하지 않으며, 실행 시 JSON 파일을 반드시 지정해야 합니다.

먼저 관찰 모드 파일을 만듭니다. 이 명령은 기존 파일이 있으면 덮어쓰지 않습니다.

```powershell
New-Item -ItemType Directory -Force bridge\.local | Out-Null
if (!(Test-Path bridge\.local\amount-map.json)) { Set-Content -Encoding ASCII bridge\.local\amount-map.json '{}' }
```

기본 실행은 **매핑 내용과 관계없이 관찰 모드**입니다. 신규 후원을 게임 이벤트로 선택하지 않고, 기존 미전달 이벤트도 Paper로 보내지 않으며 토큰 파일도 읽지 않습니다. `{}`는 이 의도를 나타내는 빈 매핑입니다. 후원자 정보와 메시지·금액 원문은 실시간 로그에 출력하거나 저장하지 않습니다. 관찰 중 제외된 후원은 이후 매핑을 바꿔도 재처리할 수 없습니다. 이미 Paper에 등록된 대기열은 별개이므로 실제 방송 전에는 서버 콘솔 `ejt pause`와 상태 확인도 병행하세요.

실제 금액 대응을 확인한 후에만 메모장으로 `bridge\.local\amount-map.json`을 편집합니다. 키는 수신 `payAmount` 그대로의 양의 정수 문자열, 값은 기존 규칙의 `1000`, `2000`, `5000`, `30000` 중 하나입니다. 다음은 **형식 설명용이며 대응이 검증됐다는 뜻이 아닙니다**.

```json
{"1000": 1000}
```

이 설정을 선택하면 `payAmount="1000"`에 기존 1,000치즈 게임 규칙을 적용하겠다는 사용자 설정입니다. 실검증 전에는 `{}`를 유지하세요. 매핑에 없는 금액, 선택하지 않은 후원 유형, 규칙에 맞지 않는 명령어는 `제외`로 집계합니다. 기존 `select_event()`를 그대로 사용하므로 명령어 우선순위와 룰렛·즉사 규칙도 동일합니다.

### 한 번 설정한 뒤 Paper만 실행

업데이트 전에는 구버전의 별도 수신기를 완전히 종료하세요. 구버전과 신버전의 동시 실행은 지원하지 않으며 OAuth 잠금 방식도 바뀌었습니다. 아래 설정을 마친 뒤부터는 Paper만 실행·종료합니다.

1. 위 Python 가상환경·최초 OAuth 절차를 마칩니다. 게임 금액이 미확정이면 매핑은 `{}`, 전달 활성화는 `false`로 둡니다.
2. Paper를 끈 상태에서 `plugins/EnJapToi/config.yml`에 아래 블록을 추가합니다. 이전 버전 config.yml에는 자동 추가되지 않습니다. `C:/EnJapToi`를 실제 저장소 경로로 바꾸고 방송인 채널 ID를 입력합니다. Windows 경로는 `/`를 쓰면 YAML 이스케이프 문제를 피할 수 있습니다.

```yaml
receiver:
  enabled: true
  python: 'C:/EnJapToi/.venv/Scripts/python.exe'
  script: 'C:/EnJapToi/bridge/receiver.py'
  channel-id: 'ACTUAL_BROADCASTER_CHANNEL_ID'
  donation-type: CHAT
  amount-map: 'C:/EnJapToi/bridge/.local/amount-map.json'
  client-config: 'C:/EnJapToi/bridge/.local/client.json'
  enable-game-delivery: false
  verification-file: 'C:/EnJapToi/bridge/.local/amount-verification.json'
```

Client ID/Secret은 앞서 설명한 Git 제외 `client.json`에만 저장하고, Paper config에는 **경로만** 적습니다. 환경변수를 사용하는 경우 `client-config: ''`로 두고 그 환경변수를 가진 창에서 Paper를 실행합니다. 값은 로그·GitHub에 올리지 마세요. 최초 OAuth는 별도 한 번 필요하며, 서버가 자동 로그인하거나 동의 화면을 승인하지 않습니다.

3. 기존 서버 배치 파일을 그대로 실행합니다. 예:

```powershell
java -Xms1G -Xmx2G -jar paper-26.3-230.jar --nogui
```

Paper가 플러그인을 활성화하면 Python 수신기도 시작합니다. 기본 `receiver.enabled: false`는 미설정 PC의 잘못된 실행을 막기 위한 값이며, 위 설정 후에는 자동으로 시작합니다. `enable-game-delivery: false` 상태에서도 서버가 켜져 있는 동안 공식 후원 구독·관찰은 가능하지만 게임 효과 선택·전달은 막습니다.

4. 콘솔에서 `ejt status`의 `receiver=true`와 `plugins/EnJapToi/receiver.log`의 `공식 후원 구독 확인 완료`를 확인합니다. 프로세스 생존만으로 인증·구독 성공을 뜻하지는 않습니다. 실패하면 로그의 일반 진단과 경로·권한을 확인한 후 서버를 재시작합니다.
5. 서버 콘솔 `stop` 또는 기존 종료 방법으로 종료합니다. JVM이 강제 종료돼도 부모 파이프의 EOF를 감시하는 Python 스레드가 수신기 전체를 끝냅니다. 다음 Paper 실행에서는 새 수신기·새 세션을 사용합니다. `receiver.py`의 독립 실행은 차단되며 별도 수신기를 백그라운드로 띄우지 마세요.

상세 동작과 한계는 [서버 연동 수명주기](docs/paper-receiver-lifecycle.md)를 확인하세요. 최초 인증 이후에는 친구가 수신기 실행·종료 명령을 따로 입력하지 않습니다. 설정 변경은 서버 재시작 후 반영합니다. 기본 `donation-type: CHAT`를 유지하며, 영상 후원은 별도 검증 후에만 `VIDEO`로 선택하세요.

### 연결·토큰 갱신과 복구 범위

공식 `GET /open/v1/sessions/auth` → Socket.IO 연결 → `SYSTEM connected`의 sessionKey → `POST /open/v1/sessions/events/subscribe/donation?sessionKey=...` → `SYSTEM subscribed` → `DONATION` 순서로 처리합니다. 구독 요청 중 도착한 이벤트도 채널과 유형을 확인해 저장합니다.

Socket.IO 자체의 자동 재연결을 끄고, 연결 중단·연결/구독 시간 초과·일시 API 오류 시 지수 간격으로 **새 URL·새 세션·새 구독**을 만듭니다. Access Token 만료 60초 전에는 연결을 정리하고 기존 OAuth 함수를 통해 갱신 후 새 세션을 만듭니다. REST API 401은 갱신 후 한 번만 재요청합니다. 갱신 실패·저장 실패·권한 취소는 중단하므로, 반복 강제 재시도하지 말고 원인 해결 후 다시 OAuth 로그인하세요. 수신기 실행 중 별도로 `oauth.py login/refresh`를 실행하지 마세요.

자동 모드에서는 Python의 별도 디스크 후원 대기열을 만들지 않습니다. 서버가 살아 있는 동안 선택한 효과와 로컬 ID로 Paper에 접수하고, 접수 확인이 불명확하면 같은 ID·효과로 즉시 한 번만 더 시도합니다. 이후 별도 저장·다음 실행 재생은 하지 않습니다. `queued` 또는 `duplicate`로 접수된 항목의 보존은 Paper의 `events.sqlite3`가 담당합니다. 응답이 유실됐더라도 Paper가 이미 저장했을 수 있으므로 `접수 미확인` 집계가 곧 실제 유실 확정은 아닙니다.

서버 종료 후 후원을 수집·저장하지 않으며, 이전 Python 수신함 `donations.sqlite3`도 자동 재생하지 않습니다. 이미 Paper에 정상 접수한 대기열은 Yirue 오프라인·정상/강제 재시작 후에도 기존 SQLite 방식으로 유지합니다. 금액 확인 없이 게임 효과를 선택하지 않는 기존 차단은 유지합니다.

**보장할 수 없는 부분:**
- 공식 후원 메시지에는 고유 후원 ID가 명시돼 있지 않습니다. 같은 내용이 치지직에서 두 번 수신되면 서로 다른 로컬 이벤트가 됩니다. 금액·닉네임·메시지 해시로 임의 중복 제거하지 않습니다.
- Paper 재시도는 현재 서버 실행 중 같은 ID·효과로 수행합니다. 접수되지 않은 항목을 디스크에 쌓아 나중에 전달하지 않습니다. 치지직 단계의 완벽한 중복 방지나 단 한 번 실행은 보장하지 않습니다.
- 연결 중단 중 발생하거나 로컬 저장 전에 유실된 후원을 자동 복구할 공식 이력·재생 API는 확인되지 않았습니다. 세션 목록 90일 조회는 후원 내역 조회가 아닙니다.
- Paper는 SQLite commit 이후 queued를 반환하고, 재시작 시 불확실한 실행은 UNCERTAIN으로 보류합니다. 월드·게임 효과와 DB를 하나의 트랜잭션으로 만들 수 없어 정확히 한 번 실행은 보장하지 않습니다. [상세 저장·복구 절차](docs/paper-event-durability.md)를 확인하세요.
- 처리 기록은 자동 삭제하지 않습니다. 파일을 삭제하면 대기 이벤트가 유실될 수 있으므로 임의로 지우지 마세요. 백업은 수신기를 정상 종료한 상태에서 합니다. 실서비스 보존·정리 정책은 후속 작업입니다.

공식 API 도메인은 `openapi.chzzk.naver.com`, 사용자 인증은 `chzzk.naver.com`입니다. Socket.IO 호스트는 공식 API 응답에 따라 달라집니다(문서 예: `ssio08.nchat.naver.com`). 방화벽·Codex 네트워크 제한에서는 실제 반환 호스트의 HTTPS/WebSocket 접근도 필요하며, 인증 토큰이 포함된 URL 전체를 로그나 지원 요청에 붙이지 마세요. TLS 검증과 기존 프록시는 유지합니다.

### 버전 호환성과 모의 검증

공식 문서는 Socket.IO-client 1.0.0~2.0.3을 안내합니다. 이에 맞는 `python-socketio==4.6.1` / `python-engineio==3.14.2`와 전송 의존성을 `bridge/requirements.txt`로 고정했습니다. Python Socket.IO 5.x로 임의 업그레이드하지 마세요. 이 구형 프로토콜 사용은 공식 명세와의 호환성을 위한 것이며, 실제 치지직 서버·Windows에서의 검증까지 끝났다는 뜻은 아닙니다.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

실제 계정 없이 금액 검증, 개인정보 미저장, 같은 ID/효과 재시도, 저장 후 재시작, 응답 유실, OAuth 갱신, 권한 취소와 시간 초과를 검사합니다. Socket.IO 실제 프로토콜 통합 테스트까지 실행하려면 테스트용으로만 Node.js와 npm을 설치한 뒤 다음을 실행합니다. **운영 수신기에는 Node.js가 필요 없습니다.**

```powershell
npm ci --prefix tests/socketio2 --ignore-scripts
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

로컬 전용 Socket.IO **2.0.3** 서버와 실제 Engine.IO 3 WebSocket 연결, 강제 연결 해제 후 새 세션·재구독, 모의 Paper 응답 유실과 같은 ID 재시도를 검증합니다. 로컬 테스트에서만 HTTPS 주소를 loopback HTTP로 바꿔 접속하며, 운영 코드는 HTTPS 검증을 유지합니다. Node 24에서는 구형 라이브러리의 `url.parse` 사용 경고가 나올 수 있습니다. 테스트 fixture는 외부에 공개하거나 운영 서버로 사용하지 마세요. Node가 없으면 이 통합 테스트는 건너뜁니다. Windows DPAPI 테스트도 Linux에서는 건너뜁니다.

공식 근거: [Session](https://chzzk.gitbook.io/chzzk/chzzk-api/session), [Authorization](https://chzzk.gitbook.io/chzzk/chzzk-api/authorization), [인증 헤더·공통 응답](https://chzzk.gitbook.io/chzzk/chzzk-api/tips), [User](https://chzzk.gitbook.io/chzzk/chzzk-api/user). 실제 계정·후원, 원/치즈 대응, 실제 소켓 호스트·권한 승인·재연결 동작과 플레이어 게임 효과는 친구 PC에서 별도 검증해야 합니다.

병합 전 상태 경합·장애·토큰 전달 경로 리뷰와 남은 Paper 저장 한계는 [코드 리뷰 기록](docs/chzzk-donations-review.md)에 정리했습니다. 수신 메시지는 wire 순서로 처리하며, 저장 실패·권한 취소는 후속 disconnect로 덮지 않고 중단합니다. Paper로 보내는 loopback 요청은 환경 HTTP 프록시와 리디렉션을 사용하지 않습니다. 금액 JSON에 같은 키가 두 번 있으면 실행을 거부합니다.

Paper 저장 안정성 후속 개선: [SQLite 수신 응답·UNCERTAIN 처리·이전 YAML 이관·백업 안내](docs/paper-event-durability.md). 플러그인 Java 자동 테스트 16개를 추가했습니다. 기존 리뷰 기록의 Paper 미수정 항목은 해당 후속 개선 전 상태를 설명합니다.


## 원/치즈 금액 대응 검증과 방송 전 안전 테스트

### 확인한 사실과 미확정 사항

[공식 DONATION 메시지 명세](https://chzzk.gitbook.io/chzzk/chzzk-api/session#message-event-subscribe-donation)는 `payAmount`를 **String / 후원 금액 (원)**, `donationText`를 후원 메시지로 설명합니다. 확인한 명세에는 치즈 개수 필드나 원/치즈 환산식이 없습니다. 따라서 다음 네 규칙의 원 대응은 모두 **미확정**입니다. 숫자가 같다는 이유만으로 동일하다고 적용하지 않습니다.

| 기존 게임 규칙 | 명령어·효과 | 검증된 공식 payAmount 대응 |
|---|---|---|
| 1,000치즈 | !버프·!이동·!밥·!다곡, 명령어 없으면 기존 4종 룰렛 | 미확정 |
| 2,000치즈 | !몹·!디버프, 명령어 필수 | 미확정 |
| 5,000치즈 | !삭제·!랜덤즉사·!지상, 명령어 필수 | 미확정 |
| 30,000치즈 | 메시지 무관 기존 즉사 효과 | 미확정 |

금액 문자열의 정수 형식·명령어 선택·룰렛 후보·저장/재시도는 모의 테스트로 확인할 수 있습니다. 실제 후원에서 선택한 치즈 개수와 수신 `payAmount`의 대응, 후원 유형별 실제 메시지와 로그인/권한/장시간 수신 동작은 실환경 확인이 필요합니다. 이번 작업에서는 로그인·실제 후원 결제·금액 환산 확정을 하지 않았습니다. 게임 효과·랜덤 확률·3초 간격도 변경하지 않았습니다.

### Windows에서 계정 없이 모의 데이터 넣기

Python 3.10 이상을 준비하고 저장소 루트에서 실행합니다. 이 도구는 Python 표준 라이브러리만 사용합니다. OAuth 환경변수, 토큰 파일, Paper 서버, 네트워크 연결이 필요 없습니다.

```powershell
python bridge/donation_check.py --input tests/fixtures/donations.json --amount-map tests/fixtures/simulation-amount-map.json
```

- `donations.json`은 공식 필드 모양으로 만든 **가상 데이터 10건**이며 실제 후원 기록이 아닙니다.
- `simulation-amount-map.json`의 동일 숫자 매핑은 **테스트 가정**일 뿐이며 운영용으로 복사하지 마세요.
- 출력은 `SIMULATION_ONLY_NOT_REAL_AMOUNT_VERIFICATION` 표시, 매핑 해시와 금액별 선택 효과입니다. 후원자 ID·닉네임·메시지는 출력하지 않습니다.
- 임시 SQLite DB만 사용하고 지웁니다. Paper로 보내거나 로그인하지 않으며 운영 수신함·실검증 확인 파일도 만들지 않습니다.
- 결과 `pending`은 임시 모의 DB 안의 변환 결과로, 실제 Paper 등록을 뜻하지 않습니다.
- 직접 모의 데이터를 만들려면 객체 배열 JSON에 `channelId="simulation-channel"`, `donationType="CHAT"`, 문자열 `payAmount`, 문자열 `donationText`를 넣습니다. 다른 가상 채널이면 `--channel-id`로 지정합니다. 메시지에 실제 개인정보나 인증 정보를 넣지 마세요.
- 기존 `python bridge/bridge.py ...` 로컬 송신기는 그대로 유지됩니다. 이 도구는 실제 Paper에 보낼 수 있는 별도 관리용 시뮬레이터이므로 운영 서버에서 위험 효과를 시험하지 마세요.

전체 모의 테스트는 위 가상환경 설치 후 다음 명령으로 실행합니다. 실제 Socket.IO 호환성 검사까지 실행하려면 앞서 안내한 테스트용 Node.js 설치도 필요합니다.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

### 실검증 전에는 전달을 켜지 마세요

실시간 수신기의 기본값은 관찰 모드입니다. 매핑 파일이 비어 있지 않아도 **신규 효과 선택·과거 대기열 전달을 모두 차단**합니다. 실제 네트워크 관찰은 OAuth가 필요하지만, 위 오프라인 검증은 필요 없습니다.

향후 방송인이 통제된 환경에서 **매핑의 각 항목을 실제로 확인한 후에만**, Git 제외 경로 `bridge\.local\amount-verification.json`에 아래 형식의 운영자 확인 기록을 작성할 수 있습니다. 이 단계는 이번 작업에서 수행하지 않았습니다. API가 발급하는 인증서가 아니라 사용자의 직접 확인 선언입니다. 도구가 실제 검증 여부를 증명하지 못합니다.

```json
{
  "version": 1,
  "channelId": "ACTUAL_BROADCASTER_CHANNEL_ID",
  "mappingSha256": "SHA256_OF_THE_EXACT_MAPPING",
  "confirmedByOperator": false
}
```

위 템플릿의 `false`는 전달을 허용하지 않습니다. 실제 확인 전에는 바꾸지 마세요. 채널 ID와 매핑 해시는 정확히 일치해야 하며, 매핑을 바꾸면 기존 확인 파일은 거부됩니다. 해시는 위 오프라인 검증 출력에서 확인할 수 있지만 **해시를 얻거나 모의 테스트에 통과한 것만으로 실검증이 되는 것은 아닙니다.** JSON은 UTF-8(Windows BOM 포함 가능) 또는 ASCII로 저장합니다.

직접 검증을 마쳐 유효한 확인 파일을 준비한 후에만 Paper config에서 전달을 활성화합니다. Paper가 내부적으로 대응하는 검증 옵션을 전달합니다. 수신기 독립 실행은 하지 않습니다.

```yaml
receiver:
  enable-game-delivery: true
  verification-file: 'C:/EnJapToi/bridge/.local/amount-verification.json'
```

옵션만 있거나, 확인이 false이거나, 채널·매핑이 다르면 OAuth 호출 전에 실행을 거부합니다. 비밀키·토큰은 이 파일에 넣지 마세요. 검증 파일을 추가한다고 기본 관찰 실행이 자동으로 활성화되지는 않습니다.

**이전 대기열:** 이전 버전의 Python 수신함은 금액 확인 여부와 관계없이 자동으로 가져오지 않습니다. 서버가 꺼진 동안 수집됐을 수 있으므로 새 ID로 재전송하거나 DB를 복사하지 마세요. Paper에 이미 정상 접수된 대기열은 그대로 보존됩니다. 모의 테스트는 금액 차단을 해제하지 않습니다.

### OAuth 로그인 실패 진단 코드

로그인 콜백에서 토큰 API 오류와 로컬 저장 오류를 구분합니다. 브라우저에는 안전한 진단 코드만 표시하고, CMD에는 고정된 설명 및 확인 가능한 숫자 HTTP 상태만 출력합니다. API 응답 본문·헤더·URL, Client Secret, 인증 코드/state, 액세스·리프레시 토큰, 원본 예외 메시지는 출력하지 않습니다.

| 진단 코드 | 의미와 확인할 항목 |
|---|---|
| `TOKEN_HTTP_400`, `TOKEN_HTTP_401`, `TOKEN_HTTP_403` 등 | 토큰 API가 해당 HTTP 상태로 요청을 거부했습니다. 상태만으로 Secret 오류·권한 오류 등을 단정할 수 없습니다. 앱 설정·등록 콜백·승인 절차를 확인하세요. |
| `TOKEN_HTTP_302` 등 3xx | 토큰 요청의 리디렉션을 차단했습니다. 인증정보를 다른 주소로 보내지 않습니다. |
| `TOKEN_RESPONSE_JSON` | 응답의 JSON 해석 또는 크기 검증 실패. HTTP 응답을 받았다면 CMD에 상태도 표시합니다. 원문은 출력하지 않습니다. |
| `TOKEN_RESPONSE_SCHEMA` | JSON은 해석했지만 토큰 필드·타입·값이 기대한 명세와 다릅니다. HTTP 200이어도 이 오류가 날 수 있습니다. |
| `TOKEN_NETWORK` | 연결·TLS·시간 초과·불완전한 전송 등 통신 실패. 원본 예외·부분 응답은 출력하지 않습니다. |
| `TOKEN_API_UNKNOWN` | 주입된 토큰 처리기 등의 오류를 안전하게 분류할 수 없어 원문을 숨긴 경우입니다. 저장 오류로 단정하지 않습니다. |
| `LOCAL_TOKEN_SAVE` | 토큰 API 단계 이후 로컬 암호화·파일 저장에 실패했습니다. 파일 권한·공간·Windows 사용자를 확인하세요. 이 코드만으로 DPAPI 자체가 원인이라고 단정하지 않습니다. |
| `LOCAL_TOKEN_READ` | 로컬 토큰 파일 읽기·복호화·형식 확인 실패입니다. |
| `LOCAL_OPERATION` | 콜백 대기 준비나 기타 로컬 처리 실패입니다. |

예를 들어 `TOKEN_HTTP_401`과 `TOKEN_RESPONSE_SCHEMA (HTTP 200)`, `LOCAL_TOKEN_SAVE`는 서로 다른 단계입니다. 지원 요청에는 진단 코드와 숫자 HTTP 상태만 공유하세요. 브라우저 주소·원문 응답·토큰 파일·설정의 비밀값을 붙이지 마세요. 실패한 인증 코드나 일회용 Refresh Token을 자동 재시도하지 않으며, 설정 확인 후 새 로그인으로 다시 인증합니다. state 검증, 토큰 보호 저장, 파일 잠금, TLS 검증과 로그 비공개 정책은 유지합니다.

OAuth `TOKEN_HTTP_401` 요청 검토: [공식 문서와 요청 URL·POST·JSON·필드 대조 및 입력 출처 확인](docs/oauth-request-review.md). 요청 형식 자체는 확인한 명세와 일치합니다. 환경변수/파일의 ID·Secret 혼합은 차단했지만 실제 401 원인을 확정한 것은 아닙니다.

### HTTP 401의 공식 오류 코드 구분

[치지직 공식 API 공통 오류 규격](https://chzzk.gitbook.io/chzzk/chzzk-api/tips)은 HTTP 401의 Error Message로 `INVALID_CLIENT`, `UNAUTHORIZED`, `INVALID_TOKEN`을 나열하며 실패 JSON의 필드는 `code`, `message`입니다.

토큰 API가 HTTP 401을 반환하면 본문을 최대 4KB(+크기 초과 확인 1바이트)까지만 메모리에서 검사합니다. 최상위 `message`가 위 세 문자열 중 하나와 **정확히** 일치할 때만 CMD와 브라우저에 표시합니다. 예: `[TOKEN_HTTP_401] ... (HTTP 401) / API INVALID_CLIENT`. Client ID/Secret, 인증 코드/state, 토큰, 본문 전체·부분, 헤더·URL, 원본 예외는 출력하거나 저장하지 않습니다.

알 수 없는 코드, 설명이 덧붙은 문자열, 다른 필드의 코드, JSON 오류·중복 키·크기 초과·본문 읽기 실패는 원문을 숨기고 기존 HTTP 401 및 `공식 오류 코드 확인 불가`만 표시합니다. 다른 HTTP 상태의 본문은 검사하지 않습니다. 허용 코드도 Client 설정 등의 구체적 오입력 원인을 확정하는 증거는 아닙니다. 실패한 인증 코드·Refresh Token을 자동 재시도하지 않습니다. 지원 요청에는 안전한 진단 코드·HTTP 상태·허용된 API 코드만 공유하세요.
