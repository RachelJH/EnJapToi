"""Offline DONATION-format simulation. Never authenticates or sends to Paper."""
import argparse
import json
from pathlib import Path
import re
import tempfile

if __package__:
    from . import receiver
else:
    import receiver


def check(payloads, mapping, channel='simulation-channel'):
    if not isinstance(payloads, list) or len(payloads) > 1000:
        raise receiver.ReceiverError('모의 입력은 최대 1,000개의 DONATION 객체 배열이어야 합니다.')
    results = []
    with tempfile.TemporaryDirectory(prefix='enjaptoi-simulation-') as directory:
        journal = receiver.Journal(Path(directory) / 'data' / 'simulation.sqlite3')
        try:
            intake = receiver.Intake(journal, channel, mapping, allow_game_events=True)
            for index, payload in enumerate(payloads):
                data = receiver.object_message(payload)
                before = journal.db.execute('SELECT count(*) FROM events').fetchone()[0]
                intake.receive(data)
                row = journal.db.execute('SELECT effect,status FROM events ORDER BY rowid DESC LIMIT 1').fetchone()
                after = journal.db.execute('SELECT count(*) FROM events').fetchone()[0]
                amount = data.get('payAmount')
                results.append({'index':index, 'payAmount': amount if isinstance(amount,str) and re.fullmatch(r'[1-9][0-9]{0,11}', amount) else None,
                                'effect':row[0] if after > before else None,
                                'status':row[1] if after > before else 'ignored'})
        finally:
            journal.close()
    return {'validation':'SIMULATION_ONLY_NOT_REAL_AMOUNT_VERIFICATION',
            'mappingSha256':receiver.mapping_digest(mapping),'results':results}


def main(argv=None):
    parser = argparse.ArgumentParser(description='Offline DONATION conversion check; no OAuth, Socket.IO or Paper requests')
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--amount-map', type=Path, required=True)
    parser.add_argument('--channel-id', default='simulation-channel')
    args = parser.parse_args(argv)
    try:
        raw = args.input.read_bytes()
        if len(raw) > 1048576:
            raise receiver.ReceiverError('모의 파일 크기 제한을 초과했습니다.')
        result = check(json.loads(raw), receiver.amount_map(args.amount_map), args.channel_id)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, receiver.ReceiverError):
        print('모의 입력 또는 매핑을 확인하세요. 원본 데이터는 출력하지 않습니다.')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
