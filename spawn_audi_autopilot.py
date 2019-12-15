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
    args = argparser.parse_args()
    client = carla.Client(args.host, args.port)
    client.set_timeout(100.0)
    world = client.get_world()
    blueprint_library = world.get_blueprint_library()

    batch = []
    SpawnActor = carla.command.SpawnActor
    SetAutopilot = carla.command.SetAutopilot
    FutureActor = carla.command.FutureActor

    spawn_points = world.get_map().get_spawn_points()
    car_bp = blueprint_library.find('vehicle.audi.tt')
    car_bp.set_attribute('role_name', 'hero')
    car_transform = spawn_points[0]
    if car_bp.has_attribute('driver_id'):
        driver_id = random.choice(blueprint.get_attribute('driver_id').recommended_values)
        blueprint.set_attribute('driver_id', driver_id)
    batch.append(SpawnActor(car_bp, car_transform).then(SetAutopilot(FutureActor, True)))
    client.apply_batch_sync(batch)
if __name__ == '__main__':

    try:
        main()
    except KeyboardInterrupt:
        pass
    finally:
        print('\ndone.')

