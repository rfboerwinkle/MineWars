from Galactic import *

class Soylent:
	def __init__(self, parent):
		self.parent = parent
		self.teams = np.zeros(parent.shape, dtype=np.uint8)
		self.deltas = []

	def getDeltas(self):
		deltas = self.deltas
		self.deltas = []
		return deltas

	def update(self, sendDeltas=True):
		print("updating soylent")
		collectors = []#(coords, teamID)
		offset = BuildingInfo["collector"]["shape"]
		offset = (offset[0]/2, offset[1]/2)
		for y in range(self.parent.shape[0]):
			for x in range(self.parent.shape[1]):
				building = self.parent.buildings.data[y][x]
				if building:
					if building["type"] == "collector" and building["completion"] == 0 and building["connected"]:
						if building["connected"]:
							collectors.append(((x+offset[0],y+offset[1]), building["teamID"]))

		newTeams = np.zeros(self.parent.shape, dtype=np.uint8)
		distances = np.zeros(self.parent.shape, dtype=np.uint)+(SOYLENT_RANGE+1)
		currentDistance = np.zeros(self.parent.shape, dtype=np.uint)
		y,x = np.mgrid[:self.parent.shape[0], :self.parent.shape[1]]
		for collector in collectors:
			currentDistance = np.hypot(x-collector[0][0], y-collector[0][1])
			replaceMask = currentDistance < distances
			newTeams[replaceMask] = collector[1]
			distances[replaceMask] = currentDistance[replaceMask]

		if sendDeltas:
			differences = np.where(self.teams != newTeams)
			self.deltas = self.deltas + list(zip(differences[1], differences[0]))
		self.teams = newTeams

		for teamID in range(1,len(self.parent.teams)+1):
			self.parent.teams[teamID-1]["soylent"] = np.sum(self.teams == teamID)
