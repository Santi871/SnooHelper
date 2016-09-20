from time import sleep, time
import logging
import OAuth2Util
import praw
import puni
from peewee import OperationalError, IntegrityError
from retrying import retry
from snoohelper.reddit_interface import bot_threading
from snoohelper.utils import utils as utils
from .bot_modules.summary_generator.summary_generator import SummaryGenerator
from .bot_modules.spam_cruncher.spam_cruncher import SpamCruncher
from .bot_modules.user_warnings.user_warnings import UserWarnings
from .bot_modules.flair_enforcer.flair_enforcer import FlairEnforcer
from .database_models import UserModel, AlreadyDoneModel, SubmissionModel, db
from peewee import DoesNotExist

db.connect()

try:
    db.create_tables(models=[UserModel, AlreadyDoneModel, SubmissionModel])
except OperationalError:
    pass
db.close()


class RedditBot:

    """Primary Reddit interface - interacts with Reddit on behalf of the user/subreddit/Slack team"""

    def __init__(self, team_config):
        self.logger = logging.getLogger('RedditBot of ' + team_config.team_name)
        self.logger.info("Initializing RedditBot...")
        self.team_config = team_config
        self.oauth_config_filename = team_config.team_name + "_oauth.ini"
        self.subreddit_name = team_config.subreddit
        self.already_done_helper = utils.AlreadyDoneHelper(self.logger)
        handler = praw.handlers.MultiprocessHandler()
        self.r = praw.Reddit(user_agent="windows:SnooHelper 0.1 by /u/santi871", handler=handler)
        self._authenticate()
        self.subreddit = self.r.get_subreddit(self.subreddit_name)
        self.subreddit_name = self.subreddit.display_name
        self.webhook = team_config.webhook
        self._init_modules()
        self.logger.info("Done initializing RedditBot.")

    def _init_modules(self):
        self.logger.info("Initializing modules...")
        self.un = None
        self.user_warnings = None
        self.spam_cruncher = None
        self.flair_enforcer = None
        users_tracked = False
        self.botbans = False

        if 'botbans' in self.team_config.modules:
            self.botbans = True

        if "usernotes" in self.team_config.modules:
            self.un = puni.UserNotes(self.r, self.subreddit)

        if "userwarnings" in self.team_config.modules:
            self.user_warnings = UserWarnings(self.subreddit_name, self.webhook, 10, 5, 1, botbans=self.botbans)
            users_tracked = True

        if "spamwatch" in self.team_config.modules:
            self.spam_cruncher = SpamCruncher(filename='config.ini', section='spamcruncher')
            self.scan_submissions()

        if "flairenforcer" in self.team_config.modules:
            self.flair_enforcer = FlairEnforcer(self.r, self.subreddit_name)

        if "watchstickies" in self.team_config.modules or self.user_warnings is not None:
            self.scan_modlog()

        if self.user_warnings is not None or self.botbans or self.flair_enforcer is not None:
            self.scan_submissions()

        if self.user_warnings or self.botbans:
            self.scan_comments()

        if "watchqueue" in self.team_config.modules:
            self.monitor_queue()

        self.summary_generator = SummaryGenerator(self.subreddit_name, self.team_config.access_token,
                                                  spamcruncher=self.spam_cruncher, users_tracked=users_tracked,
                                                  botbans=self.botbans, un=self.un)

        self.logger.info("Done initializing modules.")

    @retry(stop_max_attempt_number=4)
    def _authenticate(self):
        self.logger.info("Authenticating Reddit instance...")
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

        if self.botbans:
            user, _ = UserModel.get_or_create(username=redditor.name, subreddit=subreddit)
            if not user.shadowbanned:
                user.shadowbanned = True
                user.save()
                attachment = response.add_attachment(title="User /u/%s has been botbanned.",
                                        title_link="https://reddit.com/u/" + user.username, color='good')
                attachment.add_field("Author", author)
            else:
                response.add_attachment(text='Error: user is already botbanned', color='danger')
        else:
            response.add_attachment(text='Error: botbans are not enabled for this team.', color='danger')
        return response

    def unbotban(self, user, author, replace_original=False):
        response = utils.SlackResponse(replace_original=replace_original)
        try:
            redditor = self.r.get_redditor(user_name=user)
        except praw.errors.NotFound:
            response.add_attachment(text='Error: user not found', color='danger')
            return response

        if self.botbans:
            user, _ = UserModel.get_or_create(username=redditor.name, subreddit=self.subreddit_name)
            if user.shadowbanned:
                user.shadowbanned = False
                user.save()
                attachment = response.add_attachment(title="User /u/%s has been unbotbanned.",
                                                     title_link="https://reddit.com/u/" + user.username, color='good')
                attachment.add_field("Author", author)
            else:
                response.add_attachment(text='Error: user is not botbanned', color='danger')
        else:
            response.add_attachment(text='Error: botbans are not enabled for this team.', color='danger')
        return response

    def track_user(self, user, replace_original=False):
        response = utils.SlackResponse(replace_original=replace_original)
        try:
            redditor = self.r.get_redditor(user_name=user)
        except praw.errors.NotFound:
            response.add_attachment(text='Error: user not found', color='danger')
            return response

        if self.user_warnings is not None:
            user, _ = UserModel.get_or_create(username=redditor.name, subreddit=self.subreddit_name)
            if not user.tracked:
                user.tracked = True
                user.save()
                response.add_attachment(title="User /u/%s has been marked for tracking.",
                                        title_link="https://reddit.com/u/" + user.username, color='good')
            else:
                response.add_attachment(text='Error: user is already being tracked', color='danger')
        else:
            response.add_attachment(text='Error: user tracking is not enabled for this team.', color='danger')
        return response

    def untrack_user(self, user, replace_original=False):
        response = utils.SlackResponse(replace_original=replace_original)
        try:
            redditor = self.r.get_redditor(user_name=user)
        except praw.errors.NotFound:
            response.add_attachment(text='Error: user not found', color='danger')
            return response

        if self.user_warnings is not None:
            user, _ = UserModel.get_or_create(username=redditor.name, subreddit=self.subreddit_name)
            if user.tracked:
                user.tracked = True
                user.save()
                response.add_attachment(title="Ceasing to track user /u/%s.",
                                        title_link="https://reddit.com/u/" + user.username, color='good')
            else:
                response.add_attachment(text='Error: user is not being tracked', color='danger')
        else:
            response.add_attachment(text='Error: user tracking is not enabled for this team.', color='danger')
        return response

    @bot_threading.own_thread
    def quick_user_summary(self, r, o, user, request):
        self.logger.info("Generating user overview: " + user)
        o.refresh()

        if self.spam_cruncher is not None:
            self.spam_cruncher.set_reddit(r)
        response = self.summary_generator.generate_quick_summary(r, username=user)
        request.delayed_response(response)

    @bot_threading.own_thread
    def expanded_user_summary(self, r, o, request, limit, username):
        self.logger.info("Generating expanded user summary: " + username)
        response = utils.SlackResponse('Processing your request... please allow a few seconds.', replace_original=False)
        o.refresh()
        self.summary_generator.generate_expanded_summary(r, username, limit, request)
        return response

    @bot_threading.own_thread
    def scan_modlog(self, r, o):
        self.logger.info("Starting scan_modlog thread...")
        subreddit = r.get_subreddit(self.subreddit_name)
        relevant_actions = ('removecomment', 'removelink', 'approvelink', 'approvecomment', 'banuser', 'sticky')

        while True:
            db.connect()
            o.refresh()
            modlog = list(subreddit.get_mod_log(limit=20))
            new_items = 0

            for item in modlog:
                try:
                    self.already_done_helper.add(item.id, item.subreddit)
                    new_items += 1
                except IntegrityError:
                    continue

                if item.action in relevant_actions:
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
                        if self.un is not None:
                            utils.add_ban_note(self.un, item)
                        user.bans += 1
                    elif item.action == 'unbanuser':
                        if self.un is not None:
                            utils.add_ban_note(self.un, item, unban=True)
                    elif item.action == 'sticky' and "watchstickies" in self.team_config.modules and \
                            item.target_fullname.startswith('t1'):
                        comment = r.get_info(thing_id=item.target_fullname)
                        submission = comment.submission

                        if "flair" not in comment.body:
                            SubmissionModel.create(submission_id=submission.id, sticky_cmt_id=comment.id,
                                                   subreddit=submission.subreddit.display_name)
                    user.save()
                    self.user_warnings.check_user_offenses(user)
            db.close()
            sleep(30)

    @bot_threading.own_thread
    def scan_comments(self, r, o):
        self.logger.info("Starting scan_comments thread...")
        while True:
            db.connect()
            o.refresh()
            comments = r.get_comments(self.subreddit_name, limit=50, sort='new')

            for comment in comments:
                try:
                    self.already_done_helper.add(comment.id, self.subreddit_name)
                except IntegrityError:
                    continue

                try:
                    user = UserModel.get(UserModel.username == comment.author.name and
                                         UserModel.subreddit == comment.subreddit.display_name)
                except DoesNotExist:
                    continue

                if user.shadowbanned:
                    self.logger.info("Removed comment by: " + user.username)
                    comment.remove()
                if user.tracked:
                    self.user_warnings.send_warning(comment)

                self.user_warnings.check_user_offenses(user)
            db.close()
            sleep(5)

    @bot_threading.own_thread
    def scan_submissions(self, r, o):
        self.logger.info("Starting scan_submissions thread...")
        if self.spam_cruncher is not None:
            self.spam_cruncher.set_reddit(r)
        subreddit = r.get_subreddit(self.subreddit_name)
        while True:
            db.connect()
            o.refresh()
            submissions = subreddit.get_new(limit=50)

            for submission in submissions:
                if self.flair_enforcer is not None and submission.link_flair_text is None:
                    self.flair_enforcer.add_submission(submission)

                try:
                    self.already_done_helper.add(submission.id, self.subreddit_name)
                except IntegrityError:
                    continue

                if not submission.is_self:
                    results = self.spam_cruncher.analyze_user(submission.author.name)
                    print(results.get_json(indent=4))

                try:
                    user = UserModel.get(UserModel.username == submission.author.name and
                                         UserModel.subreddit == submission.subreddit.display_name)
                except DoesNotExist:
                    continue

                if user.shadowbanned:
                    self.logger.info("Removed submission by: " + user.username)
                    submission.remove()
                if user.tracked:
                    self.user_warnings.send_warning(submission)

                self.user_warnings.check_user_offenses(user)
            db.close()
            sleep(60)

    @bot_threading.own_thread
    def monitor_queue(self, r, o):
        self.logger.info("Starting monitor queues thread...")
        last_warned_modqueue = 0
        while True:
            o.refresh()
            modqueue = list(r.get_mod_queue(self.subreddit_name))

            if len(modqueue) > 30 and time() - last_warned_modqueue > 7200:
                message = utils.SlackResponse()
                message.add_attachment(title='Warning: modqueue has 30> items', text='Please clean modqueue.',
                                       color='warning')
                last_warned_modqueue = time()
                self.webhook.send_message(message)
            sleep(1800)









