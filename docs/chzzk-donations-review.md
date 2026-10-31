# 실시간 후원 수신기 병합 전 리뷰

대상: `feat/chzzk-donations`, 최초 구현 `b1b376c` 및 본 리뷰 수정.
최초 리뷰에서는 실제 계정·후원을 사용하지 않았고, 기존 게임 선택 규칙과 Paper 소스를 변경하지 않았습니다. 후속 Paper 저장 개선은 별도 절에서 구분합니다.

## 코드에서 확인하고 수정한 문제

1. **높음 — Socket.IO 메시지 처리 순서 경합**
   - 고정한 python-engineio 3.14.2의 `_receive_packet()`은 message마다 `run_async=True`로 새 작업 스레드를 만듭니다. 기존 Session의 RLock은 동시 실행만 막고 수신 순서는 보장하지 못했습니다.
   - 먼저 받은 후원의 저장이 뒤늦은 disconnect/권한 취소 처리보다 늦어져 건너뛰어질 수 있었습니다.
   - 메시지 콜백을 수신 스레드에서 순서대로 처리하는 버전 고정 어댑터를 적용했습니다. SQLite 저장은 후원 콜백 안에서 마치며 REST 호출은 여전히 메인 루프에서 합니다.
   - 회귀 검증: 작업 스레드를 만들지 않고 wire 순서로 처리하는 테스트, 실제 Socket.IO 2.0.3 WebSocket 연결/재연결 테스트.
   - 내부 메서드를 사용하는 어댑터이므로 의존성 버전을 바꿀 때 이 테스트를 반드시 재실행해야 합니다. 느린 디스크가 수신 루프를 지연시킬 수 있으며 지연 중 연결이 끊기면 미수신분을 복구한다는 보장은 없습니다.

2. **높음 — 저장 실패·권한 취소가 일시 연결 오류로 덮임**
   - 기존 disconnected()가 self.failure를 무조건 교체해 저장 실패 후 자동 재연결될 수 있었습니다.
   - 권한 취소가 먼저 수신됐어도 큐에 남은 connected 처리에서 accepting이 다시 켜질 수 있었습니다. 구독 REST 요청 도중 발생한 치명 오류도 뒤이은 HTTP timeout에 가려질 수 있었습니다.
   - 치명 오류 우선 보존, 즉시 수신 차단, 구독 요청 전후·연결 교체 시 오류 확인을 추가했습니다. 요청하지 않은 구독 확인은 실패로 처리하고 세션 키 변경은 새 연결로 복구합니다. 잘못된 DONATION JSON도 조용히 버리는 대신 명확히 중단합니다.
   - 회귀 검증: 저장 실패→disconnect, revoked→지연 connected, 저장 실패→구독 HTTP timeout, handshake 예외, 잘못된 JSON/구독 확인/세션 키 변경.

3. **높음 — Paper 브리지 토큰이 프록시·리디렉션을 따라갈 경로**
   - 기존 urllib.request.urlopen은 환경 프록시와 기본 리디렉션을 사용했습니다. 설정된 HTTP 프록시로 loopback 요청이 나가거나 302의 다른 목적지에 X-EJT-Token이 전달될 수 있었습니다. 실제 유출이 발생했다는 증거는 아닙니다.
   - loopback Paper 전달에만 프록시를 사용하지 않고 리디렉션을 거부합니다. 공식 치지직 HTTPS 요청의 프록시와 TLS 검증은 유지합니다. Paper 응답 크기도 제한했습니다.
   - 회귀 검증: 환경 프록시를 설정한 실제 로컬 HTTP 테스트에서 프록시 사용 및 302 대상 접근이 없음을 확인. 기존 후원 변환 규칙은 변경하지 않았습니다.

4. **중간 — 중복 금액 JSON 키의 묵시적 덮어쓰기**
   - 같은 원 금액 키를 두 번 쓰면 마지막 게임 금액이 조용히 선택됐습니다. 매핑 파일의 중복 키를 이제 거부합니다.

## 기존 장애 경로 재검증

- 랜덤 효과는 SQLite INSERT 전 한 번만 선택하며, 전달 전에 commit합니다. 재시도 시 select_event()를 다시 호출하지 않습니다.
- Paper 수락 후 응답만 유실되거나 로컬 done commit이 실패하면 pending이 남습니다. 재실행 때 같은 ID·효과로 보내고 Paper의 duplicate 응답으로 완료 처리합니다.
- SQLite 저장 오류가 난 이벤트는 Paper로 전달하지 않습니다. 현재 받은 이벤트의 저장이 실패했다면 치지직에서 복구할 수 있다는 보장은 없습니다.
- DB에 후원자 ID·닉네임·메시지/금액 원문·토큰/세션 URL은 저장하지 않습니다. 출력은 고정된 진단과 집계입니다. OAuth와 Socket.IO의 원본 예외는 출력하지 않습니다.

## 최초 리뷰 당시의 Paper 한계 (후속 저장 개선 전)

- `EnJapToi.java`의 수신 처리에서 received/queue를 갱신하고 saveState() 후 queued를 반환합니다. saveState()는 IOException을 기록만 하고 호출자에게 실패를 전달하지 않습니다. 따라서 **queued는 디스크 저장 성공의 증명이 아닙니다.** 수신기가 done으로 기록한 뒤 서버가 장애로 재시작하면 이벤트가 유실될 수 있습니다.
- ticker는 queue.removeFirst()와 saveState()를 먼저 수행한 뒤 executeEvent()를 호출합니다. 그 사이 강제 종료되면 게임 효과가 유실될 수 있습니다. 상태 파일의 비원자적 쓰기 문제도 남습니다.
- 최초 리뷰에서는 게임 규칙 및 Paper 플러그인을 변경하지 않았습니다. 이후 사용자 요청으로 [SQLite 저장·실행 의도 기록](paper-event-durability.md)을 도입했습니다. 현재 동작과 여전히 남는 세계 상태/DB 원자성 한계는 해당 문서를 기준으로 확인하세요.

## 아직 실환경에서 검증하지 못한 위험·보장 밖의 범위

- 공식 DONATION 명세에는 고유 후원 ID와 replay cursor가 없습니다. 같은 후원 재전송을 두 로컬 이벤트로 처리할 수 있고, 끊긴 동안의 후원을 자동 복구할 수 있다고 보장하지 않습니다. 금액·닉네임·내용 해시로 임의 중복 제거하지 않습니다.
- 실제 치지직 계정/Scope, 원 문자열과 치즈 금액의 대응, 실제 세션 URL/heartbeat/장시간 연결, Windows 브라우저·DPAPI와 플레이어 게임 효과는 미검증입니다.
- 파일 잠금은 같은 설치 폴더의 수신기만 제한합니다. 저장소 복사본을 여러 개 실행하거나 수신함/서버 상태를 과거 백업으로 되돌리면 중복·유실 가능성이 있습니다.
- 미전달 이벤트를 자동 폐기하지 않으므로 영구적인 Paper 오류는 FIFO 대기열을 막습니다. 저장소 증가·디스크 부족·파일 권한·백업 보존 정책은 운영자가 관리해야 합니다.

## 재현 명령

```text
python -m pip install -r bridge/requirements.txt
npm ci --prefix tests/socketio2 --ignore-scripts
python -m unittest discover -s tests -v
```

Socket.IO fixture는 외부 공개하지 않는 테스트 전용입니다. 실제 계정 인증 없이 실행합니다. Windows DPAPI 검사는 Windows에서만 실행되며 Linux에서는 skipped로 구분합니다.

공식 근거: https://chzzk.gitbook.io/chzzk/chzzk-api/session
