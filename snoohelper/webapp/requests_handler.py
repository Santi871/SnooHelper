import snoohelper.utils as utils
import snoohelper.utils.exceptions


class RequestsHandler:
    """
    Handles Slack HTTP requests for buttons and slash commands
    """
    def __init__(self, teams_controller):
        """
        Construct RequestsHandler instance

        :param teams_controller: an instance of SlackTeamsController that contains the SlackTeams
        """
        self.teams_controller = teams_controller
        self.teams = teams_controller.teams

    def handle_command(self, slack_request):
        """
        Process a Slack slash command HTTP request, returns a response

        :param slack_request: SlackRequest object representing the Slack HTTP request
        :return: SlackResponse object representing a JSON-encoded response
        """

        response = utils.slack.SlackResponse("Processing your request... please allow a few seconds.")
        user = slack_request.command_args[0]
        team = self.teams_controller.lookup_team_by_id(slack_request.team_id)

        if slack_request.command == '/user':
            team.bot.quick_user_summary(user=user, request=slack_request)
        elif slack_request.command == '/botban':
            try:
                response = team.bot.botban(user=user, author=slack_request.user)
            except utils.exceptions.UserAlreadyBotbanned:
                response = utils.slack.SlackResponse()
                response.add_attachment(text="Error: user already botbanned.", color='danger')

        elif slack_request.command == '/modmail':
            team.bot.message_modmail(' '.join(slack_request.command_args), slack_request.user, slack_request)
        else:
            response = utils.slack.SlackResponse("Command not available.")

        return response

    def handle_button(self, slack_request):
        """
        Process a Slack button HTTP request, returns a response

        :param slack_request: SlackRequest object representing the Slack HTTP request
        :return: SlackResponse object representing a JSON-encoded response
        """
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
            try:
                team.bot.track_user(user=target_user)
                new_button = utils.slack.SlackButton("Untrack", "untrack_" + target_user)
                replace_buttons = {'Track': new_button}

                response = utils.slack.slackresponse_from_message(slack_request.original_message,
                                                                             footer="Tracking user.",
                                                                             change_buttons=replace_buttons)
            except utils.exceptions.UserAlreadyTracked:
                response = utils.slack.SlackResponse()
                response.add_attachment(text='Error: user is not being tracked', color='danger')

        elif button_pressed == "untrack":
            target_user = '_'.join(slack_request.actions[0]['value'].split('_')[1:])
            try:
                team.bot.untrack_user(user=target_user)
                new_button = utils.slack.SlackButton("Track", "track_" + target_user)
                replace_buttons = {'Untrack': new_button}

                response = utils.slack.slackresponse_from_message(slack_request.original_message,
                                                                             footer="User untracked.",
                                                                             change_buttons=replace_buttons)
            except utils.exceptions.UserAlreadyUntracked:
                response = utils.slack.SlackResponse()
                response.add_attachment(text='Error: user is not being tracked', color='danger')

        elif button_pressed == "botban":
            target_user = '_'.join(slack_request.actions[0]['value'].split('_')[1:])

            try:
                team.bot.botban(user=target_user, author=slack_request.user)
                new_button = utils.slack.SlackButton("Unbotban", "unbotban_" + target_user, style='danger')
                replace_buttons = {'Botban': new_button}

                response = utils.slack.slackresponse_from_message(slack_request.original_message,
                                                                             footer="User botbanned.",
                                                                             change_buttons=replace_buttons)
            except utils.exceptions.UserAlreadyBotbanned:
                response = utils.slack.SlackResponse()
                response.add_attachment(text='Error: user is already botbanned.', color='danger')

        elif button_pressed == "unbotban":
            target_user = '_'.join(slack_request.actions[0]['value'].split('_')[1:])

            try:
                team.bot.unbotban(user=target_user, author=slack_request.user)
                new_button = utils.slack.SlackButton("Botban", "botban_" + target_user, style='danger')
                replace_buttons = {'Unbotban': new_button}

                response = utils.slack.slackresponse_from_message(slack_request.original_message,
                                                                             footer="User unbotbanned.",
                                                                             change_buttons=replace_buttons)
            except utils.exceptions.UserAlreadyUnbotbanned:
                response = utils.slack.SlackResponse()
                response.add_attachment(text='Error: user is not botbanned.', color='danger')

        elif button_pressed == "verify":
            original_message = utils.slack.slackresponse_from_message(slack_request.original_message,
                                                                                 delete_buttons=['Verify'],
                                                                                 footer="Verified by @" + slack_request.user)
            response = original_message
        else:
            response = utils.slack.SlackResponse("Button not functional.")

        return response
