# -*- coding: utf-8 -*-
"""Unit tests for the pure functions of plugins/mps-git-flow/skills/mps-git-flow/scripts/mps.py (no network, no git)."""

import importlib.util
import io
import json
import os
import re
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
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

    UNITY_AT_ROOT = mps.generated_rules([""], [])

    def test_default_patterns_at_the_unity_root(self):
        generated = ["ProjectSettings/ProjectSettings.asset", "ProjectSettings/Sub/Deep.asset",
                     "Packages/packages-lock.json", "UserSettings/EditorUserSettings.asset", "Game.csproj",
                     "Assembly-CSharp.csproj", "Game.sln", "Library/ScriptAssemblies/x.dll"]
        for path in generated:
            self.assertTrue(mps.is_generated_path(path, self.UNITY_AT_ROOT), path)
        real = ["Assets/Scripts/Login.cs", "Packages/manifest.json", "Docs/ProjectSettings.md",
                "ProjectSettingsBackup/x.asset", "src/Game.csproj.bak", "LibraryCode/a.cs"]
        for path in real:
            self.assertFalse(mps.is_generated_path(path, self.UNITY_AT_ROOT), path)

    def test_patterns_are_anchored_to_unity_roots(self):
        """G1: a folder that merely has the same name deeper down is real work."""
        for path in ("Assets/Plugins/Library/Core.cs", "Assets/Editor/ProjectSettings/Tool.cs",
                     "Assets/Scripts/Game.csproj", "Tools/Build.sln"):
            self.assertFalse(mps.is_generated_path(path, self.UNITY_AT_ROOT), path)

    def test_nested_unity_project_and_windows_paths(self):
        rules = mps.generated_rules(["Client/Game"], [])
        self.assertTrue(mps.is_generated_path("Client/Game/ProjectSettings/TagManager.asset", rules))
        self.assertTrue(mps.is_generated_path("Client\\Game\\Packages\\packages-lock.json", rules))
        self.assertTrue(mps.is_generated_path("Client/Game/Game.csproj", rules))
        self.assertFalse(mps.is_generated_path("Client/Game/Assets/a.cs", rules))
        self.assertFalse(mps.is_generated_path("ProjectSettings/TagManager.asset", rules))  # repo root is not Unity
        self.assertFalse(mps.is_generated_path("Server/Server.csproj", rules))

    def test_no_unity_project_means_no_defaults(self):
        rules = mps.generated_rules([], [])
        self.assertEqual(rules, [])
        self.assertFalse(mps.is_generated_path("Server.sln", rules))
        self.assertFalse(mps.is_generated_path("ProjectSettings/x.asset", rules))

    def test_user_patterns_are_validated(self):
        """G2: wildcard-only or wildcard-first patterns are rejected."""
        valid, rejected = mps.parse_generated_patterns(
            " Assets/Gen/** , *, **, **/*, */**, /, *.lock, */Gen/**, ?x/y, yarn.lock, Assets\\Data\\*.json,")
        self.assertEqual(valid, ["Assets/Gen/**", "yarn.lock", "Assets/Data/*.json"])
        self.assertEqual(rejected, ["*", "**", "**/*", "*/**", "/", "*.lock", "*/Gen/**", "?x/y"])
        self.assertEqual(mps.parse_generated_patterns(None), ([], []))
        rules = mps.generated_rules([], valid)  # extra patterns apply even without a Unity project
        self.assertTrue(mps.is_generated_path("Assets/Gen/a/b.cs", rules))
        self.assertTrue(mps.is_generated_path("yarn.lock", rules))
        self.assertFalse(mps.is_generated_path("web/yarn.lock", rules))
        self.assertTrue(mps.is_generated_path("Assets/Data/settings.json", rules))
        self.assertFalse(mps.is_generated_path("Assets/Data/Sub/settings.json", rules))
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


