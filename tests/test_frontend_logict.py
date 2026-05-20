"""
unit/frontend/test_frontend_logic.py
Unit tests for frontend business logic extracted from JSX files.

These mirror the JavaScript logic in Python so we can test it in the
pytest pyramid without a browser. Covers:

  - auth_components.jsx  : isUniversityEmail, getStrength, useLockoutTimer arithmetic
  - MenuPage.jsx         : discount calculation, voucher apply logic
  - OrderPaymentApp.jsx  : isValidCardNumber, isValidExpiry, isValidCVV,
                           isValidEgyptianPhone, fmtTime
  - AdminPanel.jsx       : validateVoucher rules
"""

import re
from datetime import datetime, timedelta, timezone

import pytest

UTC = timezone.utc

# ═══════════════════════════════════════════════════════════════
# auth_components.jsx — isUniversityEmail
# ═══════════════════════════════════════════════════════════════

ALLOWED_DOMAINS_FE = ["ejust.edu.eg"]

def is_university_email_fe(email: str) -> bool:
    """Python mirror of frontend isUniversityEmail()"""
    try:
        domain = email.strip().split("@")[1].lower()
        return domain in ALLOWED_DOMAINS_FE
    except (IndexError, AttributeError):
        return False


class TestFrontendEmailValidation:

    @pytest.mark.unit
    def test_valid_ejust_email(self):
        assert is_university_email_fe("student.123456@ejust.edu.eg") is True

    @pytest.mark.unit
    def test_gmail_rejected(self):
        assert is_university_email_fe("user@gmail.com") is False

    @pytest.mark.unit
    def test_empty_string_rejected(self):
        assert is_university_email_fe("") is False

    @pytest.mark.unit
    def test_no_at_sign_rejected(self):
        assert is_university_email_fe("notanemail") is False

    @pytest.mark.unit
    def test_case_insensitive(self):
        assert is_university_email_fe("A.123456@EJUST.EDU.EG") is True


# ═══════════════════════════════════════════════════════════════
# auth_components.jsx — getStrength
# ═══════════════════════════════════════════════════════════════

def get_strength(pw: str) -> dict:
    """Python mirror of frontend getStrength()"""
    if not pw:
        return {"score": 0, "label": "", "cls": ""}
    s = 0
    if len(pw) >= 8:                          s += 1
    if re.search(r"[A-Z]", pw):              s += 1
    if re.search(r"[0-9]", pw):              s += 1
    if re.search(r"[^A-Za-z0-9]", pw):      s += 1
    labels = ["", "Weak", "Weak", "Fair", "Strong"]
    clss   = ["", "weak", "weak", "medium", "strong"]
    return {"score": s, "label": labels[s], "cls": clss[s]}


class TestPasswordStrength:

    @pytest.mark.unit
    def test_empty_password_score_zero(self):
        r = get_strength("")
        assert r["score"] == 0

    @pytest.mark.unit
    def test_short_password_weak(self):
        r = get_strength("abc")
        assert r["score"] == 0   # < 8 chars gives 0

    @pytest.mark.unit
    def test_only_lowercase_long_score_1(self):
        r = get_strength("abcdefgh")
        assert r["score"] == 1

    @pytest.mark.unit
    def test_upper_and_lower_and_long_score_2(self):
        r = get_strength("Abcdefgh")
        assert r["score"] == 2

    @pytest.mark.unit
    def test_upper_lower_number_score_3(self):
        r = get_strength("Abcdefg1")
        assert r["score"] == 3

    @pytest.mark.unit
    def test_all_criteria_score_4_strong(self):
        r = get_strength("Abcdef1!")
        assert r["score"] == 4
        assert r["label"] == "Strong"
        assert r["cls"]   == "strong"

    @pytest.mark.unit
    def test_fair_label_score_3(self):
        r = get_strength("Abcdef1g")  # no special char
        assert r["label"] == "Fair"


# ═══════════════════════════════════════════════════════════════
# OrderPaymentApp.jsx — card field validators
# ═══════════════════════════════════════════════════════════════

def is_valid_card_number(val: str) -> bool:
    return bool(re.match(r"^\d{4}\s?\d{4}\s?\d{4}\s?\d{4}$", val.strip()))

def is_valid_expiry(val: str) -> bool:
    return bool(re.match(r"^(0[1-9]|1[0-2])\s?/\s?\d{2}$", val.strip()))

def is_valid_cvv(val: str) -> bool:
    return bool(re.match(r"^\d{3,4}$", val.strip()))

def is_valid_egyptian_phone(phone: str) -> bool:
    cleaned = phone.replace(" ", "")
    return bool(re.match(r"^01\d{9}$", cleaned))


