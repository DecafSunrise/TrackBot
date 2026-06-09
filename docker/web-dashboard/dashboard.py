"""
TrackBot web dashboard — FastAPI + vanilla JS.
Provides real-time robot status and teleop controls via /cmd_vel.
"""
import asyncio
import json
import math
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from sensor_msgs.msg import BatteryState
import threading

app = FastAPI(title="TrackBot Dashboard")

# ── ROS2 bridge ─────────────────────────────────────────
class RosBridge(Node):
    def __init__(self):
        super().__init__('dashboard_bridge')
        self.cmd_pub = self.create_publisher(Twist, '/cmd_vel', 10)
        self.latest_odom = None
        self.latest_battery = None
        self.create_subscription(Odometry, '/odom', self.odom_cb, 10)
        self.create_subscription(BatteryState, '/battery', self.bat_cb, 10)

    def odom_cb(self, msg):
        self.latest_odom = msg

    def bat_cb(self, msg):
        self.latest_battery = msg

    def send_cmd_vel(self, vx, vy, wz):
        msg = Twist()
        msg.linear.x = vx
        msg.linear.y = vy
        msg.angular.z = wz
        self.cmd_pub.publish(msg)


rclpy.init(args=None)
bridge = RosBridge()
spin_thread = threading.Thread(target=lambda: rclpy.spin(bridge), daemon=True)
spin_thread.start()


# ── WebSocket state broadcaster ─────────────────────────
@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            data = {"type": "ping"}
            if bridge.latest_odom:
                p = bridge.latest_odom.pose.pose.position
                data["x"] = round(p.x, 3)
                data["y"] = round(p.y, 3)
                data["theta"] = round(
                    2 * math.atan2(
                        bridge.latest_odom.pose.pose.orientation.z,
                        bridge.latest_odom.pose.pose.orientation.w,
                    ), 3
                )
            if bridge.latest_battery:
                data["battery"] = round(bridge.latest_battery.percentage * 100, 1)

            await ws.send_text(json.dumps(data))
            await asyncio.sleep(0.2)
    except WebSocketDisconnect:
        pass


# ── Teleop endpoint ─────────────────────────────────────
@app.post("/cmd_vel")
async def cmd_vel(vx: float = 0, vy: float = 0, wz: float = 0):
    bridge.send_cmd_vel(vx, vy, wz)
    return {"status": "ok"}


# ── HTML dashboard ──────────────────────────────────────
@app.get("/")
async def index():
    return HTMLResponse("""
<!DOCTYPE html>
<html>
<head>
  <title>TrackBot Dashboard</title>
  <style>
    * { margin:0; padding:0; box-sizing:border-box; }
    body { font-family: monospace; background: #111; color: #0f0; padding: 20px; }
    h1 { font-size: 1.2em; margin-bottom: 16px; }
    .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; max-width: 600px; }
    .card { background: #1a1a1a; border: 1px solid #333; padding: 12px; border-radius: 4px; }
    .card h2 { font-size: 0.8em; color: #888; margin-bottom: 8px; }
    .val { font-size: 1.4em; }
    #joystick { width: 200px; height: 200px; border: 2px solid #555; border-radius: 50%;
                position: relative; background: #222; user-select: none; touch-action: none; }
    #knob { width: 60px; height: 60px; border-radius: 50%; background: #0f0;
            position: absolute; top: 70px; left: 70px; cursor: grab; opacity: 0.8; }
    .stop { background: #a00; color: #fff; border: none; padding: 10px 20px;
            font-size: 1em; cursor: pointer; border-radius: 4px; }
  </style>
</head>
<body>
  <h1>⚙ TrackBot</h1>
  <div class="grid">
    <div class="card"><h2>POSITION</h2><div class="val" id="pos">—</div></div>
    <div class="card"><h2>BATTERY</h2><div class="val" id="bat">—</div></div>
  </div>
  <div style="margin: 20px 0">
    <div id="joystick"><div id="knob"></div></div>
  </div>
  <button class="stop" onclick="sendCmd(0,0,0)">EMERGENCY STOP</button>

  <script>
    const ws = new WebSocket("ws://" + location.host + "/ws");
    ws.onmessage = e => {
      const d = JSON.parse(e.data);
      if (d.x !== undefined) document.getElementById("pos").textContent =
        d.x + ", " + d.y + "  θ=" + d.theta;
      if (d.battery !== undefined) document.getElementById("bat").textContent =
        d.battery + "%";
    };

    let dragging = false;
    const knob = document.getElementById("knob");
    const stick = document.getElementById("joystick");

    function sendCmd(vx, vy, wz) {
      fetch("/cmd_vel?" + new URLSearchParams({vx, vy, wz}), {method:"POST"});
    }

    function moveKnob(x, y) {
      const r = 70;
      const dx = x - 100, dy = y - 100;
      const dist = Math.sqrt(dx*dx + dy*dy);
      const clamp = Math.min(dist, r) / dist || 0;
      const cx = 100 + dx * clamp - 30;
      const cy = 100 + dy * clamp - 30;
      knob.style.left = cx + "px";
      knob.style.top = cy + "px";
      const vx = -((dy * clamp) / r);
      const wz = (dx * clamp) / r;
      sendCmd(Math.max(-1, Math.min(1, vx)), 0, Math.max(-1, Math.min(1, wz)));
    }

    stick.addEventListener("mousedown", e => { dragging = true; moveKnob(e.offsetX, e.offsetY); });
    window.addEventListener("mousemove", e => { if (dragging) moveKnob(e.offsetX, e.offsetY); });
    window.addEventListener("mouseup", () => { dragging = false;
      knob.style.left = "70px"; knob.style.top = "70px"; sendCmd(0,0,0); });

    stick.addEventListener("touchstart", e => {
      const t = e.touches[0]; const r = stick.getBoundingClientRect();
      moveKnob(t.clientX - r.left, t.clientY - r.top);
    });
    stick.addEventListener("touchmove", e => {
      e.preventDefault(); const t = e.touches[0]; const r = stick.getBoundingClientRect();
      moveKnob(t.clientX - r.left, t.clientY - r.top);
    });
    stick.addEventListener("touchend", () => {
      knob.style.left = "70px"; knob.style.top = "70px"; sendCmd(0,0,0);
    });
  </script>
</body>
</html>
""")
