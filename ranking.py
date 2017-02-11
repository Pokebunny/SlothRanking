"""
A ranking system for Sloth E-Sports Club that takes into account multiple ranking systems to create an overall player ranking. Includes StarCraft 2 Ladder MMR, Aligulac rating, and Elo rating for inhouse matches, and weights them to create a composite rating (called SlothRating). Elo rating (and other player info) must be initially provided by the user in a file and then results can be updated using this program.

HOW TO USE: Set up a player file. File must be formatted with one player on each line, in the following format:
Name AligulacID BnetID Elo
ex: Pokebunny 462 539205 2000
Aligulac ID can be found on the Aligulac website and Bnet ID can be found through the Bnet website (or ingame profile links).
NOTE: Right now, program will only check Bnet NA.

Initial version has several limitations.
1. Error testing is pretty much non-existent. The main method will check input and make sure nothing bad happens, but it won't check the file you input so may crash or perform strangely if not provided a valid player file. If it crashes, sorry.
2. There's no GUI or packaging, everything has to be done through command line and imported packages must be installed manually.
3. Ladder MMRs are only pulled from North America GM and Master 1. The region would be very easy to change, but other changes would be a bit more of a pain.

TODO in rough order of importance/likeliness to occur:
1. Better error checking.
2. Fetching all player MMRs regardless of league. This should be doable once I figure out the bnet API profile endpoint; right now I am just crawling GM and all Master 1 divisions to find players. Not efficient or functional.
3. Increased user-friendliness; create GUI and package into executable. GUI would also allow user to modify Bnet server to check for MMR, K-factor for Elo calculations, and rating weights.
4. Isolate the Bnet API authentication into a method. It works but it's bad code.
5. Store player information in a more secure way like a database or some other data form.
6. Create a web front-end and set up for more general use and deployment.

file: ranking.py
author: Nick Taber (Pokebunny)
date: 2/8/17
version: 1.0
"""

import requests
from oauthlib.oauth2 import BackendApplicationClient
from requests_oauthlib import OAuth2Session

# file of players
PLAYER_FILE = "players.txt"

# k-factor for elo rating changes
K_FACTOR = 32

# weighting for different rating systems into SlothRating
ELO_WEIGHT = 0.5
ALIG_WEIGHT = 0.3
MMR_WEIGHT = 0.2

# api key for aligulac
ALIG_KEY = "cEykL0jcdBPQmGmq5A8t"

# api keys and token uri's for battle.net api
BNET_KEY = "w26yepbvx7492z63ha77gcsp729sbq35"
BNET_SECRET = "R5wMd66967bGM7bgCS4Ru9swCq8GFXKV"
AUTH_URI = "https://us.battle.net/oauth/authorize"
TOKEN_URI = "https://us.battle.net/oauth/token"

# fetch auth token for session - probably should be done in a function
client = BackendApplicationClient(client_id=BNET_KEY)
oauth = OAuth2Session(client=client)
ACCESS_TOKEN = oauth.fetch_token(token_url=TOKEN_URI, client_id=BNET_KEY, client_secret=BNET_SECRET)

class Player:
    """
    Object to store information about a player.
    Provide player ID (name), aligulac ID, bnet ID, and Elo rating. Aligulac rating and MMR are set to 1 til manually fetched.
    """
    def __init__(self, name, alig=None, bnet=None, elo=2000.0):
        self.name = name
        self.alig = alig
        self.bnet = bnet
        self.elo = elo
        self.aligRating = 1
        self.mmr = 1
        self.sr = 0

def expected(elo1, elo2):
    """
    Calculates the expected score of player 1 vs player 2.
    :param elo1:
    :param elo2:
    :return:
    """
    return 1 / (1 + 10 ** ((elo2 - elo1) / 400))

def adjustElo(oldElo, exp, result, k=K_FACTOR):
    """
    Adjusts Elo rating based on the current elo, expected result, actual result, and K-Factor.
    :param oldElo: initial Elo of the player
    :param exp: expected result (between 0 and 1.0, 0.5 = expected 50% winrate)
    :param result: actual result (generally 0 for loss and 1 for win)
    :param k: K-factor for Elo calculations, a higher K-factor will produce bigger Elo swings
    """
    return oldElo + k * (result - exp)


