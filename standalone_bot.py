""" Run this file to run bots as a standalone application, detached from the webapp """

from snoohelper.utils.teams import SlackTeamsController

TESTING = False


def main():
    if not TESTING:
        SlackTeamsController("teams.ini", 'snoohelper_master.db')
    else:
        SlackTeamsController("teams_test.ini", 'snoohelper_test.db')


if __name__ == "__main__":
    main()
