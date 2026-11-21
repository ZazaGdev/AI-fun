"""The skill, the prompt and the READMEs: the scripts embedded in prompt.md are the real ones and
its check line holds their hashes, no file has a long dash, and every script is Python 3.8."""
import ast
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
SCRIPTS = os.path.join(PROJECT, "skill", "scripts")
FILES = ["disk_cleanup.py", "clean.py", "rules.py", "scan.py", "winsys.py"]
RAW = "https://raw.githubusercontent.com/ZazaGdev/AI-fun/main/disk-cleanup/skill/scripts/"


def read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as f:
        return f.read()


def digest(text):
    """The same normal form as the prompt's check line."""
    norm = "\n".join(l.rstrip() for l in text.replace("\r\n", "\n").strip().split("\n"))
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


class Prompt(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = read(PROJECT, "prompt.md").replace("\r\n", "\n")

    def test_the_embedded_scripts_are_the_real_ones(self):
        blocks = re.findall(r"----- BEGIN FILE (\d): (\S+) -----\n(.*?)\n----- END FILE \1 -----", self.text, re.S)
        self.assertEqual([(int(n), name) for n, name, _ in blocks], list(enumerate(FILES, 1)))
        self.assertEqual(sorted(f for f in os.listdir(SCRIPTS) if f.endswith(".py")), sorted(FILES))
        for _, name, body in blocks:
            self.assertEqual(body, read(SCRIPTS, name).replace("\r\n", "\n").rstrip("\n"), name)

    def test_the_check_line_holds_their_hashes(self):
        line = next(l for l in self.text.splitlines() if l.strip().startswith('python -c "import hashlib'))
        pairs = re.findall(r"\('([\w.]+)','([0-9a-f]{64})'\)", line)
        self.assertEqual(pairs, [(name, digest(read(SCRIPTS, name))) for name in FILES])
        self.assertIn("pathlib.Path.home()/'disk-cleanup'/'tool'", line)

    def test_both_prompts_start_with_the_path_and_stop_after_the_summary(self):
        option1, option2 = self.text.split("## Option 2", 1)
        bodies = re.findall(r"^`````text\n(.*?)\n`````$", option1, re.S | re.M)
        bodies += re.findall(r"^```text\n(.*?)\n```$", option2, re.S | re.M)
        self.assertEqual(len(bodies), 2)
        for body in bodies:
            self.assertTrue(body.startswith("Path to scan: C:\\\n"), body[:40])
            self.assertIn("Then stop. Do not ask whether to remove anything, do not offer to, and do not recommend "
                          "removing any group.", body)
            self.assertIn("only a later reply of mine that names groups or items is", body)
            self.assertIn("without --yes", body)
            self.assertIn("winget install Python.Python.3.13", body)
            self.assertIn("PowerShell does not expand ~ for python", body)
            self.assertIn("scan '<path>'", body)
            self.assertIn("clean '<report data>'", body)
            self.assertIn("comma-separated", body)
            self.assertEqual(body.count("10-minute timeout"), 2)
            self.assertIn("Dropbox's info.json and a few Windows registry keys", body)  # what else it reads

    def test_the_check_line_says_ok_for_copies_of_the_scripts(self):
        line = next(l.strip() for l in self.text.splitlines() if l.strip().startswith('python -c "import hashlib'))
        home = tempfile.mkdtemp(prefix="disk-cleanup-test-")
        try:
            tool = os.path.join(home, "disk-cleanup", "tool")
            os.makedirs(tool)
            for name in FILES:  # written back with Windows line ends, as an editor may
                with open(os.path.join(tool, name), "w", encoding="utf-8", newline="\r\n") as f:
                    f.write(read(SCRIPTS, name).replace("\r\n", "\n"))
            env = dict(os.environ, USERPROFILE=home, HOME=home)
            out = subprocess.run([sys.executable, "-c", line[len('python -c "'):-1]], capture_output=True, text=True,
                                 env=env, timeout=120)
            self.assertEqual(out.stdout.split(), [w for name in FILES for w in (name, "OK")], out.stderr)
            with open(os.path.join(tool, "rules.py"), "a", encoding="utf-8") as f:
                f.write("x = 1\n")
            out = subprocess.run([sys.executable, "-c", line[len('python -c "'):-1]], capture_output=True, text=True,
                                 env=env, timeout=120)
            self.assertIn("rules.py MISMATCH", out.stdout)
        finally:
            shutil.rmtree(home)

    def test_option_2_downloads_the_five_scripts(self):
        option2 = self.text.split("## Option 2", 1)[1]
        for name in FILES:
            self.assertIn(RAW + name, option2)
        self.assertIn("urllib", option2)
        self.assertIn("ask me to confirm", option2)


class Skill(unittest.TestCase):
    def test_frontmatter_and_steps(self):
        text = read(PROJECT, "skill", "SKILL.md")
        front = re.match(r"---\n(.*?)\n---\n", text, re.S).group(1)
        self.assertIn("name: disk-cleanup\n", front + "\n")
        description = re.search(r"^description: (.+)$", front, re.M).group(1)
        for words in ("free up disk space", "what they can delete", "/disk-cleanup", "removes nothing by itself"):
            self.assertIn(words, description)
        self.assertIn("4. Stop there. Do not ask whether to remove anything", text)
        self.assertIn("is never a request\n  to remove anything", text)
        self.assertIn("$DC scan '<path>'", text)  # single quotes: Git Bash never ends a "C:\"
        self.assertIn("$DC clean '<report data>'", text)
        self.assertIn("without `--yes`", text)
        self.assertIn("comma-separated", text)
        self.assertEqual(text.count("10-minute timeout"), 2)  # the scan and the clean


class Readme(unittest.TestCase):
    def test_readme(self):
        text = read(PROJECT, "README.md")
        self.assertIn("It removes nothing unless you ask.", text)
        self.assertIn("## If you want something removed", text)
        self.assertIn("Nothing was removed. This scan only reads.", text)
        self.assertIn("Dropbox's `info.json` and a few Windows registry keys", text)  # what else it reads
        self.assertEqual(text.lower().count("empty folders"), 1)  # only the line saying they are not listed
        self.assertNotRegex(text, r"[A-Za-z]:\\Users\\(?!you\\)\w")  # only made-up user folders

    def test_the_sample_summary_is_one_the_scan_could_print(self):
        text = read(PROJECT, "README.md")
        sample = text.split("## A sample summary", 1)[1].split("```")[1]
        root = re.search(r"Scan of (\S+) finished", sample).group(1)
        listed = sample.split("Not offered", 1)[0]
        for path in re.findall(r"[A-Z]:\\\S*", listed.split("finished", 1)[1]):
            self.assertTrue(path.lower().startswith(root.lower()), path)  # nothing outside the scanned folder
        levels = re.findall(r"^ *(\d+)\. .*?([\d.]+ [KMGT]?B|\d+ bytes) .*?(Safe|Easy to get back|Your call)",
                            sample, re.M)
        self.assertEqual([int(n) for n, _, _ in levels], list(range(1, len(levels) + 1)))
        order = ["Safe", "Easy to get back", "Your call"]
        units = {"bytes": 1, "KB": 1024, "MB": 1024 ** 2, "GB": 1024 ** 3, "TB": 1024 ** 4}
        sizes = [(order.index(level), -float(s.split()[0]) * units[s.split()[1]]) for _, s, level in levels]
        self.assertEqual(sizes, sorted(sizes))  # by level, then the larger group first
        numbers = [int(n) for n in re.findall(r"#(\d+)", sample)]
        self.assertEqual(numbers, sorted(numbers))
        self.assertGreater(numbers[0], sum(int(c.replace(",", "")) for c in re.findall(r"([\d,]+) items", sample)[:-1]))

    def test_root_readme_row(self):
        text = read(os.path.dirname(PROJECT), "README.md")
        self.assertIn("| [disk-cleanup](disk-cleanup/) | ", text)


class EveryFile(unittest.TestCase):
    def test_no_long_dashes(self):
        for top, dirs, files in os.walk(PROJECT):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for name in files:
                with open(os.path.join(top, name), encoding="utf-8") as f:
                    text = f.read()
                for dash in ("\u2014", "\u2013"):
                    self.assertNotIn(dash, text, os.path.join(top, name))

    def test_every_script_is_python_3_8(self):
        for name in FILES:
            ast.parse(read(SCRIPTS, name), filename=name, feature_version=(3, 8))
        for name in os.listdir(HERE):
            if name.endswith(".py"):
                ast.parse(read(HERE, name), filename=name, feature_version=(3, 8))


if __name__ == "__main__":
    unittest.main()
