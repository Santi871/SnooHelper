import requests
import json
from threading import Thread


def own_thread(func):
    """
    Decorator that starts a method or function on its own thread

    :param func: function
    :return: wrapped function
    """
    def wrapped_f(*args, **kwargs):
        thread = Thread(target=func, args=args, kwargs=kwargs, daemon=True)
        thread.start()

    return wrapped_f


def slackresponse_from_message(original_message, delete_buttons=None, footer=None, change_buttons=None):

    """Return a SlackResponse object from an original message dict"""

    response = SlackResponse(text=original_message.get('text', ''))
    attachments = original_message.get('attachments', list())

    if delete_buttons is None:
        delete_buttons = list()
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

        for button in attachment.get('actions', list()):
            if button.get("text") not in delete_buttons:
                button_text = button.get('text')

                if change_buttons is not None:
                    if button_text in change_buttons:
                        button = change_buttons[button_text].button_dict

                confirm = button.get('confirm', dict())
                duplicate_attachment.add_button(button.get('text'), value=button.get('value', None),
                                                style=button.get('style', 'default'), confirm=confirm.get('text', None),
                                                yes=confirm.get('ok_text', 'Yes'))

    return response


class IncomingWebhook:
    """
    Utility class that wraps a Slack webhook
    """

    def __init__(self, url):
        """
        :param url: Slack webhook URL
        """
        self.url = url

    def send_message(self, message):
        """
        Send a Slack message via the webhook

        :param message: SlackResponse object
        :return: requests.Response object
        """
        return requests.post(self.url, data=message.get_json())


class SlackButton:
    """
    Class that represents a JSON-encoded Slack button
    """

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
    """
    Class that represents a JSON-encoded Slack message field
    """

    def __init__(self, title, value, short="true"):
        self.field_dict = dict()
        self.field_dict['title'] = title
        self.field_dict['value'] = value
        self.field_dict['short'] = short


class SlackAttachment:
    """
    Class that represents a JSON-encoded Slack message attachment
    """

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

    """
    Class used for easy crafting of a Slack response
    """

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

    def add_attachment(self, title=None, text=None, fallback=None, callback_id=None, color='#5c96ab',
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

    """
    Represents an HTTP request from Slack
    """

    def __init__(self, request=None, slash_commands_secret=None, form=None):

        if form is None:
            self.form = request.form
        else:
            self.form = form

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
            self.text = self.form['text']
            self.command_args = self.form['text'].split()
            self.channel_name = self.form['channel_name']

        self.response_url = self.form['response_url']
        self.token = self.form['token']
        # self.team = team_from_team_name(self.team_domain)

        if self.slash_commands_secret is not None:
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
