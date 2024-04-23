import time

from flask import Flask, request, session, jsonify, render_template, redirect
from datetime import datetime
import pymysql.cursors
import threading
import numpy as np

from robotController import RobotController

app = Flask(__name__)
app.secret_key = datetime.now().isoformat()

# Thread-local storage for database connections
thread_local = threading.local()

SLEEP_TIME = 10.5
bot_controllers = {}
session_experiment_id = None
human_discovered_items = {}
config = {'botNums': 5, 'perSoc': 100, 'isSemantic': 1}


def background_task(sessionID):
    while True:
        time.sleep(SLEEP_TIME)  # Wait for 8 seconds

        if not bot_controllers[sessionID].game_started:
            continue

        this_round_discovered_items = []
        global human_discovered_items
        # Add human discovered items to controller class for bot social learning
        if human_discovered_items[sessionID]:
            print(f'Adding {human_discovered_items[sessionID]} to controller for bots social leaning')
            bot_controllers[sessionID].discovered_items += human_discovered_items[sessionID]
            # Clear after adding to prevent bots from checking unnecessarily
            human_discovered_items[sessionID] = []

        # Filter bot_controllers[sessionID].discovered_items to remove items that have already been discovered
        filtered_discovered_items = []
        for discovered in bot_controllers[sessionID].discovered_items:
            if discovered['item'] in filtered_discovered_items:
                continue
            else:
                filtered_discovered_items.append(discovered)
        bot_controllers[sessionID].discovered_items = filtered_discovered_items

        print(f'Filtered discovered items: {bot_controllers[sessionID].discovered_items}')

        for bot in bot_controllers[sessionID].bots:

            # Get available item ids for bot
            available_item_ids = get_available_item_ids_by_pid(bot.pID)

            social_learning_trial = None

            print(f'\n\nBot-{bot.pID} can pick {available_item_ids}')

            rand_number = np.random.randint(1, 101)

            print(f'Bot-{bot.pID} got {rand_number} for social learning, config: {config["perSoc"]}')

            # Social learning
            if rand_number <= config['perSoc']:
                social_learning_trial = bot_controllers[sessionID].apply_social_learning(bot, available_item_ids)

            if social_learning_trial:
                # Handle social learning trials
                handleItemIds(bot.pID, social_learning_trial, bot)
            # If no social learning trial is found, make a random selection
            else:
                # Make a choice and handle selection
                trial = bot_controllers[sessionID].pick_random_selection(bot, available_item_ids)
                discovered = handleItemIds(bot.pID, trial, bot)

                # Append newly discovered items to the list for social learning
                if discovered:
                    this_round_discovered_items.append({'pID': bot.pID, 'item': discovered, 'solution': trial})

        # Append discovered item to controller so that social learning can be applied next round
        bot_controllers[sessionID].discovered_items += this_round_discovered_items


def activate_background_task(session):
    # Add bots
    for _ in range(int(session['botNums'])):
        pID = addNewParticipantToExperiment(1, session['experimentID'], True)
        connection = get_db_connection()
        cursor = connection.cursor()
        # Update experiment with bots
        cursor.execute("UPDATE cce_experiments.experiments SET nParticipants = nParticipants + 1 WHERE id = %s",
                       (session['experimentID']))
        connection.commit()
        cursor.close()
        if session['experimentID'] not in bot_controllers:
            bot_controllers[session['experimentID']] = RobotController()
            human_discovered_items[session['experimentID']] = []
        bot_controllers[session['experimentID']].social_learning_percentage = session['perSoc']
        bot_controllers[session['experimentID']].add_bot(pID)

        # Add default item ids for bots
        getGamestateForParticipant(pID)

    # Start background task with session['experimentID'] as parameter
    thread = threading.Thread(target=background_task, args=(session['experimentID'],))
    thread.daemon = True  # Daemonize the thread to shut down with the app
    thread.start()


def get_db_connection():
    """
    Create a new database connection for the current thread if it doesn't already exist.
    """
    if not hasattr(thread_local, "db"):
        thread_local.db = pymysql.connect(
            host='localhost',
            user='root',
            password='root',
            database='cce_experiments',
            cursorclass=pymysql.cursors.DictCursor
        )
    return thread_local.db


