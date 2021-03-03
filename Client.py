import asyncio
import json
import websockets
import threading
import time
import pygame
pygame.init()
import pygame.gfxdraw

Ip = input("IP of server: ")
if(Ip == ""):
	Ip = "localhost"
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

def MainLoop():
	global Incoming
	global Websocket
	global Retry
	global Close

	Color = input("color in json [r,g,b]: ")
	if(Color == ""):
		Color = [255,0,0]
	else:
		Color = json.loads(Color)

	ScreenSize = (600, 600)
	Screen = pygame.display.set_mode(ScreenSize)
	while not pygame.display.get_active():
		time.sleep(0.1)
	pygame.display.set_caption("Mine Wars","Mine Wars")

	def SwapColors(surface, endcolor, startcolor = (0,0,0,255)):#does the copying, no worry
		x, y = surface.get_size()
		newsurface = surface.copy()
		for pixelx in range(x):
			for pixely in range(y):
				if(newsurface.get_at((pixelx, pixely)) == startcolor):
					newsurface.set_at((pixelx, pixely), endcolor)
		return newsurface

	Letters = {"0":["0"], "1":["1"], "2":["2"], "3":["3"], "4":["4"], "5":["5"], "6":["6"], "7":["7"], "8":["8"], "9":["9"]}#[black, red, green, blue]

	for letter in Letters:
		Letters[letter][0] = pygame.image.load("Pictures/Letters/"+letter+".png")
		Letters[letter].append(SwapColors(Letters[letter][0], (255,0,0,255)))
		Letters[letter].append(SwapColors(Letters[letter][0], (0,255,0,255)))
		Letters[letter].append(SwapColors(Letters[letter][0], (0,0,255,255)))

	HUDTile = pygame.image.load("Pictures/HUDTile.png")
	NonDecorativeHeight = 75

	Teams = {}
	OwnTeam = 0

	TerrainColors = []
	TerrainMap = [] #[height, is a mine?]
	BuildingMap = []
	SoylentMap = []#[team otherwise False]
	FlyingBuildings = []
	Lasers = []
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

	def CheckEdges(coords):
		if(coords[0]<0 or coords[1]<0 or coords[0] >= len(TerrainMap[0]) or coords[1] >= len(TerrainMap)):
			return False
		else:
			return True

	def DisplayText(destination, text, coords, colorindex = 0):
		for i in range(len(text)):
			destination.blit(Letters[text[i]][colorindex], coords)
			coords[0] += Letters[text[i]][colorindex].get_width()

	def ToDisplayCoords(coords, center = False):
		if(center):
			return [round(((coords[0]+.5)*SquareLength) + ViewCoords[0]), round(((coords[1]+.5)*SquareLength) + ViewCoords[1])]
		else:
			return [round((coords[0]*SquareLength) + ViewCoords[0]), round((coords[1]*SquareLength) + ViewCoords[1])]

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

	while not Close:
		WaitFramerate(1/60)
		OutgoingMessage = False
		events = pygame.event.get()
		keys = pygame.key.get_pressed()
		if not(Websocket):
			for event in events:
				if(event.type == pygame.QUIT):
					Close = True
			continue

		for event in events:
			if(event.type == pygame.QUIT):
				Close = True
			elif(event.type == pygame.MOUSEBUTTONDOWN):
				clickedcoords = [(event.pos[0] - ViewCoords[0])//SquareLength, (event.pos[1] - ViewCoords[1])//SquareLength]
				if(Teams[OwnTeam]["status"] == "w"):
					OutgoingMessage = {"type":"land", "coords":clickedcoords, "color":Color}
					continue
				if(Action == "T"):
					if(ActionSequence == 0):
						SelectedCoords = clickedcoords
						if(CheckEdges(SelectedCoords)):
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
					if(CheckEdges(SelectedCoords)):
						if not(BuildingMap[SelectedCoords[1]][SelectedCoords[0]]):
							OutgoingMessage = {"type":"erect", "building":ToBuild, "coords":SelectedCoords}
					SelectedCoords = False
				elif(Action == "R"):
					SelectedCoords = clickedcoords
					if(CheckEdges(SelectedCoords)):
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
		if(keys[pygame.K_1]):#1
			ToBuild = "relay"
		if(keys[pygame.K_2]):#2
			ToBuild = "collector"
		if(keys[pygame.K_3]):#3
			ToBuild = "blaster"

		Screen.fill([100,100,200])#start of display

		for row in range(len(TerrainMap)):#display terrain
			for square in range(len(TerrainMap[row])):
				color = TerrainColors[TerrainMap[row][square][0]]
				x, y = ToDisplayCoords((square, row))
				pygame.gfxdraw.box(Screen, [x, y, SquareLength, SquareLength], color)
				if(TerrainMap[row][square][1]):
					x, y = ToDisplayCoords((square, row), center = True)
					pygame.gfxdraw.filled_circle(Screen, x, y, Center, [221, 158, 30])

		for row in range(len(SoylentMap)):#display soylent
			for square in range(len(SoylentMap[row])):
				if(SoylentMap[row][square]):
					teamfull = Teams[SoylentMap[row][square]]
					color = [teamfull["color"][0], teamfull["color"][1], teamfull["color"][2], 80]
					x, y = ToDisplayCoords((square, row))
					pygame.gfxdraw.box(Screen, [x, y, SquareLength, SquareLength], color)

		for row in range(len(BuildingMap)):#display connections
			for square in range(len(BuildingMap[row])):
				if(BuildingMap[row][square]):
					for connection in BuildingMap[row][square]["connections"]:
						pygame.draw.line(Screen, (0,0,0), ToDisplayCoords((square, row), center = True), ToDisplayCoords(connection, center = True))

		for row in range(len(BuildingMap)):#display buildings
			for square in range(len(BuildingMap[row])):
				if(BuildingMap[row][square]):
					building = BuildingMap[row][square]
					x, y = ToDisplayCoords((square,row), center = True)
					pygame.gfxdraw.filled_circle(Screen, x, y, BuildingRadius, Teams[building["team"]]["color"])
					Screen.blit(BuildingInfo[building["type"]]["image"], ToDisplayCoords((square,row)))
					if(building["completion"] != 0):
						DisplayText(Screen, str(building["completion"]), ToDisplayCoords((square,row)), colorindex = 2)
					else:
						DisplayText(Screen, str(building["health"]), ToDisplayCoords((square,row)), colorindex = 1)
					if(BuildingInfo[building["type"]]["ammo"]):
						x, y = ToDisplayCoords((square,row+1))
						DisplayText(Screen, str(building["ammo"]), [x, y-5], colorindex = 3)#Y offset value should be minus number height

		for laser in Lasers:#display lasers
			pygame.draw.line(Screen, (0,0,255), ToDisplayCoords(laser[0], center = True), ToDisplayCoords(laser[1], center = True), width = 3)

		for building in FlyingBuildings:#display flying buildings
			pygame.gfxdraw.filled_circle(Screen, round((building[1][0]*SquareLength)+Center + ViewCoords[0]), round((building[1][1]*SquareLength)+Center + ViewCoords[1]), BuildingRadius, Teams[building[0]["team"]]["color"])
			Screen.blit(BuildingInfo[building[0]["type"]]["image"], (round((building[1][0]*SquareLength) + ViewCoords[0]), round((building[1][1]*SquareLength) + ViewCoords[1])))

		if(SelectedCoords):#display selection
			pygame.gfxdraw.rectangle(Screen, [SelectedCoords[0]*SquareLength + ViewCoords[0], SelectedCoords[1]*SquareLength + ViewCoords[1], SquareLength, SquareLength], Teams[OwnTeam]["color"])

		hudinfo = pygame.Surface((HUD.get_width(), HUD.get_height()), flags = pygame.SRCALPHA)

		if(len(Teams) > 0):
			number = str(Teams[OwnTeam]["energy"])
			numbercoords = [10, 5]
			DisplayText(hudinfo, number, numbercoords)

		Screen.blit(HUD, (0,ScreenSize[1]-80))
		Screen.blit(hudinfo, (0,ScreenSize[1]-80))

		pygame.display.flip()

		if(OutgoingMessage):
			OutgoingMessage = json.dumps(OutgoingMessage)
			asyncio.run(Websocket.send(OutgoingMessage))
		for i in range(len(Incoming)):
			info = Incoming.pop(0)
			if(info["type"] == "deltas"):
				for tile in info["building map"]:
					BuildingMap[tile[0][1]][tile[0][0]] = tile[1]
				for tile in info["soylent map"]:
					SoylentMap[tile[0][1]][tile[0][0]] = tile[1]
			elif(info["type"] == "misc"):
				FlyingBuildings = info["flying buildings"]
				Teams = info["teams"]
				Lasers = info["lasers"]
			elif(info["type"] == "sync"):
				BuildingMap = info["building map"]
				TerrainMap = info["terrain map"]
				SoylentMap = info["soylent map"]
				TerrainColors = info["terrain colors"]
				BuildingInfo = info["building info"]
				LoadPictures()
				OwnTeam = info["own team"]
			else:
				print(info)
	pygame.quit()

GameThread = None
GameThread = threading.Thread(group=None, target=MainLoop, name="GameThread")
GameThread.start()
asyncio.get_event_loop().run_until_complete(Reciever())
print("Closed!")
