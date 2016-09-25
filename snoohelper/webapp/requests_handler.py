from snoohelper.reddit_interface.bot import RedditBot
from snoohelper.utils import utils as utils


class RequestsHandler:

    """Processes incoming slack requests, performs operations on appropriate Reddit bot and returns a SlackResponse"""

    def __init__(self, slack_teams_config):
        self.slack_teams_config = slack_teams_config
        self.bots = dict()

        for team in self.slack_teams_config.teams:
            if team.subreddit is not None:
                self.bots[team.team_name] = RedditBot(team_config=team)

    def add_new_bot(self, team_name):
        team = utils.team_from_team_name(team_name)
        if team_name not in self.bots and team.subreddit is not None:
            self.bots[team.team_name] = RedditBot(team_config=team)

    def handle_command(self, slack_request):
        response = utils.SlackResponse("Processing your request... please allow a few seconds.")
        if slack_request.command == '/userz':
            self.bots[slack_request.team_domain].quick_user_summary(user=slack_request.command_args[0],
                                                                    request=slack_request)
        return response

    def handle_button(self, slack_request):
        response = utils.SlackResponse("Processing your request... please allow a few seconds.", replace_original=False)
        button_pressed = slack_request.actions[0]['value'].split('_')[0]
        args = slack_request.actions[0]['value'].split('_')[1:]
        target_user = '_'.join(args[1:])

        if button_pressed == "summary":
            original_message = utils.slackresponse_from_message(slack_request.original_message,
                                                                footer="Summary (%s) requested." % args[0])
            original_message.set_replace_original(True)
            response = original_message
            self.bots[slack_request.team_domain].expanded_user_summary(request=slack_request,
                                                                                  limit=int(args[0]),
                                                                                  username=target_user)
        elif button_pressed == "track":
            response = self.bots[slack_request.team_domain].track_user(user=target_user)
        elif button_pressed == "untrack":
            response = self.bots[slack_request.team_domain].untrack_user(user=target_user)
        elif button_pressed == "botban":
            response = self.bots[slack_request.team_domain].botban(user=target_user, author=slack_request.user)
        elif button_pressed == "unbotban":
            response = self.bots[slack_request.team_domain].unbotban(user=target_user, author=slack_request.user)

        return response
