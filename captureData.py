import glob
import os
import sys
import carla
import argparse
import math
import random
import time
import logging
import queue
import datetime
import threading

try: 
    sys.path.append(glob.glob('**/carla-*%d.%d-%s.egg' % ( 
    sys.version_info.major, 
    sys.version_info.minor, 
    'win-amd64' if os.name == 'nt' else 'linux-x86_64'))[0]) 
except IndexError: 
    pass

###########################################################
#
# ISENSOR - a class which defines CARLA sensor objects and
# provides an API for attaching to a car and saving images.
#
###########################################################

class iSensor:
    def __init__(self):
        self.x = 0
        self.y = 0
        self.z = 0
        self.yaw = 0
        self.imageQueue = queue.Queue()
        self._type = 'rgb'

    def set_meta_params(self, dirname, path, name):
        self.dirpath = '%s/%s/%s' % (dirname, path,name)
        cwd = os.getcwd()
        path = os.path.join(cwd, self.dirpath)
        if not(os.path.exists(path)):
            os.makedirs(path)
        
    def set_params(self, x, y, z, yaw):
        self.x = x
        self.y = y
        self.z = z
        self.yaw = yaw

    def attach_to_car(self, car, blueprint, world, sensorType):
        camera_transform = carla.Transform(carla.Location(x=self.x, y=self.y, z=self.z), carla.Rotation(yaw=self.yaw))
        if sensorType == 'rgb':
            camera_bp = blueprint.find('sensor.camera.rgb') #default set to rgb
            self._type = 'rgb'
        elif sensorType == 'seg':
            camera_bp = blueprint.find('sensor.camera.semantic_segmentation')
            self._type = 'seg'
        elif sensorType == 'depth':
            camera_bp = blueprint.find('sensor.camera.depth')
            self._type = 'depth'
        self.sensor = world.spawn_actor(camera_bp, camera_transform, attach_to=car)

    def listen(self):
        self.sensor.listen(self.imageQueue.put)

    def saveImage(self,frameNumber):
        image = self.imageQueue.get()
        if self._type == 'seg':
            image.convert(carla.ColorConverter.CityScapesPalette)
        elif self._type == 'depth':
            image.convert(carla.ColorConverter.LogarithmicDepth)
        image.save_to_disk('%s/%06d.png' % (self.dirpath, frameNumber))

    def destroy(self):
        self.sensor.destroy()

###########################################################
#
# SENSOR CREATOR - reads the input .cam file, creates a list
# of sensor objects attached to the egoVehicle.
#
###########################################################

def sensorCreator(filename, car, client, dirname, dirprefix, sensorType):
    world = client.get_world()
    blueprint = world.get_blueprint_library()
    if os.path.isfile(filename) == False:
        print(".cam file specified does not exist. Please check the path.")
        return
    fp = open(filename)
    iSensor_list = []
    linecounter = 0
    for line in fp:
        firstchar = line[0]
        if firstchar != '#': #If the line is not a comment...
            args = line.split(" ")
            if len(args) != 5:
                print("Incorrect number of arguments on line %i of file %s." % (linecounter, filename))
                if int(yaw) < 0 or int(yaw) > 359:
                    print("On line %i, yaw should be in range 0 to 359." % linecounter)
                    return
            else:
                new_sensor = iSensor()
                new_sensor.set_params(float(args[1]), float(args[2]), float(args[3]), int(args[4]))
                new_sensor.set_meta_params(dirname, dirprefix, args[0])
                new_sensor.attach_to_car(car, blueprint, world, sensorType)
                iSensor_list.append(new_sensor)
        linecounter = linecounter + 1
    return iSensor_list

###########################################################
#
# IMAGE SAVER - saves images using multi-threading for 
# all sensors.
#
###########################################################

def imageSaver(sensorList, frameNumber, maxThreads):
    numSensors = len(sensorList)
    numFullThreads = int(numSensors / maxThreads)
    threadRemainder = numSensors % maxThreads
    #Start full threads
    sensorCounter = 0
    if numFullThreads > 0:
        for j in range(0, numFullThreads):
            for i in range(0, maxThreads):
                threads = list()
                thread = threading.Thread(target = sensorList[sensorCounter].saveImage, args=(frameNumber,))
                threads.append(thread)
                sensorCounter = sensorCounter + 1
                thread.start()
            for thread in threads:
                thread.join()
    if threadRemainder > 0:
        for i in range(0, threadRemainder):
            threads = list()
            thread = threading.Thread(target = sensorList[sensorCounter].saveImage, args=(frameNumber,))
            threads.append(thread)
            sensorCounter = sensorCounter + 1
            thread.start()
        for thread in threads:
            thread.join()
    return

##############################################################
#
#   RUN_CONDITION
#
##############################################################

