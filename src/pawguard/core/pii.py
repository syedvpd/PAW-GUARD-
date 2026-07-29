"""Personally Identifiable Information masking utilities.

Used to mask sensitive data (phone numbers, email addresses, IP addresses)
in general system views so that only authorised roles see the full value.
"""

import re


def mask_email(email: str | None) -> str | None:
    if email is None:
        return None
    at = email.find("@")
    if at < 2:
        return email
    return email[0] + "***" + email[at - 1 :]


def mask_phone(phone: str | None) -> str | None:
    if phone is None:
        return None
    digits = re.sub(r"\D", "", phone)
    if len(digits) < 6:
        return "******"
    return digits[:2] + "****" + digits[-2:]


def mask_ip(ip_address: str | None) -> str | None:
    if ip_address is None:
        return None
    if "." in ip_address:
        parts = ip_address.split(".")
        if len(parts) == 4:
            return f"{parts[0]}.{parts[1]}.xxx.xxx"
    if ":" in ip_address:
        parts = ip_address.split(":")
        return f"{parts[0]}::xxxx"
    return ip_address


def mask_full_name(name: str | None) -> str | None:
    if name is None:
        return None
    parts = name.split()
    if not parts:
        return name
    return parts[0] + (" " + " ".join(p[0] + "***" for p in parts[1:]) if len(parts) > 1 else "")