@app.teardown_appcontext
def close_db_connection(exception=None):
    """
    Close the database connection at the end of the request.
    """
    if hasattr(thread_local, "db"):
        thread_local.db.close()
        del thread_local.db


################### Home page ##################
@app.route("/")
def home():
    prolificID = request.args.get('pid', default=np.random.randint(0, 10000000))
    studyID = request.args.get('sid')
    sessionID = request.args.get('sesid')
    is_semantic = int(request.args.get('isSemantic', 0))

    if 'prolificID' not in session:
        session['prolificID'] = prolificID
        session['studyID'] = studyID
        session['sessionID'] = sessionID
        session['semantic_extension'] = "-semantic" if is_semantic == 1 else ""

    return render_template("IndIntro.html", semantic_extension=session['semantic_extension'])


# http://127.0.0.1:5000/groupIntro?numBots=5&perSoc=50&isSemantic=1
################### Home page group ##################
@app.route("/groupIntro")
def groupIntro():
    prolificID = request.args.get('pid', np.random.randint(0, 10000000))
    studyID = request.args.get('sid')
    sessionID = request.args.get('sesid')
    bot_num = int(request.args.get('numBots', 0))
    is_semantic = int(request.args.get('isSemantic', 0))
    perSoc = int(request.args.get('perSoc', 100))

    if 'prolificID' not in session:
        # global BOT_NUM
        session['prolificID'] = prolificID
        session['studyID'] = studyID
        session['sessionID'] = sessionID
        # session['bot_num'] = bot_num
        # session['semantic_extension'] = "-semantic" if is_semantic == 1 else ""
        # session['perSoc'] = perSoc
        # bot_controller.social_learning_percentage = perSoc
        # BOT_NUM = 5 if bot_num > 5 else bot_num

    # TODO: Fix semantic extension
    return render_template("groupIntro.html", semantic_extension="")


################### NO ID PAGE ##################
@app.route("/noID")
def noID():
    return render_template("noID.html")


################### GROUP PLAY SELECTION OPTIONS ##################
@app.route("/groupPlay")
def groupPlay():
    # Check for participant id
    if 'participantID' in session:

        if session['experiment_type'] == 0:
            return redirect("/individualTotem")
        elif session['experiment_type'] == 1:
            if 'score' in session:
                return redirect("/groupTotem")
            ###################################################################### addd here if the experiment started go to the play
            return redirect("/groupPlay")


# check if the experiment code matches to the experiment created, and if so join
@app.route('/groupPlay/joinExperiment', methods=['POST'])
def joinExperiment():
    # Fetch data
    data = request.get_json()
    experimentID = data.get('experimentCode', '')

    # Fetch first experiment with given id (experimentID)
    # Get a database connection
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute(
        'SELECT * FROM cce_experiments.experiments where id = %s', (experimentID,))
    experiment = cursor.fetchone()
    response = ''
    if not experiment:
        # response = ' Experiment is not found.'
        response = 0
    else:
        # Fetch all participant with given experiment id
        cursor.execute(
            'SELECT * FROM cce_experiments.participants where experimentID = %s', (experimentID,))
        participants = cursor.fetchall()

        # Check if the experiment is full
        if len(participants) < experiment['nParticipants']:
            response = 1
            pID = addNewParticipantToExperiment(1, experimentID, False)
            global session_experiment_id
            session_experiment_id = experimentID
            session['experimentID'] = experimentID
            session['nParticipants'] = experiment['nParticipants']
            session['host'] = False
        else:
            response = -1

    cursor.close()
    return jsonify(response)


