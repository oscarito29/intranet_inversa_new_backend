"""
Django quitó `UnsaltedMD5PasswordHasher` (estaba deprecado desde hace años),
pero `identify_hasher()` sigue reconociendo un hash de 32 caracteres hex sin
`$` como algoritmo `unsalted_md5` (ver django.contrib.auth.hashers). Esta
clase lo reimplementa solo para VERIFICAR los hashes MD5 sin salt que ya
existen en la tabla `user` legacy. Nunca se usa para generar hashes nuevos:
Argon2PasswordHasher es el primero en PASSWORD_HASHERS, así que todo login
exitoso re-hashea la contraseña a Argon2 automáticamente.
"""

import hashlib

from django.contrib.auth.hashers import BasePasswordHasher, mask_hash
from django.utils.crypto import constant_time_compare
from django.utils.translation import gettext_noop as _


class LegacyUnsaltedMD5PasswordHasher(BasePasswordHasher):
    algorithm = 'unsalted_md5'

    def salt(self) -> str:
        return ''

    def encode(self, password: str, salt: str) -> str:
        if salt != '':
            raise ValueError('salt must be empty.')
        return hashlib.md5(password.encode()).hexdigest()

    def decode(self, encoded: str) -> dict:
        return {'algorithm': self.algorithm, 'hash': encoded, 'salt': None}

    def verify(self, password: str, encoded: str) -> bool:
        return constant_time_compare(encoded, self.encode(password, ''))

    def safe_summary(self, encoded: str) -> dict:
        decoded = self.decode(encoded)
        return {_('algorithm'): decoded['algorithm'], _('hash'): mask_hash(decoded['hash'], show=3)}

    def harden_runtime(self, password: str, encoded: str) -> None:
        pass
