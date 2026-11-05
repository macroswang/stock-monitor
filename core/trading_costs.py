"""Deterministic A-share round-trip cost calculation for paired T trades."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


CENT = Decimal("0.01")


def _decimal(value, label):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"{label}无效") from None
    if not result.is_finite() or result < 0:
        raise ValueError(f"{label}无效")
    return result


def cents(value):
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def paired_profit(sell_price, buy_price, shares, rule):
    """Return a cent-rounded fee breakdown using the rule's frozen fee inputs."""
    sell = _decimal(sell_price, "卖出价格")
    buy = _decimal(buy_price, "买入价格")
    if sell <= 0 or buy <= 0 or isinstance(shares, bool) or not isinstance(shares, int) or shares <= 0:
        raise ValueError("成对T价格或股数无效")
    commission_wan = _decimal(rule.get("commission_wan", 2), "佣金率")
    minimum = _decimal(rule.get("minimum_commission", 5), "最低佣金")
    stamp_per_mille = _decimal(rule.get("stamp_per_mille", .5), "印花税率")
    transfer_per_mille = _decimal(rule.get("transfer_per_mille", .01), "过户费率")
    slippage_per_mille = _decimal(rule.get("slippage_per_mille", 0), "滑点")
    if slippage_per_mille >= 1000:
        raise ValueError("滑点须小于1000‰")

    quantity = Decimal(shares)
    sale = sell * (Decimal(1) - slippage_per_mille / 1000) * quantity
    purchase = buy * (Decimal(1) + slippage_per_mille / 1000) * quantity
    sell_commission = cents(max(sale * commission_wan / 10000, minimum))
    buy_commission = cents(max(purchase * commission_wan / 10000, minimum))
    commission = cents(sell_commission + buy_commission)
    stamp = cents(sale * stamp_per_mille / 1000)
    transfer = cents(sale * transfer_per_mille / 1000) + cents(purchase * transfer_per_mille / 1000)
    transfer = cents(transfer)
    gross = cents((sell - buy) * quantity)
    slippage = cents((sell * quantity - sale) + (purchase - buy * quantity))
    fees = cents(commission + stamp + transfer)
    cost = cents(fees + slippage)
    net = cents(gross - cost)
    return {
        "sell": str(sell), "buy": str(buy), "shares": shares,
        "gross": float(gross), "commission": float(commission), "stamp": float(stamp),
        "transfer": float(transfer), "slippage": float(slippage), "fees": float(fees),
        "cost": float(cost), "net": float(net),
    }
