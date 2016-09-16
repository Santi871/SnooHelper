from reddit_interface.bot import RedditBot
import utils.utils as utils


class RequestsHandler:

    """Processes incoming slack requests, performs operations on appropriate Reddit bot and returns a SlackResponse"""

    def __init__(self, slack_teams_config):
        self.slack_teams_config = slack_teams_config
        self.bots = dict()

        for team in self.slack_teams_config.teams:
            if team.subreddit is not None:
                self.bots[team.team_name] = RedditBot(team=team)

    def add_new_bot(self, team):
        if team.team_name not in self.bots and team.subreddit is not None:
            self.bots[team.team_name] = RedditBot(team=team)

    def handle_command(self, slack_request):
        response = utils.SlackResponse("Processing your request... please allow a few seconds.")
        if slack_request.command == '/userz':
            self.bots[slack_request.team_domain].user_summary(user=slack_request.command_args[0], request=slack_request)
        return response


