import csv
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from .mailtester import (
    _read_valid_emails,
    verify_candidates,
    verify_leads_early_stop,
    verify_single_email_api,
)


class MailTesterParsingTests(SimpleTestCase):
    def test_reads_only_valid_email_results(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output.csv"
            with output.open("w", newline="", encoding="utf-8") as file:
                writer = csv.DictWriter(file, fieldnames=["email", "status"])
                writer.writeheader()
                writer.writerows([
                    {"email": "person@example.com", "status": "Valid"},
                    {"email": "bad@example.com", "status": "Invalid"},
                ])

            valid_emails, summary = _read_valid_emails([output])
            self.assertEqual(valid_emails, {"person@example.com"})
            self.assertEqual(summary["rows"], 2)

    def test_accepts_descriptive_valid_statuses(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output.csv"
            output.write_text(
                "Email Address,Verification Result\n"
                "person@example.com,Valid email\n",
                encoding="utf-8",
            )

            valid_emails, _ = _read_valid_emails([output])
            self.assertEqual(valid_emails, {"person@example.com"})

    def test_accepts_boolean_validity_column(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output.csv"
            output.write_text(
                "checked_address,is_valid\n"
                "person@example.com,true\n",
                encoding="utf-8",
            )

            valid_emails, _ = _read_valid_emails([output])
            self.assertEqual(valid_emails, {"person@example.com"})

    def test_accepts_headerless_mailtester_output(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output_emails.txt.csv"
            output.write_text(
                "person@example.com,mb,Valid,Valid Person,example.com\n",
                encoding="utf-8",
            )

            valid_emails, summary = _read_valid_emails([output])

            self.assertEqual(valid_emails, {"person@example.com"})
            self.assertEqual(summary["rows"], 1)

    def test_uses_mailtester_verdict_column_for_headerless_output(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output_emails.txt.csv"
            output.write_text(
                "valid@example.com,mb,Valid,Valid Person,example.com\n"
                "abuse@example.com,mb,Abuse,Abuse Person,example.com\n"
                "mx@example.com,ko,No MX,No MX Person,example.com\n",
                encoding="utf-8",
            )

            valid_emails, summary = _read_valid_emails([output])

            self.assertEqual(valid_emails, {"valid@example.com"})
            self.assertEqual(summary["statuses"], {
                "valid": 1,
                "abuse": 1,
                "no mx": 1,
            })


class MailTesterAPITests(SimpleTestCase):
    @patch("requests.get")
    def test_verify_single_email_api_valid(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "code": "ok",
            "message": "Accepted",
            "email": "valid@example.com",
        }
        mock_get.return_value = mock_response

        is_valid = verify_single_email_api("valid@example.com", "fake_key")
        self.assertTrue(is_valid)

    @patch("requests.get")
    def test_verify_single_email_api_rejected(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "code": "ko",
            "message": "Rejected",
            "email": "invalid@example.com",
        }
        mock_get.return_value = mock_response

        is_valid = verify_single_email_api("invalid@example.com", "fake_key")
        self.assertFalse(is_valid)

    @patch("time.sleep", return_value=None)
    @patch("requests.get")
    def test_verify_single_email_api_retries_on_rate_limit(self, mock_get, mock_sleep):
        # 1st call: Rate limit message
        rate_limit_resp = MagicMock()
        rate_limit_resp.status_code = 200
        rate_limit_resp.json.return_value = {
            "code": "mb",
            "message": "Too Many Requests - Your rate is now 65",
        }

        # 2nd call: Successful Accepted
        success_resp = MagicMock()
        success_resp.status_code = 200
        success_resp.json.return_value = {
            "code": "ok",
            "message": "Accepted",
        }

        mock_get.side_effect = [rate_limit_resp, success_resp]

        is_valid = verify_single_email_api("retry@example.com", "fake_key")
        self.assertTrue(is_valid)
        self.assertEqual(mock_get.call_count, 2)

    @patch("tasks.mailtester.verify_single_email_api")
    @patch("tasks.mailtester.get_mailtester_api_key", return_value="test_key")
    def test_verify_candidates_bulk(self, mock_get_key, mock_verify):
        mock_verify.side_effect = lambda email, **kw: email == "yes@example.com"

        candidates = ["yes@example.com", "no@example.com", "yes@example.com"]
        result = verify_candidates(candidates)

        self.assertEqual(result, {"yes@example.com"})

    @patch("tasks.mailtester.time.sleep", return_value=None)
    @patch("tasks.mailtester.verify_single_email_api")
    @patch("tasks.mailtester.get_mailtester_api_key", return_value="test_key")
    def test_verify_leads_early_stop_first_hit_breaks_loop(self, mock_get_key, mock_verify, mock_sleep):
        # Lead has 8 candidates. Candidate 0 is valid. Candidates 1..7 should NEVER be checked.
        candidates = [f"cand_{i}@example.com" for i in range(8)]
        lead = {"first_name": "John", "last_name": "Doe", "email_candidates": candidates}

        mock_verify.side_effect = lambda email, **kw: email == "cand_0@example.com"

        verified_leads, valid_emails, stats = verify_leads_early_stop([lead])

        self.assertEqual(len(verified_leads), 1)
        self.assertEqual(verified_leads[0]["email"], "cand_0@example.com")
        self.assertEqual(valid_emails, {"cand_0@example.com"})
        self.assertEqual(mock_verify.call_count, 1)  # Only candidate 0 checked!
        self.assertEqual(stats["checks_made"], 1)
        self.assertEqual(stats["checks_saved"], 7)  # Saved 7 calls!

    @patch("tasks.mailtester.time.sleep", return_value=None)
    @patch("tasks.mailtester.verify_single_email_api")
    @patch("tasks.mailtester.get_mailtester_api_key", return_value="test_key")
    def test_verify_leads_early_stop_fallback_to_second_hit(self, mock_get_key, mock_verify, mock_sleep):
        # Candidate 0 invalid, candidate 1 valid -> stops at candidate 1, skips 2..7
        candidates = [f"user_{i}@company.com" for i in range(8)]
        lead = {"first_name": "Jane", "last_name": "Smith", "email_candidates": candidates}

        mock_verify.side_effect = lambda email, **kw: email == "user_1@company.com"

        verified_leads, valid_emails, stats = verify_leads_early_stop([lead])

        self.assertEqual(verified_leads[0]["email"], "user_1@company.com")
        self.assertEqual(mock_verify.call_count, 2)  # Checked candidate 0 and 1
        self.assertEqual(stats["checks_made"], 2)
        self.assertEqual(stats["checks_saved"], 6)

    @patch("tasks.mailtester.time.sleep", return_value=None)
    @patch("tasks.mailtester.verify_single_email_api")
    @patch("tasks.mailtester.get_mailtester_api_key", return_value="test_key")
    def test_verify_leads_early_stop_no_valid_candidates(self, mock_get_key, mock_verify, mock_sleep):
        # All candidates invalid -> lead email empty, 0 calls saved
        candidates = ["a@bad.com", "b@bad.com", "c@bad.com"]
        lead = {"first_name": "Bob", "last_name": "Brown", "email_candidates": candidates}

        mock_verify.return_value = False

        verified_leads, valid_emails, stats = verify_leads_early_stop([lead])

        self.assertEqual(verified_leads[0]["email"], "")
        self.assertEqual(len(valid_emails), 0)
        self.assertEqual(mock_verify.call_count, 3)
        self.assertEqual(stats["checks_made"], 3)
        self.assertEqual(stats["checks_saved"], 0)

    @patch("tasks.mailtester.time.sleep", return_value=None)
    @patch("tasks.mailtester.verify_single_email_api")
    @patch("tasks.mailtester.get_mailtester_api_key", return_value="test_key")
    def test_verify_leads_early_stop_domain_pattern_priority(self, mock_get_key, mock_verify, mock_sleep):
        import os
        from unittest.mock import patch

        lead_1 = {
            "first_name": "Alice",
            "last_name": "Wong",
            "email_candidates": ["alice.wong@acme.com", "awong@acme.com", "alicewong@acme.com"],
        }
        lead_2 = {
            "first_name": "Bob",
            "last_name": "Smith",
            "email_candidates": ["bob.smith@acme.com", "bsmith@acme.com", "bobsmith@acme.com"],
        }

        # Acme uses format index 1 (flast)
        mock_verify.side_effect = lambda email, **kw: email in ("awong@acme.com", "bsmith@acme.com")

        with patch.dict(os.environ, {"MAILTESTER_CONCURRENCY": "1"}):
            verified_leads, valid_emails, stats = verify_leads_early_stop([lead_1, lead_2])

        self.assertEqual(verified_leads[0]["email"], "awong@acme.com")
        self.assertEqual(verified_leads[1]["email"], "bsmith@acme.com")
        # Lead 1 checked alice.wong (fail) then awong (pass) -> 2 checks
        # Lead 2 prioritized bsmith (pass on 1st attempt!) -> 1 check
        # Total checks = 3 instead of 4
        self.assertEqual(mock_verify.call_count, 3)
        self.assertEqual(stats["checks_made"], 3)
        self.assertEqual(stats["checks_saved"], 3)