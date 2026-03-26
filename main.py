"""
Golden State Warriors Game Notifier with Philips Hue Lights
Google Cloud Function to detect Warriors games and trigger light notifications

This function:
1. Checks ESPN API daily for Warriors games
2. If a game is found, schedules Hue light notifications:
   - 15 minutes before: Pulse with opposing team colors
   - At game time: Flash with Warriors colors
"""

import os
import json
import requests
from datetime import datetime, timedelta
import pytz
from google.cloud import secretmanager
from google.cloud import tasks_v2
import base64


# Team Colors (hex codes)
WARRIORS_COLORS = {
    'primary': '#006BB6',  # Warriors Blue
    'secondary': '#FDB927'  # Warriors Gold
}

# Opponent team colors mapping (subset of common opponents)
TEAM_COLORS = {
    'Lakers': {'primary': '#552583', 'secondary': '#FDB927'},
    'Clippers': {'primary': '#C8102E', 'secondary': '#1D428A'},
    'Suns': {'primary': '#1D1160', 'secondary': '#E56020'},
    'Kings': {'primary': '#5A2D81', 'secondary': '#63727A'},
    'Mavericks': {'primary': '#00538C', 'secondary': '#002B5E'},
    'Nuggets': {'primary': '#0E2240', 'secondary': '#FEC524'},
    'Grizzlies': {'primary': '#5D76A9', 'secondary': '#12173F'},
    'Pelicans': {'primary': '#0C2340', 'secondary': '#C8102E'},
    'Rockets': {'primary': '#CE1141', 'secondary': '#000000'},
    'Spurs': {'primary': '#C4CED4', 'secondary': '#000000'},
    'Thunder': {'primary': '#007AC1', 'secondary': '#EF3B24'},
    'Trail Blazers': {'primary': '#E03A3E', 'secondary': '#000000'},
    'Jazz': {'primary': '#002B5C', 'secondary': '#00471B'},
    'Timberwolves': {'primary': '#0C2340', 'secondary': '#236192'},
    'Heat': {'primary': '#98002E', 'secondary': '#F9A01B'},
    'Celtics': {'primary': '#007A33', 'secondary': '#BA9653'},
    'Nets': {'primary': '#000000', 'secondary': '#FFFFFF'},
    'Knicks': {'primary': '#006BB6', 'secondary': '#F58426'},
    'Raptors': {'primary': '#CE1141', 'secondary': '#000000'},
    '76ers': {'primary': '#006BB6', 'secondary': '#ED174C'},
    'Bucks': {'primary': '#00471B', 'secondary': '#EEE1C6'},
    'Bulls': {'primary': '#CE1141', 'secondary': '#000000'},
    'Cavaliers': {'primary': '#860038', 'secondary': '#041E42'},
    'Pacers': {'primary': '#002D62', 'secondary': '#FDBB30'},
    'Pistons': {'primary': '#C8102E', 'secondary': '#1D42BA'},
    'Hawks': {'primary': '#E03A3E', 'secondary': '#C1D32F'},
    'Hornets': {'primary': '#1D1160', 'secondary': '#00788C'},
    'Magic': {'primary': '#0077C0', 'secondary': '#C4CED4'},
    'Wizards': {'primary': '#002B5C', 'secondary': '#E31837'},
}


class SecretManager:
    """Helper class to retrieve and update secrets in Google Secret Manager"""
    
    def __init__(self, project_id):
        self.project_id = project_id
        self.client = secretmanager.SecretManagerServiceClient()
    
    def get_secret(self, secret_name):
        """Retrieve a secret value"""
        name = f"projects/{self.project_id}/secrets/{secret_name}/versions/latest"
        response = self.client.access_secret_version(request={"name": name})
        return response.payload.data.decode('UTF-8')
    
    def update_secret(self, secret_name, secret_value):
        """Add a new version of a secret (updates the secret value)"""
        try:
            parent = f"projects/{self.project_id}/secrets/{secret_name}"
            payload = secret_value.encode('UTF-8')
            
            response = self.client.add_secret_version(
                request={
                    "parent": parent,
                    "payload": {"data": payload}
                }
            )
            
            print(f"Updated secret {secret_name} to new version: {response.name}")
            return True
        except Exception as e:
            print(f"Error updating secret {secret_name}: {e}")
            return False


