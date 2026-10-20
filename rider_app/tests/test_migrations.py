"""Tests for the rider_app schema repair migration.

They cover the three states that matter:

* a healthy schema - the migration must not touch it;
* a drifted schema (the columns are gone but ``django_migrations`` already
  records the migration as applied) - the historical failure mode, where
  ``migrate`` alone can no longer repair anything;
* a drifted schema that still holds rows - the repair must not lose data.
"""
import importlib

from django.apps import apps as global_apps
from django.db import OperationalError, connection
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.recorder import MigrationRecorder
from django.test import TransactionTestCase
from django.test.utils import CaptureQueriesContext

from rider_app.models import OrderAssignment

from .test_assignment_flow import make_order, make_rider, make_user

migration = importlib.import_module(
    'rider_app.migrations.0002_ensure_acceptance_columns'
)


class RepairMigrationTestCase(TransactionTestCase):
    """Base class that can drop and restore assignment columns."""

    def tearDown(self):
        # TransactionTestCase flushes rows but keeps the schema, so any
        # column removed by a test has to be put back for the next test.
        self.restore_columns()

    # -- helpers ---------------------------------------------------------
    def column_names(self):
        with connection.cursor() as cursor:
            return {
                description.name
                for description in connection.introspection.get_table_description(
                    cursor, 'rider_app_orderassignment'
                )
            }

    def drop_column(self, field_name):
        field = OrderAssignment._meta.get_field(field_name)
        with connection.schema_editor() as editor:
            editor.remove_field(OrderAssignment, field)

    def restore_columns(self):
        with connection.schema_editor() as editor:
            migration.ensure_acceptance_columns(global_apps, editor)

    def apply_migration(self):
        self.restore_columns()

    def pending_migrations(self):
        executor = MigrationExecutor(connection)
        targets = executor.loader.graph.leaf_nodes()
        return executor.migration_plan(targets)

    def recorded_migrations(self, app='rider_app'):
        recorder = MigrationRecorder(connection)
        return set(
            recorder.migration_qs.filter(app=app).values_list('name', flat=True)
        )


class HealthySchemaTests(RepairMigrationTestCase):
    def test_columns_are_present_in_a_freshly_migrated_database(self):
        self.assertIn('response_time', self.column_names())
        self.assertIn('acceptance_score', self.column_names())

    def test_migration_is_recorded_as_applied(self):
        self.assertIn('0002_ensure_acceptance_columns', self.recorded_migrations())

    def test_migration_executes_no_ddl_on_a_healthy_schema(self):
        with CaptureQueriesContext(connection) as queries:
            self.apply_migration()

        statements = [query['sql'] for query in queries.captured_queries]
        altering = [
            sql for sql in statements
            if 'ALTER TABLE' in sql.upper() or 'DROP ' in sql.upper()
        ]
        self.assertEqual(altering, [])

    def test_columns_survive_a_second_run(self):
        self.apply_migration()
        self.apply_migration()

        self.assertIn('response_time', self.column_names())
        self.assertIn('acceptance_score', self.column_names())

    def test_reverse_migration_does_not_drop_columns(self):
        with connection.schema_editor() as editor:
            migration.noop(global_apps, editor)

        self.assertIn('response_time', self.column_names())
        self.assertIn('acceptance_score', self.column_names())


class DriftedSchemaTests(RepairMigrationTestCase):
    def test_drift_reproduces_the_reported_failure(self):
        self.drop_column('response_time')

        with self.assertRaises(OperationalError):
            list(OrderAssignment.objects.all())

    def test_migrate_alone_cannot_repair_a_drifted_schema(self):
        # The migration is already recorded as applied, so Django has nothing
        # left to run - exactly the state that made the 2025 incident sticky.
        self.assertIn('0002_ensure_acceptance_columns', self.recorded_migrations())
        self.drop_column('response_time')

        self.assertEqual(self.pending_migrations(), [])
        self.assertNotIn('response_time', self.column_names())

    def test_repair_restores_the_missing_columns(self):
        self.drop_column('response_time')
        self.drop_column('acceptance_score')

        self.apply_migration()

        self.assertIn('response_time', self.column_names())
        self.assertIn('acceptance_score', self.column_names())
        self.assertEqual(
            list(OrderAssignment.objects.all().values_list('id', flat=True)), []
        )

    def test_repair_restores_acceptance_score_with_a_default(self):
        rider = make_rider('drift_default')
        order = make_order(make_user('drift_default_customer'))
        assignment = OrderAssignment.objects.create(
            rider=rider, order=order, status='accepted'
        )

        self.drop_column('acceptance_score')
        self.apply_migration()

        assignment.refresh_from_db()
        self.assertEqual(assignment.acceptance_score, 0)
        self.assertEqual(assignment.status, 'accepted')

    def test_repair_only_touches_the_assignments_table(self):
        self.drop_column('response_time')

        with CaptureQueriesContext(connection) as queries:
            self.apply_migration()

        statements = [
            query['sql'] for query in queries.captured_queries
            if 'ALTER TABLE' in query['sql'].upper()
        ]
        self.assertTrue(statements)
        for sql in statements:
            self.assertIn('rider_app_orderassignment', sql)


class DataPreservationTests(RepairMigrationTestCase):
    def setUp(self):
        super().setUp()
        self.rider = make_rider('drift_rows')
        self.order = make_order(make_user('drift_rows_customer'))
        self.assignment = OrderAssignment.objects.create(
            rider=self.rider, order=self.order, status='accepted'
        )

    def test_existing_rows_are_preserved_by_the_repair(self):
        self.drop_column('response_time')
        self.drop_column('acceptance_score')

        self.apply_migration()

        rows = list(
            OrderAssignment.objects.all().values(
                'id', 'status', 'rider_id', 'order_id'
            )
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['id'], self.assignment.id)
        self.assertEqual(rows[0]['status'], 'accepted')
        self.assertEqual(rows[0]['rider_id'], self.rider.id)
        self.assertEqual(rows[0]['order_id'], self.order.id)

    def test_related_records_are_preserved_by_the_repair(self):
        self.drop_column('response_time')

        self.apply_migration()

        self.assertTrue(self.rider.orderassignment_set.exists())
        self.assertEqual(
            self.rider.orderassignment_set.count(), 1
        )

    def test_response_time_is_usable_again_after_the_repair(self):
        from datetime import timedelta

        self.drop_column('response_time')
        self.apply_migration()

        self.assignment.response_time = timedelta(seconds=45)
        self.assignment.save()

        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.response_time, timedelta(seconds=45))
