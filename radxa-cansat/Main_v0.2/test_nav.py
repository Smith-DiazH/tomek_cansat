# test_nav.py corregido  posición más alejada del target
from robot_state import RobotState
from navigation  import NavigationController, _distance_m

s = RobotState()
s.update_gps(-12.0150, -77.0500, 0.0, True)   # ~1 km del target
s.update_imu(yaw=45.0, pitch=0.0, roll=0.0)
s.update_target(-12.020722, -77.057913)

# Verificar distancia antes de correr el PID
dist = _distance_m(-12.0150, -77.0500, -12.020722, -77.057913)
print(f"Distancia al target: {dist:.1f} m")

nav = NavigationController()
nav.step(s, dt=0.05)

vl, vr = s.get_motor_command()
print(f"VL={vl:.3f} rad/s   VR={vr:.3f} rad/s")
print(f"Arrived={nav.arrived}")
