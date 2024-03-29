import random


class RobotController:

    def __init__(self):
        self.discovered_items = []
        self.bots = []
        self.bots_setup = False
        self.game_started = False
        self.social_learning_percentage = None

    def add_bot(self, pID):
        self.bots.append(Robot(pID))
        self.bots_setup = True

    def choose_selection(self, bot, item_ids):
        # Choose how many spots to fill (1,2 or 3)
        spots_to_fill = random.choice([1, 2, 3])
        print(f'Bot-{bot.pID} is filling {spots_to_fill} spot(s)')
        # For every spot that will be filled, pick a ranodm item
        selected_item_ids = [str(random.choice(item_ids)) for _ in range(spots_to_fill)]
        print(f'Bot-{bot.pID}\'s selection: {item_ids}')
        print(f'Bot-{bot.pID} chose: {selected_item_ids}')
        return selected_item_ids

    def apply_social_learning(self, bot, botItemIds):
        print(f'\n\nApplying Bot-{bot.pID} social learning')
        print(f'Validating discovered: {self.discovered_items} with bot experience: {bot.seen_items} and {botItemIds}')
        # If no items are found
        if not map(lambda x: x.items, self.discovered_items.copy()):
            return []
        trials = []
        # Iterate threw discovered items
        for discovered in self.discovered_items:
            # Check if we have (already seen) item, if so we dont want to apply social learning
            # Check if the person found is the same, if so we dont want to apply social learning
            # Check if all items in solution are available to bot
            # print(f"{[int(solutionItem) for solutionItem in discovered['solution']]} in {bot.seen_items.copy() + botItemIds.copy()} is = {}")
            if (self.social_learning_percentage < 100) and (discovered['pID'] == bot.pID or discovered['item'] in botItemIds or discovered['item'] in bot.seen_items or (not set([int(solutionItem) for solutionItem in discovered['solution']]).issubset(bot.seen_items.copy() + botItemIds.copy()))):
                continue
            trial = []
            print(f'Applying social learning for item: {discovered}')
            # Iterate threw solution items
            for item in discovered['solution']:
                perc = int(random.random() * 100)
                print(
                    f'Rolled {perc} < {self.social_learning_percentage} out of 100 for social learning for guess: {item} in: {discovered}')
                # Apply percentage to build the trial
                if perc < self.social_learning_percentage:
                    trial.append(item)
            # Add trial to list
            trials.append(trial)
        print(f'Ended with trials {trials} for Bot-{bot.pID}')
        return trials


class Robot:

    def __init__(self, pID):
        self.pID = pID
        self.number_of_trials = 0
        self.score = 0
        self.seen_items = []
