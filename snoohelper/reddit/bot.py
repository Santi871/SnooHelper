import re
import time
from threading import Thread
import traceback
import imgurpython.helpers.error
import praw
import praw.exceptions
import prawcore.exceptions
import puni
from peewee import OperationalError, IntegrityError, DoesNotExist, SqliteDatabase
import datetime
import requests.exceptions
from retrying import retry

from snoohelper.database.models import UserModel, AlreadyDoneModel, SubmissionModel, UnflairedSubmissionModel, db, Proxy
from snoohelper.database.models import FilterModel
from snoohelper.utils.reddit import AlreadyDoneHelper, is_banned
from snoohelper.utils.slack import own_thread
import snoohelper.utils.slack
import snoohelper.utils.exceptions
import snoohelper.utils.reddit
import snoohelper.utils.credentials
from .bot_modules.flair_enforcer import FlairEnforcer
from .bot_modules.summary_generator import SummaryGenerator
from .bot_modules.user_warnings import UserWarnings
from .bot_modules.filters import FiltersController
from .bot_modules.floodgate import Floodgate

REDDIT_APP_ID = snoohelper.utils.credentials.get_token("REDDIT_APP_ID", "credentials")
REDDIT_APP_SECRET = snoohelper.utils.credentials.get_token("REDDIT_APP_SECRET", "credentials")
REDDIT_REDIRECT_URI = snoohelper.utils.credentials.get_token("REDDIT_REDIRECT_URI", "credentials")


def retry_if_connection_error(exc):
    if isinstance(exc, requests.exceptions.ConnectionError) or isinstance(exc, prawcore.exceptions.RequestException):
        print("Connection error")
        time.sleep(5)
        return True
    return False


