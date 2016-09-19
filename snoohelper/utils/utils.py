import configparser
import json
import time
from puni import Note
import requests
from peewee import OperationalError, InterfaceError

from snoohelper.reddit_interface.database_models import AlreadyDoneModel


def get_token(token_name, section, config_name='config.ini'):

    """Get token from .ini file"""

    config = configparser.ConfigParser()
    config.read(config_name)
    token = config.get(section, token_name)
    return token

REDDIT_APP_ID = get_token("REDDIT_APP_ID", "credentials")
REDDIT_APP_SECRET = get_token("REDDIT_APP_SECRET", "credentials")


def add_ban_note(un, action, unban=False):
    if not action.description:
        reason = "none provided"
    else:
        reason = action.description

    if not unban:
        n = Note(action.target_author, 'Banned, reason: ' + reason + ', length: ' + action.details,
                 action.mod_id, '', 'ban')
    elif unban and action.description != 'was temporary':
        n = Note(action.target_author, 'Unbanned.',
                 action.mod_id, '', 'spamwarning')
    else:
        return
    un.add_note(n)


def set_team_access_credentials(team_name, credentials):

    """Save Reddit user's access/refresh tokens for the bot to use"""

    config = configparser.ConfigParser()
    config.read(team_name + '_oauth.ini')
    config.set('token', 'token', credentials['access_token'])
    config.set('token', 'refresh_token', credentials['refresh_token'])
    config.set('token', 'valid_until', str(time.time() + 3600))

    with open(team_name + '_oauth.ini', 'w') as configfile:
        config.write(configfile)


def team_from_team_name(team_name):

    """Return a team object from the team's name"""

    config = configparser.ConfigParser()
    config.read('teams.ini')
    team = None

    for section in config.sections():
        if section == team_name:
            modules = config[section]['modules'].split(',')
            team = SlackTeam(team_name=team_name, team_id=config[section]['team_id'],
                             access_token=config[section]['access_token'], subreddit=config[section]['subreddit'],
                             webhook_url=config[section]['webhook_url'], modules=modules)
        break

    return team


def slackresponse_from_message(original_message, delete_buttons=False, footer=None, change_buttons=None):

    """Return a SlackResponse object from an original message dict"""

    response = SlackResponse(text=original_message.get('text', ''))
    attachments = original_message.get('attachments', list())

    for attachment in attachments:
        if footer is None:
            footer = attachment.get('footer', None)
        else:
            footer = attachment.get('footer', '') + '\n' + footer
        duplicate_attachment = response.add_attachment(title=attachment.get('title', None),
                                                       title_link=attachment.get('title_link', None),
                                                       fallback=attachment.get('fallback', None),
                                                       color=attachment.get('color', None),
                                                       footer=footer,
                                                       callback_id=attachment.get('callback_id', None),
                                                       image_url=attachment.get('image_url', None),
                                                       text=attachment.get('text', None),
                                                       author_name=attachment.get('author_name', None),
                                                       ts=attachment.get('ts', None))

        for field in attachment.get('fields', list()):
            duplicate_attachment.add_field(title=field.get('title', None), value=field.get('value', None),
                                           short=field.get('short', False))

        if not delete_buttons:
            for button in attachment.get('actions', list()):
                button_text = button.get('text')
                if button_text in change_buttons:
                    button = change_buttons[button_text].button_dict

                confirm = button.get('confirm', dict())
                duplicate_attachment.add_button(button.get('text'), value=button.get('value', None),
                                                style=button.get('style', 'default'), confirm=confirm.get('text', None),
                                                yes=confirm.get('ok_text', 'Yes'))

    return response


