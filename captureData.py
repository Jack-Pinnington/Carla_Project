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
import weakref
import json

try: 
    sys.path.append(glob.glob('**/carla-*%d.%d-%s.egg' % ( 
    sys.version_info.major, 
    sys.version_info.minor, 
    'win-amd64' if os.name == 'nt' else 'linux-x86_64'))[0]) 
except IndexError: 
    pass

###########################################################
#
#  Localization objects - GPS and IMU classes
#
###########################################################

class IMUSensor(object):
    def __init__(self, parent_actor):
        self.sensor = None
        self._parent = parent_actor
        self.accelerometer = (0.0, 0.0, 0.0)
        self.gyroscope = (0.0, 0.0, 0.0)
        self.compass = 0.0
        world = self._parent.get_world()
        bp = world.get_blueprint_library().find('sensor.other.imu')
        self.sensor = world.spawn_actor(
            bp, carla.Transform(), attach_to=self._parent)
        # We need to pass the lambda a weak reference to self to avoid circular
        # reference.
        weak_self = weakref.ref(self)
        self.sensor.listen(
            lambda sensor_data: IMUSensor._IMU_callback(weak_self, sensor_data))

    @staticmethod
    def _IMU_callback(weak_self, sensor_data):
        self = weak_self()
        if not self:
            return
        limits = (-99.9, 99.9)
        self.accelerometer = (
            max(limits[0], min(limits[1], sensor_data.accelerometer.x)),
            max(limits[0], min(limits[1], sensor_data.accelerometer.y)),
            max(limits[0], min(limits[1], sensor_data.accelerometer.z)))
        self.gyroscope = (
            max(limits[0], min(limits[1], math.degrees(sensor_data.gyroscope.x))),
            max(limits[0], min(limits[1], math.degrees(sensor_data.gyroscope.y))),
            max(limits[0], min(limits[1], math.degrees(sensor_data.gyroscope.z))))
        self.compass = math.degrees(sensor_data.compass)

    def data(self):
        returnList = []
        returnList.append(self.accelerometer)
        returnList.append(self.gyroscope)
        returnList.append(self.compass)
        return returnList

    def destroy(self):
        self.sensor.destroy()

class GnssSensor(object):
    def __init__(self, parent_actor):
        self.sensor = None
        self._parent = parent_actor
        self.lat = 0.0
        self.lon = 0.0
        world = self._parent.get_world()
        bp = world.get_blueprint_library().find('sensor.other.gnss')
        self.sensor = world.spawn_actor(bp, carla.Transform(carla.Location(x=1.0, z=2.8)), attach_to=self._parent)
        # We need to pass the lambda a weak reference to self to avoid circular
        # reference.
        weak_self = weakref.ref(self)
        self.sensor.listen(lambda event: GnssSensor._on_gnss_event(weak_self, event))

    @staticmethod
    def _on_gnss_event(weak_self, event):
        self = weak_self()
        if not self:
            return
        self.lat = event.latitude
        self.lon = event.longitude

    def data(self):
        returnList = [self.lat, self.lon]
        return returnList

    def destroy(self):
        self.sensor.destroy()

def saveGPStoFile(imuList, gpsList, frameNumber, filePrefix):
    filename = '%s/%06d.txt' % (filePrefix, frameNumber)
    #Using JSON dict method
    jsonDict = {"Accelerometer": imuList[0], "Gyroscope": imuList[1], "Compass": imuList[2], "Latitude": gpsList[0], "Longitude": gpsList[1]}
    with open(filename, 'w') as outfile:
        json.dump(jsonDict, outfile)
    
##############################################################
#
#   RUN_GPS
#
##############################################################
def runGPS(logFile, logFileName, logFrames, outputDir, client):

    #Make the GPS directory if it doesn't already exist.
    dirPrefix = '%s/%s/GPS' % (outputDir, logFileName)
    cwd = os.getcwd()
    path = os.path.join(cwd, dirPrefix)
    if not(os.path.exists(path)):
        os.makedirs(path)

    #Turn on synchronous mode
    settings = client.get_world().get_settings()
    settings.synchronous_mode = True
    settings.fixed_delta_seconds = 0.10
    client.get_world().apply_settings(settings)

    for i in range(0,5):
        client.get_world().tick()

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
    
    #Create GPS and IMU sensor.
    gpsSensor = GnssSensor(egoVehicle)
    imuSensor = IMUSensor(egoVehicle)

    #20 ticks to skip spawn animation - in sync with the rgb runCondition.
    for i in range(0, 20):
        client.get_world().tick()

    #Sleep here is required to prevent buffering problem - buffer will read from previous step rather than current.
    time.sleep(2)

    #Start saving data.
    #Wait for the running log to finish
    for frameNumber in range (0,int(logFrames/2)-40):
        client.get_world().tick()
        saveGPStoFile(imuSensor.data(), gpsSensor.data(), frameNumber, dirPrefix)
        #imageSaver(sensorList, frameNumber, int(threadNumber))

    #Destroy the cameras - required since the car they are attached to is deleted on replay.
    #World should be asynchronous again - speed increase since no more data is collected.
    settings = client.get_world().get_settings()
    settings.synchronous_mode = False
    settings.fixed_delta_seconds = 0
    client.get_world().apply_settings(settings)

    imuSensor.destroy()
    gpsSensor.destroy()

###########################################################
#
# ISENSOR - a class which defines CARLA sensor objects and
# provides an API for attaching to a car and saving images.
#
###########################################################