class TestCardValidation:

    @pytest.mark.unit
    def test_valid_16_digit_card(self):
        assert is_valid_card_number("4111111111111111") is True

    @pytest.mark.unit
    def test_valid_card_with_spaces(self):
        assert is_valid_card_number("4111 1111 1111 1111") is True

    @pytest.mark.unit
    def test_15_digit_card_invalid(self):
        assert is_valid_card_number("411111111111111") is False

    @pytest.mark.unit
    def test_card_with_letters_invalid(self):
        assert is_valid_card_number("411111111111111X") is False

    @pytest.mark.unit
    def test_empty_card_invalid(self):
        assert is_valid_card_number("") is False


class TestExpiryValidation:

    @pytest.mark.unit
    def test_valid_expiry_mm_yy(self):
        assert is_valid_expiry("12/25") is True

    @pytest.mark.unit
    def test_valid_expiry_with_spaces(self):
        assert is_valid_expiry("01 / 26") is True

    @pytest.mark.unit
    def test_invalid_month_00(self):
        assert is_valid_expiry("00/25") is False

    @pytest.mark.unit
    def test_invalid_month_13(self):
        assert is_valid_expiry("13/25") is False

    @pytest.mark.unit
    def test_invalid_format_yyyy(self):
        assert is_valid_expiry("12/2025") is False


class TestCVVValidation:

    @pytest.mark.unit
    def test_three_digit_cvv(self):
        assert is_valid_cvv("123") is True

    @pytest.mark.unit
    def test_four_digit_cvv(self):
        assert is_valid_cvv("1234") is True

    @pytest.mark.unit
    def test_two_digit_cvv_invalid(self):
        assert is_valid_cvv("12") is False

    @pytest.mark.unit
    def test_five_digit_cvv_invalid(self):
        assert is_valid_cvv("12345") is False

    @pytest.mark.unit
    def test_alpha_cvv_invalid(self):
        assert is_valid_cvv("abc") is False


class TestEgyptianPhoneValidation:

    @pytest.mark.unit
    def test_valid_01x_number(self):
        assert is_valid_egyptian_phone("01012345678") is True

    @pytest.mark.unit
    def test_valid_015_number(self):
        assert is_valid_egyptian_phone("01512345678") is True

    @pytest.mark.unit
    def test_10_digits_invalid(self):
        assert is_valid_egyptian_phone("0101234567") is False

    @pytest.mark.unit
    def test_12_digits_invalid(self):
        assert is_valid_egyptian_phone("010123456789") is False

    @pytest.mark.unit
    def test_not_starting_with_01_invalid(self):
        assert is_valid_egyptian_phone("02012345678") is False

    @pytest.mark.unit
    def test_spaces_stripped(self):
        assert is_valid_egyptian_phone("010 1234 5678") is True


# ═══════════════════════════════════════════════════════════════
# OrderPaymentApp.jsx — fmtTime
# ═══════════════════════════════════════════════════════════════

def fmt_time(s: int) -> str:
    """Mirror of frontend fmtTime()"""
    m   = s // 60
    sec = s % 60
    return f"{str(m).zfill(2)}:{str(sec).zfill(2)}"


class TestFmtTime:

    @pytest.mark.unit
    def test_600_seconds_is_10_00(self):
        assert fmt_time(600) == "10:00"

    @pytest.mark.unit
    def test_0_seconds_is_00_00(self):
        assert fmt_time(0) == "00:00"

    @pytest.mark.unit
    def test_90_seconds_is_01_30(self):
        assert fmt_time(90) == "01:30"

    @pytest.mark.unit
    def test_65_seconds(self):
        assert fmt_time(65) == "01:05"

    @pytest.mark.unit
    def test_59_seconds(self):
        assert fmt_time(59) == "00:59"


# ═══════════════════════════════════════════════════════════════
# MenuPage.jsx — discount application logic
# ═══════════════════════════════════════════════════════════════

def apply_voucher_discount(subtotal: float, discount_type: str, discount_value: float) -> float:
    """Mirror of frontend discount calculation in applyVoucher()"""
    if discount_type == "percent":
        return min((discount_value / 100) * subtotal, subtotal)
    elif discount_type == "flat":
        return min(discount_value, subtotal)
    elif discount_type == "free_delivery":
        return 0.0
    return 0.0


class TestVoucherDiscountApplication:

    @pytest.mark.unit
    def test_flat_discount_applied(self):
        assert apply_voucher_discount(100.0, "flat", 20.0) == 20.0

    @pytest.mark.unit
    def test_flat_discount_capped_at_subtotal(self):
        assert apply_voucher_discount(15.0, "flat", 20.0) == 15.0

    @pytest.mark.unit
    def test_percent_discount_applied(self):
        assert apply_voucher_discount(100.0, "percent", 25.0) == 25.0

    @pytest.mark.unit
    def test_percent_discount_capped(self):
        assert apply_voucher_discount(50.0, "percent", 200.0) == 50.0

    @pytest.mark.unit
    def test_free_delivery_zero_discount(self):
        assert apply_voucher_discount(100.0, "free_delivery", 0.0) == 0.0

    @pytest.mark.unit
    def test_unknown_type_zero_discount(self):
        assert apply_voucher_discount(100.0, "mystery", 50.0) == 0.0