################### GROUP EXPERIMENT START ##################
@app.route('/groupStart')
def groupStart():
    if 'participantID' in session:
        if session['experiment_type'] == 0:
            return redirect("/individualTotem")
        elif 'experiment_type' in session and session['experiment_type'] == 1:
            if 'score' in session:
                return redirect("/groupTotem")

    # Open up a connection to the DB
    connection = get_db_connection()
    cursor = connection.cursor()

    if 'stored_datetime' not in session:

        session['experiment_type'] = 1

        ################## Check if prolific ID was registered before ########
        # cursor.execute(
        #    'SELECT * FROM cce_experiments.participants where prolificID = %s', (session['polificID'],))
        # participant = cursor.fetchone()
        # if not participant:
        #    pID = addNewParticipantToExperiment(1, experimentID)

        session['stored_datetime'] = datetime.now().isoformat()
        global session_experiment_id

        # Check if there is experiment with type 1 and with smaller than 6 participants
        cursor.execute(
            'SELECT * FROM cce_experiments.experiments where nParticipants < 6 and type = 1 and started = 0')  # Check if there is experiment with type 1 and with smaller than 6 participants
        experiment = cursor.fetchone()
        expID = ''
        if experiment:  # There is an experiment with less participants - so add this participant there
            expID = experiment['id']
            session_experiment_id = expID
            session['experimentID'] = expID
            pID = addNewParticipantToExperiment(1, expID, False)
            # Update mutation
            cursor.execute(
                'Update cce_experiments.experiments SET nParticipants = %s where id = %s',
                (int(experiment['nParticipants']) + 1, expID,))
            # Commit transaction
            connection.commit()

        else:  # No there is no experiment so add new experiment
            # Create random pID
            pID = np.random.randint(0, 10000000)

            # Fetch any (one) participants by the just generated pID
            cursor.execute(
                'SELECT * FROM cce_experiments.participants where pID = %s', (pID,))
            participant = cursor.fetchone()

            # Keep retrying to generate the pID until a unique one arises
            while participant:
                pID = np.random.randint(0, 10000000)
                cursor.execute(
                    'SELECT * FROM cce_experiments.participants where pID = %s', (pID,))
                participant = cursor.fetchone()

            # Store in session
            session['participantID'] = pID

            # Fetch any (one) participants by the just generated expID
            expID = np.random.randint(0, 10000000)
            cursor.execute(
                'SELECT * FROM cce_experiments.experiments where id = %s', (expID,))
            experiment = cursor.fetchone()

            # Keep retrying to generate the pID until a unique one arises
            while experiment:
                expID = np.random.randint(0, 10000000)
                cursor.execute(
                    'SELECT * FROM cce_experiments.experiments where id = %s', (expID,))
                experiment = cursor.fetchone()

            # Store in session
            session_experiment_id = expID
            session['experimentID'] = expID

            session['botNums'] = config['botNums']
            session['perSoc'] = config['perSoc']
            session['semantic_extension'] = '-semantic' if config['isSemantic'] == 1 else ''

            # Insert the experiment with the above generated data
            cursor.execute('INSERT INTO cce_experiments.experiments VALUES \
                (%s, 1, NULL, NULL, 1, %s, %s, %s, NULL, 0, %s, %s, %s, %s)', (
                 expID, session['prolificID'], session['studyID'], session['sessionID'], session['stored_datetime'],
                 True if len(session['semantic_extension']) > 0 else False, config['perSoc'],
                 config['botNums']))

            # Commit transaction
            connection.commit()

            # Insert the participants with the above generated data
            cursor.execute('INSERT INTO cce_experiments.participants VALUES \
                (%s, %s, 0, %s, %s)', (pID, expID, session['prolificID'], False))

            # Commit transaction
            connection.commit()

    # Fetch all participants by experiment id
    cursor.execute(
        'SELECT * FROM cce_experiments.participants where experimentID = %s', (session['experimentID'],))
    nParticipants = cursor.fetchall()

    # If there is only one participant, activate the background task (add bots since its a new game)
    if len(nParticipants) == 1 and session['botNums'] > 0:
        activate_background_task(session)

    # Fetch all participants by experiment id
    cursor.execute('SELECT * FROM cce_experiments.participants where experimentID = %s', (session['experimentID'],))
    nParticipants = cursor.fetchall()

    cursor.close()

    return render_template("groupStart.html", participantCount=len(nParticipants))


