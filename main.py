from snoohelper.utils.teams import SlackTeamsController
from snoohelper.webapp.requests_handler import RequestsHandler
from snoohelper.webapp.webapp import create_app
from snoohelper.utils.credentials import get_token

if __name__ == '__main__':
    context = ('santihub.crt', 'santihub.key')
    testing = bool(get_token("testing", "credentials"))
    if not testing:
        controller = SlackTeamsController("teams.ini", 'snoohelper_master.db')
    else:
        controller = SlackTeamsController("teams_test.ini", 'snoohelper_test.db')
    handler = RequestsHandler(controller)
    app = create_app(controller, handler)
    app.run(host='0.0.0.0', port=5023, ssl_context=context, threaded=True)
