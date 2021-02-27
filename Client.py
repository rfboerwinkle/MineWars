import asyncio
import json
import websockets
import threading
import time
import pygame
pygame.init()
import pygame.gfxdraw

Ip = input("IP of server: ")
Websocket = False
Retry = False
Incoming = []
Close = False

async def Reciever():
	global Websocket
	global Incoming
	global Retry
	global Close
	global Ip
	uri = "ws://" + Ip + ":2000"
	Websocket = await websockets.connect(uri)
	while True:
		info = await Websocket.recv()
		Incoming.append(json.loads(info))
		if(Close):
			await Websocket.close()
			break
	quit()

def MainLoop():
	global Incoming
	global Websocket
	global Retry
	global Close

	Color = input("color in json [r,g,b]: ")
	Color = json.loads(Color)

	ScreenSize = (600, 600)
	screen = pygame.display.set_mode(ScreenSize)
	while not pygame.display.get_active():
		time.sleep(0.1)
	pygame.display.set_caption("Mine Wars","Mine Wars")

	Letters = {"0":"0", "1":"1", "2":"2", "3":"3", "4":"4", "5":"5", "6":"6", "7":"7", "8":"8", "9":"9"}

	for letter in Letters:
		Letters[letter] = pygame.image.load("Pictures/Letters/"+letter+".png")

	HUDTile = pygame.image.load("Pictures/HUDTile.png")
	NonDecorativeHeight = 75

	Teams = []
	OwnTeam = 0
	Settings = {}

	TerrainColors = []
	TerrainMap = [] #[height, is a mine?]
	BuildingMap = []
	FlyingBuildings = []
	BuildingInfo = []

	SelectedCoords = False
	ActionSequence = 0
	ViewCoords = [0,0]
	Action = "T"#"E":erect, "R":raze, "T":translate

	ToBuild = "collector"

	SquareLength = 21
	Center = SquareLength//2
	BuildingRadius = SquareLength//3

	EightSquares = [[-1,-1], [0,-1], [1,-1], [1,0], [1,1], [0,1], [-1,1], [-1,0]]

	HUD = pygame.Surface((ScreenSize[0],HUDTile.get_height()))
	for i in range(ScreenSize[0]//HUDTile.get_width() + 1):
		HUD.blit(HUDTile, (80*i, 0))

	def checkedges(coords):
		if(coords[0]<0 or coords[1]<0 or coords[0] >= len(TerrainMap[0]) or coords[1] >= len(TerrainMap)):
			return False
		else:
			return True

	def displaytext(destination, text, coords):
		for i in range(len(text)):
			destination.blit(Letters[text[i]], coords)
			coords[0] += Letters[text[i]].get_width()

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

	def LoadPictures():
		nonlocal BuildingInfo
		for building in BuildingInfo:
			BuildingInfo[building]["image"] = pygame.image.load("Pictures/Buildings/" + building + ".png")

	while True:
		WaitFramerate(1/60)
		OutgoingMessage = False
		events = pygame.event.get()
		keys = pygame.key.get_pressed()
		if not(Websocket):
			for event in events:
				if(event.type == pygame.QUIT):
					pygame.quit()
					Close = True
			continue

		for event in events:
			if(event.type == pygame.QUIT):
				pygame.quit()
				Close = True
			elif(event.type == pygame.MOUSEBUTTONDOWN):
				clickedcoords = [(event.pos[0] - ViewCoords[0])//SquareLength, (event.pos[1] - ViewCoords[1])//SquareLength]
				if(Teams[OwnTeam]["status"] == "w"):
					OutgoingMessage = {"type":"land", "coords":clickedcoords, "color":Color}
					continue
				if(Action == "T"):
					if(ActionSequence == 0):
						SelectedCoords = clickedcoords
						if(checkedges(SelectedCoords)):
							if(BuildingMap[SelectedCoords[1]][SelectedCoords[0]]):
								if(BuildingMap[SelectedCoords[1]][SelectedCoords[0]]["team"] == OwnTeam):
									ActionSequence = 1
								else:
									SelectedCoords = False
							else:
								SelectedCoords = False
						else:
							SelectedCoords = False
					elif(ActionSequence == 1):
						newcoords = clickedcoords
						if not(BuildingMap[newcoords[1]][newcoords[0]]):
							OutgoingMessage = {"type":"translate", "start":SelectedCoords, "end":newcoords}
						SelectedCoords = False
						ActionSequence = 0
				elif(Action == "E"):
					SelectedCoords = clickedcoords
					if(checkedges(SelectedCoords)):
						if not(BuildingMap[SelectedCoords[1]][SelectedCoords[0]]):
							OutgoingMessage = {"type":"erect", "building":ToBuild, "coords":SelectedCoords}
					SelectedCoords = False
				elif(Action == "R"):
					SelectedCoords = clickedcoords
					if(checkedges(SelectedCoords)):
						if(BuildingMap[SelectedCoords[1]][SelectedCoords[0]]):
							if(BuildingMap[SelectedCoords[1]][SelectedCoords[0]]["team"] == OwnTeam):
								OutgoingMessage = {"type":"raze", "coords":SelectedCoords}
					SelectedCoords = False

		if(keys[pygame.K_UP] or keys[pygame.K_w]):
			ViewCoords[1] += 3
		if(keys[pygame.K_DOWN] or keys[pygame.K_s]):
			ViewCoords[1] -= 3
		if(keys[pygame.K_RIGHT] or keys[pygame.K_d]):
			ViewCoords[0] -= 3
		if(keys[pygame.K_LEFT] or keys[pygame.K_a]):
			ViewCoords[0] += 3
		if(keys[pygame.K_e]):
			Action = "E"
			ActionSequence = 0
			SelectedCoords = False
		if(keys[pygame.K_r]):
			Action = "R"
			ActionSequence = 0
			SelectedCoords = False
		if(keys[pygame.K_t]):
			Action = "T"
			ActionSequence = 0
			SelectedCoords = False
		if(keys[pygame.K_0]):#0
			ToBuild = "base"
		if(keys[pygame.K_1]):#1
			ToBuild = "relay"
		if(keys[pygame.K_2]):#2
			ToBuild = "collector"
		if(keys[pygame.K_3]):#3
			ToBuild = "blaster"

		screen.fill([100,100,200])#start of display

		for row in range(len(TerrainMap)):#display terrain
			for square in range(len(TerrainMap[row])):
				color = TerrainColors[TerrainMap[row][square][0]]
				pygame.gfxdraw.box(screen, [square*SquareLength + ViewCoords[0], row*SquareLength + ViewCoords[1], SquareLength, SquareLength], color)
				if(TerrainMap[row][square][1]):
					pygame.gfxdraw.filled_circle(screen, (square*SquareLength)+Center + ViewCoords[0], (row*SquareLength)+Center + ViewCoords[1], Center, [221, 158, 30])

		for row in range(len(BuildingMap)):#display connections
			for square in range(len(BuildingMap[row])):
				if(BuildingMap[row][square]):
					for connection in BuildingMap[row][square]["connections"]:
						pygame.draw.line(screen, (0,0,0), [(square*SquareLength)+Center + ViewCoords[0], (row*SquareLength)+Center + ViewCoords[1]], [(connection[0]*SquareLength)+Center + ViewCoords[0], (connection[1]*SquareLength)+Center + ViewCoords[1]])

		for row in range(len(BuildingMap)):#display buildings
			for square in range(len(BuildingMap[row])):
				if(BuildingMap[row][square]):
					pygame.gfxdraw.filled_circle(screen, (square*SquareLength)+Center + ViewCoords[0], (row*SquareLength)+Center + ViewCoords[1], BuildingRadius, Teams[BuildingMap[row][square]["team"]]["color"])
					screen.blit(BuildingInfo[BuildingMap[row][square]["type"]]["image"], ((square*SquareLength) + ViewCoords[0], (row*SquareLength) + ViewCoords[1]))

		for building in FlyingBuildings:#display flying buildings
			pygame.gfxdraw.filled_circle(screen, round((building[1][0]*SquareLength)+Center + ViewCoords[0]), round((building[1][1]*SquareLength)+Center + ViewCoords[1]), BuildingRadius, Teams[building[0]["team"]]["color"])
			screen.blit(BuildingInfo[building[0]["type"]]["image"], (round((building[1][0]*SquareLength) + ViewCoords[0]), round((building[1][1]*SquareLength) + ViewCoords[1])))

		if(SelectedCoords):#display selection
			pygame.gfxdraw.rectangle(screen, [SelectedCoords[0]*SquareLength + ViewCoords[0], SelectedCoords[1]*SquareLength + ViewCoords[1], SquareLength, SquareLength], Teams[OwnTeam]["color"])

		hudinfo = pygame.Surface((HUD.get_width(), HUD.get_height()), flags = pygame.SRCALPHA)

		if(len(Teams) > 0):
			number = str(Teams[OwnTeam]["energy"])
			numbercoords = [10, 5]
			displaytext(hudinfo, number, numbercoords)

		screen.blit(HUD, (0,ScreenSize[1]-80))
		screen.blit(hudinfo, (0,ScreenSize[1]-80))

		pygame.display.flip()

		if(OutgoingMessage):
			OutgoingMessage = json.dumps(OutgoingMessage)
			asyncio.run(Websocket.send(OutgoingMessage))
		for i in range(len(Incoming)):
			info = Incoming.pop(0)
			if(info["type"] == "building map delta"):
				for tile in info["info"]:
					BuildingMap[tile[0][1]][tile[0][0]] = tile[1]
			elif(info["type"] == "misc"):
				FlyingBuildings = info["flying buildings"]
				Teams = info["teams"]
			elif(info["type"] == "sync"):
				BuildingMap = info["building map"]
			elif(info["type"] == "terrain map"):
				TerrainMap = info["map"]
			elif(info["type"] == "terrain colors"):
				TerrainColors = info["colors"]
			elif(info["type"] == "settings"):
				Settings = info["settings"]
			elif(info["type"] == "building info"):
				BuildingInfo = info["info"]
				LoadPictures()
			elif(info["type"] == "team"):
				OwnTeam = info["team"]
			else:
				print(info)

GameThread = None
GameThread = threading.Thread(group=None, target=MainLoop, name="GameThread")
GameThread.start()
asyncio.get_event_loop().run_until_complete(Reciever())
