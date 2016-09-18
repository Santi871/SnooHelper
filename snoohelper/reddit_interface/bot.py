from time import sleep, time

import OAuth2Util
import praw
import puni
from peewee import OperationalError, IntegrityError
from retrying import retry
from snoohelper.reddit_interface import bot_threading
from snoohelper.utils import utils as utils
from .bot_modules.summary_generator.summary_generator import SummaryGenerator
from .bot_modules.spam_cruncher.spam_cruncher import SpamCruncher
from .database_models import UserModel, AlreadyDoneModel, db

db.connect()

try:
    db.create_tables(models=[UserModel, AlreadyDoneModel])
except OperationalError:
    pass
db.close()


class RedditBot:

    """Primary Reddit interface - interacts with Reddit on behalf of the user/subreddit/Slack team"""

    def __init__(self, team_config):
        self.team_config = team_config
        self.oauth_config_filename = team_config.team_name + "_oauth.ini"
        self.subreddit_name = team_config.subreddit
        self.already_done_helper = utils.AlreadyDoneHelper()
        handler = praw.handlers.MultiprocessHandler()
        self.r = praw.Reddit(user_agent="windows:SnooHelper 0.1 by /u/santi871", handler=handler)
        self._authenticate()
        self.subreddit = self.r.get_subreddit(self.subreddit_name)
        self.webhook = utils.IncomingWebhook(team_config.webhook_url)

        self.un = None
        if "usernotes" in team_config.modules:
            # self.un = puni.UserNotes(self.r, self.subreddit)
            pass
        self.spam_cruncher = SpamCruncher(filename='config.ini', section='spamcruncher')
        self.spam_cruncher.set_reddit(self.r)
        self.summary_generator = SummaryGenerator(self.subreddit_name, self.team_config.access_token,
                                                  spamcruncher=self.spam_cruncher, users_tracked=True)

        self.scan_modlog()
        # self.scan_submissions()

    @retry(stop_max_attempt_number=4)
    def _authenticate(self):
        o = OAuth2Util.OAuth2Util(self.r, configfile=self.oauth_config_filename)
        o.refresh(force=True)
        self.r.config.api_request_delay = 1

    def botban(self, user, subreddit, author, replace_original=False):
        response = utils.SlackResponse(replace_original=replace_original)
        try:
            redditor = self.r.get_redditor(user_name=user)
        except praw.errors.NotFound:
            response.add_attachment(text='Error: user not found', color='danger')
            return response

        user, _ = UserModel.get_or_create(username=redditor.name, subreddit=subreddit)

        if not user.shadowbanned:
            user.shadowbanned = True
            user.save()
            attachment = response.add_attachment(title="User /u/%s has been botbanned.",
                                    title_link="https://reddit.com/u/" + user.username, color='good')
            attachment.add_field("Author", author)
            return response
        else:
            response.add_attachment(text='Error: user is already botbanned', color='danger')
            return response

    def unbotban(self, user, subreddit, author, replace_original=False):
        response = utils.SlackResponse(replace_original=replace_original)
        try:
            redditor = self.r.get_redditor(user_name=user)
        except praw.errors.NotFound:
            response.add_attachment(text='Error: user not found', color='danger')
            return response

        user, _ = UserModel.get_or_create(username=redditor.name, subreddit=subreddit)

        if user.shadowbanned:
            user.shadowbanned = False
            user.save()
            attachment = response.add_attachment(title="User /u/%s has been unbotbanned.",
                                                 title_link="https://reddit.com/u/" + user.username, color='good')
            attachment.add_field("Author", author)
            return response
        else:
            response.add_attachment(text='Error: user is not botbanned', color='danger')
            return response

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
        db.connect()

        while True:

            o.refresh()
            modlog = list(subreddit.get_mod_log(limit=20))
            new_items = 0

            for item in modlog:
                try:
                    self.already_done_helper.add(item.id, item.subreddit)
                    new_items += 1
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
            sleep(30)

    @bot_threading.own_thread
    def scan_comments(self, r, o):
        db.connect()
        while True:
            o.refresh()
            comments = r.get_comments(self.subreddit_name, limit=50, sort='new')

            for comment in comments:
                try:
                    self.already_done_helper.add(comment.id, self.subreddit_name)
                except IntegrityError:
                    continue
            sleep(5)

    @bot_threading.own_thread
    def scan_submissions(self, r, o):
        db.connect()
        self.spam_cruncher.set_reddit(r)
        subreddit = r.get_subreddit(self.subreddit_name)
        while True:
            o.refresh()
            submissions = subreddit.get_new(limit=20)

            for submission in submissions:
                try:
                    self.already_done_helper.add(submission.id, self.subreddit_name)
                except IntegrityError:
                    continue

                if not submission.is_self:
                    results = self.spam_cruncher.analyze_user(submission.author.name)
                    print(results.get_json(indent=4))

            sleep(60)

    @bot_threading.own_thread
    def monitor_queues(self, r, o):
        last_warned_modqueue = 0
        last_warned_unmoderated = 0
        while True:
            o.refresh()
            modqueue = list(r.get_mod_queue(self.subreddit_name))
            unmoderated = list(r.get_unmoderated(self.subreddit_name))

            if len(modqueue) > 30 and time() - last_warned_modqueue > 7200:
                message = utils.SlackResponse()
                message.add_attachment(title='Warning: modqueue has 30> items', text='Please clean modqueue.',
                                       color='warning')
                last_warned_modqueue = time()
                self.webhook.send_message(message)
            if len(unmoderated) > 30 and time() - last_warned_unmoderated > 7200:
                message = utils.SlackResponse()
                message.add_attachment(title='Warning: unmoderated queue has 30> items',
                                       text='Please clean unmoderated queue.',
                                       color='warning')
                last_warned_unmoderated = time()
                self.webhook.send_message(message)

            sleep(1800)









