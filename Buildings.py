from Galactic import *
import math

class Buildings:
	CONNECTION_CIRCLE = Circle(CONNECTION_RANGE*2+1, donut=True)#TODO even- and odd- sided versions

	def __init__(self, parent):
		self.parent = parent
		print(parent.shape)
		self.data = [[False for x in range(parent.shape[1])] for y in range(parent.shape[0])]
		self.flying = []
		self.deltas = []

	def getDeltas(self):
		deltas = self.deltas
		self.deltas = []
		return deltas

	def query(self, coords):
		if self.data[coords[1]][coords[0]]:
			if self.data[coords[1]][coords[0]]["type"] == "coords":
				coords = self.data[coords[1]][coords[0]]["coords"]
		return (self.data[coords[1]][coords[0]], coords)

	def place(self, building, coords):
		shape = BuildingInfo[building["type"]]["shape"]

		for y in range(shape[1]):
			for x in range(shape[0]):
				checkcoords = (coords[0] + x, coords[1] + y)
				if x == 0 and y == 0:
					self.data[checkcoords[1]][checkcoords[0]] = building
				else:
					self.data[checkcoords[1]][checkcoords[0]] = {"type":"coords", "coords":coords}
				self.deltas.append(checkcoords)

		connectionTiles = np.where(Buildings.CONNECTION_CIRCLE)#make connections
		rawy = connectionTiles[0] - Buildings.CONNECTION_CIRCLE.shape[0]//2
		rawx = connectionTiles[1] - Buildings.CONNECTION_CIRCLE.shape[1]//2
		for rawtile in zip(rawx, rawy):
			tile = (rawtile[0]+coords[0], rawtile[1]+coords[1])
			if not self.parent.checkEdges(tile):
				continue
			otherBuilding = self.data[tile[1]][tile[0]]
			if otherBuilding:
				if otherBuilding["type"] == "coords":
					tile = otherBuilding["coords"]
					otherBuilding = self.data[tile[1]][tile[0]]
				if otherBuilding["teamID"] == building["teamID"]:
					if tile in building["connections"] or tile == coords:
						continue
					otherBuilding["connections"].append(coords)#TODO consider putting coords in the delta, unsure of the reprecussions
					self.deltas.append(tile)
					building["connections"].append(tile)

	def removeConnections(self, coords):
		building, coords = self.query(coords)
		for i in range(len(building["connections"])):
			connection = building["connections"].pop(0)
			self.data[connection[1]][connection[0]]["connections"].remove(coords)
			self.deltas.append(connection)

	def translate(self, startcoords, endcoords):
		building, startcoords = self.query(startcoords)

		vector = math.atan2(endcoords[1]-startcoords[1], endcoords[0]-startcoords[0])
		vector = [math.cos(vector), math.sin(vector)]
		if abs(vector[0]) < .00000001: # to prevent instant moving
			vector[0] = 0
		if abs(vector[1]) < .00000001: # to prevent instant moving
			vector[1] = 0
		self.flying.append([building, vector, startcoords, endcoords])
		self.raze(startcoords, serious = False)
		self.parent.census(building["teamID"])

	def land(self, flyingbuilding):
		building = flyingbuilding[0]
		building["coords"] = flyingbuilding[3]
		if building["type"] == "base":
			self.parent.teams[building["teamID"]-1]["base coords"] = (building["coords"][0], building["coords"][1])
		self.place(building, flyingbuilding[3])
		self.parent.census(building["teamID"])
		self.flying.remove(flyingbuilding)

	def raze(self, coords, serious=True): # serious means was killed (if it is a base, remove the team)
		building = self.data[coords[1]][coords[0]]

		teamID = building["teamID"]
		self.removeConnections(coords)

		if serious:
			if building["type"] == "base":
				if building["teamID"] > 0:
					self.parent.removeTeam(building["teamID"])

		shape = BuildingInfo[building["type"]]["shape"]
		for y in range(shape[1]):
			for x in range(shape[0]):
				checkCoords = (coords[0] + x, coords[1] + y)
				self.data[checkCoords[1]][checkCoords[0]] = False
				self.deltas.append(checkCoords)

		if building["teamID"] == 0:
			return
		if building["type"] == "collector":
			self.parent.soylent.update()

		self.parent.census(teamID)

	def fly(self):
		for building in self.flying:
			building[2] = [building[2][0] + building[1][0], building[2][1] + building[1][1]]
			if building[1][0] > 0:
				if building[2][0] >= building[3][0]:
					self.land(building)
			elif building[1][0] < 0:
				if building[2][0] <= building[3][0]:
					self.land(building)
			else:
				if building[1][1] > 0:
					if building[2][1] >= building[3][1]:
						self.land(building)
				else:
					if building[2][1] <= building[3][1]:
						self.land(building)
