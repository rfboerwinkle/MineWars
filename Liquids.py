import numpy as np
from Galactic import *

class Liquids:
	SCALE = 2**8 # the granularity difference between the official and individual team liquid maps
	KERNEL = np.array((0.1,0.8,0.1)) # convolved with the liquid maps to make them flow

	def npAddScalar(array, coords, value):
		curValue = array[coords]
		value += curValue
		info = np.iinfo(array.dtype)
		if value > info.max:
			value = info.max
		elif value < info.min:
			value = info.min
		array[coords] = value

	def npAddArray(base, addition): # modifies base
		base += addition
		base[base < addition] = np.iinfo(base.dtype).max

	def npSubArray(base, subtraction): # modifies base
		base -= subtraction
		info = np.iinfo(base.dtype)
		base[info.max - base < subtraction] = info.min

	def __init__(self, parent):
		self.parent = parent
		self.heights = np.zeros(parent.shape, dtype=np.uint8)
		self.teams = np.zeros(parent.shape, dtype=np.uint8)
		self.feralHeights = np.zeros(parent.shape, dtype=np.uint16)
		self.deltas = []

	def getDeltas(self):
		deltas = self.deltas
		self.deltas = []
		return deltas

	def add(self, teamID, amount, x, y):
		Liquids.npAddScalar(self.parent.teams[teamID-1]["liquid map"], (y,x), amount*Liquids.SCALE)

	def sub(self, amount, x, y):
		Liquids.npAddScalar(self.parent.teams[self.teams[y,x]-1]["liquid map"], (y,x), -amount*Liquids.SCALE)

	def flow(self):
		for team in self.parent.teams:
			team["liquid map"] = np.apply_along_axis(lambda x: np.convolve(x, Liquids.KERNEL, mode='same'), 0, team["liquid map"])
			team["liquid map"] = np.apply_along_axis(lambda x: np.convolve(x, Liquids.KERNEL, mode='same'), 1, team["liquid map"])
			team["liquid map"] = np.uint16(team["liquid map"])
		self.feralHeights = np.apply_along_axis(lambda x: np.convolve(x, Liquids.KERNEL, mode='same'), 0, self.feralHeights)
		self.feralHeights = np.apply_along_axis(lambda x: np.convolve(x, Liquids.KERNEL, mode='same'), 1, self.feralHeights)
		self.feralHeights = np.uint16(self.feralHeights)

	def merge(self):
		oldHeights = np.copy(self.heights)
		oldTeams = np.copy(self.teams)

		liquidSum = np.zeros(self.parent.shape, dtype=np.uint32)
		for team in self.parent.teams:
			Liquids.npAddArray(liquidSum, team["liquid map"])
		Liquids.npAddArray(liquidSum, self.feralHeights)

		for i,team in enumerate(self.parent.teams):
			Liquids.npSubArray(team["liquid map"], liquidSum - team["liquid map"])
			mask = team["liquid map"] > 0
			self.heights[mask] = (team["liquid map"]//Liquids.SCALE)[mask]
			self.teams[mask] = i+1
			npSave(str(i+1)+"liquidMap", team["liquid map"]) # testing reasons
		Liquids.npSubArray(self.feralHeights, liquidSum - self.feralHeights)
		mask = self.feralHeights > 0
		self.heights[mask] = (self.feralHeights//Liquids.SCALE)[mask]
		self.teams[mask] = 0

		rawDeltas = np.where((oldHeights != self.heights) + (oldTeams != self.teams))
		self.deltas = zip(rawDeltas[1], rawDeltas[0])
