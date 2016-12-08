import unittest
import os
from snoohelper.utils.teams import SlackTeamsController
from snoohelper.utils.credentials import get_token
from snoohelper.reddit.bot_modules.flair_enforcer import UnflairedSubmission
from snoohelper.webapp.requests_handler import RequestsHandler
from snoohelper.webapp.webapp import create_app
import utils.slack


def create_dummy_command_request(command):
    dummy_request = {
        'user_name': 'Santi871',
        'team_domain': 'snoohelpertesting',
        'team_id': get_token("team_id", "SnooHelper Testing", "teams_test.ini"),
        'command': command,
        'text': 'santi871',
        'channel_name': '#general',
        'response_url': get_token("webhook_url", "SnooHelper Testing", "teams_test.ini"),
        'token': 'abc123'
    }
    return utils.slack.SlackRequest(form=dummy_request)


class SnooHelperTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):

        travis_ci = os.environ.get('team_name', False)
        if travis_ci:
            cls.teams_controller = SlackTeamsController("teams_test.ini", "snoohelper_test.db", vars_from_env=True)
            cls.team_name = "SnooHelper"
        else:
            cls.team_name = "SnooHelper Testing"
            cls.teams_controller = SlackTeamsController("teams_test.ini", "snoohelper_test.db")
        cls.bot = cls.teams_controller.teams[cls.team_name].bot
        cls.submission = cls.bot.r.submission("5gk734")
        cls.requests_handler = RequestsHandler(cls.teams_controller)
        app = create_app(cls.teams_controller, cls.requests_handler)
        cls.app = app.test_client()
        cls.app.testing = True

    def test_botban(self):
        response = self.bot.botban("santi871", "santi871")
        self.assertTrue(isinstance(response, utils.slack.SlackResponse))

    def test_unbotban(self):
        response = self.bot.unbotban("santi871", "santi871")
        self.assertTrue(isinstance(response, utils.slack.SlackResponse))

    def test_track_user(self):
        response = self.bot.track_user("santi871")
        self.assertTrue(isinstance(response, utils.slack.SlackResponse))

    def test_check_user_offenses(self):
        self.bot.user_warnings.check_user_offenses('santi871')

    def test_send_warning(self):
        self.bot.user_warnings.send_warning(self.submission)

    def test_check_user_posts(self):
        self.bot.user_warnings.check_user_posts(self.submission)

    def test_untrack_user(self):
        response = self.bot.untrack_user("santi871")
        self.assertTrue(isinstance(response, utils.slack.SlackResponse))

    def test_add_unflaired_submission(self):
        submission = self.bot.flair_enforcer.add_submission(self.submission)
        self.assertTrue(isinstance(submission, UnflairedSubmission))

    def test_quick_summary(self):
        self.bot.summary_generator.generate_quick_summary('santi871')

    def test_expanded_summary(self):
        self.bot.summary_generator.generate_expanded_summary('santi871', 100)

    def test_command_requests(self):
        dummy_request = create_dummy_command_request('/user')
        response = self.requests_handler.handle_command(dummy_request)
        self.assertTrue(isinstance(response, utils.slack.SlackResponse))

        dummy_request = create_dummy_command_request('/botban')
        response = self.requests_handler.handle_command(dummy_request)
        self.assertTrue(isinstance(response, utils.slack.SlackResponse))

        dummy_request = create_dummy_command_request('/modmail')
        response = self.requests_handler.handle_command(dummy_request)
        self.assertTrue(isinstance(response, utils.slack.SlackResponse))

    def test_slack_auth_endpoint(self):
        result = self.app.get("/slack/oauthcallback")
        self.assertEqual(result.status_code, 302)

    def test_reddit_auth_endpoint(self):
        result = self.app.get("/reddit/oauthcallback")
        self.assertEqual(result.status_code, 302)

if __name__ == '__main__':
    unittest.main()
