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


GIT = shutil.which("git")
LARGE_FILE_BYTES = mps.MAX_FILE_BYTES + 1024


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
        self.assertEqual(self.mps("git", "commit", "--message=feat: MPS-1 x", "--all")["error"], "unmerged_files")
        self.assertEqual(self.head(), before)
        preflight = self.mps("git", "preflight", "--base", "develop")
        self.assertIn("unmerged_files", [b["code"] for b in preflight["blockers"]])

    # -- C2 --------------------------------------------------------------

    def test_commit_never_includes_env_files_or_secrets(self):
        self.prepare("feature/MPS-1-x", "MPS-1")
        self.write("cfg/app.ini", "a=1\n")
        self.write("cfg/.env.local", "MPS_GITLAB_PAT=glpat-abcdefghijklmnop\n")
        before = self.head()
        for files in (["cfg"], ["."]):
            result = self.mps("git", "commit", "--message=feat: MPS-1 x", "--files", *files)
            self.assertEqual(result["error"], "env_file")
            self.assertEqual(result["files"], ["cfg/.env.local"])
            self.assertEqual(self.head(), before)
            self.assertEqual(self.git("diff", "--cached", "--name-only").strip(), "")
            self.assertTrue(os.path.isfile(os.path.join(self.repo, "cfg", ".env.local")))
        self.write("cfg/token.py", "GITLAB = 'glpat-abcdefghijklmnop'\n")
        result = self.mps("git", "commit", "--message=feat: MPS-1 x", "--files", "cfg/token.py")
        self.assertEqual(result["error"], "secret_detected")
        self.assertEqual(self.head(), before)
        ok = self.mps("git", "commit", "--message=feat: MPS-1 x", "--files", "cfg/app.ini")
        self.assertEqual(ok["files"], ["A\tcfg/app.ini"])

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
        self.mps("git", "commit", "--message=fix: MPS-2 x", "--all")
        result = self.prepare("bugfix/MPS-2-x", "MPS-2", "release/1.0")
        self.assertEqual(result["error"], "branch_base_mismatch")
        self.assertEqual([c["subject"] for c in result["foreign_commits"]], ["feat: MPS-5 unreleased feature"])
        self.git("switch", "-q", "develop")
        self.assertEqual(self.prepare("bugfix/MPS-2-x", "MPS-2", "release/1.0")["error"], "branch_base_mismatch")
        self.assertEqual(self.git("branch", "--show-current").strip(), "develop")
        same = self.prepare("bugfix/MPS-2-x", "MPS-2")
        self.assertEqual(same["action"], "switched_existing")

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
        committed = self.mps("git", "commit", "--message=feat: MPS-4 Đổi tên", "--files", "renamed.txt")
        self.assertEqual(committed["files"], ["R100\tapp.txt\trenamed.txt"])
        self.assertEqual(self.git("log", "-1", "--format=%s").strip(), "feat: MPS-4 Đổi tên")
        self.assertEqual(self.git("status", "--porcelain").strip(), "")
        self.mps("git", "push", "--branch", "feature/MPS-4-z", "--base", "develop")
        self.assertEqual(self.mps("git", "commit", "--message=feat: MPS-4 again", "--all")["error"],
                         "nothing_to_commit")
        self.assertEqual(self.prepare("feature/MPS-4-z", "MPS-4")["action"], "already_on_branch")
        self.assertTrue(self.mps("git", "push", "--branch", "feature/MPS-4-z", "--base", "develop")["ok"])


if __name__ == "__main__":
    unittest.main()
