import unittest
from snoohelper.utils.teams import SlackTeamsController
from snoohelper.reddit.bot import SnooHelperBot
from snoohelper.utils.slack import SlackResponse
from snoohelper.reddit.bot_modules.flair_enforcer import UnflairedSubmission


class SnooHelperBotTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.team_name = "SnooHelper Testing"
        cls.teams_controller = SlackTeamsController("teams_test.ini", "snoohelper_test.db")
        cls.bot = cls.teams_controller.add_bot(cls.team_name)

    def test_add_bot(self):
        self.assertTrue(isinstance(self.teams_controller.add_bot(self.team_name), SnooHelperBot))

    def test_botban(self):
        response = self.bot.botban("santi871", "santi871")
        self.assertTrue(isinstance(response, SlackResponse))

    def test_unbotban(self):
        response = self.bot.unbotban("santi871", "santi871")
        self.assertTrue(isinstance(response, SlackResponse))

    def test_track_user(self):
        response = self.bot.track_user("santi871")
        self.assertTrue(isinstance(response, SlackResponse))

    def test_untrack_user(self):
        response = self.bot.untrack_user("santi871")
        self.assertTrue(isinstance(response, SlackResponse))

    def test_add_unflaired_submission(self):
        submission = self.bot.r.submission("5gk734")
        submission = self.bot.flair_enforcer.add_submission(submission)
        self.assertTrue(isinstance(submission, UnflairedSubmission))

    def test_check_submissions(self):
        self.bot.flair_enforcer.check_submissions(force_approve=True)

    def test_quick_summary(self):
        self.bot.summary_generator.generate_quick_summary('santi871')

    def test_expanded_summary(self):
        self.bot.summary_generator.generate_expanded_summary('santi871', 100)

if __name__ == '__main__':
    unittest.main()
