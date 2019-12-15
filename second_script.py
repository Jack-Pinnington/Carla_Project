import glob
import os
import sys
import carla
import argparse
import math
import random
import time
import logging

try: 
    sys.path.append(glob.glob('**/carla-*%d.%d-%s.egg' % ( 
    sys.version_info.major, 
    sys.version_info.minor, 
    'win-amd64' if os.name == 'nt' else 'linux-x86_64'))[0]) 
except IndexError: 
    pass

###########################################################
#
# iSensor Class definitions
#
###########################################################


class iSensor:
    def __init__(self):
        self.x = 0
        self.y = 0
        self.z = 0
        self.yaw = 0

    def set_meta_params(self, path, name):
        self.dirpath = "%s/%s" % (path,name)
        
    def set_params(self, x, y, z, yaw):
        self.x = x
        self.y = y
        self.z = z
        self.yaw = yaw

    def get_params(self):
        return_list = [self.x, self.y, self.z, self.yaw]
        return return_list

    def attach_to_car(self, car, blueprint, world):
        camera_transform = carla.Transform(carla.Location(x=self.x, y=self.y, z=self.z), carla.Rotation(yaw=self.yaw))
        camera_bp = blueprint.find('sensor.camera.rgb') #default set to rgb
        self.sensor = world.spawn_actor(camera_bp, camera_transform, attach_to=car)

    def listen(self, dirname):
	print("Saving to: %s/%s" % (dirname, self.dirpath))
        self.sensor.listen(lambda image: image.save_to_disk('%s/%s/%06d.png' % (dirname, self.dirpath,image.frame_number)))

    def destroy(self):
	self.sensor.destroy()

###########################################################
#
# Function to check the format of the .cam file and create
# the sensor objects.
#
###########################################################

def sensor_handler(filename, car, blueprint, world, dirname, dirprefix):
    if os.path.isfile(filename) == False:
	print(".cam file specified does not exist. Please check the path.")
	return
    fp = open(filename)
    iSensor_list = []
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
                new_sensor.set_meta_params(dirprefix, args[0])
		new_sensor.attach_to_car(car, blueprint, world)
                iSensor_list.append(new_sensor)
    for sensor in iSensor_list:
        sensor.listen(dirname)
    return iSensor_list

###########################################################
#
# WEATHER HANDLER - handles the list of weather parameters
#
########################################################### 

def weatherHandler(line, lineCounter):
    args = line.split(",")
    if len(args) != 6:
	print("Error: Incorrect number of arguments on line %i of weather .csv file." % lineCounter)
	return
    clouds = float(args[0])
    rain = float(args[1])
    water = float(args[2])
    wind = float(args[3])
    azimuth = float(args[4])
    altitude = float(args[5])
    if (clouds > 100 or clouds < 0):
        print("Clouds should be in range 0 < clouds < 100.")
	return
    if (rain > 100 or rain < 0):
        print("Rain should be in range 0 < rain < 100.")
	return
    if (water > 100 or water < 0):
        print("Water should be in range 0 < water < 100.")
	return
    if (wind > 100 or wind < 0):
        print("Wind should be in range 0 < wind < 100.")
	return
    if (azimuth > 360 or azimuth < 0):
        print("Azimuth should be in range 0 < azimuth < 360.")
	return
    if (altitude > 90 or altitude < -90):
        print("Altitude should be in range -90 < altitude < 90.")
	return
    weather = carla.WeatherParameters(
	cloudyness = clouds,
        precipitation = rain,
	precipitation_deposits = water,
	wind_intensity = wind,
	sun_azimuth_angle = azimuth,
	sun_altitude_angle = altitude)
    return weather

###########################################################
#
# getLogTime/Name - returns the length of a log file in seconds/name
#
###########################################################

def getLogTime(logFile, client):
    logFileInfo = client.show_recorder_file_info(logFile, False).split("\n")
    logFileLength = len(logFileInfo)
    DurString = logFileInfo[logFileLength-2].split(" ")
    logTime = float(DurString[1])
    return logTime

