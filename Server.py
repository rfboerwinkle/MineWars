import asyncio
import websockets
import threading
import json
import time
import math
import random
import numpy as np
import io

from Galactic import *
from GameMap import *

Actions = []

async def Reciever(websocket, path):
	global Actions
	Actions.append({"metatype":"new player", "websocket":websocket})
	try:
		async for message in websocket:
			data = json.loads(message)
			data["metatype"] = "player action"
			data["websocket"] = websocket
			Actions.append(data)
	finally:
		Actions.append({"metatype":"remove team", "websocket":websocket})

def MainLoop():
	global Actions

	Teams = []
	Strangers = [] # list of websockets that haven't been setup yet

	Settings = {}
	Map = GameMap()

	Lasers = []

	# TODO: maybe have one big loop that everything else looks off of, like liquid things
	ENERGY_COOLDOWN = 15
	EnergyTimer = 15

# setup functions

	def MakeNew(thing, mapfill=False):#mapfill can't be a list; TODO make things fill with "None", maybe
		if thing == "team":#energy needs = [coords]
			return {"websocket":False, "name":"", "color":[0,0,0], "status":"w", "energy":0, "base coords":[0,0], "energy needs":[], "soylent":0, "liquid map": np.zeros(Map.shape, dtype=np.uint16)}
		elif thing == "map":
			return [[mapfill for x in range(Map.shape[1])] for y in range(Map.shape[0])]
		elif thing == "base":
			return {"type":"base", "teamID":0, "health":50, "completion":50, "connections":[]}
		elif thing == "collector":
			return {"type":"collector", "teamID":0, "health":1, "completion":5, "connections":[], "connected":False}
		elif thing == "blaster":
			return {"type":"blaster", "teamID":0, "health":10, "completion":15, "angle":0, "ammo":0, "connections":[], "cooldown":0}
		elif thing == "emitter":
			return {"type":"emitter", "teamID":0, "health":10, "completion":15, "ammo":0, "connections":[], "cooldown":0}
		elif thing == "relay":
			return {"type":"relay", "teamID":0, "health":5, "completion":10, "connections":[]}

	BlasterCircle = Circle(BLASTER_RANGE*2)

	def NewMap(mapName):
		nonlocal Map, Teams # TODO: reset the teams
		Map = GameMap(mapName, Teams)
		Sync()

# building "Function" functions

	def EmitterFunction(x,y):
		building = Map.buildings.data[y][x]

		if building["completion"] > 0 or building["ammo"] <= 0:
			return
		building["ammo"] -= 1

		Map.liquids.add(building["teamID"], 1, x, y)
		Map.buildings.deltas.append((x,y))

	def BlasterFunction(x,y):# TODO make line of sight
		building = Map.buildings.data[y][x]

		if building["completion"] > 0 or building["ammo"] <= 0:
			return
		building["cooldown"] -= 1
		if building["cooldown"] <= 0:
			building["cooldown"] = BuildingInfo["blaster"]["cooldown"]
		else:
			return

		rawTiles = np.where(BlasterCircle)
		rawy = rawTiles[0] - BlasterCircle.shape[0]//2
		rawx = rawTiles[1] - BlasterCircle.shape[1]//2
		for tile in sorted(zip(rawy, rawx), key=lambda x:x[0]**2+x[1]**2):#no sqrt, because it is a strictly increasing funciton
			coords = (tile[0] + x, tile[1] + y)
			if not Map.checkEdges(coords):
				continue

			if Map.liquids.heights[coords[1], coords[0]] > 0 and (Map.liquids.teams[coords[1], coords[0]] != building["teamID"] or building["teamID"] == 0):
				Map.buildings.deltas.append([x,y])
				startcoords = (x+BuildingInfo["blaster"]["shape"][0]/2, y+BuildingInfo["blaster"]["shape"][1]/2)
				Lasers.append((startcoords, (coords[0]+0.5, coords[1]+0.5)))
				Map.liquids.sub(5, coords[0], coords[1])
				building["ammo"] -= 1
				break

			if Map.buildings.data[coords[1]][coords[0]]:
				attackBuilding, attackCoords = Map.buildings.query(coords)
				if attackBuilding is building:
					continue
				if attackBuilding["teamID"] != building["teamID"] or building["teamID"] == 0:
					Map.buildings.deltas.append(attackCoords)
					Map.buildings.deltas.append((x,y))
					startCoords = (x+BuildingInfo["blaster"]["shape"][0]/2, y+BuildingInfo["blaster"]["shape"][1]/2)
					Lasers.append((startCoords, (coords[0]+0.5, coords[1]+0.5)))
					attackBuilding["health"] -= 5
					if attackBuilding["health"] <= 0:
						Map.buildings.raze(attackCoords)
					building["ammo"] -= 1
					break

