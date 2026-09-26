"""SMS veri con le tre variabili Twilio, finti con nessuna, avvio bloccato a metà (decisione 2026-09-26)."""
import unittest

from vela.adapters.sms_fake import FakeSms
from vela.adapters.sms_twilio import TwilioSms
from vela.app import build_notifier
from vela.config import Settings

FULL = dict(twilio_account_sid="AC1", twilio_auth_token="token-segreto", twilio_from="+15550001111")


class BuildNotifierTest(unittest.TestCase):
    def test_no_twilio_variables_gives_fake_sms(self):
        self.assertIsInstance(build_notifier(Settings()), FakeSms)

    def test_all_three_give_twilio(self):
        self.assertIsInstance(build_notifier(Settings(**FULL)), TwilioSms)

    def test_partial_configuration_blocks_startup_naming_the_missing(self):
        with self.assertRaises(RuntimeError) as ctx:
            build_notifier(Settings(twilio_account_sid="AC1", twilio_auth_token="token-segreto"))
        self.assertIn("TWILIO_FROM", str(ctx.exception))
        self.assertNotIn("token-segreto", str(ctx.exception))

    def test_twilio_is_independent_from_upstream_mode(self):
        self.assertIsInstance(build_notifier(Settings(vela_upstream_mode="replay", **FULL)), TwilioSms)