class SlackTeamsConfig:

    """Takes care of setting up the config for new Slack teams and holding a list of the current teams"""

    def __init__(self, filename):
        self.filename = filename
        self.config = configparser.ConfigParser()
        self.teams = self.get_teams()

    def get_teams(self):

        """Parse teams configfile to generate Team objects"""

        teams = list()
        self.config.read(self.filename)

        for section in self.config.sections():
            team_name = section
            team_id = self.config[section]['team_id']
            access_token = self.config[section]['access_token']
            subreddit = self.config.get(section, 'subreddit')
            modules = self.config.get(section, 'modules').split(',')

            team = SlackTeam(team_name, team_id, access_token, subreddit=subreddit,
                             webhook_url=self.config[section]['webhook_url'], modules=modules)
            teams.append(team)

        return teams

    def add_team(self, args_dict):

        """Save new team's attributes to configfile"""

        self.config.read(self.filename)
        if not args_dict['ok']:
            return False

        team_name = args_dict['team_name']
        team_id = args_dict['team_id']
        access_token = args_dict['access_token']
        webhook_url = args_dict['incoming_webhook']['url']

        try:
            self.config.add_section(team_name)
        except configparser.DuplicateSectionError:
            raise TeamAlreadyExists

        self.config[team_name]["team_id"] = team_id
        self.config[team_name]['access_token'] = access_token
        self.config[team_name]['webhook_url'] = webhook_url
        self.config[team_name]["subreddit"] = "False"
        self.config[team_name]["modules"] = "False"
        with open(self.filename, 'w') as configfile:
            self.config.write(configfile)
        team = SlackTeam(team_name, team_id, access_token, webhook_url, modules=None)
        self.teams.append(team)

        return team

    def set_modules(self, team_name, modules):
        self.config[team_name]["modules"] = ','.join(modules)
        with open(self.filename, 'w') as configfile:
            self.config.write(configfile)

        for team in self.teams:
            if team.team_name == team_name:
                team.modules = modules

        self._create_oauth_file(team_name, modules)

    def set_subreddit(self, team_name, subreddit, usernotes=False):

        """Bind a Slack team to a subreddit for the bot to operate on"""

        self.config.read(self.filename)
        team = None
        for team in self.teams:
            if team.team_name == team_name:
                team.subreddit = subreddit
                for section in self.config.sections():
                    if section == team_name:
                        self.config.set(section, 'subreddit', subreddit)
                        self.config.set(section, 'usernotes', str(usernotes))
                        with open(self.filename, 'w') as configfile:
                            self.config.write(configfile)
                break
        return team

    @staticmethod
    def _create_oauth_file(team_name, modules):

        """Create and prepare a configfile to store the team's authorizing user Reddit access/refresh tokens"""

        config = configparser.ConfigParser()

        try:
            config.add_section('app')
            config.add_section('server')
            config.add_section('token')
        except configparser.DuplicateSectionError:
            pass

        # Add variable scopes form, not hardcoded
        config.set('app', 'scope', 'identity,modlog,modposts,mysubreddits,read,history,modflair,flair')
        config.set('app', 'refreshable', 'True')
        config.set('app', 'app_key', REDDIT_APP_ID)
        config.set('app', 'app_secret', REDDIT_APP_SECRET)
        config.set('server', 'server_mode', 'False')
        config.set('server', 'url', '127.0.0.1')
        config.set('server', 'port', '65010')
        config.set('server', 'redirect_path', 'authorize_callback')
        config.set('server', 'link_path', 'oauth')
        config.set('token', 'token', 'None')
        config.set('token', 'refresh_token', 'None')
        config.set('token', 'valid_until', '0')

        with open(team_name + '_oauth.ini', 'w') as configfile:
            config.write(configfile)


class IncomingWebhook:

    def __init__(self, url):
        self.url = url

    def send_message(self, response):
        requests.post(self.url, data=response.get_json())


class SlackTeam:

    def __init__(self, team_name, team_id, access_token, webhook_url, modules, subreddit=None):
        self.team_name = team_name
        self.team_id = team_id
        self.access_token = access_token
        self.webhook = IncomingWebhook(webhook_url)
        self.modules = modules
        if subreddit == 'False':
            self.subreddit = None
        else:
            self.subreddit = subreddit


class SlackButton:

    def __init__(self, text, value=None, style="default", confirm=None, yes='Yes'):
        self.button_dict = dict()
        self.button_dict['text'] = text
        self.button_dict['name'] = text
        self.button_dict['style'] = style
        if value is None:
            self.button_dict['value'] = text
        else:
            self.button_dict['value'] = value
        self.button_dict['type'] = 'button'

        if confirm is not None:
            confirm_dict = dict()
            confirm_dict['title'] = "Are you sure?"
            confirm_dict['text'] = confirm
            confirm_dict['ok_text'] = yes
            confirm_dict['dismiss_text'] = 'Cancel'
            self.button_dict['confirm'] = confirm_dict


class SlackField:

    def __init__(self, title, value, short="true"):
        self.field_dict = dict()
        self.field_dict['title'] = title
        self.field_dict['value'] = value
        self.field_dict['short'] = short


class SlackAttachment:

    def __init__(self, title=None, text=None, fallback=None, callback_id=None, color=None, title_link=None,
                 image_url=None, footer=None, author_name=None, ts=None):

        self.attachment_dict = dict()

        if fallback is not None:
            self.attachment_dict['fallback'] = fallback
        if callback_id is not None:
            self.attachment_dict['callback_id'] = callback_id
        if color is not None:
            self.attachment_dict['color'] = color
        if title_link is not None:
            self.attachment_dict['title_link'] = title_link
        if image_url is not None:
            self.attachment_dict['image_url'] = image_url
        if title is not None:
            self.attachment_dict['title'] = title
        if text is not None:
            self.attachment_dict['text'] = text
        if footer is not None:
            self.attachment_dict['footer'] = footer
        if author_name is not None:
            self.attachment_dict['author_name'] = author_name
        if ts is not None:
            self.attachment_dict['ts'] = ts

        self.attachment_dict['mrkdwn_in'] = ['title', 'text']

    def add_field(self, title, value, short="true"):

        if 'fields' not in self.attachment_dict:
            self.attachment_dict['fields'] = []

        field = SlackField(title, value, short)
        self.attachment_dict['fields'].append(field.field_dict)

    def add_button(self, text, value=None, style="default", confirm=None, yes=None):

        if 'actions' not in self.attachment_dict:
            self.attachment_dict['actions'] = []

        button = SlackButton(text, value, style, confirm, yes)
        self.attachment_dict['actions'].append(button.button_dict)

    def set_footer(self, footer):
        self.attachment_dict['footer'] = footer


