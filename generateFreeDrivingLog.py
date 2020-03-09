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
        default='/vol/teaching/drive_weather/logs/FreeDrivingFresh.log')
    argparser.add_argument(
	'--recorderTime',
	default = 100,
        type=float)
    args = argparser.parse_args()
    client = carla.Client(args.host, args.port)
    client.set_timeout(1000)
    world = client.get_world()
    blueprint_library = world.get_blueprint_library()
    spawn_points = world.get_map().get_spawn_points()
    num_points = len(spawn_points)
    print('Number of available spawn points = %i' % num_points)

    batch = []
    SpawnActor = carla.command.SpawnActor
    SetAutopilot = carla.command.SetAutopilot
    FutureActor = carla.command.FutureActor
    client.apply_batch_sync([carla.command.DestroyActor(x) for x in world.get_actors()])

    world = client.get_world()
    world.wait_for_tick()
    world = client.get_world()

    #Spawn 99 NPC vehicles
    for i in range(1, 99):
	vehicle_bp = random.choice(blueprint_library.filter('vehicle.*'))
	vehicle_transform = spawn_points[i]
	batch.append(SpawnActor(vehicle_bp, vehicle_transform).then(SetAutopilot(FutureActor, True)))
    client.apply_batch_sync(batch)

    batch = []
    #Spawn 1 ego vehicle (vehicle.audi.tt)
    hero_bp = blueprint_library.find('vehicle.audi.tt')
    hero_transform = spawn_points[0]
    hero_bp.set_attribute('role_name', 'hero')
    if hero_bp.has_attribute('driver_id'):
        driver_id = random.choice(blueprint.get_attribute('driver_id').recommended_values)
        blueprint.set_attribute('driver_id', driver_id)
    batch.append(SpawnActor(hero_bp, hero_transform).then(SetAutopilot(FutureActor, True)))
    client.apply_batch_sync(batch)
    time.sleep(1)
    
    #Check I have created an egoVehicle...
    egoFlag = "false"
    actorList = world.get_actors()
    for actor in actorList:
	if(actor.attributes.get('role_name' == 'hero')):
		print("egoVehicle found!\n")
		egoFlag = "true"
		break

    if(egoFlag == "false"):
	print("Could not find egoVehicle even though I just spawned it!")

    client.start_recorder(args.recorderFile)
    for i in range(0, int(args.recorderTime)):
	time.sleep(1)
    client.stop_recorder()
    world = client.get_world()
    world.wait_for_tick()
    world = client.get_world()
    client.apply_batch_sync([carla.command.DestroyActor(x) for x in world.get_actors()])

if __name__ == '__main__':

    try:
        main()
    except KeyboardInterrupt:
        pass
    finally:
