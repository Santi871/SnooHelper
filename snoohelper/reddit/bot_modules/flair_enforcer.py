import datetime
import praw
import praw.exceptions
from snoohelper.database.models import UnflairedSubmissionModel
import time
from peewee import DoesNotExist


class FlairEnforcer:

    """
    Automatically removes unflaired submissions, keeps track of them, and approves them if they have been flaired
    Posts a flair-your-post message, allows flairing via a comment reply
    Requires 'modflair' and 'privatemessages' permissions (the latter only if comments_flairing is set to True)
    """

    def __init__(self, r, subreddit, sample_submission, grace_period=600, comments_flairing=True):
        """
        Constructor for FlairEnforcer

        :param r: instance of praw.Reddit
        :param subreddit: name of subreddit
        :param sample_submission: instance of praw.models.Submission of subreddit, to get flair choices
        :param grace_period: seconds to allow user to assign a flair before removing their submission
        :param comments_flairing: allow user to flair via comment reply
        """
        self.r = r
        self.comments_flairing = comments_flairing
        self.subreddit = subreddit
        self.sub_object = self.r.subreddit(self.subreddit)
        self.sub_mod = self.sub_object.mod
        self.unflaired_submissions = list()
        self.grace_period = grace_period
        self.flairs = [(flair['flair_text'], flair['flair_template_id']) for flair in sample_submission.flair.choices()]
        self._load_from_database()

    def _load_from_database(self):
        """
        Get tracked unflaired submissions from database
        """
        for unflaired_submission in UnflairedSubmissionModel.select():
            unflaired_submission_obj = UnflairedSubmission(self.r, unflaired_submission.submission_id, self.sub_object,
                                                           unflaired_submission.comment_id,
                                                           self.comments_flairing)
            deleted = unflaired_submission_obj.delete_if_overtime()
            if not deleted:
                self.unflaired_submissions.append(unflaired_submission_obj)

    def check_submissions(self, force_approve=False, force_check=False):
        """
        Checks comment replies from inbox and also checks the flair of the tracked unflaired submissions
        Approves those that have been flaired manually, and assigns flair and approves those flaired by comment reply

        :param force_approve: Approve all tracked submissions. For debugging purposes.
        :param force_check: Check regardless of whether the PM is marked unread
        """
        if self.comments_flairing:
            new_replies = self.r.inbox.comment_replies(limit=20)
            for reply in new_replies:
                if reply.new or force_check:

                    body = reply.body.split()
                    if len(body) < 4:
                        comment = self.r.comment(reply.id)
                        submission = comment.submission
                        unflaired_submission = None

                        for unflaired_submission_instance in self.unflaired_submissions:
                            try:
                                if unflaired_submission_instance.submission == submission.id or\
                                    unflaired_submission_instance.submission.id == submission.id or\
                                        unflaired_submission_instance.comment.id == comment.id:
                                    unflaired_submission = unflaired_submission_instance
                                    break
                            except AttributeError:
                                continue

                        if unflaired_submission is None:
                            reply.mark_read()
                            continue

                        for word in body:
                            word = word.lower()
                            word = word.strip("'")
                            word = word.strip('"')

                            for tup in self.flairs:

                                try:
                                    if word == tup[0].lower() and comment.author.name == submission.author.name:
                                        submission.flair.select(tup[1], tup[0])
                                        self.sub_mod.remove(comment)
                                        unflaired_submission.approve()
                                        self.unflaired_submissions.remove(unflaired_submission)

                                except AttributeError:
                                    self.unflaired_submissions.remove(unflaired_submission)
                    reply.mark_read()

        for unflaired_submission in self.unflaired_submissions:
            is_flaired = False

            try:
                is_flaired = unflaired_submission.check_if_flaired()
            except AttributeError:
                self.unflaired_submissions.remove(unflaired_submission)

            if is_flaired or force_approve:
                unflaired_submission.approve()
                self.unflaired_submissions.remove(unflaired_submission)
            else:
                deleted = unflaired_submission.delete_if_overtime()
                if deleted:
                    self.unflaired_submissions.remove(unflaired_submission)

    def add_submission(self, submission, force=False):
        """
        Removes an unflaired submission if the time elapsed since its creation is longer than grace_period

        :param submission: instance of praw.models.Submission
        :param force: remove submission regardless of grace period
        :return: tuple of instance of UnflairedSubmission and instance of praw.models.Comment
        """
        dt = datetime.datetime.utcfromtimestamp(submission.created_utc)

        if (datetime.datetime.utcnow() - dt).total_seconds() > self.grace_period or force:
            unflaired_submission_obj = UnflairedSubmission(self.r, submission, comments_flairing=self.comments_flairing)
            comment = unflaired_submission_obj.remove_and_comment()
            self.unflaired_submissions.append(unflaired_submission_obj)
            return unflaired_submission_obj, comment


