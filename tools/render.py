"""Render a generated URDF to a PNG. Optional dev tool, not part of the app.

    python3 tools/render.py out_dir

Needs PyBullet, which the package itself does not:

    python3 -m pip install pybullet

Headless (ER_TINY_RENDERER + DIRECT), so it works over SSH and in CI, and writes
the PNG by hand rather than pulling in Pillow. Links are coloured by role — the
point is to be able to tell at a glance whether the machine is assembled the way
you meant, which is the one class of error a URDF parser cannot catch.

It found two on its first run (log.md, 2026-08-28): wheels buried inside the
chassis, and a chassis wider than its own track.
"""

import sys, math, struct, zlib
import pybullet as p, pybullet_data

# link-name substring -> RGBA
COLORS = [
    ("wheel",   (0.16,0.16,0.18,1)),
    ("panel",   (0.45,0.47,0.52,1)),
    ("head",    (0.30,0.62,0.85,1)),
    ("base",    (0.38,0.40,0.45,1)),
    ("shoulder",(0.91,0.45,0.28,1)),
    ("elbow",   (0.91,0.45,0.28,1)),
    ("wrist",   (0.91,0.45,0.28,1)),
    ("link",    (0.80,0.82,0.86,1)),
    ("effector",(0.25,0.72,0.55,1)),
]
def colour_for(name):
    for key, c in COLORS:
        if key in name:
            return c
    return (0.7,0.7,0.72,1)

def png(path, W, H, rgb):
    raw = bytearray()
    for y in range(H):
        raw.append(0)
        row = rgb[y*W*4:(y+1)*W*4]
        for x in range(W):
            raw += bytes(row[x*4:x*4+3])
    def chunk(t,d):
        c=t+d; return struct.pack(">I",len(d))+c+struct.pack(">I",zlib.crc32(c)&0xffffffff)
    open(path,"wb").write(b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB",W,H,8,2,0,0,0))
        + chunk(b"IDAT", zlib.compress(bytes(raw),6)) + chunk(b"IEND", b""))

def render(urdf, out, poses, dist, target, yaw=52, pitch=-18):
    cid = p.connect(p.DIRECT)
    p.setAdditionalSearchPath(pybullet_data.getDataPath())
    p.setGravity(0,0,0)
    plane = p.loadURDF("plane.urdf")
    p.changeVisualShape(plane, -1, rgbaColor=(0.97,0.97,0.98,1))
    b = p.loadURDF(urdf, useFixedBase=True)

    names = {-1: p.getBodyInfo(b)[0].decode()}
    for i in range(p.getNumJoints(b)):
        names[i] = p.getJointInfo(b,i)[12].decode()
    for idx, nm in names.items():
        p.changeVisualShape(b, idx, rgbaColor=colour_for(nm))
    for jname, val in poses.items():
        for i in range(p.getNumJoints(b)):
            if p.getJointInfo(b,i)[1].decode()==jname:
                p.resetJointState(b,i,val)

    W,H = 1200, 800
    view = p.computeViewMatrixFromYawPitchRoll(target, dist, yaw, pitch, 0, 2)
    proj = p.computeProjectionMatrixFOV(42, W/H, 0.01, 20)
    img = p.getCameraImage(W,H,view,proj, lightDirection=[1.2,1.0,2.0],
                           shadow=1, renderer=p.ER_TINY_RENDERER)
    png(out, W, H, img[2]); print("wrote", out)
    p.disconnect(cid)

R = math.radians
D = sys.argv[1]
render("/tmp/bench_arm.urdf", D+"/arm.png",
       {"base_to_shoulder": R(-55), "upper_link_to_elbow": R(70), "fore_link_to_wrist": R(35)},
       dist=0.95, target=(0.08,0,0.22))
render("/tmp/mobile_manipulator.urdf", D+"/mm.png",
       {"drive_base_to_shoulder": R(-50), "upper_link_to_elbow": R(65), "fore_link_to_wrist": R(30)},
       dist=1.45, target=(0.05,0,0.30))
render("/tmp/rover.urdf", D+"/rover.png", {}, dist=0.85, target=(0,0,0.15), yaw=38, pitch=-14)
