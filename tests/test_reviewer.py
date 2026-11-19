import unittest

from app.github import InvalidPullRequestUrl, parse_pull_request_url
from app.reviewer import added_lines, review_patch


class ReviewPatchTests(unittest.TestCase):
    def test_added_lines_track_new_file_line_numbers(self) -> None:
        patch = """diff --git a/src/task.py b/src/task.py
new file mode 100644
--- /dev/null
+++ b/src/task.py
@@ -0,0 +1,3 @@
+first = 1
+second = 2
+third = 3
"""

        result = list(added_lines(patch))

        self.assertEqual([(line.path, line.line) for line in result], [
            ("src/task.py", 1),
            ("src/task.py", 2),
            ("src/task.py", 3),
        ])

    def test_reports_unsafe_operations_on_added_lines_only(self) -> None:
        patch = """diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -8,2 +8,3 @@
 existing = eval(value)
+result = eval(user_input)
+subprocess.run(command, shell=True)
 context = 1
"""

        report = review_patch(patch)

        self.assertEqual([finding.line for finding in report.findings], [9, 10])
        self.assertEqual([finding.severity for finding in report.findings], ["high", "high"])
        self.assertEqual(report.lines_reviewed, 2)

    def test_clean_patch_has_no_findings(self) -> None:
        patch = """diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -0,0 +1,1 @@
+total = sum(values)
"""

        report = review_patch(patch)

        self.assertEqual(report.findings, [])
        self.assertEqual(report.files_reviewed, 1)

    def test_detects_formatted_sql_queries(self) -> None:
        patch = """diff --git a/db.py b/db.py
--- a/db.py
+++ b/db.py
@@ -0,0 +1 @@
+cursor.execute(f"SELECT * FROM users WHERE name = '{name}'")
"""

        report = review_patch(patch)

        self.assertEqual(report.findings[0].title, "SQL query interpolates a formatted string")

    def test_accepts_github_pull_request_url(self) -> None:
        self.assertEqual(
            parse_pull_request_url("https://github.com/acme/widget/pull/42"),
            ("acme", "widget", 42),
        )

    def test_rejects_non_github_pull_request_url(self) -> None:
        with self.assertRaises(InvalidPullRequestUrl):
            parse_pull_request_url("https://example.com/acme/widget/pull/42")


if __name__ == "__main__":
    unittest.main()