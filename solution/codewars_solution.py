from hashlib import md5


def crack(hash):
    target = hash.lower()

    for number in range(100_000):
        pin = f"{number:05d}"

        if md5(pin.encode("ascii")).hexdigest() == target:
            return pin

    return None
