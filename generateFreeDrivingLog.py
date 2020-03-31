import glob
import os
import sys
import argparse

try:
    sys.path.append(glob.glob('../carla/dist/carla-*%d.%d-%s.egg' % (
        sys.version_info.major,
        sys.version_info.minor,
        'win-amd64' if os.name == 'nt' else 'linux-x86_64'))[0])
except IndexError:
    pass

import carla
import argparse
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
    command = SpawnActor(vehicle_bp, spawnPoint).then(SetAutopilot(FutureActor, True))
    return command

def spawnMotorbike(spawnPoint):
    vehicle_bp = random.choice(motorbikeBlueprints)
    command = SpawnActor(vehicle_bp, spawnPoint).then(SetAutopilot(FutureActor, True))
    return command

def spawnBike(spawnPoint):
    vehicle_bp = random.choice(bicycleBlueprints)
    command = SpawnActor(vehicle_bp, spawnPoint).then(SetAutopilot(FutureActor, True))
    return command

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
        default='/home/jack/Carla/Carla_0.9.8_package/Town03.log')
    argparser.add_argument(
	'--recorderTime',
	default = 180,
        type=float)
    args = argparser.parse_args()
    client = carla.Client(args.host, args.port)
    client.set_timeout(1000)
    client.load_world('Town03')
    world = client.get_world()

    blueprint_library = world.get_blueprint_library()
    spawn_points = world.get_map().get_spawn_points()
    num_points = len(spawn_points)
    print('Number of available spawn points = %i' % num_points)
    #Shuffle spawn points so everything is randomized - stops there being clumps of vehicles.
    random.shuffle(spawn_points)

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

    for i in range(1, 90):
        vehiclesToSpawn.append(spawnCar(spawn_points[i]))
    for i in range(91, 105):
        vehiclesToSpawn.append(spawnMotorbike(spawn_points[i]))
    for i in range(106, 110):
        vehiclesToSpawn.append(spawnBike(spawn_points[i]))

    #Necessary to batch_sync in chunks - sending all at once will cause a SegFault in the server.
    chunkSize = 9
    numFullChunks = int(len(vehiclesToSpawn) / chunkSize)
    chunkRemainder = len(vehiclesToSpawn) % chunkSize
    print('Spawning %s Vehicles!' % len(vehiclesToSpawn))
    if numFullChunks > 0:
        for i in range(0, numFullChunks):
            chunk = vehiclesToSpawn[(chunkSize*i):(chunkSize*i)+(chunkSize)]
            batchResponse = client.apply_batch_sync(chunk)
            for response in batchResponse:
                spawnedVehicleIDs.append(response.actor_id)
    if chunkRemainder > 0:
        chunk = vehiclesToSpawn[(chunkSize*numFullChunks):(chunkSize*numFullChunks)+chunkRemainder]
        batchResponse = client.apply_batch_sync(chunk)
        for response in batchResponse:
            spawnedVehicleIDs.append(response.actor_id)

    world.wait_for_tick()

