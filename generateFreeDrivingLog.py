try:
    sys.path.append(glob.glob('../carla/dist/carla-*%d.%d-%s.egg' % (
        sys.version_info.major,
        sys.version_info.minor,
        'win-amd64' if os.name == 'nt' else 'linux-x86_64'))[0])
except IndexError:
    pass

import glob
import os
import sys
import argparse
import carla
import logging
import random
import time

carBlueprints = []
motorbikeBlueprints = []
bicycleBlueprints = []

SpawnActor = carla.command.SpawnActor
SetAutopilot = carla.command.SetAutopilot
FutureActor = carla.command.FutureActor

def makeNightBlueprints(bpl):
    #Cars
    carBlueprints.append(bpl.find('vehicle.audi.tt'))
    carBlueprints.append(bpl.find('vehicle.chevrolet.impala'))
    carBlueprints.append(bpl.find('vehicle.dodge_charger.police'))
    carBlueprints.append(bpl.find('vehicle.audi.etron'))
    carBlueprints.append(bpl.find('vehicle.lincoln.mkz2017'))
    carBlueprints.append(bpl.find('vehicle.mustang.mustang'))
    carBlueprints.append(bpl.find('vehicle.tesla.model3'))
    carBlueprints.append(bpl.find('vehicle.volkswagen.t2'))

    #Notable absence of the Tesla Cybertruck... it's just ridiculous

    #Motorbikes
    motorbikeBlueprints.append(bpl.find('vehicle.harley-davidson.low_rider'))
    motorbikeBlueprints.append(bpl.find('vehicle.yamaha.yzf'))

    #Bicycles
    bicycleBlueprints.append(bpl.find('vehicle.gazelle.omafiets'))
    bicycleBlueprints.append(bpl.find('vehicle.diamondback.century'))
    bicycleBlueprints.append(bpl.find('vehicle.bh.crossbike'))

def spawnCar(spawnPoint):
    vehicle_bp = random.choice(carBlueprints)
    color = random.choice(vehicle_bp.get_attribute('color').recommended_values)
    vehicle_bp.set_attribute('color', color)
    command = SpawnActor(vehicle_bp, spawnPoint).then(SetAutopilot(FutureActor, True))
    return command

def spawnMotorbike(spawnPoint):
    vehicle_bp = random.choice(motorbikeBlueprints)
    color = random.choice(vehicle_bp.get_attribute('color').recommended_values)
    vehicle_bp.set_attribute('color', color)
    command = SpawnActor(vehicle_bp, spawnPoint).then(SetAutopilot(FutureActor, True))
    return command

def spawnBike(spawnPoint):
    vehicle_bp = random.choice(bicycleBlueprints)
    color = random.choice(vehicle_bp.get_attribute('color').recommended_values)
    vehicle_bp.set_attribute('color', color)
    command = SpawnActor(vehicle_bp, spawnPoint).then(SetAutopilot(FutureActor, True))
    return command

def batchSpawn(client, actorList, chunkSize):
    response = []
    numFullChunks = int(len(actorList) / chunkSize)
    chunkRemainder = len(actorList) % chunkSize
    if numFullChunks > 0:
        for i in range(0, numFullChunks):
            chunk = actorList[(chunkSize*i):(chunkSize*i)+(chunkSize)]
            batchResponse = client.apply_batch_sync(chunk)
            response.extend(batchResponse)
    if chunkRemainder > 0:
        chunk = actorList[(chunkSize*numFullChunks):(chunkSize*numFullChunks)+chunkRemainder]
        batchResponse = client.apply_batch_sync(chunk)
        response.extend(batchResponse)
    return response

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
    argparser.add_argument(
	'--recorderFile',
        default='/home/jack/Carla/Carla_0.9.8_package/Town01_test.log')
    argparser.add_argument(
	'--recorderTime',
	default = 5,
        type=float)
    argparser.add_argument(
        '--townNumber',
        default = 1,
        type=int)
    argparser.add_argument(
	'--numWalkers',
	default = 60,
        type=int)
    argparser.add_argument(
	'--numCars',
	default = 90,
        type=int)
    argparser.add_argument(
	'--numMotorbikes',
	default = 15,
        type=int)
    argparser.add_argument(
	'--numBicycles',
	default = 15,
        type=int)
    args = argparser.parse_args()
    client = carla.Client(args.host, args.port)
    client.set_timeout(1000)
    #Load the town.
    if (args.townNumber < 0 or args.townNumber > 5):
        print("Error: Expected town number in range 1 to 5.")
        return
    townName = 'Town0%i' % args.townNumber
    client.load_world(townName)
    world = client.get_world()

    blueprint_library = world.get_blueprint_library()
    spawn_points = world.get_map().get_spawn_points()
    num_points = len(spawn_points)
    print('Number of available spawn points = %i' % num_points)
    #Shuffle spawn points so everything is randomized - stops there being clumps of vehicles.
    random.shuffle(spawn_points)

    #settings = world.get_settings()
    #settings.fixed_delta_seconds = 0.10
    #world.apply_settings(settings)

    batch = []

    world = client.get_world()
    world.wait_for_tick()
    world = client.get_world()