class HueAPI:
    """Philips Hue Remote API client with OAuth token refresh"""
    
    def __init__(self, client_id, client_secret, refresh_token, bridge_id, secret_manager=None, project_id=None):
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.bridge_id = bridge_id
        self.access_token = None
        self.cert_path = '/tmp/hue_cert.pem'  # Certificate will be stored here
        self.secret_manager = secret_manager  # Optional: for persisting new refresh tokens
        self.project_id = project_id  # Optional: for persisting new refresh tokens
        
    def refresh_access_token(self):
        """Refresh the OAuth access token using refresh token"""
        url = "https://api.meethue.com/v2/oauth2/token"
        
        data = {
            'grant_type': 'refresh_token',
            'refresh_token': self.refresh_token,
            'client_id': self.client_id,
            'client_secret': self.client_secret
        }
        
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        
        # Try with certificate first, fall back to no verification
        try:
            response = requests.post(url, data=data, headers=headers, verify=self.cert_path)
            response.raise_for_status()
        except Exception as cert_error:
            print(f"Certificate verification failed: {cert_error}")
            print("Falling back to no SSL verification (not recommended for production)")
            response = requests.post(url, data=data, headers=headers, verify=False)
            response.raise_for_status()
        
        token_data = response.json()
        self.access_token = token_data['access_token']
        
        # Update refresh token if a new one is provided
        if 'refresh_token' in token_data:
            new_refresh_token = token_data['refresh_token']
            self.refresh_token = new_refresh_token
            
            # Persist the new refresh token to Secret Manager
            if self.secret_manager and self.project_id:
                print(f"New refresh token received, updating Secret Manager...")
                success = self.secret_manager.update_secret('hue_refresh_token', new_refresh_token)
                if success:
                    print("✓ Refresh token successfully persisted to Secret Manager")
                else:
                    print("✗ Warning: Failed to persist refresh token to Secret Manager")
            else:
                print("Warning: SecretManager not provided, new refresh token not persisted")
        
        return self.access_token
    
    def get_lights(self):
        """Get all lights connected to the bridge"""
        if not self.access_token:
            self.refresh_access_token()
        
        url = f"https://api.meethue.com/route/api/{self.bridge_id}/lights"
        headers = {
            'Authorization': f'Bearer {self.access_token}'
        }
        
        try:
            response = requests.get(url, headers=headers, verify=self.cert_path)
            response.raise_for_status()
        except:
            response = requests.get(url, headers=headers, verify=False)
            response.raise_for_status()
        
        return response.json()
    
    def set_light_state(self, light_id, state):
        """Set the state of a specific light"""
        if not self.access_token:
            self.refresh_access_token()
        
        url = f"https://api.meethue.com/route/api/{self.bridge_id}/lights/{light_id}/state"
        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json'
        }
        
        try:
            response = requests.put(url, json=state, headers=headers, verify=self.cert_path)
            response.raise_for_status()
        except:
            response = requests.put(url, json=state, headers=headers, verify=False)
            response.raise_for_status()
        
        return response.json()
    
    def hex_to_xy(self, hex_color):
        """Convert hex color to Hue XY color space"""
        # Remove # if present
        hex_color = hex_color.lstrip('#')
        
        # Convert to RGB
        r = int(hex_color[0:2], 16) / 255.0
        g = int(hex_color[2:4], 16) / 255.0
        b = int(hex_color[4:6], 16) / 255.0
        
        # Apply gamma correction
        r = pow((r + 0.055) / 1.055, 2.4) if r > 0.04045 else r / 12.92
        g = pow((g + 0.055) / 1.055, 2.4) if g > 0.04045 else g / 12.92
        b = pow((b + 0.055) / 1.055, 2.4) if b > 0.04045 else b / 12.92
        
        # Convert to XYZ
        X = r * 0.649926 + g * 0.103455 + b * 0.197109
        Y = r * 0.234327 + g * 0.743075 + b * 0.022598
        Z = r * 0.000000 + g * 0.053077 + b * 1.035763
        
        # Calculate xy
        total = X + Y + Z
        if total == 0:
            return [0.0, 0.0]
        
        x = X / total
        y = Y / total
        
        return [x, y]
    
    def pulse_colors(self, colors, duration_seconds=60):
        """Pulse lights alternating between colors (for pre-game notification)"""
        lights = self.get_lights()
        
        # Store original states
        original_states = {}
        for light_id in lights.keys():
            original_states[light_id] = {
                'on': lights[light_id]['state']['on'],
                'bri': lights[light_id]['state'].get('bri', 254),
                'xy': lights[light_id]['state'].get('xy', [0.3, 0.3])
            }
        
        # Pulse pattern: alternate between colors with breathing effect
        # This simplified version sets colors - actual pulsing would need
        # multiple API calls or use of the 'transitiontime' parameter
        
        for light_id in lights.keys():
            # Set to first color with transition
            xy_color = self.hex_to_xy(colors[0])
            state = {
                'on': True,
                'xy': xy_color,
                'bri': 254,
                'transitiontime': 10  # 1 second (in 100ms increments)
            }
            self.set_light_state(light_id, state)
        
        # Note: For continuous pulsing, you'd need to implement a loop
        # or use Cloud Scheduler to call this function multiple times
        # For simplicity, this does a single color transition
        
        return original_states
    
    def flash_colors(self, colors, flash_count=5):
        """Flash lights alternating between colors (for game start notification)"""
        lights = self.get_lights()
        
        # Store original states
        original_states = {}
        for light_id in lights.keys():
            original_states[light_id] = {
                'on': lights[light_id]['state']['on'],
                'bri': lights[light_id]['state'].get('bri', 254),
                'xy': lights[light_id]['state'].get('xy', [0.3, 0.3])
            }
        
        # Flash between Warriors colors (blue and gold)
        import time
        for i in range(flash_count):
            color = colors[i % len(colors)]  # Alternate between colors
            xy_color = self.hex_to_xy(color)
            
            for light_id in lights.keys():
                state = {
                    'on': True,
                    'xy': xy_color,
                    'bri': 254,
                    'transitiontime': 5  # 0.5 seconds (in 100ms increments)
                }
                self.set_light_state(light_id, state)
            
            time.sleep(1.0)  # Wait 1 second between color changes
        
        return original_states
    
    def restore_lights(self, original_states):
        """Restore lights to original state"""
        for light_id, state in original_states.items():
            self.set_light_state(light_id, state)