########################################################
#
#   SPAWN WALKERS BEGIN
#
########################################################
    # some settings
    walkerNumber = 60
    blueprintsWalkers = blueprint_library.filter('walker.pedestrian.*')
    percentagePedestriansRunning = 0.1      # how many pedestrians will run
    percentagePedestriansCrossing = 0.2     # how many pedestrians will walk through the road

    # 1. take all the random locations to spawn
    walkerSpawnPoints = []
    for i in range(walkerNumber):
        spawn_point = carla.Transform()
        loc = world.get_random_location_from_navigation()
        if (loc != None):
            spawn_point.location = loc
            walkerSpawnPoints.append(spawn_point)
    # 2. Create Walker Blueprints
    walkersToSpawn = []
    walker_speed = []
    for spawn_point in walkerSpawnPoints:
        walker_bp = random.choice(blueprintsWalkers)
        # set as not invincible
        if walker_bp.has_attribute('is_invincible'):
            walker_bp.set_attribute('is_invincible', 'false')
        # set the max speed
        if walker_bp.has_attribute('speed'):
            if (random.random() > percentagePedestriansRunning):
                # walking
                walker_speed.append(walker_bp.get_attribute('speed').recommended_values[1])
            else:
                # running
                walker_speed.append(walker_bp.get_attribute('speed').recommended_values[2])
        else:
            print("Walker has no speed")
            walker_speed.append(0.0)
        walkersToSpawn.append(SpawnActor(walker_bp, spawn_point))

    #Batch Spawn Walkers.
    spawnedWalkerList = []
    walker_speed2 = []
    chunkSize = 9
    numFullChunks = int(len(walkersToSpawn) / chunkSize)
    chunkRemainder = len(walkersToSpawn) % chunkSize
    print('Spawning Walkers!')
    if numFullChunks > 0:
        for i in range(0, numFullChunks):
            chunk = walkersToSpawn[(chunkSize*i):(chunkSize*i)+(chunkSize)]
            batchResponse = client.apply_batch_sync(chunk)
            for response in batchResponse:
                spawnedWalkerList.append({"id": response.actor_id})
                walker_speed2.append(walker_speed[i])
    if chunkRemainder > 0:
        chunk = walkersToSpawn[(chunkSize*numFullChunks):(chunkSize*numFullChunks)+chunkRemainder]
        batchResponse = client.apply_batch_sync(chunk)
        for response in batchResponse:
            spawnedWalkerList.append({"id": response.actor_id})
            walker_speed2.append(walker_speed[i])
    #results = client.apply_batch_sync(batch, True)
    walker_speed = walker_speed2

    # 3. Create walker controllers
    walkerControllersToSpawn = []
    walker_controller_bp = world.get_blueprint_library().find('controller.ai.walker')
    for i in range(len(spawnedWalkerList)):
        walkerControllersToSpawn.append(SpawnActor(walker_controller_bp, carla.Transform(), spawnedWalkerList[i]["id"]))

    #Batch the walker controllers!
    chunkSize = 9
    numFullChunks = int(len(walkerControllersToSpawn) / chunkSize)
    chunkRemainder = len(walkerControllersToSpawn) % chunkSize
    resultCounter = 0
    print('Spawning Controllers!')
    if numFullChunks > 0:
        for i in range(0, numFullChunks):
            chunk = walkerControllersToSpawn[(chunkSize*i):(chunkSize*i)+(chunkSize)]
            batchResponse = client.apply_batch_sync(chunk)
            for response in batchResponse:
                spawnedWalkerList[resultCounter]["con"] = response.actor_id
                resultCounter = resultCounter + 1
    if chunkRemainder > 0:
        chunk = walkerControllersToSpawn[(chunkSize*numFullChunks):(chunkSize*numFullChunks)+chunkRemainder]
        batchResponse = client.apply_batch_sync(chunk)
        for response in batchResponse:
            spawnedWalkerList[resultCounter]["con"] = response.actor_id
            resultCounter = resultCounter + 1

    # 4. we put altogether the walkers and controllers id to get the objects from their id
    walkerIDList = []
    for i in range(len(spawnedWalkerList)):
        walkerIDList.append(spawnedWalkerList[i]["con"])
        walkerIDList.append(spawnedWalkerList[i]["id"])
    controllerList = []
    for i in range(len(spawnedWalkerList)):
        controllerList.append(spawnedWalkerList[i]["con"])
    controllerList = world.get_actors(controllerList)
    walkerActorList = world.get_actors(walkerIDList)
    world.wait_for_tick()

    print("Total walkers spawned: %s" % len(controllerList))

    # 5. initialize each controller and set target to walk to (list is [controler, actor, controller, actor ...])
    # set how many pedestrians can cross the road
    world.set_pedestrians_cross_factor(percentagePedestriansCrossing)
    for i in range(0, len(controllerList)):
        # start walker
        controllerList[i].start()
        # set walk to random point
        controllerList[i].go_to_location(world.get_random_location_from_navigation())
        # max speed
        controllerList[i].set_max_speed(float(walker_speed[int(i/2)]))


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

    print('Deleting Vehicles!')
    numFullChunks = int(len(spawnedVehicleIDs) / chunkSize)
    chunkRemainder = len(spawnedVehicleIDs) % chunkSize
    
    if numFullChunks > 0:
        for i in range(0, numFullChunks):
            chunk = spawnedVehicleIDs[(chunkSize*i):(chunkSize*i)+(chunkSize)]
            batchResponse = client.apply_batch_sync([carla.command.DestroyActor(x) for x in chunk])
    if chunkRemainder > 0:
        chunk = spawnedVehicleIDs[(chunkSize*numFullChunks):(chunkSize*numFullChunks)+chunkRemainder]
        batchResponse = client.apply_batch_sync([carla.command.DestroyActor(x) for x in chunk])

    #Delete the walker actors!
    print('Deleting Walkers + Controllers!')

    for i in range(0, len(controllerList)):
        controllerList[i].stop()

    numFullChunks = int(len(walkerIDList) / chunkSize)
    chunkRemainder = len(walkerIDList) % chunkSize
    
    if numFullChunks > 0:
        for i in range(0, numFullChunks):
            chunk = walkerIDList[(chunkSize*i):(chunkSize*i)+(chunkSize)]
            batchResponse = client.apply_batch_sync([carla.command.DestroyActor(x) for x in chunk])
    if chunkRemainder > 0:
        chunk = walkerIDList[(chunkSize*numFullChunks):(chunkSize*numFullChunks)+chunkRemainder]
        batchResponse = client.apply_batch_sync([carla.command.DestroyActor(x) for x in chunk])

if __name__ == '__main__':

    try:
        main()
    except KeyboardInterrupt:
        pass