def result(p1, p2, winner):
    """
    Adjusts two players Elo ratings given the result of a game between them.
    :param p1: Player 1 (must be Player object)
    :param p2: Player 2 (must be Player object)
    :param winner: 1 if p1 wins, 2 if p2 wins
    """
    ex = expected(p1.elo, p2.elo)
    if winner == 1:
        res1 = 1
        res2 = 0
    elif winner == 2:
        res1 = 0
        res2 = 1
    else:
        return
    p1.elo = adjustElo(p1.elo, ex, res1)
    p2.elo = adjustElo(p2.elo, 1 - ex, res2)

def getPlayerList(filename=PLAYER_FILE):
    """
    Given a file path, generates a list of Player objects within the file.
    File must be formatted with one player on each line, in the following format:
    Name AligulacID BnetID Elo
    ex: Pokebunny 462 539205 2000
    :param filename: path to file
    :return: a list of Player objects in the file
    """
    playerList = []
    for line in open(filename):
        line = line.split()
        playerList.append(Player(line[0], line[1], line[2], float(line[3])))
    return playerList

def setAligRatings(playerList):
    """
    Given a list of Player objects, sets all Aligulac rating fields given that all players have valid Aligulac IDs.
    :param playerList:
    :return:
    """
    players = ""
    for p in playerList:
        players += p.alig + ";"
    players = players[:-1]
    url = "http://aligulac.com/api/v1/player/set/" + players + "/?apikey=" + ALIG_KEY + "&format=json"
    response = requests.get(url=url)
    data = response.json()
    i = 0
    for p in playerList:
        cur = data["objects"][i]
        p.aligRating = round(cur["current_rating"]["rating"] * 1000 + 1000)
        i += 1

def setMMRs(playerList):
    """
    Given a player list, attempts to find all players and set MMRs for them. MMR will not be modified if no value is found.
    Only looks through North America 1v1 GM and Master 1, takes highest MMR found.
    :param playerList: the list of Players to set MMRs for.
    """
    # GRANDMASTER
    gmUrl = "https://us.api.battle.net/data/sc2/league/31/201/0/6?access_token=" + ACCESS_TOKEN["access_token"]
    gmResponse = requests.get(url=gmUrl)
    gmLadderId = gmResponse.json()["tier"][0]["division"][0]["ladder_id"]
    url2 = "https://us.api.battle.net/data/sc2/ladder/" + str(gmLadderId) + "?access_token=" + ACCESS_TOKEN["access_token"]
    response2 = requests.get(url=url2)
    data2 = response2.json()
    idDict = bnetIdDict(playerList)
    for i in range(len(data2["team"])):
        id = data2["team"][i]["member"][0]["legacy_link"]["id"]
        if(str(id) in idDict):
            curMMR = idDict[str(id)].mmr
            newMMR = data2["team"][i]["rating"]
            if newMMR > curMMR:
                idDict[str(id)].mmr = newMMR

    # MASTER 1
    masterUrl = "https://us.api.battle.net/data/sc2/league/31/201/0/5?access_token=" + ACCESS_TOKEN["access_token"]
    masterResponse = requests.get(url=masterUrl)
    masterData = masterResponse.json()
    for i in range(len(masterData["tier"][0]["division"])):
        masterLadderId = masterResponse.json()["tier"][0]["division"][i]["ladder_id"]
        masterUrl2 = "https://us.api.battle.net/data/sc2/ladder/" + str(masterLadderId) + "?access_token=" + ACCESS_TOKEN["access_token"]
        masterResponse2 = requests.get(url=masterUrl2)
        masterData2 = masterResponse2.json()
        for i in range(len(masterData2["team"])):
            id = masterData2["team"][i]["member"][0]["legacy_link"]["id"]
            if (str(id) in idDict):
                curMMR = idDict[str(id)].mmr
                newMMR = masterData2["team"][i]["rating"]
                if newMMR > curMMR:
                    idDict[str(id)].mmr = newMMR

