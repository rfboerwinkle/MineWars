import asyncio # TODO complete the conversion of teams to a list
import websockets
import threading
import json
import time
import os
import io
import sys
import pygame
pygame.init()
import pygame.gfxdraw
import numpy as np

from Galactic import *

if len(sys.argv) > 1:
	Ip = sys.argv[1]
else:
	Ip = input("IP of server: ")

if len(sys.argv) > 2:
	Name = sys.argv[2]
else:
	Name = input("name: ")

if len(sys.argv) > 3:
	Color = sys.argv[3]
else:
	Color = input("color in json [r,g,b]: ")
Color = json.loads(Color)

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
	uri = "ws://" + Ip + ":2000" # Who is 'uri'?
	Websocket = await websockets.connect(uri)
	while True:
		info = await Websocket.recv()
		Incoming.append(json.loads(info))
		if Close:
			print("Closing Reciever")
			await Websocket.close()
			break

def MainLoop():
	global Incoming
	global Websocket
	global Retry
	global Close
	global Color
	global Name

	OutgoingMessage = {"type":"setup", "color":Color, "name":Name}

	ScreenSize = (600, 600)
	Screen = pygame.display.set_mode(ScreenSize)
	while not pygame.display.get_active():
		time.sleep(0.1)
	pygame.display.set_caption("Mine Wars")

	def SwapColors(surface, endcolor, startcolor=(0,0,0,255)): # does the copying, no worry
		x, y = surface.get_size()
		newsurface = surface.copy()
		for pixelx in range(x): # TODO use numpy, maybe?
			for pixely in range(y):
				if newsurface.get_at((pixelx, pixely)) == startcolor:
					newsurface.set_at((pixelx, pixely), endcolor)
		return newsurface

	LETTERS = {} # "char":[black, red, green, blue]

	for name in os.listdir("Pictures/Letters/other"):
		LETTERS[name[:-4]] = ["other"]
	for name in os.listdir("Pictures/Letters/lower"):
		LETTERS[name[:-4]] = ["lower"]
	for name in os.listdir("Pictures/Letters/upper"):
		LETTERS[name[:-4].upper()] = ["upper"]

	for letter in LETTERS:
		if LETTERS[letter][0] == "upper":
			filename = letter.lower()
		else:
			filename = letter
		LETTERS[letter][0] = pygame.image.load("Pictures/Letters/"+LETTERS[letter][0]+"/"+filename+".png")
		LETTERS[letter].append(SwapColors(LETTERS[letter][0], (255,0,0,255)))
		LETTERS[letter].append(SwapColors(LETTERS[letter][0], (0,255,0,255)))
		LETTERS[letter].append(SwapColors(LETTERS[letter][0], (0,0,255,255)))

	LetterHeight = LETTERS["0"][0].get_height()

	BUILDING_PICTURES = {} # "building":pygame.Surface of the building

	for building in BuildingInfo:
		BUILDING_PICTURES[building] = pygame.image.load("Pictures/Buildings/" + building + ".png")

	Synced = False # makes sure everything has been initialized before it tries to display stuff
	Prompt = False # for typing

	Teams = []
	OwnTeamID = 0
	FeralColor = [130, 100, 50]

	TerrainColors = []
	TerrainMap = []
	SoylentMap = []
	BuildingMap = []
	LiquidMapHeight = np.zeros((1,1), np.uint8)
	LiquidMapTeam = np.zeros((1,1), np.uint8)
	Lasers = []
	FlyingBuildings = []

	SquareLength = 11 # constant right now, haven't changed name because TODO zooming

	MouseCoords = [0,0]
	SelectedCoords = False
	ActionSequence = 0
	ViewCoords = [0,0]
	Action = "T" # "E":erect, "R":raze, "T":translate
	ToBuild = "collector"

# misc functions

	def LoadArray(array, dtype=np.uint8):
		f = io.StringIO()
		f.write(array)
		f.seek(0)
		loaded = np.loadtxt(f, dtype=dtype)
		print(loaded)
		return loaded

	def CheckEdges(coords):
		if coords[0]<0 or coords[1]<0 or coords[0] >= TerrainMap.shape[1] or coords[1] >= TerrainMap.shape[0]:
			return False
		else:
			return True

	def ToDisplayCoords(coords, shape=None): # if shape is provided, centers
		if shape:
			return [round((coords[0]+(shape[0] / 2))*SquareLength + ViewCoords[0]), round((coords[1]+(shape[1] / 2)) * SquareLength + ViewCoords[1])]
		else:
			return [round(coords[0]*SquareLength + ViewCoords[0]), round(coords[1]*SquareLength + ViewCoords[1])]

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

	def QueryBuilding(coords):
		if BuildingMap[coords[1]][coords[0]]:
			if BuildingMap[coords[1]][coords[0]]["type"] == "coords":
				coords = BuildingMap[coords[1]][coords[0]]["coords"]
		return (BuildingMap[coords[1]][coords[0]], coords)

