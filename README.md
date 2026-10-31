# 엔잡퇴 v0.1 — Paper 플러그인 소스 + 로컬 후원 시뮬레이터

**상태: Java 25 빌드 검증 완료·실제 Paper 서버 실행 미검증 개발 초안. 실제 치지직 연결은 포함하지 않습니다.**

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
4. 서버 콘솔에서 `version` 명령으로 Paper 버전을 확인. API 의존성은 공식 저장소의 `26.3.build.235-stable`로 고정했습니다. 공식 서버 목록의 Paper 26.3 안정 빌드 235와 대응하며, 사용자의 실제 서버 빌드와 일치하는지는 별도 확인이 필요합니다. `plugin.yml`의 `api-version: '26.3'`과 실제 서버 로딩도 확인하세요.
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
- Paper 26.1 이후 Maven 버전 표기([공식 문서](https://docs.papermc.io/paper/dev/project-setup/))를 따르며, 가변 범위 `[26.3.build,)` 대신 검증한 `26.3.build.235-stable`을 고정해 사용합니다. 저장소는 `https://repo.papermc.io/repository/maven-public/`, Java 타깃은 25입니다.
- 산출물: `paper-plugin/target/enjaptoi-0.1.0.jar`. JAR 무결성, 플러그인 클래스·설정 포함, Java 25 바이트코드를 확인했습니다.
- Python 송신기의 명령어 10개, 선택 규칙 4개, 임시 HTTP 모의 수신기로의 CLI 전송을 검증했습니다. 실제 Paper 통합 테스트는 아닙니다.
- 저장소에 Java 자동 테스트가 없어 Maven은 `No tests to run`을 보고합니다. 실제 서버 로딩, 중복 방지·대기열의 서버 동작, 게임 효과는 아직 검증하지 않았습니다.

## 명령어 규칙
- 1000: `!버프`, `!이동`, `!밥`, `!다곡`; 메시지에 명령어가 없으면 4종 균등 룰렛.
- 2000: `!몹`, `!디버프` (명령어 필수).
- 5000: `!삭제`, `!랜덤즉사`, `!지상` (명령어 필수).
- 30000: 메시지 무관 즉사.
- 메시지의 공백으로 분리된 정확한 명령어만 인식하며 여러 명령어가 있으면 첫 번째를 사용.

## 반드시 해결해야 할 항목
1. **실제 치지직 API 연동 없음.** 공식 인증/후원 세션 수신 및 이벤트 고유 ID 확인 후 별도 어댑터 구현 필요. 현재 Python은 로컬 시뮬레이터임.
2. **실제 Paper 26.3 서버 테스트 미실시.** API 다운로드와 Java 25 빌드는 검증했으며, 서버 로딩 및 실제 게임 효과는 별도 테스트가 필요합니다.
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