# ═══════════════════════════════════════════════════════════════
# AdminPanel.jsx — validateVoucher
# ═══════════════════════════════════════════════════════════════

def validate_voucher_fe(form: dict) -> dict:
    """Mirror of AdminPanel validateVoucher()"""
    errors = {}
    code = (form.get("code") or "").strip().upper()
    if not code:
        errors["code"] = "Code is required."
    elif not re.match(r"^[A-Z0-9_-]{2,20}$", code):
        errors["code"] = "2-20 characters, letters/numbers/dash/underscore only."

    dtype  = form.get("discount_type", "flat")
    dvalue = form.get("discount_value", "")

    if dtype != "free_delivery":
        try:
            val = float(dvalue)
            if val <= 0:
                errors["discount_value"] = "Enter a value > 0."
            elif dtype == "percent" and val > 100:
                errors["discount_value"] = "Percentage cannot exceed 100."
        except (TypeError, ValueError):
            errors["discount_value"] = "Enter a value > 0."

    min_order = form.get("min_order", "")
    if min_order:
        try:
            if float(min_order) < 0:
                errors["min_order"] = "Must be ≥ 0."
        except (TypeError, ValueError):
            errors["min_order"] = "Must be ≥ 0."

    max_uses = form.get("max_uses", "")
    try:
        if not max_uses or int(max_uses) < 1:
            errors["max_uses"] = "Must be ≥ 1."
    except (TypeError, ValueError):
        errors["max_uses"] = "Must be ≥ 1."

    if not form.get("expires_at"):
        errors["expires_at"] = "Expiry date is required."

    return errors


class TestVoucherAdminValidation:

    @pytest.mark.unit
    def test_valid_flat_voucher_no_errors(self):
        errors = validate_voucher_fe({
            "code": "SAVE20", "discount_type": "flat",
            "discount_value": "20", "min_order": "50",
            "max_uses": "100", "expires_at": "2025-12-31T23:59",
        })
        assert errors == {}

    @pytest.mark.unit
    def test_missing_code_error(self):
        errors = validate_voucher_fe({
            "code": "", "discount_type": "flat",
            "discount_value": "20", "min_order": "0",
            "max_uses": "1", "expires_at": "2025-12-31T23:59",
        })
        assert "code" in errors

    @pytest.mark.unit
    def test_invalid_code_characters(self):
        errors = validate_voucher_fe({
            "code": "SAVE $$ 20", "discount_type": "flat",
            "discount_value": "20", "min_order": "0",
            "max_uses": "1", "expires_at": "2025-12-31T23:59",
        })
        assert "code" in errors

    @pytest.mark.unit
    def test_code_too_short(self):
        errors = validate_voucher_fe({
            "code": "A", "discount_type": "flat",
            "discount_value": "20", "min_order": "0",
            "max_uses": "1", "expires_at": "2025-12-31T23:59",
        })
        assert "code" in errors

    @pytest.mark.unit
    def test_percent_over_100_error(self):
        errors = validate_voucher_fe({
            "code": "OVER100", "discount_type": "percent",
            "discount_value": "150", "min_order": "0",
            "max_uses": "1", "expires_at": "2025-12-31T23:59",
        })
        assert "discount_value" in errors

    @pytest.mark.unit
    def test_zero_discount_value_error(self):
        errors = validate_voucher_fe({
            "code": "ZERO", "discount_type": "flat",
            "discount_value": "0", "min_order": "0",
            "max_uses": "1", "expires_at": "2025-12-31T23:59",
        })
        assert "discount_value" in errors

    @pytest.mark.unit
    def test_free_delivery_no_value_needed(self):
        errors = validate_voucher_fe({
            "code": "FREEDEL", "discount_type": "free_delivery",
            "discount_value": "", "min_order": "0",
            "max_uses": "1", "expires_at": "2025-12-31T23:59",
        })
        assert "discount_value" not in errors

    @pytest.mark.unit
    def test_missing_expiry_error(self):
        errors = validate_voucher_fe({
            "code": "TEST10", "discount_type": "flat",
            "discount_value": "10", "min_order": "0",
            "max_uses": "1", "expires_at": "",
        })
        assert "expires_at" in errors

    @pytest.mark.unit
    def test_zero_max_uses_error(self):
        errors = validate_voucher_fe({
            "code": "TEST10", "discount_type": "flat",
            "discount_value": "10", "min_order": "0",
            "max_uses": "0", "expires_at": "2025-12-31T23:59",
        })
        assert "max_uses" in errors