@app.route('/checkParticipants', methods=['POST'])
def checkParticipants():
    # Open up a connection to the DB
    connection = get_db_connection()
    cursor = connection.cursor()

    # Find one experiment by id
    cursor.execute(
        'SELECT * FROM cce_experiments.experiments where id = %s', (session['experimentID']))
    experiment = cursor.fetchone()

    # Calculate the elapsed time

    current_datetime = datetime.now()
    started_time = experiment['waitingStartTime']

    c = current_datetime - started_time

    minutes = c.total_seconds() / 60
    seconds = c.total_seconds() % 60

    minStr = str(int(minutes))
    if len(minStr) == 1:
        minStr = "0" + minStr
    secStr = str(int(seconds))
    if len(secStr) == 1:
        secStr = "0" + secStr

    cursor.close()
    return jsonify({'data': experiment['nParticipants'], 'limit': 6, 'elapsedTime': minStr + ":" + secStr})


@app.route('/checkElapsedTime', methods=['POST'])
def checkElapsedTime():
    current_datetime = datetime.now().isoformat()
    return jsonify({'currentTime': current_datetime, 'startTime': session['stored_datetime']})


################### GROUP EXPERIMENT START ##################


def addNewParticipantToExperiment(expType, expID, isBot):
    # Open up a connection to the DB
    connection = get_db_connection()
    cursor = connection.cursor()

    # set values
    if not isBot:
        session['experiment_type'] = expType
        session['number_of_trials'] = 0

    # randomly generate pId
    pID = np.random.randint(0, 10000000)
    cursor.execute(
        'SELECT * FROM cce_experiments.participants where pID = %s', (pID,))
    participant = cursor.fetchone()

    # Fetch any (one) participants by the just generated pID
    while participant:
        pID = np.random.randint(0, 10000000)
        cursor.execute(
            'SELECT * FROM cce_experiments.participants where pID = %s', (pID,))
        participant = cursor.fetchone()

    # store pID in session
    if not isBot:
        session['participantID'] = pID

    # store pID in db
    cursor.execute('INSERT INTO cce_experiments.participants VALUES \
        (%s, %s, 0, %s, %s)', (pID, expID, session['prolificID'], isBot))

    # commit transaction
    connection.commit()
    cursor.close()
    return pID


def addNewParticipantAndExperiment(expType, nParticipants):
    # Open up a connection to the DB
    connection = get_db_connection()
    cursor = connection.cursor()

    # set values
    session['experiment_type'] = expType
    session['number_of_trials'] = 0

    # Randomly generate pID
    pID = np.random.randint(0, 10000000)

    # Fetch any (one) participants by the just generated pID
    cursor.execute(
        'SELECT * FROM cce_experiments.participants where pID = %s', (pID,))
    participant = cursor.fetchone()

    # Keep retrying to generate the pID until a unique one arises
    while participant:
        pID = np.random.randint(0, 10000000)
        cursor.execute(
            'SELECT * FROM cce_experiments.participants where pID = %s', (pID,))
        participant = cursor.fetchone()

    # store pID in session
    session['participantID'] = pID

    # Randomly generate expID
    expID = np.random.randint(0, 10000000)

    # Fetch any (one) participants by the just generated expID
    cursor.execute(
        'SELECT * FROM cce_experiments.experiments where id = %s', (expID,))
    experiment = cursor.fetchone()

    # Keep retrying to generate the expID until a unique one arises
    while experiment:
        expID = np.random.randint(0, 10000000)
        cursor.execute(
            'SELECT * FROM cce_experiments.experiments where id = %s', (expID,))
        experiment = cursor.fetchone()

    # store pID in session
    global session_experiment_id
    session_experiment_id = expID
    session['experimentID'] = expID

    # Store in db
    cursor.execute('INSERT INTO cce_experiments.experiments VALUES \
        (%s, %s, %s, NULL, %s, %s, %s, %s, NULL, 0, NULL, %s, NULL, NULL)', (
        expID, expType, session['stored_datetime'], nParticipants, session['prolificID'], session['studyID'],
        session['sessionID'], True if len(session['semantic_extension']) > 0 else False))
    connection.commit()

    # Store in db
    cursor.execute('INSERT INTO cce_experiments.participants VALUES \
        (%s, %s, 0, %s, %s)', (pID, expID, session['prolificID'], False))
    connection.commit()
    cursor.close()
    return pID, expID


