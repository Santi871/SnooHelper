from reddit_interface.bot import RedditBot


class RequestsHandler:

    def __init__(self, slack_teams_config):
        self.slack_teams_config = slack_teams_config
        self.bots = dict()

        for team in self.slack_teams_config.teams:
            if team.subreddit is not None:
                self.bots[team.team_name] = RedditBot(team=team.team_name)

    def add_new_bot(self, team):
        if team.team_name not in self.bots and team.subreddit is not None:
            self.bots[team.team_name] = RedditBot(team=team.team_name)