class ESPNGameChecker:
    """Check ESPN API for Warriors games"""
    
    WARRIORS_TEAM_ID = "9"  # Golden State Warriors team ID in ESPN
    
    @staticmethod
    def get_todays_game():
        """
        Check if Warriors have a game today
        Returns: dict with game info or None if no game
        """
        today = datetime.now(pytz.timezone('America/Los_Angeles')).strftime('%Y%m%d')
        
        url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{ESPNGameChecker.WARRIORS_TEAM_ID}/schedule"
        
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            # Look for today's game in the events
            events = data.get('events', [])
            
            for event in events:
                game_date = event.get('date', '')
                # Parse the game date (format: 2026-01-29T03:00Z)
                game_datetime = datetime.fromisoformat(game_date.replace('Z', '+00:00'))
                game_date_str = game_datetime.astimezone(pytz.timezone('America/Los_Angeles')).strftime('%Y%m%d')
                
                if game_date_str == today:
                    # Found today's game
                    competitions = event.get('competitions', [{}])[0]
                    competitors = competitions.get('competitors', [])
                    
                    # Determine home/away and opponent
                    home_team = None
                    away_team = None
                    is_warriors_home = False
                    opponent_name = None
                    
                    for competitor in competitors:
                        team = competitor.get('team', {})
                        if team.get('id') == ESPNGameChecker.WARRIORS_TEAM_ID:
                            is_warriors_home = competitor.get('homeAway') == 'home'
                        else:
                            opponent_name = team.get('displayName', 'Unknown')
                    
                    return {
                        'game_time': game_datetime.astimezone(pytz.timezone('America/Los_Angeles')),
                        'opponent': opponent_name,
                        'is_home_game': is_warriors_home,
                        'event_name': event.get('name', 'Warriors Game')
                    }
            
            # No game found today
            return None
            
        except requests.exceptions.RequestException as e:
            print(f"Error fetching ESPN data: {e}")
            return None