def getGamestateForParticipant(pID):
    # Open up a connection to the DB
    connection = get_db_connection()
    cursor = connection.cursor()

    # select all gamestates by participant id
    cursor.execute(
        'SELECT * FROM cce_experiments.gamestate where participantID = %s', (pID,))
    gamestate = cursor.fetchall()

    # if none found
    if not gamestate:
        # get all games
        cursor.execute(
            'SELECT * FROM cce_experiments.totemgame where given = 1')
        rules = cursor.fetchall()
        inventoryItemIDs = []

        # Iterate over the fetched data and append to the result list
        for rule in rules:
            inventoryItemIDs.append(rule['item'])
            cursor.execute('INSERT INTO cce_experiments.gamestate VALUES \
                (%s, %s, %s)', (pID, rule['item'], 0))
            connection.commit()
    else:
        inventoryItemIDs = []
        for item in gamestate:
            inventoryItemIDs.append(item['itemID'])

    cursor.close()
    return inventoryItemIDs


#####  Individual totem game
@app.route("/individualTotem")
def individualTotem():
    # Back to homepage
    if 'prolificID' not in session:
        return redirect("/")

    if 'experiment_type' in session:
        if session['experiment_type'] == 1:
            return redirect("/groupTotem")

    if 'score' not in session:
        session['score'] = 0

    # Session variable does not exist
    if 'stored_datetime' not in session:
        current_datetime = datetime.now().isoformat()
        session['stored_datetime'] = current_datetime

    if 'participantID' not in session:
        pID, expID = addNewParticipantAndExperiment(0, 1)

    # Fetch gamestate
    inventoryItemIDs = getGamestateForParticipant(session['participantID'])

    return render_template("individualTotem.html", inventoryItemIDs=inventoryItemIDs,
                           startingTime=session['stored_datetime'], numOfTrials=session['number_of_trials'],
                           score=session['score'], semantic_extension=session['semantic_extension'])


@app.route("/totemTutorial")
def totemTutorial():
    if 'tutorialScore' not in session:
        session['tutorialTrials'] = 0
        session['tutorialScore'] = 0
        # if host?, then update the start time and go to the game
        inventoryItemIDs = [1, 2, 3, 4, 5, 6]
        session['inventoryItemIDs'] = inventoryItemIDs
        session[
            'messageDisplay'] = ""  # "Please try placing the second item (small tree) in one of the slots and press Combine button to generate a twig!"

    # Setup tutorial values
    pids = [0, 1, 2, 3, 4, 5]
    scores = [15, 0, 0, 0, 0, 0]
    participants = []
    counter = 1
    for i in range(len(scores)):
        participants.append([pids[i], counter, scores[i]])
        counter = counter + 1

    return render_template("totemTutorial.html", inventoryItemIDs=session['inventoryItemIDs'],
                           numOfTrials=session['tutorialTrials'], messageDisplay=session['messageDisplay'],
                           participants=participants, score=session['tutorialScore'],
                           semantic_extension=session['semantic_extension'])


@app.route('/tutorial', methods=['POST'])
def tutorial():
    data = request.json
    current_item_ids = data.get('currentItemIds', [])
    if (len(current_item_ids) >= 1):

        if 'tutorialTrials' in session:
            session['tutorialTrials'] += 1
        else:
            session['tutorialTrials'] = 1

            # convert all item ids to int
        current_item_ids = [int(numeric_string) for numeric_string in current_item_ids]
        # Sort
        current_item_ids.sort()
        # convert back to string
        current_item_ids = [str(numeric) for numeric in current_item_ids]

        trialStr = ''
        # Append string
        for j in range(len(current_item_ids)):
            trialStr = trialStr + '.' + current_item_ids[j]

        # Hardcoded game clauses
        if trialStr == ".2":
            inventoryItemIDs = session['inventoryItemIDs']
            if 13 not in inventoryItemIDs:
                inventoryItemIDs.append(13)
                session['inventoryItemIDs'] = inventoryItemIDs
                session['tutorialScore'] = session['tutorialScore'] + 15

        if trialStr == ".3.3":
            inventoryItemIDs = session['inventoryItemIDs']
            if 11 not in inventoryItemIDs:
                inventoryItemIDs.append(11)
                session['inventoryItemIDs'] = inventoryItemIDs
                session['tutorialScore'] = session['tutorialScore'] + 15

    return jsonify(message="Image IDs received")


