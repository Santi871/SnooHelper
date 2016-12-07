import random
import string
import time

import praw
import requests
from flask import Flask, request, Response, redirect, render_template, make_response
from flask_sslify import SSLify
import snoohelper.utils as utils
from snoohelper.utils.credentials import get_token
from .form import SubredditSelectForm, ModulesSelectForm

SLACK_APP_ID = get_token("SLACK_APP_ID", "credentials")
SLACK_APP_SECRET = get_token("SLACK_APP_SECRET", "credentials")
SLACK_COMMANDS_TOKEN = get_token("SLACK_COMMANDS_TOKEN", "credentials")
REDDIT_APP_ID = get_token("REDDIT_APP_ID", "credentials")
REDDIT_APP_SECRET = get_token("REDDIT_APP_SECRET", "credentials")
REDDIT_REDIRECT_URI = get_token("REDDIT_REDIRECT_URI", "credentials")


def create_app(teams_controller, handler):
    new_app = Flask(__name__, template_folder='../webapp/templates')
    SSLify(new_app)
    new_app.config['CONTROLLER'] = teams_controller
    new_app.config['HANDLER'] = handler
    new_app.config['WTF_CSRF_ENABLED'] = True
    new_app.config['SECRET_KEY'] = get_token("SECRET_KEY", "credentials")

    reddits = dict()
    cur_bot = dict()

    @new_app.route("/slack/oauthcallback", methods=['POST', 'GET'])
    def slack_oauth_callback():
        form = ModulesSelectForm()
        slack_teams_controller = new_app.config['CONTROLLER']

        if not form.validate_on_submit():
            data = {'client_id': SLACK_APP_ID, 'client_secret': SLACK_APP_SECRET, 'code': request.args.get('code')}
            response = requests.post('https://slack.com/api/oauth.access', params=data)
            response_json = response.json()

            # handle already existing team
            cur_bot[response_json['team_name']] = slack_teams_controller.teams.get(response_json['team_name'], None)
            slack_teams_controller.add_team(response_json)

            response = make_response(render_template('modules_select.html',
                                                     title='Modules Select', form=form))
            response.set_cookie('slack_team_name', response_json['team_name'])

            return response
        else:
            scopes = ['identity', 'mysubreddits', 'modposts', 'read', 'history', 'privatemessages']
            form_data = form.modules_select.data
            team_name = request.cookies.get('slack_team_name')

            if "usernotes" in form_data:
                scopes.append('wikiedit')
                scopes.append('wikiread')
            if "userwarnings" in form_data:
                scopes.append('modlog')
            if "flairenforce" in form_data:
                scopes.append('flair')
                scopes.append('modflair')
                scopes.append('submit')
                scopes.append('report')

            slack_teams_controller.teams[team_name].set("modules", ','.join(form_data))
            slack_teams_controller.teams[team_name].set("scopes", ','.join(scopes))
            state = ''.join(random.SystemRandom().choice(string.ascii_uppercase + string.digits) for _ in range(8))
            r = praw.Reddit(user_agent="Snoohelper 0.1 by /u/Santi871",
                            client_id=REDDIT_APP_ID, client_secret=REDDIT_APP_SECRET,
                            redirect_uri=REDDIT_REDIRECT_URI)
            reddits[state] = r
            url = r.auth.url(scopes, state, 'permanent')
            response = make_response(redirect(url, code=302))

            return response

    @new_app.route('/reddit/oauthcallback', methods=['POST', 'GET'])
    def reddit_oauth_callback():
        form = SubredditSelectForm()
        slack_teams_controller = new_app.config['CONTROLLER']

        if request.method == 'GET':
            code = request.args.get('code', None)
            state = request.args.get('state', None)
            r = reddits[state]
            team_name = request.cookies.get('slack_team_name')
            if code is not None:
                while True:
                    try:
                        refresh_token = r.auth.authorize(code)
                        slack_teams_controller.teams[team_name].set("reddit_refresh_token", refresh_token)
                        break
                        # catch oauth errors
                    except requests.exceptions.ConnectionError:
                        print("Connection error")
                        time.sleep(0.5)
                        continue

                choices = [(subreddit.display_name, subreddit.display_name)
                           for subreddit in r.user.moderator_subreddits(limit=None)]
                form.subreddit_select.choices = choices
                reddits.pop(state, None)
                return render_template('subreddit_select.html', title='Select Subreddit', form=form)

        elif request.method == 'POST':
            subreddit = form.subreddit_select.data
            team_name = request.cookies.get('slack_team_name', None)

            if team_name is None:
                return "There was an error processing your request, please try again."

            slack_teams_controller.teams[team_name].set("subreddit", subreddit)
            try:
                cur_bot[team_name].halt = True
            except AttributeError:
                pass

            slack_teams_controller.add_bot(team_name)

            return "Successfully added Slack team and linked to subreddit. Enjoy!"

    @new_app.route('/slack/commands', methods=['POST'])
    def command():
        requests_handler = new_app.config['HANDLER']
        slack_request = utils.slack.SlackRequest(request, SLACK_COMMANDS_TOKEN)
        if slack_request.is_valid:

            response = requests_handler.handle_command(slack_request)
            return Response(response=response.get_json(), mimetype="application/json")

        else:
            return "Invalid request token."

    @new_app.route('/slack/action-endpoint', methods=['POST'])
    def button_response():
        requests_handler = new_app.config['HANDLER']
        slack_request = utils.slack.SlackRequest(request, SLACK_COMMANDS_TOKEN)
        if slack_request.is_valid:

            response = requests_handler.handle_button(slack_request)
            if response is None:
                return Response(status=200)

            return Response(response=response.get_json(), mimetype="application/json")

        else:
            return "Invalid request token."

    return new_app