def getLogName(logFile):
    logFileName = logFile.split(".")[0]
    logFileName = logFileName.split("/")
    lfLength = len(logFileName)
    logFileName = logFileName[lfLength - 1]
    return logFileName

###########################################################
#
# Post-processing - match all file names.
#
###########################################################

def postProcess(directory, logFileName):
    path = "%s/%s" % (directory, logFileName)
    imageLengthList = []
    folders = ([name for name in os.listdir(path)])
    #Get the number of images in each folder.
    for folder in folders:
        sensors = os.listdir(os.path.join(path, folder))
	for sensor in sensors:
	    dirName = "%s/%s" % (folder, sensor)
	    nImages = len(os.listdir(os.path.join(path, dirName)))
            imageLengthList.append(nImages)
    #Get the minimum
    minImages = min(imageLengthList)
    for folder in folders:
	sensors = os.listdir(os.path.join(path, folder))
	for sensor in sensors:
	    dirName = "%s/%s" % (folder, sensor)
	    imageList = os.listdir(os.path.join(path, dirName))
	    imageList.sort()
	    imageCounter = 0
	    for image in imageList:
		newFileName = "%06d.png" % imageCounter
		newFilePath = os.path.join(path, dirName, newFileName)
		imagePath = os.path.join(path, dirName, image)
		if imageCounter < minImages:
		    os.rename(imagePath, newFilePath)
		else:
		    os.remove(imagePath)
		imageCounter = imageCounter + 1
    
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
	default='.',
	help='Directory output images will be saved to.')
    argparser.add_argument(
        '--sensors',
        default='nil',
        help='.cam file to define cameras to be attached to the vehicle.')
    argparser.add_argument(
        '-l', '--logfile',
        metavar='F',
        help='Logfile containing the scenario to be replayed')
    args = argparser.parse_args()

    #Create the Carla client.
    #os.system(". /vol/teaching/drive_weather/run_carla")
    client = carla.Client(args.host, args.port)
    client.set_timeout(100.0)

    #Get recorder file info.
    logFileName = getLogName(args.logfile)
    logTime = getLogTime(args.logfile, client)
    world = client.get_world()
    blueprint_library = world.get_blueprint_library()

    if os.path.isfile(args.weather_parameters) == False:
	print(".csv Weather file specified does not exist. Please check the path.")
	return
    weatherFile = open(args.weather_parameters)
    #For each weather condition specified, run the log file.
    for line in weatherFile:
        #Read one set of weather conditions from the .csv input file.
        weather = weatherHandler(line, 0)
        if (weather == None):
	    return
        dirprefix = '%s/%d_%d_%d_%d_%d_%d' % (logFileName, weather.cloudyness, weather.precipitation, weather.precipitation_deposits, weather.wind_intensity, weather.sun_azimuth_angle, weather.sun_altitude_angle)
        #Replay the selected log file.
	client.replay_file(args.logfile, 0, 0, 0)
        #World updates to the log file on the next tick - required to wait to read actor pool.
        world = client.get_world()
        world.wait_for_tick()
        world = client.get_world()
        #LIMIT FRAMERATE TO 20FPS
        settings = world.get_settings()
        settings.fixed_delta_seconds = 0.05
        world.apply_settings(settings)
        world.set_weather(weather)
        #Find my vehicle (audi tt) and attach all specified sensors.
	egoVehicle = world.get_actors().filter('vehicle.audi.tt')[0]
	sensorList = sensor_handler(args.sensors, egoVehicle, blueprint_library, world, args.dir, dirprefix)
        world.set_weather(weather)
        #Wait for the running log to finish
	time.sleep(logTime)
        #Destroy the camera - only way to stop it listening (and send to new directory).
        for camera in sensorList:
            camera.destroy()

    #Post processing renames all image files to begin at 000000.png and matches image number.
    postProcess(args.dir, logFileName)

if __name__ == '__main__':

    try:
        main()
    except KeyboardInterrupt:
        pass
    finally:
        print('\nDone!')

