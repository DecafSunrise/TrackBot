# Navigation (Nav2)

Configuration for autonomous mapping, localization, and path planning using the Nav2 stack with OAK-D-Lite depth data.

## Overview

```
OAK-D-Lite                        Nav2 Stack
───────────                        ┌─────────┐
/depth/points ────────────────────►│ AMCL    │──► /map
                                  │         │
/odom ────────────────────────────►│         │
                                  └─────────┘
                                  ┌─────────┐
                                  │ Planner │──► global path
                                  │ (Navfn) │
                                  └─────────┘
                                  ┌─────────┐
                                  │Controller│──► /cmd_vel
                                  │ (Reg.   │
                                  │  Pure   │
                                  │  Purs.) │
                                  └─────────┘
                                  ┌─────────┐
                                  │Costmaps │
                                  │(local + │
                                  │ global) │
                                  └─────────┘
```

## Key Parameters

All parameters live in `config/nav2_params.yaml`.

### Controller: Regulated Pure Pursuit

```yaml
FollowPath:
  plugin: nav2_regulated_pure_pursuit_controller::RegulatedPurePursuitController
  desired_linear_vel: 0.3       # m/s — max forward speed
  max_linear_accel: 0.5         # m/s² — gentle acceleration
  max_linear_decel: 0.5         # m/s² — gentle deceleration
  lookahead_dist: 0.3           # m — lookahead point distance
  min_lookahead_dist: 0.2
  max_lookahead_dist: 0.6
  rotate_to_heading_angular_vel: 1.0  # rad/s — spin speed
```

### Costmaps

Obstacle sources: only the OAK-D-Lite depth point cloud (`/depth/points`).

**Local costmap** (rolling window, follows the robot):

```yaml
width: 3            # meters
height: 3
resolution: 0.05    # 5 cm cells
obstacle_layer:
  observation_sources: camera_depth
  max_obstacle_height: 2.0
  min_obstacle_height: 0.0
inflation_layer:
  inflation_radius: 0.25
```

**Global costmap** (fixed map frame):

```yaml
width: 20           # meters
height: 20
resolution: 0.05
plugins: [StaticLayer, ObstacleLayer, InflationLayer]
inflation_layer:
  inflation_radius: 0.5
```

### AMCL

Differential-drive robot model with OAK-D depth used for scan matching.

## Launching

The Nav2 stack is not auto-launched by `docker compose up`. Start it when needed:

```bash
# Launch Nav2 with the OAK-D depth topic as scan source
docker compose exec motor-control \
  ros2 launch nav2_bringup navigation_launch.py \
    use_sim_time:=False \
    params_file:=/ros2_ws/src/trackbot_bringup/config/nav2_params.yaml
```

Or via a dedicated nav2 service in docker-compose (add when you're ready for autonomous navigation).

## SLAM

For mapping, use Cartographer or slam-toolbox with the OAK-D depth data:

```bash
# Launch SLAM toolbox
docker compose exec motor-control \
  ros2 launch slam_toolbox online_async_launch.py \
    use_sim_time:=False
```

Save the map when done:

```bash
ros2 run nav2_map_server map_saver_cli -f ~/maps/my_map
```

## RViz

For visualization, launch RViz on the host (requires display):

```bash
docker compose exec -e DISPLAY=$DISPLAY oak-camera \
  rviz2 -d /ros2_ws/src/trackbot_bringup/config/trackbot.rviz
```

The `.rviz` config at `config/trackbot.rviz` includes:
- Grid (odom frame)
- TF tree
- RobotModel
- LaserScan (/depth/points as scan proxy)
- Map
- Path

## Tuning for Small Chassis

Your small tracked chassis (~10" / 25 cm long) has a tight turning radius. Key adjustments:

| Parameter | Small chassis | Large chassis | Reason |
|---|---|---|---|
| lookahead_dist | 0.3 m | 1.0 m+ | Small bot needs tighter lookahead |
| inflation_radius | 0.25 m | 0.5 m+ | Tracks can squeeze through tighter gaps |
| xy_goal_tolerance | 0.15 m | 0.25 m | Need finer positioning for tight spaces |
| desired_linear_vel | 0.3 m/s | 0.5 m/s+ | Slower is safer at this scale |
| costmap resolution | 0.05 m | 0.05 m | Same — this is fine for most robots |
