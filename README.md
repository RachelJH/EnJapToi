# 엔잡퇴 v0.1 — Paper 플러그인 소스 + 로컬 후원 시뮬레이터

**상태: Java 25 빌드·Paper 26.3 빌드 230 서버 통합 검증 완료·게임 내 효과 미검증 개발 초안. 치지직 OAuth 인증 도구를 포함하며, 실시간 후원 수신은 아직 구현하지 않았습니다.**

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
- 저장소에 Java 자동 테스트가 없어 Maven은 `No tests to run`을 보고합니다. Paper 26.3 빌드 230 / API 230에서 플러그인 활성화, `ejt status`, 토큰 생성, `!밥` 후원의 `queued` 응답, 동일 ID의 `duplicate` 응답, 플레이어 0명 상태의 대기열 저장 및 정상 재시작 후 보존을 검증했습니다. 실제 플레이어가 접속하지 않아 게임 효과는 미검증입니다.

## 명령어 규칙
- 1000: `!버프`, `!이동`, `!밥`, `!다곡`; 메시지에 명령어가 없으면 4종 균등 룰렛.
- 2000: `!몹`, `!디버프` (명령어 필수).
- 5000: `!삭제`, `!랜덤즉사`, `!지상` (명령어 필수).
- 30000: 메시지 무관 즉사.
- 메시지의 공백으로 분리된 정확한 명령어만 인식하며 여러 명령어가 있으면 첫 번째를 사용.

## 반드시 해결해야 할 항목
1. **실시간 치지직 후원 수신 미구현.** OAuth 도구는 추가했지만 실제 계정 인증은 미검증입니다. 후원 세션 수신, 금액 단위와 이벤트 식별 정책 검증 및 별도 어댑터 구현이 필요합니다. `bridge.py`는 계속 로컬 시뮬레이터입니다.
2. **실제 게임 효과 미검증.** Paper 26.3 빌드 230에서 서버 통합 검증을 완료했으며, 플레이어가 접속한 상태의 게임 효과와 비정상 종료 시 복구는 별도 테스트가 필요합니다.
3. 상태 파일의 이벤트 실행 전 저장 구조는 강제 종료 순간 이벤트 유실 가능. 금전성 이벤트에 대해 원자적 상태 저장/실행 전후 기록/관리자 재처리 기능 필요.
4. `received` 목록은 무한히 커지므로 운영 전 보존 정책 필요.
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

이 기능은 **로그인·토큰 발급·갱신만** 처리합니다. 로그인해도 실제 후원은 아직 Minecraft로 전달되지 않습니다. Paper 26.3 빌드 230과 Java 25, 기존 게임 규칙에는 변화가 없습니다. 인증 단계에서는 Paper 서버를 켜지 않아도 됩니다.

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

환경변수 대신 설정 파일을 사용하려면 Git에서 제외된 `bridge\.local\client.json`을 만들고 `clientId`, `clientSecret` 문자열 키를 넣을 수 있습니다. `--config bridge\.local\client.json`을 `login` 또는 `refresh` 뒤에 붙이세요. 이 JSON은 **평문**이므로 Windows 파일 보안에서 본인 계정만 접근하도록 제한하고 공유·백업에서 제외하세요. 환경변수가 있으면 파일보다 우선합니다. 일반 추적 파일에 비밀값을 넣지 마세요.

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

`status`는 토큰을 노출하지 않고 로컬 저장과 만료 임박 여부만 확인합니다. **방송인 계정·권한·서버 측 유효성을 확인하는 API 호출은 하지 않습니다.** 공식 문서상 Access Token은 1일, Refresh Token은 30일이며 갱신 토큰은 일회용입니다. `refresh`는 현재 환경변수/설정 파일로 새 토큰을 요청하고 새 Refresh Token까지 함께 교체 저장합니다. 미래 수신기에서 사용할 `refresh_tokens()`는 만료 60초 전부터 갱신할 수 있도록 구현했지만, 현재 상시 실행·자동 갱신 프로세스는 없습니다.

갱신 중 통신이나 저장에 실패했다면 기존 Refresh Token이 이미 사용됐을 수 있습니다. 반복 재시도하지 말고 `login`으로 다시 인증하세요. 새 인증 정보를 저장한 뒤 이전 저장 파일로 되돌리지 마세요.

작업 후 현재 PowerShell의 클라이언트 정보를 지우려면:

```powershell
Remove-Item Env:CHZZK_CLIENT_ID, Env:CHZZK_CLIENT_SECRET -ErrorAction SilentlyContinue
```

### 오류 해결·보안

- **18766 포트 사용 중:** 다른 OAuth 도구를 종료하고 다시 시도합니다. 등록된 콜백 포트는 임의로 변경하지 않습니다.
- **대기 시간 만료·state 오류:** 같은 실행에서 열린 브라우저 탭으로 인증해야 합니다. 이전 탭을 닫고 `login`을 새로 실행합니다.
- **인증 거부·토큰 응답 오류:** Client ID/Secret, 앱 상태, 등록된 권한과 콜백 주소를 확인한 뒤 다시 로그인합니다. 원본 오류 응답·인증 URL·브라우저 주소를 공개하지 마세요.
- **잠금 파일 잔존:** 모든 `oauth.py` 작업이 종료됐는지 확인한 경우에만 `bridge\.local\tokens.dat.lock`을 삭제합니다. 진행 중에는 삭제하지 마세요.
- **Windows 복호화 실패:** 같은 Windows 사용자에서 실행했는지 확인하고, 필요하면 다시 로그인합니다. 평문 저장으로 우회하지 않습니다.
- 콜백 접근 로그, 요청·응답 본문, 인증 코드, 토큰과 후원자 정보는 기록하지 않습니다. 지원 요청 시에는 화면의 일반 오류 메시지만 공유하세요. 토큰 폴더와 클라이언트 파일을 Git에 강제로 추가하지 마세요.
- 공식 API는 HTTPS 및 TLS 검증을 유지하고 토큰 요청의 HTTP 리디렉션을 따라가지 않습니다. 네트워크 제한이 있다면 브라우저 인증에 `chzzk.naver.com`, 토큰 API에 `openapi.chzzk.naver.com` 접근이 필요합니다. 로그인 중 추가 브라우저 인증 도메인은 실제 흐름에서 확인해야 합니다.

### 공식 근거와 검증 범위

- [Authorization](https://chzzk.gitbook.io/chzzk/chzzk-api/authorization): 인증 요청, `state`, 토큰 발급·갱신, 일회용 Refresh Token.
- [API 공통 안내](https://chzzk.gitbook.io/chzzk/chzzk-api/tips): 공식 API 도메인·인증 규격.
- [Session](https://chzzk.gitbook.io/chzzk/chzzk-api/session): 후원 조회 권한. 실시간 수신은 이번 범위 밖입니다.
- [User](https://chzzk.gitbook.io/chzzk/chzzk-api/user): 유저 정보 조회 권한. 사용자 정보 API 호출도 아직 추가하지 않았습니다.

모의 검증은 `python -m unittest discover -s tests -v`로 실행합니다. 테스트는 고정된 localhost 콜백 포트를 사용하므로 OAuth 작업과 동시에 실행하지 마세요. 외부 계정·API에는 연결하지 않고 브라우저와 토큰 API를 대체합니다. Windows에서는 같은 테스트가 DPAPI 저장 왕복도 검사하며, Linux에서는 해당 검사를 건너뜁니다. 실제 계정 승인, 실제 토큰 발급·갱신, 권한 승인 결과 및 Windows 브라우저/DPAPI 동작은 실행 PC에서 추가 검증해야 합니다.
