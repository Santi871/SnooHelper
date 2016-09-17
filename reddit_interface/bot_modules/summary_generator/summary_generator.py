from imgurpython import ImgurClient
import matplotlib.pyplot as plt
import numpy as np
import utils.utils as utils
import praw.errors
from reddit_interface.database_models import UserModel
import datetime
import os
import math


class SummaryGenerator:

    def __init__(self, subreddit, access_token, un=None, users_tracked=False):

        self.imgur = ImgurClient(utils.get_token("IMGUR_CLIENT_ID", 'credentials'),
                     utils.get_token("IMGUR_CLIENT_SECRET", 'credentials'))
        self.users_tracked = users_tracked
        self.subreddit = subreddit
        self.un = un
        self.access_token = access_token

    def generate_quick_summary(self, r, username):

        response = utils.SlackResponse()

        try:
            user = r.get_redditor(username, fetch=True)
        except praw.errors.NotFound:
            response.add_attachment(response.add_attachment(fallback="Summary error.",
                                                            title="Error: user not found.", color='danger'))
            return response

        username = user.name

        combined_karma = user.link_karma + user.comment_karma
        account_creation = str(datetime.datetime.fromtimestamp(user.created_utc))

        last_note = None
        if self.un is not None:
            notes = list(self.un.get_notes(username))
            if len(notes):
                last_note = str(notes[0].note)

        attachment = response.add_attachment(title='Summary for /u/' + user.name,
                                title_link="https://www.reddit.com/user/" + username,
                                color='#3AA3E3', callback_id='user_' + username)

        attachment.add_field("Combined karma", combined_karma)
        attachment.add_field("Redditor since", account_creation)

        if self.users_tracked:
            user_track = UserModel.get(UserModel.username == username and UserModel.subreddit == self.subreddit)

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
        attachment.add_button("Track", "track_" + username)
        attachment.add_button("Shadowban", "shadowban_" + username, style='danger')

        return response

    def generate_expanded_summary(self, r, username, limit, request):

        response = utils.SlackResponse(replace_original=False)
        user = r.get_redditor(username, fetch=True)

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

        karma_accumulator = 0
        karma_accumulated = []
        karma_accumulated_total = []

        for comment in user.get_comments(limit=limit):

            displayname = comment.subreddit.display_name

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

            i += 1

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

        plt.savefig(filename)

        path = os.getcwd() + "/" + filename

        link = self.imgur.upload_from_path(path, config=None, anon=True)
        os.remove(path)

        plt.clf()

        attachment = response.add_attachment(fallback="Summary for /u/" + username, image_url=link['link'],
                                color=color)
        attachment.add_field("Troll likelihood", troll_likelihood)
        attachment.add_field("Total comments read", total_comments_read)
        request.delayed_response(response)
