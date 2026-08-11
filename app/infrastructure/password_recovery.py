"""Interactive local password recovery command."""

from getpass import getpass

from app.infrastructure.auth import reset_admin_password


def main() -> int:
    password = getpass("New administrator password: ")
    confirm = getpass("Confirm new password: ")
    if password != confirm:
        print("Passwords do not match.")
        return 1
    ok, message = reset_admin_password(password)
    print(message)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
