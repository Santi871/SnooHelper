from reddit_interface import bot_threading
import utils.utils as utils
from time import sleep
from peewee import OperationalError, IntegrityError
from .database_models import UserModel, AlreadyDoneModel, db
import puni
import praw
import OAuth2Util
from .bot_modules.summary_generator import summary_generator
from retrying import retry

db.connect()

try:
    db.create_tables(models=[UserModel, AlreadyDoneModel])
except OperationalError:
    pass


class RedditBot:

    """Primary Reddit interface - interacts with Reddit on behalf of the user/subreddit/Slack team"""

    def __init__(self, team):
        self.config = team
        self.oauth_config_filename = team.team_name + "_oauth.ini"
        self.subreddit_name = team.subreddit
        self.already_done_helper = utils.AlreadyDoneHelper()
        self.scan_modlog()
        handler = praw.handlers.MultiprocessHandler()
        self.r = praw.Reddit(user_agent="windows:RedditSlacker2 0.1 by /u/santi871", handler=handler)
        self._authenticate()
        self.subreddit = self.r.get_subreddit(self.subreddit_name)

        self.un = None
        if team.usernotes:
            self.un = puni.UserNotes(self.r, self.subreddit)
        self.summary_generator = summary_generator.SummaryGenerator(self.subreddit_name, self.config.access_token,
                                                                    users_tracked=True)

    @retry(stop_max_attempt_number=4)
    def _authenticate(self):
        o = OAuth2Util.OAuth2Util(self.r, configfile=self.oauth_config_filename)
        o.refresh(force=True)
        self.r.config.api_request_delay = 1

    @bot_threading.own_thread
    def quick_user_summary(self, r, o, user, request):
        o.refresh()
        response = self.summary_generator.generate_quick_summary(r, username=user)
        request.delayed_response(response)

    @bot_threading.own_thread
    def expanded_user_summary(self, r, o, request, limit, username):
        response = utils.SlackResponse('Processing your request... please allow a few seconds.', replace_original=False)
        o.refresh()
        self.summary_generator.generate_expanded_summary(r, username, limit, request)

        return response

    @bot_threading.own_thread
    def scan_modlog(self, r, o):
        subreddit = r.get_subreddit(self.subreddit_name)

        while True:
            o.refresh()
            modlog = subreddit.get_mod_log(limit=20)

            for item in modlog:
                try:
                    self.already_done_helper.add(item.id, item.subreddit)
                except IntegrityError:
                    continue
                user, _ = UserModel.get_or_create(username=item.target_author, subreddit=item.subreddit)

                if item.action == 'removecomment':
                    user.removed_comments += 1
                elif item.action == 'removelink':
                    user.removed_submissions += 1
                elif item.action == 'approvelink':
                    user.approved_submissions += 1
                elif item.action == 'approvecomment':
                    user.approved_comments += 1
                elif item.action == 'banuser':
                    user.bans += 1
                user.save()
            sleep(10)








