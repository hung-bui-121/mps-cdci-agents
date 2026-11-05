# -*- coding: utf-8 -*-
"""Unit tests for the pure functions of plugins/mps-git-flow/skills/mps-git-flow/scripts/mps.py (no network, no git)."""

import importlib.util
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

SCRIPT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "plugins", "mps-git-flow", "skills",
                           "mps-git-flow", "scripts", "mps.py")


def _load_module():
    spec = importlib.util.spec_from_file_location("mps", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mps = _load_module()
BRANCHES = {"dev": "develop", "beta_prefix": "release/", "prod": "master"}


class ParseEnvTests(unittest.TestCase):
    def test_basic_comments_quotes_and_export(self):
        text = "\n".join([
            "# comment",
            "",
            "MPS_JIRA_URL=https://jira.example",
            "MPS_JIRA_PAT=abc123",
            "MPS_JIRA_PROJECT_KEY=          # inline comment only",
            "MPS_BRANCH_DEV = 'develop'",
            'MPS_CA_BUNDLE="C:/certs/my ca.pem"',
            "export MPS_BRANCH_PROD=main # trailing comment",
            "not a valid line",
        ])
        env = mps.parse_env(text)
        self.assertEqual(env["MPS_JIRA_URL"], "https://jira.example")
        self.assertEqual(env["MPS_JIRA_PAT"], "abc123")
        self.assertEqual(env["MPS_JIRA_PROJECT_KEY"], "")
        self.assertEqual(env["MPS_BRANCH_DEV"], "develop")
        self.assertEqual(env["MPS_CA_BUNDLE"], "C:/certs/my ca.pem")
        self.assertEqual(env["MPS_BRANCH_PROD"], "main")
        self.assertEqual(len(env), 6)

    def test_crlf_and_last_duplicate_wins(self):
        env = mps.parse_env("A=1\r\nA=2\r\n")
        self.assertEqual(env, {"A": "2"})

    def test_update_env_text_replaces_and_dedupes(self):
        text = "A=1\nMPS_JIRA_PROJECT_KEY=\nB=2\nMPS_JIRA_PROJECT_KEY=OLD\n"
        updated = mps.update_env_text(text, "MPS_JIRA_PROJECT_KEY", "MPS")
        self.assertEqual(updated, "A=1\nMPS_JIRA_PROJECT_KEY=MPS\nB=2\n")
        self.assertEqual(mps.parse_env(updated)["MPS_JIRA_PROJECT_KEY"], "MPS")

    def test_update_env_text_appends_and_keeps_crlf(self):
        updated = mps.update_env_text("A=1\r\n", "MPS_GITLAB_PROJECT", "group/sub/proj")
        self.assertEqual(updated, "A=1\r\nMPS_GITLAB_PROJECT=group/sub/proj\r\n")

    def test_update_env_text_quotes_values_with_spaces(self):
        updated = mps.update_env_text("", "MPS_CA_BUNDLE", "C:/my certs/ca.pem")
        self.assertEqual(mps.parse_env(updated)["MPS_CA_BUNDLE"], "C:/my certs/ca.pem")


class SlugifyTests(unittest.TestCase):
    def test_vietnamese_fold(self):
        self.assertEqual(mps.slugify("Sửa lỗi đăng nhập Đặc biệt!"), "sua-loi-dang-nhap-dac-biet")

    def test_collapse_and_trim(self):
        self.assertEqual(mps.slugify("  --Hello,   World__2.0--  "), "hello-world-2-0")

    def test_length_cap_cuts_at_dash_boundary(self):
        title = "Thêm màn hình quản lý người dùng cho trang quản trị hệ thống nội bộ"
        slug = mps.slugify(title)
        self.assertLessEqual(len(slug), mps.SLUG_MAX_LEN)
        self.assertFalse(slug.endswith("-"))
        self.assertTrue(("them-man-hinh-quan-ly-nguoi-dung-cho-trang-quan-tri-he-thong").startswith(slug))
        self.assertEqual(slug, "them-man-hinh-quan-ly-nguoi-dung-cho-trang-quan")

    def test_single_long_word_is_hard_cut(self):
        self.assertEqual(len(mps.slugify("a" * 80)), mps.SLUG_MAX_LEN)

    def test_symbols_only_gives_empty_slug(self):
        self.assertEqual(mps.slugify("!!! ???"), "")


class BuildNamesTests(unittest.TestCase):
    def test_story(self):
        names = mps.build_names("mps-123", "story", "Thêm màn hình Đăng nhập")
        self.assertEqual(names["branch"], "feature/MPS-123-them-man-hinh-dang-nhap")
        self.assertEqual(names["commit_message"], "feat: MPS-123 Thêm màn hình Đăng nhập")
        self.assertEqual(names["mr_title"], "MPS-123 Thêm màn hình Đăng nhập")
        self.assertEqual(names["mr_description"], "Close MPS-123")

    def test_bug(self):
        names = mps.build_names("MPS-7", "bug", "Sửa lỗi  crash khi mở app")
        self.assertEqual(names["branch"], "bugfix/MPS-7-sua-loi-crash-khi-mo-app")
        self.assertEqual(names["commit_message"], "fix: MPS-7 Sửa lỗi crash khi mở app")
        self.assertEqual(names["mr_title"], "MPS-7 Sửa lỗi crash khi mở app")
        self.assertEqual(names["mr_description"], "Close MPS-7")

    def test_hotfix(self):
        names = mps.build_names("MPS-9", "hotfix", "Lỗi thanh toán")
        self.assertEqual(names["branch"], "hotfix/MPS-9-loi-thanh-toan")
        self.assertEqual(names["commit_message"], "fix: MPS-9 Lỗi thanh toán")
        self.assertEqual(names["mr_title"], "MPS-9 Lỗi thanh toán")
        self.assertEqual(names["mr_description"], "Close MPS-9")

    def test_invalid_key_and_type(self):
        with self.assertRaises(mps.MpsError) as ctx:
            mps.build_names("123", "story", "x")
        self.assertEqual(ctx.exception.code, "invalid_ticket_key")
        with self.assertRaises(mps.MpsError) as ctx:
            mps.build_names("MPS-1", "task", "x")
        self.assertEqual(ctx.exception.code, "invalid_type")
        with self.assertRaises(mps.MpsError) as ctx:
            mps.build_names("MPS-1", "bug", "   ")
        self.assertEqual(ctx.exception.code, "empty_title")


class PhaseRuleTests(unittest.TestCase):
    def test_dev_story_and_bug(self):
        story = mps.plan_phase("dev", "story", BRANCHES)
        self.assertEqual((story["kind"], story["base_branch"], story["target_branch"]),
                         ("feature", "develop", "develop"))
        self.assertEqual(story["naming_type"], "story")
        bug = mps.plan_phase("dev", "bug", BRANCHES)
        self.assertEqual(bug["kind"], "bugfix")
        self.assertEqual(bug["naming_type"], "bug")

    def test_beta_story_rejected(self):
        with self.assertRaises(mps.MpsError) as ctx:
            mps.plan_phase("beta", "story", BRANCHES)
        self.assertEqual(ctx.exception.code, "phase_rule_violation")

    def test_beta_bug_needs_release_lookup(self):
        plan = mps.plan_phase("beta", "bug", BRANCHES)
        self.assertEqual(plan["kind"], "bugfix")
        self.assertTrue(plan["needs_release_lookup"])
        self.assertIsNone(plan["base_branch"])

    def test_production_story_rejected(self):
        with self.assertRaises(mps.MpsError) as ctx:
            mps.plan_phase("production", "story", BRANCHES)
        self.assertEqual(ctx.exception.code, "phase_rule_violation")

    def test_production_bug_is_hotfix_with_warning(self):
        plan = mps.plan_phase("production", "bug", BRANCHES, access_level=40)
        self.assertEqual((plan["kind"], plan["base_branch"], plan["target_branch"]), ("hotfix", "master", "master"))
        self.assertEqual(plan["naming_type"], "hotfix")
        self.assertTrue(plan["requires_explicit_confirmation"])
        self.assertIn("CẢNH BÁO", plan["warning"])
        self.assertEqual(plan["access_level_name"], "Maintainer")

    def test_production_warning_stronger_below_maintainer(self):
        developer = mps.plan_phase("production", "bug", BRANCHES, access_level=30)["warning"]
        maintainer = mps.plan_phase("production", "bug", BRANCHES, access_level=40)["warning"]
        self.assertGreater(len(developer), len(maintainer))
        self.assertIn("Developer", developer)

    def test_protected_branches(self):
        self.assertTrue(mps.is_protected_branch("develop", BRANCHES))
        self.assertTrue(mps.is_protected_branch("master", BRANCHES))
        self.assertTrue(mps.is_protected_branch("release/1.2.0", BRANCHES))
        self.assertFalse(mps.is_protected_branch("feature/MPS-1-x", BRANCHES))


class ReleaseSortTests(unittest.TestCase):
    def test_version_order(self):
        branches = [
            {"name": "release/1.9.2", "committed_date": "2024-05-01T10:00:00.000+07:00"},
            {"name": "release/1.10.0", "committed_date": "2024-01-01T10:00:00.000+07:00"},
            {"name": "release/1.2", "committed_date": "2024-06-01T10:00:00Z"},
            {"name": "feature/x", "committed_date": "2025-01-01T10:00:00Z"},
        ]
        names = [b["name"] for b in mps.sort_release_branches(branches, "release/")]
        self.assertEqual(names, ["release/1.10.0", "release/1.9.2", "release/1.2"])
        self.assertEqual(mps.release_sort_method(branches, "release/"), "version")

    def test_fallback_to_committed_date(self):
        branches = [
            {"name": "release/1.10.0", "committed_date": "2024-01-01T10:00:00.000+07:00"},
            {"name": "release/next", "committed_date": "2024-03-01T03:00:00.000+00:00"},
            {"name": "release/1.9.2", "committed_date": "2024-02-01T10:00:00.123456789+07:00"},
        ]
        names = [b["name"] for b in mps.sort_release_branches(branches, "release/")]
        self.assertEqual(names, ["release/next", "release/1.9.2", "release/1.10.0"])
        self.assertEqual(mps.release_sort_method(branches, "release/"), "committed_date")

    def test_timezone_aware_date_compare(self):
        branches = [
            {"name": "release/a", "committed_date": "2024-01-01T08:00:00+07:00"},
            {"name": "release/b", "committed_date": "2024-01-01T02:00:00Z"},
        ]
        names = [b["name"] for b in mps.sort_release_branches(branches, "release/")]
        self.assertEqual(names, ["release/b", "release/a"])

    def test_empty(self):
        self.assertEqual(mps.sort_release_branches([{"name": "develop"}], "release/"), [])


class ScanSecretsTests(unittest.TestCase):
    DIFF = "\n".join([
        "diff --git a/app/config.py b/app/config.py",
        "index 111..222 100644",
        "--- a/app/config.py",
        "+++ b/app/config.py",
        "@@ -10,2 +10,4 @@ def x():",
        " unchanged = 1",
        "-password = 'old-removed-value'",
        "+GITLAB = 'glpat-abcdefghij1234567890'",
        "+db_password = 'hunter22secret'",
        "+name = 'ok'",
        "diff --git a/keys/id_rsa b/keys/id_rsa",
        "new file mode 100644",
        "--- /dev/null",
        "+++ b/keys/id_rsa",
        "@@ -0,0 +1,2 @@",
        "+-----BEGIN OPENSSH PRIVATE KEY-----",
        "++++ not a header, an added line starting with ++",
        "diff --git a/.env.example b/.env.example",
        "--- a/.env.example",
        "+++ b/.env.example",
        "@@ -1 +1 @@",
        "-MPS_JIRA_PAT=",
        "+MPS_JIRA_PAT=realtoken123",
    ])

    def test_findings(self):
        findings = mps.scan_secrets(self.DIFF)
        summary = sorted((f["file"], f["line"], f["rule"]) for f in findings)
        self.assertEqual(summary, [
            (".env.example", 1, "mps_pat"),
            ("app/config.py", 11, "gitlab_token"),
            ("app/config.py", 12, "generic_secret"),
            ("keys/id_rsa", 1, "private_key"),
        ])
        generic = [f for f in findings if f["rule"] == "generic_secret"][0]
        self.assertTrue(generic["confirmable"])

    def test_removed_lines_and_empty_values_ignored(self):
        diff = "+++ b/a.txt\n@@ -1,2 +1,1 @@\n-token = 'abcdefgh'\n+MPS_GITLAB_PAT=\n"
        self.assertEqual(mps.scan_secrets(diff), [])

    def test_findings_never_contain_secret_text(self):
        for finding in mps.scan_secrets(self.DIFF):
            self.assertNotIn("glpat-abcdefghij", str(finding))

    def test_scan_text(self):
        findings = mps.scan_text("new.cfg", "a=1\npassword: superSecret!\n")
        self.assertEqual([(f["line"], f["rule"]) for f in findings], [(2, "generic_secret")])


class GitParsingTests(unittest.TestCase):
    def test_parse_porcelain_z(self):
        output = "M  staged.txt\0 M unstaged.txt\0MM both.txt\0R  new.txt\0old.txt\0?? untracked.txt\0UU conflict.txt\0"
        status = mps.parse_porcelain_z(output)
        self.assertEqual(status["staged"], ["staged.txt", "both.txt", "old.txt", "new.txt"])
        self.assertEqual(status["unstaged"], ["unstaged.txt", "both.txt"])
        self.assertEqual(status["untracked"], ["untracked.txt"])
        self.assertEqual(status["unmerged"], ["conflict.txt"])
        self.assertEqual(status["renames"], {"new.txt": "old.txt"})

    def test_targets_and_renames(self):
        targets = [mps.normalize_target_path(p) for p in ["./cfg/", "src\\a.py", "."]]
        self.assertEqual(targets, ["cfg", "src/a.py", "."])
        self.assertTrue(mps.path_in_targets("cfg/.env.local", ["cfg"]))
        self.assertFalse(mps.path_in_targets("cfgx/a", ["cfg"]))
        self.assertTrue(mps.path_in_targets("anything", ["."]))
        self.assertEqual(mps.expand_rename_sources(["new.txt"], {"new.txt": "old.txt"}), ["new.txt", "old.txt"])
        self.assertEqual(mps.expand_rename_sources(["old.txt"], {"new.txt": "old.txt"}), ["old.txt", "new.txt"])
        self.assertEqual(mps.expand_rename_sources(["x"], {"new.txt": "old.txt"}), ["x"])

    def test_parse_check_attr_z(self):
        output = "big.bin\0filter\0lfs\0a.txt\0filter\0unspecified\0"
        self.assertEqual(mps.parse_check_attr_z(output), {"big.bin": "lfs", "a.txt": "unspecified"})

    def test_find_foreign_commits(self):
        log = "aaaa\tfix: MPS-2 Sửa lỗi\nbbbb\tfeat: MPS-5 unreleased\ncccc\tfix: mps-2 lower case\ndddd\tfix: MPS-20 other\n"
        foreign = mps.find_foreign_commits(log, "MPS-2")
        self.assertEqual([c["sha"] for c in foreign], ["bbbb", "dddd"])

    def test_is_env_file(self):
        self.assertTrue(mps.is_env_file(".env"))
        self.assertTrue(mps.is_env_file("server/.env.production"))
        self.assertFalse(mps.is_env_file(".env.example"))
        self.assertFalse(mps.is_env_file("docs/environment.md"))

    def test_parse_remote_project_path(self):
        gitlab = "https://git-gst.mto.zing.vn"
        self.assertEqual(mps.parse_remote_project_path("https://git-gst.mto.zing.vn/grp/sub/proj.git", gitlab),
                         "grp/sub/proj")
        self.assertEqual(mps.parse_remote_project_path("https://user:pw@GIT-GST.mto.zing.vn:8443/grp/proj", gitlab),
                         "grp/proj")
        self.assertEqual(mps.parse_remote_project_path("git@git-gst.mto.zing.vn:grp/proj.git", gitlab), "grp/proj")
        self.assertEqual(mps.parse_remote_project_path("ssh://git@git-gst.mto.zing.vn:2222/grp/proj.git", gitlab),
                         "grp/proj")
        self.assertIsNone(mps.parse_remote_project_path("https://github.com/grp/proj.git", gitlab))

    def test_sanitize_remote_url(self):
        self.assertEqual(mps.sanitize_remote_url("https://oauth2:glpat-x@host/g/p.git"), "https://host/g/p.git")
        self.assertEqual(mps.sanitize_remote_url("git@host:g/p.git"), "git@host:g/p.git")

    def test_classify_git_network_error(self):
        rejected = " ! [rejected]        x -> x (fetch first)\nerror: failed to push some refs"
        self.assertEqual(mps.classify_git_network_error(rejected, "push")[0], "push_rejected")
        auth = "remote: HTTP Basic: Access denied\nfatal: Authentication failed for 'https://h/g/p.git/'"
        self.assertEqual(mps.classify_git_network_error(auth, "push")[0], "auth_failed")
        self.assertTrue(mps.is_git_auth_error(auth))
        dns = "fatal: unable to access 'https://h/': Could not resolve host: h"
        self.assertEqual(mps.classify_git_network_error(dns, "fetch")[0], "network_unreachable")

    def test_apply_budget(self):
        self.assertEqual(mps.apply_budget(["abc", "defg", "hi"], 5), [("abc", False), ("de", True), ("", True)])


class JiraHelperTests(unittest.TestCase):
    def test_normalize_issue_type(self):
        self.assertEqual(mps.normalize_issue_type("Story"), "story")
        self.assertEqual(mps.normalize_issue_type("BUG"), "bug")
        self.assertIsNone(mps.normalize_issue_type("Task"))

    def test_pick_transition(self):
        transitions = [{"id": "11", "name": "In Progress", "to": {"name": "In Progress"}},
                       {"id": "21", "name": "Resolve Issue", "to": {"name": "Resolved"}},
                       {"id": "31", "name": "Finish", "to": {"name": "Closed"}}]
        self.assertEqual(mps.pick_transition(transitions, "resolved")["id"], "21")
        self.assertEqual(mps.pick_transition(transitions, "done")["id"], "31")
        self.assertIsNone(mps.pick_transition(transitions[:1], "done"))
        vietnamese = [{"id": "5", "name": "Hoàn thành", "to": {"name": "Xong"}}]
        self.assertEqual(mps.pick_transition(vietnamese, "done")["id"], "5")

    def test_resolved_falls_back_to_done_transition(self):
        no_resolve = [{"id": "11", "name": "In Progress", "to": {"name": "In Progress"}},
                      {"id": "41", "name": "Done", "to": {"name": "Done"}}]
        self.assertEqual(mps.pick_transition(no_resolve, "resolved")["id"], "41")
        self.assertTrue(mps.is_in_target_state("Closed", "done", "resolved"))
        self.assertTrue(mps.is_in_target_state("Done", "done", "resolved"))

    def test_is_in_target_state(self):
        self.assertTrue(mps.is_in_target_state("Done", "done", "done"))
        self.assertFalse(mps.is_in_target_state("Resolved", "indeterminate", "done"))
        self.assertTrue(mps.is_in_target_state("Resolved", "indeterminate", "resolved"))
        self.assertFalse(mps.is_in_target_state("In Progress", "indeterminate", "resolved"))

    def test_missing_required_fields_and_field_args(self):
        meta = mps.normalize_field_meta_list([
            {"fieldId": "summary", "name": "Summary", "required": True},
            {"fieldId": "reporter", "name": "Reporter", "required": True},
            {"fieldId": "priority", "name": "Priority", "required": True, "hasDefaultValue": True},
            {"fieldId": "customfield_1", "name": "Team", "required": True, "schema": {"type": "option"},
             "allowedValues": [{"id": "100", "value": "Client"}, {"id": "101", "value": "Server"}]},
            {"fieldId": "components", "name": "Component/s", "required": True,
             "schema": {"type": "array", "items": "component"}, "allowedValues": [{"id": "7", "name": "Core"}]},
        ])
        missing = mps.find_missing_required_fields(meta, {})
        self.assertEqual([m["id"] for m in missing], ["components", "customfield_1"])
        self.assertEqual(missing[1]["allowed_values"][1], {"id": "101", "value": "Server"})
        provided = mps.parse_field_args(["team=server", "customfield_1=Client", "Component/s=core"], meta)
        self.assertEqual(provided, {"customfield_1": {"id": "100"}, "components": [{"id": "7"}]})
        self.assertEqual(mps.find_missing_required_fields(meta, provided), [])
        with self.assertRaises(mps.MpsError) as ctx:
            mps.parse_field_args(["Team=Nope"], meta)
        self.assertEqual(ctx.exception.code, "invalid_field_value")
        with self.assertRaises(mps.MpsError) as ctx:
            mps.parse_field_args(["Unknown=1"], meta)
        self.assertEqual(ctx.exception.code, "unknown_field")

    def test_choose_resolution(self):
        self.assertEqual(mps.choose_resolution([{"id": "1", "name": "Done"}, {"id": "2", "name": "Fixed"}])["id"], "2")
        self.assertEqual(mps.choose_resolution([{"id": "1", "name": "Done"}])["id"], "1")
        self.assertIsNone(mps.choose_resolution([{"id": "3", "name": "Won't Fix"}, {"id": "4", "name": "Duplicate"}]))
        self.assertIsNone(mps.choose_resolution([]))


class RedactTests(unittest.TestCase):
    def test_registered_secret_is_masked(self):
        mps.register_secret("supersecretvalue")
        self.assertEqual(mps.redact('{"x": "supersecretvalue"}'), '{"x": "****"}')


class JiraProjectChoiceTests(unittest.TestCase):
    """R1: the ticket's project may differ from the GitLab project; --project overrides the configured default."""

    def test_override_wins_and_is_normalized(self):
        self.assertEqual(mps.choose_create_project("art", "MPS"), "ART")
        self.assertEqual(mps.choose_create_project(None, "mps"), "MPS")
        self.assertEqual(mps.choose_create_project("", "MPS"), "MPS")

    def test_invalid_key_rejected(self):
        with self.assertRaises(mps.MpsError) as ctx:
            mps.choose_create_project("ART-12", "MPS")
        self.assertEqual(ctx.exception.code, "invalid_project_key")

    def test_ticket_keys_from_any_board_are_accepted(self):
        self.assertEqual(mps.normalize_issue_key("art-12"), "ART-12")
        names = mps.build_names("ART-12", "story", "Vẽ lại icon")
        self.assertEqual(names["branch"], "feature/ART-12-ve-lai-icon")
        self.assertEqual(names["mr_description"], "Close ART-12")
        self.assertTrue(mps.mentions_key("feat: ART-12 Vẽ lại icon", "ART-12"))


class ReviewClassifyTests(unittest.TestCase):
    """R2: the reviewer's FILES block drives the default commit set; out-of-scope is excluded by default."""

    REPLY = "\n".join([
        "### Kết quả review phạm vi - MPS-1",
        "| a | b | c | d |",
        "VERDICT: FAIL",
        "",
        "FILES:",
        "in_scope: src/login.cs",
        "out_of_scope: ProjectSettings/ProjectSettings.asset",
        "mixed: src/menu.cs   (rename of unrelated variable)",
        "- concern: `src/debug.cs`",
        "in_scope: src/login.cs",
        "in_scope: not/in/bundle.cs",
        "",
        "BUNDLE: `AB12CD`",
        "VERDICT: FAIL",
    ])

    def test_parse_review_files(self):
        entries, verdict, bundle_id = mps.parse_review_files(self.REPLY)
        self.assertEqual((verdict, bundle_id), ("FAIL", "ab12cd"))
        self.assertEqual(entries[0], ("in_scope", "src/login.cs"))
        self.assertEqual(entries[3], ("concern", "src/debug.cs"))
        self.assertEqual(len(entries), 6)

    def test_classify_review(self):
        entries, _, _ = mps.parse_review_files(self.REPLY)
        uncommitted = ["src/login.cs", "ProjectSettings/ProjectSettings.asset", "src/menu.cs", "src/debug.cs",
                       "package-lock.json"]
        result = mps.classify_review(entries, uncommitted, ["src/old.cs"], "PASS")
        self.assertEqual(result["commit_files"], ["src/login.cs", "src/debug.cs"])
        self.assertEqual(result["concern_files"], ["src/debug.cs"])
        self.assertEqual(result["needs_decision"], [])
        self.assertEqual(result["excluded_files"], ["ProjectSettings/ProjectSettings.asset"])
        self.assertEqual(result["mixed_files"], ["src/menu.cs"])
        self.assertEqual(result["unclassified_files"], ["package-lock.json"])
        self.assertEqual(result["duplicate_paths"], ["src/login.cs"])
        self.assertEqual(result["unknown_paths"], ["not/in/bundle.cs"])
        self.assertFalse(result["complete"])

    def test_complete_classification(self):
        entries, verdict, _ = mps.parse_review_files("FILES:\nin_scope: a.cs\nout_of_scope: b.meta\nVERDICT: PASS\n")
        result = mps.classify_review(entries, ["a.cs", "b.meta"], [], verdict)
        self.assertTrue(result["complete"])
        self.assertEqual(verdict, "PASS")
        self.assertEqual(result["commit_files"], ["a.cs"])

    def test_fail_verdict_moves_concerns_to_needs_decision(self):
        entries, verdict, _ = mps.parse_review_files("FILES:\nin_scope: a.cs\nconcern: d.cs\nVERDICT: FAIL\n")
        result = mps.classify_review(entries, ["a.cs", "d.cs"], [], verdict)
        self.assertEqual((result["commit_files"], result["needs_decision"]), (["a.cs"], ["d.cs"]))
        self.assertTrue(result["complete"])
        no_verdict = mps.classify_review(entries, ["a.cs", "d.cs"], [], None)
        self.assertEqual(no_verdict["commit_files"], ["a.cs"])
        self.assertFalse(no_verdict["complete"])

    def test_no_files_block(self):
        self.assertEqual(mps.parse_review_files("in_scope: a.cs\nVERDICT: PASS"), ([], "PASS", None))

    def test_stale_bundle_reason(self):
        bundle = {"bundle_id": "ab12", "base": "develop", "branch": "feature/X-1-a", "head": "h1",
                  "blobs": {"a.txt": "b1"}}
        ok_args = ("develop", "feature/X-1-a", "h1", {"a.txt": "b1"})
        self.assertIsNone(mps.stale_bundle_reason(bundle, "ab12", *ok_args))
        self.assertEqual(mps.stale_bundle_reason(None, "ab12", *ok_args), "no_bundle")
        self.assertEqual(mps.stale_bundle_reason(bundle, None, *ok_args), "reply_without_bundle_id")
        self.assertEqual(mps.stale_bundle_reason(bundle, "ffff", *ok_args), "reply_for_other_bundle")
        self.assertEqual(mps.stale_bundle_reason(bundle, "ab12", "release/1.0", "feature/X-1-a", "h1",
                                                 {"a.txt": "b1"}), "base_changed")
        self.assertEqual(mps.stale_bundle_reason(bundle, "ab12", "develop", "feature/X-1-a", "h2",
                                                 {"a.txt": "b1"}), "branch_or_commit_changed")
        self.assertEqual(mps.stale_bundle_reason(bundle, "ab12", "develop", "feature/X-1-a", "h1",
                                                 {"a.txt": "b2"}), "files_changed")
        self.assertEqual(mps.stale_bundle_reason(bundle, "ab12", "develop", "feature/X-1-a", "h1",
                                                 {"a.txt": "b1", "new.txt": "b3"}), "files_changed")

    def test_inferred_target_verdict(self):
        self.assertEqual(mps.inferred_target_verdict("develop", ["develop"], "develop"), "ok")
        self.assertEqual(mps.inferred_target_verdict("release/1.0", ["develop"], "develop"), "mismatch")
        self.assertEqual(mps.inferred_target_verdict("develop", ["develop", "master"], "develop"), "ok")
        self.assertEqual(mps.inferred_target_verdict("master", ["develop", "master"], "develop"), "ambiguous")
        self.assertEqual(mps.inferred_target_verdict("release/1.0", ["release/1.0"], "develop"), "ok")


class BranchContextTests(unittest.TestCase):
    """R3: the MR goes back into exactly the branch the work was based on."""

    def test_detect_roles(self):
        ctx = mps.detect_branch_context
        self.assertEqual(ctx("develop", BRANCHES, None)["detected_phase"], "dev")
        beta = ctx("release/1.1", BRANCHES, None)
        self.assertEqual((beta["current_branch_role"], beta["detected_phase"], beta["detected_base"]),
                         ("beta", "beta", "release/1.1"))
        self.assertEqual(ctx("master", BRANCHES, None)["detected_phase"], "production")
        ticket = ctx("bugfix/MPS-2-x", BRANCHES, "release/1.0")
        self.assertEqual((ticket["current_branch_role"], ticket["detected_phase"], ticket["detected_base"]),
                         ("ticket", "beta", "release/1.0"))
        self.assertEqual(ctx("bugfix/MPS-2-x", BRANCHES, None)["current_branch_role"], "other")
        self.assertEqual(ctx("my-work", BRANCHES, None)["current_branch_role"], "other")
        self.assertEqual(ctx(None, BRANCHES, None)["current_branch_role"], "detached")

    def assert_error(self, code, func, *args):
        with self.assertRaises(mps.MpsError) as ctx:
            func(*args)
        self.assertEqual(ctx.exception.code, code)

    def test_reconcile_phase_dirty_tree_pins(self):
        on_develop = mps.detect_branch_context("develop", BRANCHES, None)
        self.assertEqual(mps.reconcile_phase(on_develop, None, True), ("dev", "detected", True))
        self.assertEqual(mps.reconcile_phase(on_develop, "dev", True), ("dev", "detected", True))
        self.assert_error("phase_conflict", mps.reconcile_phase, on_develop, "beta", True)

    def test_reconcile_phase_clean_tree_follows_request(self):
        on_develop = mps.detect_branch_context("develop", BRANCHES, None)
        self.assertEqual(mps.reconcile_phase(on_develop, "beta", False), ("beta", "requested_clean_tree", False))
        self.assert_error("phase_required", mps.reconcile_phase, on_develop, None, False)
        on_master = mps.detect_branch_context("master", BRANCHES, None)
        self.assert_error("phase_required", mps.reconcile_phase, on_master, None, False)
        other = mps.detect_branch_context("my-work", BRANCHES, None)
        self.assertEqual(mps.reconcile_phase(other, "beta", True), ("beta", "requested", False))
        self.assert_error("phase_required", mps.reconcile_phase, other, None, True)

    def test_own_ticket_branch_pins_even_when_clean(self):
        own = mps.detect_branch_context("bugfix/MPS-2-x", BRANCHES, "release/1.0", key="MPS-2")
        self.assertEqual(own["current_branch_role"], "ticket")
        self.assertEqual(mps.reconcile_phase(own, None, False), ("beta", "detected", True))
        self.assert_error("phase_conflict", mps.reconcile_phase, own, "dev", False)
        foreign = mps.detect_branch_context("bugfix/MPS-2-x", BRANCHES, "release/1.0", key="MPS-3")
        self.assertEqual((foreign["current_branch_role"], foreign["branch_ticket_key"]), ("other", "MPS-2"))
        self.assertEqual(mps.reconcile_phase(foreign, "dev", True), ("dev", "requested", False))

    def test_recorded_base_gone(self):
        gone = mps.detect_branch_context("bugfix/MPS-2-x", BRANCHES, "release/0.9", key="MPS-2",
                                         recorded_base_exists=False)
        self.assertEqual((gone["current_branch_role"], gone["recorded_base_gone"]), ("other", True))
        self.assertEqual(mps.reconcile_phase(gone, "beta", False)[0], "beta")
        self.assert_error("recorded_base_gone", mps.reconcile_phase, gone, "beta", True)

    def test_detached_head(self):
        self.assertEqual(mps.unique_protected_branch(["HEAD", "develop", "feature/x"], BRANCHES), "develop")
        self.assertIsNone(mps.unique_protected_branch(["develop", "master"], BRANCHES))
        on_develop = mps.detect_branch_context(None, BRANCHES, None, detached_at="develop")
        self.assertEqual((on_develop["current_branch_role"], on_develop["detached"]), ("dev", True))
        unknown = mps.detect_branch_context(None, BRANCHES, None)
        self.assertEqual(unknown["current_branch_role"], "detached")
        self.assert_error("detached_head", mps.reconcile_phase, unknown, "dev", True)
        self.assertEqual(mps.reconcile_phase(unknown, "dev", False)[0], "dev")

    def test_release_branch_checks(self):
        branches = [{"name": "release/1.1", "committed_date": "2024-01-01T00:00:00Z"},
                    {"name": "release/1.2", "committed_date": "2024-02-01T00:00:00Z"}]
        names = [b["name"] for b in mps.sort_release_branches(branches, "release/")]
        warning = mps.check_release_branch("release/1.1", names)
        self.assertEqual((warning["code"], warning["latest"]), ("not_latest_release", "release/1.2"))
        self.assertIsNone(mps.check_release_branch("release/1.2", names))
        self.assert_error("release_branch_gone", mps.check_release_branch, "release/1.0", names)
        self.assert_error("release_branch_gone", mps.check_release_branch, "release/1.1", [])

    def test_closest_bases(self):
        self.assertEqual(mps.closest_bases({"develop": 1, "release/1.0": 2, "master": 1}), ["develop", "master"])
        self.assertEqual(mps.closest_bases({}), [])
        self.assertEqual(mps.ticket_key_of_branch("bugfix/art-12-x"), "ART-12")
        self.assertIsNone(mps.ticket_key_of_branch("develop"))


class GeneratedFilesTests(unittest.TestCase):
    """Tool-generated files (Unity) never make the current branch 'hold work' for phase pinning."""

    DEFAULTS = mps.DEFAULT_GENERATED_PATTERNS

    def test_default_patterns(self):
        generated = ["ProjectSettings/ProjectSettings.asset", "ProjectSettings/Sub/Deep.asset",
                     "Packages/packages-lock.json", "UserSettings/EditorUserSettings.asset", "Game.csproj",
                     "Assembly-CSharp.csproj", "Game.sln", "Library/ScriptAssemblies/x.dll"]
        for path in generated:
            self.assertTrue(mps.is_generated_path(path, self.DEFAULTS), path)
        real = ["Assets/Scripts/Login.cs", "Packages/manifest.json", "Docs/ProjectSettings.md",
                "ProjectSettingsBackup/x.asset", "src/Game.csproj.bak", "LibraryCode/a.cs"]
        for path in real:
            self.assertFalse(mps.is_generated_path(path, self.DEFAULTS), path)

    def test_windows_paths_and_nested_unity_project(self):
        self.assertTrue(mps.is_generated_path("ProjectSettings\\TagManager.asset", self.DEFAULTS))
        self.assertTrue(mps.is_generated_path("Client/Game/ProjectSettings/TagManager.asset", self.DEFAULTS))
        self.assertTrue(mps.is_generated_path("Client\\Game\\Packages\\packages-lock.json", self.DEFAULTS))
        self.assertTrue(mps.is_generated_path("Client/Game/Game.csproj", self.DEFAULTS))
        self.assertFalse(mps.is_generated_path("Client/Game/Assets/a.cs", self.DEFAULTS))

    def test_extra_patterns_from_env(self):
        patterns = mps.generated_patterns(" Assets/Gen/** , *.lock ,Assets\\AddressableAssetsData\\*.json,")
        self.assertEqual(patterns[:len(self.DEFAULTS)], list(self.DEFAULTS))
        self.assertEqual(patterns[len(self.DEFAULTS):],
                         ["Assets/Gen/**", "*.lock", "Assets/AddressableAssetsData/*.json"])
        self.assertTrue(mps.is_generated_path("Assets/Gen/a/b.cs", patterns))
        self.assertTrue(mps.is_generated_path("yarn.lock", patterns))
        self.assertTrue(mps.is_generated_path("Assets/AddressableAssetsData/settings.json", patterns))
        self.assertFalse(mps.is_generated_path("Assets/AddressableAssetsData/Sub/settings.json", patterns))
        self.assertEqual(mps.generated_patterns(None), list(self.DEFAULTS))
        self.assertIn("MPS_GENERATED_PATTERNS", mps.KNOWN_KEYS)


GIT = shutil.which("git")
LARGE_FILE_BYTES = mps.MAX_FILE_BYTES + 1024


class FakeService(object):
    """Stands in for ServiceClient: routes (method, path) to canned JSON and records every call."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def request(self, method, path, params=None, body=None, allow_statuses=()):
        self.calls.append((method, path, body))
        if (method, path) not in self.routes:
            raise AssertionError("unexpected call %s %s" % (method, path))
        status, data = self.routes[(method, path)]
        if status >= 400 and status not in allow_statuses:
            raise mps.MpsError("http_error", "fake %d" % status, status=status)
        return mps.HttpResponse(status, data, {})

    def get(self, path, params=None):
        return self.request("GET", path, params=params).data


def fake_gitlab(release_branches):
    return FakeService({
        ("GET", "/projects/grp%2Fproj"): (200, {"id": 1, "path_with_namespace": "grp/proj", "web_url": "u"}),
        ("GET", "/projects/1/repository/branches"): (200, [{"name": n, "commit": {"committed_date": None}}
                                                           for n in release_branches]),
    })


def fake_jira():
    story_fields = [{"fieldId": "summary", "name": "Summary", "required": True},
                    {"fieldId": "assignee", "name": "Assignee", "required": False}]
    routes = {
        ("GET", "/rest/api/2/myself"): (200, {"name": "hung"}),
        ("GET", "/rest/api/2/project"): (200, [{"key": "MPS", "name": "Game"}, {"key": "ART", "name": "Artist"}]),
        ("GET", "/rest/api/2/project/ART"): (200, {"key": "ART", "name": "Artist"}),
        ("GET", "/rest/api/2/project/NOPE"): (404, None),
        ("POST", "/rest/api/2/issue"): (201, {"key": "ART-1"}),
    }
    for project in ("ART", "MPS"):
        base = "/rest/api/2/issue/createmeta/%s/issuetypes" % project
        routes[("GET", base)] = (200, {"values": [{"id": "10", "name": "Story"}], "isLast": True})
        routes[("GET", base + "/10")] = (200, {"values": story_fields, "isLast": True})
    return FakeService(routes)


def _rmtree(path):
    # git marks object files read-only, which rmtree cannot delete on Windows.
    for folder, _, files in os.walk(path):
        for name in files:
            try:
                os.chmod(os.path.join(folder, name), stat.S_IWRITE | stat.S_IREAD)
            except OSError:
                pass
    shutil.rmtree(path, ignore_errors=True)


@unittest.skipIf(GIT is None, "git is not installed")
class GitFlowTests(unittest.TestCase):
    """End-to-end git behaviour against a local bare origin (offline). Calls mps.main() in-process."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mps-test-")
        self.addCleanup(_rmtree, self.tmp)
        self.addCleanup(os.chdir, os.getcwd())
        empty_config = os.path.join(self.tmp, "empty.gitconfig")
        open(empty_config, "w").close()
        env = mock.patch.dict(os.environ, {"GIT_CONFIG_GLOBAL": empty_config, "GIT_CONFIG_NOSYSTEM": "1"})
        env.start()
        self.addCleanup(env.stop)
        self.origin = os.path.join(self.tmp, "origin.git")
        self.repo = os.path.join(self.tmp, "repo")
        self.other = os.path.join(self.tmp, "other")
        self.git("init", "--bare", "-b", "develop", self.origin, cwd=self.tmp)
        self.git("clone", "-q", self.origin, self.repo, cwd=self.tmp)
        self.set_identity(self.repo)
        self.write("app.txt", "line1\nline2\n")
        self.git("add", ".")
        self.git("commit", "-q", "-m", "init")
        self.git("push", "-q", "-u", "origin", "develop")
        self.git("push", "-q", "origin", "develop:release/1.0")
        self.write("feature.txt", "unreleased\n")
        self.git("add", ".")
        self.git("commit", "-q", "-m", "feat: MPS-5 unreleased feature")
        self.git("push", "-q")
        os.chdir(self.repo)

    # -- helpers ---------------------------------------------------------

    def git(self, *args, cwd=None):
        return subprocess.run(["git"] + list(args), cwd=cwd or self.repo, check=True, capture_output=True,
                              encoding="utf-8").stdout

    def set_identity(self, path):
        self.git("config", "user.name", "Tester", cwd=path)
        self.git("config", "user.email", "tester@example.com", cwd=path)

    def write(self, path, text, root=None):
        full = os.path.join(root or self.repo, path)
        os.makedirs(os.path.dirname(full) or ".", exist_ok=True)
        with open(full, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)

    def read(self, path):
        with open(os.path.join(self.repo, path), encoding="utf-8") as handle:
            return handle.read()

    def mps(self, *argv):
        buffer = io.BytesIO()
        stream = io.TextIOWrapper(buffer, encoding="utf-8")
        with mock.patch.object(sys, "stdout", stream):
            code = mps.main(list(argv))
        stream.flush()
        result = json.loads(buffer.getvalue().decode("utf-8"))
        self.assertEqual(result["ok"], code == 0, result)
        return result

    def push_upstream(self, branch, path, text, message):
        if not os.path.isdir(self.other):
            self.git("clone", "-q", self.origin, self.other, cwd=self.tmp)
            self.set_identity(self.other)
        self.git("fetch", "-q", cwd=self.other)
        self.git("switch", "-q", "-C", branch, "origin/" + branch, cwd=self.other)
        self.write(path, text, root=self.other)
        self.git("add", ".", cwd=self.other)
        self.git("commit", "-q", "-m", message, cwd=self.other)
        self.git("push", "-q", "origin", branch, cwd=self.other)

    def prepare(self, branch, key, base="develop", *extra):
        return self.mps("git", "prepare-branch", "--base", base, "--branch", branch, "--key", key, *extra)

    def make_bundle(self, base="develop"):
        return self.mps("git", "diff-for-review", "--base=" + base, "--to-file")["bundle_id"]

    def write_reply(self, bundle_id, in_scope, out_of_scope=(), mixed=(), concern=(), verdict="PASS", name="review"):
        """A scope reviewer's reply in the required format; bundle_id/verdict None leave that line out."""
        lines = ["FILES:"]
        for category, paths in (("in_scope", in_scope), ("out_of_scope", out_of_scope), ("mixed", mixed),
                                ("concern", concern)):
            lines.extend("%s: %s" % (category, path) for path in paths)
        if bundle_id:
            lines.append("BUNDLE: " + bundle_id)
        if verdict:
            lines.append("VERDICT: " + verdict)
        reply = os.path.join(mps.mps_tmp_dir(self.repo), name + ".txt")
        with open(reply, "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
        return reply

    def classify(self, reply, base="develop"):
        return self.mps("review", "classify", "--base=" + base, "--result-file=" + reply)

    def approve(self, in_scope, base="develop", **reply_args):
        """diff-for-review, a reviewer reply for that bundle, then `review classify` (writes scope.json)."""
        bundle_id = self.make_bundle(base)
        return self.classify(self.write_reply(bundle_id, in_scope, **reply_args), base)

    def commit(self, message, *files):
        return self.mps("git", "commit", "--message=" + message, "--files", *files)

    def write_env(self, **values):
        self.write(".env", "".join("%s=%s\n" % item for item in values.items()))
        self.write(".gitignore", ".env\n")
        self.git("add", ".gitignore")
        self.git("commit", "-q", "-m", "chore: ignore env")
        self.git("push", "-q", "origin", "HEAD")

    def head(self):
        return self.git("rev-parse", "HEAD").strip()

    # -- C1 --------------------------------------------------------------

    def test_stash_conflict_blocks_rerun_commit_and_preflight(self):
        self.push_upstream("develop", "app.txt", "line1\nline2 upstream\n", "upstream edit")
        self.write("app.txt", "line1\nline2 mine\n")
        conflict = self.prepare("feature/MPS-1-x", "MPS-1")
        self.assertEqual(conflict["error"], "stash_conflict")
        self.assertIn("mps-auto", self.git("stash", "list"))
        self.assertEqual(self.prepare("feature/MPS-1-x", "MPS-1")["error"], "unmerged_files")
        before = self.head()
        self.assertEqual(self.mps("git", "commit", "--message=feat: MPS-1 x", "--files", "app.txt")["error"],
                         "unmerged_files")
        self.assertEqual(self.head(), before)
        preflight = self.mps("git", "preflight", "--base", "develop")
        self.assertIn("unmerged_files", [b["code"] for b in preflight["blockers"]])

    # -- C2 --------------------------------------------------------------

    def test_commit_never_includes_env_files_or_secrets(self):
        self.prepare("feature/MPS-1-x", "MPS-1")
        self.write("cfg/app.ini", "a=1\n")
        self.write("cfg/.env.local", "MPS_GITLAB_PAT=glpat-abcdefghijklmnop\n")
        self.write("cfg/token.py", "GITLAB = 'glpat-abcdefghijklmnop'\n")
        before = self.head()
        for files in (["cfg"], ["."], ["./"], ["cfg/typo.ini"]):
            result = self.commit("feat: MPS-1 x", *files)
            self.assertEqual(result["error"], "explicit_files_required")
            self.assertEqual(self.head(), before)
        self.assertEqual(self.commit("x", "cfg/.env.local")["error"], "env_file")
        approved = self.approve(["cfg/app.ini", "cfg/token.py"])
        self.assertEqual(approved["files_to_classify"], ["cfg/app.ini", "cfg/token.py"])  # .env never offered
        # A .env staged earlier (e.g. by an IDE) is caught too, and nothing is committed.
        self.git("add", "-f", "cfg/.env.local")
        result = self.commit("feat: MPS-1 x", "cfg/app.ini")
        self.assertEqual(result["error"], "env_file")
        self.assertEqual(result["files"], ["cfg/.env.local"])
        self.assertEqual(self.head(), before)
        self.assertEqual(self.git("diff", "--cached", "--name-only").strip(), "")
        self.assertTrue(os.path.isfile(os.path.join(self.repo, "cfg", ".env.local")))
        result = self.commit("feat: MPS-1 x", "cfg/token.py")
        self.assertEqual(result["error"], "secret_detected")
        self.assertEqual(self.head(), before)
        ok = self.commit("feat: MPS-1 x", "cfg/app.ini")
        self.assertEqual(ok["files"], ["A\tcfg/app.ini"])
        self.assertEqual(sorted(ok["left_uncommitted"]), ["cfg/.env.local", "cfg/token.py"])

    def test_push_checks_every_commit_for_env_files_and_secrets(self):
        self.prepare("feature/MPS-1-x", "MPS-1")
        self.write(".env.local", "X=1\n")
        self.git("add", "-f", ".env.local")
        self.git("commit", "-q", "-m", "feat: MPS-1 sneaky env")
        self.write("later.txt", "fine\n")
        self.git("add", "later.txt")
        self.git("commit", "-q", "-m", "feat: MPS-1 later")
        result = self.mps("git", "push", "--branch", "feature/MPS-1-x", "--base", "develop")
        self.assertEqual(result["error"], "env_file")
        self.git("rm", "-q", "--cached", ".env.local")
        self.write("key.pem", "-----BEGIN RSA PRIVATE KEY-----\n")
        self.git("add", "key.pem")
        self.git("commit", "-q", "-m", "feat: MPS-1 key")
        self.assertEqual(self.mps("git", "push", "--branch", "feature/MPS-1-x", "--base", "develop")["error"],
                         "env_file")
        self.assertEqual(self.git("ls-remote", "--heads", "origin", "feature/MPS-1-x").strip(), "")

    def test_push_refuses_secret_and_review_bundle_hides_env(self):
        self.prepare("feature/MPS-1-x", "MPS-1")
        self.write("key.pem", "-----BEGIN RSA PRIVATE KEY-----\n")
        self.git("add", "key.pem")
        self.git("commit", "-q", "-m", "feat: MPS-1 key")
        result = self.mps("git", "push", "--branch", "feature/MPS-1-x", "--base", "develop")
        self.assertEqual(result["error"], "secret_detected")
        self.assertEqual(result["findings"][0]["rule"], "private_key")
        self.write("cfg/.env.local", "SECRET_VALUE_XYZ=1\n")
        review = self.mps("git", "diff-for-review", "--base", "develop", "--to-file")
        self.assertEqual(review["hidden_files"], ["cfg/.env.local"])
        with open(review["bundle_path"], encoding="utf-8") as handle:
            bundle = handle.read()
        self.assertIn("cfg/.env.local: [content hidden]", bundle)
        self.assertNotIn("SECRET_VALUE_XYZ", bundle)

    # -- C3 --------------------------------------------------------------

    def test_beta_refuses_dev_based_branch(self):
        self.prepare("bugfix/MPS-2-x", "MPS-2")
        self.write("fix.txt", "fix\n")
        self.approve(["fix.txt"])
        self.commit("fix: MPS-2 x", "fix.txt")
        # R3: the recorded base answers first ...
        self.assertEqual(self.prepare("bugfix/MPS-2-x", "MPS-2", "release/1.0")["error"], "base_mismatch")
        # ... and without a recorded base (e.g. branch made by hand) the foreign-commit check still catches it.
        self.git("config", "--unset", "branch.bugfix/MPS-2-x.mps-base")
        result = self.prepare("bugfix/MPS-2-x", "MPS-2", "release/1.0")
        self.assertEqual(result["error"], "branch_base_mismatch")
        self.assertEqual([c["subject"] for c in result["foreign_commits"]], ["feat: MPS-5 unreleased feature"])
        self.git("switch", "-q", "develop")
        self.assertEqual(self.prepare("bugfix/MPS-2-x", "MPS-2", "release/1.0")["error"], "branch_base_mismatch")
        self.assertEqual(self.git("branch", "--show-current").strip(), "develop")
        same = self.prepare("bugfix/MPS-2-x", "MPS-2")
        self.assertEqual((same["action"], same["base_recorded"]), ("switched_existing", True))
        self.assertEqual(mps.recorded_base(self.repo, "bugfix/MPS-2-x"), "develop")

    # -- M1 --------------------------------------------------------------

    def test_local_commits_not_carried(self):
        self.git("switch", "-q", "-c", "my-work")
        self.write("work.txt", "ide commit\n")
        self.git("add", "work.txt")
        self.git("commit", "-q", "-m", "work from IDE")
        preflight = self.mps("git", "preflight", "--base", "develop", "--branch", "feature/MPS-3-y")
        warning = [w for w in preflight["warnings"] if w["code"] == "local_commits_not_carried"]
        self.assertEqual(warning[0]["count"], 1)
        refused = self.prepare("feature/MPS-3-y", "MPS-3")
        self.assertEqual(refused["error"], "local_commits_not_carried")
        self.assertEqual(self.git("branch", "--show-current").strip(), "my-work")
        created = self.prepare("feature/MPS-3-y", "MPS-3", "develop", "--leave-commits")
        self.assertEqual((created["action"], created["commits_left_behind"]), ("created_from_base", 1))
        self.assertIn("work from IDE", self.git("log", "-1", "--format=%s", "my-work"))

    # -- M2 --------------------------------------------------------------

    def test_large_file_blocker_skips_lfs(self):
        self.write(".gitattributes", "*.bin filter=lfs diff=lfs merge=lfs -text\n")
        with open(os.path.join(self.repo, "asset.bin"), "wb") as handle:
            handle.write(b"x" * LARGE_FILE_BYTES)
        with open(os.path.join(self.repo, "dump.dat"), "wb") as handle:
            handle.write(b"x" * LARGE_FILE_BYTES)
        preflight = self.mps("git", "preflight", "--base", "develop")
        large = [b for b in preflight["blockers"] if b["code"] == "large_file"][0]
        self.assertEqual([f["file"] for f in large["files"]], ["dump.dat"])

    # -- M5 --------------------------------------------------------------

    def test_failed_switch_restores_stashed_changes(self):
        self.write("app.txt", "line1\nline2 dirty\n")
        self.write("new.txt", "untracked\n")
        with self.assertRaises(mps.MpsError) as ctx:
            mps._switch_with_stash(self.repo, ["switch", "no-such-branch"])
        self.assertEqual(ctx.exception.code, "switch_failed")
        self.assertEqual(self.read("app.txt"), "line1\nline2 dirty\n")
        self.assertEqual(self.read("new.txt"), "untracked\n")
        self.assertEqual(self.git("stash", "list").strip(), "")

    # -- M6 --------------------------------------------------------------

    def test_missing_git_identity(self):
        self.git("config", "--unset", "user.name")
        self.git("config", "--unset", "user.email")
        preflight = self.mps("git", "preflight")
        self.assertIn("missing_git_identity", [b["code"] for b in preflight["blockers"]])
        self.assertEqual(self.mps("git", "set-identity", "--name=Nguyễn Văn A", "--email", "a@example.com")["scope"],
                         "local")
        preflight = self.mps("git", "preflight")
        self.assertNotIn("missing_git_identity", [b["code"] for b in preflight["blockers"]])
        self.assertEqual(self.mps("git", "set-identity", "--name", "A", "--email", "bad")["error"], "invalid_identity")

    # -- resume + rename (m6) -------------------------------------------

    def test_resume_after_push_and_rename_commit(self):
        self.prepare("feature/MPS-4-z", "MPS-4")
        self.git("mv", "app.txt", "renamed.txt")
        self.assertEqual(self.approve(["renamed.txt"])["files_to_classify"], ["renamed.txt"])
        committed = self.commit("feat: MPS-4 Đổi tên", "renamed.txt")
        self.assertEqual(committed["files"], ["R100\tapp.txt\trenamed.txt"])
        self.assertEqual(self.git("log", "-1", "--format=%s").strip(), "feat: MPS-4 Đổi tên")
        self.assertEqual(self.git("status", "--porcelain").strip(), "")
        self.mps("git", "push", "--branch", "feature/MPS-4-z", "--base", "develop")
        self.assertEqual(self.mps("git", "commit", "--message=feat: MPS-4 again", "--files", "renamed.txt")["error"],
                         "nothing_to_commit")
        self.assertEqual(self.prepare("feature/MPS-4-z", "MPS-4")["action"], "already_on_branch")
        self.assertTrue(self.mps("git", "push", "--branch", "feature/MPS-4-z", "--base", "develop")["ok"])

    # -- R2: explicit file lists, out-of-scope files stay on disk ----------

    def test_all_flag_is_gone(self):
        buffer = io.BytesIO()
        stream = io.TextIOWrapper(buffer, encoding="utf-8")
        with mock.patch.object(sys, "stdout", stream), self.assertRaises(SystemExit) as ctx:
            mps.main(["git", "commit", "--message=x", "--all"])
        stream.flush()
        self.assertEqual(ctx.exception.code, mps.EXIT_USAGE)
        self.assertEqual(json.loads(buffer.getvalue().decode("utf-8"))["error"], "usage_error")

    def test_out_of_scope_files_are_left_uncommitted(self):
        self.prepare("feature/MPS-6-login", "MPS-6")
        self.write("src/login.cs", "class Login {}\n")
        self.write("ProjectSettings/ProjectSettings.asset", "unity: regenerated\n")
        self.write("app.txt", "line1\nline2 edited by unity import\n")
        review = self.mps("git", "diff-for-review", "--base=develop", "--to-file")
        self.assertEqual(sorted(review["files_to_classify"]),
                         ["ProjectSettings/ProjectSettings.asset", "app.txt", "src/login.cs"])
        with open(review["bundle_path"], encoding="utf-8") as handle:
            text = handle.read()
        self.assertIn("## 0. Files to classify", text)
        self.assertIn("Bundle-ID: " + review["bundle_id"], text)
        reply = self.write_reply(review["bundle_id"], ["src/login.cs"],
                                 out_of_scope=["ProjectSettings/ProjectSettings.asset", "app.txt"], verdict="FAIL")
        classified = self.classify(reply)
        self.assertTrue(classified["complete"])
        self.assertEqual(classified["commit_files"], ["src/login.cs"])
        # M1: an excluded file cannot slip into the commit just by being listed.
        sneaky = self.commit("feat: MPS-6 Login", "src/login.cs", "ProjectSettings/ProjectSettings.asset")
        self.assertEqual((sneaky["error"], sneaky["files"]), ("not_in_scope", ["ProjectSettings/ProjectSettings.asset"]))
        committed = self.commit("feat: MPS-6 Login", *classified["commit_files"])
        self.assertEqual(committed["files"], ["A\tsrc/login.cs"])
        self.assertEqual(sorted(committed["left_uncommitted"]), ["ProjectSettings/ProjectSettings.asset", "app.txt"])
        self.assertIn("unity import", self.read("app.txt"))
        self.assertNotIn("mps-tmp", self.git("status", "--porcelain", "-uall"))
        self.assertFalse(os.path.exists(mps.scope_path(self.repo)))  # one review approves one commit

    # -- R3: recorded base, base_mismatch, MR guard, phase detection --------

    def test_recorded_base_and_mismatch(self):
        created = self.prepare("bugfix/MPS-7-x", "MPS-7", "release/1.0")
        self.assertEqual((created["action"], created["base_recorded"]), ("created_from_base", True))
        self.assertEqual(self.git("config", "--local", "--get", "branch.bugfix/MPS-7-x.mps-base").strip(),
                         "release/1.0")
        mismatch = self.prepare("bugfix/MPS-7-x", "MPS-7", "develop")
        self.assertEqual((mismatch["error"], mismatch["recorded_base"]), ("base_mismatch", "release/1.0"))
        self.write("fix.txt", "fix\n")
        self.approve(["fix.txt"], base="release/1.0")
        self.commit("fix: MPS-7 x", "fix.txt")
        self.assertEqual(self.mps("git", "push", "--branch=bugfix/MPS-7-x", "--base=develop")["error"], "base_mismatch")
        self.assertEqual(self.mps("git", "push", "--branch=bugfix/MPS-7-x", "--base=feature/x")["error"],
                         "invalid_base")
        self.assertEqual(self.prepare("bugfix/MPS-7-x", "MPS-7", "my-work")["error"], "invalid_base")
        preflight = self.mps("git", "preflight")
        self.assertEqual((preflight["current_branch_role"], preflight["recorded_base"], preflight["detected_phase"]),
                         ("ticket", "release/1.0", "beta"))

    def guard_error(self, *args):
        with self.assertRaises(mps.MpsError) as ctx:
            mps.ensure_mr_target(self.repo, *args)
        return ctx.exception.code

    def test_mr_guard(self):
        self.prepare("feature/MPS-8-y", "MPS-8")
        self.write("y.txt", "y\n")
        self.approve(["y.txt"])
        self.commit("feat: MPS-8 y", "y.txt")
        self.assertEqual(mps.ensure_mr_target(self.repo, "feature/MPS-8-y", "develop", "MPS-8", BRANCHES), "develop")
        self.assertEqual(self.guard_error("feature/MPS-8-y", "release/1.0", "MPS-8", BRANCHES),
                         "target_mismatch_recorded_base")
        self.assertEqual(self.guard_error("feature/MPS-8-y", "feature/x", "MPS-8", BRANCHES), "invalid_base")
        self.assertEqual(self.guard_error("feature/MPS-0-none", "develop", "MPS-8", BRANCHES), "branch_not_found")
        # m2: without a recorded base the target must be the closest protected branch ...
        self.git("config", "--unset", "branch.feature/MPS-8-y.mps-base")
        self.assertEqual(self.guard_error("feature/MPS-8-y", "release/9.9", "MPS-8", BRANCHES), "base_not_found")
        self.assertEqual(self.guard_error("feature/MPS-8-y", "release/1.0", "MPS-8", BRANCHES),
                         "target_mismatch_inferred_base")
        self.assertIsNone(mps.ensure_mr_target(self.repo, "feature/MPS-8-y", "develop", "MPS-8", BRANCHES))
        # ... and every commit must belong to the ticket.
        self.assertEqual(self.guard_error("feature/MPS-8-y", "develop", "MPS-9", BRANCHES), "branch_base_mismatch")
        # ... checked on the pushed branch when there is one (that is what the MR contains).
        self.mps("git", "push", "--branch=feature/MPS-8-y", "--base=develop")
        self.git("commit", "-q", "--allow-empty", "-m", "local only, not pushed")
        self.assertIsNone(mps.ensure_mr_target(self.repo, "feature/MPS-8-y", "develop", "MPS-8", BRANCHES))
        # The CLI applies the guard before any GitLab call (none is configured here).
        refused = self.mps("mr", "ensure", "--source=feature/MPS-8-y", "--target=release/1.0", "--title=t",
                           "--description=Close MPS-8", "--key=MPS-8", "--type=bug")
        self.assertEqual(refused["error"], "target_mismatch_inferred_base")
        # m3: a Story can never go into a release branch, whatever the branches say.
        story = self.mps("mr", "ensure", "--source=feature/MPS-8-y", "--target=release/1.0", "--title=t",
                         "--description=Close MPS-8", "--key=MPS-8", "--type=story")
        self.assertEqual(story["error"], "phase_rule_violation")

    def plan(self, *args):
        return self.mps("flow", "plan", *args)

    def test_flow_plan_dirty_tree_and_ticket_branch(self):
        # M2: a clean develop does not pin the phase; the user's choice wins.
        self.assertEqual(self.plan("--type=story", "--key=MPS-9")["error"], "phase_required")
        clean = self.plan("--type=story", "--key=MPS-9", "--phase=dev")
        self.assertEqual((clean["phase"], clean["phase_source"]), ("dev", "requested_clean_tree"))
        self.write("wip.txt", "work\n")
        dirty = self.plan("--type=story", "--key=MPS-9")
        self.assertEqual((dirty["phase"], dirty["phase_source"], dirty["target_branch"]), ("dev", "detected", "develop"))
        self.assertEqual(self.plan("--type=bug", "--key=MPS-9", "--phase=production")["error"], "phase_conflict")
        os.remove(os.path.join(self.repo, "wip.txt"))
        # The current ticket's own branch pins its recorded base even when clean.
        self.prepare("bugfix/MPS-9-z", "MPS-9", "release/1.0")
        self.assertEqual(self.plan("--type=bug", "--key=MPS-9", "--phase=dev")["error"], "phase_conflict")
        self.assertEqual(self.plan("--type=story", "--key=MPS-9")["error"], "phase_rule_violation")
        # M3c: another ticket's branch does not pin anything.
        other = self.plan("--type=bug", "--key=MPS-10", "--phase=dev")
        self.assertEqual((other["phase"], other["current_branch_role"]), ("dev", "other"))
        self.assertIn("other_ticket_branch", [w["code"] for w in other["warnings"]])
        self.git("switch", "-q", "-c", "my-work")
        self.assertEqual(self.plan("--type=bug", "--key=MPS-9")["error"], "phase_required")

    def test_flow_plan_recorded_base_gone(self):
        self.git("push", "-q", "origin", "develop:release/2.0")
        self.prepare("bugfix/MPS-11-x", "MPS-11", "release/2.0")
        self.git("push", "-q", "origin", "--delete", "release/2.0")
        self.git("update-ref", "refs/remotes/origin/release/2.0", "HEAD")  # stale local ref: the pruned fetch clears it
        clean = self.plan("--type=bug", "--key=MPS-11", "--phase=dev")
        self.assertEqual((clean["phase"], clean["current_branch_role"]), ("dev", "other"))
        self.assertIn("recorded_base_gone", [w["code"] for w in clean["warnings"]])
        self.assertFalse(mps.ref_exists(self.repo, "refs/remotes/origin/release/2.0"))
        self.write("wip.txt", "work\n")
        self.assertEqual(self.plan("--type=bug", "--key=MPS-11", "--phase=dev")["error"], "recorded_base_gone")

    def test_flow_plan_detached_head(self):
        self.git("switch", "-q", "--detach", "origin/develop")
        self.write("wip.txt", "work\n")
        plan = self.plan("--type=bug", "--key=MPS-12")
        self.assertEqual((plan["phase"], plan["base_branch"], plan["detached"]), ("dev", "develop", True))
        self.git("commit", "-q", "--allow-empty", "-m", "detached work")  # a commit no origin branch points at
        self.assertEqual(self.plan("--type=bug", "--key=MPS-12", "--phase=dev")["error"], "detached_head")

    def test_flow_plan_beta_with_mocked_gitlab(self):
        self.write_env(MPS_GITLAB_URL="https://git.example", MPS_GITLAB_PAT="x", MPS_GITLAB_PROJECT="grp/proj")
        with mock.patch.object(mps, "gitlab_client", return_value=fake_gitlab(["release/1.0", "release/1.1"])):
            latest = self.plan("--type=bug", "--key=MPS-13", "--phase=beta")
            self.assertEqual((latest["base_branch"], latest["phase_source"]), ("release/1.1", "requested_clean_tree"))
            self.git("switch", "-q", "release/1.0")
            self.write("wip.txt", "work\n")
            pinned = self.plan("--type=bug", "--key=MPS-13")
            self.assertEqual((pinned["phase"], pinned["base_branch"], pinned["target_branch"]),
                             ("beta", "release/1.0", "release/1.0"))
            self.assertEqual([w["code"] for w in pinned["warnings"]], ["not_latest_release"])
        with mock.patch.object(mps, "gitlab_client", return_value=fake_gitlab(["release/1.1"])):
            self.assertEqual(self.plan("--type=bug", "--key=MPS-13")["error"], "release_branch_gone")

    def test_jira_create_on_another_board_with_mocked_jira(self):
        self.write_env(MPS_JIRA_URL="https://jira.example", MPS_JIRA_PAT="x", MPS_JIRA_PROJECT_KEY="MPS")
        jira = fake_jira()
        with mock.patch.object(mps, "jira_client", return_value=jira):
            created = self.mps("jira", "create", "--type=story", "--summary=Vẽ lại icon", "--project=art")
            self.assertEqual((created["key"], created["project"]), ("ART-1", "ART"))
            body = [call[2] for call in jira.calls if call[0] == "POST"][0]
            self.assertEqual(body["fields"]["project"], {"key": "ART"})
            self.assertEqual(body["fields"]["assignee"], {"name": "hung"})
            missing = self.mps("jira", "create", "--type=story", "--summary=x", "--project=NOPE")
            self.assertEqual(missing["error"], "jira_project_not_found")
            self.assertEqual([p["key"] for p in missing["available_projects"]], ["ART", "MPS"])
            default = self.mps("jira", "create", "--type=story", "--summary=x")
            self.assertEqual(default["project"], "MPS")
            self.assertNotIn(("GET", "/rest/api/2/project/MPS", None), jira.calls)  # default is not re-validated

    # -- round 2: M1 scope gate, M5 exact paths ----------------------------

    def test_commit_requires_fresh_review(self):
        self.prepare("feature/MPS-14-a", "MPS-14")
        self.write("a.txt", "a\n")
        self.write("b.txt", "b\n")
        self.assertEqual(self.commit("feat: MPS-14 a", "a.txt")["error"], "scope_review_required")
        self.approve(["a.txt"], out_of_scope=["b.txt"], mixed=[])
        self.assertEqual(self.commit("feat: MPS-14 a", "a.txt", "b.txt")["error"], "not_in_scope")
        self.assertEqual(self.mps("git", "commit", "--message=x", "--files", "a.txt",
                                  "--include-out-of-scope", "c.txt")["error"], "invalid_include")
        self.write("a.txt", "a changed after review\n")
        self.assertEqual(self.commit("feat: MPS-14 a", "a.txt")["error"], "changed_since_review")
        self.approve(["a.txt"], out_of_scope=["b.txt"])
        self.git("commit", "-q", "--allow-empty", "-m", "feat: MPS-14 head moved")
        self.assertEqual(self.commit("feat: MPS-14 a", "a.txt")["error"], "scope_review_required")
        self.approve(["a.txt"], out_of_scope=["b.txt"])
        # The user explicitly named b.txt: it may be included.
        done = self.mps("git", "commit", "--message=feat: MPS-14 a", "--files", "a.txt", "b.txt",
                        "--include-out-of-scope", "b.txt")
        self.assertEqual(sorted(done["files"]), ["A\ta.txt", "A\tb.txt"])
        self.assertFalse(os.path.exists(mps.scope_path(self.repo)))

    def test_mixed_and_needs_decision_require_explicit_choice(self):
        self.prepare("feature/MPS-15-a", "MPS-15")
        self.write("a.txt", "a\n")
        self.write("m.txt", "m\n")
        self.write("c.txt", "c\n")
        result = self.approve(["a.txt"], mixed=["m.txt"], concern=["c.txt"], verdict="FAIL")
        self.assertEqual((result["commit_files"], result["needs_decision"], result["mixed_files"]),
                         (["a.txt"], ["c.txt"], ["m.txt"]))
        self.assertEqual(self.commit("feat: MPS-15 a", "a.txt", "m.txt")["error"], "not_in_scope")
        self.assertEqual(self.commit("feat: MPS-15 a", "a.txt", "c.txt")["error"], "not_in_scope")

    def test_deleted_folder_is_not_accepted(self):
        self.prepare("feature/MPS-16-cleanup", "MPS-16")
        self.write("Assets/Old/a.txt", "a\n")
        self.write("Assets/Old/b.txt", "b\n")
        self.git("add", "Assets")
        self.git("commit", "-q", "-m", "feat: MPS-16 add old assets")
        shutil.rmtree(os.path.join(self.repo, "Assets"))
        refused = self.commit("feat: MPS-16 cleanup", "Assets/Old")
        self.assertEqual(refused["error"], "explicit_files_required")
        self.assertEqual((refused["files"], refused["changed_files_inside"]),
                         (["Assets/Old"], ["Assets/Old/a.txt", "Assets/Old/b.txt"]))
        self.approve(["Assets/Old/a.txt", "Assets/Old/b.txt"])
        done = self.commit("feat: MPS-16 cleanup", "Assets/Old/a.txt", "Assets/Old/b.txt")
        self.assertEqual(sorted(done["files"]), ["D\tAssets/Old/a.txt", "D\tAssets/Old/b.txt"])

    # -- round 3 -----------------------------------------------------------

    def test_edit_between_bundle_and_classify_is_stale(self):
        """M1: the approval is bound to what the reviewer saw, not to the state at classify time."""
        self.prepare("feature/MPS-17-a", "MPS-17")
        self.write("a.txt", "reviewed\n")
        bundle_id = self.make_bundle()
        self.write("a.txt", "reviewed\nplus an unreviewed line\n")
        stale = self.classify(self.write_reply(bundle_id, ["a.txt"]))
        self.assertEqual((stale["error"], stale["reason"]), ("review_stale", "files_changed"))
        self.write("new.txt", "appeared after the bundle\n")
        self.assertEqual(self.classify(self.write_reply(bundle_id, ["a.txt"]))["reason"], "files_changed")
        self.assertEqual(self.commit("feat: MPS-17 a", "a.txt")["error"], "scope_review_required")

    def test_old_or_incomplete_reviews_never_approve(self):
        """M2: reused reply, reply without BUNDLE, reply without VERDICT, include on an incomplete scope."""
        self.prepare("feature/MPS-18-a", "MPS-18")
        self.write("a.txt", "a\n")
        old_bundle = self.make_bundle()
        old_reply = self.write_reply(old_bundle, ["a.txt"], name="old")
        self.write("b.txt", "b\n")
        new_bundle = self.make_bundle()
        reused = self.classify(old_reply)
        self.assertEqual((reused["error"], reused["reason"]), ("review_stale", "reply_for_other_bundle"))
        no_id = self.classify(self.write_reply(None, ["a.txt", "b.txt"]))
        self.assertEqual((no_id["error"], no_id["reason"]), ("review_stale", "reply_without_bundle_id"))
        no_verdict = self.classify(self.write_reply(new_bundle, ["a.txt", "b.txt"], verdict=None))
        self.assertFalse(no_verdict["complete"])
        self.assertEqual(self.commit("feat: MPS-18 a", "a.txt")["error"], "scope_incomplete")
        partial = self.classify(self.write_reply(new_bundle, ["a.txt"]))  # b.txt not classified
        self.assertFalse(partial["complete"])
        forced = self.mps("git", "commit", "--message=feat: MPS-18 a", "--files", "a.txt", "b.txt",
                          "--include-out-of-scope", "b.txt")
        self.assertEqual(forced["error"], "scope_incomplete")
        self.assertTrue(self.classify(self.write_reply(new_bundle, ["a.txt"], out_of_scope=["b.txt"]))["complete"])
        self.assertTrue(self.commit("feat: MPS-18 a", "a.txt")["ok"])

    def test_squash_merged_branch_is_not_unpushed_work(self):
        """M3: after squash-merge + branch deletion + prune, the old ticket's commits are not 'unpushed'."""
        self.prepare("feature/MPS-19-a", "MPS-19")
        self.write("a.txt", "a\n")
        self.approve(["a.txt"])
        self.commit("feat: MPS-19 a", "a.txt")
        pushed = self.mps("git", "push", "--branch=feature/MPS-19-a", "--base=develop")
        self.assertEqual(mps.last_pushed_commit(self.repo, "feature/MPS-19-a"), pushed["pushed_commit"])
        # A maintainer squash-merges on GitLab, which then deletes the source branch.
        self.push_upstream("develop", "a.txt", "a\n", "MPS-19 a (squashed)")
        self.git("push", "-q", "origin", "--delete", "feature/MPS-19-a", cwd=self.other)
        self.git("fetch", "-q", "--prune")
        self.assertFalse(mps.ref_exists(self.repo, "refs/remotes/origin/feature/MPS-19-a"))
        self.assertEqual(mps.unpushed_commit_count(self.repo), 0)
        self.assertEqual(mps.work_in_progress(self.repo, mps.DEFAULT_GENERATED_PATTERNS), (False, []))
        preflight = self.mps("git", "preflight", "--base=develop", "--branch=feature/MPS-20-b")
        self.assertNotIn("local_commits_not_carried", [w["code"] for w in preflight["warnings"]])
        nxt = self.prepare("feature/MPS-20-b", "MPS-20")
        self.assertEqual((nxt["action"], nxt["commits_left_behind"]), ("created_from_base", 0))
        # Without the record the same commit would count as unpushed (the regression this guards against).
        self.git("config", "--unset", "branch.feature/MPS-19-a.mps-pushed")
        self.git("switch", "-q", "feature/MPS-19-a")
        self.assertEqual(mps.unpushed_commit_count(self.repo), 1)

    def test_resume_commit_with_leftover_files(self):
        """m2: re-running the same commit after success is nothing_to_commit, even with other files still changed."""
        self.prepare("feature/MPS-21-a", "MPS-21")
        self.write("a.txt", "a\n")
        self.write("left.txt", "not for this ticket\n")
        self.approve(["a.txt"], out_of_scope=["left.txt"])
        self.assertEqual(self.commit("feat: MPS-21 a", "a.txt")["left_uncommitted"], ["left.txt"])
        again = self.commit("feat: MPS-21 a", "a.txt")
        self.assertEqual((again["error"], again["already_committed"]), ("nothing_to_commit", ["a.txt"]))
        self.assertEqual(self.commit("feat: MPS-21 a", "a.txt", "typo.txt")["error"], "explicit_files_required")

    def test_inferred_base_tie_is_ambiguous(self):
        """m3: develop and master on the same commit: only develop may be inferred."""
        self.git("push", "-q", "origin", "develop:master")
        self.git("fetch", "-q")
        self.prepare("feature/MPS-22-a", "MPS-22")
        self.write("a.txt", "a\n")
        self.approve(["a.txt"])
        self.commit("feat: MPS-22 a", "a.txt")
        self.git("config", "--unset", "branch.feature/MPS-22-a.mps-base")
        with self.assertRaises(mps.MpsError) as ctx:
            mps.ensure_mr_target(self.repo, "feature/MPS-22-a", "master", "MPS-22", BRANCHES)
        self.assertEqual((ctx.exception.code, ctx.exception.extra["inferred_bases"]),
                         ("target_ambiguous", ["develop", "master"]))
        self.assertIsNone(mps.ensure_mr_target(self.repo, "feature/MPS-22-a", "develop", "MPS-22", BRANCHES))

    # -- generated files and phase pinning ----------------------------------

    def test_generated_files_do_not_pin_the_phase(self):
        self.git("switch", "-q", "release/1.0")
        self.write("ProjectSettings/ProjectSettings.asset", "unity rewrote this\n")
        self.write("Game.csproj", "<Project/>\n")
        plan = self.plan("--type=bug", "--key=MPS-30", "--phase=dev")
        self.assertEqual((plan["phase"], plan["phase_source"], plan["work_in_progress"]),
                         ("dev", "requested_clean_tree", False))
        self.assertEqual(sorted(plan["generated_changes"]), ["Game.csproj", "ProjectSettings/ProjectSettings.asset"])
        required = self.plan("--type=bug", "--key=MPS-30")
        self.assertEqual((required["error"], len(required["generated_changes"])), ("phase_required", 2))
        # A real source change on the release branch does pin it.
        self.write("src/fix.cs", "class Fix {}\n")
        conflict = self.plan("--type=bug", "--key=MPS-30", "--phase=dev")
        self.assertEqual(conflict["error"], "phase_conflict")
        self.assertEqual(len(conflict["generated_changes"]), 2)
        # Committing is unaffected: the generated files are still offered to the scope review.
        uncommitted, _ = mps.review_candidates(self.repo, "origin/release/1.0")
        self.assertIn("ProjectSettings/ProjectSettings.asset", uncommitted)

    def test_generated_patterns_from_env(self):
        self.write(".env", "MPS_GENERATED_PATTERNS=Assets/Gen/**\n")  # untracked .env never counts as work
        self.git("switch", "-q", "release/1.0")
        self.write("Assets/Gen/Bindings.cs", "// generated\n")
        plan = self.plan("--type=bug", "--key=MPS-31", "--phase=dev")
        self.assertEqual((plan["phase_source"], plan["generated_changes"]),
                         ("requested_clean_tree", ["Assets/Gen/Bindings.cs"]))
        self.assertEqual(self.mps("env", "set", "MPS_GENERATED_PATTERNS", "Assets/Gen/**,*.lock")["key"],
                         "MPS_GENERATED_PATTERNS")


if __name__ == "__main__":
    unittest.main()
