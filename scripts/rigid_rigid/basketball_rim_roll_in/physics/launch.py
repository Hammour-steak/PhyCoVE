"""Turn "throw at this point on the backboard, this hard" into a velocity.

The scene's editable launch condition is not a velocity vector: a viewer who
says "aim at the top corner instead" is talking about a place on the board,
and one who says "twice as fast" is talking about the throw, not the vector.
So the parameters kept in the scenario are the release point, the aim point and
the release speed; the simulator solves the ballistic problem for the velocity
that actually hits the aim point, and the edit vocabulary multiplies that
speed. A shot edited to double speed keeps its aim, which is what makes the
edit legible: the ball strikes the same board, twice as hard.
"""
from __future__ import annotations

import math


def solve(release, aim, speed, gravity=9.81, arc='low'):
    """Velocity that carries a projectile from ``release`` through ``aim``.

    ``arc`` picks between the two solutions a fixed speed admits: the flat
    one that arrives sooner, or the lob that arrives at the top of an arc.
    Both are found from the standard range equation for equal release and
    impact heights, corrected for the height difference ``h``:

        tan(theta) = (v^2 +- sqrt(v^4 - g (g L^2 + 2 h v^2))) / (g L)

    Raises when the speed is too low to reach the point at all, because a
    take that cannot hit its target is not a take.
    """
    dx, dz = aim[0] - release[0], aim[2] - release[2]
    dy = aim[1] - release[1]
    horizontal = math.hypot(dx, dy)
    if horizontal <= 0:
        raise ValueError('aim point must not sit straight above the release point')
    speed_sq = speed * speed
    discriminant = speed_sq * speed_sq - gravity * (gravity * horizontal ** 2 + 2 * dz * speed_sq)
    if discriminant < 0:
        raise ValueError(f'{speed:g} m/s cannot reach the aim point '
                         f'({horizontal:.2f} m out, {dz:+.2f} m up)')
    root = math.sqrt(discriminant)
    tangent = (speed_sq + (root if arc == 'high' else -root)) / (gravity * horizontal)
    angle = math.atan(tangent)
    horizontal_speed = speed * math.cos(angle)
    velocity = [dx / horizontal * horizontal_speed,
                dy / horizontal * horizontal_speed,
                speed * math.sin(angle)]
    # Time of flight, kept so a scenario can quote when the board is struck.
    flight = horizontal / horizontal_speed
    return velocity, {'launch_angle_deg': math.degrees(angle), 'flight_time_sec': flight,
                      'apex_m': release[2] + velocity[2] ** 2 / (2 * gravity)}


def spin_vector(spin, travel_xy, tilt=0.0):
    """Angular velocity for a shot: spin about the axis across the throw.

    A basketball shot leaves the hand with backspin about the horizontal axis
    perpendicular to its travel, so that is the default axis. ``tilt`` rotates
    that axis towards the vertical, which is how a shot is given sidespin: at
    +90 degrees the ball spins about the world z axis, and that is the spin
    that keeps a ball circling a rim instead of dropping straight through it.
    """
    dx, dy = travel_xy
    norm = math.hypot(dx, dy) or 1.0
    across = (-dy / norm, dx / norm, 0.0)              # horizontal, normal to travel
    up = (0.0, 0.0, 1.0)
    a = math.radians(tilt)
    axis = [across[i] * math.cos(a) + up[i] * math.sin(a) for i in range(3)]
    return [spin * axis[0], spin * axis[1], spin * axis[2]]