def runCondition(condName, condWeather, condLights, logFile, logFileName, logFrames, sensorFile, sensorDir, sensorType, threadNumber, client):

    dirprefix = '%s/%s' % (logFileName, condName)

    #Turn on synchronous mode
    settings = client.get_world().get_settings()
    settings.synchronous_mode = True
    settings.fixed_delta_seconds = 0.10
    client.get_world().apply_settings(settings)

    #Replay the log file
    client.replay_file(logFile, 0, 0, 0)
    client.get_world().tick()
    actorList = client.get_world().get_actors()

    #Find the hero vehicle and attach the sensors.
    egoVehicle = None
    audiList = actorList.filter('vehicle.audi.tt')
    for actor in audiList:
        if(actor.attributes["role_name"] == 'hero'):
            egoVehicle = actor
            break
    if egoVehicle == None:
        print("Error: Could not find the ego vehicle!")
        return
    sensorList = sensorCreator(sensorFile, egoVehicle, client, sensorDir, dirprefix, sensorType)

    #Set the weather and manage the headlights.
    if sensorType == 'rgb':
        client.get_world().set_weather(condWeather)
        vehicleList = actorList.filter('vehicle.*')
        lightState = carla.VehicleLightState.NONE
        lightState |= carla.VehicleLightState.Position
        if(condLights == True):
            lightState |= carla.VehicleLightState.LowBeam
            lightState |= carla.VehicleLightState.Fog
        for vehicle in vehicleList:
            vehicle.set_light_state(carla.VehicleLightState(lightState))

    #weather = client.get_world().get_weather()
    #weather.precipitation = 100
    #client.get_world().set_weather(weather)

    #Wait 42 frames for vehicles to spawn - this is just the behaviour of the .log file.
    for i in range(0, 21):
        client.get_world().tick()

    #Start saving data.
    for sensor in sensorList:
        sensor.listen() 
    #Wait for the running log to finish
    for frameNumber in range (0,1):#(0,int(nFrames/2)-40):
        client.get_world().tick()
        imageSaver(sensorList, frameNumber, int(threadNumber))

    #Destroy the cameras - required since the car they are attached to is deleted on replay.
    #World should be asynchronous again - speed increase since no more data is collected.
    settings = client.get_world().get_settings()
    settings.synchronous_mode = False
    settings.fixed_delta_seconds = 0
    client.get_world().apply_settings(settings)
    for sensor in sensorList:
        sensor.destroy()

###########################################################
#
# WEATHER HANDLER - creates a list of weatherConditions from input file
#
########################################################### 

class weatherCondition:
    def __init__(self):
        self.weather = carla.WeatherParameters()
        self.headlights = False
        self.name = ""

    def setWeather(self, weather):
        self.weather = weather

    def setName(self, string):
        self.name = string

    def setHeadlights(self, boolin):
        self.headlights = bool(boolin)

    def getWeather(self):
        return self.weather

    def getName(self):
        return self.name

    def getHeadlights(self):
        return self.headlights

    def printWeather(self):
        print("WEATHER CONDITION")
        print("    Name: %s" % self.name)
        print("    Weather:", self.weather)
        print("    Headlights: ", self.headlights)
        
def weatherListConstructor(filename):
    if os.path.isfile(filename) == False:
        print("Weather .csv file specified does not exist. Please check the path.")
        return
    fp = open(filename)
    weatherList = []
    lineCount = 0
    for line in fp:
        if line[0] != '#': #If the line is not a comment...
            args = line.split(",")
            if len(args) != 11:
                print("Error: expected 11 arguments on line %i of weather file." % lineCount)
                return
            Name = args[0]
            cloudiness = float(args[1])
            precipitation = float(args[2])
            precipitation_deposits = float(args[3])
            wind_intensity = float(args[4])
            fog_density = float(args[5])
            fog_distance = float(args[6])
            wetness = float(args[7])
            sun_azimuth_angle = float(args[8])
            sun_altitude_angle = float(args[9])
            headlights = float(args[10])
            if (cloudiness > 100 or cloudiness < 0):
                print("Line %i: Clouds should be in range 0 < clouds < 100." % lineCount)
                return
            if (precipitation > 100 or precipitation < 0):
                print("Line %i: Rain should be in range 0 < rain < 100." % lineCount)
                return
            if (precipitation_deposits > 100 or precipitation_deposits < 0):
                print("Line %i: Water should be in range 0 < water < 100." % lineCount)
                return
            if (wind_intensity > 100 or wind_intensity < 0):
                print("Line %i: Wind should be in range 0 < wind < 100." % lineCount)
                return
            if (fog_density > 100 or fog_density < 0):
                print("Line %i: Fog density should be in range 0 < fog density < 100." % lineCount)
                return
            if (fog_distance < 0):
                print("Line %i: Fog distance should be in range 0 < fog distance." % lineCount)
                return
            if (wetness > 100 or wetness < 0):
                print("Line %i: Wetness should be in range 0 < wetness < 100." % lineCount)
                return
            if (sun_azimuth_angle > 360 or sun_azimuth_angle < 0):
                print("Line %i: Azimuth should be in range 0 < azimuth < 360." % lineCount)
                return
            if (sun_altitude_angle > 90 or sun_altitude_angle < -90):
                print("Line %i: Altitude should be in range -90 < altitude < 90." % lineCount)
                return
            weather = carla.WeatherParameters(
                cloudiness = cloudiness,
                precipitation = precipitation,
	        precipitation_deposits = precipitation_deposits,
	        wind_intensity = wind_intensity,
                fog_density = fog_density,
                fog_distance = fog_distance,
                wetness = wetness,
	        sun_azimuth_angle = sun_azimuth_angle,
	        sun_altitude_angle = sun_altitude_angle)
            newCondition = weatherCondition()
            newCondition.setName(Name)
            newCondition.setWeather(weather)
            newCondition.setHeadlights(headlights)
            weatherList.append(newCondition)
        lineCount = lineCount + 1
    return weatherList

