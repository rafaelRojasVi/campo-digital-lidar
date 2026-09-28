from __future__ import annotations

import pytest
from app.token_crypto import TokenDecryptionError, decrypt_token, encrypt_token
from cryptography.fernet import Fernet


def _key() -> str:
    return Fernet.generate_key().decode("utf-8")


def test_decrypt_token_recovers_the_original_value() -> None:
    key = _key()

    ciphertext = encrypt_token("a-real-graph-access-token", key=key)

    assert decrypt_token(ciphertext, key=key) == "a-real-graph-access-token"


def test_encrypt_token_does_not_store_the_plaintext() -> None:
    key = _key()

    ciphertext = encrypt_token("a-real-graph-access-token", key=key)

    assert b"a-real-graph-access-token" not in ciphertext


def test_decrypt_token_rejects_the_wrong_key() -> None:
    ciphertext = encrypt_token("a-real-graph-access-token", key=_key())

    with pytest.raises(TokenDecryptionError):
        decrypt_token(ciphertext, key=_key())


def test_decrypt_token_rejects_tampered_ciphertext() -> None:
    key = _key()
    ciphertext = bytearray(encrypt_token("a-real-graph-access-token", key=key))
    ciphertext[-1] ^= 0xFF

    with pytest.raises(TokenDecryptionError):
        decrypt_token(bytes(ciphertext), key=key)