class FakeMrGitLab(object):
    """A GitLab project (grp/proj, id 1) with labels and merge requests that POST / PUT really change.

    reject_extras: the POST is refused (400) while it carries assignee_ids or labels.
    race_status: another open MR for the branch appears just before the POST, which GitLab refuses with this status.
    """

    def __init__(self, labels=("Enhancement", "Bug"), mrs=(), reject_extras=False, race_status=None):
        self.user = {"id": 7, "username": "hung"}
        self.labels = [{"name": name} for name in labels]
        self.mrs = [dict(mr) for mr in mrs]
        self.reject_extras = reject_extras
        self.race_status = race_status
        self.calls = []

    def respond(self, status, data):
        return mps.HttpResponse(status, json.loads(json.dumps(data)), {})

    def find_mr(self, path):
        return [mr for mr in self.mrs if "/merge_requests/%s" % mr["iid"] == path[len("/projects/1"):]][0]

    def request(self, method, path, params=None, body=None, allow_statuses=()):
        self.calls.append((method, path, body))
        if (method, path) == ("GET", "/projects/grp%2Fproj"):
            return self.respond(200, {"id": 1, "path_with_namespace": "grp/proj", "web_url": "u"})
        if (method, path) == ("GET", "/user"):
            return self.respond(200, self.user)
        if (method, path) == ("GET", "/projects/1/labels"):
            assert params["include_ancestor_groups"] == "true"
            wanted = params["search"].lower()
            return self.respond(200, [label for label in self.labels if wanted in label["name"].lower()])
        if (method, path) == ("GET", "/projects/1/merge_requests"):
            return self.respond(200, [mr for mr in self.mrs if mr["source_branch"] == params["source_branch"]])
        if (method, path) == ("POST", "/projects/1/merge_requests"):
            if self.race_status:
                self.mrs.append({"iid": 9, "web_url": "u", "title": "t", "source_branch": body["source_branch"],
                                 "target_branch": body["target_branch"], "state": "opened", "labels": [],
                                 "assignees": []})
                return self.respond(self.race_status, {"message": ["Another open merge request already exists"]})
            if self.reject_extras and ("labels" in body or "assignee_ids" in body):
                return self.respond(400, {"message": "invalid assignee or label"})
            mr = {"iid": len(self.mrs) + 1, "web_url": "https://git.example/mr", "title": body["title"],
                  "description": body["description"], "source_branch": body["source_branch"],
                  "target_branch": body["target_branch"], "state": "opened",
                  "labels": [body["labels"]] if body.get("labels") else [],
                  "assignees": [self.user] if body.get("assignee_ids") == [self.user["id"]] else []}
            self.mrs.append(mr)
            return self.respond(201, mr)
        if method == "PUT" and path.startswith("/projects/1/merge_requests/"):
            mr = self.find_mr(path)
            if "assignee_ids" in body:
                mr["assignees"] = [self.user]
            if "add_labels" in body:
                mr["labels"] = mr["labels"] + [body["add_labels"]]
            return self.respond(200, mr)
        raise AssertionError("unexpected call %s %s" % (method, path))

    def get(self, path, params=None):
        return self.request("GET", path, params=params).data

    def bodies(self, method):
        return [call[2] for call in self.calls if call[0] == method]


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

    def make_unity_project(self, folder=""):
        """Commit ProjectSettings/ProjectVersion.txt (marks a Unity project root) on the current branch and push."""
        self.write(os.path.join(folder, "ProjectSettings", "ProjectVersion.txt"), "m_EditorVersion: 2022.3.0f1\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "chore: unity project")
        self.git("push", "-q", "origin", "HEAD")

    def test_generated_files_do_not_pin_the_phase(self):
        self.git("switch", "-q", "release/1.0")
        self.make_unity_project()
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

    def test_folder_named_like_generated_one_is_real_work(self):
        """G1: Assets/Plugins/Library/Core.cs is code, not Unity's Library/ folder."""
        self.git("switch", "-q", "release/1.0")
        self.make_unity_project()
        self.write("Assets/Plugins/Library/Core.cs", "class Core {}\n")
        conflict = self.plan("--type=bug", "--key=MPS-32", "--phase=dev")
        self.assertEqual((conflict["error"], conflict["generated_changes"]), ("phase_conflict", []))

    def test_non_unity_repo_does_not_use_the_defaults(self):
        self.git("switch", "-q", "release/1.0")
        self.write("Server.sln", "solution\n")
        self.write("ProjectSettings/x.asset", "not unity\n")
        conflict = self.plan("--type=bug", "--key=MPS-33", "--phase=dev")
        self.assertEqual((conflict["error"], conflict["generated_changes"]), ("phase_conflict", []))

    def test_nested_unity_project_found_on_disk(self):
        self.git("switch", "-q", "release/1.0")
        # Untracked version file: the Unity root is found on disk, not only through git.
        self.write("Client/Game/ProjectSettings/ProjectVersion.txt", "m_EditorVersion: 2022.3.0f1\n")
        self.write("Client/Game/ProjectSettings/TagManager.asset", "tags\n")
        self.write("Client/Game/Game.csproj", "<Project/>\n")
        plan = self.plan("--type=bug", "--key=MPS-34", "--phase=dev")
        self.assertEqual(plan["phase_source"], "requested_clean_tree")
        self.assertEqual(sorted(plan["generated_changes"]),
                         ["Client/Game/Game.csproj", "Client/Game/ProjectSettings/ProjectVersion.txt",
                          "Client/Game/ProjectSettings/TagManager.asset"])
        self.write("Client/Server.csproj", "<Project/>\n")  # outside the Unity root: real work
        self.assertEqual(self.plan("--type=bug", "--key=MPS-34", "--phase=dev")["error"], "phase_conflict")

    def test_generated_patterns_from_env(self):
        self.write(".env", "MPS_GENERATED_PATTERNS=Assets/Gen/**,*\n")  # untracked .env never counts as work
        self.git("switch", "-q", "release/1.0")
        self.write("Assets/Gen/Bindings.cs", "// generated\n")
        plan = self.plan("--type=bug", "--key=MPS-31", "--phase=dev")
        self.assertEqual((plan["phase_source"], plan["generated_changes"]),
                         ("requested_clean_tree", ["Assets/Gen/Bindings.cs"]))
        self.assertEqual([(w["code"], w["patterns"]) for w in plan["warnings"]],
                         [("invalid_generated_pattern", ["*"])])
        # G2: the rejected '*' does not hide real work.
        self.write("src/fix.cs", "class Fix {}\n")
        conflict = self.plan("--type=bug", "--key=MPS-31", "--phase=dev")
        self.assertEqual(conflict["error"], "phase_conflict")
        self.assertEqual(conflict["warnings"][0]["code"], "invalid_generated_pattern")
        # Only the user edits this key, by hand.
        refused = self.mps("env", "set", "MPS_GENERATED_PATTERNS", "*")
        self.assertEqual(refused["error"], "manual_edit_required")
        self.assertNotIn("MPS_GENERATED_PATTERNS", self.mps("env", "set", "FOO", "x")["allowed_keys"])

    def test_closed_unmerged_branch_counts_again(self):
        """m1: pushed but never merged (MR closed, branch deleted) -> still unpushed work."""
        self.prepare("feature/MPS-35-a", "MPS-35")
        self.write("a.txt", "a\n")
        self.approve(["a.txt"])
        self.commit("feat: MPS-35 a", "a.txt")
        self.mps("git", "push", "--branch=feature/MPS-35-a", "--base=develop")
        self.git("push", "-q", "origin", "--delete", "feature/MPS-35-a")
        self.git("fetch", "-q", "--prune")
        self.assertEqual(mps.unpushed_commit_count(self.repo), 1)
        refused = self.prepare("feature/MPS-36-b", "MPS-36")
        self.assertEqual((refused["error"], refused["count"]), ("local_commits_not_carried", 1))

    # -- 0.1.1: project setup, version check, .env onboarding ----------------

    def settings_bytes(self):
        with open(os.path.join(self.repo, ".claude", "settings.json"), "rb") as handle:
            return handle.read()

    def env_check(self, latest=None):
        """`env check` with the GitHub version lookup replaced (tests never reach the network)."""
        with mock.patch.object(mps, "fetch_latest_plugin_version", return_value=latest):
            return self.mps("env", "check")

    def write_connected_env(self):
        self.write_env(MPS_JIRA_URL="https://jira.example", MPS_JIRA_PAT="jira-token", MPS_JIRA_PROJECT_KEY="MPS",
                       MPS_GITLAB_URL="https://git.example", MPS_GITLAB_PAT="gitlab-token",
                       MPS_GITLAB_PROJECT="grp/proj")

    def connected_env_check(self, latest=None):
        """A successful `env check` (after write_connected_env) with Jira and GitLab faked."""
        jira = FakeService({("GET", "/rest/api/2/myself"): (200, {"name": "hung"}),
                            ("GET", "/rest/api/2/project/MPS"): (200, {"key": "MPS", "name": "Game"})})
        gitlab = FakeService({("GET", "/user"): (200, {"id": 7, "username": "hung"}),
                              ("GET", "/projects/grp%2Fproj"): (200, {"id": 1, "path_with_namespace": "grp/proj"}),
                              ("GET", "/projects/1/members/all/7"): (200, {"access_level": 30})})
        with mock.patch.object(mps, "jira_client", return_value=jira), \
                mock.patch.object(mps, "gitlab_client", return_value=gitlab):
            return self.env_check(latest)

    def test_project_setup_creates_settings_and_is_idempotent(self):
        """P1."""
        first = self.mps("project", "setup")
        expected = mps.render_settings_json(mps.merge_project_settings({})[0], "\n").encode("utf-8")
        self.assertEqual(self.settings_bytes(), expected)
        self.assertEqual((first["created"], first["changed"], first["changes"]),
                         (True, True, NEW_SETTINGS_CHANGES))
        self.assertTrue(first["gitignore_updated"])
        self.assertIn(".env", self.read(".gitignore").splitlines())
        self.assertEqual(first["files_to_commit"], [".claude/settings.json", ".gitignore"])
        self.assertEqual((first["warnings"], first["next"]), ([], "commit_with_mps_git_flow"))
        second = self.mps("project", "setup")
        self.assertEqual((second["created"], second["changed"], second["changes"]), (False, False, []))
        self.assertEqual(self.settings_bytes(), expected)

    def test_project_setup_keeps_keys_and_crlf_and_refuses_invalid_json(self):
        """P2."""
        os.makedirs(os.path.join(self.repo, ".claude"))
        path = os.path.join(self.repo, ".claude", "settings.json")
        with open(path, "wb") as handle:
            handle.write(b'{\r\n  "permissions": {"allow": ["Bash(ls)"]},\r\n  "env": {"A": "1"}\r\n}\r\n')
        result = self.mps("project", "setup")
        self.assertEqual(result["changes"], NEW_SETTINGS_CHANGES)
        written = self.settings_bytes()
        self.assertNotIn(b"\n", written.replace(b"\r\n", b""))
        data = json.loads(written.decode("utf-8"))
        self.assertEqual(list(data), ["permissions", "env", "extraKnownMarketplaces", "enabledPlugins", "attribution"])
        self.assertEqual((data["permissions"], data["env"]), ({"allow": ["Bash(ls)"]}, {"A": "1"}))
        broken = b'{"permissions": {'
        with open(path, "wb") as handle:
            handle.write(broken)
        refused = self.mps("project", "setup")
        self.assertEqual(refused["error"], "settings_invalid_json")
        self.assertIsInstance(refused["line"], int)
        self.assertEqual(self.settings_bytes(), broken)

    def write_settings(self, data):
        os.makedirs(os.path.join(self.repo, ".claude"), exist_ok=True)
        with open(os.path.join(self.repo, ".claude", "settings.json"), "wb") as handle:
            handle.write(data)

    def test_project_setup_rerun_before_commit_still_lists_files(self):
        """M4: changed false does not mean committed."""
        self.mps("project", "setup")
        again = self.mps("project", "setup")
        self.assertFalse(again["changed"])
        self.assertEqual(again["files_to_commit"], [".claude/settings.json", ".gitignore"])
        self.assertEqual(again["next"], "commit_with_mps_git_flow")
        self.git("add", ".claude/settings.json", ".gitignore")
        self.git("commit", "-q", "-m", "chore: integrate plugin")
        done = self.mps("project", "setup")
        self.assertEqual((done["changed"], done["files_to_commit"], done["next"]), (False, [], None))

    def test_project_setup_is_a_no_op_on_integrated_crlf_bom_file(self):
        rendered = mps.render_settings_json(mps.merge_project_settings({"model": "x"})[0], "\r\n")
        original = UTF8_BOM + rendered.encode("utf-8")
        self.write_settings(original)
        result = self.mps("project", "setup")
        self.assertEqual((result["changed"], result["changes"]), (False, []))
        self.assertEqual(self.settings_bytes(), original)

    def test_project_setup_keeps_the_file_indent(self):
        self.write_settings(b'{\n    "model": "x"\n}\n')
        self.mps("project", "setup")
        text = self.settings_bytes().decode("utf-8")
        self.assertTrue(text.startswith('{\n    "model": "x",\n    "extraKnownMarketplaces": {\n        "'), text)
        self.assertEqual([name for name in os.listdir(os.path.join(self.repo, ".claude"))], ["settings.json"])

    def test_tracked_settings_are_not_reported_as_ignored(self):
        """m2: git keeps committing a tracked file whatever .gitignore says."""
        self.write_settings(b"{}\n")
        self.git("add", ".claude/settings.json")
        self.git("commit", "-q", "-m", "chore: settings")
        self.write(".gitignore", ".claude/\n")
        result = self.mps("project", "setup")
        self.assertEqual(result["warnings"], [])
        self.assertIn(".claude/settings.json", result["files_to_commit"])

    def test_invalid_settings_count_as_not_integrated(self):
        self.write_settings(b'{"enabledPlugins": ')
        self.assertEqual(mps.project_settings_status(self.repo), "missing")
        self.assertIsNone(mps.load_project_settings(self.repo))

    def test_env_check_skips_version_check_when_pinned(self):
        """M3: a ref-pinned marketplace is a deliberate version choice."""
        settings = mps.merge_project_settings({})[0]
        settings["extraKnownMarketplaces"]["mps-cdci-agents"]["source"]["ref"] = "v0.1.1"
        self.write_settings(mps.render_settings_json(settings, "\n").encode("utf-8"))
        self.write_connected_env()
        with mock.patch.object(mps, "fetch_latest_plugin_version", return_value="99.0.0") as fetch:
            result = self.connected_env_check(latest="99.0.0")
            fetch.assert_not_called()
        self.assertEqual(result["plugin_version"],
                         {"running": mps.VERSION, "latest": None, "checked": False, "pinned": "v0.1.1"})
        codes = [w["code"] for w in result["warnings"]]
        self.assertNotIn("plugin_outdated", codes)
        self.assertNotIn("project_not_integrated", codes)

    def test_project_setup_warns_when_settings_are_ignored(self):
        """P3."""
        self.write(".gitignore", ".claude/\n")
        result = self.mps("project", "setup")
        self.assertEqual([w["code"] for w in result["warnings"]], ["settings_ignored_by_git"])

    def test_env_check_reports_newer_plugin_version(self):
        """P4: plugin_outdated on success and on errors; an unreachable GitHub is silent."""
        self.write_connected_env()
        outdated = self.connected_env_check(latest="99.0.0")
        self.assertEqual(outdated["plugin_version"], {"running": mps.VERSION, "latest": "99.0.0", "checked": True})
        warning = [w for w in outdated["warnings"] if w["code"] == "plugin_outdated"][0]
        self.assertEqual((warning["latest"], warning["running"]), ("99.0.0", mps.VERSION))
        self.assertEqual(warning["commands"], ["claude plugin marketplace update mps-cdci-agents",
                                               "claude plugin update mps-git-flow@mps-cdci-agents"])
        self.assertEqual(outdated["gitlab_access_level"], 30)
        offline = self.connected_env_check(latest=None)
        self.assertEqual(offline["plugin_version"], {"running": mps.VERSION, "latest": None, "checked": False})
        self.assertNotIn("plugin_outdated", [w["code"] for w in offline["warnings"]])
        os.remove(os.path.join(self.repo, ".env"))
        missing = self.env_check(latest="99.0.0")
        self.assertEqual((missing["error"], missing["next"]), ("env_missing", "env init --open"))
        self.assertEqual(missing["plugin_version"]["latest"], "99.0.0")
        self.assertIn("plugin_outdated", [w["code"] for w in missing["warnings"]])

    def test_env_check_reports_project_not_integrated(self):
        """P5."""
        self.write_connected_env()
        before = self.connected_env_check()
        self.assertIn("project_not_integrated", [w["code"] for w in before["warnings"]])
        self.mps("project", "setup")
        after = self.connected_env_check()
        self.assertNotIn("project_not_integrated", [w["code"] for w in after["warnings"]])

    def test_env_init_gives_fill_guide_for_blank_member_keys(self):
        """R.11.4: a new .env needs the three member keys; a filled one needs nothing."""
        created = self.mps("env", "init")
        self.assertTrue(created["created"])
        self.assertEqual(created["keys_to_fill"], list(mps.MEMBER_KEYS))
        self.assertEqual([entry["key"] for entry in created["fill_guide"]], list(mps.MEMBER_KEYS))
        with open(os.path.join(self.repo, ".env"), "rb") as handle:
            text = handle.read().decode("utf-8")
        for key, value in (("MPS_JIRA_PAT", "jira-token"), ("MPS_JIRA_PROJECT_KEY", "MPS"),
                           ("MPS_GITLAB_PAT", "gitlab-token")):
            text = mps.update_env_text(text, key, value)
        with open(os.path.join(self.repo, ".env"), "wb") as handle:
            handle.write(text.encode("utf-8"))
        again = self.mps("env", "init")
        self.assertEqual((again["created"], again["fill_guide"], again["keys_to_fill"]), (False, [], []))

    def test_env_check_missing_tokens_gives_fill_guide(self):
        """R.11.4: blank PATs -> missing_config with a guide for exactly those keys."""
        self.write_env(MPS_JIRA_PAT="", MPS_JIRA_PROJECT_KEY="MPS", MPS_GITLAB_PAT="")
        result = self.env_check()
        self.assertEqual(result["error"], "missing_config")
        self.assertEqual(result["missing_keys"], ["MPS_JIRA_PAT", "MPS_GITLAB_PAT"])
        self.assertEqual([entry["key"] for entry in result["fill_guide"]], ["MPS_JIRA_PAT", "MPS_GITLAB_PAT"])
        self.assertIn("plugin_version", result)

    def test_env_check_rejected_token_gives_fill_guide(self):
        """R.11.2: a 401 from GitLab during env check carries the guide for that one token."""
        self.write_env(MPS_JIRA_URL="https://jira.example", MPS_JIRA_PAT="jira-token", MPS_JIRA_PROJECT_KEY="MPS",
                       MPS_GITLAB_URL="https://git.example", MPS_GITLAB_PAT="gitlab-token")
        jira = FakeService({("GET", "/rest/api/2/myself"): (200, {"name": "hung"})})
        gitlab = mock.Mock()
        gitlab.get.side_effect = mps.MpsError("auth_failed", "401", service="gitlab", status=401)
        with mock.patch.object(mps, "jira_client", return_value=jira), \
                mock.patch.object(mps, "gitlab_client", return_value=gitlab):
            result = self.env_check()
        self.assertEqual(result["error"], "auth_failed")
        self.assertEqual([entry["key"] for entry in result["fill_guide"]], ["MPS_GITLAB_PAT"])
        self.assertIn("hết hạn", result["fill_guide"][0]["steps"][0])

    # -- 0.1.1: MR assignee, labels, no AI attribution ------------------------

    def pushed_ticket_branch(self, key):
        """A pushed ticket branch with one commit for `key`, ready for `mr ensure`."""
        if not os.path.isfile(os.path.join(self.repo, ".env")):
            self.write_env(MPS_GITLAB_URL="https://git.example", MPS_GITLAB_PAT="gitlab-token",
                           MPS_GITLAB_PROJECT="grp/proj")
        branch = "feature/%s-a" % key
        self.prepare(branch, key)
        self.write("a.txt", "a %s\n" % key)
        self.approve(["a.txt"])
        self.commit("feat: %s a" % key, "a.txt")
        self.mps("git", "push", "--branch=" + branch, "--base=develop")
        return branch

    def ensure_mr(self, gitlab, branch, key, kind="story", description=None):
        with mock.patch.object(mps, "gitlab_client", return_value=gitlab):
            return self.mps("mr", "ensure", "--source=" + branch, "--target=develop", "--title=%s a" % key,
                            "--description=" + (description or "Close " + key), "--key=" + key, "--type=" + kind)

    def test_mr_created_with_assignee_and_label(self):
        branch = self.pushed_ticket_branch("MPS-40")
        gitlab = FakeMrGitLab()
        result = self.ensure_mr(gitlab, branch, "MPS-40", "story")
        self.assertEqual((result["existed"], result["assignees"], result["labels"], result["warnings"]),
                         (False, ["hung"], ["Enhancement"], []))
        body = gitlab.bodies("POST")[0]
        self.assertEqual((body["assignee_ids"], body["labels"]), ([7], "Enhancement"))
        self.assertFalse(result["attribution_removed"])

    def test_existing_mr_gets_missing_assignee_and_label(self):
        branch = self.pushed_ticket_branch("MPS-41")
        mr = {"iid": 5, "web_url": "u", "title": "t", "source_branch": branch, "target_branch": "develop",
              "state": "opened", "labels": [], "assignees": []}
        gitlab = FakeMrGitLab(mrs=[mr])
        result = self.ensure_mr(gitlab, branch, "MPS-41", "bug")
        self.assertEqual((result["existed"], result["assignees"], result["labels"]), (True, ["hung"], ["Bug"]))
        self.assertEqual(gitlab.bodies("PUT"), [{"assignee_ids": [7]}, {"add_labels": "Bug"}])
        self.assertEqual(gitlab.bodies("POST"), [])

    def test_existing_assignee_is_left_alone(self):
        branch = self.pushed_ticket_branch("MPS-42")
        mr = {"iid": 6, "web_url": "u", "title": "t", "source_branch": branch, "target_branch": "develop",
              "state": "opened", "labels": ["Bug"], "assignees": [{"id": 9, "username": "lead"}]}
        gitlab = FakeMrGitLab(mrs=[mr])
        result = self.ensure_mr(gitlab, branch, "MPS-42", "bug")
        self.assertEqual((result["assignees"], result["labels"], result["warnings"]), (["lead"], ["Bug"], []))
        self.assertEqual(gitlab.bodies("PUT"), [])

    def test_missing_label_warns_and_still_creates_the_mr(self):
        branch = self.pushed_ticket_branch("MPS-43")
        gitlab = FakeMrGitLab(labels=("Bug report",))
        result = self.ensure_mr(gitlab, branch, "MPS-43", "bug")
        self.assertEqual((result["existed"], result["labels"], result["assignees"]), (False, [], ["hung"]))
        self.assertEqual([(w["code"], w["label"]) for w in result["warnings"]], [("label_not_found", "Bug")])
        self.assertNotIn("labels", gitlab.bodies("POST")[0])

    def test_label_with_other_case_uses_the_existing_name(self):
        branch = self.pushed_ticket_branch("MPS-44")
        gitlab = FakeMrGitLab(labels=("bug", "enhancement"))
        result = self.ensure_mr(gitlab, branch, "MPS-44", "bug")
        self.assertEqual(result["labels"], ["bug"])
        self.assertEqual(gitlab.bodies("POST")[0]["labels"], "bug")

    def test_rejected_extras_still_create_the_mr(self):
        branch = self.pushed_ticket_branch("MPS-46")
        gitlab = FakeMrGitLab(reject_extras=True)
        result = self.ensure_mr(gitlab, branch, "MPS-46", "story")
        self.assertEqual((result["existed"], result["iid"]), (False, 1))
        self.assertEqual(sorted(w["code"] for w in result["warnings"]), ["assign_failed", "label_failed"])
        self.assertEqual(len(gitlab.bodies("POST")), 2)

    def test_mr_appearing_during_create_is_reused(self):
        """n2: GitLab may answer 409 or 422 when an open MR for the branch already exists."""
        branch = self.pushed_ticket_branch("MPS-47")
        for status in (409, 422):
            gitlab = FakeMrGitLab(race_status=status)
            result = self.ensure_mr(gitlab, branch, "MPS-47", "bug")
            self.assertEqual((result["existed"], result["iid"], result["assignees"], result["labels"]),
                             (True, 9, ["hung"], ["Bug"]), status)

    def test_ai_attribution_stripped_from_commit_and_mr(self):
        branch = "feature/MPS-45-a"
        self.write_env(MPS_GITLAB_URL="https://git.example", MPS_GITLAB_PAT="gitlab-token",
                       MPS_GITLAB_PROJECT="grp/proj")
        self.prepare(branch, "MPS-45")
        self.write("a.txt", "a\n")
        self.approve(["a.txt"])
        only_ai = self.commit("Co-Authored-By: Claude <noreply@anthropic.com>", "a.txt")
        self.assertEqual(only_ai["error"], "empty_message")
        human = "Co-Authored-By: Lan Nguyen <lan@example.com>"
        message = "feat: MPS-45 a\n\n%s\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\n" % human
        done = self.commit(message, "a.txt")
        self.assertTrue(done["attribution_removed"])
        self.assertEqual(self.git("log", "-1", "--format=%B").strip(), "feat: MPS-45 a\n\n" + human)
        self.mps("git", "push", "--branch=" + branch, "--base=develop")
        gitlab = FakeMrGitLab()
        description = ("Close MPS-45\n%s\n\n\U0001F916 Generated with [Claude Code](https://claude.com/claude-code)"
                       % human)
        result = self.ensure_mr(gitlab, branch, "MPS-45", "story", description)
        self.assertTrue(result["attribution_removed"])
        self.assertEqual(gitlab.bodies("POST")[0]["description"], "Close MPS-45\n" + human)


# ---------------------------------------------------------------------------
# 0.1.1: project integration, version check, release discipline, bootstrap
# ---------------------------------------------------------------------------

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
PLUGIN_DIR = os.path.join(REPO_ROOT, "plugins", "mps-git-flow")
SCRIPTS_DIR = os.path.join(PLUGIN_DIR, "skills", "mps-git-flow", "scripts")
BOOTSTRAP_PS1 = os.path.join(SCRIPTS_DIR, "bootstrap.ps1")
BOOTSTRAP_SH = os.path.join(SCRIPTS_DIR, "bootstrap.sh")
UTF8_BOM = b"\xef\xbb\xbf"
NEW_SETTINGS_CHANGES = ["marketplace_added", "plugin_enabled", "attribution_disabled"]
EXPECTED_MARKETPLACE = {"source": {"source": "github", "repo": "hung-bui-121/mps-cdci-agents"}, "autoUpdate": True}
BOOTSTRAP_KEYS = ("ok", "os", "python_cmd", "missing", "manual_steps")
BOOTSTRAP_TIMEOUT_SECONDS = 120
# A fake installer outlives the tiny test budget by far; the pipe must close long before it ends.
SLOW_INSTALLER_SECONDS = 25
PIPE_CLOSE_MAX_SECONDS = 15
# The stalled lookup is given 0.2 s; anything near the real 3 s would mean the thread limit does not work.
STALLED_LOOKUP_MAX_SECONDS = 2


def _read_bytes(path):
    with open(path, "rb") as handle:
        return handle.read()


class MergeProjectSettingsTests(unittest.TestCase):
    """U1."""

    def test_empty_settings_get_both_entries(self):
        merged, changes, warnings = mps.merge_project_settings({})
        self.assertEqual(merged, {"extraKnownMarketplaces": {"mps-cdci-agents": EXPECTED_MARKETPLACE},
                                  "enabledPlugins": {"mps-git-flow@mps-cdci-agents": True},
                                  "attribution": {"commit": "", "pr": "", "sessionUrl": False}})
        self.assertEqual((changes, warnings), (NEW_SETTINGS_CHANGES, []))

    def test_unrelated_keys_and_order_kept_input_not_mutated(self):
        settings = {"permissions": {"allow": ["Bash(ls)"]}, "env": {"A": "1"}, "hooks": {"Stop": []}}
        original = json.loads(json.dumps(settings))
        merged, _, _ = mps.merge_project_settings(settings)
        self.assertEqual(list(merged), ["permissions", "env", "hooks", "extraKnownMarketplaces", "enabledPlugins",
                                        "attribution"])
        self.assertEqual(merged["hooks"], {"Stop": []})
        self.assertEqual(settings, original)

    def test_existing_entry_auto_update_turned_on(self):
        settings = {"extraKnownMarketplaces": {"mps-cdci-agents": {
            "source": {"source": "github", "repo": "hung-bui-121/mps-cdci-agents"}, "autoUpdate": False}},
            "enabledPlugins": {"mps-git-flow@mps-cdci-agents": False}}
        merged, changes, warnings = mps.merge_project_settings(settings)
        self.assertEqual(changes, ["auto_update_enabled", "plugin_enabled", "attribution_disabled"])
        self.assertEqual(warnings, [])
        self.assertIs(merged["extraKnownMarketplaces"]["mps-cdci-agents"]["autoUpdate"], True)
        self.assertIs(merged["enabledPlugins"]["mps-git-flow@mps-cdci-agents"], True)

    def test_pinned_ref_is_not_a_different_source(self):
        entry = {"source": {"source": "github", "repo": "hung-bui-121/mps-cdci-agents", "ref": "v0.1.1"},
                 "autoUpdate": True}
        merged, changes, warnings = mps.merge_project_settings({"extraKnownMarketplaces": {"mps-cdci-agents": entry}})
        self.assertEqual((changes, warnings), (["plugin_enabled", "attribution_disabled"], []))
        self.assertEqual(merged["extraKnownMarketplaces"]["mps-cdci-agents"]["source"]["ref"], "v0.1.1")

    def test_different_source_is_kept_and_reported(self):
        local = {"source": "directory", "path": "D:/work/mps-cdci-agents"}
        settings = {"extraKnownMarketplaces": {"mps-cdci-agents": {"source": local, "autoUpdate": True}}}
        merged, _, warnings = mps.merge_project_settings(settings)
        self.assertEqual(merged["extraKnownMarketplaces"]["mps-cdci-agents"]["source"], local)
        self.assertEqual([(w["code"], w["source"]) for w in warnings], [("marketplace_source_differs", local)])
        self.assertIn("D:/work/mps-cdci-agents", warnings[0]["message"])

    def test_second_merge_is_a_no_op(self):
        merged, _, _ = mps.merge_project_settings({"model": "x"})
        again, changes, warnings = mps.merge_project_settings(merged)
        self.assertEqual((again, changes, warnings), (merged, [], []))

    def test_unexpected_types_conflict(self):
        for settings, key in (({"extraKnownMarketplaces": []}, "extraKnownMarketplaces"),
                              ({"extraKnownMarketplaces": {"mps-cdci-agents": "x"}},
                               "extraKnownMarketplaces.mps-cdci-agents"),
                              ({"extraKnownMarketplaces": {"mps-cdci-agents": None}},
                               "extraKnownMarketplaces.mps-cdci-agents"),
                              ({"enabledPlugins": ["mps-git-flow@mps-cdci-agents"]}, "enabledPlugins")):
            with self.assertRaises(mps.MpsError) as ctx:
                mps.merge_project_settings(settings)
            self.assertEqual((ctx.exception.code, ctx.exception.extra["key"]), ("settings_conflict", key))


class AttributionSettingTests(unittest.TestCase):
    """`project setup` hides Claude Code's commit / PR attribution without overwriting the project's own choice."""

    def test_partial_attribution_gets_only_the_missing_parts(self):
        merged, changes, warnings = mps.merge_project_settings({"attribution": {"pr": ""}})
        self.assertEqual(merged["attribution"], {"pr": "", "commit": "", "sessionUrl": False})
        self.assertIn("attribution_disabled", changes)
        self.assertEqual(warnings, [])

    def test_custom_attribution_is_kept_and_reported(self):
        custom = {"commit": "Made by the team", "pr": "", "sessionUrl": True}
        merged, changes, warnings = mps.merge_project_settings({"attribution": dict(custom)})
        self.assertEqual(merged["attribution"], custom)
        self.assertNotIn("attribution_disabled", changes)
        self.assertEqual([(w["code"], w["keys"]) for w in warnings], [("attribution_kept", ["commit", "sessionUrl"])])

    def test_false_already_hides_everything(self):
        merged, changes, _ = mps.merge_project_settings({"attribution": False})
        self.assertIs(merged["attribution"], False)
        self.assertNotIn("attribution_disabled", changes)

    def test_unexpected_type_conflicts(self):
        with self.assertRaises(mps.MpsError) as ctx:
            mps.merge_project_settings({"attribution": "none"})
        self.assertEqual((ctx.exception.code, ctx.exception.extra["key"]), ("settings_conflict", "attribution"))


class StripAiAttributionTests(unittest.TestCase):
    def test_claude_lines_removed_human_lines_kept(self):
        text = "\n".join([
            "feat: MPS-1 Thêm màn hình",
            "",
            "Close MPS-1",
            "Co-Authored-By: Lan Nguyen <lan@example.com>",
            "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>",
            "  co-authored-by: Someone <bot@anthropic.com>  ",
            "Claude-Session: https://claude.ai/code/session_1",
            "\U0001F916 Generated with [Claude Code](https://claude.com/claude-code)",
            "Generated with Claude Code",
            "",
            "",
        ])
        cleaned, removed = mps.strip_ai_attribution(text)
        self.assertTrue(removed)
        self.assertEqual(cleaned, "feat: MPS-1 Thêm màn hình\n\nClose MPS-1\n"
                                  "Co-Authored-By: Lan Nguyen <lan@example.com>")

    def test_text_without_attribution_is_untouched(self):
        for text in ("Close MPS-2\n\n", "fix: MPS-3 Claude là tên nhân vật trong game", "Generated with care", ""):
            self.assertEqual(mps.strip_ai_attribution(text), (text, False))

    def test_human_lines_mentioning_claude_are_kept(self):
        for line in ("Co-Authored-By: Claude Martin <claude.martin@vng.com.vn>", "claude-api: bump SDK",
                     "Generated with the OpenAPI generator for the claude endpoint", "Close MPS-12",
                     "Claude-Version: 3 (header documented in the API)", "See https://claude.ai/code for details"):
            self.assertEqual(mps.strip_ai_attribution(line), (line, False), line)

    def test_ai_forms_are_stripped(self):
        for line in ("Co-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
                     "Co-Authored-By: Claude <noreply@anthropic.com>",
                     "Co-Authored-By: Claude Code",
                     "\U0001F916 Generated with [Claude Code](https://claude.com/claude-code)",
                     "Generated by Claude Code",
                     "https://claude.ai/code/session_01AbCdEf",
                     "Claude-Session: abc"):
            self.assertEqual(mps.strip_ai_attribution("Close MPS-12\n" + line), ("Close MPS-12", True), line)

    def test_only_attribution_leaves_nothing(self):
        self.assertEqual(mps.strip_ai_attribution("Co-Authored-By: Claude <noreply@anthropic.com>\n"), ("", True))


class LabelMatchTests(unittest.TestCase):
    def test_match_ignores_case_and_returns_the_exact_name(self):
        self.assertEqual(mps.match_label_name([{"name": "Bug report"}, {"name": "bug"}], "Bug"), "bug")
        self.assertEqual(mps.match_label_name(["ENHANCEMENT"], "Enhancement"), "ENHANCEMENT")
        self.assertIsNone(mps.match_label_name([{"name": "Bugfix"}], "Bug"))
        self.assertIsNone(mps.match_label_name(None, "Bug"))

    def test_assignee_usernames(self):
        self.assertEqual(mps.mr_assignee_usernames({"assignees": [{"username": "a"}, {"username": "b"}]}), ["a", "b"])
        self.assertEqual(mps.mr_assignee_usernames({"assignees": [], "assignee": {"username": "c"}}), ["c"])
        self.assertEqual(mps.mr_assignee_usernames({}), [])


class SettingsTextTests(unittest.TestCase):
    """U2."""

    def test_bom_and_empty_text(self):
        self.assertEqual(mps.parse_settings_text(chr(0xFEFF) + '{"a": 1}'), {"a": 1})
        self.assertEqual(mps.parse_settings_text(" \r\n"), {})

    def test_not_object_and_invalid_json(self):
        with self.assertRaises(mps.MpsError) as ctx:
            mps.parse_settings_text("[1]")
        self.assertEqual(ctx.exception.code, "settings_not_object")
        with self.assertRaises(mps.MpsError) as ctx:
            mps.parse_settings_text('{\n  "a":')
        self.assertEqual(ctx.exception.code, "settings_invalid_json")
        self.assertEqual((ctx.exception.extra["line"], ctx.exception.extra["column"]), (2, 7))

    def test_render_keeps_vietnamese_and_newline_style(self):
        settings = {"note": "Tiếng Việt", "nested": {"a": [1, 2]}}
        text = mps.render_settings_json(settings, "\r\n")
        self.assertIn('"Tiếng Việt"', text)
        self.assertTrue(text.endswith("}\r\n"))
        self.assertNotIn("\n", text.replace("\r\n", ""))
        self.assertEqual(mps.parse_settings_text(text), settings)
        self.assertTrue(mps.render_settings_json({}, "\n").endswith("\n"))


class PluginVersionTests(unittest.TestCase):
    """U3, U4."""

    def test_parse_and_compare(self):
        self.assertEqual(mps.parse_plugin_version("0.1.10"), (0, 1, 10))
        self.assertEqual(mps.parse_plugin_version("v0.2.0"), (0, 2, 0))
        self.assertTrue(mps.is_newer_version("0.1.10", "0.1.9"))
        self.assertTrue(mps.is_newer_version("0.2.0", "0.1.99"))
        self.assertTrue(mps.is_newer_version("v0.2.0", "0.1.1"))
        self.assertFalse(mps.is_newer_version("0.1.1", "0.1.1"))
        self.assertFalse(mps.is_newer_version("0.1.0", "0.1.1"))
        for bad in ("", "1.x", "1.2", None, 3):
            self.assertIsNone(mps.parse_plugin_version(bad))
            self.assertFalse(mps.is_newer_version(bad, "0.1.0"))
            self.assertFalse(mps.is_newer_version("9.9.9", bad))

    def test_update_blockers(self):
        self.assertEqual(mps.update_blockers({}), [])
        self.assertEqual(mps.update_blockers({"DISABLE_AUTOUPDATER": "1", "DISABLE_UPDATES": "",
                                              "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"}),
                         ["DISABLE_AUTOUPDATER", "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"])
        self.assertEqual(mps.update_blockers({"DISABLE_UPDATES": "1", "FORCE_AUTOUPDATE_PLUGINS": "1"}), [])


class FakeHttpResponse(object):
    def __init__(self, status, body):
        self.status = status
        self.body = body

    def read(self, size=-1):
        self.size = size
        return self.body if size < 0 else self.body[:size]

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


class FetchLatestVersionTests(unittest.TestCase):
    """U4: the GitHub lookup never raises and never sends a token."""

    def setUp(self):
        self.cfg = mps.Config(tempfile.gettempdir(), {"MPS_GITLAB_PAT": "gitlab-token"}, True)

    def fetch(self, outcome, environ=None):
        opener = mock.Mock()
        if isinstance(outcome, BaseException):
            opener.open.side_effect = outcome
        else:
            opener.open.return_value = outcome
        with mock.patch.object(mps.urllib.request, "build_opener", return_value=opener) as build:
            version = mps.fetch_latest_plugin_version(self.cfg, environ if environ is not None else {})
        return version, build, opener

    def test_version_from_manifest(self):
        version, _, opener = self.fetch(FakeHttpResponse(200, b'{"name": "mps-git-flow", "version": "0.2.0"}'))
        self.assertEqual(version, "0.2.0")
        request = opener.open.call_args[0][0]
        self.assertEqual(request.full_url, mps.PLUGIN_MANIFEST_URL)
        self.assertEqual(set(k.lower() for k in request.headers), {"user-agent"})
        self.assertEqual(opener.open.call_args[1]["timeout"], mps.VERSION_CHECK_TIMEOUT_SECONDS)

    def test_failures_give_none(self):
        not_found = mps.urllib.error.HTTPError(mps.PLUGIN_MANIFEST_URL, 404, "Not Found", {}, io.BytesIO(b""))
        for outcome in (socket.timeout("timed out"), not_found, FakeHttpResponse(200, b"<html>"),
                        FakeHttpResponse(200, b'{"name": "x"}'), FakeHttpResponse(200, b'{"version": "1.x"}'),
                        FakeHttpResponse(204, b"")):
            self.assertIsNone(self.fetch(outcome)[0], outcome)

    def test_nonessential_traffic_off_makes_no_request(self):
        version, build, _ = self.fetch(FakeHttpResponse(200, b'{"version": "9.9.9"}'),
                                       environ={"CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"})
        self.assertIsNone(version)
        build.assert_not_called()

    def test_disable_autoupdater_still_checks(self):
        version, _, _ = self.fetch(FakeHttpResponse(200, b'{"version": "9.9.9"}'), environ={"DISABLE_AUTOUPDATER": "1"})
        self.assertEqual(version, "9.9.9")

    def test_body_read_is_bounded(self):
        response = FakeHttpResponse(200, b'{"version": "0.3.0"}')
        self.assertEqual(self.fetch(response)[0], "0.3.0")
        self.assertEqual(response.size, mps.MANIFEST_MAX_BYTES)

    def test_stalled_lookup_returns_within_the_limit(self):
        """A lookup that hangs (e.g. DNS) is abandoned after the timeout; env check is not delayed further."""
        release = threading.Event()
        self.addCleanup(release.set)
        opener = mock.Mock()
        opener.open.side_effect = lambda *args, **kwargs: release.wait(30)
        with mock.patch.object(mps.urllib.request, "build_opener", return_value=opener), \
                mock.patch.object(mps, "VERSION_CHECK_TIMEOUT_SECONDS", 0.2):
            started = time.monotonic()
            version = mps.fetch_latest_plugin_version(self.cfg, {})
            elapsed = time.monotonic() - started
        self.assertIsNone(version)
        self.assertLess(elapsed, STALLED_LOOKUP_MAX_SECONDS)


class IntegrationStatusTests(unittest.TestCase):
    """U5."""

    def test_pinned_marketplace_ref(self):
        def settings(source):
            return {"extraKnownMarketplaces": {"mps-cdci-agents": {"source": source}}}
        self.assertEqual(mps.pinned_marketplace_ref(settings({"source": "github", "repo": "r", "ref": "v0.1.1"})),
                         "v0.1.1")
        for value in (settings({"source": "github", "repo": "r"}), settings({"ref": " "}), settings("x"), None, {},
                      {"extraKnownMarketplaces": {"mps-cdci-agents": None}}):
            self.assertIsNone(mps.pinned_marketplace_ref(value))

    def test_detect_json_indent(self):
        self.assertEqual(mps.detect_json_indent('{\n    "a": 1\n}\n'), 4)
        self.assertEqual(mps.detect_json_indent('{\r\n\t"a": 1\r\n}\r\n'), "\t")
        self.assertEqual(mps.detect_json_indent('{"a": 1}'), mps.DEFAULT_SETTINGS_INDENT)
        self.assertEqual(mps.detect_json_indent(""), mps.DEFAULT_SETTINGS_INDENT)
        self.assertIn('\n\t"a"', mps.render_settings_json({"a": 1}, "\n", "\t"))

    def test_status(self):
        self.assertEqual(mps.project_integration_status({}), "missing")
        self.assertEqual(mps.project_integration_status({"enabledPlugins": {mps.PLUGIN_KEY: False}}), "missing")
        self.assertEqual(mps.project_integration_status({"enabledPlugins": {mps.PLUGIN_KEY: True}}), "integrated")
        self.assertEqual(mps.project_integration_status({"enabledPlugins": [mps.PLUGIN_KEY]}), "missing")


class ReleaseDisciplineTests(unittest.TestCase):
    """U6: every release bumps mps.VERSION and plugin.json together and documents itself."""

    def test_plugin_json_version_matches_script(self):
        manifest = json.loads(_read_bytes(os.path.join(PLUGIN_DIR, ".claude-plugin", "plugin.json")).decode("utf-8"))
        self.assertEqual(manifest["version"], mps.VERSION)

    def test_changelog_has_entry(self):
        changelog = _read_bytes(os.path.join(REPO_ROOT, "CHANGELOG.md")).decode("utf-8")
        self.assertRegex(changelog, r"(?m)^## " + re.escape(mps.VERSION) + r"(\s|$)")

    def test_marketplace_has_no_plugin_version(self):
        marketplace = json.loads(_read_bytes(os.path.join(REPO_ROOT, ".claude-plugin", "marketplace.json"))
                                 .decode("utf-8"))
        entry = [p for p in marketplace["plugins"] if p["name"] == "mps-git-flow"][0]
        self.assertNotIn("version", entry)

    def test_readme_settings_block_matches_project_setup(self):
        readme = _read_bytes(os.path.join(REPO_ROOT, "README.md")).decode("utf-8")
        blocks = [b for b in re.findall(r"```json\n(.*?)```", readme, re.DOTALL) if "extraKnownMarketplaces" in b]
        self.assertEqual(len(blocks), 1)
        self.assertEqual(json.loads(textwrap.dedent(blocks[0])), mps.merge_project_settings({})[0])


class BootstrapFileHygieneTests(unittest.TestCase):
    """U7: encodings and PowerShell 5.1 / POSIX guards that a casual edit could break."""

    def test_ps1_has_bom_and_no_ps6_tokens(self):
        data = _read_bytes(BOOTSTRAP_PS1)
        self.assertTrue(data.startswith(UTF8_BOM))
        text = data.decode("utf-8")
        for token in ("??", "&&", "$IsWindows"):
            self.assertNotIn(token, text)

    def test_sh_is_lf_without_bom(self):
        data = _read_bytes(BOOTSTRAP_SH)
        self.assertNotIn(b"\r", data)
        self.assertFalse(data.startswith(UTF8_BOM))

    def test_no_prompts(self):
        for path in (BOOTSTRAP_PS1, BOOTSTRAP_SH):
            text = _read_bytes(path).decode("utf-8-sig")
            self.assertNotIn("Read-Host", text)
            self.assertIsNone(re.search(r"(^|[\s;&|(])read\s", text, re.MULTILINE), path)


class EnvTemplateTests(unittest.TestCase):
    """R.11.4: the member keys come first and blank; everything else keeps the defaults."""

    def setUp(self):
        self.text = _read_bytes(mps.ENV_TEMPLATE_PATH).decode("utf-8")
        self.values = mps.parse_env(self.text)

    def test_member_keys_first_and_blank(self):
        keys = [m.group(1) for m in (mps._ENV_LINE_RE.match(line.strip()) for line in self.text.splitlines()
                                     if line.strip() and not line.strip().startswith("#")) if m]
        self.assertEqual(keys[:3], list(mps.MEMBER_KEYS))
        for key in mps.MEMBER_KEYS:
            self.assertEqual(self.values[key], "")

    def test_every_other_key_present_with_default(self):
        for key in mps.KNOWN_KEYS:
            self.assertIn(key, self.values)
            if key in mps.DEFAULTS:
                self.assertEqual(self.values[key], mps.DEFAULTS[key])

    def test_template_holds_no_secret_pattern(self):
        self.assertEqual([f for f in mps.scan_text("env.example", self.text) if not f["confirmable"]], [])


class EnvFillGuideTests(unittest.TestCase):
    """R.11.2 / R.11.4."""

    def test_blank_member_keys_in_order_with_links(self):
        guide = mps.env_fill_guide({"MPS_JIRA_PROJECT_KEY": " "}, "https://jira.example/", "https://git.example")
        self.assertEqual([g["key"] for g in guide], list(mps.MEMBER_KEYS))
        links = dict((g["key"], g["link"]) for g in guide)
        self.assertEqual(links["MPS_JIRA_PAT"], "https://jira.example" + mps.JIRA_PAT_PAGE)
        self.assertEqual(links["MPS_GITLAB_PAT"], "https://git.example/-/user_settings/personal_access_tokens"
                                                  "?name=mps-git-flow&scopes=api,write_repository")
        self.assertIsNone(links["MPS_JIRA_PROJECT_KEY"])
        self.assertTrue(all(g["label"] and g["steps"] for g in guide))

    def test_subset_is_ordered_and_tokens_never_copied(self):
        values = {"MPS_JIRA_PAT": "super-secret-jira", "MPS_GITLAB_PAT": "super-secret-gitlab"}
        self.assertEqual([g["key"] for g in mps.env_fill_guide(values, "https://j", "https://g")],
                         ["MPS_JIRA_PROJECT_KEY"])
        guide = mps.env_fill_guide(values, "https://j", "https://g", keys=["MPS_GITLAB_PAT", "MPS_JIRA_PAT"],
                                   token_rejected=True)
        self.assertEqual([g["key"] for g in guide], ["MPS_JIRA_PAT", "MPS_GITLAB_PAT"])
        self.assertTrue(all("hết hạn" in g["steps"][0] for g in guide))
        dumped = json.dumps(guide, ensure_ascii=False)
        self.assertNotIn("super-secret", dumped)

    def test_deleted_default_line_is_restored(self):
        guide = mps.env_fill_guide({}, "https://j", "https://g", keys=["MPS_GITLAB_URL"])
        self.assertEqual(guide[0]["steps"], ["Khôi phục dòng mặc định trong file .env: "
                                             "MPS_GITLAB_URL=https://git-gst.mto.zing.vn"])


def _script_functions(text, names, start, end):
    """Source of the named functions, copied from a bootstrap script (each starts on the line beginning with
    `start % name` and ends at the first following line equal to `end`)."""
    lines = text.splitlines()
    blocks = []
    for name in names:
        first = [i for i, line in enumerate(lines) if line.startswith(start % name)][0]
        last = lines.index(end, first)
        blocks.append("\n".join(lines[first:last + 1]))
    return "\n\n".join(blocks)


def _pipe_close_seconds(command):
    """Seconds until the command's stdout pipe reaches EOF (not just until the command exits), and its output."""
    started = time.monotonic()
    proc = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=BOOTSTRAP_TIMEOUT_SECONDS)
    return time.monotonic() - started, proc.stdout.decode("utf-8", "replace")