@app.route('/tutorialTimeUpdate', methods=['POST'])
def tutorialTimeUpdate():
    button_ids = [0, 1, 2, 3, 4, 5]
    scores = [15, 0, 0, 0, 0, 0]
    response_data = []
    for i in range(len(scores)):
        response_data.append({'button_id': button_ids[i], 'score': scores[i]})

    return jsonify({'data': response_data})


@app.route('/btnParticipantTutorial', methods=['POST'])
def btnParticipantTutorial():
    data = request.get_json()
    parID = data.get('buttonId', '')
    innoPar = []
    if parID == '0':
        innoPar = [{'name': 11}]
    return jsonify(innoPar)


@app.route('/dispRuleTutorial', methods=['POST'])
def dispRuleTutorial():
    data = request.get_json()
    itemID = data.get('item', '')
    rItems = []
    if itemID == 11:
        # Get game by item
        # Open up a connection to the DB
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute('Select * from cce_experiments.totemgame where item = %s', (itemID,))
        items = cursor.fetchone()

        if items:
            colNames = ['c1', 'c2', 'c3']
            # append item in index by column name
            for c in colNames:
                if items[c] != 0:
                    rItems.append({'name': items[c]})

        cursor.close()
    return jsonify(rItems)


@app.route('/get_item_ids', methods=['POST'])
def get_item_ids():
    data = request.json
    current_item_ids = data.get('currentItemIds', [])
    discovered = handleItemIds(session['participantID'], current_item_ids, False)
    if discovered:
        human_discovered_items[session['experimentID']].append(
            {'pID': session['participantID'], 'item': discovered, 'solution': current_item_ids})
    return jsonify(message="Image IDs received")


def handleItemIds(pID, current_item_ids, bot):
    if len(current_item_ids) >= 1:

        if not bot:
            # Append or initialize trials in session
            if 'number_of_trials' in session:
                session['number_of_trials'] += 1
            else:
                session['number_of_trials'] = 1
        else:
            bot.number_of_trials += 1

        trialNum = session['number_of_trials'] if not bot else bot.number_of_trials
        # open connection to db
        connection = get_db_connection()
        cursor = connection.cursor()

        # Convert to int, sort, convert back to string
        current_item_ids = [int(numeric_string) for numeric_string in current_item_ids]
        current_item_ids.sort()
        current_item_ids = [str(numeric) for numeric in current_item_ids]

        # Append this string with the current item id delimited by a .
        trialStr = ''
        for j in range(len(current_item_ids)):
            trialStr = trialStr + '.' + current_item_ids[j]

        # Save with current date time
        current_datetime = datetime.now().isoformat()
        # print(f'Updating trials for: {pID}')
        cursor.execute('INSERT INTO cce_experiments.trials VALUES \
                (%s, %s, %s, %s)',
                       (pID, trialStr, trialNum, current_datetime))
        connection.commit()

        # append a maximum of 3 zero's
        for j in range(len(current_item_ids), 3):
            current_item_ids.append('0')

        # select a discovered totem by item ids
        cursor.execute(
            'SELECT * FROM cce_experiments.totemgame where c1 = %s and c2 = %s and c3 = %s',
            (current_item_ids[0], current_item_ids[1], current_item_ids[2]))
        item = cursor.fetchone()

        newlyDiscoveredItem = None

        # if found, get the state
        if item:
            cursor.execute(
                'SELECT * FROM cce_experiments.gamestate where participantID = %s and itemID = %s',
                (pID, item['item'],))
            discovered = cursor.fetchone()

            # if not discovered, make one
            if not discovered:
                newlyDiscoveredItem = item['item']
                print(f'Updating gamestate for: {pID}')
                cursor.execute('INSERT INTO cce_experiments.gamestate VALUES \
                    (%s, %s, %s)', (pID, item['item'], trialNum))
                connection.commit()

                cursor.execute('Select score from cce_experiments.participants where pID = %s',
                               (pID,))
                score = cursor.fetchone()
                if not bot:
                    session['score'] = int(score['score']) + int(item['point'])
                    nScore = session['score']
                else:
                    bot.score += int(item['point'])
                    nScore = bot.score
                print(f'Updating score for participant: {pID}')
                cursor.execute('UPDATE cce_experiments.participants set score = %s where pID = %s',
                               (nScore, pID,))
                connection.commit()

        cursor.close()
        return newlyDiscoveredItem


