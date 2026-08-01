from decimal import Decimal

import pytest

from hyc_domain.decimals import DecimalValidationError, DecimalValue


@pytest.mark.parametrize(
    "raw",
    [0.1, "01", "1e2", "NaN", "Infinity", " 1", "+1", "1.", "-0", "-0.00"],
)
def test_decimal_rejects_noncanonical_boundary_values(raw: object) -> None:
    with pytest.raises(DecimalValidationError):
        DecimalValue.parse(raw)  # type: ignore[arg-type]


def test_decimal_preserves_canonical_exact_value() -> None:
    assert DecimalValue.parse(Decimal("12.340")).canonical() == "12.340"