class UnflairedSubmission:

    def __init__(self, r, submission, subreddit, comment=None, comments_flairing=True):
        self.r = r
        self._submission = submission
        self.sub = subreddit
        self.sub_mod = subreddit.mod
        self.comment = comment
        self.fullname = self.submission.fullname
        self.flairs = [(flair['flair_text'], flair['flair_template_id']) for flair in self.submission.flair.choices()]
        self.comments_flairing = comments_flairing

        if comment is not None:
            self.comment = r.comment(comment)

        try:
            self.report = submission.mod_reports[0][0]
        except IndexError:
            self.report = None

    @property
    def submission(self):
        if isinstance(self._submission, str):
            self._submission = self.r.submission(self._submission)
            return self._submission
        else:
            return self._submission

    @submission.setter
    def submission(self, v):
        self._submission = v

    def remove_and_comment(self):
        s1 = self.submission.author.name
        s2 = 'https://www.reddit.com/message/compose/?to=/r/' + self.sub

        comment = generate_flair_comment(s1, s2, self.flairs, self.comments_flairing)

        try:
            self.comment = self.submission.reply(comment)
        except praw.exceptions.APIException as e:
            print("PRAW Exception: " + str(e))
            return

        self.sub_mod.distinguish(self.comment)
        self.sub_mod.remove(self.submission)
        UnflairedSubmissionModel.create(submission_id=self.submission.id, comment_id=self.comment.id,
                                        subreddit=self.submission.subreddit.display_name)
        return self.comment

    def check_if_flaired(self):
        self.submission = self.r.submission(self.submission.id)

        if self.submission.link_flair_text is not None:
            return True
        return False

    def approve(self):
        self.sub_mod.approve(self.submission)
        if self.report is not None:
            self.submission.report(self.report)

        try:
            self.sub_mod.remove(self.comment)
        except AttributeError:
            pass

        try:
            unflaired_submission = UnflairedSubmissionModel.\
                get(UnflairedSubmissionModel.submission_id == self.submission.id)
            unflaired_submission.delete_instance()
        except:
            pass

    def delete_if_overtime(self):
        delta_time = time.time() - self.submission.created_utc

        try:
            if delta_time >= 13600:
                self.sub_mod.remove(self.comment)
                unflaired_submission = UnflairedSubmissionModel.get(
                    UnflairedSubmissionModel.submission_id == self.submission.id)
                unflaired_submission.delete_instance()
                return True
            else:
                return False
        except (AttributeError, UnflairedSubmissionModel.DoesNotExist, DoesNotExist):
            return False


def generate_flair_comment(s1, s2, flairs, comments_flairing=True):

    s3 = flairs[0][0]
    if comments_flairing:
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

    else:
        comment = ("""Hi /u/%s,

It looks like you haven't assigned a category flair to your question, so it has been automatically removed.
You can assign a category flair to your question by clicking the *flair* button under it.

Shortly after you have assigned a category flair to your question, it will be **automatically re-approved** and
 this message
will be deleted.

**How to flair your question:**

* Click the flair button under your question and pick a category from the list.

**List of available flairs:**


""") % s1

    for flair in flairs:
        comment += "* " + flair[0] + '\n\n'

    comment += "---\n\n*I am a bot, and this action was performed automatically.\n"
    comment += "Please [contact the moderators](%s) if you have any questions or concerns*" % s2
    return comment
