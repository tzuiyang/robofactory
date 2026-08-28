"""Look at a generated design. Optional dev tool, not part of the app.

    python3 tools/view.py                     # newest URDF in runs/
    python3 tools/view.py /tmp/rover.urdf     # a specific one
    python3 tools/view.py --gravity           # let it fall over

Needs PyBullet, which the package itself does not:

    python3 -m pip install pybullet

Isaac Sim is not an option on macOS — it requires an NVIDIA GPU. Gazebo builds
on a Mac but is a fight. PyBullet is one pip install, opens a window, and gives
a slider per joint, which is all you need to answer "does this look like a
machine that could do the job".

Gravity is OFF by default and that is deliberate. Link inertias in the exported
URDF are uniform-box estimates (see `export/urdf.py`), so anything you learn
with gravity on is about the estimate, not about the robot. Kinematics — reach,
joint directions, whether the proportions look sane — is what this model is good
for, and that needs no physics at all.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def newest_urdf() -> Path | None:
    files = sorted(ROOT.glob("runs/*.urdf"), key=lambda f: f.stat().st_mtime)
    return files[-1] if files else None


def main(argv: list[str]) -> int:
    try:
        import pybullet as p
        import pybullet_data
    except ImportError:
        print("PyBullet is not installed. It is optional and only used by this viewer:\n"
              "    python3 -m pip install pybullet")
        return 1

    gravity = "--gravity" in argv
    paths = [a for a in argv[1:] if not a.startswith("-")]
    urdf = Path(paths[0]) if paths else newest_urdf()
    if urdf is None or not urdf.is_file():
        print("No URDF found. Run the app once (python3 serve.py --demo) to generate\n"
              "one into runs/, or pass a path.")
        return 1

    print(f"  {urdf}")
    print("  drag to orbit · scroll to zoom · sliders on the right move the joints")
    print("  gravity is " + ("ON" if gravity else "OFF — pass --gravity to enable")
          + "\n  ctrl-c or close the window to quit\n")

    p.connect(p.GUI)
    p.setAdditionalSearchPath(pybullet_data.getDataPath())
    p.configureDebugVisualizer(p.COV_ENABLE_GUI, 0)
    p.setGravity(0, 0, -9.81 if gravity else 0)
    p.loadURDF("plane.urdf")

    # Fixed base: without this the arm is a free body and drifts off on the
    # first slider move, which looks like a bug in the model and is not.
    body = p.loadURDF(str(urdf), useFixedBase=not gravity)
    p.resetDebugVisualizerCamera(1.2, 50, -25, [0, 0, 0.2])

    sliders = {}
    for i in range(p.getNumJoints(body)):
        info = p.getJointInfo(body, i)
        kind, name = info[2], info[1].decode()
        if kind == p.JOINT_FIXED:
            continue
        lo, hi = (info[8], info[9])
        if kind == p.JOINT_REVOLUTE and lo >= hi:      # continuous
            lo, hi = -3.14159, 3.14159
        sliders[i] = p.addUserDebugParameter(name, lo, hi, 0.0)

    print(f"  {p.getNumJoints(body)} joints, {len(sliders)} of them movable")
    try:
        while p.isConnected():
            for joint, slider in sliders.items():
                p.setJointMotorControl2(body, joint, p.POSITION_CONTROL,
                                        targetPosition=p.readUserDebugParameter(slider),
                                        force=200)
            p.stepSimulation()
            time.sleep(1 / 240)
    except (KeyboardInterrupt, Exception):
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
