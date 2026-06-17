import sys
import json
import os

def main():
    if len(sys.argv) < 3:
        print("{}")
        return
    tool = sys.argv[2]
    try:
        payload = json.loads(sys.argv[3])
    except:
        payload = {}
        
    if tool == "start_recording":
        out_dir = payload.get("output_dir", "")
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
            with open(os.path.join(out_dir, "recording.json"), "w") as f:
                json.dump({"status": "recording"}, f)
        print(json.dumps({"success": True}))
        return
        
    if tool == "stop_recording":
        print(json.dumps({"success": True}))
        return
        
    if tool == "list_windows":
        print(json.dumps({"windows": [{"pid": 1234, "window_id": 5678, "title": "Calculator"}]}))
        return
        
    if tool == "launch_app":
        print(json.dumps({"pid": 1234, "windows": [{"window_id": 5678}]}))
        return
        
    if tool == "get_window_state":
        print(json.dumps({"element_count": 1, "tree_markdown": "[1] AXStaticText 'display is 248171'", "elements": [{"element_index": 1, "name": "display is 248171"}]}))
        return
        
    print(json.dumps({"success": True}))

if __name__ == "__main__":
    main()
