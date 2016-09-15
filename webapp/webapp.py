import os
import requests
from flask import Flask, request, Response, redirect
from flask_sslify import SSLify
import utils.utils as utils
from webapp.requests_handler import RequestsHandler
import praw

APP_SECRET_KEY = utils.get_token("FLASK_APP_SECRET_KEY", "credentials")
SLACK_APP_ID = utils.get_token("SLACK_APP_ID", "credentials")
SLACK_APP_SECRET = utils.get_token("SLACK_APP_SECRET", "credentials")
SLACK_COMMANDS_TOKEN = utils.get_token("SLACK_COMMANDS_TOKEN", "credentials")
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = '1'
os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = '1'

app = Flask(__name__, static_url_path='')
sslify = SSLify(app)
app.secret_key = APP_SECRET_KEY
slack_teams = utils.SlackTeamsConfig('teams.ini')
handler = RequestsHandler(slack_teams)
master_r = praw.Reddit("windows:RedditSlacker2 0.1 by /u/santi871", handler=praw.handlers.MultiprocessHandler())
# set app oauth info
team_names = dict()


@app.route("/slack/oauthcallback")
def slack_oauth_callback():
    data = {'client_id': SLACK_APP_ID, 'client_secret': SLACK_APP_SECRET, 'code': request.args.get('code')}
    response = requests.post('https://slack.com/api/oauth.access', params=data)
    response_json = response.json()
    slack_teams.add_team(response_json)
    team_names[request.remote_addr] = response_json['team_name']
    url = master_r.get_authorize_url('uniqueKey')
    return redirect(url, code=302)


@app.route('/reddit/oauthcallback', methods=['POST', 'GET'])
def reddit_oauth_callback():

    if request.method == 'GET':
        code = request.args.get('code', ' ')
        access_information = master_r.get_access_information(code)

        try:
            team_name = team_names.get(request.remote_addr)
            team_names.pop(request.remote_addr, None)
        except KeyError:
            return "There was an error processing your request, please try again."
        utils.set_team_access_credentials(team_name, access_information)
        moderated_subreddits = master_r.get_my_moderation()


'''

@app.route('/slack/commands', methods=['POST'])
def command():
    slack_request = utils.SlackRequest(request, SLACK_COMMANDS_TOKEN)
    if slack_request.is_valid:

        response = handler.command_response(slack_request, form=request.form)

        return Response(response=response.get_json(), mimetype="application/json")

    else:
        return "Invalid request token."


@app.route('/slack/action-endpoint', methods=['POST'])
def button_response():

    slack_request = utils.SlackRequest(request, SLACK_COMMANDS_TOKEN)
    if slack_request.is_valid:

        response = handler.button_response(slack_request)

        if response is None:
            return Response(status=200)

        return Response(response=response.get_json(), mimetype="application/json")

    else:
        return "Invalid request token."


@app.route('/redditslacker/status', methods=['GET'])
def check_status():
    return Response(), 200

'''