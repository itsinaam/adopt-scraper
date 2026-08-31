import csv
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from .mailtester import (
    _read_valid_emails,
    verify_candidates,
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