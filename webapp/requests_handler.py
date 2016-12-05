import utils


class RequestsHandler:

    def __init__(self, teams):
        self.teams = teams

    def handle_command(self, slack_request):
        response = utils.slack.SlackResponse("Processing your request... please allow a few seconds.")
        if slack_request.command == '/userz':
            self.teams[slack_request.team_domain].bot.quick_user_summary(user=slack_request.command_args[0],
                                                                         request=slack_request)
        return response

    def handle_button(self, slack_request):
        response = utils.slack.SlackResponse("Processing your request... please allow a few seconds.",
                                             replace_original=False)
        button_pressed = slack_request.actions[0]['value'].split('_')[0]
        args = slack_request.actions[0]['value'].split('_')[1:]

        if len(args) > 1:
            target_user = '_'.join(args[1:])
        else:
            target_user = args[0]

        if button_pressed == "summary":
            original_message = utils.slack.slackresponse_from_message(slack_request.original_message,
                                                                footer="Summary (%s) requested." % args[0])
            original_message.set_replace_original(True)
            response = original_message
            self.teams[slack_request.team_domain].bot.expanded_user_summary(request=slack_request,
                                                                                  limit=int(args[0]),
                                                                                  username=target_user)
            print(3)
        elif button_pressed == "track":
            response = self.teams[slack_request.team_domain].bot.track_user(user=target_user)
        elif button_pressed == "untrack":
            response = self.teams[slack_request.team_domain].bot.untrack_user(user=target_user)
        elif button_pressed == "botban":
            response = self.teams[slack_request.team_domain].bot.botban(user=target_user, author=slack_request.user)
        elif button_pressed == "unbotban":
            response = self.teams[slack_request.team_domain].bot.unbotban(user=target_user, author=slack_request.user)
        elif button_pressed == "verify":
            original_message = utils.slack.slackresponse_from_message(slack_request.original_message,
                                                                delete_buttons=['Verify'],
                                                                footer="Verified by @" + slack_request.user)
            response = original_message

        return response