def _run_bootstrap(command, env=None):
    proc = subprocess.run(command, capture_output=True, timeout=BOOTSTRAP_TIMEOUT_SECONDS, env=env)
    lines = [line for line in proc.stdout.decode("utf-8").splitlines() if line.strip()]
    return proc.returncode, lines


class BootstrapScriptTests(unittest.TestCase):
    """B1 / B2: detect-only prints one JSON line; on a test machine Python is present."""

    def check_detect_only(self, command, expected_os):
        code, lines = _run_bootstrap(command)
        self.assertEqual(len(lines), 1, lines)
        result = json.loads(lines[0])
        for key in BOOTSTRAP_KEYS:
            self.assertIn(key, result)
        self.assertEqual((result["os"], result["mode"]), (expected_os, "detect"))
        self.assertTrue(result["ok"], result)
        self.assertEqual(code, 0)
        version = subprocess.run([result["python_cmd"], "--version"], capture_output=True, timeout=60)
        self.assertEqual(version.returncode, 0)

    @unittest.skipUnless(sys.platform.startswith("win") and shutil.which("powershell.exe"), "Windows PowerShell only")
    def test_ps1_detect_only(self):
        self.check_detect_only(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", BOOTSTRAP_PS1,
                                "-DetectOnly"], "windows")

    @unittest.skipUnless(sys.platform.startswith("win") and shutil.which("powershell.exe"), "Windows PowerShell only")
    def test_ps1_survives_a_missing_drive_on_path(self):
        """C1: a PATH entry on a drive that does not exist must not turn detection into bootstrap_failed."""
        env = dict(os.environ)
        env["PATH"] = "Q:\\nope;" + env.get("PATH", "")
        code, lines = _run_bootstrap(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                                      BOOTSTRAP_PS1, "-DetectOnly"], env)
        self.assertEqual(len(lines), 1, lines)
        result = json.loads(lines[0])
        self.assertTrue(result["ok"], result)
        self.assertEqual(code, 0)

    @unittest.skipUnless(sys.platform.startswith("win") and shutil.which("powershell.exe"), "Windows PowerShell only")
    def test_ps1_timed_out_installer_does_not_hold_stdout(self):
        """N1: a winget still running after the budget must not keep the agent's stdout pipe open."""
        folder = tempfile.mkdtemp(prefix="mps-ps1-")
        self.addCleanup(shutil.rmtree, folder, True)
        functions = _script_functions(_read_bytes(BOOTSTRAP_PS1).decode("utf-8-sig"),
                                      ("Write-Log", "Invoke-Detached"), "function %s(", "}")
        ping = os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "System32", "PING.EXE")
        harness = os.path.join(folder, "harness.ps1")
        with open(harness, "wb") as handle:
            handle.write(UTF8_BOM + "\r\n".join([
                "$ErrorActionPreference = 'Stop'",
                "$script:LogPath = '%s'" % os.path.join(folder, "install.log"),
                functions,
                "$quick = Invoke-Detached '%s' '-n 1 127.0.0.1' 30000" % ping,
                "$slow = Invoke-Detached '%s' '-n %d 127.0.0.1' 500" % (ping, SLOW_INSTALLER_SECONDS),
                "[Console]::Out.WriteLine('{\"quick\":' + $quick.Code + ',\"slow_timed_out\":' + "
                "([string]$slow.TimedOut).ToLower() + '}')",
                "exit 0", ""]).encode("utf-8"))
        elapsed, out = _pipe_close_seconds(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                                            harness])
        self.assertEqual(json.loads(out.strip()), {"quick": 0, "slow_timed_out": True})
        self.assertLess(elapsed, PIPE_CLOSE_MAX_SECONDS)
        with open(os.path.join(folder, "install.log"), "rb") as handle:
            self.assertIn(b"127.0.0.1", handle.read())

    @unittest.skipUnless(shutil.which("sh"), "needs sh")
    def test_sh_timed_out_installer_does_not_hold_stdout(self):
        """N1: an installer still running after the budget must not keep the agent's stdout pipe open."""
        folder = tempfile.mkdtemp(prefix="mps-sh-")
        self.addCleanup(shutil.rmtree, folder, True)
        functions = _script_functions(_read_bytes(BOOTSTRAP_SH).decode("utf-8"),
                                      ("log", "now_seconds", "remaining_seconds", "run_install"), "%s() {", "}")
        harness = os.path.join(folder, "harness.sh")
        with open(harness, "wb") as handle:
            handle.write("\n".join([
                "LOG_PATH=/dev/null", "INSTALL_BUDGET_SECONDS=1", "MIN_INSTALL_SECONDS=0", functions,
                "START_SECONDS=$(now_seconds)",
                "run_install sleep %d" % SLOW_INSTALLER_SECONDS,
                "printf '{\"status\":\"%s\"}\\n' \"$INSTALL_STATUS\"", "exit 0", ""]).encode("utf-8"))
        elapsed, out = _pipe_close_seconds(["sh", harness])
        self.assertEqual(json.loads(out.strip()), {"status": "timeout"})
        self.assertLess(elapsed, PIPE_CLOSE_MAX_SECONDS)

    @unittest.skipUnless(os.name == "posix" and shutil.which("sh"), "POSIX only")
    def test_sh_detect_only(self):
        self.check_detect_only(["sh", BOOTSTRAP_SH, "--detect-only"],
                               "macos" if sys.platform == "darwin" else "linux")


if __name__ == "__main__":
    unittest.main()
