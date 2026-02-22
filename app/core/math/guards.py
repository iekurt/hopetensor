def assert_finite(value):
    if value.is_nan():
        raise ValueError("NaN detected.")
    if value.is_infinite():
        raise ValueError("Infinity detected.")
    return value
