"""Deterministic limit-price protection; no account/device access."""
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_FLOOR

PRICE_POLICY = 'adverse-v1'


def price_guard(side, reference, price, maximum):
    if side not in ('buy', 'sell'):
        raise ValueError('买卖方向无效')
    values = []
    for value, label in ((reference, '信号参考价'), (price, '校验价格'), (maximum, '不利价格偏离上限')):
        try:
            number = Decimal(str(value))
        except (InvalidOperation, ValueError):
            raise ValueError(label+'无效') from None
        if not number.is_finite() or number <= 0:
            raise ValueError(label+'无效')
        values.append(number)
    base, current, limit = values
    if limit > 10:
        raise ValueError('不利价格偏离上限须不超过10%')
    signed = (current/base-1)*100
    adverse = max(Decimal(0), signed if side == 'buy' else -signed)
    boundary = base*(1+limit/100 if side == 'buy' else 1-limit/100)
    boundary = boundary.quantize(Decimal('.01'), rounding=ROUND_FLOOR if side == 'buy' else ROUND_CEILING)
    return dict(policy=PRICE_POLICY, side=side, reference_price=str(base), quote_price=str(current),
                signed_deviation_pct=float(signed), adverse_deviation_pct=float(adverse),
                maximum_pct=float(limit), boundary_price=str(boundary), allowed=adverse <= limit)


def rejection_message(check):
    direction = '买入价高于' if check['side'] == 'buy' else '卖出价低于'
    return (f"{direction}信号价的允许范围：参考{check['reference_price']}元，"
            f"校验{check['quote_price']}元，不利偏离{check['adverse_deviation_pct']:.3f}%"
            f"（上限{check['maximum_pct']:g}%）")
