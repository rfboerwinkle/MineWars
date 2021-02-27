import asyncio
import json
import websockets
import threading
import time
import copy
import math

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
	Team = {"websocket":False, "color":[0,0,0], "status":"w", "energy":0, "base coords":[0,0], "energy needs":[], "ammo paths":[], "packets":[]}
	#status: "w":waiting to place a base, "a":alive, "d":dead, "l":left and websocket is false
	#energy needs:[type, needed energy, path] note that needed energy can be zero, meaning the packets are on their way.
	#packets:[type, path, last index, distancegone, distanceleft]

	Packet = {"type":"construction", "path":False, "start":0, "end":1, "distance traveled":0, "total distance":0}#"start" and "end" are the index (of "path") of the current buildings it is between

	Settings = {}

	TerrainColors = []
	TerrainMap = [[[15,True],[14,False],[13,False],[12,False]], [[8,False],[9,False],[10,False],[11,False]], [[7,False],[6,False],[5,False],[4,False]], [[0,False],[1,False],[2,False],[3,True]]] #[height, (is a mine?)]

	BuildingInfo = {"base":{"movable":True, "ammo":False}, "collector":{"movable":False, "ammo":False}, "blaster":{"movable":True, "ammo":True}, "relay":{"movable":False, "ammo":False}}
	Buildings = {"base":{"type":"base", "team":0, "health":50, "completion":50, "energy":20, "connections":[]}, "collector":{"type":"collector", "team":5, "health":1, "completion":5, "connections":[]}, "blaster":{"type":"blaster", "team":0, "health":10, "completion":15, "angle":0, "ammo":[0,10], "connections":[]}, "relay":{"type":"relay", "team":10, "health":5, "completion":10, "connections":[]}}#remember to copy.deepcopy
	BuildingMap = []#Building, otherwise False
	FlyingBuildings = []#[Building, vector, currentcoords, endcoords]  starting coords are in Building["coords"]
	BuildingMapDelta = []#[coords]
	LiquidMap = []#[team, height]

	Lazers = []#[start coords, end coords]

	ConnectionRange = 5
	BlasterRange = 10
	EightSquares = ((-1,-1), (0,-1), (1,-1), (1,0), (1,1), (0,1), (-1,1), (-1,0))

	def Circle(r, donut = True, sort = False):
		rsqr = r*r

		tiles = []
		for x in range((r*-1), (r+1)):
			xsqr = x*x
			for y in range((r*-1), (r+1)):
				if(x == 0 and y == 0 and donut):
					continue
				ysqr = y*y
				if((xsqr + ysqr) <= rsqr):
					tiles.append([x,y])

		if(sort):
			tiles.sort(key = lambda x:abs(x[0])+abs(x[1]))
		return tiles

	ConnectionCircle = Circle(ConnectionRange, sort = True)
	BlasterCircle = Circle(BlasterRange, sort = True)

	def NewMap(mapname):
		nonlocal TerrainColors, TerrainMap, BuildingMap, Settings, LiquidMap, FlyingBuildings

		mapfile = open("Maps/"+mapname+".txt", "r")#Line 1: TerrainColor, 2: TerrainMap, 3+:optional settings
		maplist = mapfile.read()
		maplist = maplist.splitlines()
		TerrainColors = json.loads(maplist[0])
		TerrainMap = json.loads(maplist[1])
		for i in range(len(maplist)-2):
			tointerpret = maplist[i+2]
			name = ""
			for char in tointerpret:
				if(char == ":"):
					setting = name
					name = ""
					continue
				name = name + char
			print(name)
			Settings[setting] = json.loads(name)
		print(Settings)

		LiquidMap = []
		for row in TerrainMap:
			newrow = []
			for square in row:
				newrow.append(False)
			LiquidMap.append(newrow)

		FlyingBuildings = []

		BuildingMap = []
		for row in TerrainMap:
			newrow = []
			for square in row:
				newrow.append(False)
			BuildingMap.append(newrow)

		Send({"type":"terrain map", "map":TerrainMap})
		Send({"type":"terrain colors", "colors":TerrainColors})
		Send({"type":"settings", "settings":Settings})

	def CheckEdges(coords):
		if(coords[0]<0 or coords[1]<0 or coords[0] >= len(TerrainMap[0]) or coords[1] >= len(TerrainMap)):
			return False
		else:
			return True

	def distance(coords1, coords2):
		return math.sqrt((coords1[0] - coords2[0])**2 + (coords1[1] - coords2[1])**2)

	def GetEnergy():#needs to be changed to soylent
		for line in BuildingMap:
			for square in line:
				if(square == False):
					continue
				if(square["type"] == "base" or square["type"] == "collector"):
					if(square["completion"] == 0):
						Teams[square["team"]]["energy"] += .05

	def Send(message, websocket = False):
		message = json.dumps(message)
		if not(websocket):
			for team in Teams:
				if(team["status"] == "l"):
					continue
				asyncio.run(team["websocket"].send(message))#Really, we shouldn't call run each time. We need to make a separate message collector event loop handle thing
		else:
			asyncio.run(websocket.send(message))

	def Sync():
		nonlocal BuildingMap

		doctoredbuildingmap = []
		for line in BuildingMap:
			doctoredline = []
			for square in line:
				if(square == False):
					doctoredline.append(False)
				else:
					doctoredsquare = {"type":square["type"], "team":square["team"]}
					doctoredsquare["connections"] = square["connections"]
					doctoredline.append(doctoredsquare)
			doctoredbuildingmap.append(doctoredline)

		outgoing = {"type":"sync", "building map":doctoredbuildingmap}
		Send(outgoing)

	def RemoveConnections(coords):
		for i in range(len(BuildingMap[coords[1]][coords[0]]["connections"])):
			connection = BuildingMap[coords[1]][coords[0]]["connections"].pop(0)
			BuildingMap[connection[1]][connection[0]]["connections"].remove(coords)

	def MakeConnections(coords):
		nonlocal ConnectionCircle
		for rawtile in ConnectionCircle:
			tile = [rawtile[0]+coords[0], rawtile[1]+coords[1]]
			if not(CheckEdges(tile)):
				continue
			if(BuildingMap[tile[1]][tile[0]]):
				if(BuildingMap[tile[1]][tile[0]]["team"] == BuildingMap[coords[1]][coords[0]]["team"]):
					BuildingMap[tile[1]][tile[0]]["connections"].append(coords)
					BuildingMap[coords[1]][coords[0]]["connections"].append(tile)

	def Move(startcoords, endcoords):
		nonlocal BuildingMap, BuildingMapDelta, FlyingBuildings
		building = BuildingMap[startcoords[1]][startcoords[0]]

		if(BuildingMap[endcoords[1]][endcoords[0]]):
			return False
		vector = math.atan2(endcoords[1]-startcoords[1], endcoords[0]-startcoords[0])
		vector = [math.cos(vector), math.sin(vector)]
		if(abs(vector[0]) < .00000001):#to prevent instant moving
			vector[0] = 0
		if(abs(vector[1]) < .00000001):#to prevent instant moving
			vector[1] = 0
		RemoveConnections(startcoords)
		FlyingBuildings.append([building, vector, startcoords, endcoords])
		BuildingMap[startcoords[1]][startcoords[0]] = False
		print(FlyingBuildings[-1])
		Census(building["team"])
		BuildingMapDelta.append(startcoords)

	def Land(flyingbuilding):
		nonlocal BuildingMap, Teams, BuildingMapDelta, FlyingBuildings

		building = flyingbuilding[0]
		building["coords"] = flyingbuilding[3]
		if(building["type"] == "base"):
			Teams[building["team"]]["base coords"] = [building["coords"][0], building["coords"][1]]
		BuildingMap[flyingbuilding[3][1]][flyingbuilding[3][0]] = building
		MakeConnections(building["coords"])
		Census(building["team"])
		BuildingMapDelta.append(building["coords"])
		FlyingBuildings.remove(flyingbuilding)

	def Raze(coords):
		nonlocal BuildingMap
		nonlocal BuildingMapDelta

		team = BuildingMap[coords[1]][coords[0]]["team"]
		RemoveConnections(coords)
		BuildingMap[coords[1]][coords[0]] = False
		Census(team)
		BuildingMapDelta.append(coords)

	def PacketSearch(team, endcoords, flavor, kill = False):
		nonlocal Teams

		topop = []
		packetnumber = 0

		for i,packet in Teams[team]["packets"]:
			if(packet[0] == flavor):
				if(packet[-1] == endcoords):
					packetnumber += 1
					if(kill):
						topop.append(i)

		for i in reversed(topop):
			Teams[team]["packets"].pop(i)

		return packetnumber

	def Census(team):#try not to use
		nonlocal BuildingMap
		nonlocal BuildingInfo
		nonlocal Teams

		basecoords = Teams[team]["base coords"]
		if not(BuildingMap[basecoords[1]][basecoords[0]]):
			print("Team ", team, " is dead! (or we just can't find the base for some reason...)")
			return

		Teams[team]["energy needs"] = []
		Teams[team]["ammo paths"] = []

		searched = []#just coords
		tosearch = [[basecoords, 0, [basecoords]]]#[coords, total distance(no sqrt), path from base]

		while len(tosearch):
			tosearch.sort(key = lambda x:x[1])
			searching = tosearch.pop(0)
			searched.append(searching[0])
			building = BuildingMap[searching[0][1]][searching[0][0]]

			if(building["completion"] != 0):
				neededenergy = building["completion"] - PacketSearch(building["team"], searching, "construction")
				Teams[team]["energy needs"].append(["construction", neededenergy, searching[2]])
				continue

			if(BuildingInfo[building["type"]]["ammo"]):#TODO use different list
				Teams[team]["ammo paths"].append(searching[2])

			for connectedcoords in building["connections"]:
				found = False
				for coords in searched:
					if(coords == connectedcoords):
						found = True
						break
				if(found):
					continue
				distance = searching[1] + math.sqrt((searching[0][0] - connectedcoords[0])**2 + (searching[0][1] - connectedcoords[1])**2)
				for i,info in enumerate(tosearch):
					if(info[0] == connectedcoords):
						if(info[1] > distance):
							tosearch.pop(i)
						else:
							found = True
						break
				if(found):
					continue

				tosearch.append([connectedcoords, distance, searching[2] + [connectedcoords]])

		print("energy needs: ", Teams[team]["energy needs"])


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

	def BlasterFunction(x,y):
		nonlocal BlasterCircle
		nonlocal BuildingMap
		nonlocal BuildingMapDelta
		nonlocal LiquidMap
		nonlocal Lazers

		building = BuildingMap[y][x]

		if(building["completion"] != 0):
			return
		if(building["ammo"][0] <= 0):
			return

		for tile in BlasterCircle:
			coords = [tile[0] + x, tile[1] + y]
			if not(CheckEdges(coords)):
				continue

			if(LiquidMap[coords[1]][coords[0]]):
				if(LiquidMap[coords[1]][coords[0]][0] != building["team"]):
					BuildingMapDelta.append([x,y])#maybe LiquidMapDelta
					Lazers.append(((x,y),coords))
					LiquidMap[coords[1]][coords[0]][1] -= 5
					if(LiquidMap[coords[1]][coords[0]][1] < 0):
						LiquidMap[coords[1]][coords[0]][1] = 0
					building["ammo"][0] -= 1
					break

			if(BuildingMap[coords[1]][coords[0]]):
				if(BuildingMap[coords[1]][coords[0]]["team"] != building["team"]):
					BuildingMapDelta.append(coords)
					BuildingMapDelta.append([x,y])
					Lazers.append(((x,y),coords))
					BuildingMap[coords[1]][coords[0]]["health"] -= 5
					if(BuildingMap[coords[1]][coords[0]]["health"] < 0):
						Raze(coords)
					building["ammo"][0] -= 1
					break


	NewMap("archipelago")
	while True:
		WaitFramerate(1/30)
		#take input
		for i in range(len(Actions)):
			action = Actions.pop(0)
			if(action["metatype"] == "new player"):
				openteams = []
				Teams.append(copy.deepcopy(Team))
				Teams[-1]["websocket"] = action["websocket"]
				print(Teams)
				Send({"type":"terrain map", "map":TerrainMap}, websocket = Teams[-1]["websocket"])
				Send({"type":"terrain colors", "colors":TerrainColors}, websocket = Teams[-1]["websocket"])
				Send({"type":"settings", "settings":Settings}, websocket = Teams[-1]["websocket"])
				Send({"type":"building info", "info":BuildingInfo}, websocket = Teams[-1]["websocket"])
				Send({"type":"team", "team":len(Teams)-1}, websocket = Teams[-1]["websocket"])
				Sync()
			elif(action["metatype"] == "remove team"):
				for team in range(len(Teams)):
					if(Teams[team]["websocket"] == action["websocket"]):
						Teams[team]["status"] = "l"
						break
			elif(action["metatype"] == "player action"):
				for i,team in enumerate(Teams):
					if(team["websocket"] == action["websocket"]):
						if(action["type"] == "erect"):
							if not(BuildingMap[action["coords"][1]][action["coords"][0]]):
								BuildingMap[action["coords"][1]][action["coords"][0]] = copy.deepcopy(Buildings[action["building"]])
								BuildingMap[action["coords"][1]][action["coords"][0]]["team"] = i
								MakeConnections(action["coords"])
								Census(i)
								BuildingMapDelta.append(action["coords"])
						elif(action["type"] == "raze"):
							if(BuildingMap[action["coords"][1]][action["coords"][0]]):
								if(BuildingMap[action["coords"][1]][action["coords"][0]]["team"] == i and BuildingMap[action["coords"][1]][action["coords"][0]]["type"] != "base"):
									Raze(action["coords"])
						elif(action["type"] == "translate"):
							if(BuildingMap[action["start"][1]][action["start"][0]]):
								if(BuildingMap[action["start"][1]][action["start"][0]]["team"] == i):
									Move(action["start"], action["end"])
						elif(action["type"] == "land"):
							if(team["status"] == "w"):
								team["color"] = action["color"]
								team["base coords"] = action["coords"]
								team["status"] = "a"
								BuildingMap[action["coords"][1]][action["coords"][0]] = copy.deepcopy(Buildings["base"])
								BuildingMap[action["coords"][1]][action["coords"][0]]["team"] = i
								BuildingMap[action["coords"][1]][action["coords"][0]]["completion"] = 0
								BuildingMapDelta.append(action["coords"])
						elif(action["type"] == "color"):
							team["color"] = action["color"]
						elif(action["type"] == "say"):
							print(i, ": ", action["words"])
						break
		#do stuff
		GetEnergy()

		#fly buildings
		for flyingbuilding in FlyingBuildings:
			flyingbuilding[2] = [flyingbuilding[2][0] + flyingbuilding[1][0], flyingbuilding[2][1] + flyingbuilding[1][1]]
			if(flyingbuilding[1][0] > 0):
				if(flyingbuilding[2][0] >= flyingbuilding[3][0]):
					Land(flyingbuilding)
			elif(flyingbuilding[1][0] < 0):
				if(flyingbuilding[2][0] <= flyingbuilding[3][0]):
					Land(flyingbuilding)
			else:
				if(flyingbuilding[1][1] > 0):
					if(flyingbuilding[2][1] >= flyingbuilding[3][1]):
						Land(flyingbuilding)
				else:
					if(flyingbuilding[2][1] <= flyingbuilding[3][1]):
						Land(flyingbuilding)

		for team in Teams:
			#get ammo needs
			for path in team["ammo paths"]:
				building = BuildingMap[path[-1][1]][path[-1][0]]
				if(building == False):
					team["ammo paths"].remove(path)
					continue
				if(building["ammo"][0] < building["ammo"][1]):
					goodtogo = True
					for need in team["energy needs"]:
						if(need[2][-1] == path[-1]):
							goodtogo = False
							break

					if(goodtogo):
						team["energy needs"].append(["ammo", building["ammo"][1] - building["ammo"][0], path])

			#distribute energy
			team["energy needs"].sort(key = lambda x:x[1])
			if(len(team["energy needs"]) != 0):
				print("----------", team["energy needs"])

			toremove = []
			toadd = []
			for i,need in enumerate(team["energy needs"]):
				if(team["energy"] >= 1 and need[1] > 0):
					BuildingMapDelta.append(need[2][-1])#move to when packet arrives
					team["energy"] -= 1
					building = BuildingMap[need[2][-1][1]][need[2][-1][0]]
					if(building == False):
						toremove.append(i)
						continue
					if(need[0] == "construction"):
						building["completion"] -= 1#should make packet
					if(need[0] == "ammo"):
						building["ammo"][0] += 1#should make packet
					team["energy needs"][i][1] = need[1] - 1
					if(need[1] == 0):
						if(need[0] == "construction"):
							if(building["completion"] == 0):
								if(BuildingInfo[building["type"]]["ammo"]):
									team["ammo paths"].append(need[2])
						toremove.append(i)

			lower = 0
			for i in toremove:
				team["energy needs"].pop(i - lower)
				lower += 1

		for y in range(len(BuildingMap)):
			for x in range(len(BuildingMap[y])):
				if not(BuildingMap[y][x]):
					continue
				if(BuildingMap[y][x]["type"] == "blaster"):
					BlasterFunction(x,y)

		#transmit
		if(len(BuildingMapDelta) > 0):
			outgoingbmd = {"type":"building map delta", "info":[]}
			for coords in BuildingMapDelta:
				building = BuildingMap[coords[1]][coords[0]]
				if(building):
					print(building)
					doctoredbuilding = {"type":building["type"], "team":building["team"], "connections":building["connections"]}
				else:
					doctoredbuilding = False
				outgoingbmd["info"].append([coords, doctoredbuilding])
			BuildingMapDelta = []
			Send(outgoingbmd)

		outgoingmisc = {"type":"misc"}

		doctoredflyingbuildings = []
		for building in FlyingBuildings:
			doctoredbuilding = [{"type":building[0]["type"], "team":building[0]["team"]}, building[2]]
			doctoredflyingbuildings.append(doctoredbuilding)
		outgoingmisc["flying buildings"] = doctoredflyingbuildings

		doctoredteams = []
		for team in Teams:
			doctoredteams.append({"color":team["color"], "status":team["status"], "energy":int(team["energy"])})

		outgoingmisc["teams"] = doctoredteams
		Send(outgoingmisc)

GameThread = None
GameThread = threading.Thread(group = None, target = MainLoop, name = "GameThread")
GameThread.start()
asyncio.get_event_loop().run_until_complete(websockets.serve(Reciever, port=2000))
asyncio.get_event_loop().run_forever()