class rgbSensor:
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

def rgbSensorCreator(filename, car, client, dirname, dirprefix, sensorType):
    world = client.get_world()
    blueprint = world.get_blueprint_library()
    if os.path.isfile(filename) == False:
        print(".cam file specified does not exist. Please check the path.")
        return
    fp = open(filename)
    rgbSensorList = []
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
                new_sensor = rgbSensor()
                new_sensor.set_params(float(args[1]), float(args[2]), float(args[3]), int(args[4]))
                new_sensor.set_meta_params(dirname, dirprefix, args[0])
                new_sensor.attach_to_car(car, blueprint, world, sensorType)
                rgbSensorList.append(new_sensor)
        linecounter = linecounter + 1
    return rgbSensorList

###########################################################
#
# IMAGE SAVER - saves images using multi-threading for 
# all sensors.
#
###########################################################

def rgbSaver(sensorList, frameNumber, maxThreads):
    numSensors = len(sensorList)
    numFullThreads = int(numSensors / maxThreads)
    threadRemainder = numSensors % maxThreads
    sensorCounter = 0
    if numFullThreads > 0:
        for j in range(0, numFullThreads):
            threads = list()
            for i in range(0, maxThreads):
                thread = threading.Thread(target = sensorList[sensorCounter].saveImage, args=(frameNumber,))
                threads.append(thread)
                sensorCounter = sensorCounter + 1
                thread.start()
            for thread in threads:
                thread.join()
    if threadRemainder > 0:
        threads = list()
        for i in range(0, threadRemainder):
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

    for i in range(0,5):
        client.get_world().tick()
        time.sleep(0.1)

    #Replay the log file
    client.replay_file(logFile, 0, 0, 0)

    #time.sleep(5)
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
    sensorList = rgbSensorCreator(sensorFile, egoVehicle, client, sensorDir, dirprefix, sensorType)

    client.get_world().tick()

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

    #Wait 20 frames for vehicles to spawn to skip spawn animation.
    for i in range(0, 20):
        client.get_world().tick()
        time.sleep(0.1)
    
    #Sleep here is required to prevent buffering problem - buffer will read from previous step rather than current.
    time.sleep(2)

    #Start saving data.
    for sensor in sensorList:
        sensor.listen() 

    #Wait for the running log to finish, skipping delete animation.
    for frameNumber in range (0,int(logFrames/2)-40):
        client.get_world().tick()
        rgbSaver(sensorList, frameNumber, int(threadNumber))

    #World should be asynchronous again - server timeout if no tick received in synchronous mode.
    settings = client.get_world().get_settings()
    settings.synchronous_mode = False
    settings.fixed_delta_seconds = 0
    client.get_world().apply_settings(settings)

    for sensor in sensorList:
        sensor.destroy()

    #Reload world so any static objects moved are returned.
    client.reload_world()

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

def getLogMap(logFile, client):
    logFileInfo = client.show_recorder_file_info(logFile, False).split("\n")
    MapString = logFileInfo[1].split(" ")
    return MapString[1]

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
        type=int,
        help='Flag to generate depth, semantic and gps ground truth.')
    argparser.add_argument(
        '-l', '--logfile',
        metavar='F',
        help='Logfile containing the scenario to be replayed')
    argparser.add_argument(
	'-t', '--max_threads',
	default=3,
	help='Maximum number of threads that can be used to render images (default: 1)')
    args = argparser.parse_args()

    #Check args.
    if os.path.isfile(args.logfile) == False:
        print(".log file specified does not exist. Please check the path.")
        return
    if os.path.isfile(args.sensors) == False:
        print("Sensor file specified does not exist. Please check the path.")
        return
    if os.path.isfile(args.weather_parameters) == False:
        print("Weather .csv file specified does not exist. Please check the path.")
        return

    #Create the Carla client.
    #os.system(". /vol/teaching/drive_weather/run_carla")
    client = carla.Client(args.host, args.port)
    client.set_timeout(100.0)

    #Get recorder file info.
    logFileName = getLogName(args.logfile)
    logFrames = getLogFrames(args.logfile, client)
    logMap = getLogMap(args.logfile, client)
    #Load world to prevent sync issue on first condition.
    client.load_world(logMap)
    
    print("----------------")
    print("BEGIN LOGFILE %s, SENSORFILE %s at %s" % (args.logfile,args.sensors, datetime.datetime.now()))
    print("----------------")
    dfltWthr = client.get_world().get_weather()

    #Run truth conditions - GPS, Semantic and Depth
    if bool(args.truth):
        runGPS(args.logfile, logFileName, logFrames, args.dir, client)
        runCondition('Semantic', dfltWthr, False, args.logfile, logFileName, logFrames, args.sensors, args.dir, 'seg', args.max_threads, client)
        runCondition('Depth', dfltWthr, False, args.logfile, logFileName, logFrames, args.sensors, args.dir, 'depth', args.max_threads, client)
        print("Completed Truth at %s" % datetime.datetime.now())

    weatherConditionList = weatherListConstructor(args.weather_parameters)
    for weather in weatherConditionList:
        runCondition(weather.getName(), weather.getWeather(), weather.getHeadlights(), args.logfile, logFileName, logFrames, args.sensors, args.dir, 'rgb', args.max_threads, client)
        print("Condition: %s completed at time %s." % (weather.getName(), datetime.datetime.now()))

    print("End processing at %s" % datetime.datetime.now())

if __name__ == '__main__':

    try:
        main()
    except KeyboardInterrupt:
        pass
