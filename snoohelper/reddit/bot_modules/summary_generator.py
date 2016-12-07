import datetime
import math
import os
import matplotlib.pyplot as plt
import numpy as np
import praw
import prawcore.exceptions
from imgurpython import ImgurClient
from retrying import retry
from wordcloud import WordCloud, STOPWORDS
from snoohelper.database.models import UserModel
import snoohelper.utils
from snoohelper.utils import credentials

REDDIT_APP_ID = credentials.get_token("REDDIT_APP_ID", "credentials")
REDDIT_APP_SECRET = credentials.get_token("REDDIT_APP_SECRET", "credentials")
REDDIT_REDIRECT_URI = credentials.get_token("REDDIT_REDIRECT_URI", "credentials")


class SummaryGenerator:

    """Module that generates user summaries. Requires 'read' and 'history' permissions."""

    def __init__(self, subreddit, refresh_token, spamcruncher=None, un=None, users_tracked=False, botbans=False):

        self.imgur = ImgurClient(credentials.get_token("IMGUR_CLIENT_ID", 'credentials'),
                                 credentials.get_token("IMGUR_CLIENT_SECRET", 'credentials'))
        self.users_tracked = users_tracked
        self.subreddit = subreddit
        self.un = un
        self.refresh_token = refresh_token
        self.spamcruncher = spamcruncher
        self.botbans = botbans
        self.r = praw.Reddit(user_agent="Snoohelper 0.1 by /u/Santi871",
                                 client_id=REDDIT_APP_ID, client_secret=REDDIT_APP_SECRET,
                                 refresh_token=self.refresh_token)

    @retry(stop_max_attempt_number=2)
    def generate_quick_summary(self, username):
        r = self.r

        response = snoohelper.utils.slack.SlackResponse()

        try:
            user = r.redditor(username)
            username = user.name
        except prawcore.exceptions.NotFound:
            response.add_attachment(fallback="Summary error.",
                                    title="Error: user not found.", color='danger')
            return response

        user_track, _ = UserModel.get_or_create(username=username.lower(), subreddit=self.subreddit)

        combined_karma = user.link_karma + user.comment_karma
        account_creation = str(datetime.datetime.fromtimestamp(user.created_utc))

        last_note = None
        if self.un is not None:
            notes = list(self.un.get_notes(username))
            if len(notes):
                last_note = str(notes[0].note)

        attachment = response.add_attachment(title='Overview for /u/' + user.name,
                                title_link="https://www.reddit.com/user/" + username,
                                color='#5c96ab', callback_id='user_' + username)

        attachment.add_field("Combined karma", combined_karma)
        attachment.add_field("Redditor since", account_creation)

        if self.spamcruncher is not None:
            results = self.spamcruncher.analyze_user(username)
            spammer_likelihood = 'Low'

            if results.spammer_likelihood > 100:
                spammer_likelihood = 'Moderate'
            if results.spammer_likelihood > 180:
                spammer_likelihood = 'High'

            attachment.add_field("Spammer likelihood", spammer_likelihood)

        if self.users_tracked:
            if user_track is not None:
                user_is_shadowbanned = "No"
                user_is_tracked = "No"

                comment_removals = user_track.removed_comments
                submission_removals = user_track.removed_submissions
                bans = user_track.bans
                approvals = user_track.approved_comments + user_track.approved_submissions

                if user_track.shadowbanned:
                    user_is_shadowbanned = "Yes"
                if user_track.tracked:
                    user_is_tracked = "Yes"
                if not comment_removals:
                    comment_removals = "None recorded"
                if not submission_removals:
                    submission_removals = "None recorded"
                if not bans:
                    bans = "None recorded"
                if not approvals:
                    approvals = "None recorded"

                attachment.add_field("Removed comments", comment_removals)
                attachment.add_field("Removed submissions", submission_removals)
                attachment.add_field("Bans", bans)
                attachment.add_field("Approvals", approvals)
                attachment.add_field("Shadowbanned", user_is_shadowbanned)
                attachment.add_field("Tracked", user_is_tracked)

        if last_note is not None:
            attachment.add_field("Latest usernote", last_note, short=False)

        attachment.add_button("Summary (500)", "summary_500_" + username, style='primary')
        attachment.add_button("Summary (1000)", "summary_1000_" + username, style='primary')

        if self.users_tracked and not user_track.tracked:
            attachment.add_button("Track", "track_" + user.name)
        elif self.users_tracked and user_track.tracked:
            attachment.add_button("Untrack", "untrack_" + user.name)

        if self.botbans and not user_track.shadowbanned:
            attachment.add_button("Botban", "botban_" + user.name, style='danger')
        elif self.botbans and user_track.shadowbanned:
            attachment.add_button("Unbotban", "unbotban_" + user.name, style='danger')

        return response

    @retry(stop_max_attempt_number=2)
    def generate_expanded_summary(self, username, limit, request):
        r = self.r
        response = snoohelper.utils.slack.SlackResponse(replace_original=False)

        try:
            user = r.redditor(username)
            username = user.name
        except prawcore.exceptions.NotFound:
            response.add_attachment(fallback="Summary error.",
                                    title="Error: user not found.", color='danger')
            return response

        i = 0
        total_comments = 0
        subreddit_names = []
        subreddit_total = []
        ordered_subreddit_names = []
        comments_in_subreddit = []
        ordered_comments_in_subreddit = []
        comment_lengths = []
        history = {}
        total_karma = 0
        troll_index = 0
        blacklisted_subreddits = ('theredpill', 'rage', 'atheism', 'conspiracy', 'the_donald', 'subredditcancer',
                                  'SRSsucks', 'drama', 'undelete', 'blackout2015', 'oppression', 'kotakuinaction',
                                  'tumblrinaction', 'offensivespeech', 'bixnood')
        total_negative_karma = 0
        troll_likelihood = "Low"
        color = 'good'
        x = []
        y = []
        s = []
        concatenated_comments = ""

        karma_accumulator = 0
        karma_accumulated = []
        karma_accumulated_total = []
        total_comments_read = 0

        for comment in user.comments.new(limit=limit):
            if comment.distinguished != 'moderator':
                displayname = comment.subreddit.display_name
                concatenated_comments += comment.body + " "
                i += 1

                if displayname not in subreddit_names:
                    subreddit_names.append(displayname)

                subreddit_total.append(displayname)

                total_karma = total_karma + comment.score

                x.append(datetime.datetime.utcfromtimestamp(float(comment.created_utc)))
                y.append(comment.score)
                comment_lengths.append(len(comment.body.split()))

                if comment.score < 0:
                    total_negative_karma += comment.score

                if len(comment.body) < 200:
                    troll_index += 0.1

                if displayname in blacklisted_subreddits:
                    troll_index += 2.5
            total_comments_read = i

        if total_comments_read < 3:
            response.add_attachment(fallback="Summary for /u/" + username,
                                    text="Summary error: doesn't have enough comments.",
                                    color='danger')
            request.delayed_response(response)
            return

        troll_index *= limit / total_comments_read

        average_karma = np.mean(y)

        if average_karma >= 5 and total_negative_karma > (-70 * (total_comments_read / limit)) and troll_index < 50:
            troll_likelihood = 'Low'
            color = 'good'

        if troll_index >= 40 or total_negative_karma < (-70 * (total_comments_read / limit)) or average_karma < 1:
            troll_likelihood = 'Moderate'
            color = 'warning'

        if troll_index >= 60 or total_negative_karma < (-130 * (total_comments_read / limit)) or average_karma < -2:
            troll_likelihood = 'High'
            color = 'danger'

        if troll_index >= 80 or total_negative_karma < (-180 * (total_comments_read / limit)) or average_karma < -5:
            troll_likelihood = 'Very high'
            color = 'danger'

        if troll_index >= 100 or total_negative_karma < (-200 * (total_comments_read / limit)) \
                or average_karma < -10:
            troll_likelihood = 'Extremely high'
            color = 'danger'

        for subreddit in subreddit_names:
            i = subreddit_total.count(subreddit)
            comments_in_subreddit.append(i)
            total_comments += i

        i = 0

        for subreddit in subreddit_names:

            if comments_in_subreddit[i] > (total_comments_read / (20 * (limit / 200)) /
                                               (len(subreddit_names) / 30)):
                history[subreddit] = comments_in_subreddit[i]

            i += 1

        old_range = 700 - 50
        new_range = 2000 - 50

        for item in comment_lengths:
            n = (((item - 50) * new_range) / old_range) + 50
            s.append(n)

        history_tuples = sorted(history.items(), key=lambda xa: x[1])

        for each_tuple in history_tuples:
            ordered_subreddit_names.append(each_tuple[0])
            ordered_comments_in_subreddit.append(each_tuple[1])

        user_karma_atstart = user.comment_karma - math.fabs((np.mean(y) * total_comments_read))

        for item in list(reversed(y)):
            karma_accumulator += item
            karma_accumulated.append(karma_accumulator)

        for item in karma_accumulated:
            karma_accumulated_total.append(user_karma_atstart + item)

        plt.style.use('ggplot')
        labels = ordered_subreddit_names
        sizes = ordered_comments_in_subreddit
        colors = ['yellowgreen', 'gold', 'lightskyblue', 'lightcoral', 'teal', 'chocolate', 'olivedrab', 'tan']
        plt.subplot(3, 1, 1)
        plt.rcParams['font.size'] = 8
        plt.pie(sizes, labels=labels, colors=colors,
                autopct=None, startangle=90)
        plt.axis('equal')
        plt.title('User summary for /u/' + user.name, loc='center', y=1.2)

        ax1 = plt.subplot(3, 1, 2)
        x_inv = list(reversed(x))
        plt.rcParams['font.size'] = 10
        plt.scatter(x, y, c=y, vmin=-50, vmax=50, s=s, cmap='RdYlGn')
        ax1.set_xlim(x_inv[0], x_inv[total_comments_read - 1])
        ax1.axhline(y=average_karma, xmin=0, xmax=1, c="lightskyblue", linewidth=2, zorder=4)
        plt.ylabel('Karma of comment')

        ax2 = plt.subplot(3, 1, 3)
        plt.plot_date(x, list(reversed(karma_accumulated_total)), '-r')
        plt.xlabel('Comment date')
        plt.ylabel('Total comment karma')

        filename = username + "_summary.png"

        figure = plt.gcf()
        figure.set_size_inches(11, 12)

        plt.savefig(filename, bbox_inches='tight')

        path = os.getcwd() + "/" + filename

        link = self.imgur.upload_from_path(path, config=None, anon=True)
        os.remove(path)

        plt.clf()

        attachment = response.add_attachment(fallback="Summary for /u/" + username,
                                             title='Summary for /u/' + user.name,
                                             title_link="https://www.reddit.com/user/" + username,
                                             image_url=link['link'],
                                             color=color)
        attachment.add_field("Troll likelihood", troll_likelihood)
        attachment.add_field("Total comments read", total_comments_read)

        stopwords = set(STOPWORDS)

        wordcloud = WordCloud(width=800, height=400, scale=2, background_color='white',
                              stopwords=stopwords).generate(concatenated_comments)
        filename = username + "_wordcloud.png"
        plt.imshow(wordcloud)
        plt.axis("off")
        figure = plt.gcf()
        figure.set_size_inches(13, 8)
        plt.savefig(filename, bbox_inches='tight')
        path = os.getcwd() + "/" + filename
        link = self.imgur.upload_from_path(path, config=None, anon=True)
        os.remove(path)

        plt.clf()
        response.add_attachment(fallback="Wordcloud for /u/" + user.name, image_url=link['link'],
                                             color='good')

        request.delayed_response(response)
