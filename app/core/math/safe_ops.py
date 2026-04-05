from .precision import to_decimal
from .guards import assert_finite

def safe_add(a, b):
    result = to_decimal(a) + to_decimal(b)
    return assert_finite(result)

def safe_sub(a, b):
    result = to_decimal(a) - to_decimal(b)
    return assert_finite(result)

def safe_mul(a, b):
    result = to_decimal(a) * to_decimal(b)
    return assert_finite(result)

def safe_div(a, b):
    b_val = to_decimal(b)
    if b_val == 0:
        raise ZeroDivisionError("Division by zero blocked.")
    result = to_decimal(a) / b_val
    return assert_finite(result)