def setup_hue_certificate(cert_content):
    """Write Hue certificate to temporary file"""
    cert_path = '/tmp/hue_cert.pem'
    try:
        print(f"Setting up certificate at {cert_path}")
        print(f"Certificate content length: {len(cert_content) if cert_content else 0} chars")
        
        if not cert_content:
            print("WARNING: Certificate content is empty!")
            return None
            
        with open(cert_path, 'w') as f:
            f.write(cert_content)
        
        # Verify the file was written
        with open(cert_path, 'r') as f:
            written_content = f.read()
            print(f"Certificate file written successfully, size: {len(written_content)} chars")
        
        return cert_path
    except Exception as e:
        print(f"Error writing certificate: {e}")
        return None


def morning_check(request):
    """
    Main Cloud Function entry point - runs daily at 8 AM PT
    Checks for Warriors game today and schedules notifications if found
    """
    # Get project ID from environment
    project_id = os.environ.get('GCP_PROJECT')
    location = os.environ.get('FUNCTION_REGION', 'us-west1')
    
    # Initialize Secret Manager
    sm = SecretManager(project_id)
    
    # Retrieve secrets
    hue_client_id = sm.get_secret('hue_client_id')
    hue_client_secret = sm.get_secret('hue_client_secret')
    hue_refresh_token = sm.get_secret('hue_refresh_token')
    hue_bridge_id = sm.get_secret('hue_bridge_id')
    hue_cert = sm.get_secret('hue_certificate')
    
    # Setup certificate
    setup_hue_certificate(hue_cert)
    
    # Check for today's game
    game_info = ESPNGameChecker.get_todays_game()
    
    if not game_info:
        print("No Warriors game today")
        return {'status': 'no_game', 'message': 'No Warriors game scheduled for today'}
    
    print(f"Found game: {game_info['event_name']}")
    print(f"Game time: {game_info['game_time']}")
    print(f"Opponent: {game_info['opponent']}")
    print(f"Home game: {game_info['is_home_game']}")
    
    # Calculate notification times
    game_time = game_info['game_time']
    pregame_time = game_time - timedelta(minutes=15)
    
    # Get opponent colors (default to generic if not in our mapping)
    opponent_short_name = game_info['opponent'].split()[-1]  # Get last word (e.g., "Lakers" from "Los Angeles Lakers")
    opponent_colors = TEAM_COLORS.get(opponent_short_name, {'primary': '#FF0000', 'secondary': '#0000FF'})
    
    # Schedule pre-game notification (15 min before)
    schedule_notification(
        project_id=project_id,
        location=location,
        notification_type='pregame',
        trigger_time=pregame_time,
        colors=[opponent_colors['primary'], opponent_colors['secondary']],
        hue_client_id=hue_client_id,
        hue_client_secret=hue_client_secret,
        hue_refresh_token=hue_refresh_token,
        hue_bridge_id=hue_bridge_id,
        hue_cert=hue_cert
    )
    
    # Schedule game-time notification
    schedule_notification(
        project_id=project_id,
        location=location,
        notification_type='gametime',
        trigger_time=game_time,
        colors=[WARRIORS_COLORS['primary'], WARRIORS_COLORS['secondary']],
        hue_client_id=hue_client_id,
        hue_client_secret=hue_client_secret,
        hue_refresh_token=hue_refresh_token,
        hue_bridge_id=hue_bridge_id,
        hue_cert=hue_cert
    )
    
    return {
        'status': 'success',
        'game_info': {
            'opponent': game_info['opponent'],
            'game_time': game_time.isoformat(),
            'is_home': game_info['is_home_game']
        },
        'notifications_scheduled': {
            'pregame': pregame_time.isoformat(),
            'gametime': game_time.isoformat()
        }
    }


