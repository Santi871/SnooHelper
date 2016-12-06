import re
import time
from threading import Thread

import imgurpython.helpers.error
import praw
import praw.exceptions
import prawcore.exceptions
import puni
from peewee import OperationalError, IntegrityError, DoesNotExist
from retrying import retry
import snoohelper.utils
from snoohelper.utils.slack import own_thread

from snoohelper.database.models import UserModel, AlreadyDoneModel, SubmissionModel, UnflairedSubmissionModel, db
from snoohelper.utils.reddit import AlreadyDoneHelper, is_banned
from .bot_modules.flair_enforcer import FlairEnforcer
from .bot_modules.summary_generator import SummaryGenerator
from .bot_modules.user_warnings import UserWarnings

REDDIT_APP_ID = snoohelper.utils.credentials.get_token("REDDIT_APP_ID", "credentials")
REDDIT_APP_SECRET = snoohelper.utils.credentials.get_token("REDDIT_APP_SECRET", "credentials")
REDDIT_REDIRECT_URI = snoohelper.utils.credentials.get_token("REDDIT_REDIRECT_URI", "credentials")


db.connect()

try:
    db.create_tables(models=[UserModel, AlreadyDoneModel, SubmissionModel, UnflairedSubmissionModel])
except OperationalError:
    pass
db.close()


class SnooHelperBot:

    def __init__(self, team):
        self.halt = False
        self.config = team
        self.webhook = self.config.webhook

        if self.config.reddit_refresh_token:
            self.r = praw.Reddit(user_agent="Snoohelper 0.1 by /u/Santi871",
                                 client_id=REDDIT_APP_ID, client_secret=REDDIT_APP_SECRET,
                                 refresh_token=self.config.reddit_refresh_token)

            self.thread_r = praw.Reddit(user_agent="Snoohelper 0.1 by /u/Santi871",
                                 client_id=REDDIT_APP_ID, client_secret=REDDIT_APP_SECRET,
                                 refresh_token=self.config.reddit_refresh_token)

        else:
            self.r = praw.Reddit(user_agent="Snoohelper 0.1 by /u/Santi871",
                                 client_id=REDDIT_APP_ID, client_secret=REDDIT_APP_SECRET,
                                 redirect_uri=REDDIT_REDIRECT_URI)

            self.thread_r = praw.Reddit(user_agent="Snoohelper 0.1 by /u/Santi871",
                                 client_id=REDDIT_APP_ID, client_secret=REDDIT_APP_SECRET,
                                 redirect_uri=REDDIT_REDIRECT_URI)

        self.subreddit = self.thread_r.subreddit(self.config.subreddit)
        self.subreddit_name = self.subreddit.display_name
        self.already_done_helper = AlreadyDoneHelper()

        t = Thread(target=self._init_modules)
        t.start()

    def _init_modules(self):
        self.user_warnings = None
        self.spam_cruncher = None
        self.flair_enforcer = None
        self.botbans = False
        self.watch_stickies = False
        self.un = None
        self.summary_generator = None
        users_tracked = False

        if 'botbans' in self.config.modules:
            self.botbans = True

        if "userwarnings" in self.config.modules:
            self.user_warnings = UserWarnings(self.subreddit_name, self.webhook, 10, 5, 1, botbans=self.botbans)
            users_tracked = True

        if "flairenforce" in self.config.modules:
            self.flair_enforcer = FlairEnforcer(self.r, self.subreddit_name)

        if "usernotes" in self.config.modules:
            self.un = puni.UserNotes(self.r, self.subreddit)

        if "watchstickies" in self.config.modules:
            self.watch_stickies = True

        try:
            self.summary_generator = SummaryGenerator(self.subreddit_name, self.config.reddit_refresh_token,
                                                      spamcruncher=self.spam_cruncher, users_tracked=users_tracked,
                                                      botbans=self.botbans, un=self.un)

        except imgurpython.helpers.error.ImgurClientError:
            print("IMGUR service unavailable")
            print("Summary generation not available")

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
        if self.flair_enforcer is not None:
            self.flair_enforcer.check_submissions()

        for submission in submissions:
            if self.flair_enforcer is not None and submission.link_flair_text is None:
                self.flair_enforcer.add_submission(submission)

            try:
                self.already_done_helper.add(submission.id, self.subreddit_name)
            except IntegrityError:
                continue

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
        relevant_actions = ('removecomment', 'removelink', 'approvelink', 'approvecomment', 'banuser', 'sticky')

        db.connect()
        modlog = list(subreddit.mod.log(limit=20))
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
                elif item.action == 'sticky' and "watchstickies" in self.config.modules and \
                        item.target_fullname.startswith('t1'):
                    comment = self.thread_r.comment(item.target_fullname.strip("t1"))

                    try:
                        submission = comment.submission
                    except praw.exceptions.PRAWException as e:
                        print("PRAW Exception, " + str(e))

                    try:
                        if "flair" not in comment.body:
                            SubmissionModel.create(submission_id=submission.id, sticky_cmt_id=comment.id,
                                                   subreddit=submission.subreddit.display_name)
                    except (TypeError, praw.exceptions.PRAWException) as e:
                        print("PRAW Exception, " + str(e))

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

    def scan_comments(self):
        comments = self.subreddit.comments(limit=50)
        sticky_comments_ids = ["t1_" + submission.sticky_cmt_id for submission in SubmissionModel.select()]

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
            if self.watch_stickies and comment.parent_id in sticky_comments_ids:
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
        time.sleep(1800)
        return last_warned_modqueue

    @retry
    def do_work(self):
        last_warned_modqueue = 0
        while not self.halt:
            if "watchstickies" in self.config.modules or self.user_warnings is not None:
                self.scan_modlog()

            if self.user_warnings is not None or self.botbans or self.flair_enforcer is not None:
                self.scan_submissions()

            if self.botbans or self.user_warnings:
                self.scan_comments()

            if "watchqueues" in self.config.modules:
                last_warned_modqueue = self.monitor_queue(last_warned_modqueue)

            time.sleep(self.config.sleep)