class SnooHelperBot:

    def __init__(self, team, db_name):
        self.config = team
        if db_name == "snoohelper_test.db":
            user_agent = "Snoohelper 0.3 by /u/Santi871 - unittesting"
        else:
            user_agent = "Snoohelper 0.3 by /u/Santi871 - bot of /r/" + self.config.subreddit

        if isinstance(db, Proxy):
            db.initialize(SqliteDatabase(db_name, threadlocals=True, check_same_thread=False, timeout=30))
            db.connect()
            FilterModel.create_table(True)
            SubmissionModel.create_table(True)
            try:
                db.create_tables(models=[UserModel, AlreadyDoneModel, UnflairedSubmissionModel])
            except OperationalError:
                pass
            db.close()

        self.db_name = db_name
        self.halt = False
        self.webhook = self.config.webhook

        if self.config.reddit_refresh_token:
            self.r = praw.Reddit(user_agent=user_agent,
                                 client_id=REDDIT_APP_ID, client_secret=REDDIT_APP_SECRET,
                                 refresh_token=self.config.reddit_refresh_token)

            self.thread_r = praw.Reddit(user_agent=user_agent,
                                 client_id=REDDIT_APP_ID, client_secret=REDDIT_APP_SECRET,
                                 refresh_token=self.config.reddit_refresh_token)

        else:
            self.r = praw.Reddit(user_agent=user_agent,
                                 client_id=REDDIT_APP_ID, client_secret=REDDIT_APP_SECRET,
                                 redirect_uri=REDDIT_REDIRECT_URI)

            self.thread_r = praw.Reddit(user_agent=user_agent,
                                 client_id=REDDIT_APP_ID, client_secret=REDDIT_APP_SECRET,
                                 redirect_uri=REDDIT_REDIRECT_URI)

        self.subreddit = self.thread_r.subreddit(self.config.subreddit)
        self.subreddit_name = self.subreddit.display_name
        self.already_done_helper = AlreadyDoneHelper()

        if db_name != "snoohelper_test.db":
            t = Thread(target=self._init_modules, daemon=False)
            t.start()
        else:
            self._init_modules()

    def _init_modules(self):
        self.user_warnings = None
        self.spam_cruncher = None
        self.flair_enforcer = None
        self.botbans = False
        self.watch_stickies = False
        self.un = None
        self.summary_generator = None
        self.filters_controller = None
        self.floodgate = None
        users_tracked = False

        if 'botbans' in self.config.modules:
            self.botbans = True

        if "userwarnings" in self.config.modules:
            self.user_warnings = UserWarnings(self.subreddit_name, self.webhook, 10, 5, 1, botbans=self.botbans)
            users_tracked = True

        if "flairenforce" in self.config.modules:
            sample_submission = list(self.subreddit.new(limit=1))[0]
            self.flair_enforcer = FlairEnforcer(self.r, self.subreddit_name, sample_submission)

        if "usernotes" in self.config.modules:
            self.un = puni.UserNotes(self.r, self.subreddit)

        if "floodgate" in self.config.modules:
            self.floodgate = Floodgate(faq_term_count_threshold=2)

        if "filters" in self.config.modules:
            self.filters_controller = FiltersController(self.subreddit_name)
        try:
            self.summary_generator = SummaryGenerator(self.subreddit_name, self.config.reddit_refresh_token,
                                                      spamcruncher=self.spam_cruncher, users_tracked=users_tracked,
                                                      botbans=self.botbans, un=self.un)

        except imgurpython.helpers.error.ImgurClientError:
            print("IMGUR service unavailable")
            print("Summary generation not available")
            raise

        print("Done initializing | " + self.config.subreddit)
        self.do_work()

    def botban(self, user, author, replace_original=False):
        response = snoohelper.utils.slack.SlackResponse(replace_original=replace_original)
        try:
            redditor = self.r.redditor(user)
            username = redditor.name
        except prawcore.exceptions.NotFound:
            response.add_attachment(title="Error: user not found.", color='danger')
            return response

        if self.botbans:
            user, _ = UserModel.get_or_create(username=redditor.name.lower(), subreddit=self.subreddit_name)
            if not user.shadowbanned:
                user.shadowbanned = True
                user.save()
                attachment = response.add_attachment(title="User /u/%s has been botbanned." % user.username,
                                        title_link="https://reddit.com/u/" + user.username, color='good',
                                                     callback_id="botban")
                attachment.add_field("Author", author)
            else:
                raise snoohelper.utils.exceptions.UserAlreadyBotbanned
        else:
            response.add_attachment(text='Error: botbans are not enabled for this team.', color='danger')
        return response

    def unbotban(self, user, author, replace_original=False):
        response = snoohelper.utils.slack.SlackResponse(replace_original=replace_original)
        try:
            redditor = self.r.redditor(user)
            username = redditor.name
        except prawcore.exceptions.NotFound:
            response.add_attachment(title="Error: user not found.", color='danger')
            return response

        if self.botbans:
            user, _ = UserModel.get_or_create(username=redditor.name.lower(), subreddit=self.subreddit_name)
            if user.shadowbanned:
                user.shadowbanned = False
                user.save()
                attachment = response.add_attachment(title="User /u/%s has been unbotbanned." % user.username,
                                                     title_link="https://reddit.com/u/" + user.username, color='good',
                                                     callback_id="unbotban")
                attachment.add_field("Author", author)
            else:
                raise snoohelper.utils.exceptions.UserAlreadyUnbotbanned
        else:
            response.add_attachment(text='Error: botbans are not enabled for this team.', color='danger')
        return response

    def track_user(self, user, replace_original=False):
        response = snoohelper.utils.slack.SlackResponse(replace_original=replace_original)
        try:
            redditor = self.r.redditor(user)
            username = redditor.name
        except prawcore.exceptions.NotFound:
            response.add_attachment(title="Error: user not found.", color='danger')
            return response

        if self.user_warnings is not None:
            user, _ = UserModel.get_or_create(username=redditor.name.lower(), subreddit=self.subreddit_name)
            if not user.tracked:
                user.tracked = True
                user.save()
                response.add_attachment(title="User /u/%s has been marked for tracking." % user.username,
                                        title_link="https://reddit.com/u/" + user.username, color='good')
            else:
                raise snoohelper.utils.exceptions.UserAlreadyTracked()
        else:
            response.add_attachment(text='Error: user tracking is not enabled for this team.', color='danger')
        return response

    def untrack_user(self, user, replace_original=False):
        response = snoohelper.utils.slack.SlackResponse(replace_original=replace_original)
        try:
            redditor = self.r.redditor(user)
            username = redditor.name
        except prawcore.exceptions.NotFound:
            response.add_attachment(title="Error: user not found.", color='danger')
            return response

        if self.user_warnings is not None:
            user, _ = UserModel.get_or_create(username=redditor.name.lower(), subreddit=self.subreddit_name)
            if user.tracked:
                user.tracked = False
                user.save()
                response.add_attachment(title="Ceasing to track user /u/%s." % user.username,
                                        title_link="https://reddit.com/u/" + user.username, color='good')
            else:
                raise snoohelper.utils.exceptions.UserAlreadyUntracked()
        else:
            response.add_attachment(text='Error: user tracking is not enabled for this team.', color='danger')
        return response

    @own_thread
    def inspect_ban(self, user, request):
        response = snoohelper.utils.slack.SlackResponse()
        try:
            banned_user = list(self.subreddit.banned(redditor=user))[0]
        except IndexError:
            response.add_attachment(text="No bans found for /u/{}.".format(user), color='danger')
            request.delayed_response(response)
            return

        attachment = response.add_attachment(title="Found a ban", text=banned_user.note)
        attachment.add_field("Ban date", value=str(datetime.datetime.fromtimestamp(banned_user.date)))
        request.delayed_response(response)

    def mute_user_warnings(self, user):
        self.user_warnings.mute_user_warnings(user, self.subreddit_name)

    def unmute_user_warnings(self, user):
        self.user_warnings.unmute_user_warnings(user, self.subreddit_name)

    def add_filter(self, filter_string, use_regex, expires):
        self.filters_controller.add_filter(filter_string, use_regex, expires)

    def remove_filter(self, filter_string):
        self.filters_controller.remove_filter(filter_string)

    @own_thread
    def quick_user_summary(self, user, request):
        response = self.summary_generator.generate_quick_summary(user)
        request.delayed_response(response)

    @own_thread
    def expanded_user_summary(self, request, limit, username):
        response = snoohelper.utils.slack.SlackResponse('Processing your request... please allow a few seconds.',
                                                        replace_original=False)
        self.summary_generator.generate_expanded_summary(username, limit, request)
        return response

    def scan_submissions(self):
        db.connect()
        submissions = self.subreddit.new(limit=50)
        self.check_timed_submissions()
        if self.flair_enforcer is not None:
            self.flair_enforcer.check_submissions()

        if self.floodgate is not None:
            self.floodgate.check_all()

        for submission in submissions:
            if self.flair_enforcer is not None and submission.link_flair_text is None:
                self.flair_enforcer.add_submission(submission)

            try:
                self.already_done_helper.add(submission.id, self.subreddit_name)
            except IntegrityError:
                continue

            if self.filters_controller is not None:
                results = self.filters_controller.check_all(submission.title)
                if results:
                    self.subreddit.mod.remove(submission)

            if self.floodgate is not None:
                self.floodgate.accumulate_title(submission.title, submission.created_utc)

            try:
                user = UserModel.get(UserModel.username == submission.author.name.lower() and
                                     UserModel.subreddit == submission.subreddit.display_name)
            except DoesNotExist:
                continue

            if user.shadowbanned:
                self.subreddit.mod.remove(submission)

            if self.user_warnings is not None:
                if user.tracked:
                    self.user_warnings.send_warning(submission)

                self.user_warnings.check_user_offenses(user)
        db.close()

    def scan_modlog(self):
        subreddit = self.subreddit
        relevant_actions = ('removecomment', 'removelink', 'approvelink', 'approvecomment', 'banuser')

        db.connect()
        modlog = list(subreddit.mod.log(limit=100))
        new_items = 0

        for item in modlog:
            try:
                self.already_done_helper.add(item.id, item.subreddit)
                new_items += 1
            except IntegrityError:
                continue

            if item.action in relevant_actions:
                user, _ = UserModel.get_or_create(username=item.target_author.lower(), subreddit=item.subreddit)

                if item.action == 'removecomment':
                    user.removed_comments += 1
                elif item.action == 'removelink':
                    user.removed_submissions += 1
                elif item.action == 'approvelink':
                    user.approved_submissions += 1
                elif item.action == 'approvecomment':
                    user.approved_comments += 1
                elif item.action == 'banuser':
                    try:
                        ban_length = int(re.findall('\d+', item.details)[0])
                    except IndexError:
                        ban_length = None

                    ban_target = item.target_author
                    ban_author = item._mod
                    ban_reason = item.description + " | /u/" + ban_author

                    if ban_target != "[deleted]" and is_banned(self.subreddit, user) and \
                                     "| /u/" not in item.description:

                        # Change to True to issue bans
                        if False:
                            self.subreddit.banned.add(ban_target, ban_reason=ban_reason, duration=ban_length)

                        print("Banned: {}, reason: {}, duration: {}".format(ban_target, ban_reason, ban_length))

                    if self.un is not None:
                        snoohelper.utils.reddit.add_ban_note(self.un, item)
                    user.bans += 1
                elif item.action == 'unbanuser':
                    if self.un is not None:
                        snoohelper.utils.reddit.add_ban_note(self.un, item, unban=True)
                user.save()
                self.user_warnings.check_user_offenses(user)

        db.close()

    @own_thread
    def message_modmail(self, message, author, request):
        response = snoohelper.utils.slack.SlackResponse("Message sent.")

        message += '\n\n---\n\n_Message sent from Slack via SnooHelper by Slack user @' + author + '_'
        try:
            self.subreddit.message("Message sent from Slack via SnooHelper", message)
        except prawcore.exceptions.Forbidden:
            response = snoohelper.utils.slack.SlackResponse("Message failed to send. Insufficient permissions.")
        request.delayed_response(response)

    @own_thread
    def import_botbans(self, botbans_string, request):
        botbans_string = botbans_string.replace("'", "")
        botbans_string = botbans_string.replace('"', "")
        botbans_string = botbans_string.replace("[", "")
        botbans_string = botbans_string.replace("]", "")
        botbans_string = botbans_string.replace(" ", "")
        users = botbans_string.split(',')
        n = 0
        db.connect()
        for user in users:
            user_record, _ = UserModel.get_or_create(username=user.lower(), subreddit=self.subreddit_name)
            user_record.shadowbanned = True
            user_record.save()
            n += 1
        db.close()

        response = snoohelper.utils.slack.SlackResponse()
        response.add_attachment(text="Botbans imported successfully. Number of botbans imported: {}.".format(n),
                                color='good')
        request.delayed_response(response)

    def export_botbans(self):
        exported_string = "["
        db.connect()
        for user in UserModel.select().where(UserModel.shadowbanned and UserModel.subreddit == self.subreddit_name):
            s = "'{}',".format(user.username)
            exported_string += s
        db.close()
        exported_string = exported_string[:-1] + "]"
        return snoohelper.utils.slack.SlackResponse(exported_string)

    @own_thread
    def add_watched_comment(self, comment_id, request):
        comment = self.r.comment(comment_id)
        db.connect()
        submission, _ = SubmissionModel.get_or_create(submission_id=comment.submission.id,
                                                      subreddit=self.subreddit_name)
        submission.sticky_cmt_id = comment.id
        submission.save()
        db.close()
        response = snoohelper.utils.slack.SlackResponse("Will remove replies to comment: " + comment.id)
        request.delayed_response(response)

    def check_timed_submissions(self):
        db.connect()
        submissions = SubmissionModel.select().where(SubmissionModel.subreddit == self.subreddit_name and
                                                     SubmissionModel.approve_at)
        for submission in submissions:
            if time.time() > submission.approve_at.timestamp():
                submission.delete_instance()
                submission = self.r.submission(submission.submission_id)
                self.subreddit.mod.approve(submission)
                message = snoohelper.utils.slack.SlackResponse("Approved timed submission: " + submission.permalink)
                self.webhook.send_message(message)

        submissions = SubmissionModel.select().where(SubmissionModel.subreddit == self.subreddit_name and
                                                     SubmissionModel.unlock_at)
        for submission in submissions:
            if time.time() > submission.unlock_at.timestamp():
                submission.delete_instance()
                submission = self.r.submission(submission.submission_id)
                self.subreddit.mod.unlock(submission)
                message = snoohelper.utils.slack.SlackResponse("Unlocked timed submission: " + submission.permalink)
                self.webhook.send_message(message)

        submissions = SubmissionModel.select().where(SubmissionModel.subreddit == self.subreddit_name and
                                                     SubmissionModel.lock_at)
        for submission in submissions:
            if time.time() > submission.lock_at.timestamp():
                submission.delete_instance()
                submission = self.r.submission(submission.submission_id)
                self.subreddit.mod.lock(submission)
                message = snoohelper.utils.slack.SlackResponse("Locked timed submission: " + submission.permalink)
                self.webhook.send_message(message)
        db.close()

    @own_thread
    def add_timed_submission(self, submission_id, action, hours, request):
        db.connect()
        response = None
        if action == "approve":
            submission = self.r.submission(submission_id)
            self.subreddit.mod.remove(submission)
            submission, _ = SubmissionModel.get_or_create(submission_id=submission_id, subreddit=self.subreddit_name)
            submission.approve_at = hours * 3600 + time.time()
            submission.save()
            response = snoohelper.utils.slack.SlackResponse("Will approve in {} hours.".format(hours))
        elif action == "unlock":
            submission = self.r.submission(submission_id)
            self.subreddit.mod.lock(submission)
            submission, _ = SubmissionModel.get_or_create(submission_id=submission_id, subreddit=self.subreddit_name)
            submission.unlock_at = hours * 3600 + time.time()
            submission.save()
            response = snoohelper.utils.slack.SlackResponse("Will unlock in {} hours.".format(hours))
        elif action == "lock":
            submission, _ = SubmissionModel.get_or_create(submission_id=submission_id, subreddit=self.subreddit_name)
            submission.lock_at = hours * 3600 + time.time()
            submission.save()
            response = snoohelper.utils.slack.SlackResponse("Will lock in {} hours.".format(hours))
        db.close()
        request.delayed_response(response)

    def scan_comments(self):
        db.connect()
        comments = self.subreddit.comments(limit=100)
        sticky_comments_ids = ["t1_" + submission.sticky_cmt_id for submission in
                               SubmissionModel.select().where(SubmissionModel.sticky_cmt_id)]

        for comment in comments:
            try:
                self.already_done_helper.add(comment.id, self.subreddit_name)
            except IntegrityError:
                continue

            try:
                user = UserModel.get(UserModel.username == comment.author.name.lower(),
                                     UserModel.subreddit == comment.subreddit.display_name)
            except DoesNotExist:
                continue

            if user.shadowbanned:
                self.subreddit.mod.remove(comment)
            if user.tracked:
                self.user_warnings.send_warning(comment)
            if comment.parent_id in sticky_comments_ids:
                self.subreddit.mod.remove(comment)

            self.user_warnings.check_user_offenses(user)
        db.close()

    def monitor_queue(self, last_warned_modqueue):
        modqueue = list(self.subreddit.mod.modqueue(limit=100))
        if len(modqueue) > 30 and time.time() - last_warned_modqueue > 7200:
            message = snoohelper.utils.slack.SlackResponse()
            message.add_attachment(title='Warning: modqueue has 30> items', text='Please clean modqueue.',
                                   color='warning')
            last_warned_modqueue = time.time()
            self.webhook.send_message(message)
        return last_warned_modqueue

    def do_work(self):
        last_warned_modqueue = 0
        while not self.halt:
            try:
                if self.user_warnings is not None:
                    try:
                        self.scan_modlog()
                    except TypeError:
                        pass

                if self.user_warnings is not None or self.botbans or self.flair_enforcer is not None:
                    self.scan_submissions()

                if self.botbans or self.user_warnings:
                    self.scan_comments()

                if "watchqueues" in self.config.modules:
                    last_warned_modqueue = self.monitor_queue(last_warned_modqueue)

                if self.db_name == "snoohelper_test.db":
                    break
                time.sleep(20)
            except (requests.exceptions.ConnectionError, requests.exceptions.RequestException,
                    prawcore.exceptions.RequestException):
                time.sleep(2)
                continue
            except:
                print(traceback.format_exc())
                time.sleep(5)
                continue