# display functions

	def DisplayText(dest, text, coords, colorindex=0):
		for i in range(len(text)):
			dest.blit(LETTERS[text[i]][colorindex], coords)
			coords[0] += LETTERS[text[i]][colorindex].get_width()

	def DisplayBuilding(building, coords, flying=False):
		shape = BuildingInfo[building["type"]]["shape"]
		x, y = ToDisplayCoords(coords, shape = shape)
		if building["teamID"] > 0:
			color = Teams[building["teamID"]-1]["color"]
		else:
			color = FeralColor
		pygame.gfxdraw.filled_circle(Screen, x, y, round(SquareLength*shape[0]*(.3)), color)
		Screen.blit(BUILDING_PICTURES[building["type"]], ToDisplayCoords(coords))
		if not flying:
			displaycoords = ToDisplayCoords(coords)
			if building["completion"] != 0:
				DisplayText(Screen, str(building["completion"]), displaycoords, colorindex = 2)
			else:
				DisplayText(Screen, str(building["health"]), displaycoords, colorindex = 1)
			if BuildingInfo[building["type"]]["ammo"] and building["teamID"] == OwnTeamID:
				displaycoords = ToDisplayCoords((coords[0], coords[1]+shape[1]))
				displaycoords[1] -= LetterHeight
				DisplayText(Screen, str(building["ammo"]), displaycoords, colorindex = 3)

	TerrainImage = pygame.Surface((0,0))
	def UpdateTerrainImage():
		nonlocal TerrainImage
		TerrainImage = pygame.Surface((TerrainMap.shape[1]*SquareLength, TerrainMap.shape[0]*SquareLength))
		for row in range(TerrainMap.shape[0]):
			y = row*SquareLength
			for square in range(TerrainMap.shape[1]):
				x = square*SquareLength
				color = TerrainColors[TerrainMap[row, square]]
				pygame.gfxdraw.box(TerrainImage, [x, y, SquareLength, SquareLength], color)
