import datetime

import praw
import praw.exceptions

from snoohelper.database.models import UnflairedSubmissionModel


class FlairEnforcer:

    """Module that enforces submission flair, keeps track of unflaired submissions, etc.
     Requires 'modflair' and 'flair' permissions"""

    def __init__(self, r, subreddit, grace_period=600):
        self.r = r
        self.subreddit = subreddit
        self.sub_object = self.r.subreddit(self.subreddit)
        self.unflaired_submissions = list()
        self.grace_period = grace_period
        self._load_from_database()

    def _load_from_database(self):
        for unflaired_submission in UnflairedSubmissionModel.select():
            submission = self.r.submission(unflaired_submission.submission_id)
            unflaired_submission_obj = UnflairedSubmission(self.r, submission, unflaired_submission.comment_id)
            self.unflaired_submissions.append(unflaired_submission_obj)

    def check_submissions(self):
        for unflaired_submission in self.unflaired_submissions:
            is_flaired = False

            try:
                is_flaired = unflaired_submission.check_if_flaired()
            except AttributeError:
                self.unflaired_submissions.remove(unflaired_submission)

            if is_flaired:
                unflaired_submission.approve()
                self.unflaired_submissions.remove(unflaired_submission)
            else:
                deleted = unflaired_submission.delete_if_overtime()
                if deleted:
                    self.unflaired_submissions.remove(unflaired_submission)

    def add_submission(self, submission):
        dt = datetime.datetime.utcfromtimestamp(submission.created_utc)

        if (datetime.datetime.utcnow() - dt).total_seconds() > self.grace_period:
            unflaired_submission_obj = UnflairedSubmission(self.r, submission)
            unflaired_submission_obj.remove_and_comment()
            self.unflaired_submissions.append(unflaired_submission_obj)


class UnflairedSubmission:

    def __init__(self, r, submission, comment=None):
        self.r = r
        self.submission = submission
        self.sub = submission.subreddit.display_name
        self.sub_mod = submission.subreddit.mod
        self.comment = comment
        self.fullname = self.submission.fullname
        self.flairs = [(flair['flair_text'], flair['flair_template_id']) for flair in self.submission.flair.choices()]

        if comment is not None:
            self.comment = r.comment(comment)

        try:
            self.report = submission.mod_reports[0][0]
        except IndexError:
            self.report = None

    def remove_and_comment(self):
        s1 = self.submission.author.name
        s2 = 'https://www.reddit.com/message/compose/?to=/r/' + self.sub

        comment = generate_flair_comment(s1, s2, self.flairs)

        try:
            self.comment = self.submission.reply(comment)
        except praw.exceptions.APIException:
            return

        self.sub_mod.distinguish(self.comment)
        self.sub_mod.remove(self.submission)
        UnflairedSubmissionModel.create(submission_id=self.submission.id, comment_id=self.comment.id,
                                        subreddit=self.submission.subreddit.display_name)

    def check_if_flaired(self):
        self.submission = self.r.submission(self.submission.id)
        self.submission.comments.replace_more(limit=None)
        comments = self.submission.comments.list()

        if self.submission.link_flair_text is not None:
            return True
        else:
            for comment in comments:
                body = comment.body.split()
                if len(body) < 4:
                    for word in body:
                        word = word.lower()
                        word = word.strip("'")
                        word = word.strip('"')

                        for tup in self.flairs:
                            if word == tup[0].lower() and comment.author.name == self.submission.author.name:
                                self.sub_mod.remove(comment)
                                self.submission.flair.select(tup[1], tup[0])
                                return True
        return False

    def approve(self):
        self.sub_mod.approve(self.submission)
        if self.report is not None:
            self.submission.report(self.report)

        self.sub_mod.remove(self.comment)
        unflaired_submission = UnflairedSubmissionModel.get(
            UnflairedSubmissionModel.submission_id == self.submission.id)
        unflaired_submission.delete_instance()

    def delete_if_overtime(self):
        submission_time = datetime.datetime.fromtimestamp(self.submission.created)
        d = datetime.datetime.now() - submission_time
        delta_time = d.total_seconds()

        if delta_time >= 13600:
            self.sub_mod.remove(self.comment)
            unflaired_submission = UnflairedSubmissionModel.get(
                UnflairedSubmissionModel.submission_id == self.submission.id)
            unflaired_submission.delete_instance()
            return True
        else:
            return False


def generate_flair_comment(s1, s2, flairs):

    s3 = flairs[0][0]
    comment = ("""Hi /u/%s,

It looks like you haven't assigned a category flair to your question, so it has been automatically removed.
You can assign a category flair to your question by clicking the *flair* button under it.

Shortly after you have assigned a category flair to your question, it will be **automatically re-approved** and
 this message
will be deleted.

**How to flair your question:**

* Click the flair button under your question and pick a category from the list (if you are on desktop).

* If you are not on desktop, reply to this message with the flair you want.
(Example: if you want the %s flair, reply to this message with "%s", without the quotes).

**List of available flairs:**


""") % (s1, s3, s3.lower())

    for flair in flairs:
        comment += "* " + flair[0] + '\n\n'

    comment += "---\n\n*I am a bot, and this action was performed automatically.\n"
    comment += "Please [contact the moderators](%s) if you have any questions or concerns*" % s2
    return comment