###########################################################
#
# getLogTime/Name - returns the length of a log file in seconds/name
#
###########################################################

def getLogFrames(logFile, client):
    logFileInfo = client.show_recorder_file_info(logFile, False).split("\n")
    logFileLength = len(logFileInfo)
    DurString = logFileInfo[logFileLength-2].split(" ")
    logTime = float(DurString[1])
    logFrames = int(logTime * 20)
    return logFrames

def getLogName(logFile):
    sections = logFile.split("/")
    filename = sections[len(sections)-1]
    logFileName = filename.split(".")[0]
    return logFileName

###########################################################
#
# Batch destroy actors - taken from generateFreeDrivingLog.py
#
############################################################

def batchDestroy(client, actorList, chunkSize):
    response = []
    numFullChunks = int(len(actorList) / chunkSize)
    chunkRemainder = len(actorList) % chunkSize
    if numFullChunks > 0:
        for i in range(0, numFullChunks):
            chunk = actorList[(chunkSize*i):(chunkSize*i)+(chunkSize)]
            batchResponse = client.apply_batch_sync([carla.command.DestroyActor(x) for x in chunk])
            response.extend(batchResponse)
    if chunkRemainder > 0:
        chunk = actorList[(chunkSize*numFullChunks):(chunkSize*numFullChunks)+chunkRemainder]
        batchResponse = client.apply_batch_sync([carla.command.DestroyActor(x) for x in chunk])
        response.extend(batchResponse)

###########################################################
#
# MAIN - passes arguments
#
###########################################################

def main():
    argparser = argparse.ArgumentParser(
        description=__doc__)
    argparser.add_argument(
        '--host',
        metavar='H',
        default='127.0.0.1',
        help='IP of the host server (default: 127.0.0.1)')
    argparser.add_argument(
        '-p', '--port',
        metavar='P',
        default=2000,
        type=int,
        help='TCP port to listen to (default: 2000)')
    #Weather Parameters
    #Doc: https://carla.readthedocs.io/en/latest/python_api/#carla.WeatherParameters
    argparser.add_argument(
        '--weather_parameters',
	default='nil',
	help='.csv file of all of the desired weather scenarios to run.')
    argparser.add_argument(
	'--dir',
	default='./output',
	help='Directory output images will be saved to.')
    argparser.add_argument(
        '--sensors',
        default='nil',
        help='.cam file to define cameras to be attached to the vehicle.')
    argparser.add_argument(
        '--truth',
	default=0,
        type=bool,
        help='Flag to generate depth and semantic ground truth.')
    argparser.add_argument(
        '-l', '--logfile',
        metavar='F',
        help='Logfile containing the scenario to be replayed')
    argparser.add_argument(
	'-t', '--max_threads',
	default=1,
	help='Maximum number of threads that can be used to render images (default: 1)')
    args = argparser.parse_args()

    #Create the Carla client.
    #os.system(". /vol/teaching/drive_weather/run_carla")
    client = carla.Client(args.host, args.port)
    client.set_timeout(100.0)

    #Get recorder file info.
    logFileName = getLogName(args.logfile)
    logFrames = getLogFrames(args.logfile, client)

    print("Begin processing at %s" % datetime.datetime.now())
    dfltWthr = client.get_world().get_weather()

    #Run all conditions - Semantic, Depth, Weather Conditions
    if bool(args.truth):
        runCondition('Semantic', dfltWthr, False, args.logfile, logFileName, logFrames, args.sensors, args.dir, 'seg', args.max_threads, client)
        runCondition('Depth', dfltWthr, False, args.logfile, logFileName, logFrames, args.sensors, args.dir, 'depth', args.max_threads, client)

    weatherConditionList = weatherListConstructor(args.weather_parameters)
    for weather in weatherConditionList:
        runCondition(weather.getName(), weather.getWeather(), weather.getHeadlights(), args.logfile, logFileName, logFrames, args.sensors, args.dir, 'rgb', args.max_threads, client)

    #Remove all actors.
    idList = []
    actorList = client.get_world().get_actors()
    for vehicle in actorList.filter('vehicle.*'):
        idList.append(vehicle.id)
    for walker in actorList.filter('walker.*'):
        idList.append(walker.id)

    batchDestroy(client, idList, 10)

    print("End processing at %s" % datetime.datetime.now())

if __name__ == '__main__':

    try:
        main()
    except KeyboardInterrupt:
        pass
    finally:
        print('\nDone!')
