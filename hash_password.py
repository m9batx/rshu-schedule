"""Generate a bcrypt hash for the admin password.

Usage:
    python hash_password.py "your-new-password"

Then set the environment variables on the server (do NOT commit them):

    ADMIN_USER=mohammedbekhit
    ADMIN_PASSWORD_HASH=<the printed hash>
"""
import getpass
import sys

import bcrypt


def main():
    pwd = sys.argv[1] if len(sys.argv) > 1 else getpass.getpass("New admin password: ")
    if not pwd:
        print("No password given.")
        return 1
    hashed = bcrypt.hashpw(pwd.encode("utf-8"), bcrypt.gensalt(rounds=12))
    print(hashed.decode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
