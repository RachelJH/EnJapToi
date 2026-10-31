# Paper 이벤트 저장과 강제 종료 복구

Java 25 / Paper 26.3 빌드 230 기준입니다. 게임별 효과, 후원 금액 규칙, 기본 60 ticks(3초) 간격과 Yirue 오프라인 대기는 유지합니다.

## 수신 응답

`plugins/EnJapToi/events.sqlite3`에 SQLite JDBC 트랜잭션으로 ID·효과·상태를 함께 저장합니다. journal_mode=DELETE, synchronous=FULL을 사용하며 드라이버와 Windows/Linux 네이티브 라이브러리를 JAR에 포함합니다. 한 서버만 DB를 열도록 OS 파일 잠금을 유지합니다.

- `200 queued`: PENDING 기록의 commit이 성공한 후에만 반환합니다.
- `200 duplicate`: 이미 디스크에 등록한 같은 ID입니다. 게임 실행 완료를 의미하지 않습니다.
- `409 conflict`: 같은 ID를 다른 효과로 보낸 경우입니다. 기존 효과를 덮지 않습니다. 옛 YAML에서 가져온 received ID에는 원래 효과 정보가 없어 이 비교를 할 수 없습니다.
- `503 unavailable`: 저장 실패, commit 결과 불명확 또는 Bukkit 작업 대기 시간 초과입니다. **저장되지 않았다는 뜻은 아닙니다.** 수신기는 반드시 같은 ID·같은 효과로 재시도합니다.

저장/commit 실패가 난 DB 연결로는 이후 성공 응답을 보내지 않습니다. 실행도 중단합니다. 디스크 공간·권한·파일 잠금 문제를 해결한 뒤 서버를 재시작하세요. 재시작 후 같은 ID가 저장됐으면 duplicate, 아니면 queued가 됩니다. HTTP 응답이 유실돼도 같은 동작을 합니다. 한 이벤트의 ID를 새로 만들거나 수신함을 지워 복구하지 마세요.

## 실행 상태

```text
PENDING --commit--> RUNNING --게임 효과 시도--> DONE(commit)
                       |
                오류 또는 재시작
                       ↓
                   UNCERTAIN (보류)
```

- 플레이어가 오프라인이거나 paused이면 PENDING을 실행하지 않습니다.
- RUNNING commit에 실패하면 효과를 호출하지 않습니다.
- 효과 호출 중 예외가 나면 UNCERTAIN으로 저장하고 일시정지합니다.
- 효과가 반환된 뒤 DONE commit에 실패하면 실행을 중단합니다. 재시작 시 남은 RUNNING은 UNCERTAIN으로 전환하고 일시정지합니다.
- UNCERTAIN은 완료로 삭제하거나 자동 재실행하지 않습니다. `ejt status`에서 `Pending`, `uncertain`, `paused`를 확인합니다. `ejt resume`은 나머지 PENDING을 재개할 뿐 UNCERTAIN을 재실행하지 않습니다.

**정확히 한 번 게임 실행은 보장하지 않습니다.** RUNNING 저장 직후 효과 전 종료와, 효과 후 DONE 저장 전 종료를 자동으로 구별할 수 없습니다. 불확실한 항목을 재실행하면 중복 효과가 생길 수 있어 기본적으로 보류합니다. 이는 기록 유실을 피하는 것이며 미완료 효과를 자동 복구하는 기능은 아닙니다. 월드·인벤토리 저장과 DB commit도 한 트랜잭션이 아니므로, DB가 DONE이어도 Minecraft 월드 저장 전에 종료되면 효과가 롤백될 수 있습니다. 디스크/파일시스템/장치가 동기화 요청을 올바르게 처리한다는 전제도 필요합니다.

UNCERTAIN이 있으면 서버를 중지하고 DB를 백업한 뒤, 해당 ID·효과와 실제 월드 상태를 검토하세요. 자동 복구 명령은 제공하지 않습니다. 수동 적용·보류 해제 정책은 관리자 판단과 별도 작업이 필요합니다. `/ejt test`는 기존의 즉시 실행 관리 명령으로 이 대기열을 거치지 않습니다.

## 이전 state.yml 이관·백업

1. 서버를 정상 종료하고 기존 `plugins/EnJapToi` 전체와 월드/플레이어 데이터를 백업합니다.
2. 새 JAR을 설치하고 서버를 시작합니다.
3. 유효한 `state.yml`의 received ID, pending 효과 목록, paused 상태를 하나의 DB 트랜잭션으로 한 번만 가져옵니다. 원본 YAML은 수정·삭제하지 않습니다. 파싱·검증·저장 실패 시 플러그인을 활성화하지 않습니다.
4. 옛 pending에는 원래 ID가 없으므로 이관용 ID를 부여합니다. 옛 received ID는 별도로 유지해 기존 수신기 재시도의 중복 등록을 막습니다. 이미 옛 저장 방식에서 잃어버린 이벤트는 복원할 수 없습니다.
5. 이후 상태의 기준은 SQLite입니다. `state.yml`을 편집해도 대기열은 바뀌지 않습니다. 옛 JAR로 단순 다운그레이드하면 오래된 YAML 대기열을 다시 실행할 수 있으므로 하지 마세요.

DB 복사는 서버를 중지한 상태에서 합니다. 실행 중인 DB를 과거 파일로 덮거나 DB와 Python 수신함을 서로 다른 시점의 백업으로 되돌리면 중복·유실이 가능합니다. `events.sqlite3.lock` 파일은 남아 있어도 OS 잠금이 해제돼 있으면 다시 시작할 수 있으며, 실행 중에 삭제하지 마세요. 기록 자동 삭제는 하지 않습니다.

## 검증과 범위

```text
mvn -B -U -s /workspace/setup/maven-settings.xml -f paper-plugin/pom.xml package
```

일반 PC에서는 클라우드 전용 `-s` 없이 `paper-plugin`에서 `mvn clean package`를 사용합니다. 테스트는 임시 SQLite DB, 실제 loopback HTTP, commit 전/후 오류 주입, 종료 훅 없이 Runtime.halt() 하는 별도 JVM으로 수신·저장 실패·재시도·재시작을 검증합니다. 실제 게임 효과는 호출하지 않습니다.

별도 Paper 230 서버에서도 JDBC 포함 JAR 로딩, YAML 이관, 플레이어 0명 상태 queued/duplicate, JVM 강제 종료 후 대기열·중복 기록 보존을 확인합니다. Windows 실동작, 실제 플레이어의 효과와 전원 차단/디스크 하드웨어 고장은 별도 검증 대상입니다.
