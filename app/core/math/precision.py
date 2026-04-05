from decimal import Decimal, getcontext, ROUND_HALF_UP

DEFAULT_PRECISION = 28

def configure_precision(precision: int = DEFAULT_PRECISION):
    getcontext().prec = precision

def to_decimal(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))

def round_decimal(value: Decimal, places: int = 8) -> Decimal:
    quant = Decimal("1." + "0" * places)
    return value.quantize(quant, rounding=ROUND_HALF_UP)
