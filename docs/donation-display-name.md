# 후원 표시명: 공식 명세 확인 및 구현 정책

> Current effect/tier rules and validation: [donation-effects.md](donation-effects.md). Older rule examples and test results below are historical.
확인일: 2026-11-01. 실제 계정·후원 없이 공식 문서와 모의 데이터로 확인했습니다.

## 공식 문서에 명시된 사실

| 항목 | 확인 결과 | 공식 출처 |
|---|---|---|
| 후원자 닉네임 | DONATION의 `donatorNickname`(String, 후원자 닉네임), `donatorChannelId`(String, 후원자 채널 ID)가 있습니다. ID만 제공되는 명세가 아닙니다. | [Session / 후원 이벤트 메시지](https://chzzk.gitbook.io/chzzk/chzzk-api/session#message-event-subscribe-donation) |
| 익명 여부 | 현재 DONATION 필드 목록에는 별도 익명 여부 필드가 없습니다. 익명 후원일 때 위 두 필드의 null/빈 문자열/특정 문자열 규칙도 문서에 명시돼 있지 않습니다. | [동일 명세](https://chzzk.gitbook.io/chzzk/chzzk-api/session#message-event-subscribe-donation) |
| 후원 구독 권한 | `POST /open/v1/sessions/events/subscribe/donation` 관련 Scope는 `후원 조회`입니다. 이벤트에 포함된 닉네임을 받기 위한 별도 Scope는 명시돼 있지 않습니다. | [Session](https://chzzk.gitbook.io/chzzk/chzzk-api/session) |
| 유저 조회 | `GET /open/v1/users/me`는 Access Token으로 **로그인한 본인**의 채널 정보를 조회하며 Scope는 `유저 정보 조회`입니다. 임의 후원자 ID를 넣는 유저 조회 API가 아닙니다. | [User](https://chzzk.gitbook.io/chzzk/chzzk-api/user) |
| 채널 조회 대안 | Client 인증 `GET /open/v1/channels`는 `channelIds`로 채널 정보를 조회하며 `channelName`을 반환합니다. 이는 이벤트 시점의 후원자 닉네임이나 익명 여부를 확정하는 기능이 아닙니다. | [Channel](https://chzzk.gitbook.io/chzzk/chzzk-api/channel) |
| 금액 | `payAmount`는 String이며 설명은 `후원 금액 (원)`입니다. 치즈 수량과의 대응은 이 명세만으로 확정하지 않습니다. | [후원 이벤트 메시지](https://chzzk.gitbook.io/chzzk/chzzk-api/session#message-event-subscribe-donation) |

## 구현 정책 (공식 보장과 구분)

- 공식 이벤트가 직접 제공한 `donatorNickname`만 표시명 후보로 사용합니다. 식별 정보가 없는데 이름만 있는 경우도 보수적으로 익명 처리하기 위해, `donatorChannelId`가 비어 있지 않은 문자열일 때만 후보를 사용합니다. **ID 유무가 익명 여부를 확정한다는 공식 보장은 아닙니다.** 후원자 ID는 조회·전달·저장하지 않습니다.
- 누락/null/빈 이름, 명시적 익명 표시(`익명`, `익명의 후원자`, 대소문자 무관 `anonymous`), 부적절한 타입/문자는 `익명의 후원자`로 표시합니다. 이 문자열들은 애플리케이션의 보수적 표시 정책이며 API의 공식 익명 sentinel이라고 주장하지 않습니다. 추측한 `isAnonymous` 같은 필드는 사용하지 않습니다.
- 이름은 최대 32 Unicode 코드 포인트/128 UTF-8 바이트, 첫 글자는 문자/숫자, 이후 문자/숫자/결합문자 및 ASCII 공백·밑줄·하이픈·마침표만 허용합니다. 양 끝 ASCII 공백만 제거합니다. 색상 코드(`§`, `&`), 제어·보이지 않는 방향/서식 문자, 줄바꿈, 따옴표, 꺾쇠, 슬래시 등은 이름 전체를 익명으로 대체합니다. 잘라서 다른 이름을 만들지 않습니다. 합법적인 특수문자/이모지 닉네임도 이 보수적 정책에서는 익명으로 표시될 수 있습니다.
- 이벤트가 이름과 ID를 제공했어도 사용자가 실제로 익명 후원을 선택했는지 판별할 필드는 공식 명세에 없습니다. **실제 익명 이벤트의 필드 마스킹은 미검증이며, 익명 여부의 완벽한 판별을 보장하지 않습니다.** 숨긴 신원을 다른 API로 복구하지 않습니다. 익명 개인정보 보호를 완전히 확정해야 한다면 실환경 마스킹 확인 전까지 관찰 모드를 유지해야 합니다. 현재 `enable-game-delivery: false`는 유지합니다.
- 추가 OAuth 권한, 재로그인, 유저/채널 조회 호출은 추가하지 않습니다. 기존 방송인 본인 계정 확인용 `/users/me` 호출은 그대로입니다.

## 전달·저장·알림

자동 수신기의 기존 운영자 금액 확인 → 효과 선택 뒤, 검증된 게임 치즈 등급과 안전한 표시명만 전달합니다. 원 단위 금액을 치즈로 임의 환산하지 않습니다. 같은 이벤트의 HTTP 재시도에는 같은 ID·효과·금액·표시명을 사용합니다.

닉네임은 localhost 인증 요청의 선택적 `X-EJT-Donor` 헤더로 UTF-8/Base64url 인코딩해 보냅니다. 이는 암호화가 아니며 HTTP 헤더의 문자 안전성을 위한 것입니다. Paper도 길이·UTF-8·표시 문자 검증을 수행합니다. 잘못된 이름은 효과를 버리지 않고 익명으로 처리합니다. 인스턴스/검증된 금액 메타데이터 없는 예전 모의 요청의 이름은 무시합니다. 토큰·인스턴스 인증과 프록시/리디렉션 차단을 유지합니다.

Paper SQLite의 nullable `donor` 열에 **안전한 표시명만** 효과/금액과 같은 트랜잭션으로 저장합니다. 대기열 보존에 필요한 최소 정보이며 원래 닉네임·ID·메시지·API 응답을 기록하지 않습니다. 기존 DB는 자동으로 열을 추가하고 기존 이벤트는 이름 없음으로 유지합니다. 동일 ID 재전송은 저장된 이름을 변경하지 않습니다. `DONE`/`UNCERTAIN` 전환 및 실행 중 재시작 복구 때 표시명을 NULL로 지우며 `secure_delete=ON`을 설정합니다. 기존 백업/디스크 복사본까지 삭제된다는 뜻은 아닙니다. DB/서버 폴더와 백업은 친구 PC 계정만 접근하도록 관리하세요. Python의 옛 모의 테스트용 Journal에는 이름을 저장하지 않습니다.

게임 효과 성공 → SQLite `DONE` commit → 전체 채팅 순서를 유지합니다. 실패 효과, 미확인 금액, 수동 `ejt test`, 기존 금액 없는 이벤트에는 후원 완료 알림이 없습니다. Adventure의 고정 plain text Component를 사용하므로 이름을 명령어/MiniMessage/색상 코드로 실행하지 않습니다.

```text
"홍길동"님이 "1,000치즈"를 후원하셨습니다! (후렴과 효과)
"익명의 후원자"님이 "5,000치즈"를 후원하셨습니다! (지상이동)
```

플러그인/수신기의 진단 로그에는 이름·ID·본문을 추가하지 않으며 내부 이벤트의 문자열 표현도 가립니다. **공개 채팅에 표시한 이름은 서버/다른 플러그인의 채팅 기록이나 방송 화면에 남을 수 있습니다.**

동일 로컬 ID의 중복 알림은 기존 저장 구조로 억제하지만 공식 DONATION에는 고유 후원 ID가 없어 같은 실제 후원이 별도 수신될 때 완벽한 중복 제거를 보장하지 않습니다. 게임 월드·DB·채팅은 원자적 작업이 아니므로 실행 중 장애의 `UNCERTAIN` 보류 및 완료 직후 채팅 누락 가능성도 그대로입니다.

## 친구 Windows PC 적용

1. 기존 방식으로 Paper를 `stop`하고 JAR, `plugins/EnJapToi` 폴더 및 브리지 설치 폴더를 백업합니다. DB 백업은 종료 후 수행합니다.
2. 이 브랜치의 `paper-plugin/target/enjaptoi-0.1.0.jar`로 서버 `plugins`의 기존 JAR를 교체합니다. 엔잡퇴 JAR는 하나만 남깁니다. Java 25 / Paper 26.3 build 230을 유지합니다.
3. 브리지 설치 폴더의 **`bridge/bridge.py`와 `bridge/receiver.py`를 함께 교체**합니다. 새 Python 의존성은 없습니다. OAuth·토큰·개인 설정 파일은 교체하지 않습니다.
4. 기존 자동 시작 경로, `receiver.enable-game-delivery: false`, `interval-ticks: 60`을 유지합니다. 금액 매핑·검증 파일은 생성/변경하지 않습니다. 닉네임 검증을 위해 운영 후원 전달을 켜지 않습니다.
5. 서버를 정상 실행해 `ejt status`와 관찰 로그를 확인합니다. 관찰 모드에서는 기존 `payAmount=... KRW`만 출력되며 닉네임·게임 실행·후원 알림은 나오지 않습니다. 실제 닉네임 채팅을 확인하려면 별도의 안전한 테스트 환경과 금액/익명 이벤트 검증이 필요합니다.

실제 치지직 후원/익명 이벤트, 실제 플레이어가 접속한 Paper의 채팅 표시, Windows 배포 적용은 미검증입니다. 테스트 결과는 README의 이번 변경 절을 참고하세요.
