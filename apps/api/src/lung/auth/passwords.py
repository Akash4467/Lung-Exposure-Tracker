"""Password hashing with argon2id (argon2-cffi's defaults follow the RFC 9106 guidance)."""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_hasher = PasswordHasher()
# Verified against when the account doesn't exist, so a wrong email costs the same time as a
# wrong password and response timing doesn't reveal which emails are registered.
_DUMMY_HASH = _hasher.hash("dummy-password-for-timing")

MIN_LENGTH = 8
MAX_LENGTH = 128


class WeakPasswordError(ValueError):
    pass


def check_policy(password: str, email: str | None = None) -> None:
    """Length-based policy (NIST SP 800-63B): no composition rules, but no trivial reuse."""
    if len(password) < MIN_LENGTH:
        raise WeakPasswordError(f"password must be at least {MIN_LENGTH} characters")
    if len(password) > MAX_LENGTH:
        raise WeakPasswordError(f"password must be at most {MAX_LENGTH} characters")
    if email and password.strip().lower() == email.strip().lower():
        raise WeakPasswordError("password must not be your email address")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(stored_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(stored_hash or _DUMMY_HASH, password) and stored_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(stored_hash: str) -> bool:
    return _hasher.check_needs_rehash(stored_hash)
