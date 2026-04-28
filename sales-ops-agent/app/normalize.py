import re
from urllib.parse import urlparse

LEGAL_SUFFIXES = {
    "ltd", "limited", "inc", "llc", "plc", "gmbh", "corp", "co", "company"
}


def normalize_email(email: str | None) -> str | None:
    if not email:
        return None
    value = email.strip().lower()
    return value or None


def email_domain(email: str | None) -> str | None:
    value = normalize_email(email)
    if not value or "@" not in value:
        return None
    return value.split("@", 1)[1]


def normalize_domain(url_or_domain: str | None) -> str | None:
    if not url_or_domain:
        return None
    value = url_or_domain.strip().lower()
    if not value:
        return None
    if "://" not in value:
        value = f"https://{value}"
    parsed = urlparse(value)
    host = parsed.netloc or parsed.path
    host = host.split(":", 1)[0]
    if host.startswith("www."):
        host = host[4:]
    return host or None


def normalize_company_name(name: str | None) -> str:
    if not name:
        return ""
    value = re.sub(r"[^a-zA-Z0-9\s]", " ", name.lower())
    parts = [part for part in value.split() if part not in LEGAL_SUFFIXES]
    return " ".join(parts)
