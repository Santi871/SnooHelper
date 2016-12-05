import configparser
from .slack import IncomingWebhook
from reddit.bot import SnooHelperBot


class SlackTeam:

    def __init__(self, filename, team_name, team_id, access_token, webhook_url, subreddit, modules, scopes,
                 reddit_refresh_token):
        config = configparser.ConfigParser()
        self.filename = filename
        self.team_name = team_name
        self.team_id = team_id
        self.access_token = access_token
        self.webhook_url = webhook_url
        self.webhook = IncomingWebhook(self.webhook_url)
        self.subreddit = subreddit
        self.modules = modules
        self.scopes = scopes
        self.reddit_refresh_token = reddit_refresh_token
        self.bot = None
        config.read(filename)

        try:
            config.add_section(team_name)
        except configparser.DuplicateSectionError:
            pass

        config[team_name]["team_id"] = team_id
        config[team_name]['access_token'] = access_token
        config[team_name]['webhook_url'] = webhook_url
        config[team_name]["subreddit"] = subreddit
        config[team_name]["modules"] = modules
        config[team_name]["scopes"] = scopes
        config[team_name]["reddit_refresh_token"] = reddit_refresh_token

        with open(filename, 'w') as configfile:
            config.write(configfile)

    def set(self, attribute, value):
        config = configparser.ConfigParser()
        config.read(self.filename)
        config[self.team_name][attribute] = value
        setattr(self, attribute, value)
        with open(self.filename, 'w') as configfile:
            config.write(configfile)


class SlackTeamsController:

    def __init__(self, filename):
        self.teams = dict()
        self.filename = filename

        config = configparser.ConfigParser()
        config.read(filename)

        for section in config.sections():
            team_id = config[section]["team_id"]
            access_token = config[section]['access_token']
            webhook_url = config[section]['webhook_url']
            subreddit = config[section]["subreddit"]
            modules = config[section]["modules"]
            scopes = config[section]["scopes"]
            reddit_refresh_token = config[section]["reddit_refresh_token"]

            if team_id and access_token and webhook_url and subreddit and modules and scopes and reddit_refresh_token:
                team = SlackTeam(self.filename, section, team_id, access_token, webhook_url, subreddit, modules,
                                 scopes, reddit_refresh_token)
                self.teams[section] = team
                self.add_bot(section)

    def add_bot(self, team_name):
        self.teams[team_name].bot = SnooHelperBot(self.teams[team_name])

    def add_team(self, slack_payload):
        team_name = slack_payload['team_name']
        team_id = slack_payload['team_id']
        access_token = slack_payload['access_token']
        webhook_url = slack_payload['incoming_webhook']['url']
        subreddit = ""
        modules = ""
        scopes = ""
        reddit_refresh_token = ""

        team = SlackTeam(self.filename, team_name, team_id, access_token, webhook_url, subreddit, modules, scopes,
                         reddit_refresh_token)
        self.teams[team_name] = team
        return team

    def remove_team(self, team_name):
        # terminate bot
        self.teams.pop(team_name, None)
