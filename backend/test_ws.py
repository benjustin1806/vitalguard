import asyncio
import json
import requests
import websockets

async def test_websocket_broadcast():
    uri = "ws://localhost:8000/ws/alerts"
    
    # Establish websocket connection
    print(f"Connecting to {uri}...")
    async with websockets.connect(uri) as websocket:
        print("Connected! Sending a test alert trigger request...")
        
        # Prepare alert payload
        alert_payload = {
            "room": "Room 404",
            "message": "Programmatic Test Alert",
            "severity": "medium"
        }
        
        # In a separate thread/executor, fire the POST request
        # since requests is synchronous and blocking
        loop = asyncio.get_event_loop()
        def post_alert():
            response = requests.post("http://localhost:8000/trigger-alert", json=alert_payload)
            return response.json()
            
        res = await loop.run_in_executor(None, post_alert)
        print(f"POST response: {res}")
        
        # Wait for WebSocket to receive the broadcasted event
        print("Waiting to receive broadcast message via WebSocket...")
        try:
            msg = await asyncio.wait_for(websocket.recv(), timeout=5.0)
            data = json.loads(msg)
            print(f"Received WebSocket message: {data}")
            assert data["room"] == alert_payload["room"]
            assert data["message"] == alert_payload["message"]
            assert data["severity"] == alert_payload["severity"]
            print("Websocket broadcast verification: SUCCESS!")
        except asyncio.TimeoutError:
            print("Websocket broadcast verification: FAILED (Timeout - message not received)")
        except Exception as e:
            print(f"Websocket broadcast verification: FAILED with exception: {e}")

if __name__ == "__main__":
    asyncio.run(test_websocket_broadcast())
