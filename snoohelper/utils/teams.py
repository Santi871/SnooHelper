import configparser
import snoohelper.utils as utils
import snoohelper.utils.reddit
from snoohelper.reddit.bot import SnooHelperBot
from .slack import IncomingWebhook
import os


class SlackTeam:
    """
    Represents a Slack Team and contains all the data related to it - such as authentication tokens, enabled modules,
    and other configuration parameters, saves the data to an .ini file

    The bot attribute is set after initialization by SlackTeamsController

    Should not instantiate this class directly, use SlackTeamsController.add_team()
    """
    def __init__(self, filename, team_name, team_id, access_token, webhook_url, subreddit, modules, scopes,
                 reddit_refresh_token, sleep=60.0, save_to_disk=True):
        """
        Set instance attributes and save them to an .ini file

        :param filename: name of the .ini file containing the configuration of all the teams
        :param team_name: name of the Slack team
        :param team_id: id of the Slack team
        :param access_token: access token belonging to the Slack team
        :param webhook_url: webhook url belonging to the Slack team
        :param subreddit: subreddit the Slack team is associated to
        :param modules: comma-separated string of modules
        :param scopes: comma-separated string of scopes
        :param reddit_refresh_token: refresh token for Reddit's OAuth
        :param sleep: time to sleep between subreddit submissions/comments/modlog/etc fetchings, is later automatically
        calculated based on number of subscribers
        """

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
        self.sleep = sleep
        self.bot = None

        if save_to_disk:
            config = configparser.ConfigParser()
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
            config[team_name]["sleep"] = str(self.sleep)

            with open(filename, 'w') as configfile:
                config.write(configfile)

    def set(self, attribute, value, save_to_disk=True):
        """
        Set attribute of SlackTeam and save to .ini file

        :param attribute: name of the attribute
        :param value: value to set the attribute to
        """

        setattr(self, attribute, value)
        if save_to_disk:
            config = configparser.ConfigParser()
            config.read(self.filename)
            config[self.team_name][attribute] = str(value)

            with open(self.filename, 'w') as configfile:
                config.write(configfile)


class SlackTeamsController:
    """
    Utility class for easy management of SlackTeams. Stores current teams in a dict and implements methods for adding
    and removing teams as well as adding a Reddit bot to a team
    """
    def __init__(self, filename, db_name, vars_from_env=False):
        """
        Construct the SlackTeams already present in the teams .ini file as well as their respective bots
        Holds current SlackTeams in self.teams dict, keys being the team's name
        :param filename: name of the .ini file containing the configuration of all the teams
        """
        self.teams = dict()
        self.filename = filename
        self.db_name = db_name

        if not vars_from_env:
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
                sleep = float(config[section]["sleep"])

                if team_id and access_token and webhook_url and subreddit and modules and scopes and\
                        reddit_refresh_token:
                    team = SlackTeam(self.filename, section, team_id, access_token, webhook_url, subreddit, modules,
                                     scopes, reddit_refresh_token, sleep=sleep)
                    self.teams[section] = team
                    self.add_bot(section)
        else:
            team_name = os.environ['team_name']
            team_id = os.environ['team_id']
            access_token = os.environ['access_token']
            webhook_url = os.environ['webhook_url']
            subreddit = os.environ['subreddit']
            modules = os.environ['modules']
            scopes = os.environ['scopes']
            reddit_refresh_token = os.environ['reddit_refresh_token']
            sleep = os.environ['sleep']
            print(team_name)
            team = SlackTeam(self.filename, team_name, team_id, access_token, webhook_url, subreddit, modules,
                             scopes, reddit_refresh_token, sleep=sleep, save_to_disk=False)
            self.teams[team_name] = team
            self.add_bot(team_name, save_to_disk=False)

    def add_bot(self, team_name, save_to_disk=True):
        """
        Adds a SnooHelperBot to a SlackTeam

        :param team_name: name of the team to add the bot to
        :return: instance of SnooHelperBot
        """
        bot = SnooHelperBot(self.teams[team_name], self.db_name)
        self.teams[team_name].bot = bot
        subscribers = self.teams[team_name].bot.subreddit.subscribers
        sleep = utils.reddit.calculate_sleep(subscribers)
        self.teams[team_name].set("sleep", sleep, save_to_disk)
        return bot

    def add_team(self, slack_payload):
        """
        Constructs a SlackTeam and adds it to the self.teams dict

        :param slack_payload: Slack JSON response after Slack authentication is completed
        :return: instance of SlackTeam
        """
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

    def lookup_team_by_id(self, team_id):
        """
        Find SlackTeam by its Slack id in self.teams dict and return it

        :param team_id: id of the Slack team
        :return: instance of SlackTeam, None if not found
        """
        for key, team in self.teams.items():
            if team.team_id == team_id:
                return team
        return

    def remove_team(self, team_name):
        """
        Remove a SlackTeam from the self.teams dict

        :param team_name: Name of the SlackTeam
        :return: instance of SlackTeam, or None if not found
        """
        return self.teams.pop(team_name, None)
