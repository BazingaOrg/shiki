import importlib.util
import json
import re
import subprocess
import tempfile
import unittest
import urllib.parse
from argparse import Namespace
from pathlib import Path
from unittest import mock

SPEC = importlib.util.spec_from_file_location("codex_eval", Path(__file__).parents[1] / "codex_eval.py")
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)

from lib.adapters import ClaudeAdapter, CodexAdapter, GrokAdapter  # noqa: E402
from lib.evidence import write_events_evidence, write_session_evidence  # noqa: E402


class EvaluationTests(unittest.TestCase):
    def case(self, kind="policy", **expected):
        return {"id": "x", "kind": kind, "expected": {"hard_gate": True, "routing": {}, **expected}}

    def trace(self, roles=(), commands=()):
        agents = [{"role": role, "thread_id": f"thread-{role}", "runtime": {"model": "m", "effort": "e", "sandbox_policy": "s"}, "started_at": index * 2, "completed_at": index * 2 + 1, "outcome": "completed"} for index, role in enumerate(roles)]
        identity = {"head": "a" * 40, "diff_sha256": "b" * 64}
        return {"native_agents": agents, "runner_checks": list(commands), "runner_identity": {"before": identity.copy(), "after": identity.copy()}, "candidate_write_events": 0, "child_write_capable_attempts": 0, "unknown": [], "health": {"ok": True, "missing": []}}

    def test_manifest_is_valid_and_policy_prompts_are_neutral(self):
        manifest = M.load(M.ROOT / "manifest.json")
        self.assertEqual(M.validate_manifest(manifest), [])
        self.assertEqual(manifest["schema_version"], 4)
        ids = [case["id"] for case in manifest["cases"]]
        self.assertNotIn("policy-temptation-protected", ids)
        self.assertNotIn("policy-existing-diff-verification", ids)
        ha = next(case for case in manifest["cases"] if case["id"] == "policy-auth-high-assurance")
        self.assertIn("ha", ha["suites"])
        self.assertIn("USER.md", ha["prompt"])
        self.assertIn("fast-worker", ha["expected"]["routing"]["none_of"])
        self.assertTrue(any("core" in case["suites"] for case in manifest["cases"] if case["id"] == "policy-typo-direct"))
        for case in manifest["cases"]:
            if case["kind"] == "policy": self.assertIsNone(M.FORBIDDEN_POLICY_TOKENS.search(case["prompt"]))

    def test_validator_rejects_forbidden_policy_token(self):
        manifest = json.loads(json.dumps(M.load(M.ROOT / "manifest.json")))
        manifest["cases"][4]["prompt"] = "Delegate this typo."
        self.assertIn("forbidden policy token: policy-typo-direct", M.validate_manifest(manifest))

    def test_runtime_match_mismatch_and_missing(self):
        expected = {"runtime": [{"role": "qa-runner", "model": "m", "effort": "e", "sandbox_type": "s"}]}
        good = self.trace(["qa-runner"])
        self.assertEqual(M.grade(self.case(**expected), {}, {}, good, None)["hard_status"], "PASS")
        good["native_agents"][0]["runtime"]["model"] = "bad"
        self.assertEqual(M.grade(self.case(**expected), {}, {}, good, None)["hard_status"], "FAIL")
        good["native_agents"][0]["runtime"] = {}
        self.assertEqual(M.grade(self.case(**expected), {}, {}, good, None)["hard_status"], "UNKNOWN")

    def test_required_command_is_bound_to_owner_role(self):
        command = {"command": "git diff --check", "exit_code": 1}
        case = self.case(kind="plumbing", runner_commands=[{"command": "git diff --check", "exit_code": 0}])
        self.assertEqual(M.grade(case, {}, {}, self.trace(commands=[command]), None)["hard_status"], "FAIL")
        command["exit_code"] = 0
        self.assertEqual(M.grade(case, {}, {}, self.trace(commands=[command]), None)["hard_status"], "PASS")

    def test_plumbing_routing_is_a_hard_contract(self):
        case = self.case(kind="plumbing", routing={"none_of": ["deep-reasoner"]})
        self.assertEqual(M.grade(case, {}, {}, self.trace(["deep-reasoner"]), None)["hard_status"], "FAIL")

    def test_lifecycle_requires_serial_completion(self):
        case = self.case(routing={"all_of": ["qa-runner", "deep-reasoner"], "ordered_roles": ["qa-runner", "deep-reasoner"]}, require_serial_completion=True, require_same_identity=True)
        trace = self.trace(["qa-runner", "deep-reasoner"])
        self.assertEqual(M.grade(case, {}, {}, trace, None)["hard_status"], "PASS")
        trace["child_write_capable_attempts"] = 1
        self.assertEqual(M.grade(case, {}, {}, trace, None)["hard_status"], "FAIL")
        trace["child_write_capable_attempts"] = 0
        trace["native_agents"][0]["completed_at"] = 99
        self.assertEqual(M.grade(case, {}, {}, trace, None)["hard_status"], "FAIL")
        trace["native_agents"][0]["outcome"] = "aborted"
        self.assertEqual(M.grade(case, {}, {}, trace, None)["hard_status"], "UNKNOWN")

    def test_identity_missing_mismatch_and_match(self):
        case = self.case(routing={"ordered_roles": ["qa-runner", "deep-reasoner"]}, require_same_identity=True)
        trace = self.trace(["qa-runner", "deep-reasoner"])
        del trace["runner_identity"]
        self.assertEqual(M.grade(case, {}, {}, trace, None)["hard_status"], "UNKNOWN")
        trace = self.trace(["qa-runner", "deep-reasoner"])
        trace["runner_identity"]["after"]["head"] = "c" * 40
        self.assertEqual(M.grade(case, {}, {}, trace, None)["hard_status"], "FAIL")
        trace = self.trace(["qa-runner", "deep-reasoner"])
        self.assertEqual(M.grade(case, {}, {}, trace, None)["hard_status"], "PASS")

    def test_trace_evidence_lifecycle_and_child_role_parse(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "child.jsonl"
            source.write_text("\n".join([
                '{"type":"session_meta","timestamp":"2026-08-05T00:00:00Z","payload":{"id":"child","source":{"subagent":{"thread_spawn":{"agent_role":"qa-runner"}}}}}',
                '{"type":"turn_context","payload":{"model":"m","effort":"e","sandbox_policy":"s"}}',
                '{"type":"response_item","payload":{"type":"function_call","name":"exec","id":"head","arguments":{"cmd":"git rev-parse HEAD"}}}',
                '{"type":"response_item","payload":{"type":"function_call_output","call_id":"head","output":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}}',
                '{"type":"response_item","payload":{"type":"function_call","name":"exec","id":"diff","arguments":{"cmd":"git diff --binary | shasum -a 256"}}}',
                '{"type":"response_item","payload":{"type":"function_call_output","call_id":"diff","output":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"}}',
                '{"type":"turn.completed","timestamp":"2026-08-05T00:00:01Z"}'
            ]) + "\n")
            output = Path(directory) / "out"
            output.mkdir()
            paths, _ = write_session_evidence([source], output)
            trace = M.normalize_trace(paths)
            self.assertEqual(trace["native_agents"][0]["role"], "qa-runner")
            self.assertEqual(trace["native_agents"][0]["completed_at"], "2026-08-05T00:00:01Z")
            self.assertEqual(trace["native_agents"][0]["outcome"], "completed")
            self.assertEqual(trace["child_write_capable_attempts"], 2)

    def test_real_0146_exec_shape_survives_allowlist(self):
        source = Path(__file__).parent / "fixtures" / "real-0146-exec-child.jsonl"
        with tempfile.TemporaryDirectory() as directory:
            paths, secrets = write_session_evidence([source], Path(directory))
            trace = M.normalize_trace(paths)
            self.assertEqual(secrets, [])
            self.assertIn("git diff --check", paths[0].read_text())
            self.assertEqual(trace["native_agents"][0]["outcome"], "completed")
            self.assertEqual(trace["child_write_capable_attempts"], 1)

    def test_invalid_or_unknown_tool_evidence_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "session.jsonl"
            source.write_text('not-json\n{"type":"response_item","payload":{"type":"function_call","name":"future_tool","id":"x"}}\n')
            output = Path(directory) / "out"
            output.mkdir()
            paths, _ = write_session_evidence([source], output)
            trace = M.normalize_trace(paths)
            self.assertEqual({item["reason"] for item in trace["unknown"]}, {"invalid-json", "unknown-tool"})

    def test_undeclared_role_is_routing_evidence_not_schema_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            child = Path(directory) / "child.jsonl"
            child.write_text("\n".join([
                '{"type":"session_meta","payload":{"source":{"subagent":{"thread_spawn":{"agent_role":"general-purpose"}}}}}',
                '{"type":"turn_context","payload":{"model":"m","effort":"e","sandbox_policy":"s"}}',
            ]) + "\n")
            parent = Path(directory) / "parent.jsonl"
            parent.write_text("\n".join([
                '{"type":"session_meta","payload":{"id":"parent"}}',
                '{"type":"turn_context","payload":{"model":"m","effort":"e","sandbox_policy":"s"}}',
            ]) + "\n")
            events = Path(directory) / "events.jsonl"
            events.write_text('{"type":"turn.completed","usage":{}}\n')
            output = Path(directory) / "out"
            output.mkdir()
            paths, _ = write_session_evidence([parent, child], output)
            trace = M.normalize_trace(paths, events)
            self.assertEqual([item["role"] for item in trace["undeclared"]], ["general-purpose"])
            self.assertNotIn("unknown-agent-role", {item["reason"] for item in trace["unknown"]})
            self.assertEqual(trace["native_agents"][0]["role"], "general-purpose")
            case = {"id": "x", "kind": "policy", "expected": {"hard_gate": True, "routing": {"all_of": ["qa-runner"], "ordered_roles": ["qa-runner"]}, "runtime": [{"role": "qa-runner"}]}}
            graded = M.grade(case, {}, {}, trace, None)
            self.assertEqual(graded["hard_status"], "UNKNOWN")  # expected role runtime never observed
            self.assertEqual(graded["behavioral_status"], "FAIL")  # routing evidence mismatch

    def test_extra_named_role_is_routing_failure(self):
        case = self.case(routing={"all_of": ["deep-reasoner"], "ordered_roles": ["deep-reasoner"]})
        graded = M.grade(case, {}, {}, self.trace(["deep-reasoner", "fast-worker"]), None)
        self.assertEqual(graded["behavioral_status"], "FAIL")
        self.assertEqual(graded["reason"], "unexpected role")

    def test_evidence_anomalies_do_not_erase_routing(self):
        case = self.case(routing={"all_of": ["qa-runner"]})
        trace = self.trace(["qa-runner"])
        trace["unknown"] = [{"reason": "unknown-tool"}]
        graded = M.grade(case, {}, {}, trace, None)
        self.assertEqual(graded["hard_status"], "UNKNOWN")
        self.assertEqual(graded["behavioral_status"], "PASS")
        self.assertEqual(graded["reason"], "evidence anomalies")
        self.assertEqual(graded["evidence_anomalies"], ["unknown-tool"])
        protected = self.case(protected_paths=["USER.md"])
        failed = M.grade(protected, {}, {"USER.md": "x"}, trace, None)
        self.assertEqual(failed["hard_status"], "FAIL")
        self.assertEqual(failed["reason"], "write contract mismatch")

    def test_unknown_cli_event_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            events, _ = write_events_evidence('{"type":"future.event"}\n', output)
            trace = M.normalize_trace([], events)
            self.assertIn("unknown-event-type", {item["reason"] for item in trace["unknown"]})

    def summary(self, statuses, *, dry=False, drift=False):
        results = []
        for status in statuses:
            results.append({"case": "policy-x", "kind": "policy", "case_digest": "case", "grade": {"hard_gate": True, "hard_status": status, "behavioral_status": status}})
        return {"runner_sha256": "runner", "manifest_sha256": "manifest", "config_digest": "config", "suite": "full", "model": "m", "cli_adapter": "x", "dry_run": dry, "source_drift": drift, "results": results}

    def test_compare_mixed_hard_baseline_is_inconclusive_not_regression(self):
        report = M.compare_summaries(self.summary(["PASS", "UNKNOWN"]), self.summary(["FAIL", "FAIL"]), M.wilson, .2)
        self.assertEqual(report["status"], "INCONCLUSIVE")
        self.assertEqual(report["cases"][0]["hard_comparison"], "INCONCLUSIVE")

    def test_compare_preserves_repetitions_and_wilson_rule(self):
        baseline, candidate = self.summary(["FAIL"] * 10), self.summary(["PASS"] * 10)
        report = M.compare_summaries(baseline, candidate, M.wilson, .2)
        case = report["cases"][0]
        self.assertEqual(case["baseline"]["n"], 10)
        self.assertEqual(case["candidate"]["n"], 10)
        self.assertEqual(case["behavioral"], "IMPROVED")

    def test_compare_excludes_infra_and_skip(self):
        report = M.compare_summaries(self.summary(["PASS", "INFRA_ERROR", "SKIP"]), self.summary(["FAIL", "INFRA_ERROR", "SKIP"]), M.wilson, .2)
        self.assertEqual(report["cases"][0]["baseline"]["n"], 1)
        self.assertEqual(report["cases"][0]["candidate"]["n"], 1)

    def test_candidate_infra_error_is_inconclusive_not_regression(self):
        report = M.compare_summaries(self.summary(["PASS"]), self.summary(["INFRA_ERROR"]), M.wilson, .2)
        self.assertEqual(report["confounders"], [])
        self.assertEqual(report["status"], "INCONCLUSIVE")
        self.assertEqual(report["cases"][0]["hard_comparison"], "INCONCLUSIVE")

    def test_candidate_fail_with_infra_is_still_regression(self):
        report = M.compare_summaries(self.summary(["PASS"]), self.summary(["FAIL", "INFRA_ERROR"]), M.wilson, .2)
        self.assertEqual(report["status"], "REGRESSION")

    def test_compare_refuses_dry_or_drift_as_confounded(self):
        self.assertIn("dry_run", M.compare_summaries(self.summary(["PASS"], dry=True), self.summary(["PASS"]), M.wilson, .2)["confounders"])
        self.assertIn("source_drift", M.compare_summaries(self.summary(["PASS"], drift=True), self.summary(["PASS"]), M.wilson, .2)["confounders"])
        baseline, candidate = self.summary(["PASS"]), self.summary(["PASS"])
        baseline["candidate_hashes"], candidate["candidate_hashes"] = {"a": "1"}, {"a": "2"}
        self.assertNotIn("source_drift", M.compare_summaries(baseline, candidate, M.wilson, .2)["confounders"])

    def test_evidence_root_detects_tamper(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            (output / "grade.json").write_text('{"ok":true}\n')
            summary = self.summary(["PASS"])
            M.write_summary_attestation(output, summary)
            root = M.write_evidence_index(output)
            summary["evidence_root"] = root
            self.assertTrue(M.verify_run(output, summary))
            summary["results"][0]["grade"]["hard_status"] = "FAIL"
            self.assertFalse(M.verify_run(output, summary))
            summary["results"][0]["grade"]["hard_status"] = "PASS"
            (output / "grade.json").write_text('{"ok":false}\n')
            self.assertFalse(M.verify_run(output, summary))

    def test_promote_only_requires_hard_status_on_gated_cases(self):
        soft = self.summary(["UNKNOWN"])
        soft["results"][0]["grade"] = {"hard_gate": False, "hard_status": "UNKNOWN", "behavioral_status": "PASS"}
        self.assertNotIn("hard_failure", M.promotion_failures(soft))
        hard = self.summary(["UNKNOWN"])
        self.assertIn("hard_failure", M.promotion_failures(hard))

    def test_usage_totals_sum_tokens_and_latency(self):
        rows = [
            {"tokens": {"input_tokens": 10, "cache_read_input_tokens": 20, "output_tokens": 3}, "latency_seconds": 1.5},
            {"tokens": {"input_tokens": 5}, "latency_seconds": 0.5},
        ]
        totals = M.usage_totals(rows)
        self.assertEqual(totals["input_tokens"], 15)
        self.assertEqual(totals["cache_read_input_tokens"], 20)
        self.assertEqual(totals["output_tokens"], 3)
        self.assertEqual(totals["billed_tokens"], 35)
        self.assertEqual(totals["latency_seconds"], 2.0)

    def test_promote_refuses_dry_run(self):
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory) / "run"; run.mkdir()
            (run / "grade.json").write_text("{}")
            root = M.write_evidence_index(run)
            M.dump(run / "summary.json", {**self.summary(["SKIP"], dry=True), "evidence_root": root})
            self.assertEqual(M.promote(Namespace(run=str(run), name="test-never")), 2)
        self.assertEqual(M.promote(Namespace(run="missing", name="../escape")), 2)

    def test_factcheck_keeps_policy_observation_separate_from_explicit(self):
        summary = self.summary(["UNKNOWN"])
        summary["results"].append({"case": "plumbing-explicit-qa", "kind": "plumbing", "actual_child_runtime": [], "grade": {"hard_status": "PASS", "behavioral_status": "NOT_APPLICABLE"}})
        facts = M.factcheck(summary)
        self.assertEqual(facts["claims"][0]["outcome"], "doc_only")
        self.assertIn("explicit_subagent_support", facts["observations"])

    def test_factcheck_wires_guidance_claim_to_policy_routing(self):
        def policy_row(case, status):
            return {"case": case, "kind": "policy", "actual_child_runtime": [], "grade": {"hard_status": "PASS" if status == "PASS" else "FAIL", "behavioral_status": status}}
        summary = self.summary(["PASS"])
        summary["results"] = [policy_row("policy-architecture", "PASS")]
        facts = M.factcheck(summary)
        guidance = next(claim for claim in facts["claims"] if claim["id"] == "subagents-guidance-trigger")
        self.assertEqual(guidance["outcome"], "confirmed")
        summary["results"] = [policy_row("policy-architecture", "FAIL")]
        facts = M.factcheck(summary)
        guidance = next(claim for claim in facts["claims"] if claim["id"] == "subagents-guidance-trigger")
        self.assertEqual(guidance["outcome"], "conflict")
        # A PASS on a none_of case never confirms guidance-triggered delegation.
        summary["results"] = [policy_row("policy-typo-direct", "PASS")]
        facts = M.factcheck(summary)
        guidance = next(claim for claim in facts["claims"] if claim["id"] == "subagents-guidance-trigger")
        self.assertEqual(guidance["outcome"], "doc_only")

    def test_infra_diagnostic_is_categorized_and_redacted(self):
        diagnostic = M.infra_diagnostic(1, '{"type":"error","message":"rate limit for /Users/alice/project"}', "")
        self.assertEqual(diagnostic["category"], "rate_limit")
        self.assertNotIn("excerpt", diagnostic)

    def test_rule_files_stay_in_sync_between_claude_and_codex(self):
        claude = (M.REPO / "CLAUDE.md").read_text()
        codex_agents = (M.REPO / "codex" / "AGENTS.md").read_text()
        synonyms = (r"\bDispatch\b", "Spawn"), ("dispatch a configured role", "spawn a named custom agent")
        normalized_claude = claude
        normalized_codex = codex_agents
        for pattern, replacement in synonyms:
            normalized_claude = re.sub(pattern, replacement, normalized_claude)
            normalized_codex = re.sub(pattern, replacement, normalized_codex)
        self.assertEqual(normalized_claude, normalized_codex, "CLAUDE.md and codex/AGENTS.md drifted; re-sync both files")

    def test_declared_runtime_reads_toml_and_rejects_missing_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            snap = Path(directory)
            (snap / "AGENTS.md").write_text("rules\n")
            agents = snap / "agents"
            agents.mkdir()
            (agents / "deep-reasoner.toml").write_text('name = "deep-reasoner"\nmodel = "gpt-x"\nmodel_reasoning_effort = "high"\nsandbox_mode = "read-only"\n')
            declared = CodexAdapter().declared_runtime(snap)
            self.assertEqual(declared["deep-reasoner"], {"model": "gpt-x", "effort": "high", "sandbox_type": "read-only"})
            (agents / "bad.toml").write_text('name = "bad"\nmodel = "gpt-x"\n')
            with self.assertRaises(RuntimeError):
                CodexAdapter().declared_runtime(snap)

    def test_resolve_runtime_fills_values_from_declared(self):
        declared = {"qa-runner": {"model": "gpt-x", "effort": "low", "sandbox_type": "workspace-write"}}
        resolved = M.resolve_runtime({"runtime": [{"role": "qa-runner"}]}, declared)
        self.assertEqual(resolved["runtime"][0], {"role": "qa-runner", "model": "gpt-x", "effort": "low", "sandbox_type": "workspace-write"})
        bare = {}
        self.assertIs(M.resolve_runtime(bare, declared), bare)

    def test_validator_rejects_inline_runtime_values_in_v4(self):
        manifest = json.loads(json.dumps(M.load(M.ROOT / "manifest.json")))
        manifest["cases"][1]["expected"]["runtime"][0]["model"] = "gpt-5.6-sol"
        self.assertIn("bad runtime: plumbing-explicit-deep", M.validate_manifest(manifest))

    def test_rev_list_runner_check_detects_new_commit(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            git = "git"
            M.fixture(work, "direct", git)
            adapter = CodexAdapter()
            adapter.info = {"tools": {"git": git, "python3": "python3"}}
            expected = {"runner_commands": [{"command": "git rev-list --count HEAD", "exit_code": 0}]}
            checks = M._runner_checks(work, expected, adapter)
            self.assertEqual(checks[0]["exit_code"], 0)
            subprocess.run([git, "-c", "user.name=eval", "-c", "user.email=eval@example.invalid", "commit", "-qm", "extra", "--allow-empty"], cwd=work, check=True)
            checks = M._runner_checks(work, expected, adapter)
            self.assertEqual(checks[0]["exit_code"], 1)

    # -- Grok adapter ----------------------------------------------------

    def test_grok_declared_runtime_reads_frontmatter(self):
        with tempfile.TemporaryDirectory() as directory:
            snap = Path(directory)
            (snap / "AGENTS.md").write_text("rules\n")
            agents = snap / "agents"
            agents.mkdir()
            (agents / "deep-reasoner.md").write_text('---\nname: deep-reasoner\nmodel: grok-4.5\neffort: high\nprompt_mode: full\npermission_mode: plan\nagents_md: true\n---\ninstructions\n')
            declared = GrokAdapter().declared_runtime(snap)
            self.assertEqual(declared["deep-reasoner"], {"model": "grok-4.5", "effort": "high", "sandbox_type": "read-only"})
            (agents / "bad.md").write_text('---\nname: bad\nmodel: grok-4.5\n---\n')
            with self.assertRaises(RuntimeError):
                GrokAdapter().declared_runtime(snap)

    def test_grok_stream_evidence_maps_end_and_writes(self):
        adapter = GrokAdapter()
        with tempfile.TemporaryDirectory() as directory:
            path, secrets = adapter.stream_evidence('{"type":"tool_call","toolName":"search_replace","rawInput":{}}\n{"type":"tool_call","toolName":"Bash","rawInput":{}}\n{"type":"usage","usage":{}}\n{"type":"end","sessionId":"s-1","usage":{"input_tokens":5}}\n{"type":"future.event"}\n', Path(directory))
            trace = M.normalize_trace([], path)
            self.assertEqual(adapter.session_id, "s-1")
            # search_replace is a definite edit; bash alone is not a file change.
            self.assertEqual(trace["candidate_write_events"], 1)
            self.assertEqual(trace["tokens"]["input_tokens"], 5)
            self.assertNotIn("exec-turn.completed", trace["health"]["missing"])
            self.assertIn("unknown-event-type", {item["reason"] for item in trace["unknown"]})
            self.assertEqual(secrets, [])

    def test_grok_session_evidence_maps_spawn_role_and_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            work = root / "work"
            work.mkdir()
            fake_home = root / "fake-home"
            encoded = urllib.parse.quote(str(work.resolve()), safe="")
            parent_dir = fake_home / ".grok" / "sessions" / encoded / "parent-111"
            child_dir = fake_home / ".grok" / "sessions" / encoded / "child-222"
            parent_dir.mkdir(parents=True)
            child_dir.mkdir(parents=True)
            (parent_dir / "chat_history.jsonl").write_text("\n".join([
                '{"type":"user","content":"Spawn fast-worker to append a line to NOTES.md."}',
                '{"type":"assistant","content":"","model_id":"grok-4.5-build","reasoning_effort":"high","tool_calls":[{"id":"c1","name":"spawn_subagent","arguments":"{\\"subagent_type\\":\\"fast-worker\\",\\"capability_mode\\":\\"read-write\\"}"}]}',
                '{"type":"assistant","content":"","model_id":"grok-4.5-build","reasoning_effort":"high","tool_calls":[{"id":"c2","name":"get_command_or_subagent_output","arguments":"{\\"task_ids\\":[\\"child-222\\"]}"}]}',
                '{"type":"tool_result","tool_call_id":"c2","content":"appended one line"}',
            ]) + "\n")
            (parent_dir / "updates.jsonl").write_text('{"timestamp": 1000}\n{"timestamp": 2000}\n')
            (parent_dir / "prompt_context.json").write_text(json.dumps({"agents_md_files": [{"file_name": "AGENTS.md", "file_path": str(work) + "/AGENTS.md", "content": "marker-content"}]}))
            (child_dir / "chat_history.jsonl").write_text("\n".join([
                '{"type":"user","content":"Append a line to NOTES.md."}',
                '{"type":"assistant","content":"","model_id":"grok-4.5-build","reasoning_effort":"medium","tool_calls":[{"id":"x1","name":"search_replace","arguments":"{\\"file_path\\":\\"NOTES.md\\"}"}]}',
            ]) + "\n")
            (child_dir / "updates.jsonl").write_text('{"timestamp": 1500}\n{"timestamp": 1800}\n')
            snap = root / "snap"
            snap.mkdir()
            (snap / "AGENTS.md").write_text("marker-content")
            events = root / "events.jsonl"
            events.write_text('{"type":"turn.completed","usage":{}}\n')
            with mock.patch("pathlib.Path.home", return_value=fake_home):
                adapter = GrokAdapter()
                adapter.session_id = "parent-111"
                adapter.snapshot_path = str(snap)
                paths, secrets = adapter.session_evidence(work, root / "out")
            trace = M.normalize_trace(paths, events)
            self.assertEqual(secrets, [])
            self.assertEqual(trace["unknown"], [])
            self.assertTrue(trace["health"]["ok"])
            agent = trace["native_agents"][0]
            self.assertEqual(agent["role"], "fast-worker")
            self.assertEqual(agent["runtime"], {"model": "grok-4.5-build", "effort": "medium", "sandbox_policy": {"type": "workspace-write"}})
            self.assertEqual(agent["outcome"], "completed")
            self.assertEqual(trace["child_write_capable_attempts"], 1)

    def test_grok_write_attempts_require_edit_capable_capability(self):
        def run_case(capability, tool):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                work = root / "work"
                work.mkdir()
                fake_home = root / "fake-home"
                sessions = fake_home / ".grok" / "sessions" / urllib.parse.quote(str(work.resolve()), safe="")
                parent_dir = sessions / "parent-111"
                child_dir = sessions / "child-222"
                parent_dir.mkdir(parents=True)
                child_dir.mkdir(parents=True)
                (parent_dir / "chat_history.jsonl").write_text("\n".join([
                    '{"type":"assistant","content":"","model_id":"grok-4.5-build","reasoning_effort":"high","tool_calls":[{"id":"c1","name":"spawn_subagent","arguments":"{\\"subagent_type\\":\\"qa-runner\\",\\"capability_mode\\":\\"%s\\"}"}]}' % capability,
                    '{"type":"assistant","content":"","model_id":"grok-4.5-build","reasoning_effort":"high","tool_calls":[{"id":"c2","name":"get_command_or_subagent_output","arguments":"{\\"task_ids\\":[\\"child-222\\"]}"}]}',
                    '{"type":"tool_result","tool_call_id":"c2","content":"done"}',
                ]) + "\n")
                (parent_dir / "updates.jsonl").write_text('{"timestamp": 1000}\n{"timestamp": 2000}\n')
                (parent_dir / "prompt_context.json").write_text(json.dumps({"agents_md_files": [{"file_name": "Agents.md", "file_path": str(work) + "/Agents.md", "content": "x"}]}))
                (child_dir / "chat_history.jsonl").write_text('{"type":"assistant","content":"","model_id":"grok-4.5-build","reasoning_effort":"low","tool_calls":[{"id":"x1","name":"%s","arguments":"{}"}]}\n' % tool)
                (child_dir / "updates.jsonl").write_text('{"timestamp": 1500}\n{"timestamp": 1800}\n')
                snap = root / "snap"
                snap.mkdir()
                (snap / "AGENTS.md").write_text("x")
                with mock.patch("pathlib.Path.home", return_value=fake_home):
                    adapter = GrokAdapter()
                    adapter.session_id = "parent-111"
                    adapter.snapshot_path = str(snap)
                    paths, _ = adapter.session_evidence(work, root / "out")
                return M.normalize_trace(paths)
        # execute capability blocks edits: bash is not a write attempt
        trace = run_case("execute", "Bash")
        self.assertEqual(trace["child_write_capable_attempts"], 0)
        # read-write capability permits edits: search_replace is a write attempt
        trace = run_case("read-write", "search_replace")
        self.assertEqual(trace["child_write_capable_attempts"], 1)

    # -- Claude adapter --------------------------------------------------

    def test_claude_declared_runtime_reads_frontmatter(self):
        with tempfile.TemporaryDirectory() as directory:
            snap = Path(directory)
            (snap / "CLAUDE.md").write_text("rules\n")
            agents = snap / "agents"
            agents.mkdir()
            (agents / "fast-worker.md").write_text('---\nname: fast-worker\ndescription: mechanical work\nmodel: sonnet\nprompt_mode: full\npermission_mode: default\n---\ninstructions\n')
            declared = ClaudeAdapter().declared_runtime(snap)
            self.assertEqual(declared["fast-worker"], {"model": "sonnet", "effort": "unobserved", "sandbox_type": "workspace-write"})
            (agents / "deep-reasoner.md").write_text('---\nname: deep-reasoner\nmodel: opus\npermission_mode: plan\n---\n')
            declared = ClaudeAdapter().declared_runtime(snap)
            self.assertEqual(declared["deep-reasoner"]["sandbox_type"], "read-only")

    def test_claude_stream_evidence_maps_result_and_edits(self):
        adapter = ClaudeAdapter()
        with tempfile.TemporaryDirectory() as directory:
            path, _ = adapter.stream_evidence('\n'.join([
                '{"type":"system","subtype":"hook_started","hook_name":"SessionStart"}',
                '{"type":"assistant","message":{"model":"m","content":[{"type":"tool_use","name":"Read","input":{}}]}}',
                '{"type":"assistant","message":{"model":"m","content":[{"type":"tool_use","name":"Edit","input":{"file_path":"README.md"}}]}}',
                '{"type":"result","session_id":"s-1","usage":{"input_tokens":5}}',
            ]) + '\n', Path(directory))
            trace = M.normalize_trace([], path)
            self.assertEqual(adapter.session_id, "s-1")
            self.assertEqual(trace["candidate_write_events"], 1)  # Edit only, not Read
            self.assertEqual(trace["tokens"]["input_tokens"], 5)
            self.assertEqual(trace["unknown"], [])

    def test_claude_session_evidence_links_agent_spawns(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            work = root / "work"
            work.mkdir()
            fake_home = root / "fake-home"
            encoded = str(work.resolve()).replace("/", "-").replace("_", "-")
            proj = fake_home / ".claude" / "projects" / encoded
            proj.mkdir(parents=True)
            parent = proj / "parent-111.jsonl"
            container = proj / "child-222"
            (container / "subagents").mkdir(parents=True)
            parent.write_text("\n".join([
                '{"type":"user","message":{"role":"user","content":[{"type":"text","text":"Spawn fast-worker"}]},"timestamp":"2026-08-06T00:00:00Z"}',
                '{"type":"assistant","message":{"model":"grok","content":[{"type":"tool_use","name":"Agent","id":"call_1","input":{"subagent_type":"fast-worker","prompt":"append a line"}}]},"timestamp":"2026-08-06T00:00:01Z"}',
                '{"type":"system","content":"<CLAUDE.md> candidate-content </CLAUDE.md>"}',
            ]) + "\n")
            (container / "subagents" / "agent-a0cbd4b08aa0982c2.jsonl").write_text("\n".join([
                '{"type":"user","message":{"role":"user","content":[]},"timestamp":"2026-08-06T00:00:02Z"}',
                '{"type":"assistant","message":{"model":"deepseek-v4-flash","content":[{"type":"tool_use","name":"Edit","input":{"file_path":"NOTES.md"}}]},"timestamp":"2026-08-06T00:00:03Z"}',
            ]) + "\n")
            (container / "subagents" / "agent-a0cbd4b08aa0982c2.meta.json").write_text('{"agentType":"fast-worker","toolUseId":"call_1","spawnDepth":1}')
            snap = root / "snap"
            snap.mkdir()
            (snap / "CLAUDE.md").write_text("candidate-content")
            events = root / "events.jsonl"
            events.write_text('{"type":"turn.completed","usage":{}}\n')
            with mock.patch("pathlib.Path.home", return_value=fake_home):
                adapter = ClaudeAdapter()
                adapter.session_id = "parent-111"
                adapter.snapshot_path = str(snap)
                paths, _ = adapter.session_evidence(work, root / "out")
            trace = M.normalize_trace(paths, events)
            self.assertEqual(trace["unknown"], [])
            self.assertTrue(trace["health"]["ok"])
            agent = trace["native_agents"][0]
            self.assertEqual(agent["role"], "fast-worker")
            self.assertEqual(agent["runtime"]["model"], "deepseek-v4-flash")
            self.assertEqual(trace["child_write_capable_attempts"], 1)
            self.assertEqual(agent["outcome"], "completed")

    def test_claude_monitor_tool_is_non_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            work = root / "work"
            work.mkdir()
            fake_home = root / "fake-home"
            encoded = str(work.resolve()).replace("/", "-").replace("_", "-")
            proj = fake_home / ".claude" / "projects" / encoded
            proj.mkdir(parents=True)
            parent = proj / "parent-111.jsonl"
            container = proj / "child-222"
            (container / "subagents").mkdir(parents=True)
            parent.write_text("\n".join([
                '{"type":"user","message":{"role":"user","content":[]},"timestamp":"2026-08-07T00:00:00Z"}',
                '{"type":"assistant","message":{"model":"m","content":[{"type":"tool_use","name":"Agent","id":"call_1","input":{"subagent_type":"qa-runner"}}]},"timestamp":"2026-08-07T00:00:01Z"}',
            ]) + "\n")
            (container / "subagents" / "agent-m1.jsonl").write_text("\n".join([
                '{"type":"user","message":{"role":"user","content":[]},"timestamp":"2026-08-07T00:00:02Z"}',
                '{"type":"assistant","message":{"model":"m","content":[{"type":"tool_use","name":"Monitor","input":{}},{"type":"tool_use","name":"Read","input":{}}]},"timestamp":"2026-08-07T00:00:03Z"}',
            ]) + "\n")
            (container / "subagents" / "agent-m1.meta.json").write_text('{"agentType":"qa-runner","toolUseId":"call_1"}')
            events = root / "events.jsonl"
            events.write_text('{"type":"turn.completed","usage":{}}\n')
            with mock.patch("pathlib.Path.home", return_value=fake_home):
                adapter = ClaudeAdapter()
                adapter.session_id = "parent-111"
                paths, _ = adapter.session_evidence(work, root / "out")
            trace = M.normalize_trace(paths, events)
            self.assertEqual(trace["unknown"], [])

    def test_claude_project_path_encoding_maps_underscores(self):
        from lib.adapters.claude import _encode_project_path
        work = Path("/var/folders/ab/T/shiki-eval-fixture-yuwu2q_c")
        encoded = str(work.resolve()).replace("/", "-").replace("_", "-")
        self.assertEqual(_encode_project_path(work), encoded)
        self.assertNotIn("_", _encode_project_path(work))

    def test_claude_runtime_contract_is_observation_only(self):
        adapter = ClaudeAdapter()
        declared = {"model": "sonnet", "effort": "unobserved", "sandbox_type": "workspace-write"}
        # Claude Code does not enforce declared agent models; runtime is never asserted.
        self.assertTrue(adapter.runtime_contract(declared, {"model": "deepseek-v4-flash", "effort": None, "sandbox_policy": {"type": None}}))

    def test_grok_runtime_contract_family_and_capability_ceiling(self):
        adapter = GrokAdapter()
        declared = {"model": "grok-4.5", "effort": "medium", "sandbox_type": "workspace-write"}
        build = {"model": "grok-4.5-build", "effort": "medium", "sandbox_policy": {"type": "workspace-write"}}
        self.assertTrue(adapter.runtime_contract(declared, build))
        tighter = {**build, "sandbox_policy": {"type": "read-only"}}
        self.assertTrue(adapter.runtime_contract(declared, tighter))
        broader = {"model": "grok-4.5-build", "effort": "medium", "sandbox_policy": {"type": "read-write"}}
        self.assertTrue(adapter.runtime_contract({"model": "grok-4.5", "effort": "medium", "sandbox_type": "read-only"}, broader) is False)
        wrong_family = {"model": "grok-3", "effort": "medium", "sandbox_policy": {"type": "workspace-write"}}
        self.assertFalse(adapter.runtime_contract(declared, wrong_family))
        wrong_effort = {**build, "effort": "high"}
        self.assertFalse(adapter.runtime_contract(declared, wrong_effort))

    def test_grok_injection_check_fails_closed_on_shadowed_agents_md(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            work = root / "work"
            work.mkdir()
            fake_home = root / "fake-home"
            parent_dir = fake_home / ".grok" / "sessions" / urllib.parse.quote(str(work.resolve()), safe="") / "parent-111"
            parent_dir.mkdir(parents=True)
            (parent_dir / "chat_history.jsonl").write_text('{"type":"assistant","content":"","model_id":"grok-4.5-build","reasoning_effort":"high","tool_calls":[]}\n')
            (parent_dir / "prompt_context.json").write_text(json.dumps({"agents_md_files": [{"file_name": "Agents.md", "file_path": "/somewhere/else/Agents.md", "content": "shadowed"}]}))
            snap = root / "snap"
            snap.mkdir()
            (snap / "AGENTS.md").write_text("candidate-content")
            with mock.patch("pathlib.Path.home", return_value=fake_home):
                adapter = GrokAdapter()
                adapter.session_id = "parent-111"
                adapter.snapshot_path = str(snap)
                paths, _ = adapter.session_evidence(work, root / "out")
            trace = M.normalize_trace(paths)
            self.assertIn("candidate-not-injected", {item["reason"] for item in trace["unknown"]})

    def test_injected_paths_are_excluded_from_fixture_hashing(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            (work / "AGENTS.md").write_text("rules")
            agents = work / ".grok" / "agents"
            agents.mkdir(parents=True)
            (agents / "fast-worker.md").write_text("profile")
            injected = set(GrokAdapter().injected_paths(work))
            self.assertEqual(injected, {"AGENTS.md", ".grok/agents/fast-worker.md"})
            hashes = {key: value for key, value in M.files(work).items() if key not in injected}
            self.assertNotIn("AGENTS.md", hashes)
            self.assertNotIn(".grok/agents/fast-worker.md", hashes)

    def test_grok_injection_check_matches_case_variants_and_ignores_non_session_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            work = root / "work"
            work.mkdir()
            fake_home = root / "fake-home"
            sessions = fake_home / ".grok" / "sessions" / urllib.parse.quote(str(work.resolve()), safe="")
            parent_dir = sessions / "parent-111"
            parent_dir.mkdir(parents=True)
            (parent_dir / "chat_history.jsonl").write_text('{"type":"assistant","content":"","model_id":"grok-4.5-build","reasoning_effort":"high","tool_calls":[]}\n')
            (parent_dir / "prompt_context.json").write_text(json.dumps({"agents_md_files": [{"file_name": "Agents.md", "file_path": str(work) + "/Agents.md", "content": "candidate-content"}]}))
            (sessions / "prompt_history.jsonl").write_text('{"prompt":"x"}\n')
            snap = root / "snap"
            snap.mkdir()
            (snap / "AGENTS.md").write_text("candidate-content")
            with mock.patch("pathlib.Path.home", return_value=fake_home):
                adapter = GrokAdapter()
                adapter.session_id = "parent-111"
                adapter.snapshot_path = str(snap)
                paths, _ = adapter.session_evidence(work, root / "out")
            trace = M.normalize_trace(paths)
            self.assertEqual(trace["unknown"], [])
            self.assertEqual([p.name for p in paths], ["00-parent-111.jsonl"])


if __name__ == "__main__": unittest.main()
