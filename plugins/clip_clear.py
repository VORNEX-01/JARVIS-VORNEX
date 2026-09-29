PLUGIN = {
    "name": "clip_clear",
    "description": "Clear the Windows clipboard.",
    "parameters": {"type": "OBJECT", "properties": {}},
}
import subprocess
def run(parameters, player=None, session_memory=None):
    try:
        subprocess.run("cmd /c echo off | clip", shell=True, check=False)
        return "clipboard cleared"
    except Exception as e:
        return "could not clear clipboard: %s" % e