def setSRs(playerList):
    """
    Calculates and sets SlothRating for all players in the player list.
    SlothRating is simple, it just weights the three rating components (Aligulac, MMR, and Elo) and adds them together.
    :param playerList: the list of Players to set SRs for.
    :return:
    """
    for p in playerList:
        p.sr = round((p.aligRating * ALIG_WEIGHT) + (p.mmr * MMR_WEIGHT) + round((p.elo * ELO_WEIGHT)))

def savePlayersToFile(playerList, filename=PLAYER_FILE):
    """
    Saves players in a player list to a file.
    NOTE: will overwrite anything in the file without asking.
    :param playerList: The list of Players to save to file.
    :param filename: The file name / path to save to.
    """
    file = open(filename, "w")
    for p in playerList:
        file.write(p.name + " " + p.alig + " " + p.bnet + " " + str(p.elo) + "\n")

def log(resString):
    file = open("log.txt", "a")
    file.write(resString + "\n")

def printRatingList(playerList):
    """
    Prints a table of all player ratings sorted by SlothRating.
    :param playerList: The list of Players to print.
    """
    playerList.sort(key=lambda x: x.sr, reverse=True)
    rank = 1
    print("{0:{width}} {1:{width}} {2:{width}} {3:{width}} {4:{width}} {5:{width}}".format("Rank", "ID", "SlothRating", "Elo", "Aligulac", "MMR", width=15))
    for p in playerList:
        print("{0:{width}} {1:{width}} {2:{width}} {3:{width}} {4:{width}} {5:{width}}".format(str(rank), p.name, str(p.sr), str(round(p.elo)), str(p.aligRating), str(p.mmr), width=15))
        rank += 1
    print()

def bnetIdDict(playerList):
    """
    Creates a dictionary of bnet player IDs mapped to Player objects. Used for setting MMRs of the players.
    :param playerList: the player list to map
    """
    idDict = {}
    for p in playerList:
        idDict[p.bnet] = p
    return idDict

# TODO: FUNCTION INCOMPLETE (can't figure out how to pull profiles)
def bnetLadderDict(playerList):
    ladderDict = {}
    for p in playerList:
        # url = "https://us.api.battle.net/sc2/profile/" + p.bnet + "/document/path?apikey=" + ACCESS_TOKEN["access_token"]
        url = "https://us.api.battle.net/profile/" + p.bnet + "/sc2/document/path?access_token" + ACCESS_TOKEN["access_token"]
        response = requests.get(url=url)
        data = response.json()
        print(data)
        # ladderDict[] = p

def readResultString(resString, playerList):
    """
    Inputs a game result from a string given that the players exist in the player list and string is formatted properly.
    String expected in the format of "ID1 > ID2" or "ID1 < ID2"
    This method actually error checks a bit, unlike everything else.
    :param resString: input string of result
    :param playerList: player list with given players.
    :return:
    """
    p1 = None
    p2 = None
    resArray = resString.split()
    if len(resArray) != 3:
        print("Input not recognized")
    for p in playerList:
        if resArray[0] == p.name:
            p1 = p
        elif resArray[2] == p.name:
            p2 = p
    if p1 == None or p2 == None:
        print("One of the players was not found, please try again.")
    else:
        if resArray[1] == ">":
            result(p1, p2, 1)
            log(resString)
        elif resArray[1] == "<":
            result(p1, p2, 2)
            log(resString)
        else:
            print('Improper use of result string - format should be "ID1 > ID2" or "ID1 < ID2"')


def main():
    """
    Runs the program. Loops asking for command line input with provided instructions.
    """
    plFile = input("Enter the path to the player file (default players.txt): ")
    if plFile == "":
        plFile = "players.txt"
    pl = getPlayerList(plFile)
    print("Fetching aligulac ratings...")
    setAligRatings(pl)
    print("Fetching ladder MMRs...")
    setMMRs(pl)
    while True:
        inp = input('Input game result (ID1 > ID2 or ID1 < ID2), "print" to print the rating list, "exit" to save changes and quit, "forcequit" to quit WITHOUT saving player Elo changes \n')
        if inp == "print":
            setSRs(pl)
            printRatingList(pl)
        elif inp == "exit":
            savePlayersToFile(pl, plFile)
            break
        elif inp == "forcequit":
            break
        else:
            readResultString(inp, pl)
    print("Ending program")

main()