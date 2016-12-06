import utils.slack as utils
from database.models import UserModel
import time


class UserWarnings:

    def __init__(self, subreddit, webhook, comment_threshold, submission_threshold, ban_threshold, botbans=False):
        self.webhook = webhook
        self.subreddit = subreddit
        self.comment_threshold = comment_threshold
        self.submission_threshold = submission_threshold
        self.ban_threshold = ban_threshold
        self.botbans = botbans

    def check_user_offenses(self, user):
        message = utils.SlackResponse()
        send = False
        attachment = None

        if isinstance(user, str):
            user, _ = UserModel.get_or_create(username=user.lower(), subreddit=self.subreddit)

        if user.removed_comments > self.comment_threshold:
            attachment = message.add_attachment(title="Warning regarding user /u/" + user.username,
                                    title_link="https://reddit.com/u/" + user.username,
                                    color='#5c96ab',
                                    text="User has had %s> comments removed. Please check profile history." %
                                    str(self.comment_threshold), callback_id="check_user_offenses")
            send = True

        if user.removed_submissions > self.submission_threshold:
            attachment = message.add_attachment(title="Warning regarding user /u/" + user.username,
                                                 title_link="https://reddit.com/u/" + user.username,
                                                 color='#5c96ab',
                                                 text="User has had %s> submissions removed. Please check profile"
                                                      " history." %
                                                      str(self.submission_threshold), callback_id="check_user_offenses")
            send = True

        if user.bans > self.ban_threshold:
            attachment = message.add_attachment(title="Warning regarding user /u/" + user.username,
                                                 title_link="https://reddit.com/u/" + user.username,
                                                 color='#5c96ab',
                                                 text="User has been banned %s> times. Please check profile history." %
                                                      str(self.ban_threshold), callback_id="check_user_offenses")
            send = True

        try:
            last_warned_ts = user.last_warned.timestamp()
        except AttributeError:
            last_warned_ts = 0

        if not user.warnings_muted and send and time.time() - last_warned_ts > 86400:
            attachment.add_button("Verify", value="verify", style='primary')

            if not user.tracked:
                attachment.add_button("Track", value="track_" + user.username)
            else:
                attachment.add_button("Untrack", value="untrack_" + user.username)

            if self.botbans and not user.shadowbanned:
                attachment.add_button("Botban", value="botban_" + user.username, style='danger')
            elif self.botbans and user.shadowbanned:
                attachment.add_button("Unbotban", value="unbotban_" + user.username, style='danger')
            attachment.add_button("Mute user's warnings", value="mutewarnings_" + user.username, style='danger')

            user.last_warned = time.time()
            user.save()
            self.webhook.send_message(message)

    def check_user_posts(self, thing):
        user, _ = UserModel.get_or_create(username=thing.author.name.lower(), subreddit=thing.subreddit.display_name)

        if user.tracked:
            message = utils.SlackResponse("New post by user /u/" + user.username)

            try:
                title = thing.submission.title
            except AttributeError:
                title = thing.title
            attachment = message.add_attachment(title=title, title_link=thing.permalink, text=thing.body,
                                                color='#5c96ab', callback_id="check_user_posts")
            attachment.add_button("Verify", value="verify", style='primary')
            attachment.add_button("Untrack", value="untrack_" + user.username)

            if self.botbans and not user.shadowbanned:
                attachment.add_button("Botban", value="botban_" + user.username, style='danger')
            elif self.botbans and user.shadowbanned:
                attachment.add_button("Unbotban", "unbotban_" + user.username, style='danger')
            self.webhook.send_message(message)

    def send_warning(self, thing):
        user, _ = UserModel.get_or_create(username=thing.author.name.lower(), subreddit=thing.subreddit.display_name)
        message = utils.SlackResponse("New post by user /u/" + user.username)

        try:
            title = thing.submission.title
        except AttributeError:
            title = thing.title

        try:
            body = thing.body
        except AttributeError:
            body = None

        attachment = message.add_attachment(title=title, title_link=thing.permalink(), text=body,
                                            color='#5c96ab', callback_id="send_warning")
        attachment.add_button("Verify", value="verify", style='primary')
        attachment.add_button("Untrack", value="untrack_" + user.username)

        if self.botbans and not user.shadowbanned:
            attachment.add_button("Botban", value="botban_" + user.username, style='danger')
        elif self.botbans and user.shadowbanned:
            attachment.add_button("Unbotban", value="unbotban_" + user.username, style='danger')

        self.webhook.send_message(message)

    @staticmethod
    def mute_user_warnings(user, subreddit):
        user = UserModel.get(UserModel.username == user.lower() and UserModel.subreddit == subreddit)
        user.warnings_muted = True
        user.save()
