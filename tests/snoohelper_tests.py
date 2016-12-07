import unittest
from snoohelper.utils.teams import SlackTeamsController
from snoohelper.reddit.bot import SnooHelperBot


class SnooHelperTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.teams_controller = SlackTeamsController("teams_test.ini")

    def test_bot_init(self):
        team_name = "SnooHelper Testing"
        self.assertTrue(isinstance(self.teams_controller.add_bot(team_name), SnooHelperBot))


if __name__ == '__main__':
    unittest.main()
