"""Every check is proven on the real mistake it was written for, rebuilt as a tiny repo, and on the fixed version.
Run: python3 -m unittest discover -s tests   (no skips allowed: a skipped test counts as a failure in tools/test)"""
import http.server, json, os, subprocess, tempfile, threading, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.path.join(ROOT, "bin", "agent-checks")
ME = ("Helvio Pedreschi", "helvio88@gmail.com")


class Repo:
    def __init__(self):
        self.dir = tempfile.mkdtemp()
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(("GIT_", "GITHUB_", "AGENT_CHECKS"))}
        self.env["HOME"] = self.dir
        self.git("init", "-q", "-b", "main")

    def git(self, *a, who=ME):
        env = dict(self.env, GIT_AUTHOR_NAME=who[0], GIT_AUTHOR_EMAIL=who[1], GIT_COMMITTER_NAME=who[0], GIT_COMMITTER_EMAIL=who[1])
        r = subprocess.run(["git", *a], cwd=self.dir, env=env, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        return r.stdout.strip()

    def commit(self, files, msg="change", who=ME):
        for p, body in files.items():
            full = os.path.join(self.dir, p)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w", encoding="utf-8") as f:
                f.write(body)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", msg, who=who)
        return self.git("rev-parse", "HEAD")

    def run(self, *a, env=None):
        r = subprocess.run(["python3", BIN, *a], cwd=self.dir, env=dict(self.env, **(env or {})), capture_output=True, text=True)
        return r.returncode, r.stdout + r.stderr


class Identity(unittest.TestCase):
    def test_agent_guessed_identity_is_refused_and_named(self):
        r = Repo(); base = r.commit({"a": "1"})
        r.commit({"a": "2"}, who=("Cursor Agent", "cursoragent@cursor.com"))
        r.commit({"a": "3"}, who=("root", "root@runner.heart-of-gold"))
        code, out = r.run("identity", f"{base}..HEAD")
        self.assertEqual(code, 1); self.assertIn("Cursor Agent", out); self.assertIn("root@runner", out); self.assertIn("Fix:", out)

    def test_work_email_is_refused(self):
        r = Repo(); base = r.commit({"a": "1"})
        r.commit({"a": "2"}, who=("Helvio Pedreschi", "helvio@work.example.com"))
        self.assertEqual(r.run("identity", f"{base}..HEAD")[0], 1)

    def test_the_one_identity_and_bots_pass(self):
        r = Repo(); base = r.commit({"a": "1"})
        r.commit({"a": "2"})
        r.commit({"a": "3"}, who=("dependabot[bot]", "49699333+dependabot[bot]@users.noreply.github.com"))
        self.assertEqual(r.run("identity", f"{base}..HEAD")[0], 0)

    def test_listed_outside_contributor_passes(self):
        r = Repo(); base = r.commit({"a": "1"})
        r.commit({".agent-checks.toml": '[identity]\nallow-emails = ["x@example.com"]\n'})
        r.commit({"a": "2"}, who=("Sam", "x@example.com"))
        self.assertEqual(r.run("identity", f"{base}..HEAD")[0], 0)


class Voice(unittest.TestCase):
    def test_em_dash_fails_with_line_number_and_fix(self):
        r = Repo(); r.commit({"README.md": "ok\nthis \u2014 that\n"})
        code, out = r.run("voice", "tree")
        self.assertEqual(code, 1); self.assertIn("README.md:2", out); self.assertIn("use a period", out)

    def test_diff_mode_only_sees_added_lines(self):
        r = Repo(); base = r.commit({"README.md": "old \u2014 text\n"})
        r.commit({"README.md": "old \u2014 text\nnew line\n"})
        self.assertEqual(r.run("voice", "diff", base, "HEAD")[0], 0)
        r.commit({"README.md": "old \u2014 text\nnew line\nbad \u2014 line\n"})
        self.assertEqual(r.run("voice", "diff", base, "HEAD")[0], 1)

    def test_exceptions_need_reason_and_unexpired_date(self):
        r = Repo(); r.commit({"a.md": "x \u2014 y voice-ok: quoting a user until 2999-01-01\n"})
        self.assertEqual(r.run("voice", "tree")[0], 0)
        r.commit({"a.md": "x \u2014 y voice-ok: quoting a user until 2001-01-01\n"})
        self.assertEqual(r.run("voice", "tree")[0], 1)
        r.commit({"a.md": "x \u2014 y voice-ok: until 2999-01-01\n"})
        self.assertEqual(r.run("voice", "tree")[0], 1)

    def test_repo_words_come_from_config(self):
        r = Repo()
        r.commit({".agent-checks.toml": '[[voice.extra]]\npattern = "(?i)the host"\nwhy = "jargon"\nfix = "say the computer"\n', "a.md": "talk to the host now\n"})
        code, out = r.run("voice", "tree")
        self.assertEqual(code, 1); self.assertIn("say the computer", out)

    def test_a_repo_word_can_be_limited_to_some_files(self):
        r = Repo()
        r.commit({".agent-checks.toml": '[[voice.extra]]\npattern = "pkexec"\nwhy = "terminal text in the UI"\nfix = "describe the step"\npaths = "\\\\.qml$"\n',
                  "docs/notes.md": "uses pkexec\n", "ui/a.qml": "text: 'run pkexec'\n"})
        code, out = r.run("voice", "tree")
        self.assertEqual(code, 1); self.assertIn("ui/a.qml:1", out); self.assertNotIn("docs/notes.md", out)

    def test_instruction_files_may_name_the_banned_words(self):
        r = Repo(); r.commit({"AGENTS.md": "Never use an em dash (\u2014).\n"})
        self.assertEqual(r.run("voice", "tree")[0], 0)


class Docs(unittest.TestCase):
    CFG = '[docs]\nuser-facing = "^(src)/"\nrequire = ["CHANGELOG.md", "README.md"]\n'

    def test_user_facing_change_without_docs_fails(self):
        r = Repo(); base = r.commit({".agent-checks.toml": self.CFG, "README.md": "r", "CHANGELOG.md": "c"})
        r.commit({"src/app.py": "x"})
        code, out = r.run("docs", base, "HEAD")
        self.assertEqual(code, 1); self.assertIn("CHANGELOG.md", out); self.assertIn("Docs: skip", out)

    def test_docs_in_a_later_commit_of_the_same_range_pass(self):
        r = Repo(); base = r.commit({".agent-checks.toml": self.CFG, "README.md": "r", "CHANGELOG.md": "c"})
        r.commit({"src/app.py": "x"}); r.commit({"README.md": "r2", "CHANGELOG.md": "c2"})
        self.assertEqual(r.run("docs", base, "HEAD")[0], 0)

    def test_skip_line_and_non_user_facing_pass(self):
        r = Repo(); base = r.commit({".agent-checks.toml": self.CFG, "README.md": "r", "CHANGELOG.md": "c"})
        r.commit({"src/app.py": "x"}, msg="refactor\n\nDocs: skip internal rename only")
        self.assertEqual(r.run("docs", base, "HEAD")[0], 0)
        r2 = Repo(); b2 = r2.commit({".agent-checks.toml": self.CFG, "README.md": "r"})
        r2.commit({"tools/x.sh": "x"})
        self.assertEqual(r2.run("docs", b2, "HEAD")[0], 0)


class ModelIds(unittest.TestCase):
    def test_default_model_and_literal_ids_fail(self):
        r = Repo(); r.commit({"app/settings.py": 'DEFAULT_MODEL = "grok-4.7"\n', "app/b.py": 'x = "gpt-5-mini"\n'})
        code, out = r.run("model-ids")
        self.assertEqual(code, 1); self.assertIn("settings.py:1", out); self.assertIn("b.py:1", out)

    def test_tests_comments_and_dated_exceptions_pass(self):
        r = Repo()
        r.commit({"tests/test_a.py": 'x = "grok-4.7"\n', "app/a.py": '# grok-4 was removed\ny = "claude-3-old"  # model-id-ok: matches stored legacy values until 2999-01-01\n'})
        self.assertEqual(r.run("model-ids")[0], 0)


class Private(unittest.TestCase):
    def test_word_from_env_is_found_and_allowlist_needs_a_reason(self):
        r = Repo(); r.commit({"tests/t.py": 'friend = "Alice"\n'})
        code, out = r.run("private", env={"AGENT_CHECKS_PRIVATE_WORDS": "Alice\nSmith"})
        self.assertEqual(code, 1); self.assertIn("tests/t.py:1", out); self.assertNotIn("Alice", out)
        r.commit({".agent-checks.toml": '[[private.allow]]\npath = "^tests/t.py$"\nwhy = "fixture"\n'})
        self.assertEqual(r.run("private", env={"AGENT_CHECKS_PRIVATE_WORDS": "Alice"})[0], 0)

    def test_hashed_names_and_plain_patterns_work_without_a_secret_list(self):
        r = Repo(); h = r.run("private-hash", "Alice")[1].strip()
        r.commit({".agent-checks.toml": f'[private]\nhashes = ["{h}"]\npatterns = ["my\\\\.house"]\n', "tests/t.py": 'x = "alice"\n', "a.md": "see my.house\n"})
        code, out = r.run("private")
        self.assertEqual(code, 1); self.assertIn("tests/t.py:1", out); self.assertIn("a.md:1", out); self.assertNotIn("rthur", out)

    def test_no_list_passes_unless_required(self):
        r = Repo(); r.commit({"a.txt": "Alice"})
        self.assertEqual(r.run("private")[0], 0)
        r.commit({".agent-checks.toml": "[private]\nrequired = true\n"})
        self.assertEqual(r.run("private")[0], 1)


class ReleaseVersion(unittest.TestCase):
    CFG = ('[[release.version]]\nfile = "internal/config/config.go"\npattern = \'const Version = "([^"]+)"\'\n'
           '[[release.version]]\nfile = "server.json"\npattern = \'(?m)^  "version": "([^"]+)"\'\n'
           '[[release.version]]\nfile = "server.json"\npattern = \'"identifier": "[^"]*:([0-9][^"]*?)(?:-slim)?"\'\n')

    def files(self, v):
        return {".agent-checks.toml": self.CFG, "internal/config/config.go": f'const Version = "{v}"\n',
                "server.json": '{\n  "version": "%s",\n  "packages": [{"identifier": "ghcr.io/x/y:%s"}, {"identifier": "ghcr.io/x/y:%s-slim"}]\n}\n' % (v, v, v)}

    def test_skgate_v0_26_0_shape_fails_before_publish(self):
        r = Repo(); r.commit(self.files("0.25.3"))
        code, out = r.run("release-version", "v0.26.0")
        self.assertEqual(code, 1); self.assertIn("config.go says 0.25.3", out); self.assertIn("server.json says 0.25.3", out)

    def test_agreeing_files_pass_and_a_stale_identifier_fails(self):
        r = Repo(); r.commit(self.files("0.27.0"))
        self.assertEqual(r.run("release-version", "v0.27.0")[0], 0)
        f = self.files("0.27.0"); f["server.json"] = f["server.json"].replace("y:0.27.0-slim", "y:0.26.1-slim")
        r.commit(f)
        code, out = r.run("release-version", "v0.27.0")
        self.assertEqual(code, 1); self.assertIn("0.26.1", out)

    def test_a_pattern_that_matches_nothing_is_an_error_not_a_pass(self):
        r = Repo(); r.commit({".agent-checks.toml": '[[release.version]]\nfile = "a.txt"\npattern = \'v=(.*)\'\n', "a.txt": "nothing"})
        self.assertEqual(r.run("release-version", "v1.0.0")[0], 1)


class ReleaseAssets(unittest.TestCase):
    def serve(self, pages):
        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(s):
                body = pages.get(s.path)
                s.send_response(200 if body else 404); s.end_headers()
                s.wfile.write(json.dumps(body or {}).encode())
            def log_message(s, *a): pass
        srv = http.server.HTTPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        return {"AGENT_CHECKS_API": f"http://127.0.0.1:{srv.server_port}", "AGENT_CHECKS_TRIES": "1"}

    def test_ha_supergrok_0_6_0_release_without_zip_fails(self):
        env = self.serve({"/repos/o/r/releases/tags/0.6.0": {"assets": []}, "/repos/o/r/releases/tags/0.6.1": {"assets": [{"name": "supergrok.zip"}]}})
        r = Repo()
        code, out = r.run("release-assets", "o/r", "0.6.0", "supergrok.zip", env=env)
        self.assertEqual(code, 1); self.assertIn("supergrok.zip", out)
        self.assertEqual(r.run("release-assets", "o/r", "0.6.1", "supergrok.zip", env=env)[0], 0)

    def test_missing_release_page_fails(self):
        env = self.serve({}); code, out = Repo().run("release-assets", "o/r", "v0.5.0", "x.zip", env=env)
        self.assertEqual(code, 1); self.assertIn("no GitHub Release", out)


class NightlyAlert(unittest.TestCase):
    def test_failure_opens_one_issue_then_comments_and_recovery_closes_it(self):
        calls, issues = [], []

        class H(http.server.BaseHTTPRequestHandler):
            def reply(s, obj, code=200):
                s.send_response(code); s.end_headers(); s.wfile.write(json.dumps(obj).encode())
            def body(s):
                n = int(s.headers.get("Content-Length", 0)); return json.loads(s.rfile.read(n) or b"{}")
            def do_GET(s): s.reply(list(issues))
            def do_POST(s):
                calls.append(("POST", s.path)); b = s.body()
                if s.path.endswith("/issues"): issues.append({"number": 7, "title": b["title"]})
                s.reply({})
            def do_PATCH(s): calls.append(("PATCH", s.path)); issues.clear(); s.reply({})
            def log_message(s, *a): pass
        srv = http.server.HTTPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        env = {"AGENT_CHECKS_API": f"http://127.0.0.1:{srv.server_port}", "GITHUB_TOKEN": "t", "GITHUB_REPOSITORY": "o/r", "GITHUB_RUN_ID": "9"}
        r = Repo()
        self.assertEqual(r.run("nightly-alert", "fail", env=env)[0], 0)
        self.assertEqual(r.run("nightly-alert", "fail", env=env)[0], 0)
        self.assertEqual(calls, [("POST", "/repos/o/r/issues"), ("POST", "/repos/o/r/issues/7/comments")])
        self.assertEqual(r.run("nightly-alert", "ok", env=env)[0], 0)
        self.assertEqual(calls[-1], ("PATCH", "/repos/o/r/issues/7"))


class NoSkips(unittest.TestCase):
    def test_a_skipped_test_fails_even_though_the_command_passes(self):
        r = Repo()
        code, out = r.run("no-skips", "--", "sh", "-c", "echo '--- SKIP: TestFocusRingsInBrowser'; exit 0")
        self.assertEqual(code, 1); self.assertIn("did not run", out)
        self.assertEqual(r.run("no-skips", "--", "sh", "-c", "echo '12 passed, 2 skipped in 1s'")[0], 1)

    def test_clean_run_passes_and_failure_code_is_kept(self):
        r = Repo()
        self.assertEqual(r.run("no-skips", "--", "sh", "-c", "echo '12 passed'")[0], 0)
        self.assertEqual(r.run("no-skips", "--", "sh", "-c", "exit 3")[0], 3)

    def test_hide_keeps_the_output_short_but_still_counts_skips(self):
        code, out = Repo().run("no-skips", "--hide", "^ok ", "--", "sh", "-c", "echo 'ok one'; echo '--- SKIP: TestX'")
        self.assertEqual(code, 1); self.assertNotIn("ok one", out)

    def test_explicit_escape_hatch(self):
        self.assertEqual(Repo().run("no-skips", "--", "sh", "-c", "echo '1 skipped'", env={"AGENT_CHECKS_ALLOW_SKIP": "1"})[0], 0)


class Workflows(unittest.TestCase):
    BAD = "name: n\non: push\njobs:\n  j:\n    if: ${{ secrets.X != '' }}\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo hi\n"
    GOOD = "name: n\non: push\njobs:\n  j:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo hi\n"

    def test_ha_supergrok_oauth_smoke_mistake_is_caught(self):
        r = Repo(); r.commit({".github/workflows/w.yml": self.BAD})
        code, out = r.run("actionlint")
        self.assertNotEqual(code, 0); self.assertIn('"secrets" is not allowed here', out)
        r.commit({".github/workflows/w.yml": self.GOOD})
        self.assertEqual(r.run("actionlint")[0], 0)


FIXTURES = os.path.join(ROOT, "tests", "fixtures", "workflow-permissions")


def fixture_flows(kind):
    """The real v0.5.5 release workflow pair of a shipped app (names made neutral), as a repo's .github/workflows files."""
    out = {}
    for name in os.listdir(os.path.join(FIXTURES, kind)):
        with open(os.path.join(FIXTURES, kind, name), encoding="utf-8") as f:
            out[f".github/workflows/{name}"] = f.read()
    return out


CALLEE = "name: ci\non:\n  workflow_call:\njobs:\n  alert:\n    runs-on: ubuntu-latest\n    permissions:\n      issues: write\n    steps:\n      - run: echo hi\n"


def caller(extra="", top="permissions:\n  contents: write\n"):
    return f"name: rel\non:\n  push:\n{top}jobs:\n  test:\n    uses: ./.github/workflows/ci.yml\n{extra}"


class WorkflowPermissions(unittest.TestCase):
    def test_the_release_that_never_started_is_caught_and_named(self):
        r = Repo(); r.commit(fixture_flows("failing"))
        code, out = r.run("workflow-permissions")
        self.assertEqual(code, 1)
        for word in (".github/workflows/release.yml", "job 'test'", ".github/workflows/ci.yml", "job 'alert'", "issues: write", "startup_failure", "Fix:"):
            self.assertIn(word, out)
        self.assertEqual(out.count("startup_failure"), 1)  # one finding for the one broken call

    def test_actionlint_does_not_see_it(self):
        r = Repo(); r.commit(fixture_flows("failing"))
        self.assertEqual(r.run("actionlint")[0], 0)

    def test_the_fixed_release_passes(self):
        r = Repo(); r.commit(fixture_flows("fixed"))
        self.assertEqual(r.run("workflow-permissions")[0], 0)

    def test_it_runs_with_the_other_checks_in_local_and_ci(self):
        r = Repo(); r.commit(fixture_flows("failing"))
        code, out = r.run("local", "HEAD")
        self.assertEqual(code, 1); self.assertIn("FAIL workflow permissions", out)
        r.commit(fixture_flows("fixed"))
        self.assertIn("ok   workflow permissions", r.run("local", "HEAD")[1])

    def test_ways_to_hold_the_permission(self):
        for label, files in {
            "job block": {"rel.yml": caller("    permissions:\n      issues: write\n"), "ci.yml": CALLEE},
            "flow block": {"rel.yml": caller("    permissions: { issues: write, contents: read }\n"), "ci.yml": CALLEE},
            "workflow level": {"rel.yml": caller(top="permissions:\n  issues: write\n"), "ci.yml": CALLEE},
            "write-all": {"rel.yml": caller(top="permissions: write-all\n"), "ci.yml": CALLEE},
            "callee asks only read": {"rel.yml": caller(top="permissions:\n  issues: read\n"), "ci.yml": CALLEE.replace("issues: write", "issues: read")},
            "callee sets nothing": {"rel.yml": caller(), "ci.yml": CALLEE.replace("    permissions:\n      issues: write\n", "")},
            "other repo's workflow": {"rel.yml": caller().replace("./.github/workflows/ci.yml", "acme/shared/.github/workflows/ci.yml@v1")},
        }.items():
            with self.subTest(label):
                r = Repo(); r.commit({f".github/workflows/{n}": b for n, b in files.items()})
                code, out = r.run("workflow-permissions"); self.assertEqual(code, 0, out)

    def test_ways_to_miss_it(self):
        for label, files in {
            "write-all in the callee": {"rel.yml": caller(), "ci.yml": CALLEE.replace("    permissions:\n      issues: write\n", "").replace("jobs:", "permissions: write-all\njobs:")},
            "caller holds read": {"rel.yml": caller("    permissions:\n      issues: read\n"), "ci.yml": CALLEE},
            "caller holds nothing": {"rel.yml": caller("    permissions: {}\n"), "ci.yml": CALLEE},
            "nothing set anywhere on the caller": {"rel.yml": caller(top=""), "ci.yml": CALLEE},
            "two levels down": {"rel.yml": caller("    permissions:\n      contents: read\n"),
                                "ci.yml": "name: ci\non:\n  workflow_call:\njobs:\n  inner:\n    uses: ./.github/workflows/leaf.yml\n    permissions:\n      contents: read\n",
                                "leaf.yml": CALLEE.replace("issues: write", "pages: write")},
        }.items():
            with self.subTest(label):
                r = Repo(); r.commit({f".github/workflows/{n}": b for n, b in files.items()})
                code, out = r.run("workflow-permissions"); self.assertEqual(code, 1, out)

    def test_the_repo_default_can_be_declared(self):
        files = {".github/workflows/rel.yml": caller(top=""), ".github/workflows/ci.yml": CALLEE.replace("issues: write", "issues: read")}
        r = Repo(); r.commit(dict(files, **{".agent-checks.toml": '[workflow-permissions]\ndefault = "write"\n'}))
        self.assertEqual(r.run("workflow-permissions")[0], 0)
        r.commit({".agent-checks.toml": '[workflow-permissions]\ndefault = "maybe"\n'})
        self.assertEqual(r.run("workflow-permissions")[0], 2)

    def test_text_that_looks_like_a_key_is_not_one(self):
        text = caller("    permissions:\n      issues: write\n").replace("on:\n", "on:\n  workflow_dispatch:\n")
        other = "name: o\non: push\njobs:\n  a:\n    runs-on: ubuntu-latest\n    steps:\n      - name: x\n        run: |\n          echo 'permissions:'\n          echo 'uses: ./.github/workflows/ci.yml'\n      - uses: actions/checkout@v7\n"
        r = Repo(); r.commit({".github/workflows/rel.yml": text, ".github/workflows/ci.yml": CALLEE, ".github/workflows/o.yml": other})
        self.assertEqual(r.run("workflow-permissions")[0], 0)

    def test_what_it_cannot_read_is_reported_not_passed(self):
        r = Repo(); r.commit({".github/workflows/rel.yml": caller("    permissions:\n      issues: sometimes\n"), ".github/workflows/ci.yml": CALLEE})
        code, out = r.run("workflow-permissions")
        self.assertEqual(code, 1); self.assertIn("sometimes", out)

    def test_a_repo_without_workflows_passes(self):
        r = Repo(); r.commit({"a": "1"})
        self.assertEqual(r.run("workflow-permissions")[0], 0)


class Vendored(unittest.TestCase):
    def test_vendored_copy_verifies_and_a_hand_edit_is_caught(self):
        # tools/vendor always clones its source (GitHub by default); the test points it at a local clone of HEAD
        src = tempfile.mkdtemp()
        subprocess.run(["git", "clone", "-q", ROOT, src], check=True, capture_output=True)
        r = Repo(); r.commit({"README.md": "hi"})
        env = dict(os.environ, HOME=r.dir, AGENT_CHECKS_SOURCE=src)
        out = subprocess.run([os.path.join(ROOT, "tools", "vendor"), r.dir], capture_output=True, text=True, env=env)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(open(os.path.join(r.dir, ".agent-checks", "SOURCE")).read().strip(), src)
        self.assertEqual(open(os.path.join(r.dir, ".agent-checks", "REF")).read().strip(), subprocess.run(["git", "-C", src, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip())
        vendored = os.path.join(r.dir, ".agent-checks", "bin", "agent-checks")
        ok = subprocess.run(["python3", vendored, "verify"], cwd=r.dir, capture_output=True, text=True)
        self.assertEqual(ok.returncode, 0, ok.stdout)
        with open(os.path.join(r.dir, ".agent-checks", "checks", "voice.py"), "a") as f:
            f.write("# sneaky\n")
        bad = subprocess.run(["python3", vendored, "verify"], cwd=r.dir, capture_output=True, text=True)
        self.assertEqual(bad.returncode, 1); self.assertIn("voice.py was edited by hand", bad.stdout); self.assertIn(src, bad.stdout)

    def test_vendored_files_are_never_scanned_by_the_other_checks(self):
        r = Repo(); r.commit({".agent-checks/checks/voice.py": "BANNED = '\u2014'", ".agent-checks/x.md": "bad \u2014 text"})
        self.assertEqual(r.run("voice", "tree")[0], 0)


class Ci(unittest.TestCase):
    def test_pull_request_event_runs_range_checks(self):
        r = Repo(); base = r.commit({"README.md": "ok"})
        head = r.commit({"README.md": "ok \u2014 no"}, who=("Cursor Agent", "cursoragent@cursor.com"))
        ev = os.path.join(r.dir, "..", "ev%d.json" % os.getpid())
        with open(ev, "w") as f:
            json.dump({"pull_request": {"base": {"sha": base}, "head": {"sha": head}}}, f)
        code, out = r.run("ci", env={"GITHUB_EVENT_NAME": "pull_request", "GITHUB_EVENT_PATH": ev})
        self.assertEqual(code, 1); self.assertIn("FAIL identity", out); self.assertIn("FAIL voice", out)

    def test_new_branch_push_is_checked_against_the_default_branch(self):
        r = Repo(); r.commit({"README.md": "ok"})
        r.git("update-ref", "refs/remotes/origin/main", "HEAD")
        r.git("checkout", "-q", "-b", "cook/x")
        head = r.commit({"a.txt": "x"}, who=("Cursor Agent", "cursoragent@cursor.com"))
        ev = os.path.join(r.dir, "..", "ev2_%d.json" % os.getpid())
        with open(ev, "w") as f:
            json.dump({"ref": "refs/heads/cook/x", "before": "0" * 40, "after": head, "repository": {"default_branch": "main"}}, f)
        code, out = r.run("ci", env={"GITHUB_EVENT_NAME": "push", "GITHUB_EVENT_PATH": ev})
        self.assertEqual(code, 1); self.assertIn("FAIL identity", out)


if __name__ == "__main__":
    unittest.main()
