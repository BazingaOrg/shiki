import hashlib
import json
import unittest

import test_codex_eval as existing
from test_codex_eval import M
from lib.adapters import ClaudeAdapter, GrokAdapter


class RoutingUpdateTests(unittest.TestCase):
    def setUp(self):
        self.helpers = existing.EvaluationTests()

    def test_optional_delegation_checks_every_actual_worker(self):
        expected = {
            "routing": {"allowed_roles": ["fast-worker"]},
            "runtime": [{"role": "fast-worker", "model": "m", "effort": "e", "sandbox_type": "s"}],
        }
        case = self.helpers.case(**expected)
        for roles in ([], ["fast-worker"], ["fast-worker", "fast-worker"]):
            self.assertEqual(M.grade(case, {}, {}, self.helpers.trace(roles), None)["status"], "PASS")
        trace = self.helpers.trace(["fast-worker", "fast-worker"])
        trace["native_agents"][1]["runtime"]["model"] = "wrong"
        self.assertEqual(M.grade(case, {}, {}, trace, None)["hard_status"], "FAIL")
        trace["native_agents"][1]["runtime"] = None
        self.assertEqual(M.grade(case, {}, {}, trace, None)["hard_status"], "UNKNOWN")
        self.assertEqual(M.grade(case, {}, {}, self.helpers.trace(["deep-reasoner"]), None)["behavioral_status"], "FAIL")

    def test_bulk_result_requires_correct_content_and_no_extra_edits(self):
        case = next(case for case in M.load(M.ROOT / "manifest.json")["cases"] if case["id"] == "policy-bulk-config")
        before = {path: "old" for path in case["expected"]["exact_changed_paths"]}
        correct = {path: hashlib.sha256(b"enabled = true\n").hexdigest() for path in before}
        self.assertEqual(M.grade(case, before, correct, self.helpers.trace(), None)["status"], "PASS")
        wrong = {**correct, next(iter(correct)): hashlib.sha256(b"enabled = false\n\n").hexdigest()}
        self.assertEqual(M.grade(case, before, wrong, self.helpers.trace(), None)["hard_status"], "FAIL")
        self.assertEqual(M.grade(case, before, {**correct, "unrelated.txt": "changed"}, self.helpers.trace(), None)["hard_status"], "FAIL")

    def test_independent_review_cannot_be_replaced_by_direct_execution(self):
        case = next(case for case in M.load(M.ROOT / "manifest.json")["cases"] if case["id"] == "policy-auth-high-assurance")
        result = M.grade(case, {}, {}, self.helpers.trace(), None)
        self.assertEqual(result["behavioral_status"], "FAIL")
        self.assertNotEqual(result["hard_status"], "PASS")

    def test_frozen_review_separates_mutation_from_unobserved_shell(self):
        case = self.helpers.case(require_same_identity=True)
        trace = self.helpers.trace()
        self.assertEqual(M.grade(case, {}, {}, trace, None)["hard_status"], "PASS")
        trace["child_write_capable_attempts"] = 1
        self.assertEqual(M.grade(case, {}, {}, trace, None)["hard_status"], "UNKNOWN")
        trace["child_mutation_attempts"] = 1
        self.assertEqual(M.grade(case, {}, {}, trace, None)["hard_status"], "FAIL")

    def test_known_write_failure_is_not_hidden_by_unknown_runtime(self):
        case = self.helpers.case(runtime=[{"role": "qa-runner"}], protected_paths=["USER.md"])
        self.assertEqual(M.grade(case, {}, {"USER.md": "changed"}, self.helpers.trace(), None)["hard_status"], "FAIL")

    def test_model_experiment_preserves_other_confounders(self):
        baseline = self.helpers.summary(["PASS"])
        baseline["results"][0]["actual_parent_runtime"] = {"model": "m"}
        candidate = json.loads(json.dumps(baseline))
        candidate["model"] = "new-model"
        candidate["results"][0]["actual_parent_runtime"] = {"model": "new-model"}
        self.assertEqual(M.compare_summaries(baseline, candidate, M.wilson, .2)["status"], "CONFOUNDED")
        report = M.compare_summaries(baseline, candidate, M.wilson, .2, "models")
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["models"]["candidate"], "new-model")
        self.assertIsNone(report["usage"]["candidate"])
        for field in ("config_digest", "cli_version", "runner_sha256", "adapter", "effort", "repetitions", "timeout", "max_input_tokens"):
            altered = {**candidate, field: "different"}
            self.assertEqual(M.compare_summaries(baseline, altered, M.wilson, .2, "models")["status"], "CONFOUNDED")

    def test_optional_direct_success_does_not_claim_a_spawn(self):
        summary = {"results": [{"case": "policy-architecture", "kind": "policy", "actual_child_runtime": [], "grade": {"hard_status": "PASS", "behavioral_status": "PASS"}}]}
        claim = next(row for row in M.factcheck(summary)["claims"] if row["id"] == "subagents-guidance-trigger")
        self.assertEqual(claim["outcome"], "doc_only")

    def test_invalid_optional_roles_and_content_paths_are_rejected(self):
        manifest = M.load(M.ROOT / "manifest.json")
        manifest["cases"][0]["expected"]["routing"] = {"allowed_roles": ["unknown"]}
        manifest["cases"][0]["expected"]["expected_contents"] = {"../outside": "bad"}
        errors = M.validate_manifest(manifest)
        self.assertIn("bad routing role: plumbing-direct", errors)
        self.assertIn("bad expected_contents: plumbing-direct", errors)

    def test_unknown_grok_capability_does_not_pass(self):
        declared = {"model": "grok-4.6", "effort": "medium", "sandbox_type": "workspace-write"}
        actual = {"model": "grok-4.6-build", "effort": "medium", "sandbox_policy": {"type": "future-mode"}}
        self.assertIsNone(GrokAdapter().runtime_contract(declared, actual))

    def test_claude_unobserved_runtime_cannot_be_promoted_as_pass(self):
        case = self.helpers.case(runtime=[{"role": "qa-runner", "model": "haiku", "effort": "unobserved", "sandbox_type": "unobserved"}])
        trace = self.helpers.trace(["qa-runner"])
        trace["native_agents"][0]["runtime"] = {"model": "claude-haiku-4-5-20251001", "effort": "unobserved", "sandbox_policy": {"type": "unobserved"}}
        self.assertEqual(M.grade(case, {}, {}, trace, None, contract=ClaudeAdapter().runtime_contract)["hard_status"], "UNKNOWN")

    def test_provider_reported_cost_and_missing_coverage_are_distinct(self):
        import tempfile
        from pathlib import Path
        from lib.evidence import reported_cost
        for invalid in (None, True, -1, float("nan"), float("inf"), "0.1"):
            self.assertIsNone(reported_cost(invalid))
        with tempfile.TemporaryDirectory() as directory:
            events, _ = GrokAdapter().stream_evidence(json.dumps({"type": "end", "sessionId": "parent", "usage": {"input_tokens": 5}, "total_cost_usd": .01}), Path(directory))
            trace = M.normalize_trace([], events)
            self.assertEqual(trace["reported_cost_usd"], .01)
        totals = M.usage_totals([{"tokens": {"input_tokens": 5}, "reported_cost_usd": .01}, {"tokens": {}}])
        self.assertEqual(totals["reported_cost_usd"], .01)
        self.assertEqual(totals["cost_observed_cases"], 1)
        self.assertEqual(totals["token_observed_cases"], 1)
        self.assertEqual(totals["total_cases"], 2)
        self.assertIsNone(M.usage_totals([{"tokens": {}}])["reported_cost_usd"])

    def test_grok_role_files_are_snapshotted_and_injected(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            adapter = GrokAdapter()
            snapshot = adapter.snapshot(M.REPO, root)
            self.assertIn("grok/roles/qa-runner.toml", snapshot["hashes"])
            work = root / "work"
            work.mkdir()
            adapter.prepare(work, Path(snapshot["path"]), "low")
            self.assertIn(".grok/roles/qa-runner.toml", adapter.injected_paths(work))
            self.assertEqual((work / ".grok/roles/qa-runner.toml").read_text(), (M.REPO / "grok/roles/qa-runner.toml").read_text())

    def test_grok_1024_lifecycle_uses_spawn_identity_and_metadata(self):
        import tempfile
        from pathlib import Path
        data = M.load(Path(__file__).parent / 'fixtures/grok-1.0.24-lifecycle.json')
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory) / data['parent_id']
            parent.mkdir()
            (parent / 'chat_history.jsonl').write_text('\n'.join(json.dumps(row) for row in data['parent_history']))
            meta_path = parent / 'subagents' / data['child_id'] / 'meta.json'
            meta_path.parent.mkdir(parents=True)
            meta_path.write_text(json.dumps(data['child_meta']))
            adapter = GrokAdapter()
            roles, capabilities, completed = adapter._parent_facts(parent)
            self.assertEqual(roles, {data['child_id']: 'qa-runner'})
            self.assertEqual(capabilities, {})
            self.assertEqual(completed, {data['child_id']})
            self.assertEqual(adapter.child_lifecycles[data['child_id']][1], data['child_meta']['completed_at'])
            rows = [row for row in data['parent_history'] if row.get('type') != 'tool_result' or '=== Task' not in row.get('content', '')]
            (parent / 'chat_history.jsonl').write_text('\n'.join(json.dumps(row) for row in rows))
            meta = {**data['child_meta'], 'status': 'running', 'completed_at': None}
            meta_path.write_text(json.dumps(meta))
            self.assertEqual(adapter._parent_facts(parent)[2], set())
            meta_path.write_text(json.dumps({**data['child_meta'], 'parent_session_id': 'wrong-parent'}))
            self.assertEqual(adapter._parent_facts(parent)[2], set())

    def test_grok_polling_order_does_not_assign_roles_or_complete_running_tasks(self):
        import tempfile
        from pathlib import Path
        def call(ident, name, args):
            return {'type': 'assistant', 'tool_calls': [{'id': ident, 'name': name, 'arguments': json.dumps(args)}]}
        rows = [
            call('a', 'spawn_subagent', {'subagent_type': 'fast-worker'}),
            {'type': 'tool_result', 'tool_call_id': 'a', 'content': 'subagent_id: child-a'},
            call('b', 'spawn_subagent', {'subagent_type': 'qa-runner'}),
            {'type': 'tool_result', 'tool_call_id': 'b', 'content': 'subagent_id: child-b'},
            call('wait', 'get_command_or_subagent_output', {'task_ids': ['child-b', 'child-a']}),
            {'type': 'tool_result', 'tool_call_id': 'wait', 'content': '=== Task child-b ===\nStatus: running\n=== Task child-a ===\nStatus: completed\nExit Code: 0\n=== Output ===\n'},
        ]
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            (parent / 'chat_history.jsonl').write_text('\n'.join(json.dumps(row) for row in rows))
            roles, _, completed = GrokAdapter()._parent_facts(parent)
            self.assertEqual(roles, {'child-a': 'fast-worker', 'child-b': 'qa-runner'})
            self.assertEqual(completed, {'child-a'})

    def test_model_experiment_requires_observed_requested_model(self):
        baseline = self.helpers.summary(["PASS"])
        candidate = self.helpers.summary(["PASS"])
        report = M.compare_summaries(baseline, candidate, M.wilson, .2, "models")
        self.assertIn("candidate_model_unobserved", report["confounders"])
        baseline["results"][0]["actual_parent_runtime"] = {"model": "m"}
        candidate["results"][0]["actual_parent_runtime"] = {"model": "fallback"}
        report = M.compare_summaries(baseline, candidate, M.wilson, .2, "models")
        self.assertIn("candidate_model_mismatch", report["confounders"])

    def test_claude_requested_effort_is_applied_to_invocation(self):
        from pathlib import Path
        adapter = ClaudeAdapter()
        adapter.info = {"binary": "claude"}
        argv = adapter.invocation(Path("."), "task", "claude-opus-5", "high")
        self.assertEqual(argv[argv.index("--effort") + 1], "high")

    def test_model_experiment_rejects_mid_session_fallback(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            session = Path(directory) / "parent.jsonl"
            session.write_text("\n".join(json.dumps(row) for row in [
                {"type": "session_meta", "session_id": "parent", "agent_role": None},
                {"type": "turn_context", "model": "fallback", "effort": "high", "sandbox_policy": {}},
                {"type": "turn_context", "model": "m", "effort": "high", "sandbox_policy": {}},
            ]))
            trace = M.normalize_trace([session])
            self.assertEqual(trace["parent_runtime"]["observed_models"], ["fallback", "m"])
        baseline = self.helpers.summary(["PASS"])
        baseline["results"][0]["actual_parent_runtime"] = {"model": "m"}
        candidate = self.helpers.summary(["PASS"])
        candidate["results"][0]["actual_parent_runtime"] = trace["parent_runtime"]
        report = M.compare_summaries(baseline, candidate, M.wilson, .2, "models")
        self.assertIn("candidate_model_mismatch", report["confounders"])

    def test_model_experiment_rejects_unrecorded_run_limits(self):
        baseline = self.helpers.summary(["PASS"])
        baseline["results"][0]["actual_parent_runtime"] = {"model": "m"}
        for field in ("repetitions", "timeout", "max_input_tokens"):
            candidate = json.loads(json.dumps(baseline))
            del candidate[field]
            report = M.compare_summaries(baseline, candidate, M.wilson, .2, "models")
            self.assertEqual(report["status"], "CONFOUNDED")
            self.assertIn(f"candidate_{field}_unobserved", report["confounders"])

    def test_run_limits_are_attested(self):
        from lib.evidence import summary_core
        summary = self.helpers.summary(["PASS"])
        core = summary_core(summary)
        for field in ("repetitions", "timeout", "max_input_tokens"):
            self.assertEqual(core[field], summary[field])
