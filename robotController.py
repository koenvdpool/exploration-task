import random


class RobotController:

    def __init__(self):
        self.discovered_items = []
        self.bots = []
        self.game_started = False
        self.social_learning_percentage = None

    def add_bot(self, pID):
        self.bots.append(Robot(pID))

    def pick_random_selection(self, bot, item_ids):
        # Choose how many spots to fill (1,2 or 3)
        spots_to_fill = random.choice([1, 2, 3])
        print(f'Bot-{bot.pID} is filling {spots_to_fill} spot(s)')
        # For every spot that will be filled, pick a random item
        selected_item_ids = [int(random.choice(item_ids)) for _ in range(spots_to_fill)]
        selected_item_ids.sort()

        # Make sure bots don't submit the same trial twice
        while selected_item_ids in bot.submitted_trials:
            print(f'Bot-{bot.pID} has already submitted {selected_item_ids} before')
            selected_item_ids = [int(random.choice(item_ids)) for _ in range(spots_to_fill)]
            selected_item_ids.sort()

        selected_item_ids = [str(id) for id in selected_item_ids]
        print(f'Bot-{bot.pID}\'s selection: {item_ids}')
        print(f'Bot-{bot.pID} chose: {selected_item_ids}')
        return selected_item_ids

    def apply_social_learning(self, bot, botItemIds):
        print(f'Starting Bot-{bot.pID} social learning')
        print(
            f'Validating discovered: {self.discovered_items} with bot\'s submissions: {bot.submitted_trials} and item ids: {botItemIds}')
        # If no items are found
        if not map(lambda x: x['items'], self.discovered_items.copy()):
            return None

        # Filter self.discovered_items to only include items that are not in bot.seen_items
        filtered_social_learning_choices = list(filter(
                                # Filter out items that are not available - Filter out items that bot itself has found
            lambda discovered: (discovered['item'] not in botItemIds) and (discovered['pID'] is not bot.pID) and (
                # Filter out items that the bot cannot make (yet) (convert items in discovered['solution'] to int)
                set(map(lambda x: int(x), discovered['solution'])).issubset(botItemIds)), self.discovered_items.copy()))

        print(
            f'Filtered discovered items {filtered_social_learning_choices} out of {self.discovered_items} for Bot-{bot.pID}')

        # Make choice from the remaining items else return None
        if not filtered_social_learning_choices:
            print(f'No items found for Bot-{bot.pID} to apply social learning')
            return None

        print(f'Bot-{bot.pID} is applying social learning')
        trial = random.choice(filtered_social_learning_choices)['solution']

        print(f'Ended with trial {trial} for Bot-{bot.pID}')
        return trial


class Robot:

    def __init__(self, pID):
        self.pID = pID
        self.number_of_trials = 0
        self.score = 0
        self.submitted_trials = []
