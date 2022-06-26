# syntax:
#
# Settings = {"flow rate":0.2}
# Teams = []; each "team" is a dictionary (see "Server.MakeNew"), "teamID" is the identification (1 indexed) of the "team" within "Teams".  This is so something without a team can have a "teamID" of 0
#	team["status"] =  "w":waiting to place a base, "a":alive
# TerrainColors = [(color in RGB)]; each index is a terrain height
# TerrainMap = np.uint8; 2D; height
# SoylentMap = np.uint8; 2D; teamID
# BuildingMap = [[building (see Server.MakeNew) | {"type":"coords", "coords":coords to building's info} | False]]
# LiquidMapHeight = np.uint8; 2D; height
# LiquidMapTeam = np.uint8; 2D; teamID
# These compose the official liquid map that is sent to clients and used in most calculations. For flow computing reasons, a more granular (np.uint16) map exists in each team. See Server.LiquidFlow() for more info
# Lazers = [((start coords), (end coords))]
# FlyingBuildings = [(building, vector, currentcoords, endcoords)]; starting coords are in Building["coords"]

import numpy as np

BLASTER_RANGE = 30
SOYLENT_RANGE = 12 # can't be more than 255, see "Server.UpdateSoylent"
CONNECTION_RANGE = 15

BuildingInfo = {
	"base":{"movable":True, "ammo":None, "cooldown":False, "shape":(3,3)},
	"collector":{"movable":False, "ammo":None, "cooldown":False, "shape":(2,2)},
	"blaster":{"movable":True, "ammo":10, "cooldown":30, "shape":(2,2)},
	"emitter":{"movable":True, "ammo":10, "cooldown":20, "shape":(2,2)},
	"relay":{"movable":False, "ammo":None, "cooldown":False, "shape":(2,2)}
}

def Circle(d, donut=False, donutSideLength=1): # returns numpy array with inscribed circle of "True"s, optional square donut hole
	output = np.zeros((d,d), dtype=np.bool_)
	r = d/2 - 0.5
	y,x = np.mgrid[:d,:d]
	output[(x-r)**2 + (y-r)**2 <= r**2] = True
	if donut:
		output[(np.absolute(y-r) < donutSideLength) * (np.absolute(x-r) < donutSideLength)] = False
	return output

def LineOfSight(x0, y0, x1, y1):
	coords = []
	dx =  abs(x1-x0)
	if x0 < x1:
		sx = 1
	else:
		sx = -1
	dy = -abs(y1-y0)
	if y0 < y1:
		sy = 1
	else:
		sy = -1
	err = dx+dy
	while True:
		coords.append((x0, y0))
		if x0 == x1 and y0 == y1:
			break
		e2 = 2*err
		if e2 >= dy:
			err += dy
			x0 += sx
		if e2 <= dx:
			err += dx
			y0 += sy
	return coords

def GoodPrint(toprint, squarefunction = False):
	for line in toprint:
		for square in line:
			if square == False:
				square = "F"
			elif square == True:
				square = "T"
			if squarefunction:
				square = squarefunction(square)
			print(square, end=",")
		print()

def npSave(name, array):
	f = open(name, "w")
	f.write(f"{array.dtype}\n")
	if array.dtype == np.uint8:
		np.savetxt(f, array, fmt="%2x")
	elif array.dtype == np.uint16:
		np.savetxt(f, array, fmt="%4x")
	elif array.dtype == np.uint32:
		np.savetxt(f, array, fmt="%8x")
	elif array.dtype == np.int32:
		np.savetxt(f, array, fmt="%8x")
	elif array.dtype == np.int64:
		np.savetxt(f, array, fmt="%16x")
	else:
		f.write("idk how to handle this type")
	f.close()
