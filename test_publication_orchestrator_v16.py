import unittest

from services.publication_orchestrator_v16 import plan_distribution


class PlanDistributionTests(unittest.TestCase):
    def test_requires_confirmed_publication(self):
        with self.assertRaises(ValueError) as ctx:
            plan_distribution({"publication_id": "p1", "status": "draft"})
        self.assertRegex(str(ctx.exception), "publication_must_be_confirmed_published")

    def test_idempotent_tasks_and_review_gates(self):
        event = {"publication_id": "pub-123", "status": "published"}
        a = plan_distribution(event, ["linkedin_profile", "x"])
        b = plan_distribution(event, ["x", "linkedin_profile"])
        self.assertEqual(a["idempotency_key"], b["idempotency_key"])
        self.assertEqual(
            [t["task_id"] for t in a["tasks"]],
            [t["task_id"] for t in b["tasks"]],
        )
        self.assertTrue(all(t["approval_required"] for t in a["tasks"]))
        self.assertTrue(all(
            t["status"] == "human_review_queue"
            for t in a["tasks"]
            if t["action"] in {"comment", "reaction", "share"}
        ))

    def test_paid_campaign_needs_explicit_approval(self):
        event = {"publication_id": "pub-123", "status": "published"}
        pending = plan_distribution(event, ["youtube"], include_paid=True)
        paid = next(t for t in pending["tasks"] if t["action"] == "paid_promotion")
        self.assertEqual(paid["status"], "approval_required")
        self.assertIs(paid["approval_required"], True)
        approved = plan_distribution(event, ["youtube"], include_paid=True, paid_approved=True)
        paid2 = next(t for t in approved["tasks"] if t["action"] == "paid_promotion")
        self.assertEqual(paid2["status"], "approved_to_queue")

    def test_unknown_channel_fails_closed(self):
        with self.assertRaises(ValueError) as ctx:
            plan_distribution({"publication_id": "p1", "status": "published"}, ["telegram_fake"])
        self.assertRegex(str(ctx.exception), "unsupported_channels")

    def test_requires_publication_id(self):
        with self.assertRaises(ValueError) as ctx:
            plan_distribution({"status": "published"})
        self.assertRegex(str(ctx.exception), "publication_id_required")


if __name__ == "__main__":
    unittest.main()
