import sqlite3
import unittest

from atlas_engine.identity_policy import RequestPrincipal, AuthorizationDenied
from atlas_engine.tenant_repository_prototype import initialize_prototype_schema, TenantTaskRepository
from atlas_engine.tenant_learning_repository import initialize_learning_schema, TenantLearningRepository
from atlas_engine.tenant_execution_repository import (
    ensure_execution_parent_keys, initialize_execution_schema, TenantExecutionRepository
)


class TenantExecutionRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        initialize_prototype_schema(self.db)
        initialize_learning_schema(self.db)
        ensure_execution_parent_keys(self.db)
        initialize_execution_schema(self.db)
        self.a = RequestPrincipal("issuer", "alice", "tenant-a", True,
                                  frozenset({"tasks:read", "tasks:write", "lessons:read", "lessons:write"}))
        self.b = RequestPrincipal("issuer", "bob", "tenant-b", True,
                                  frozenset({"tasks:read", "tasks:write", "lessons:read", "lessons:write"}))
        self.ta = TenantTaskRepository(self.db, self.a).create_task("A task")
        self.tb = TenantTaskRepository(self.db, self.b).create_task("B task")
        self.aa = TenantTaskRepository(self.db, self.a).create_attempt(self.ta, "failed")
        self.ab = TenantTaskRepository(self.db, self.b).create_attempt(self.tb, "failed")
        TenantLearningRepository(self.db, self.a).add_lesson("lesson-a", self.ta, "Validated lesson")
        self.ra = TenantExecutionRepository(self.db, self.a)
        self.rb = TenantExecutionRepository(self.db, self.b)

    def tearDown(self):
        self.db.close()

    def test_recovery_and_cancellation_are_tenant_scoped(self):
        self.ra.add_recovery_decision("d1", self.ta, self.aa, "retry", "Reviewed", True, True)
        self.ra.add_cancellation("c1", self.ta, self.aa, "Stop requested")
        self.assertEqual(len(self.ra.list_recovery_decisions(self.ta)), 1)
        self.assertEqual(len(self.ra.list_cancellations(self.ta)), 1)
        self.assertEqual(self.rb.list_recovery_decisions(self.tb), [])
        self.assertEqual(self.rb.list_cancellations(self.tb), [])
        with self.assertRaises(Exception):
            self.ra.add_recovery_decision("bad", self.ta, self.ab, "retry", "cross tenant")

    def test_retry_schedule_and_lesson_use(self):
        self.ra.add_retry_schedule("s1", self.ta, self.aa, 2, "2030-01-01T00:00:00Z",
                                   "2030-01-02T00:00:00Z", "worker", "1", "idem-1",
                                   "temporary", {"max_attempts": 2})
        self.ra.record_lesson_use("u1", self.ta, self.aa, "lesson-a")
        self.assertEqual(self.ra.list_retry_schedules(self.ta)[0]["policy"], {"max_attempts": 2})
        self.assertEqual(len(self.ra.list_lesson_uses(self.ta)), 1)
        self.assertEqual(self.rb.list_retry_schedules(self.tb), [])
        self.assertEqual(self.rb.list_lesson_uses(self.tb), [])
        with self.assertRaises(Exception):
            self.ra.record_lesson_use("bad-use", self.ta, self.aa, "missing-lesson")

    def test_sql_foreign_keys_reject_cross_tenant_parent_links(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute(
                """INSERT INTO tenant_recovery_decisions
                   (decision_id, tenant_id, task_id, attempt_id, action, reason)
                   VALUES ('bad', 'tenant-a', ?, ?, 'retry', 'forged')""",
                (self.ta, self.ab),
            )

    def test_scope_is_required(self):
        read_only = RequestPrincipal("issuer", "alice", "tenant-a", True,
                                     frozenset({"tasks:read", "lessons:read"}))
        repo = TenantExecutionRepository(self.db, read_only)
        with self.assertRaises(AuthorizationDenied):
            repo.add_recovery_decision("denied", self.ta, self.aa, "retry", "no write scope")


if __name__ == "__main__":
    unittest.main()


    def test_every_execution_child_write_rejects_foreign_tenant_attempt(self):
        with self.assertRaises(Exception):
            self.ra.add_cancellation("foreign-cancel", self.ta, self.ab, "cross-tenant")
        with self.assertRaises(Exception):
            self.ra.add_retry_schedule(
                "foreign-retry", self.ta, self.ab, 2,
                "2030-01-01T00:00:00Z", "2030-01-02T00:00:00Z",
                "worker", "1", "foreign-idem", "temporary", {"max_attempts": 2},
            )
        with self.assertRaises(Exception):
            self.ra.record_lesson_use("foreign-use", self.ta, self.ab, "lesson-a")
        self.assertEqual(self.ra.list_cancellations(self.ta), [])
        self.assertEqual(self.ra.list_retry_schedules(self.ta), [])
        self.assertEqual(self.ra.list_lesson_uses(self.ta), [])

    def test_foreign_tenant_task_ids_are_not_visible_in_execution_reads(self):
        self.assertEqual(self.ra.list_recovery_decisions(self.ta), [])
        self.assertEqual(self.ra.list_cancellations(self.ta), [])
        self.assertEqual(self.ra.list_retry_schedules(self.ta), [])
        self.assertEqual(self.ra.list_lesson_uses(self.ta), [])
        with self.assertRaises(Exception):
            self.ra.list_cancellations(self.tb)
        with self.assertRaises(Exception):
            self.ra.list_retry_schedules(self.tb)
        with self.assertRaises(Exception):
            self.ra.list_lesson_uses(self.tb)
