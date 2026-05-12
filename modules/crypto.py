import base64
import hmac
import os

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


def generate_key():
    return base64.urlsafe_b64encode(os.urandom(32))


def _derive(key):
    if isinstance(key, str):
        key = key.encode()
    raw = base64.urlsafe_b64decode(key)
    aes_key = raw[:16]
    hmac_key = raw[16:32]
    return aes_key, hmac_key


def encrypt(key, data):
    if isinstance(data, str):
        data = data.encode()
    aes_key, hmac_key = _derive(key)
    iv = os.urandom(16)
    padder = padding.PKCS7(128).padder()
    padded = padder.update(data) + padder.finalize()
    cipher = Cipher(algorithms.AES(aes_key), modes.CBC(iv))
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(padded) + encryptor.finalize()
    sig = hmac.new(hmac_key, iv + ciphertext, "sha256").digest()
    return sig + iv + ciphertext


def decrypt(key, data):
    aes_key, hmac_key = _derive(key)
    sig = data[:32]
    iv = data[32:48]
    ciphertext = data[48:]
    expected = hmac.new(hmac_key, iv + ciphertext, "sha256").digest()
    if not hmac.compare_digest(sig, expected):
        raise ValueError("HMAC mismatch: data corrupted or wrong key")
    cipher = Cipher(algorithms.AES(aes_key), modes.CBC(iv))
    decryptor = cipher.decryptor()
    padded = decryptor.update(ciphertext) + decryptor.finalize()
    unpadder = padding.PKCS7(128).unpadder()
    return unpadder.update(padded) + unpadder.finalize()