##################  Group totem game ###########################
@app.route("/groupTotem")
def groupTotem():
    # Valid session check
    if 'experiment_type' in session:
        if session['experiment_type'] == 0:
            return redirect("/individualTotem")

    if session['experimentID'] in bot_controllers and not bot_controllers[session['experimentID']].game_started:
        bot_controllers[session['experimentID']].game_started = True
    elif session['experimentID'] not in bot_controllers and session['experiment_type'] == 1:
        return redirect("/groupIntro")



    # Open up a connection to the DB
    connection = get_db_connection()
    cursor = connection.cursor()

    if 'score' not in session:
        session['number_of_trials'] = 0
        session['score'] = 0
        # if host?, then update the start time and go to the game
        current_datetime = datetime.now().isoformat()
        session['stored_datetime'] = current_datetime

        # fetch time and update if non existent
        cursor.execute(
            'SELECT StartTime FROM cce_experiments.experiments where id = %s', (session['experimentID'],))
        entry = cursor.fetchone()
        if entry['StartTime'] is None:
            cursor.execute("UPDATE cce_experiments.experiments SET StartTime = %s, started = 1 WHERE id = %s",
                           (current_datetime, session['experimentID'],))
            connection.commit()

    inventoryItemIDs = getGamestateForParticipant(session['participantID'])

    # Fetch all ids and scores
    cursor.execute(
        'SELECT pID,score,isRobot from cce_experiments.participants WHERE pID !=%s and experimentID = %s ORDER by pID',
        (session['participantID'], session['experimentID']))
    result = cursor.fetchall()
    participants = []
    counter = 1
    # append participants per row of id and scores
    for row in result:
        participants.append([row['pID'], counter, row['score'], row['isRobot']])
        counter = counter + 1

    # print(participants)
    cursor.close()
    return render_template("groupTotem.html", inventoryItemIDs=inventoryItemIDs,
                           startingTime=session['stored_datetime'], numOfTrials=session['number_of_trials'],
                           participants=participants, score=session['score'],
                           semantic_extension=session['semantic_extension'])


@app.route('/btnParticipant', methods=['POST'])
def btnParticipant():
    data = request.get_json()
    parID = data.get('buttonId', '')
    session['otherParID'] = parID

    # Open up a connection to the DB
    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute(
        'Select itemID from cce_experiments.gamestate where participantID = %s and innoTrial!=0', (parID,))
    results = cursor.fetchall()

    # Append all of the item ids
    innoPar = []
    for row in results:
        innoPar.append({'name': row['itemID']})

    # Get score by participant id
    cursor.execute('Select score from cce_experiments.participants where pID = %s', (parID,))
    score = cursor.fetchone()

    # get scores by experiment id
    cursor.execute('Select score from cce_experiments.participants where experimentID = %s', (session['experimentID'],))
    allParticipantScores = cursor.fetchall()

    # Append all scores
    allscores = ""
    for row in allParticipantScores:
        allscores = allscores + "." + str(row['score'])

    # Save with the time now
    checkedTime = datetime.now().isoformat()

    cursor.execute(
        'INSERT INTO cce_experiments.socialinteractions VALUES \
        (%s, %s, %s, %s, %s, %s, 0, %s)', (
            session['participantID'], parID, session['number_of_trials'], session['score'], score['score'], allscores,
            checkedTime))
    connection.commit()
    cursor.close()

    return jsonify(innoPar)