class SlackResponse:

    """Class used for easy crafting of a Slack response"""

    def __init__(self, text=None, response_type="in_channel", replace_original=True):
        self.response_dict = dict()
        self.attachments = []
        self._is_prepared = False

        if text is not None:
            self.response_dict['text'] = text

        if not replace_original:
            self.response_dict['replace_original'] = False

        self.response_dict['response_type'] = response_type

    def set_replace_original(self, value):
        self.response_dict['replace_original'] = value

    def add_attachment(self, title=None, text=None, fallback=None, callback_id=None, color=None,
                       title_link=None, footer=None,
                       image_url=None, author_name=None, ts=None):

        if 'attachments' not in self.response_dict:
            self.response_dict['attachments'] = []

        attachment = SlackAttachment(title=title, text=text, fallback=fallback, callback_id=callback_id, color=color,
                                     title_link=title_link, image_url=image_url, footer=footer, author_name=author_name,
                                     ts=ts)

        self.attachments.append(attachment)
        return attachment

    def _prepare(self):
        self.response_dict['attachments'] = []
        for attachment in self.attachments:
            self.response_dict['attachments'].append(attachment.attachment_dict)

    def get_json(self, indent=0):

        """Returns the JSON form of the response, ready to be sent to Slack via POST data"""

        self._prepare()

        return json.dumps(self.response_dict, indent=indent)

    def get_dict(self):

        """Returns the dict form of the response, can be sent to Slack in GET or POST params"""

        self._prepare()

        return self.response_dict

    def post_to_channel(self, token, channel, as_user=False):

        """Posts the SlackResponse object to a specific channel. The Slack team it's posted to depends on the
        token that is passed. Passing as_user will make RS post the response as the user who authorized the app."""

        response_dict = self.get_dict()

        try:
            response_dict['attachments'] = json.dumps(self.response_dict['attachments'])
        except KeyError:
            pass

        response_dict['channel'] = channel
        response_dict['token'] = token

        if as_user:
            response_dict['as_user'] = 'true'

        request_response = requests.post('https://slack.com/api/chat.postMessage',
                                         params=response_dict)

        try:
            response_dict['attachments'] = json.loads(self.response_dict['attachments'])
        except KeyError:
            pass

        return request_response.json().get('ts', None)

    def update_message(self, timestamp, channel, bot_token, parse='full'):

        response_dict = self.get_dict()
        response_dict['attachments'] = json.dumps(self.response_dict['attachments'])
        response_dict['channel'] = channel
        response_dict['token'] = bot_token
        response_dict['ts'] = timestamp
        response_dict['as_user'] = 'true'
        response_dict['parse'] = parse

        request_response = requests.post('https://slack.com/api/chat.update',
                                         params=response_dict)
        return request_response


class SlackRequest:

    """Parses HTTP request from Slack"""

    def __init__(self, request, slash_commands_secret):

        self.form = request.form
        self.request_type = "command"
        self.response = None
        self.command = None
        self.actions = None
        self.callback_id = None
        self.is_valid = False
        self.slash_commands_secret = slash_commands_secret

        if 'payload' in self.form:
            self.request_type = "button"
            self.form = json.loads(dict(self.form)['payload'][0])
            self.user = self.form['user']['name']
            self.user_id = self.form['user']['id']
            self.team_domain = self.form['team']['domain']
            self.team_id = self.form['team']['id']
            self.callback_id = self.form['callback_id']
            self.actions = self.form['actions']
            self.message_ts = self.form['message_ts']
            self.channel = self.form['channel']['id']
            self.original_message = self.form['original_message']
        else:
            self.user = self.form['user_name']
            self.team_domain = self.form['team_domain']
            self.team_id = self.form['team_id']
            self.command = self.form['command']
            self.command_args = self.form['text'].split()
            self.channel_name = self.form['channel_name']

        self.response_url = self.form['response_url']
        self.token = self.form['token']
        self.team = team_from_team_name(self.team_domain)

        if self.token == self.slash_commands_secret:
            self.is_valid = True

    def delayed_response(self, response):

        """Slack demands a response within 3 seconds. Additional responses can be sent through this method, in the
        form of a SlackRequest object or plain text string"""

        headers = {"content-type": "plain/text"}

        if isinstance(response, SlackResponse):
            headers = {"content-type": "application/json"}
            response = response.get_json()

        slack_response = requests.post(self.response_url, data=response, headers=headers)

        return slack_response


class AlreadyDoneHelper:

    def __init__(self):
        query = AlreadyDoneModel.delete().where((time.time() - AlreadyDoneModel.timestamp) > 7200)
        num = query.execute()

        if num:
            print("AlreadyDoneHelper: cleaned up %s ids." % str(num))

    @staticmethod
    def add(thing_id, subreddit):

        while True:
            try:
                AlreadyDoneModel.create(thing_id=thing_id, timestamp=time.time(), subreddit=subreddit)
                break
            except (OperationalError, InterfaceError):
                print("Failed to write")
                time.sleep(1)


class TeamAlreadyExists(Exception):
    pass












