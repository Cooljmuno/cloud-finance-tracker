import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError, connection, transaction
from psycopg import sql

APP_ROLE = "finance_app"


class Command(BaseCommand):
    help = "Create the restricted application role during an administrator bootstrap task."
    requires_system_checks = []

    def handle(self, *args, **options):
        if (
            os.getenv("ENABLE_DATABASE_BOOTSTRAP") != "true"
            or os.getenv("DJANGO_SETTINGS_MODULE") != "config.settings.production"
            or settings.DEBUG
        ):
            raise CommandError(
                "Database bootstrap is disabled outside an explicit production task."
            )

        password = os.getenv("APP_DATABASE_PASSWORD", "")
        if len(password) < 32 or "\x00" in password:
            raise CommandError("APP_DATABASE_PASSWORD must contain at least 32 valid characters.")
        if connection.vendor != "postgresql":
            raise CommandError("Database bootstrap requires PostgreSQL.")
        if connection.settings_dict["USER"] == APP_ROLE:
            raise CommandError("Database bootstrap requires the separate administrator connection.")

        try:
            with transaction.atomic(), connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                    ["cloud-finance-tracker:database-bootstrap"],
                )
                cursor.execute(
                    "SELECT rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls "
                    "FROM pg_roles WHERE rolname = %s",
                    [APP_ROLE],
                )
                existing = cursor.fetchone()
                if existing and any(existing):
                    raise CommandError("The existing application role has unexpected privileges.")
                if existing:
                    cursor.execute(
                        "SELECT 1 FROM pg_auth_members WHERE member = "
                        "(SELECT oid FROM pg_roles WHERE rolname = %s) LIMIT 1",
                        [APP_ROLE],
                    )
                    if cursor.fetchone():
                        raise CommandError(
                            "The existing application role has unexpected memberships."
                        )
                    cursor.execute(
                        sql.SQL("ALTER ROLE {} WITH LOGIN NOINHERIT PASSWORD {}").format(
                            sql.Identifier(APP_ROLE), sql.Literal(password)
                        )
                    )
                else:
                    cursor.execute(
                        sql.SQL(
                            "CREATE ROLE {} WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
                            "NOREPLICATION NOBYPASSRLS NOINHERIT PASSWORD {}"
                        ).format(sql.Identifier(APP_ROLE), sql.Literal(password))
                    )
                cursor.execute("SELECT current_database()")
                database_name = cursor.fetchone()[0]
                cursor.execute(
                    sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                        sql.Identifier(database_name), sql.Identifier(APP_ROLE)
                    )
                )
                cursor.execute(
                    sql.SQL("GRANT USAGE, CREATE ON SCHEMA public TO {}").format(
                        sql.Identifier(APP_ROLE)
                    )
                )
        except DatabaseError:
            raise CommandError(
                "Database bootstrap failed; check connectivity and administrator permissions."
            ) from None

        self.stdout.write(self.style.SUCCESS("Application database role is ready."))