# transmission functions

	def Send(message, websocket=None):
		message = json.dumps(message, separators=(",", ":"), default=Serialize)
		print(f"O({len(message)}): {message}")
		if websocket:
			asyncio.run(websocket.send(message))
		else:
			for team in Teams:
				asyncio.run(team["websocket"].send(message)) # Martin: Really, we shouldn't call run each time. We need to make a separate message collector event loop handle thing

	def Serialize(obj):
		if isinstance(obj, np.ndarray):
			if obj.dtype == np.uint8:
				f = io.StringIO()
				np.savetxt(f, obj, fmt="%2x")
				f.seek(0)
				return f.read()
			else:
				raise TypeError(f"Tried to serialize numpy array:\n{obj}\nof dtype:\n{obj.dtype}\nbut didn't recognize type!")
		elif isinstance(obj, np.int64) or isinstance(obj, np.uint8):
			return int(obj)
		else:
			raise TypeError(f"Tried to serialize object:\n{obj}\nof type:\n{type(obj)}\nbut didn't recognize type!")

	def Doctor(thingType, thing, onTeam=True):
		if thingType == "building":
			if thing["type"] == "coords":
				return thing
			keys = ("type", "teamID", "connections")
			if onTeam:
				keys = keys + ("health", "completion")
				if BuildingInfo[thing["type"]]["ammo"]:
					keys = keys + ("ammo",)

		elif thingType == "flying building":
			keys = ("type", "teamID")
			if onTeam:
				keys = keys + ("health",)

		elif thingType == "team":
			keys = ("color", "status")
			if onTeam:
				keys = keys + ("energy",)

		output = {key: thing[key] for key in keys}
		if thingType == "team" and onTeam: # Inelegant, if you can find a better way, go right ahead
			output["energy"] = int(output["energy"])
		return output

	def Sync(teamID=None):
		print("Syncing")

		doctoredBuildings = []
		for line in Map.buildings.data:
			doctoredLine = []
			for square in line:
				if square == False:
					doctoredLine.append(False)
				else:
					doctoredSquare = Doctor("building", square)
					doctoredLine.append(doctoredSquare)
			doctoredBuildings.append(doctoredLine)

		doctoredTeams = [Doctor("team", team) for team in Teams]

		outgoing = {
			"type": "sync",
			"terrain colors": Map.terrain.colors,
			"terrain map": Map.terrain.heights,
			"soylent map": Map.soylent.teams,
			"building map": doctoredBuildings,
			"liquid map height": Map.liquids.heights,
			"liquid map team": Map.liquids.teams,
			"teams": doctoredTeams
		}
		if teamID:
			outgoing["own teamID"] = teamID
			Send(outgoing, websocket = Teams[teamID-1]["websocket"])
			print("    sent to team number:", teamID)
		else:
			for teamID in range(1, len(Teams)+1):
				outgoing["own teamID"] = teamID
				Send(outgoing, websocket = Teams[teamID-1]["websocket"])
				print("    sent to team number:", teamID)

