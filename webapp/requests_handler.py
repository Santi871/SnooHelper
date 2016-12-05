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

        if button_pressed == "summary":
            limit = int(slack_request.actions[0]['value'].split('_')[1])
            target_user = '_'.join(slack_request.actions[0]['value'].split('_')[2:])
            original_message = utils.slack.slackresponse_from_message(slack_request.original_message,
                                                                footer="Summary (%s) requested." % args[0])
            original_message.set_replace_original(True)
            response = original_message
            team.bot.expanded_user_summary(request=slack_request, limit=limit, username=target_user)
        elif button_pressed == "track":
            target_user = '_'.join(slack_request.actions[0]['value'].split('_')[1:])
            response = team.bot.track_user(user=target_user)
        elif button_pressed == "untrack":
            target_user = '_'.join(slack_request.actions[0]['value'].split('_')[1:])
            response = team.bot.untrack_user(user=target_user)
        elif button_pressed == "botban":
            target_user = '_'.join(slack_request.actions[0]['value'].split('_')[1:])
            response = team.bot.botban(user=target_user, author=slack_request.user)
        elif button_pressed == "unbotban":
            target_user = '_'.join(slack_request.actions[0]['value'].split('_')[1:])
            response = team.bot.unbotban(user=target_user, author=slack_request.user)
        elif button_pressed == "verify":
            original_message = utils.slack.slackresponse_from_message(slack_request.original_message,
                                                                delete_buttons=['Verify'],
                                                                footer="Verified by @" + slack_request.user)
            response = original_message
        else:
            response = utils.slack.SlackResponse("Button not functional.")

        return response
