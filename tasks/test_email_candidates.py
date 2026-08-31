from django.test import SimpleTestCase

from .email_candidates import add_email_candidates, generate_email_candidates


class EmailCandidateTests(SimpleTestCase):
    def test_generates_the_eight_requested_formats(self):
        row = {
            "First Name": "Muhammad",
            "Last Name": "Akram",
            "Company Domain": "https://brainxtech.com/",
        }

        self.assertEqual(
            generate_email_candidates(row),
            [
                "muhammad.akram@brainxtech.com",
                "muhammadakram@brainxtech.com",
                "makram@brainxtech.com",
                "muhammad.a@brainxtech.com",
                "akram.muhammad@brainxtech.com",
                "akr ammuhammad@brainxtech.com".replace(" ", ""),
                "m.akram@brainxtech.com",
                "muhammad a@brainxtech.com".replace(" ", ""),
            ],
        )

    def test_missing_inputs_do_not_create_invalid_candidates(self):
        self.assertEqual(
            generate_email_candidates(
                {
                    "First Name": "Muhammad",
                    "Last Name": "Akram",
                    "Company Domain": "",
                }
            ),
            [],
        )

    def test_add_candidates_preserves_original_fields(self):
        row = {
            "First Name": "A",
            "Last Name": "B",
            "Company Domain": "example.com",
        }
        enriched = add_email_candidates([row])[0]

        self.assertEqual(enriched["First Name"], "A")
        self.assertEqual(enriched["email_candidates"], [
            "a.b@example.com",
            "ab@example.com",
            "b.a@example.com",
            "ba@example.com",
        ])