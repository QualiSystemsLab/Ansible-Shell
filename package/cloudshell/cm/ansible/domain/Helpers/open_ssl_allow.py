import os

OPEN_SSL_ENV_VARS = [
    "CRYPTOGRAPHY_ALLOW_OPENSSL_102",
    "CRYPTOGRAPHY_ALLOW_OPENSSL_101"
]


def crypto_allow_openssl():
    for curr_var in OPEN_SSL_ENV_VARS:
        os.environ[curr_var] = "1"
