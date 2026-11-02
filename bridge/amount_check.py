"""Compare manually observed KRW and cheese tiers offline; never approve delivery."""
import argparse
import json
import re
from pathlib import Path

if __package__:
    from . import bridge, receiver
else:
    import bridge
    import receiver


TIERS = (1000, 2000, 3000, 4000, 5000, 30000)


def compare(pay_amount, expected_cheese, mapping):
    """MATCH means agreement with a candidate map, not proof of a conversion ratio."""
    if (not isinstance(pay_amount, str)
            or not re.fullmatch(r'[1-9][0-9]{0,11}', pay_amount)
            or type(expected_cheese) is not int or expected_cheese not in TIERS):
        raise ValueError('Invalid observation')
    # Validate the entire candidate, including unrelated entries. Never infer one.
    if not isinstance(mapping, dict) or any(
            not isinstance(key, str) or not re.fullmatch(r'[1-9][0-9]{0,11}', key)
            or type(tier) is not int or tier not in TIERS
            for key, tier in mapping.items()):
        raise ValueError('Invalid candidate map')
    candidate = mapping.get(pay_amount)
    return {
        'purpose': 'OBSERVATION_COMPARISON_ONLY_NOT_REAL_AMOUNT_VERIFICATION',
        'payAmountKrw': pay_amount,
        'expectedCheese': expected_cheese,
        'candidateCheese': candidate,
        'comparison': 'UNMAPPED' if candidate is None else (
            'MATCH' if candidate == expected_cheese else 'MISMATCH'),
        'expectedEffects': [effect for effect, tier in bridge.PRICE.items()
                            if tier == expected_cheese],
        'authorizesGameDelivery': False,
    }


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's default diagnostic can echo arbitrary input or file paths.
        raise ValueError('Invalid arguments')


def main(argv=None):
    parser = SafeParser(description='Offline manual amount comparison; no OAuth, Paper or file writes')
    parser.add_argument('--pay-amount', required=True, help='Validated numeric payAmount from observation log, in KRW')
    parser.add_argument('--expected-cheese', required=True, help='Cheese tier independently confirmed in donation UI/history')
    parser.add_argument('--amount-map', type=Path, help='Optional existing candidate KRW-string -> cheese map; read only')
    try:
        args = parser.parse_args(argv)
        tiers = {str(tier): tier for tier in TIERS}
        if args.expected_cheese not in tiers:
            raise ValueError('Invalid expected tier')
        mapping = receiver.amount_map(args.amount_map) if args.amount_map is not None else {}
        result = compare(args.pay_amount, tiers[args.expected_cheese], mapping)
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return 2 if result['comparison'] == 'MISMATCH' else 0
    except (OSError, ValueError, receiver.ReceiverError):
        print('Invalid observation, candidate map or arguments. Raw input is not displayed.')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