#				if TerrainMap[row, square][1]: # this is for if you want to draw mines
#					pygame.gfxdraw.filled_circle(TerrainImage, x+(SquareLength//2), y+(SquareLength//2), SquareLength//2, [221, 158, 30])

	SoylentImage = pygame.Surface((0,0), flags=pygame.SRCALPHA)
	def UpdateSoylentImage():
		nonlocal SoylentImage
		SoylentImage = pygame.Surface((len(SoylentMap[0])*SquareLength, len(SoylentMap)*SquareLength), flags=pygame.SRCALPHA)
		for row in range(len(SoylentMap)):
			y = row*SquareLength
			for square in range(len(SoylentMap[row])):
				if SoylentMap[row][square]:
					x = square*SquareLength
					teamfull = Teams[SoylentMap[row][square]-1]
					color = teamfull["color"] + [100]
					pygame.gfxdraw.box(SoylentImage, (x, y, SquareLength, SquareLength), color)

	def DisplayGame():
		coords = ToDisplayCoords((0,0))
		Screen.blit(TerrainImage, coords)
		Screen.blit(SoylentImage, coords)

		for row in range(len(BuildingMap)): # display connections
			for square in range(len(BuildingMap[row])):
				if BuildingMap[row][square]:
					building = BuildingMap[row][square]
					if building["type"] == "coords":
						continue
					for connection in building["connections"]:
						startshape = BuildingInfo[building["type"]]["shape"]
						endshape = BuildingInfo[BuildingMap[connection[1]][connection[0]]["type"]]["shape"]
						pygame.draw.line(Screen, (0,0,0), ToDisplayCoords((square, row), shape=startshape), ToDisplayCoords(connection, shape=endshape))

		for row in range(len(BuildingMap)): # display buildings
			for square in range(len(BuildingMap[row])):
				if BuildingMap[row][square]:
					if BuildingMap[row][square]["type"] == "coords":
						continue
					building = QueryBuilding((square,row))[0]
					DisplayBuilding(building, (square, row))

		for row in range(LiquidMapTeam.shape[0]): # display liquid
			for square in range(LiquidMapTeam.shape[1]):
				if LiquidMapHeight[row,square]:
					if LiquidMapTeam[row,square] != 0:
						color = Teams[LiquidMapTeam[row,square]-1]["color"]
					else:
						color = FeralColor
					alpha = LiquidMapHeight[row,square]*20
					if alpha > 200:
						alpha = 200
					pygame.gfxdraw.box(Screen, (square*SquareLength, row*SquareLength, SquareLength, SquareLength), (color[0],color[1],color[2],alpha))

		for laser in Lasers: # display lasers
			pygame.draw.line(Screen, (0,0,255), ToDisplayCoords(laser[0]), ToDisplayCoords(laser[1]), 3)

		for building in FlyingBuildings: # display flying buildings
			DisplayBuilding(building[0], building[1], flying = True)

		if Action == "E": # display building preview
			DisplayBuilding({"type":ToBuild, "teamID":OwnTeamID}, MouseCoords, flying = True)
		if Action == "T" and ActionSequence == 1:
			if QueryBuilding(SelectedCoords):
				DisplayBuilding({"type":QueryBuilding(SelectedCoords)[0]["type"], "teamID":OwnTeamID}, MouseCoords, flying = True)
		if Teams[OwnTeamID-1]["status"] == "w":
			DisplayBuilding({"type":"base", "teamID":OwnTeamID}, MouseCoords, flying = True)

		if SelectedCoords: # display selection
			info = QueryBuilding(SelectedCoords)
			startcoords = ToDisplayCoords(info[1])
			shape = BuildingInfo[info[0]["type"]]["shape"]
			pygame.gfxdraw.rectangle(Screen, [startcoords[0], startcoords[1], shape[0] * SquareLength, shape[1] * SquareLength], Teams[OwnTeamID-1]["color"])

	HUD_BACKGROUND = pygame.Surface((ScreenSize[0], ScreenSize[1]), pygame.SRCALPHA)
	HUD_BACKGROUND.fill((221, 158, 30, 230))
	pygame.draw.rect(HUD_BACKGROUND, (221, 142, 30), (0, 0, ScreenSize[0], 5))
	def DisplayHUD():
		if Prompt:
			y = round(ScreenSize[1]*.6)
		else:
			y = round(ScreenSize[1]*.85)
		Screen.blit(HUD_BACKGROUND, (0,y))
		y += 10

		if Synced:
			number = str(Teams[OwnTeamID-1]["energy"])
			numbercoords = [10, y]
			DisplayText(Screen, number, numbercoords)
			y += LetterHeight

			x = 5
			for color in TerrainColors:
				pygame.gfxdraw.box(Screen, [x, y, SquareLength, SquareLength], color)
				x+= SquareLength
			y += SquareLength

			x = 5
			if CheckEdges(MouseCoords):
				height = LiquidMapHeight[MouseCoords[1],MouseCoords[0]]
				team = LiquidMapTeam[MouseCoords[1],MouseCoords[0]]
				if height:
					if team != 0:
						color = Teams[team - 1]["color"]
					else:
						color = FeralColor
					pygame.gfxdraw.box(Screen, [x, y, SquareLength, SquareLength], color)
					x += SquareLength
					DisplayText(Screen, str(height), [x,y])

	while not Close:
		WaitFramerate(1/60)
		events = pygame.event.get()
		keys = pygame.key.get_pressed()
		if not Websocket:
			for event in events:
				if event.type == pygame.QUIT:
					Close = True
			continue

		for event in events:
			if event.type == pygame.QUIT:
				Close = True
			elif event.type == pygame.MOUSEMOTION:
				MouseCoords = [(event.pos[0] - ViewCoords[0])//SquareLength, (event.pos[1] - ViewCoords[1])//SquareLength]
			elif event.type == pygame.MOUSEBUTTONDOWN:
				clickedcoords = [(event.pos[0] - ViewCoords[0])//SquareLength, (event.pos[1] - ViewCoords[1])//SquareLength]
				if Teams[OwnTeamID-1]["status"] == "w":
					OutgoingMessage = {"type":"land", "coords":clickedcoords}
					continue
				if Action == "T":
					if ActionSequence == 0:
						SelectedCoords = clickedcoords
						if CheckEdges(SelectedCoords):
							building = QueryBuilding(SelectedCoords)[0]
							if building:
								if building["teamID"] == OwnTeamID:
									ActionSequence = 1
								else:
									SelectedCoords = False
							else:
								SelectedCoords = False
						else:
							SelectedCoords = False
					elif ActionSequence == 1:
						newcoords = clickedcoords
						if not BuildingMap[newcoords[1]][newcoords[0]]:
							OutgoingMessage = {"type":"translate", "start":SelectedCoords, "end":newcoords}
						SelectedCoords = False
						ActionSequence = 0
				elif Action == "E":
					SelectedCoords = clickedcoords
					if CheckEdges(SelectedCoords):
						if not BuildingMap[SelectedCoords[1]][SelectedCoords[0]]:
							OutgoingMessage = {"type":"erect", "building":ToBuild, "coords":SelectedCoords}
					SelectedCoords = False
				elif Action == "R":
					SelectedCoords = clickedcoords
					if CheckEdges(SelectedCoords):
						building = QueryBuilding(SelectedCoords)[0]
						if building:
							if building["teamID"] == OwnTeamID:
								OutgoingMessage = {"type":"raze", "coords":SelectedCoords}
					SelectedCoords = False

		if keys[pygame.K_UP] or keys[pygame.K_w]:
			ViewCoords[1] += 3
		if keys[pygame.K_DOWN] or keys[pygame.K_s]:
			ViewCoords[1] -= 3
		if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
			ViewCoords[0] -= 3
		if keys[pygame.K_LEFT] or keys[pygame.K_a]:
			ViewCoords[0] += 3
		if keys[pygame.K_e]:
			Action = "E"
			ActionSequence = 0
			SelectedCoords = False
		if keys[pygame.K_r]:
			Action = "R"
			ActionSequence = 0
			SelectedCoords = False
		if keys[pygame.K_t]:
			Action = "T"
			ActionSequence = 0
			SelectedCoords = False
		if keys[pygame.K_1]:
			ToBuild = "relay"
		if keys[pygame.K_2]:
			ToBuild = "collector"
		if keys[pygame.K_3]:
			ToBuild = "blaster"
		if keys[pygame.K_4]:
			ToBuild = "emitter"
		if keys[pygame.K_BACKQUOTE]:
			Prompt = True
		if keys[pygame.K_ESCAPE]:
			Prompt = False

		Screen.fill([100,100,200]) # start of display

		if Synced:
			DisplayGame()

		DisplayHUD()

		pygame.display.flip()

		if OutgoingMessage:
			OutgoingMessage = json.dumps(OutgoingMessage, separators=(",", ":"))
			print(f"O({len(OutgoingMessage)}): {OutgoingMessage}")
			asyncio.run(Websocket.send(OutgoingMessage))
			OutgoingMessage = False
		for i in range(len(Incoming)):
			info = Incoming.pop(0)
			if info["type"] == "deltas":
				print("I:", info)
				for tile in info["soylent map"]:
					SoylentMap[tile[0][1]][tile[0][0]] = tile[1]
				if len(info["soylent map"]) > 0:
					UpdateSoylentImage()
				for tile in info["building map"]:
					BuildingMap[tile[0][1]][tile[0][0]] = tile[1]
				for tile in info["liquid map"]:
					LiquidMapHeight[tile[0][1], tile[0][0]] = tile[1]
					LiquidMapTeam[tile[0][1], tile[0][0]] = tile[2]
			elif info["type"] == "misc":
				FlyingBuildings = info["flying buildings"]
				Teams = info["teams"]
				Lasers = info["lasers"]
			elif info["type"] == "sync":
				Synced = True
				TerrainColors = info["terrain colors"]
				TerrainMap = LoadArray(info["terrain map"])
				SoylentMap = LoadArray(info["soylent map"])
				BuildingMap = info["building map"]
				LiquidMapHeight = LoadArray(info["liquid map height"])
				LiquidMapTeam = LoadArray(info["liquid map team"])
				Teams = info["teams"]
				OwnTeamID = info["own teamID"]
				UpdateTerrainImage()
				UpdateSoylentImage()
			else:
				print("UFO:", info)
	pygame.quit()
	print("Closing MainLoop")

GameThread = None
GameThread = threading.Thread(group=None, target=MainLoop, name="GameThread")
GameThread.start()
asyncio.get_event_loop().run_until_complete(Reciever())
