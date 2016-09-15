import requests
import json
import configparser
import time


def get_token(token_name, section, config_name='config.ini'):

    config = configparser.ConfigParser()
    config.read(config_name)
    token = config.get(section, token_name)
    return token


def set_team_access_credentials(team_name, credentials):
    config = configparser.ConfigParser()
    config.read(team_name + '_oauth.ini')
    config.set('token', 'token', credentials['access_token'])
    config.set('token', 'refresh_token', credentials['refresh_token'])
    config.set('token', 'valid_until', time.time() + 3600)

    with open(team_name + '_oauth.ini', 'w') as configfile:
        config.write(configfile)


class SlackTeamsConfig:

    def __init__(self, filename):
        self.filename = filename
        self.config = configparser.ConfigParser()
        self.teams = self.get_teams()

    def get_teams(self):
        teams = list()
        self.config.read(self.filename)

        for section in self.config.sections():
            team_name = section
            team_id = self.config[section]['team_id']
            access_token = self.config[section]['access_token']
            team = SlackTeam(team_name, team_id, access_token)
            teams.append(team)

        return teams

    def add_team(self, args_dict):
        if not args_dict['ok']:
            return False

        team_name = args_dict['team_name']
        team_id = args_dict['team_id']
        access_token = args_dict['access_token']

        try:
            self.config.add_section(team_name)
        except configparser.DuplicateSectionError:
            # team already exists
            raise

        self.config[team_name]["team_id"] = team_id
        self.config[team_name]['access_token'] = access_token
        with open(self.filename, 'w') as configfile:
            self.config.write(configfile)
        team = SlackTeam(team_name, team_id, access_token)
        self.teams.append(team)
        self._create_oauth_file(team_name)

        return team

    @staticmethod
    def _create_oauth_file(team_name):
        config = configparser.ConfigParser()

        config.add_section('app')
        config.add_section('server')
        config.add_section('token')

        config.set('app', 'scope', 'identity,modlog,modposts')
        config.set('app', 'refreshable', 'True')
        config.set('server', 'server_mode', 'False')
        config.set('server', 'url', '127.0.0.1')
        config.set('server', 'port', '65010')
        config.set('server', 'redirect_path', 'authorize_callback')
        config.set('server', 'link_path', 'oauth')
        config.set('token', 'token', 'None')
        config.set('token', 'refresh_token', 'None')
        config.set('token', 'valid_until', 0)

        with open(team_name + '_oauth.ini', 'w') as configfile:
            config.write(configfile)


class RSConfig:

    def __init__(self, filename):
        self.filename = filename
        self.config = configparser.ConfigParser()

    @property
    def user_agent(self):
        self.config.read(self.filename)
        return self.config['credentials', 'REDDIT_USER_AGENT']


class SlackTeam:

    def __init__(self, team_name, team_id, access_token):
        self.team_name = team_name
        self.team_id = team_id
        self.access_token = access_token


class SlackButton:

    def __init__(self, text, value=None, style="default", confirm=None, yes=None):
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


class SlackResponse:

    """Class used for easy crafting of a Slack response"""

    def __init__(self, text=None, response_type="in_channel", replace_original=True):
        self.response_dict = dict()
        self.attachments = []
        self._is_prepared = False

        if text is not None:
            self.response_dict['text'] = text

        if not replace_original:
            self.response_dict['replace_original'] = 'false'

        self.response_dict['response_type'] = response_type

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

    def get_json(self):

        """Returns the JSON form of the response, ready to be sent to Slack via POST data"""

        self._prepare()

        return json.dumps(self.response_dict)

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
            self.original_message = self.form['original_message']
        else:
            self.user = self.form['user_name']
            self.team_domain = self.form['team_domain']
            self.team_id = self.form['team_id']
            self.command = self.form['command']
            self.text = self.form['text']
            self.channel_name = self.form['channel_name']

        self.response_url = self.form['response_url']
        self.token = self.form['token']

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