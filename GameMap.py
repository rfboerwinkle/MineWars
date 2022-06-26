from Terrain import *
from Buildings import *
from Liquids import *
from Soylent import *
from cv2 import imread
import math
import json

class GameMap:
	def __init__(self, mapName=None, teams=None):
		self.teams = teams
		if mapName == None:
			return

		f = open("Maps/"+mapName+"/Info.txt", "r")
		maplist = f.read().splitlines() # originally, and maybe in the future, there was other data here
		rawColors = json.loads(maplist[0])

		rawHeights = np.int32(imread("Maps/"+mapName+"/TerrainMap.png"))
		rawHeights = (rawHeights[:,:,0]<<16)+(rawHeights[:,:,1]<<8)+rawHeights[:,:,2] # this
		colors = np.int32(rawColors)
		colors = (colors[:,2]<<16)+(colors[:,1]<<8)+colors[:,0] # and this are different, because cv2 reads in BGR colorspace
		sorter = colors.argsort()
		heights = np.uint8(sorter[np.searchsorted(colors, rawHeights, sorter=sorter)])
		self.shape = heights.shape
		self.terrain = Terrain(self, heights, rawColors)

		self.buildings = Buildings(self)
		self.liquids = Liquids(self)
		self.soylent = Soylent(self)

	def checkEdges(self, coords):
		if coords[0]<0 or coords[1]<0 or coords[0] >= self.shape[1] or coords[1] >= self.shape[0]:
			return False
		else:
			return True

	def checkPlace(self, shape, coords):
		if not self.checkEdges(coords):
			return False

		baseElevation = self.terrain.heights[coords[1], coords[0]]
		for y in range(shape[1]):
			for x in range(shape[0]):
				checkcoords = (coords[0] + x, coords[1] + y)
				if not self.checkEdges(checkcoords):
					return False
				if self.terrain.heights[checkcoords[1], checkcoords[0]] != baseElevation:
					return False
				if self.buildings.data[checkcoords[1]][checkcoords[0]]:
					return False

		return True

	def census(self, teamID):#try not to use
		basecoords = self.teams[teamID-1]["base coords"]
		if not self.buildings.data[basecoords[1]][basecoords[0]]:
			print(f"Team number {teamID} is dead! (or we just can't find the base for some reason...)")
			return

		for row in self.buildings.data:
			for building in row:
				if building:
					if building["type"] == "collector" and building["teamID"] == teamID:
						building["connected"] = False

		self.teams[teamID-1]["energy needs"] = []

		searched = [] # just coords
		toSearch = [[basecoords, 0, [basecoords]]] # [coords, total distance(no sqrt), path from base]

		while len(toSearch): # do i really need this "len"
			toSearch.sort(key = lambda x:x[1])
			searching = toSearch.pop(0)
			searched.append(searching[0])
			building = self.buildings.data[searching[0][1]][searching[0][0]]

			if building["completion"] != 0 or BuildingInfo[building["type"]]["ammo"]:
				self.teams[teamID-1]["energy needs"].append(searching[2][-1])
				continue

			if building["type"] == "collector":
				building["connected"] = True

			for connectedCoords in building["connections"]:
				found = False
				for coords in searched:
					if coords == connectedCoords:
						found = True
						break
				if found:
					continue
				distance = searching[1] + math.sqrt((searching[0][0] - connectedCoords[0])**2 + (searching[0][1] - connectedCoords[1])**2)
				for i,info in enumerate(toSearch):
					if info[0] == connectedCoords:
						if info[1] > distance:
							toSearch.pop(i)
						else:
							found = True
						break
				if found:
					continue

				toSearch.append([connectedCoords, distance, searching[2] + [connectedCoords]])

		self.soylent.update()

	def removeTeam(teamID): # remember to remove: buildings.baseCoords, liquids.teamHeights, soylent.teamSums
		for y in range(self.shape[0]):
			for x in range(self.shape[1]):
				building = self.buildings.data[y][x]
				if building:
					if building["type"] == "coords":
						continue
					if building["teamID"] == teamID:
						building["teamID"] = 0
						if building["type"] == "collector":
							building["connected"] = False
						self.buildings.removeConnections((x,y))
					elif building["teamID"] > teamID:
						building["teamID"] -= 1

		self.soylent.update(sendDeltas=False)
		self.liquids.teams[self.liquids.teams == teamID] = 0
		self.liquids.teams[self.liquids.teams > teamID] -= 1