#################################################################
#
#   SPAWN VEHICLES
#
#################################################################

    makeNightBlueprints(blueprint_library)

    vehiclesToSpawn = []
    spawnedVehicleIDs = []

    #EGOVEHICLE at 0
    #Spawn 1 ego vehicle (vehicle.audi.tt)
    hero_bp = blueprint_library.find('vehicle.audi.tt')
    hero_transform = spawn_points[0]
    hero_bp.set_attribute('role_name', 'hero')
    print(hero_bp.get_attribute('role_name'))
    if hero_bp.has_attribute('driver_id'):
        driver_id = random.choice(blueprint.get_attribute('driver_id').recommended_values)
        blueprint.set_attribute('driver_id', driver_id)
    vehiclesToSpawn.append(SpawnActor(hero_bp, hero_transform).then(SetAutopilot(FutureActor, True)))

    #Spawn other vehicles
    carFinish = int(args.numCars + 1)
    motorbikeStart = carFinish
    motorbikeFinish = int(motorbikeStart + args.numMotorbikes)
    bicycleStart = motorbikeFinish
    bicycleFinish = int(bicycleStart + args.numBicycles)

    for i in range(1, carFinish):
        vehiclesToSpawn.append(spawnCar(spawn_points[i]))
    for i in range(motorbikeStart, motorbikeFinish):
        vehiclesToSpawn.append(spawnMotorbike(spawn_points[i]))
    for i in range(bicycleStart, bicycleFinish):
        vehiclesToSpawn.append(spawnBike(spawn_points[i]))

    print('Spawning %s Vehicles!' % len(vehiclesToSpawn))
    for response in batchSpawn(client, vehiclesToSpawn, 10):
        spawnedVehicleIDs.append(response.actor_id)
    world.wait_for_tick()

########################################################
#
#   SPAWN WALKERS BEGIN
#
########################################################
    # some settings
    walkerNumber = args.numWalkers
    blueprintsWalkers = blueprint_library.filter('walker.pedestrian.*')
    percentagePedestriansRunning = 0.1      # how many pedestrians will run
    percentagePedestriansCrossing = 0.2     # how many pedestrians will walk through the road

    # Find my spawn locations.
    walkerSpawnPoints = []
    for i in range(walkerNumber):
        spawn_point = carla.Transform()
        loc = world.get_random_location_from_navigation()
        if (loc != None):
            spawn_point.location = loc
            walkerSpawnPoints.append(spawn_point)

    # Create Walker Blueprints
    walkersToSpawn = []
    walkerBPSpeed = []
    for spawn_point in walkerSpawnPoints:
        walker_bp = random.choice(blueprintsWalkers)
        # set as not invincible
        if walker_bp.has_attribute('is_invincible'):
            walker_bp.set_attribute('is_invincible', 'false')
        # set the max speed
        if walker_bp.has_attribute('speed'):
            if (random.random() > percentagePedestriansRunning):
                # walking
                walkerBPSpeed.append(walker_bp.get_attribute('speed').recommended_values[1])
            else:
                # running
                walkerBPSpeed.append(walker_bp.get_attribute('speed').recommended_values[2])
        else:
            print("Walker has no speed")
            walkerBPSpeed.append(0.0)
        walkersToSpawn.append(SpawnActor(walker_bp, spawn_point))

    #Batch Spawn Walkers
    spawnedWalkerList = []
    walkerSpawnedSpeed = []
    responseNumber = 0
    for response in batchSpawn(client, walkersToSpawn, 10):
        if not(response.error):
            spawnedWalkerList.append({"id": response.actor_id})
            walkerSpawnedSpeed.append(walkerBPSpeed[responseNumber])
        responseNumber = responseNumber + 1

    # Create walker controllers
    walkerControllersToSpawn = []
    walker_controller_bp = world.get_blueprint_library().find('controller.ai.walker')
    for i in range(len(spawnedWalkerList)):
        walkerControllersToSpawn.append(SpawnActor(walker_controller_bp, carla.Transform(), spawnedWalkerList[i]["id"]))

    # Batch the controllers
    resultCounter = 0
    for response in batchSpawn(client, walkerControllersToSpawn, 10):
        spawnedWalkerList[resultCounter]["con"] = response.actor_id
        resultCounter = resultCounter + 1

    # Create a full list of IDs (walkerIDList) and list of controllers (controllerList)
    walkerIDList = []
    controllerList = []
    for i in range(len(spawnedWalkerList)):
        controllerList.append(spawnedWalkerList[i]["con"])
        walkerIDList.append(spawnedWalkerList[i]["con"])
        walkerIDList.append(spawnedWalkerList[i]["id"])
    controllerList = world.get_actors(controllerList)
    world.wait_for_tick()

    print("Total walkers spawned: %s" % len(controllerList))

    # Set each controller to their seeded speed
    world.set_pedestrians_cross_factor(percentagePedestriansCrossing)
    for i in range(0, len(controllerList)):
        controllerList[i].start()
        controllerList[i].go_to_location(world.get_random_location_from_navigation())
        controllerList[i].set_max_speed(float(walkerSpawnedSpeed[i]))


##############################################################
#
#   RECORD AND DELETE WHEN FINISHED
#
##############################################################

    client.start_recorder(args.recorderFile)
    print('Sleeping for %i seconds...' % int(args.recorderTime))
    for i in range(0, int(args.recorderTime)):
        time.sleep(1)
    client.stop_recorder()
    world = client.get_world()
    world.wait_for_tick()
    world = client.get_world()

    print('Output log saved to:  %s' % args.recorderFile)

    batchDestroy(client, spawnedVehicleIDs, 10)

    #Delete the walker actors!
    for i in range(0, len(controllerList)):
        controllerList[i].stop()
    batchDestroy(client, walkerIDList, 10)

    print('Deleted all vehicles + pedestrians.')

if __name__ == '__main__':

    try:
        main()
    except KeyboardInterrupt:
        pass
