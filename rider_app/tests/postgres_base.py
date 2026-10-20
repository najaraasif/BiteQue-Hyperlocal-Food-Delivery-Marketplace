"""Test harness for PostgreSQL.

Why this exists
---------------
Django's ``TransactionTestCase`` cleans the test database by truncating
every table that has a model. The project's test database also contains a
leftover auto-created many-to-many table, ``user_app_order_menu_items``,
which predates ``Order.menu_items`` being switched to the explicit
``OrderMenuItem`` through model. That leftover table still references
``merchant_app_restaurantmenu`` and is not part of Django's truncate list,
so PostgreSQL refuses to clean the database::

    cannot truncate a table referenced in a foreign key constraint
    DETAIL:  Table "user_app_order_menu_items" references
             "merchant_app_restaurantmenu".

Django itself solves this by issuing ``TRUNCATE ... CASCADE`` when it flushes
only a subset of the apps (``available_apps`` is set). This base class does
the same thing for every PostgreSQL test, which keeps the cleanup correct
without touching the migrations or any production code.

Usage
-----
    from rider_app.tests.postgres_base import PostgresTransactionTestCase


    class MyTest(PostgresTransactionTestCase):
        ...
"""
from django.core.management import call_command
from django.db import connections
from django.test import TransactionTestCase


class PostgresTransactionTestCase(TransactionTestCase):
    """A ``TransactionTestCase`` whose cleanup tolerates leftover tables."""

    def _fixture_teardown(self):
        for db_name in self._databases_names(include_mirrors=False):
            inhibit_post_migrate = (
                self.available_apps is not None
                or (
                    self.serialized_rollback
                    and hasattr(connections[db_name], '_test_serialized_contents')
                )
            )
            call_command(
                'flush',
                verbosity=0,
                interactive=False,
                database=db_name,
                reset_sequences=False,
                # the leftover many-to-many table references a table Django
                # truncates, so the referencing table has to go as well
                allow_cascade=True,
                inhibit_post_migrate=inhibit_post_migrate,
            )
