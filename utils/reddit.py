from database.models import AlreadyDoneModel
from peewee import OperationalError, InterfaceError
import time
from puni import Note
from retrying import retry


def clamp(min_value, max_value, x):
    return max(min(x, max_value), min_value)


def calculate_sleep(subscribers):
    sleep = -24.58 + ((300.3865 + 24.58) / (1 + (subscribers / 2285664) ** 0.9862365))
    sleep = clamp(40, 300, sleep)
    return sleep


def add_ban_note(un, action, unban=False):
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


def get_my_moderation(reddit):
    url = "/subreddits/mine/moderator"
    params = {"limit": 100}
    return list(reddit.get(url, params=params))


def is_banned(subreddit, user):
    url = 'r/{}/about/banned/'.format(subreddit.display_name)
    params = {'unique': subreddit._reddit._next_unique, 'user': user}
    if len(list(subreddit._reddit.get(url, params=params))) == 1:
        return True
    else:
        return False


class AlreadyDoneHelper:

    @retry(stop_max_attempt_number=6, wait_fixed=3000)
    def __init__(self, logger=None):
        query = AlreadyDoneModel.delete().where((time.time() - AlreadyDoneModel.timestamp) > 604800)
        num = query.execute()

        if num:
            if logger is not None:
                logger.info("AlreadyDoneHelper: cleaned up %s ids." % str(num))
            print("AlreadyDoneHelper: cleaned up %s ids." % str(num))

    @staticmethod
    def add(thing_id, subreddit):

        while True:
            try:
                AlreadyDoneModel.create(thing_id=thing_id, timestamp=time.time(), subreddit=subreddit)
                break
            except (OperationalError, InterfaceError):
                print("Failed to write")
                time.sleep(1)

