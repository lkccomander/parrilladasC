import argparse
import sys
from getpass import getpass

from pydantic import ValidationError
from sqlalchemy.orm import Session

from parrilladas.core.config import Settings
from parrilladas.db.session import create_database_engine
from parrilladas.modules.accounts.errors import AccountError
from parrilladas.modules.accounts.models import Role
from parrilladas.modules.accounts.schemas import AccountCreate, PasswordReset
from parrilladas.modules.accounts.service import AccountService


def main() -> None:
    parser = argparse.ArgumentParser(description="Administración privada de cuentas Parrilladas")
    parser.add_argument("command", choices=["bootstrap-admin", "reset-password"])
    args = parser.parse_args()
    if not sys.stdin.isatty():
        parser.exit(1, "Use una terminal interactiva para introducir la contraseña en privado.\n")
    email = input("Correo: ")
    name = input("Nombre: ") if args.command == "bootstrap-admin" else None
    password = getpass("Contraseña (15–128 caracteres): ")
    confirmation = getpass("Confirmar contraseña: ")
    if password != confirmation:
        parser.exit(1, "Las contraseñas no coinciden.\n")
    try:
        data = (
            AccountCreate(email=email, display_name=name, role=Role.ADMIN, password=password)
            if args.command == "bootstrap-admin"
            else PasswordReset(email=email, password=password)
        )
    except ValidationError:
        parser.exit(1, "Revise correo, nombre y longitud de la contraseña.\n")
    engine = create_database_engine(Settings())
    try:
        with Session(engine, expire_on_commit=False) as session:
            service = AccountService(session)
            if args.command == "bootstrap-admin":
                service.bootstrap_admin(data)
            else:
                service.reset_password(data)
    except AccountError as error:
        parser.exit(1, f"{error}\n")
    finally:
        engine.dispose()
    print("Cuenta actualizada. La contraseña no se ha mostrado ni guardado en archivos.")


if __name__ == "__main__":
    main()