def schedule_notification(project_id, location, notification_type, trigger_time, colors, 
                          hue_client_id, hue_client_secret, hue_refresh_token, 
                          hue_bridge_id, hue_cert):
    """
    Schedule a one-time Cloud Task to trigger notification at specific time
    """
    try:
        # Create Cloud Tasks client
        client = tasks_v2.CloudTasksClient()
        
        # Queue name (we'll use the default queue)
        queue_name = f"projects/{project_id}/locations/{location}/queues/default"
        print(f"Using queue: {queue_name}")
        
        # Gen2 Cloud Function URL (Cloud Run format)
        function_url = os.environ.get('NOTIFICATION_FUNCTION_URL', 
                                      'https://warriors-notification-sur5hdfshq-uw.a.run.app')
        print(f"Target function URL: {function_url}")
        
        # Prepare payload
        payload = {
            'notification_type': notification_type,
            'colors': colors,
            'hue_client_id': hue_client_id,
            'hue_client_secret': hue_client_secret,
            'hue_refresh_token': hue_refresh_token,
            'hue_bridge_id': hue_bridge_id,
            'hue_cert': hue_cert
        }
        
        # Convert trigger time to timestamp
        schedule_time = trigger_time.timestamp()
        print(f"Scheduling for timestamp: {schedule_time} ({trigger_time})")
        
        # Create the task
        task = {
            'http_request': {
                'http_method': tasks_v2.HttpMethod.POST,
                'url': function_url,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps(payload).encode('utf-8'),
                'oidc_token': {
                    'service_account_email': f"9010317804-compute@developer.gserviceaccount.com"
                }
            },
            'schedule_time': {'seconds': int(schedule_time)}
        }
        
        # Create the task
        print(f"Creating task in queue {queue_name}...")
        response = client.create_task(parent=queue_name, task=task)
        print(f"✓ Scheduled {notification_type} notification for {trigger_time}")
        print(f"  Task name: {response.name}")
        return True
        
    except Exception as e:
        print(f"✗ Error scheduling task: {e}")
        print(f"  Error type: {type(e).__name__}")
        print(f"  Full error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def trigger_notification(request):
    """
    Cloud Function entry point for triggering notifications
    Called by Cloud Tasks at scheduled times
    """
    try:
        request_json = request.get_json()
        
        notification_type = request_json['notification_type']
        colors = request_json['colors']
        
        # Setup certificate FIRST (before HueAPI tries to use it)
        setup_hue_certificate(request_json['hue_cert'])
        
        # Get project ID for Secret Manager updates
        project_id = os.environ.get('GCP_PROJECT')
        
        # Initialize Secret Manager for token persistence
        sm = SecretManager(project_id)
        
        # Initialize Hue API with SecretManager for automatic token persistence
        hue = HueAPI(
            client_id=request_json['hue_client_id'],
            client_secret=request_json['hue_client_secret'],
            refresh_token=request_json['hue_refresh_token'],
            bridge_id=request_json['hue_bridge_id'],
            secret_manager=sm,
            project_id=project_id
        )
        
        # Trigger appropriate notification and restore lights after
        if notification_type == 'pregame':
            print("Triggering pre-game flash notification")
            original_states = hue.flash_colors(colors, flash_count=5)
            print("Restoring lights to original state")
            hue.restore_lights(original_states)
        elif notification_type == 'gametime':
            print("Triggering game-time flash notification")
            original_states = hue.flash_colors(colors, flash_count=5)
            print("Restoring lights to original state")
            hue.restore_lights(original_states)
        
        return {'status': 'success', 'notification_type': notification_type}
        
    except Exception as e:
        print(f"Error triggering notification: {e}")
        return {'status': 'error', 'message': str(e)}, 500