#cyclic / updating functions

	def IncrementEnergy():
		nonlocal Teams
		for i,team in enumerate(Teams):
			if team["status"] == "a":
				team["energy"] += .5
				team["energy"] += team["soylent"] * .005

	def RemoveTeam(teamID): # remember to remove: buildings.baseCoords, liquids.teamHeights, soylent.teamSums
		Map.removeTeam(teamID)
		Teams.pop(teamID-1)
		Sync()
		print("Teams:", Teams)

	lastTime = None
	maxFrameTime = 0;
	def WaitFramerate(T):
		nonlocal lastTime, maxFrameTime
		ctime = time.monotonic()
		if lastTime:
			frameTime = ctime-lastTime
			sleepTime = T-frameTime
			if frameTime > maxFrameTime:
				maxFrameTime = frameTime
				print("Frame took "+str(maxFrameTime))
			lastTime = lastTime+T
			if sleepTime > 0:
				time.sleep(sleepTime)
		else:
			lastTime = ctime

	NewMap("PCB")
	while True:
		WaitFramerate(1/30)
		#take input
		for i in range(len(Actions)):
			action = Actions.pop(0)
			print("I:", action)
			if action["metatype"] == "new player":
				Strangers.append(action["websocket"])
			elif action["metatype"] == "remove team":
				for teamID in range(1, len(Teams)+1):
					if Teams[teamID-1]["websocket"] == action["websocket"]:
						RemoveTeam(teamID)
						break
				for stranger in range(len(Strangers)):
					if Strangers[stranger] == action["websocket"]:
						Strangers.pop(stranger)
						break
			elif action["metatype"] == "player action":
				if action["type"] == "setup":
					for stranger in range(len(Strangers)):
						if Strangers[stranger] == action["websocket"]:
							Teams.append(MakeNew("team"))
							teamID = len(Teams)
							Teams[teamID-1]["websocket"] = action["websocket"]
							Teams[teamID-1]["color"] = action["color"]
							Teams[teamID-1]["name"] = action["name"]
							Sync(teamID=teamID)
							Strangers.pop(stranger)
							print("Teams:", Teams)
					continue
				for teamID in range(1, len(Teams)+1):
					if Teams[teamID-1]["websocket"] == action["websocket"]:
						if action["type"] == "erect":
							action["coords"] = tuple(action["coords"])
							if Map.checkPlace(BuildingInfo[action["building"]]["shape"], action["coords"]) and action["building"] != "base":
								newBuilding = MakeNew(action["building"])
								newBuilding["teamID"] = teamID
								Map.buildings.place(newBuilding, action["coords"])
								Map.census(teamID)
						elif action["type"] == "raze":
							action["coords"] = tuple(action["coords"])
							building, coords = Map.buildings.query(action["coords"])
							if building:
								if building["teamID"] == teamID and building["type"] != "base":
									Map.buildings.raze(coords)
						elif action["type"] == "translate":
							action["start"] = tuple(action["start"])
							action["end"] = tuple(action["end"])
							building = Map.buildings.query(action["start"])[0]
							if building:
								if building["teamID"] == teamID and BuildingInfo[building["type"]]["movable"]:
									if Map.checkPlace(BuildingInfo[building["type"]]["shape"], action["end"]):
										Map.buildings.translate(action["start"], action["end"])
						elif action["type"] == "land":
							if Teams[teamID-1]["status"] == "w":
								action["coords"] = tuple(action["coords"])
								if Map.checkPlace(BuildingInfo["base"]["shape"], action["coords"]):
									Teams[teamID-1]["base coords"] = action["coords"]
									Teams[teamID-1]["status"] = "a"
									newBuilding = MakeNew("base")
									newBuilding["teamID"] = teamID
									newBuilding["completion"] = 0
									Map.buildings.place(newBuilding, action["coords"])
						else:
							print("UFO: ", action)
						break
		# do stuff
		EnergyTimer -= 1
		if EnergyTimer <= 0:
			IncrementEnergy()
			EnergyTimer = ENERGY_COOLDOWN

		Map.buildings.fly()

		for teamID in range(1, len(Teams)+1): # do stuff per team
			# distribute energy
			# intrinsically sorted by distance from base, maybe something else later?

			toRemove = []
			for i,need in enumerate(Teams[teamID-1]["energy needs"]):
				if Teams[teamID-1]["energy"] >= 1:
					building = Map.buildings.data[need[1]][need[0]]
					if building == False:
						toRemove.append(i)
						continue
					if building["completion"] > 0:
						building["completion"] -= 1
						Map.buildings.deltas.append(need)
						Teams[teamID-1]["energy"] -= 1
						if building["completion"] == 0:
							Map.census(teamID) # maybe only make it census max once per turn
					elif BuildingInfo[building["type"]]["ammo"]:
						if building["ammo"] < BuildingInfo[building["type"]]["ammo"]:
							building["ammo"] += 1
							Map.buildings.deltas.append(need)
							Teams[teamID-1]["energy"] -= 1
					else:
						toRemove.append(i)

			lower = 0
			for i in toRemove:
				Teams[teamID-1]["energy needs"].pop(i - lower)
				lower += 1

		for y in range(Map.shape[0]): # make buildings function
			for x in range(Map.shape[1]):
				building = Map.buildings.data[y][x]
				if not building:
					continue
				if building["type"] == "blaster":
					BlasterFunction(x,y)
				elif building["type"] == "emitter":
					EmitterFunction(x,y)

		Map.liquids.flow()
		Map.liquids.merge()

		# transmit
		# TODO: only send the deltas needed, also make this whole segment more elegant
		BuildingMapDelta = Map.buildings.getDeltas()
		SoylentMapDelta = Map.soylent.getDeltas()
		LiquidMapDelta = list(Map.liquids.getDeltas()) # returns a "zip"
		if len(BuildingMapDelta) > 0 or len(SoylentMapDelta) > 0 or len(LiquidMapDelta) > 0:
			outgoingdeltas = {"type":"deltas", "building map":[], "soylent map":[], "liquid map":[]}
			for coords in BuildingMapDelta:
				building = Map.buildings.data[coords[1]][coords[0]]
				if building:
					doctoredbuilding = Doctor("building", building)
				else:
					doctoredbuilding = False
				outgoingdeltas["building map"].append((coords, doctoredbuilding))
			BuildingMapDelta = []

			for coords in SoylentMapDelta:
				outgoingdeltas["soylent map"].append((coords, Map.soylent.teams[coords[1], coords[0]]))
			SoylentMapDelta = []

			for coords in LiquidMapDelta:
				outgoingdeltas["liquid map"].append((coords, Map.liquids.heights[coords[1], coords[0]], Map.liquids.teams[coords[1], coords[0]]))
			LiquidMapDelta = []
			Send(outgoingdeltas)

		outgoingmisc = {"type":"misc"}

		doctoredflyingbuildings = []
		for building in Map.buildings.flying:
			doctoredbuilding = [Doctor("flying building", building[0]), building[2]]
			doctoredflyingbuildings.append(doctoredbuilding)
		outgoingmisc["flying buildings"] = doctoredflyingbuildings

		outgoingmisc["teams"] = [Doctor("team", team) for team in Teams]

		outgoingmisc["lasers"] = Lasers
		Lasers = []

		# end of segment that needs eleganting

		Send(outgoingmisc)

GameThread = None
GameThread = threading.Thread(group=None, target=MainLoop, name="GameThread")
GameThread.start()
asyncio.get_event_loop().run_until_complete(websockets.serve(Reciever, port=2000))
asyncio.get_event_loop().run_forever()
