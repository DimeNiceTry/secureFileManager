import secrets
import hashlib
from typing import Tuple
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, HashingError
from cryptography.fernet import Fernet
from loguru import logger

class CryptoService:

    def __init__(self):

        self.password_hasher = PasswordHasher(
            time_cost=3,
            memory_cost=65536,
            parallelism=1,
            hash_len=32,
            salt_len=16
        )

    def hash_password(self, password: str) -> str:

        try:
            return self.password_hasher.hash(password)
        except Exception as e:
            logger.error(f"Password hashing failed: {e}")
            raise HashingError(f"Failed to hash password: {e}")

    def verify_password(self, password: str, hashed_password: str) -> bool:

        try:
            self.password_hasher.verify(hashed_password, password)
            return True
        except VerifyMismatchError:
            return False
        except Exception as e:
            logger.error(f"Password verification failed: {e}")
            return False

    def needs_rehash(self, hashed_password: str) -> bool:

        try:
            return self.password_hasher.check_needs_rehash(hashed_password)
        except Exception:
            return True

    def generate_file_encryption_key(self) -> bytes:

        return Fernet.generate_key()

    def encrypt_data(self, data: bytes, key: bytes) -> bytes:

        f = Fernet(key)
        return f.encrypt(data)

    def decrypt_data(self, encrypted_data: bytes, key: bytes) -> bytes:

        f = Fernet(key)
        return f.decrypt(encrypted_data)

    def calculate_file_checksum(self, file_path: str) -> str:

        sha256_hash = hashlib.sha256()

        with open(file_path, "rb") as f:

            for chunk in iter(lambda: f.read(4096), b""):
                sha256_hash.update(chunk)

        return sha256_hash.hexdigest()

    def generate_secure_token(self, length: int = 32) -> str:

        return secrets.token_hex(length)

    def generate_salt(self, length: int = 16) -> bytes:

        return secrets.token_bytes(length)