@app.route('/dispRule', methods=['POST'])
def dispRule():
    data = request.get_json()
    itemID = data.get('item', '')

    # Get one game by itemID
    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute('SELECT * FROM cce_experiments.totemgame WHERE item = %s', itemID)
    items = cursor.fetchone()

    rItems = []

    if items:
        # define columns
        colNames = ['c1', 'c2', 'c3']
        # iterate through
        for c in colNames:
            # if index of items fetched has an entry that is this iteration
            if items[c] != 0:
                # Add to list as the name
                rItems.append({'name': items[c]})

    # Get scores by other participant id
    cursor.execute('Select score from cce_experiments.participants where pID = %s', (session['otherParID'],))
    score = cursor.fetchone()

    # Get scores by this experiment id
    cursor.execute('Select score from cce_experiments.participants where experimentID = %s', (session['experimentID'],))
    allParticipantScores = cursor.fetchall()

    allscores = ""
    # Append all of the participant scores to a string delimted by a .
    for row in allParticipantScores:
        allscores = allscores + "." + str(row['score'])

    # Now
    checkedTime = datetime.now().isoformat()

    # Insert into db
    cursor.execute(
        'INSERT INTO cce_experiments.socialinteractions VALUES \
        (%s, %s, %s, %s, %s, %s, %s, %s)', (
            session['participantID'], session['otherParID'], session['number_of_trials'], session['score'],
            score['score'],
            allscores, itemID, checkedTime))
    connection.commit()
    cursor.close()

    return jsonify(rItems)


@app.route('/updateParticipantScores', methods=['POST'])
def updateParticipantScores():
    button_ids = request.json['button_ids']
    response_data = []
    # Iterate through ids
    for button_id in button_ids:
        if button_id != '':
            # fetch one score by pID
            try:
                # Open connection to db
                connection = get_db_connection()
                cursor = connection.cursor()
                cursor.execute('SELECT score FROM cce_experiments.participants WHERE pID = %s', button_id)
                score = cursor.fetchone()
                cursor.close()
                if score:
                    response_data.append({'button_id': button_id, 'score': score['score']})
            except Exception as e:
                print(f"Error: {e}")

    current_datetime = datetime.now().isoformat()

    return jsonify({'data': response_data, 'currentTime': current_datetime, 'startTime': session['stored_datetime']})


##################  Group totem game ###########################

@app.route('/expClosed')
def expClosed():
    bot_controllers[session['experimentID']].game_started = False
    del bot_controllers[session['experimentID']]
    del human_discovered_items[session['experimentID']]
    # Update experiment endtime with current datetime
    expID = session['experimentID']
    current_datetime = datetime.now().isoformat()
    # Open up a connection to the DB
    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute("UPDATE cce_experiments.experiments SET type = -1, EndTime = %s, code = %s WHERE id = %s",
                   (current_datetime, "nocomp", expID,))
    connection.commit()
    cursor.close()
    return render_template('expClosed.html')


@app.route('/experimentComplete')
def experimentComplete():
    bot_controllers[session['experimentID']].game_started = False
    del bot_controllers[session['experimentID']]
    del human_discovered_items[session['experimentID']]
    if 'experimentID' in session:
        expID = session['experimentID']

        # Update endtime with current time if doesnt exist.
        current_datetime = datetime.now().isoformat()
        # Open up a connection to the DB
        connection = get_db_connection()
        cursor = connection.cursor()

        cursor.execute(
            'SELECT EndTime FROM cce_experiments.experiments where id = %s', (expID,))
        entry = cursor.fetchone()
        if entry['EndTime'] is None:
            cursor.execute("UPDATE cce_experiments.experiments SET EndTime = %s, code = %s WHERE id = %s",
                           (current_datetime, "C1GS5IXU", expID,))
            connection.commit()

        cursor.close()
    # Experiment type is individual play
    if session['experiment_type'] == 0:
        return redirect("https://forms.gle/fZAmz7gy3ieqwhkz7")
    # experiment type is group play
    else:
        return redirect("https://forms.gle/61hPEoCwrWb5VW7R6")
    # return render_template('https://app.prolific.com/submissions/complete?cc=C1GS5IXU')


def get_available_item_ids_by_pid(pid):
    # Open up a connection to the DB
    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute(
        'Select itemID from cce_experiments.gamestate where participantID = %s', (pid,))

    itemIds = [row['itemID'] for row in cursor.fetchall()]
    cursor.close()
    return itemIds


if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True, port=5000, threaded=True)
