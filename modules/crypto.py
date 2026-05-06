from cryptography.fernet import Fernet


def generate_key():
    return Fernet.generate_key()


def encrypt(key, data):
    f = Fernet(key)
    if isinstance(data, str):
        data = data.encode()
    return f.encrypt(data)


def decrypt(key, data):
    f = Fernet(key)
    return f.decrypt(data)
