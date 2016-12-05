import utils


class RequestsHandler:

    def __init__(self, teams_controller):
        self.teams_controller = teams_controller
        self.teams = teams_controller.teams

    def handle_command(self, slack_request):
        response = utils.slack.SlackResponse("Processing your request... please allow a few seconds.")
        user = slack_request.command_args[0]
        team = self.teams_controller.lookup_team_by_id(slack_request.team_id)

        if slack_request.command == '/user':
            team.bot.quick_user_summary(user=user, request=slack_request)
        elif slack_request.command == '/botban':
            response = team.bot.botban(user=user, author=slack_request.user)
        else:
            response = utils.slack.SlackResponse("Command not available.")

        return response

    def handle_button(self, slack_request):
        button_pressed = slack_request.actions[0]['value'].split('_')[0]
        args = slack_request.actions[0]['value'].split('_')[1:]
        team = self.teams_controller.lookup_team_by_id(slack_request.team_id)

        if len(args) > 1:
            target_user = '_'.join(args[1:])
        elif len(args):
            target_user = args[0]
        else:
            target_user = None

        if button_pressed == "summary":
            original_message = utils.slack.slackresponse_from_message(slack_request.original_message,
                                                                footer="Summary (%s) requested." % args[0])
            original_message.set_replace_original(True)
            response = original_message
            team.bot.expanded_user_summary(request=slack_request,
                                                                                  limit=int(args[0]),
                                                                                  username=target_user)
        elif button_pressed == "track":
            response = team.bot.track_user(user=target_user)
        elif button_pressed == "untrack":
            response = team.bot.untrack_user(user=target_user)
        elif button_pressed == "botban":
            response = team.bot.botban(user=target_user, author=slack_request.user)
        elif button_pressed == "unbotban":
            response = team.bot.unbotban(user=target_user, author=slack_request.user)
        elif button_pressed == "verify":
            original_message = utils.slack.slackresponse_from_message(slack_request.original_message,
                                                                delete_buttons=['Verify'],
                                                                footer="Verified by @" + slack_request.user)
            response = original_message
        else:
            response = utils.slack.SlackResponse("Button not functional.")

        return response
