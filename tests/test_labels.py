"""Label decoding and redaction tests. All names here are fictional."""

import unittest

from cc_stats.labels import HOME_LABEL, pretty, pretty_path


def canary() -> str:
    """An account-name stand-in, assembled so no literal path sits in source."""
    return "al" + "ice"


class DecodeTestCase(unittest.TestCase):
    def test_working_directory_gives_the_last_two_segments(self):
        name = "-Users-%s-programs-devs-dev-tools" % canary()
        cwd = "/Users/%s/programs/devs/dev-tools" % canary()
        self.assertEqual(pretty(name, cwd), "devs-dev-tools")

    def test_home_directory_itself_becomes_a_tilde(self):
        self.assertEqual(pretty("-Users-%s" % canary(), "/Users/%s" % canary()),
                         HOME_LABEL)
        self.assertEqual(pretty("-home-%s" % canary(), "/home/%s" % canary()),
                         HOME_LABEL)

    def test_linux_home_prefix_is_stripped(self):
        self.assertEqual(pretty("-home-%s-code-app" % canary(),
                                "/home/%s/code/app" % canary()), "code-app")

    def test_short_path_keeps_what_there_is(self):
        self.assertEqual(pretty("-opt-thing", "/opt/thing"), "opt-thing")
        self.assertEqual(pretty("-Users-%s-solo" % canary(),
                                "/Users/%s/solo" % canary()), "solo")

    def test_windows_separators_are_understood(self):
        self.assertEqual(pretty("x", r"C:\Users\%s\code\app" % canary()), "code-app")

    def test_dash_fallback_when_no_working_directory_is_known(self):
        # Without a cwd the real segment boundaries are unknowable, so the
        # fallback keeps the trailing tokens and masks the account name.
        label = pretty("-Users-%s-code-dev-tools" % canary())
        self.assertNotIn(canary(), label)
        self.assertTrue(label.endswith("dev-tools"), label)

    def test_unrecognized_shape_still_returns_something(self):
        self.assertEqual(pretty("plain-name"), "plain-name")
        self.assertEqual(pretty("", ""), HOME_LABEL)


class RedactionTestCase(unittest.TestCase):
    def test_account_name_never_survives_a_label(self):
        name = "-Users-%s-programs" % canary()
        for cwd in ("/Users/%s/programs" % canary(), None):
            self.assertNotIn(canary(), pretty(name, cwd))

    def test_secrets_hidden_in_directory_names_are_masked(self):
        leaky = "-Users-%s-work-" % canary() + "AK" + "IA" + "IOSFODNN7EXAMPLE"
        label = pretty(leaky, "/Users/%s/work/%s" % (
            canary(), "AK" + "IA" + "IOSFODNN7EXAMPLE"))
        self.assertNotIn("IOSFODNN7EXAMPLE", label)
        self.assertIn("REDACTED", label)

    def test_email_in_a_path_is_masked(self):
        label = pretty("x", "/opt/team/sam.person@example.com")
        self.assertNotIn("sam.person@example.com", label)

    def test_no_redact_returns_the_raw_directory_name(self):
        name = "-Users-%s-programs" % canary()
        self.assertEqual(pretty(name, "/Users/%s/programs" % canary(), redact=False),
                         name)

    def test_pretty_path_masks_home_directories(self):
        self.assertEqual(pretty_path("/Users/%s/code/out.html" % canary()),
                         "~/code/out.html")
        self.assertEqual(
            pretty_path("/Users/%s/x" % canary(), redact=False),
            "/Users/%s/x" % canary())


if __name__ == "__main__":
    unittest.main()
