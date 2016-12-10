import time

from peewee import OperationalError, InterfaceError
from puni import Note
from retrying import retry

from snoohelper.database.models import AlreadyDoneModel


def clamp(min_value, max_value, x):
    return max(min(x, max_value), min_value)


def calculate_sleep(subscribers):
    """
    Calculates SlackTeam.sleep based on the subscribers number

    :param subscribers: Number of subreddit  subscribers
    :return: sleep seconds (float)
    """
    sleep = -24.58 + ((300.3865 + 24.58) / (1 + (subscribers / 2285664) ** 0.9862365))
    sleep = clamp(40, 300, sleep)
    return sleep


def add_ban_note(un, action, unban=False):
    """
    Adds a ban/unban note to a user when they are banned/unbanned

    :param un: puni.UserNotes instance
    :param action: Modaction from modlog
    :param unban: pass True if it's an unban
    :return: None
    """
    if not action.description:
        reason = "none provided"
    else:
        reason = action.description

    if not unban:
        n = Note(action.target_author, 'Banned, reason: ' + reason + ', length: ' + action.details,
                 action.mod, '', 'ban')
    elif unban and action.description != 'was temporary':
        n = Note(action.target_author, 'Unbanned.',
                 action.mod, '', 'spamwarning')
    else:
        return
    un.add_note(n)


def is_banned(subreddit, user):
    """
    Lookup whether Reddit user is banned from subreddit

    :param subreddit: praw.Subreddit instance
    :param user: praw.Redditor instance
    :return: True if banned, False if not banned
    """
    url = 'r/{}/about/banned/'.format(subreddit.display_name)
    params = {'unique': subreddit._reddit._next_unique, 'user': user}
    if len(list(subreddit._reddit.get(url, params=params))) == 1:
        return True
    else:
        return False


def get_scopes(form_data):
    scopes = ['identity', 'mysubreddits', 'read']
    if "usernotes" in form_data:
        scopes.append('wikiedit')
        scopes.append('wikiread')
    if "userwarnings" in form_data:
        scopes.append('modlog')
    if "flairenforce" in form_data:
        scopes.append('flair')
        scopes.append('modflair')
        scopes.append('submit')
        scopes.append('report')
        scopes.append('modposts')
        scopes.append("privatemessages")
    if "modposts" not in scopes and ("botbans" in form_data or "filters" in form_data):
        scopes.append("modposts")
    if "sendmodmail" in form_data and "privatemessages" not in scopes:
        scopes.append("privatemessages")

    return scopes, form_data


class AlreadyDoneHelper:
    """
    Utility class for easy management of Reddit items or posts that have already been checked
    """
    @retry(stop_max_attempt_number=6, wait_fixed=3000)
    def __init__(self, logger=None):
        """
        Construct AlreadyDoneHelper. Cleans up id's older than a week

        :param logger: logging.Logger instance
        """
        query = AlreadyDoneModel.delete().where((time.time() - AlreadyDoneModel.timestamp) > 604800)
        num = query.execute()

        if num:
            if logger is not None:
                logger.info("AlreadyDoneHelper: cleaned up %s ids." % str(num))
            print("AlreadyDoneHelper: cleaned up %s ids." % str(num))

    @staticmethod
    def add(thing_id, subreddit):
        """
        Attempts to insert AlreadyDoneModel instance to database
        Raises IntegrityError if the id already exists in database

        :param thing_id: Reddit item/post id
        :param subreddit: subreddit display name
        """

        while True:
            try:
                AlreadyDoneModel.create(thing_id=thing_id, timestamp=time.time(), subreddit=subreddit)
                break
            except (OperationalError, InterfaceError):
                print("Failed to write")
                time.sleep(1)

